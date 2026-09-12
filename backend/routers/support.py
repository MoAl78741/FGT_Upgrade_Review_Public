"""Private operator diagnostics with a deliberately narrow, non-content payload."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..database import get_db
from .. import team
from ..settings import settings
from ..maintenance import diagnostics

router = APIRouter(prefix='/api/support', tags=['support'])

@router.get('/diagnostics')
def support_diagnostics(request: Request, db: Session = Depends(get_db)):
    if settings.public:
        raise HTTPException(404, 'Support diagnostics are available only for private installations.')
    if team.enabled(): team.admin(request, db)
    return diagnostics()
