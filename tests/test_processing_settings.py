import json
from dataclasses import replace
import pytest
from test_team import named, login
from test_security import hosted, upload
from backend import queue
from backend.models import InstallationSetting, ScrapeJob, AuditEvent
from backend.processing_settings import effective, attempt

VALUES = dict(timeout_minutes=60, max_files=25, max_pages=800, workers=1)


def test_private_settings_require_admin_and_completed_setup(named):
    c, db = named
    assert c.get('/api/settings/processing').status_code == 401
    login(c, 'reviewer')
    assert c.put('/api/settings/processing', json=VALUES).status_code == 403
    login(c, 'viewer')
    assert c.delete('/api/settings/processing').status_code == 403
    login(c, 'admin')
    from backend.models import TeamUser
    user = db.get(TeamUser, 'admin'); user.must_change_password = True; db.commit()
    assert c.put('/api/settings/processing', json=VALUES).status_code == 403


def test_private_settings_persist_validate_reset_and_audit(named):
    c, db = named; login(c, 'admin')
    initial = c.get('/api/settings/processing').json()['values']
    for value in [dict(VALUES, timeout_minutes=121), dict(VALUES, workers=3), dict(VALUES, max_files=0), dict(VALUES, timeout_minutes=True), dict(VALUES, max_pages=2001), dict(VALUES, grid_url='http://invalid')]:
        assert c.put('/api/settings/processing', json=value).status_code == 422
    assert c.put('/api/settings/processing', json=VALUES, headers={'Origin':'https://evil.example'}).status_code == 403
    assert c.put('/api/settings/processing', json=VALUES).status_code == 200
    db.expire_all()
    assert json.loads(db.get(InstallationSetting, 'processing').value_json) == VALUES
    cfg = effective(db, queue.settings)
    assert (cfg.timeout, cfg.max_files, cfg.max_pages, cfg.workers) == (3600,25,800,1)
    caps = c.get('/api/capabilities').json()
    assert (caps['timeout_minutes'], caps['max_files'], caps['max_pages'], caps['workers']) == (60,25,800,1)
    assert db.query(AuditEvent).filter_by(action='settings.processing.updated').count() == 1
    assert c.delete('/api/settings/processing').json()['values'] == initial


def test_public_cannot_change_installation_and_timeout_is_per_attempt(hosted):
    a,b,sessions,cfg = hosted
    for c in (a,b): c.get('/api/capabilities')
    assert a.put('/api/settings/processing', json=VALUES).status_code == 403
    assert a.delete('/api/settings/processing').status_code == 403
    assert a.get('/api/settings/processing').status_code == 403
    for raw in ['31','0','-1','1.5','nan']:
        r=a.post('/api/jobs/upload', headers={'X-PDF-Timeout-Minutes':raw}, files=[('files',('v7.6.6.pdf',b'%PDF-fixture'))])
        assert r.status_code == 422, r.text
    r=a.post('/api/jobs/upload',headers={'X-PDF-Timeout-Minutes':'12'},files=[('files',('v7.6.6.pdf',b'%PDF-fixture'))]);assert r.status_code==201,r.text
    key=r.json()['id']
    other=upload(b).json()['id']
    with sessions() as db:
        job=db.get(ScrapeJob,key)
        assert attempt(job,cfg).timeout==720
        assert attempt(db.get(ScrapeJob,other),cfg).timeout==1800
        job.status='failed';db.commit()
    assert a.post(f'/api/jobs/{key}/retry',headers={'X-PDF-Timeout-Minutes':'20'}).status_code==200
    with sessions() as db: assert attempt(db.get(ScrapeJob,key),cfg).timeout==1200


def test_running_attempt_keeps_limits_after_admin_change(named):
    c, db=named;login(c,'admin')
    r=c.post('/api/jobs/upload', files=[('files',('v7.6.6.pdf',b'%PDF-fixture'))]);assert r.status_code==201,r.text
    key=r.json()['id']
    assert c.put('/api/settings/processing',json=VALUES).status_code==200
    db.expire_all()
    cfg=effective(db,queue.settings)
    assert cfg.timeout==3600
    prior=attempt(db.get(ScrapeJob,key),cfg)
    assert prior.timeout==1800 and prior.max_pages==500
    # A retry uses the new installation defaults while retaining completed files.
    job=db.get(ScrapeJob,key);job.status='partial';job.file_outcomes_json=json.dumps([{'name':'v7.6.6.pdf','status':'completed'}]);db.commit()
    assert c.post(f'/api/jobs/{key}/retry').status_code==200
    db.expire_all()
    assert attempt(db.get(ScrapeJob,key),cfg).timeout==3600
    assert json.loads(db.get(ScrapeJob,key).file_outcomes_json)[0]['status']=='completed'


def test_worker_uses_selected_deadline_and_reports_it(hosted, monkeypatch):
    import time
    a,_,sessions,cfg=hosted
    a.get('/api/capabilities')
    r=a.post('/api/jobs/upload',headers={'X-PDF-Timeout-Minutes':'9'},files=[('files',('v7.6.6.pdf',b'%PDF-fixture'))]);assert r.status_code==201
    assert r.json()['processing_timeout_seconds']==540
    key=r.json()['id']
    with sessions() as db:
        db.get(ScrapeJob,key).status='running';db.commit()
    def parser(job_id,path,deadline):
        assert 530 < deadline-time.monotonic() <= 540
        return '7.6.6',{},[],{},{}
    monkeypatch.setattr(queue,'parse_isolated',parser)
    queue.run_pdf(key)
    assert a.get('/api/jobs/'+key).json()['status']=='completed'
