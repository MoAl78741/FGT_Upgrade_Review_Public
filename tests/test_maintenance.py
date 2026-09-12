import fcntl
import json
import sqlite3
import zipfile
from dataclasses import replace
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend import maintenance
from backend.models import Base, ScrapeJob, Review, TeamUser, TeamSession
from datetime import datetime, timedelta

@pytest.fixture
def installation(tmp_path):
    database = tmp_path/'original.db'; uploads = tmp_path/'uploads'; (uploads/'job').mkdir(parents=True)
    (uploads/'job'/'source.pdf').write_bytes(b'%PDF-1.7 private source bytes')
    engine = create_engine('sqlite:///'+str(database)); Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(ScrapeJob(id='job', owner_id='customer-secret', from_version='7.4.10', to_version='7.4.11', status='completed', all_data_json='{"private":"original source"}', log='private logs'))
        db.add(Review(id='review', owner_id='customer-secret', title='Private customer title', decisions_json='{"finding":{"status":"reviewed","note":"private note"}}'))
        db.add(TeamUser(id='user', username='private-person', password_hash='secret-hash'))
        db.add(TeamSession(id='session-secret', user_id='user', expires_at=datetime.utcnow()+timedelta(hours=8)))
        db.commit()
    engine.dispose()
    return database, uploads


def test_backup_restore_preserves_evidence_and_revokes_sessions(installation, tmp_path):
    database, uploads = installation; archive = tmp_path/'backup.zip'
    maintenance.backup(archive, database, uploads)
    assert archive.stat().st_mode & 0o777 == 0o600
    target = tmp_path/'restored.db'; restored = tmp_path/'restored-uploads'
    result = maintenance.restore(archive, target, restored)
    assert result['sessions_revoked'] is True
    assert (restored/'job/source.pdf').read_bytes() == (uploads/'job/source.pdf').read_bytes()
    with sqlite3.connect(database) as before, sqlite3.connect(target) as after:
        for table in ['scrape_jobs','reviews','team_users']:
            assert before.execute(f'select * from {table}').fetchall() == after.execute(f'select * from {table}').fetchall()
        assert after.execute('select count(*) from team_sessions').fetchone()[0] == 0
        assert before.execute('select count(*) from team_sessions').fetchone()[0] == 1
        assert after.execute("select action from audit_events").fetchone()[0] == 'installation.restored'
    with pytest.raises(ValueError, match='empty database'): maintenance.restore(archive, target, restored)
    with pytest.raises(FileExistsError): maintenance.backup(archive, database, uploads)


def test_backup_requires_stopped_server(installation, tmp_path):
    database, uploads = installation
    with open(str(database)+'.worker.lock', 'a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='Stop the application'):
            maintenance.backup(tmp_path/'backup.zip', database, uploads)
    assert not (tmp_path/'backup.zip').exists()


def test_no_symlinks_or_recursive_backup(installation, tmp_path):
    database, uploads = installation
    with pytest.raises(ValueError, match='outside'): maintenance.backup(uploads/'archive.zip', database, uploads)
    (uploads/'job'/'link').symlink_to(database)
    with pytest.raises(ValueError, match='link'): maintenance.backup(tmp_path/'backup.zip', database, uploads)


@pytest.mark.parametrize('name', ['../escape', 'uploads/../../escape', '/absolute', 'uploads/job/../../escape', 'uploads/job\\escape'])
def test_restore_rejects_archive_traversal(installation, tmp_path, name):
    database, uploads = installation; archive=tmp_path/'backup.zip';maintenance.backup(archive,database,uploads)
    with zipfile.ZipFile(archive) as z: entries={n:z.read(n) for n in z.namelist()}
    manifest=json.loads(entries['manifest.json']);manifest['files'][name]={'bytes':1,'sha256':'bad'}
    entries['manifest.json']=json.dumps(manifest).encode();entries[name]=b'x'
    with zipfile.ZipFile(archive,'w') as z:
        for n,data in entries.items():z.writestr(n,data)
    target=tmp_path/'new.db'
    with pytest.raises(ValueError, match='Unsafe archive path'):maintenance.restore(archive,target,tmp_path/'new-uploads')
    assert not target.exists()
    assert not (tmp_path/'escape').exists()


def test_corruption_cannot_publish_partial_restore(installation, tmp_path):
    database, uploads=installation;archive=tmp_path/'backup.zip';maintenance.backup(archive,database,uploads)
    with zipfile.ZipFile(archive) as z:entries={n:z.read(n) for n in z.namelist()}
    entries['uploads/job/source.pdf']=b'x'*len(entries['uploads/job/source.pdf'])
    with zipfile.ZipFile(archive,'w') as z:
        for n,data in entries.items():z.writestr(n,data)
    with pytest.raises(ValueError, match='checksum'):maintenance.restore(archive,tmp_path/'new.db',tmp_path/'new-uploads')
    assert not (tmp_path/'new.db').exists() and not (tmp_path/'new-uploads').exists()


def test_diagnostics_exclude_private_fields(installation):
    database,_=installation
    result=maintenance.diagnostics(database);serialized=json.dumps(result)
    assert result['database']['jobs_by_status']['completed']==1
    for secret in ['customer-secret','private-person','private note','source.pdf','secret-hash','session-secret',str(database),'private logs','original source']:
        assert secret not in serialized
    assert 'integrity_check' not in serialized  # No potentially content-bearing SQLite error messages.


def test_public_archives_disabled(installation, tmp_path, monkeypatch):
    monkeypatch.setattr(maintenance,'settings',replace(maintenance.settings,edition='public'))
    with pytest.raises(ValueError, match='private edition'):maintenance.backup(tmp_path/'backup.zip',*installation)


def test_restore_rejects_links_and_size_bombs(installation, tmp_path, monkeypatch):
    database,uploads=installation;archive=tmp_path/'backup.zip';maintenance.backup(archive,database,uploads)
    monkeypatch.setattr(maintenance,'MAX_ARCHIVE_BYTES',1)
    with pytest.raises(ValueError, match='size limit'):maintenance.restore(archive,tmp_path/'new.db',tmp_path/'new-uploads')
    monkeypatch.setattr(maintenance,'MAX_ARCHIVE_BYTES',4*1024**3)
    with zipfile.ZipFile(archive) as z:entries={n:z.read(n) for n in z.namelist()}
    with zipfile.ZipFile(archive,'w') as z:
        for n,data in entries.items():
            info=zipfile.ZipInfo(n)
            info.external_attr=(0o120777 if n.startswith('uploads/') else 0o100600)<<16
            z.writestr(info,data)
    with pytest.raises(ValueError, match='Links'):maintenance.restore(archive,tmp_path/'new.db',tmp_path/'new-uploads')


def test_restore_failure_removes_partial_files(installation, tmp_path, monkeypatch):
    database,uploads=installation;archive=tmp_path/'backup.zip';maintenance.backup(archive,database,uploads)
    def failed_copy(source,destination):
        destination.mkdir();(destination/'partial').write_text('partial');raise OSError('disk full')
    monkeypatch.setattr(maintenance.shutil,'copytree',failed_copy)
    with pytest.raises(OSError, match='disk full'):maintenance.restore(archive,tmp_path/'new.db',tmp_path/'new-uploads')
    assert not (tmp_path/'new.db').exists()
    assert list((tmp_path/'new-uploads').iterdir())==[]


def test_application_cannot_migrate_database_during_maintenance(tmp_path):
    import os, subprocess, sys
    database=tmp_path/'empty.db'
    env=os.environ|{'DB_PATH':str(database),'UPLOADS_DIR':str(tmp_path/'uploads'),'APP_EDITION':'private','APP_ORIGIN':'http://127.0.0.1:18999'}
    with maintenance.offline_lock(database):
        result=subprocess.run([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','18999'],env=env,capture_output=True,text=True,timeout=60)
    assert result.returncode != 0 and 'Run one API/dispatcher' in result.stderr
    assert not database.exists()


@pytest.mark.parametrize('schema', [
    'CREATE VIRTUAL TABLE custom_search USING fts5(content)',
    'CREATE VIEW custom_view AS SELECT id FROM team_sessions',
    "CREATE TRIGGER custom_trigger AFTER DELETE ON team_sessions BEGIN UPDATE scrape_jobs SET log='trigger ran'; END",
])
def test_restore_rejects_executable_or_virtual_database_schema(installation, tmp_path, schema):
    database, uploads=installation
    with sqlite3.connect(database) as db:db.execute(schema)
    archive=tmp_path/'custom.zip';maintenance.backup(archive,database,uploads)
    with pytest.raises(ValueError, match='unsupported views, triggers or virtual tables'):
        maintenance.restore(archive,tmp_path/'restored.db',tmp_path/'restored-uploads')
    assert not (tmp_path/'restored.db').exists()
    with sqlite3.connect(database) as db:assert db.execute('select log from scrape_jobs').fetchone()[0]=='private logs'
