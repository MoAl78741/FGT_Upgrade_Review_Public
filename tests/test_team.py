import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta
import pytest
from backend import security, queue, team
from backend.database import get_db
from backend.main import app
from backend.models import TeamUser, Workspace, WorkspaceMember, TeamSession, ScrapeJob, AuditEvent
from backend.routers import jobs, uploads, auth

PASSWORD = 'correct-horse-battery-staple'
PASSWORD_HASH = team.hash_password(PASSWORD)


@pytest.fixture
def named(client, monkeypatch):
    cfg = replace(security.settings, team_auth=True)
    for module in [security, queue, jobs, uploads]: monkeypatch.setattr(module, 'settings', cfg)
    auth.ATTEMPTS.clear()
    client.headers['Origin'] = 'http://testserver'
    gen = app.dependency_overrides[get_db](); db = next(gen)
    try:
        db.add_all([Workspace(id='one', name='Customer One'), Workspace(id='two', name='Customer Two'),
                    TeamUser(id='admin', username='admin', password_hash=PASSWORD_HASH, is_admin=True),
                    TeamUser(id='reviewer', username='reviewer', password_hash=PASSWORD_HASH),
                    TeamUser(id='viewer', username='viewer', password_hash=PASSWORD_HASH),
                    WorkspaceMember(workspace_id='one', user_id='reviewer', role='reviewer'),
                    WorkspaceMember(workspace_id='one', user_id='viewer', role='viewer')])
        for ws in ['one', 'two']:
            db.add(ScrapeJob(id=ws+'-job', owner_id=ws, status='completed', source='pdf', from_version='7.6.5', to_version='7.6.6', versions_json='["7.6.6"]', all_data_json=json.dumps({'7.6.6': {'known_issues': [{'Bug ID': '123', 'Description': 'source'}]}})))
        db.commit()
        yield client, db
    finally: gen.close()


def login(client, name):
    result = client.post('/api/auth/login', json={'username': name, 'password': PASSWORD})
    assert result.status_code == 200, result.text
    return result


def test_private_routes_require_named_login(named):
    c, _ = named
    assert c.get('/api/capabilities').json()['team_auth'] is True
    assert c.get('/api/auth/status').json()['authenticated'] is False
    assert c.get('/api/jobs').status_code == 401
    assert c.get('/api/reviews').status_code == 401
    response = login(c, 'reviewer')
    assert 'httponly' in response.headers['set-cookie'].lower()
    assert 'samesite=strict' in response.headers['set-cookie'].lower()
    assert 'password_hash' not in c.get('/api/auth/status').text
    assert PASSWORD not in c.get('/api/auth/status').text


def test_workspace_isolation_and_mutation_permissions(named):
    c, _ = named;login(c, 'reviewer')
    assert [j['id'] for j in c.get('/api/jobs').json()] == ['one-job']
    assert c.get('/api/jobs/two-job').status_code == 404
    assert c.delete('/api/jobs/two-job').status_code == 404
    assert c.get('/api/jobs/two-job/files/0').status_code == 404
    assert c.post('/api/auth/workspace', json={'workspace_id': 'two'}).status_code == 404
    assert c.get('/api/auth/users').status_code == 403
    r = c.post('/api/reviews', json={'title': 'Customer One review'}).json()
    assert c.post(f"/api/reviews/{r['id']}/jobs", json={'revision': 1, 'job_id': 'two-job'}).status_code == 404
    login(c, 'admin')
    assert c.post('/api/auth/workspace', json={'workspace_id': 'two'}).status_code == 200
    assert c.get('/api/reviews').json() == []
    assert c.get('/api/reviews/'+r['id']).status_code == 404


def test_viewer_can_read_but_cannot_edit(named):
    c, _ = named;login(c, 'viewer')
    assert c.get('/api/jobs/one-job').status_code == 200
    for method, route, payload in [('post', '/api/reviews', {'title': 'forbidden'}), ('delete', '/api/jobs/one-job', None), ('post', '/api/jobs/one-job/cancel', None)]:
        assert getattr(c, method)(route, **({'json': payload} if payload else {})).status_code == 403


def test_roles_revoked_immediately_and_last_admin_protected(named):
    c, db = named;login(c, 'reviewer')
    member = db.get(WorkspaceMember, ('one', 'reviewer'));db.delete(member);db.commit()
    assert c.get('/api/jobs').status_code == 403
    login(c, 'admin')
    assert c.put('/api/auth/users/admin', json={'active': False, 'is_admin': False}).status_code == 409
    assert c.post('/api/auth/users', json={'username': 'reviewer', 'password': PASSWORD}).status_code == 409
    result = c.post('/api/auth/users', json={'username': 'new-user', 'password': PASSWORD})
    assert result.status_code == 201
    assert 'password_hash' not in result.text
    assert PASSWORD not in result.text


def test_audit_attributes_changes_without_copying_notes(named):
    c, db = named;login(c, 'reviewer')
    r=c.post('/api/reviews', json={'title': 'Pilot'}).json()
    r=c.post(f"/api/reviews/{r['id']}/jobs", json={'revision': 1, 'job_id': 'one-job'}).json()
    result=c.put(f"/api/reviews/{r['id']}/decisions/{r['findings'][0]['id']}", json={'revision': 2, 'status': 'reviewed', 'note': 'private reviewer note'})
    assert result.status_code == 200
    audit=c.get('/api/auth/audit', params={'target_id': r['id']}).json()
    assert len(audit) == 3
    assert all(e['actor_name'] == 'reviewer' for e in audit)
    assert 'private reviewer note' not in json.dumps(audit)
    assert audit[0]['details']['revision'] == 3
    assert c.get('/api/auth/admin-audit').status_code == 403


def test_password_reset_logout_and_expiry_revoke_sessions(named):
    c, db = named;login(c, 'reviewer')
    token=c.cookies.get(team.COOKIE);session=db.get(TeamSession, hashlib.sha256(token.encode()).hexdigest())
    session.expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    assert c.get('/api/jobs').status_code == 401
    login(c,'admin')
    assert c.post('/api/auth/users/reviewer/password', json={'new_password': 'a-new-long-password'}).status_code == 204
    assert c.post('/api/auth/logout').status_code == 204
    assert c.get('/api/jobs').status_code == 401
    assert c.post('/api/auth/login', json={'username': 'reviewer', 'password': PASSWORD}).status_code == 401


def test_csrf_and_login_throttling(named):
    c,_=named
    assert c.post('/api/auth/login', headers={'Origin': 'https://evil.example'}, json={'username':'admin','password':PASSWORD}).status_code == 403
    for _ in range(5):
        assert c.post('/api/auth/login', json={'username':'unknown','password':'bad'}).status_code == 401
    assert c.post('/api/auth/login', json={'username':'unknown','password':'bad'}).status_code == 429


def test_hashes_are_salted_and_no_password_truncation():
    a=team.hash_password(PASSWORD);b=team.hash_password(PASSWORD)
    assert a != b and PASSWORD not in a
    assert team.verify_password(PASSWORD,a)
    assert not team.verify_password(PASSWORD+'suffix',a)


def test_stale_tab_cannot_create_in_switched_workspace(named):
    c, _ = named; login(c, 'admin')
    c.headers['X-Workspace-ID'] = 'one'
    assert c.post('/api/auth/workspace', json={'workspace_id': 'two'}).status_code == 200
    assert c.post('/api/reviews', json={'title': 'Wrong customer'}).status_code == 409
    assert c.get('/api/jobs').status_code == 409
    c.headers['X-Workspace-ID'] = 'two'
    assert c.get('/api/reviews').json() == []
    assert c.post('/api/reviews', json={'title': 'Right customer'}).status_code == 201


def test_membership_administration_and_audit(named):
    c, _ = named; login(c, 'admin')
    space = c.post('/api/auth/workspaces', json={'name': 'New customer'}).json()
    membership = {'workspace_id': space['id'], 'user_id': 'reviewer', 'role': 'viewer'}
    assert c.put('/api/auth/memberships', json=membership).status_code == 200
    assert membership in c.get('/api/auth/memberships').json()
    login(c, 'reviewer')
    assert c.post('/api/auth/workspace', json={'workspace_id': space['id']}).status_code == 200
    assert c.get('/api/jobs').json() == []
    assert c.post('/api/reviews', json={'title': 'Denied'}).status_code == 403
    login(c, 'admin')
    assert c.delete('/api/auth/memberships/'+space['id']+'/reviewer').status_code == 204
    assert any(e['action'] == 'membership.revoked' and e['workspace_id'] == space['id'] for e in c.get('/api/auth/admin-audit').json())
    login(c, 'reviewer')
    assert c.post('/api/auth/workspace', json={'workspace_id': space['id']}).status_code == 404


def test_own_password_change_revokes_other_devices(named):
    c, _ = named; login(c, 'reviewer')
    old_token = c.cookies.get(team.COOKIE)
    login(c, 'reviewer')
    new_token = c.cookies.get(team.COOKIE)
    assert c.post('/api/auth/password', json={'current_password': PASSWORD, 'new_password': 'my-new-long-password'}).status_code == 204
    assert c.get('/api/jobs').status_code == 200
    c.cookies.clear(); c.cookies.set(team.COOKIE, old_token)
    assert c.get('/api/jobs').status_code == 401
    c.cookies.clear(); c.cookies.set(team.COOKIE, new_token)
    assert c.get('/api/jobs').status_code == 200


def test_https_team_origin_is_exact_and_cookie_secure(named, monkeypatch):
    c, _ = named
    cfg = replace(security.settings, origin='https://private.example')
    monkeypatch.setattr(security, 'settings', cfg)
    assert cfg.origins == {'https://private.example'}
    response = c.post('https://private.example/api/auth/login', headers={'Origin': cfg.origin}, json={'username':'admin','password':PASSWORD})
    assert response.status_code == 200
    assert 'secure' in response.headers['set-cookie'].lower()
    assert c.post('https://private.example/api/auth/login', headers={'Origin':'http://localhost:5173'}, json={'username':'admin','password':PASSWORD}).status_code == 403


def test_local_bootstrap_recovery_preserves_legacy_content(tmp_path):
    import os
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path
    from sqlalchemy import create_engine
    from backend.models import Base, Review
    from sqlalchemy.orm import Session
    database = tmp_path / 'legacy.db'
    engine = create_engine('sqlite:///'+str(database)); Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ScrapeJob(id='legacy', owner_id=None, from_version='7.6.5', to_version='7.6.6', all_data_json='{"source":"unchanged"}'))
        db.add(Review(id='review', owner_id='local', title='Existing review'))
        db.commit()
    engine.dispose()
    password = tmp_path / 'password'; password.write_text(PASSWORD); password.chmod(0o600)
    env = os.environ | {'DB_PATH':str(database), 'APP_EDITION':'private'}
    command = [sys.executable, '-m', 'backend.manage_team', 'bootstrap', '--username', 'operator', '--password-file', str(password)]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert PASSWORD not in result.stdout + result.stderr
    with sqlite3.connect(database) as db:
        assert db.execute('select owner_id, all_data_json from scrape_jobs').fetchone() == ('local', '{"source":"unchanged"}')
        assert db.execute('select owner_id, title from reviews').fetchone() == ('local', 'Existing review')
        assert db.execute('select count(*) from team_users').fetchone()[0] == 1
        old_hash = db.execute('select password_hash from team_users').fetchone()[0]
    assert subprocess.run(command, env=env, capture_output=True).returncode != 0
    password.write_text('replacement-local-password')
    command[3] = 'reset-password'
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(database) as db:
        new_hash = db.execute('select password_hash from team_users').fetchone()[0]
        assert new_hash != old_hash and team.verify_password('replacement-local-password', new_hash)
    password.chmod(0o644)
    assert subprocess.run(command, env=env, capture_output=True).returncode != 0
    password.chmod(0o600)
    assert subprocess.run(command, env=env | {'APP_EDITION':'public','APP_ORIGIN':'https://public.example'}, capture_output=True).returncode != 0


def test_support_diagnostics_require_private_administrator(named, monkeypatch):
    from backend.routers import support
    c, _ = named
    monkeypatch.setattr(support, 'diagnostics', lambda: {'format': 1, 'version': 'test'})
    login(c, 'reviewer')
    assert c.get('/api/support/diagnostics').status_code == 403
    login(c, 'admin')
    assert c.get('/api/support/diagnostics').json() == {'format': 1, 'version': 'test'}
    monkeypatch.setattr(support, 'settings', replace(support.settings, edition='public'))
    assert c.get('/api/support/diagnostics').status_code == 404


def test_initial_password_blocks_every_data_and_admin_route(named):
    c, db = named
    user = db.get(TeamUser, 'admin'); user.password_hash = team.hash_password('password'); user.must_change_password = True; db.commit()
    assert c.post('/api/auth/login', json={'username':'admin','password':'password'}).status_code == 200
    state = c.get('/api/auth/status').json()
    assert state['user']['must_change_password'] and state['workspaces'] == [] and state['workspace_id'] is None
    for method, route, body in [
        ('get','/api/jobs',None), ('get','/api/jobs/one-job',None), ('delete','/api/jobs/one-job',None),
        ('post','/api/jobs/one-job/cancel',None), ('get','/api/jobs/one-job/files/0',None),
        ('get','/api/reviews',None), ('post','/api/reviews',{'title':'blocked'}),
        ('get','/api/auth/users',None), ('get','/api/auth/memberships',None),
        ('get','/api/auth/admin-audit',None), ('get','/api/auth/audit',None),
        ('post','/api/auth/workspace',{'workspace_id':'one'}), ('get','/api/support/diagnostics',None)]:
        r = getattr(c, method)(route, **({'json':body} if body else {}))
        assert r.status_code == 403, (route,r.text)
    assert c.post('/api/auth/password',json={'new_password':'password'}).status_code == 422
    assert c.post('/api/auth/password',json={'new_password':PASSWORD}).status_code == 204
    assert not c.get('/api/auth/status').json()['user']['must_change_password']
    assert c.get('/api/jobs').status_code == 200
    db.expire_all(); assert team.verify_password(PASSWORD, db.get(TeamUser,'admin').password_hash)
    assert c.post('/api/auth/password',json={'new_password':'another-long-password'}).status_code == 401


def test_initial_admin_is_created_once_and_never_resets_existing_accounts(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from backend.models import Base
    monkeypatch.setattr(security, 'settings', replace(security.settings, team_auth=True, edition='private'))
    engine = create_engine('sqlite:///'+str(tmp_path/'fresh.db')); Base.metadata.create_all(engine)
    with Session(engine) as db:
        assert team.ensure_initial_admin(db)
        user=db.query(TeamUser).one(); assert user.username=='admin' and user.must_change_password
        assert team.verify_password('password',user.password_hash)
        user.password_hash=PASSWORD_HASH;user.must_change_password=False;db.commit()
        assert not team.ensure_initial_admin(db, allow_existing=True)
        user=db.query(TeamUser).one();assert user.password_hash==PASSWORD_HASH and not user.must_change_password
        db.commit()
        monkeypatch.setattr(security, 'settings', replace(security.settings, edition='public'))
        assert not team.ensure_initial_admin(db, allow_existing=True)
    engine.dispose()


def test_viewers_may_use_readonly_report_tools(named, monkeypatch):
    from backend.routers import presentation
    monkeypatch.setattr(presentation,'render',lambda payload: 'report' if payload['operation']=='html' else {'entries':[]})
    c,_=named;login(c,'viewer')
    assert c.post('/api/jobs/one-job/view',json={}).status_code == 200
    assert c.post('/api/jobs/one-job/export',json={}).status_code == 200
    assert c.post('/api/jobs/two-job/export',json={}).status_code == 404
    assert c.delete('/api/jobs/one-job').status_code == 403
