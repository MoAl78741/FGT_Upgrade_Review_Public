"""Security boundaries use isolated databases and inert payloads."""
import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.main import app
from backend.database import get_db
from backend.models import Base, ScrapeJob
from backend import queue, security
from backend.routers import jobs, uploads


@pytest.fixture
def hosted(monkeypatch, tmp_path):
    cfg = replace(security.settings, edition='public', origin='https://review.example', uploads=tmp_path, scrape_enabled=True)
    for module in (security, queue, jobs, uploads):
        monkeypatch.setattr(module, 'settings', cfg)
    monkeypatch.setattr(queue, 'start', lambda: None)
    monkeypatch.setattr(queue, 'stop', lambda: None)
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    def database():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = database
    monkeypatch.setattr(queue, 'SessionLocal', sessions)
    with TestClient(app, base_url='https://review.example', headers={'Origin': 'https://review.example'}) as a, TestClient(app, base_url='https://review.example', headers={'Origin': 'https://review.example'}) as b:
        yield a, b, sessions, cfg
    app.dependency_overrides.clear()
    engine.dispose()


def upload(client, name='fortios-v7.4.11.pdf', body=b'%PDF-1.7\nfixture'):
    client.get('/api/capabilities')
    return client.post('/api/jobs/upload', files=[('files', (name, body, 'application/pdf'))])


def test_owners_cannot_list_read_delete_cancel_or_retry_other_reports(hosted):
    a, b, _, _ = hosted
    a.get('/api/capabilities')
    job = upload(a)
    assert job.status_code == 201, job.text
    key = job.json()['id']
    assert len(a.get('/api/jobs').json()) == 1
    b.get('/api/capabilities')
    assert b.get('/api/jobs').json() == []
    for method, suffix in [('get', ''), ('delete', ''), ('post', '/cancel'), ('post', '/retry')]:
        assert getattr(b, method)(f'/api/jobs/{key}{suffix}').status_code == 404
    assert a.get(f'/api/jobs/{key}').status_code == 200
    assert a.post(f'/api/jobs/{key}/cancel').json()['status'] == 'cancelled'
    assert a.delete(f'/api/jobs/{key}').status_code == 204


def test_session_cookie_security_and_cross_origin(hosted):
    a, _, _, _ = hosted
    cookie = a.get('/api/capabilities').headers['set-cookie'].lower()
    assert all(x in cookie for x in ('secure', 'httponly', 'samesite=strict', 'max-age=86400'))
    assert a.post('/api/jobs', headers={'Origin': 'https://evil.example'}, json={}).status_code == 403
    assert a.get('/api/jobs', headers={'Host': 'evil.example'}).status_code == 400
    with TestClient(app, base_url='https://review.example') as anonymous:
        assert anonymous.post('/api/jobs', json={}).status_code == 403


def test_public_scraping_and_grid_url_rejected(hosted):
    a, _, _, _ = hosted
    a.get('/api/capabilities')
    req = {'from_version': '7.4.10', 'to_version': '7.4.11'}
    assert a.post('/api/jobs', json=req).status_code == 403
    assert a.post('/api/jobs', json={**req, 'grid_url': 'http://127.0.0.1:22'}).status_code == 422
    assert not a.get('/api/capabilities').json()['scraping']


def test_invalid_upload_cleans_files_and_row(hosted):
    a, _, sessions, cfg = hosted
    assert upload(a, body=b'not a PDF').status_code == 422
    assert upload(a, body=b'').status_code == 422
    assert a.get('/api/jobs').json() == []
    assert not list(cfg.uploads.iterdir())


def test_duplicate_versions_and_too_many_files(hosted):
    a, _, _, _ = hosted
    a.get('/api/capabilities')
    files = [('files', ('v7.4.11.pdf', b'%PDF-1.7\n', 'application/pdf'))] * 2
    assert a.post('/api/jobs/upload', files=files).status_code == 422
    assert a.post('/api/jobs/upload', files=files * 3).status_code in (400, 422)
    assert a.get('/api/jobs').json() == []


def test_limits_and_filename_path_isolation(hosted, monkeypatch):
    a, _, _, cfg = hosted
    cfg = replace(cfg, file_bytes=20, total_bytes=30)
    for module in (uploads, queue, security):
        monkeypatch.setattr(module, 'settings', cfg)
    assert upload(a, body=b'%PDF-' + b'a' * 30).status_code == 413
    job = upload(a, '../../v7.4.11.pdf').json()
    paths = list((cfg.uploads / job['id']).glob('*.pdf'))
    assert len(paths) == 1 and paths[0].name != 'v7.4.11.pdf'
    assert not (cfg.uploads / 'v7.4.11.pdf').exists()


def test_session_queue_limit_and_expiry(hosted):
    a, _, sessions, cfg = hosted
    job = upload(a).json()
    assert upload(a, 'v7.4.10.pdf').status_code == 429
    with sessions() as db:
        row = db.get(ScrapeJob, job['id'])
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
    assert a.get(f"/api/jobs/{job['id']}").status_code == 404
    with sessions() as db:
        queue.clean_expired(db)
        assert db.get(ScrapeJob, job['id']) is None
    assert not (cfg.uploads / job['id']).exists()


def test_partial_job_keeps_success_and_failure(hosted, monkeypatch):
    a, _, sessions, _ = hosted
    a.get('/api/capabilities')
    files = [('files', (f'v{v}.pdf', b'%PDF-1.7\n', 'application/pdf')) for v in ['7.4.10', '7.4.11']]
    key = a.post('/api/jobs/upload', files=files).json()['id']
    def parse(job_id, path, deadline):
        if '7.4.11' in path.name:
            raise ValueError('Malformed PDF')
        return ('7.4.10', {'known_issues': []}, [], {}, {})
    monkeypatch.setattr(queue, 'parse_isolated', parse)
    with sessions() as db:
        db.get(ScrapeJob, key).status = 'running'
        db.commit()
    queue.run_pdf(key)
    result = a.get(f'/api/jobs/{key}').json()
    assert result['status'] == 'partial'
    assert [f['status'] for f in result['file_outcomes']] == ['completed', 'failed']
    assert result['warnings'] and result['versions'] == ['7.4.10']
    assert len(result['provenance']['documents']) == 2


def test_legacy_script_breakout_is_inert():
    from bs4 import BeautifulSoup
    from fgt_upgrade.report import generate_html
    payload = '</script><script>/* AUDIT_INERT */</script><img src=x onerror=alert(1)>'
    html = generate_html({'7.4.11': {'known_issues': [{'Bug ID': '1', 'Description': payload, 'category': payload}]}}, [], '7.4.10', '7.4.11', {})
    soup = BeautifulSoup(html, 'html.parser')
    assert not soup.find('img', onerror=True)
    assert not any(s.string == '/* AUDIT_INERT */' for s in soup.find_all('script'))
    assert '\\u003c/script\\u003e' in html


def test_streamed_body_limit_without_content_length(hosted, monkeypatch):
    import asyncio
    from backend.security import RequestSecurity
    _, _, _, cfg = hosted
    monkeypatch.setattr(security, 'settings', replace(cfg, total_bytes=1))
    messages = iter([{'type': 'http.request', 'body': b'x' * (1024**2), 'more_body': True}, {'type': 'http.request', 'body': b'xx', 'more_body': False}])
    async def consume(scope, receive, send):
        while (await receive()).get('more_body'):
            pass
    async def receive():
        return next(messages)
    async def send(message):
        pass
    scope = {'type': 'http', 'path': '/api/jobs/upload', 'method': 'POST', 'headers': [(b'host', b'review.example'), (b'origin', b'https://review.example')], 'client': ('127.0.0.1', 123)}
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        asyncio.run(RequestSecurity(consume)(scope, receive, send))
    assert error.value.status_code == 413


def test_global_queue_capacity(hosted, monkeypatch):
    a, b, _, cfg = hosted
    monkeypatch.setattr(queue, 'settings', replace(cfg, queue_size=1))
    assert upload(a).status_code == 201
    assert upload(b).status_code == 429


def test_restart_preserves_pending_and_marks_interrupted(hosted, monkeypatch, tmp_path):
    _, _, sessions, _ = hosted
    monkeypatch.setattr(queue, 'DB_PATH', tmp_path / 'isolated.db')
    with sessions() as db:
        for key, state in [('interrupted', 'running'), ('queued', 'pending'), ('incomplete-upload', 'uploading')]:
            db.add(ScrapeJob(id=key, from_version='7.4.10', to_version='7.4.11', status=state))
        db.commit()
    # Invoke actual recovery but avoid starting a dispatcher against fixture-owned connections.
    monkeypatch.setattr(queue.threading, 'Thread', lambda **kwargs: type('Idle', (), {'start': lambda s: None, 'join': lambda s, **k: None})())
    # Fixture disables lifecycle functions; retrieve actual implementation from module source.
    import importlib.util
    spec = importlib.util.spec_from_file_location('backend.queue_recovery_test', Path(queue.__file__))
    recovery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recovery)
    recovery.DB_PATH = tmp_path / 'recovery.db'
    recovery.SessionLocal = sessions
    recovery.settings = queue.settings
    recovery.initialize_database = lambda: None  # Fixture schema belongs to its isolated engine.
    recovery.start()
    try:
        with sessions() as db:
            assert db.get(ScrapeJob, 'interrupted').status == 'failed'
            assert db.get(ScrapeJob, 'incomplete-upload').status == 'failed'
            assert db.get(ScrapeJob, 'queued').status == 'pending'
    finally:
        recovery.stop()


def test_cancel_terminates_active_process(hosted):
    import subprocess
    import sys
    a, _, sessions, _ = hosted
    key = upload(a).json()['id']
    with sessions() as db:
        db.get(ScrapeJob, key).status = 'running'
        db.commit()
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
    queue.CHILDREN[key] = process
    try:
        result = a.post(f'/api/jobs/{key}/cancel')
        assert result.status_code == 200
        assert result.json()['status'] == 'cancelled'
        assert process.poll() is not None and process.returncode < 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        queue.CHILDREN.pop(key, None)


def test_parser_timeout_terminates_child(hosted, monkeypatch):
    import subprocess
    import sys
    import time
    a, _, sessions, cfg = hosted
    key = upload(a).json()['id']
    with sessions() as db:
        db.get(ScrapeJob, key).status = 'running'
        db.commit()
    real_popen = subprocess.Popen
    children = []
    def sleeper(*args, **kwargs):
        process = real_popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
        children.append(process)
        return process
    monkeypatch.setattr(queue.subprocess, 'Popen', sleeper)
    path = next((cfg.uploads / key).glob('*.pdf'))
    with pytest.raises(RuntimeError, match='time limit'):
        queue.parse_isolated(key, path, time.monotonic() + 0.1)
    assert children and children[0].poll() is not None
    assert key not in queue.CHILDREN


def test_retry_keeps_successful_files(hosted, monkeypatch):
    a, _, sessions, _ = hosted
    a.get('/api/capabilities')
    files = [('files', (f'v{v}.pdf', b'%PDF-1.7\n', 'application/pdf')) for v in ['7.4.10', '7.4.11']]
    key = a.post('/api/jobs/upload', files=files).json()['id']
    with sessions() as db:
        job = db.get(ScrapeJob, key)
        job.status = 'partial'
        job.file_outcomes_json = json.dumps([{'name': 'v7.4.10.pdf', 'status': 'completed', 'version': '7.4.10'}, {'name': 'v7.4.11.pdf', 'status': 'failed'}])
        job.all_data_json = json.dumps({'7.4.10': {'known_issues': [{'Bug ID': '1', 'Description': 'Retained original'}]}})
        db.commit()
    assert a.post(f'/api/jobs/{key}/retry').status_code == 200
    calls = []
    def parse(job_id, path, deadline):
        calls.append(path.name)
        return ('7.4.11', {'known_issues': []}, [], {}, {})
    monkeypatch.setattr(queue, 'parse_isolated', parse)
    with sessions() as db:
        db.get(ScrapeJob, key).status = 'running'
        db.commit()
    queue.run_pdf(key)
    result = a.get(f'/api/jobs/{key}').json()
    assert result['status'] == 'completed'
    assert len(calls) == 1 and '7.4.11' in calls[0]
    assert result['all_data']['7.4.10']['known_issues'][0]['Description'] == 'Retained original'


@pytest.mark.parametrize('edition', ['private', 'public'])
def test_image_health_probe_uses_external_host_for_strict_origin(client, monkeypatch, edition):
    import io
    from backend import healthcheck
    cfg=replace(security.settings, edition=edition, team_auth=True, origin='https://health.example:8442')
    monkeypatch.setattr(security,'settings',cfg)
    monkeypatch.setenv('APP_ORIGIN',cfg.origin)
    assert client.get('/api/health').status_code == 400  # A localhost/default Host is rejected.
    def local_listener(request, timeout):
        result=client.get('/api/health', headers={'Host':request.get_header('Host')})
        assert result.status_code == 200
        return io.BytesIO(result.content)
    monkeypatch.setattr(healthcheck,'urlopen',local_listener)
    healthcheck.main()


def test_public_larger_batches_keep_byte_and_ownership_limits(hosted, monkeypatch):
    a, b, _, cfg = hosted
    cfg = replace(cfg, max_files=100)
    for module in (uploads, queue, security, jobs):
        monkeypatch.setattr(module, 'settings', cfg)
    a.get('/api/capabilities')
    files = [('files', (f'v7.4.{i}.pdf', b'%PDF-1.7\n', 'application/pdf')) for i in range(6)]
    result = a.post('/api/jobs/upload', files=files)
    assert result.status_code == 201, result.text
    assert len(result.json()['file_outcomes']) == 6
    b.get('/api/capabilities')
    assert b.get('/api/jobs').json() == []
    key = result.json()['id']
    assert b.get(f'/api/jobs/{key}').status_code == 404
    cancelled = a.post(f'/api/jobs/{key}/cancel').json()
    assert cancelled['completed_at'] is not None
    retried = a.post(f'/api/jobs/{key}/retry').json()
    assert retried['completed_at'] is None and retried['started_at'] is None


def test_parser_publishes_allowlisted_progress_and_removes_sidecar(hosted, monkeypatch):
    import subprocess
    import sys
    import time
    a, _, sessions, cfg = hosted
    key = upload(a).json()['id']
    with sessions() as db:
        job = db.get(ScrapeJob, key)
        job.status = 'running'
        job.file_outcomes_json = json.dumps([{'name': 'v7.4.11.pdf', 'status': 'running'}])
        db.commit()
    path = next((cfg.uploads / key).glob('*.pdf'))
    real_popen = subprocess.Popen
    def parser(*args, **kwargs):
        return real_popen([sys.executable, '-c',
            "import pathlib,json,time,sys; p=pathlib.Path(sys.argv[1]); p.with_suffix('.progress.json').write_text(json.dumps({'phase':'reading','pages_done':3,'total_pages':10,'secret':'must-not-copy'})); time.sleep(2); p.with_suffix('.result.json').write_text(json.dumps({'result':[]}))", str(path)], start_new_session=True)
    monkeypatch.setattr(queue.subprocess, 'Popen', parser)
    assert queue.parse_isolated(key, path, time.monotonic() + 15) == []
    with sessions() as db:
        outcomes = json.loads(db.get(ScrapeJob, key).file_outcomes_json)
        assert outcomes[0]['progress'] == {'phase': 'reading', 'pages_done': 3, 'total_pages': 10}
    assert not path.with_suffix('.progress.json').exists()


def test_report_tools_do_not_cross_sessions(hosted):
    a,b,sessions,_ = hosted
    key = upload(a).json()['id']; b.get('/api/capabilities')
    for endpoint in ['view','export']:
        assert b.post(f'/api/jobs/{key}/{endpoint}',json={}).status_code == 404
        assert a.post(f'/api/jobs/{key}/{endpoint}',json={},headers={'Origin':'https://other.example'}).status_code == 403
    assert b.get(f'/api/jobs/{key}/compare?from_version=7.4.11&to_version=7.4.11').status_code == 404
    review=a.post('/api/reviews',json={'title':'Private session review'}).json()
    assert b.get(f"/api/reviews/{review['id']}/export").status_code == 404
    with sessions() as db:
        db.get(ScrapeJob,key).expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    assert a.post(f'/api/jobs/{key}/export',json={}).status_code == 404
