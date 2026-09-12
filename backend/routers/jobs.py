from datetime import datetime
import json
import re
import shutil
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import ScrapeJob
from ..schemas import CreateJobRequest, JobDetailResponse, JobResponse
from ..security import owner, owned_job, visible_jobs
from ..settings import settings
from .. import queue, team
from ..file_metrics import finish_files, pending_file
from ..processing_settings import effective, snapshot
from ..build_info import VERSION, BUILD_NUMBER, BUILD_REVISION

router = APIRouter(prefix='/api')


def response(job, detail=False):
    result = (JobDetailResponse if detail else JobResponse).model_validate(job)
    result.include_from = json.loads(job.request_json or '{}').get('include_from', False)
    result.file_outcomes = json.loads(job.file_outcomes_json or '[]')
    result.warnings = json.loads(job.warnings_json or '[]')
    result.provenance = json.loads(job.provenance_json or '{}')
    if job.source == 'pdf':
        result.processing_timeout_seconds = json.loads(job.request_json or '{}').get('processing', {}).get('timeout_seconds')
    if detail:
        result.versions = json.loads(job.versions_json or '[]')
        result.all_data = json.loads(job.all_data_json or '{}')
        result.special_notices = json.loads(job.special_notices_json or '[]')
    return result


@router.get('/capabilities')
def capabilities(request: Request, response: Response, db: Session = Depends(get_db)):
    # Private login must remain discoverable before selecting a workspace.
    from .. import team
    if not team.enabled():
        owner(request, response, db)
    cfg = effective(db, settings)
    return {'team_auth': settings.team_auth and not settings.public, 'version': VERSION, 'build_number': BUILD_NUMBER, 'build_revision': BUILD_REVISION,
            'source_code_url': settings.source_code_url, 'edition': settings.edition, 'scraping': settings.scraping,
            'selenium': settings.scraping and bool(settings.grid_url), 'config_analysis': 'browser-only',
            'retention_hours': 24 if settings.public else None,
            'max_files': cfg.max_files, 'max_file_bytes': settings.file_bytes,
            'max_total_bytes': settings.total_bytes, 'max_pages': cfg.max_pages, 'timeout_minutes': cfg.timeout // 60, 'workers': cfg.workers}


@router.post('/jobs', response_model=JobResponse, status_code=201)
def create_job(req: CreateJobRequest, db: Session = Depends(get_db), owner_id=Depends(owner)):
    if not settings.scraping:
        raise HTTPException(403, 'Scraping is disabled in this edition/deployment.')
    if req.use_selenium and not settings.grid_url:
        raise HTTPException(422, 'Selenium must be configured by the deployment operator.')
    versions = [req.from_version, req.to_version]
    if any(not re.fullmatch(r'\d{1,2}\.\d{1,2}\.\d{1,3}', v) for v in versions):
        raise HTTPException(422, 'Invalid FortiOS version')
    if tuple(map(int, versions[0].split('.'))) >= tuple(map(int, versions[1].split('.'))):
        raise HTTPException(422, 'from_version must be strictly less than to_version')
    job = queue.reserve(db, owner_id, from_version=req.from_version, to_version=req.to_version,
                        source='scrape', use_selenium=req.use_selenium,
                        request_json=req.model_dump_json(), status='pending')
    return response(job)


@router.get('/jobs', response_model=list[JobResponse])
def list_jobs(db: Session = Depends(get_db), owner_id=Depends(owner)):
    return [response(j) for j in visible_jobs(db, owner_id).order_by(ScrapeJob.created_at.desc()).all()]


@router.get('/jobs/{job_id}', response_model=JobDetailResponse)
def get_job(job_id: str, db: Session = Depends(get_db), owner_id=Depends(owner)):
    return response(owned_job(db, job_id, owner_id), True)


@router.post('/jobs/{job_id}/cancel', response_model=JobResponse)
def cancel_job(job_id: str, db: Session = Depends(get_db), owner_id=Depends(owner)):
    with queue.LOCK:
        job = owned_job(db, job_id, owner_id)
        if job.status in {'pending', 'running', 'uploading'}:
            finish_files(job, 'cancelled', 'Cancelled before completion.')
            job.status = 'cancelled'
            job.completed_at = datetime.utcnow()
            team.audit(db, 'job.cancelled', job.id, workspace_id=owner_id)
            db.commit()
            queue.terminate(job_id)
        return response(job)


@router.post('/jobs/{job_id}/retry', response_model=JobResponse)
def retry_job(job_id: str, request: Request, db: Session = Depends(get_db), owner_id=Depends(owner)):
    with queue.LOCK:
        job = owned_job(db, job_id, owner_id)
        if job.status not in {'failed', 'partial', 'cancelled'} or not job.request_json:
            raise HTTPException(409, 'This job cannot be retried. Upload the files again.')
        if job.source != 'pdf' and not settings.scraping:
            raise HTTPException(403, 'Scraping is disabled.')
        db.commit()
        from sqlalchemy import text
        db.execute(text('BEGIN IMMEDIATE'))
        active = db.query(ScrapeJob).filter(ScrapeJob.status.in_(['pending', 'running', 'uploading']))
        if active.filter(ScrapeJob.status != 'running').count() >= settings.queue_size or (settings.public and active.filter(ScrapeJob.owner_id == owner_id).count()):
            db.rollback()
            raise HTTPException(429, 'Queue or session limit reached.')
        if job.source == 'pdf':
            args = json.loads(job.request_json)
            args['processing'] = snapshot(request, effective(db, settings))
            job.request_json = json.dumps(args)
        job.status, job.error_message, job.completed_at, job.started_at = 'pending', None, None, None
        previous = json.loads(job.file_outcomes_json or '[]')
        job.file_outcomes_json = json.dumps([f if f.get('status') == 'completed' else pending_file(f) for f in previous])
        job.warnings_json = '[]'
        team.audit(db, 'job.retried', job.id, workspace_id=owner_id)
        db.commit()
        return response(job)


@router.delete('/jobs/{job_id}', status_code=204)
def delete_job(job_id: str, db: Session = Depends(get_db), owner_id=Depends(owner)):
    with queue.LOCK:
        job = owned_job(db, job_id, owner_id)
        job.status = 'cancelled'
        db.commit()
        queue.terminate(job_id)
        shutil.rmtree(settings.uploads / job_id, ignore_errors=True)
        db.delete(job)
        team.audit(db, 'job.deleted', job_id, workspace_id=owner_id)
        db.commit()


@router.get('/jobs/{job_id}/files/{file_index}')
def source_file(job_id: str, file_index: int, db: Session = Depends(get_db), owner_id=Depends(owner)):
    from pathlib import Path
    from fastapi.responses import FileResponse
    job = owned_job(db, job_id, owner_id)
    if job.source != 'pdf':
        raise HTTPException(404, 'No uploaded PDF for this report')
    files = json.loads(job.request_json or '{}').get('files', [])
    if file_index < 0 or file_index >= len(files):
        raise HTTPException(404, 'Source file not found')
    item = files[file_index]
    root = (settings.uploads / job.id).resolve()
    path = (root / item['stored']).resolve()
    if path.parent != root or not path.is_file() or path.suffix.lower() != '.pdf':
        raise HTTPException(404, 'Source file unavailable')
    return FileResponse(path, media_type='application/pdf', filename=Path(item['name']).name,
                        content_disposition_type='inline')
