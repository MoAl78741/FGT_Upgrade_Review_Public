"""Persistent SQLite queue. One dispatcher per database; bounded child processes."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
import shutil
from fastapi import HTTPException
from sqlalchemy import text
from .database import SessionLocal, DB_PATH
from .models import ScrapeJob, BrowserSession, Review, TeamSession
from .settings import settings
from .processing_settings import effective, attempt
from .file_metrics import stamp, elapsed, pending_file, finish_files
from .container_worker import ContainerProcess

ROOT = Path(__file__).resolve().parent.parent
STOP = threading.Event()
THREAD = None
CHILDREN = {}
LOCK = threading.RLock()
LEASE = None


def reserve(db, owner_id, **kwargs):
    # Serialize capacity admission across API processes, not only Python threads.
    db.commit()
    db.execute(text('BEGIN IMMEDIATE'))
    active = db.query(ScrapeJob).filter(ScrapeJob.status.in_(['uploading', 'pending', 'running']))
    if active.filter(ScrapeJob.status != 'running').count() >= settings.queue_size:
        db.rollback()
        raise HTTPException(429, 'Queue is full. Try again later.')
    if settings.public and active.filter(ScrapeJob.owner_id == owner_id).count():
        db.rollback()
        raise HTTPException(429, 'Your session already has a queued or running job.')
    used = sum(p.stat().st_size for p in settings.uploads.rglob('*') if p.is_file()) if settings.uploads.exists() else 0
    reserved = active.filter(ScrapeJob.status == 'uploading').count() * settings.total_bytes
    if used + reserved + settings.total_bytes > settings.storage_bytes:
        db.rollback()
        raise HTTPException(507, 'Storage limit reached. Delete reports or try again after expiry.')
    job = ScrapeJob(owner_id=owner_id, expires_at=datetime.utcnow() + timedelta(hours=24) if settings.public else None, **kwargs)
    db.add(job)
    db.flush()
    from . import team
    team.audit(db, 'job.created', job.id, workspace_id=owner_id, details={'source': kwargs.get('source', 'scrape')})
    db.commit()
    db.refresh(job)
    return job


def terminate(job_id):
    with LOCK:
        process = CHILDREN.get(job_id)
        if process and process.poll() is None:
            if isinstance(process, ContainerProcess):
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)


def clean_expired(db):
    db.query(TeamSession).filter(TeamSession.expires_at <= datetime.utcnow()).delete()
    db.query(Review).filter(Review.expires_at <= datetime.utcnow()).delete()
    for job in db.query(ScrapeJob).filter(ScrapeJob.expires_at <= datetime.utcnow()).all():
        terminate(job.id)
        shutil.rmtree(settings.uploads / job.id, ignore_errors=True)
        db.delete(job)
    db.query(BrowserSession).filter(BrowserSession.expires_at <= datetime.utcnow()).delete()
    db.commit()


def parse_isolated(job_id, path, deadline):
    with SessionLocal() as db:
        cfg = attempt(db.get(ScrapeJob, job_id), effective(db, settings))
    output = path.with_suffix('.result.json')
    progress_path = path.with_suffix('.progress.json')
    progress_path.unlink(missing_ok=True)
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'PYTHONPATH': str(ROOT),
           'PYTHONDONTWRITEBYTECODE': '1', 'FGT_SANDBOXED': '1',
           'JOB_TIMEOUT_SECONDS': str(cfg.timeout), 'MAX_PDF_PAGES': str(cfg.max_pages),
           'WORKER_MEMORY_BYTES': str(settings.memory_bytes), 'HOME': str(path.parent),
           'TMPDIR': str(path.parent)}
    command = [sys.executable, '-m', 'backend.parse_process', str(path), str(output)]
    with LOCK:
        if STOP.is_set():
            raise RuntimeError('Worker stopped')
        with SessionLocal() as check:
            current = check.get(ScrapeJob, job_id)
            if not current or current.status != 'running':
                raise RuntimeError('Job cancelled')
        from .container_worker import enabled, ContainerProcess
        if enabled():
            process = ContainerProcess(job_id, path, output, min(cfg.timeout, max(1, deadline-time.monotonic())), cfg.max_pages)
        else:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        CHILDREN[job_id] = process
    try:
        last_progress = None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, cfg.timeout)
            try:
                process.wait(timeout=min(1, remaining))
                break
            except subprocess.TimeoutExpired:
                if progress_path.exists() and progress_path.stat().st_size <= 4096:
                    try:
                        value = json.loads(progress_path.read_text())
                        phase = value.get('phase')
                        done, total = value.get('pages_done', 0), value.get('total_pages', 0)
                        if phase not in {'reading', 'formatting', 'finalizing'} or type(done) is not int or type(total) is not int or not 0 <= done <= total <= cfg.max_pages:
                            continue
                        progress = {'phase': phase, 'pages_done': done, 'total_pages': total}
                        if progress != last_progress:
                            with LOCK, SessionLocal() as db:
                                job = db.get(ScrapeJob, job_id)
                                if job and job.status == 'running':
                                    outcomes = json.loads(job.file_outcomes_json or '[]')
                                    for item in outcomes:
                                        if item.get('status') == 'running':
                                            item['progress'] = progress
                                            if total > 0:
                                                item['page_count'] = total
                                            item['elapsed_seconds'] = elapsed(item.get('started_at'))
                                    job.file_outcomes_json = json.dumps(outcomes)
                                    db.commit()
                            last_progress = progress
                    except (ValueError, OSError, AttributeError):
                        pass  # A missing/invalid sidecar must not affect parsed content.
        if process.returncode or not output.exists():
            raise RuntimeError('Isolated parser failed. Verify sandbox support and document validity.')
        result = json.loads(output.read_text())
        if type(result.get('page_count')) is int and 0 <= result['page_count'] <= 1000000:
            with LOCK, SessionLocal() as db:
                job = db.get(ScrapeJob, job_id)
                if job and job.status == 'running':
                    outcomes = json.loads(job.file_outcomes_json or '[]')
                    for item in outcomes:
                        if item.get('status') == 'running':
                            item['page_count'] = result['page_count']
                    job.file_outcomes_json = json.dumps(outcomes)
                    db.commit()
        if 'error' in result:
            raise ValueError(result['error'])
        return result['result']
    except subprocess.TimeoutExpired:
        terminate(job_id)
        raise RuntimeError('Processing exceeded the time limit.')
    finally:
        if isinstance(process, ContainerProcess):
            process.kill()
        with LOCK:
            CHILDREN.pop(job_id, None)
        output.unlink(missing_ok=True)
        progress_path.unlink(missing_ok=True)
        progress_path.with_suffix('.tmp').unlink(missing_ok=True)


def run_pdf(job_id):
    from fgt_upgrade.constants import PDF_PARSER_REVISION
    with SessionLocal() as db:
        job = db.get(ScrapeJob, job_id)
        cfg = attempt(job, effective(db, settings))
        deadline = time.monotonic() + cfg.timeout
        args = json.loads(job.request_json)
        if 'processing' not in args:
            args['processing'] = {'timeout_seconds': cfg.timeout, 'max_pages': cfg.max_pages}
            job.request_json = json.dumps(args)
            db.commit()
        manifest = json.loads(job.request_json)['files']
        data = json.loads(job.all_data_json or '{}')
        notices = json.loads(job.special_notices_json or '[]')
        previous = json.loads(job.file_outcomes_json or '[]')
        outcomes = [previous[i] if i < len(previous) and previous[i].get('status') == 'completed' else pending_file({'name': item['name'], **({'page_count': previous[i]['page_count']} if i < len(previous) and previous[i].get('page_count') is not None else {})}) for i, item in enumerate(manifest)]
        for index, item in enumerate(manifest):
            if outcomes[index]['status'] == 'completed':
                continue
            db.expire_all()
            job = db.get(ScrapeJob, job_id)
            if not job or job.status != 'running' or STOP.is_set():
                return
            started = time.monotonic()
            can_start = started < deadline
            if can_start:
                outcomes[index].update(status='running', started_at=stamp(), elapsed_seconds=0)
            else:
                outcomes[index]['not_processed'] = True
            job.file_outcomes_json = json.dumps(outcomes)
            db.commit()
            try:
                if not can_start:
                    raise RuntimeError('Processing exceeded the time limit.')
                version, content, special, section_pages, notice_pages = parse_isolated(job_id, settings.uploads / job_id / item['stored'], deadline)
                if not version:
                    raise ValueError('No FortiOS version detected.')
                if version in data:
                    raise ValueError('Another file already supplies this version; import revisions separately.')
                content['_section_status'] = {
                    key: ('captured' if (value if isinstance(value, list) else value.get('blocks') if isinstance(value, dict) else value) else 'captured_empty' if key in section_pages else 'not_captured')
                    for key, value in content.items() if not key.startswith('_')}
                data[version] = content
                notices.extend({**notice, 'version': version} for notice in special)
                outcomes[index].update(status='completed', version=version, section_pages=section_pages, notice_pages=notice_pages)
            except Exception as exc:
                outcomes[index].update(status='failed', error=str(exc))
            db.expire_all()
            job = db.get(ScrapeJob, job_id)
            if not job or job.status != 'running' or STOP.is_set():
                return
            latest = json.loads(job.file_outcomes_json or '[]')
            if index < len(latest):
                for key in ['progress', 'page_count']:
                    if key in latest[index]:
                        outcomes[index][key] = latest[index][key]
            if can_start:
                outcomes[index].update(completed_at=stamp(), elapsed_seconds=round(max(0, time.monotonic() - started), 3))
            job.file_outcomes_json = json.dumps(outcomes)
            job.all_data_json = json.dumps(data)
            job.special_notices_json = json.dumps(notices)
            job.versions_json = json.dumps(sorted(data, key=lambda v: tuple(map(int, v.split('.')))))
            db.commit()
        versions = sorted(data, key=lambda v: tuple(map(int, v.split('.'))))
        failures = [o for o in outcomes if o['status'] == 'failed']
        job.status = ('partial' if failures else 'completed') if versions else 'failed'
        job.error_message = 'No files were processed successfully.' if not versions else None
        job.versions_json = json.dumps(versions)
        job.all_data_json = json.dumps(data)
        job.special_notices_json = json.dumps(notices)
        job.warnings_json = json.dumps([f"{len(failures)} file(s) failed; report is incomplete."] if failures else [])
        import re
        revisions = {}
        for version, sections in data.items():
            changelog = next((value for key, value in sections.items() if 'change' in key and 'log' in key), {})
            dates = re.findall(r'\b20\d{2}-\d{2}-\d{2}\b', json.dumps(changelog))
            if dates:
                revisions[version] = max(dates)
        job.provenance_json = json.dumps({**json.loads(job.provenance_json or '{}'), 'source': 'pdf', 'parser_revision': PDF_PARSER_REVISION,
            'document_revision': '; '.join(f'{v}: change log through {d}' for v, d in revisions.items()) or 'Not detected; see source change log.',
            'section_policy': 'Absent sections are not evidence of no changes.'})
        job.completed_at = datetime.utcnow()
        db.commit()


def run_job(job_id):
    try:
        with SessionLocal() as db:
            job = db.get(ScrapeJob, job_id)
            source = job.source
            args = json.loads(job.request_json or '{}')
        if source == 'pdf':
            run_pdf(job_id)
        else:
            # Scraping needs network; never available in public mode.
            command = [sys.executable, '-m', 'backend.scrape_process', job_id]
            with LOCK:
                with SessionLocal() as check:
                    current = check.get(ScrapeJob, job_id)
                    if not current or current.status != 'running' or STOP.is_set():
                        return
                process = subprocess.Popen(command, cwd=ROOT, start_new_session=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                CHILDREN[job_id] = process
            try:
                process.wait(timeout=settings.timeout)
                if process.returncode:
                    raise RuntimeError('Scraper process failed.')
            except subprocess.TimeoutExpired:
                terminate(job_id)
                raise RuntimeError('Processing exceeded the time limit.')
            finally:
                with LOCK:
                    CHILDREN.pop(job_id, None)
    except Exception as exc:
        with SessionLocal() as db:
            job = db.get(ScrapeJob, job_id)
            if job and job.status == 'running':
                finish_files(job, 'failed', str(exc))
                job.status, job.error_message = 'failed', str(exc)
                job.completed_at = datetime.utcnow()
                db.commit()

    finally:
        from .administration import record_event
        from .notifications import notify
        with SessionLocal() as db:
            job=db.get(ScrapeJob,job_id)
            if job and job.status in ('completed','partial','failed','cancelled'):
                record_event(db,'job.'+job.status,workspace_id=job.owner_id,target_id=job.id,severity='warning' if job.status in ('failed','partial') else 'info')
                if job.status in ('failed','partial'):notify(db,'job.failed',job.owner_id,job.id)
                db.commit()


def dispatch():
    active = {}
    last_cleanup = 0
    while not STOP.wait(0.5):
        active = {key: t for key, t in active.items() if t.is_alive()}
        with SessionLocal() as db:
            if time.monotonic() - last_cleanup >= 10:
                with LOCK:
                    clean_expired(db)
                last_cleanup = time.monotonic()
            cfg = effective(db, settings)
            owners = {row.owner_id for row in db.query(ScrapeJob).filter(ScrapeJob.id.in_(active)).all()}
            for job in db.query(ScrapeJob).filter(ScrapeJob.status == 'pending').order_by(ScrapeJob.created_at).all():
                if len(active) >= cfg.workers:
                    break
                if job.owner_id in owners:
                    continue
                changed = db.query(ScrapeJob).filter(ScrapeJob.id == job.id, ScrapeJob.status == 'pending').update({'status': 'running', 'started_at': datetime.utcnow()}, synchronize_session=False)
                db.commit()
                if not changed:
                    continue
                thread = threading.Thread(target=run_job, args=(job.id,), daemon=True)
                active[job.id] = thread
                owners.add(job.owner_id)
                thread.start()


def initialize_database():
    from .database import run_migrations, engine
    from .models import Base
    run_migrations()
    Base.metadata.create_all(bind=engine)
    from . import team
    with SessionLocal() as db:
        team.ensure_initial_admin(db)


def start():
    global THREAD, LEASE
    settings.uploads.mkdir(parents=True, exist_ok=True)
    LEASE = open(str(DB_PATH) + '.worker.lock', 'a')
    try:
        fcntl.flock(LEASE, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        LEASE.close()
        LEASE = None
        raise RuntimeError('Run one API/dispatcher process per database.')
    # Acquire the installation lease before additive migrations or any data writes.
    try:
        from .restore_journal import recover
        recover(DB_PATH)
        initialize_database()
        from .container_worker import recover as recover_workers
        recover_workers()
    except BaseException:
        LEASE.close(); LEASE = None
        raise
    STOP.clear()
    with SessionLocal() as db:
        for job in db.query(ScrapeJob).filter(ScrapeJob.status.in_(['running', 'uploading'])).all():
            finish_files(job, 'interrupted', 'Interrupted by server restart.', interrupted=True)
            job.status = 'failed'
            job.error_message = 'Interrupted by server restart; retry or upload again.'
            job.completed_at = datetime.utcnow()
        db.commit()
        clean_expired(db)
    THREAD = threading.Thread(target=dispatch, daemon=True)
    THREAD.start()
    from . import notifications
    notifications.start()


def stop():
    from . import notifications
    notifications.stop()
    STOP.set()
    if THREAD:
        THREAD.join(timeout=5)
    with LOCK, SessionLocal() as db:
        for job in db.query(ScrapeJob).filter(ScrapeJob.status == 'running').all():
            finish_files(job, 'interrupted', 'Interrupted by server shutdown.')
        db.commit()
    for key in list(CHILDREN):
        terminate(key)
    if LEASE:
        LEASE.close()
