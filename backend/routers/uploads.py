import hashlib
import json
import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..database import get_db
from ..schemas import JobResponse
from ..security import owner
from ..settings import settings
from ..processing_settings import effective, snapshot
import re

def detect_version_from_filename(name):
    match = re.search(r'(?<!\d)(\d{1,2}\.\d{1,2}\.\d{1,3})(?!\d)', name)
    return match.group(1) if match else None
from .. import queue
from .jobs import response

router = APIRouter(prefix='/api')


@router.post('/jobs/upload', response_model=JobResponse, status_code=201)
async def upload_pdfs(request: Request, db: Session = Depends(get_db), owner_id=Depends(owner)):
    cfg = effective(db, settings)
    processing = snapshot(request, cfg)
    # Reserve before reading multipart content to bound concurrent temporary storage.
    job = queue.reserve(db, owner_id, from_version='pending', to_version='pending', source='pdf', status='uploading')
    directory = settings.uploads / job.id
    directory.mkdir(parents=True, mode=0o700)
    try:
        manifest, versions, total = [], [], 0
        async with request.form(max_files=cfg.max_files, max_fields=0) as form:
            files = form.getlist('files')
            if not 1 <= len(files) <= cfg.max_files:
                raise HTTPException(422, f'Upload between 1 and {cfg.max_files} PDFs.')
            for upload in files:
                name = Path(getattr(upload, 'filename', '') or '').name
                version = detect_version_from_filename(name)
                if not name.lower().endswith('.pdf') or not version:
                    raise HTTPException(422, 'Each PDF filename must include its FortiOS version.')
                if version in versions:
                    raise HTTPException(422, 'Upload one document per version; compare revisions in separate jobs.')
                stored = f'{uuid.uuid4().hex}-v{version}.pdf'
                size, digest = 0, hashlib.sha256()
                with (directory / stored).open('xb') as output:
                    while chunk := await upload.read(1024**2):
                        if size == 0 and not chunk.startswith(b'%PDF-'):
                            raise HTTPException(422, 'File is not a PDF document.')
                        size += len(chunk)
                        total += len(chunk)
                        if size > settings.file_bytes or total > settings.total_bytes:
                            raise HTTPException(413, 'PDF upload exceeds the byte limit.')
                        digest.update(chunk)
                        output.write(chunk)
                if not size:
                    raise HTTPException(422, 'Empty PDF file.')
                versions.append(version)
                manifest.append({'name': name[:255], 'stored': stored, 'sha256': digest.hexdigest(), 'bytes': size})
        versions.sort(key=lambda v: tuple(map(int, v.split('.'))))
        with queue.LOCK:
            db.refresh(job)
            if job.status != 'uploading':
                raise HTTPException(409, 'Upload was cancelled.')
            job.from_version, job.to_version = versions[0], versions[-1]
            job.request_json = json.dumps({'files': manifest, 'processing': processing})
            job.file_outcomes_json = json.dumps([{'name': f['name'], 'status': 'pending'} for f in manifest])
            job.provenance_json = json.dumps({'source': 'pdf', 'documents': [{'name': f['name'], 'sha256': f['sha256']} for f in manifest]})
            job.status = 'pending'
            db.commit()
        return response(job)
    except BaseException:
        db.rollback()
        shutil.rmtree(directory, ignore_errors=True)
        existing = db.get(type(job), job.id)
        if existing:
            db.delete(existing)
            db.commit()
        raise
