import json
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import InstallationSetting
from .. import team, security
from ..processing_settings import ProcessingInput, effective, values

router = APIRouter(prefix='/api/settings')


def authorize(request, db):
    if security.settings.public:
        raise HTTPException(403, 'Public installation limits are managed by the operator.')
    if team.enabled():
        team.admin(request, db)


def view(db):
    base = security.settings
    return {'values': values(effective(db, base)), 'defaults': values(base),
            'bounds': {'timeout_minutes': 120, 'max_files': 100, 'max_pages': 2000, 'workers': min(8, base.workers)}}


@router.get('/processing')
def read_settings(request: Request, db: Session = Depends(get_db)):
    authorize(request, db)
    return view(db)


@router.put('/processing')
def save_settings(value: ProcessingInput, request: Request, db: Session = Depends(get_db)):
    authorize(request, db)
    if value.workers > security.settings.workers:
        raise HTTPException(422, 'Simultaneous jobs cannot exceed the deployment worker limit.')
    row = db.get(InstallationSetting, 'processing')
    if not row:
        row = InstallationSetting(key='processing')
        db.add(row)
    before = values(effective(db, security.settings)) if row.value_json else values(security.settings)
    row.value_json = value.model_dump_json()
    team.audit(db, 'settings.processing.updated', 'processing', details={'before': before, 'after': value.model_dump()})
    db.commit()
    return view(db)


@router.delete('/processing')
def reset_settings(request: Request, db: Session = Depends(get_db)):
    authorize(request, db)
    row = db.get(InstallationSetting, 'processing')
    if row:
        db.delete(row)
    team.audit(db, 'settings.processing.reset', 'processing')
    db.commit()
    return view(db)
