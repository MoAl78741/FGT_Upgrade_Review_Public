"""Operator-only installation services. Secrets never appear in configuration responses."""
import hashlib
import json
import os
import secrets
import threading
KEY_LOCK=threading.RLock()
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import HTTPException
from cryptography.fernet import Fernet
from .database import DB_PATH
from .models import InstallationSetting, OperatorUser, OperatorSession, SystemEvent
from . import security, team

COOKIE='fgt_operator_session'

def state_dir():
    p=Path(os.environ.get('ADMIN_STATE_DIR', str(Path(DB_PATH).parent/'administration')))
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    return p

def cipher():
    with KEY_LOCK:return _cipher()

def _cipher():
    path=state_dir()/'secret.key'
    if not path.exists():
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as f:f.write(Fernet.generate_key())
        except FileExistsError:pass
    return Fernet(path.read_bytes())

def get_value(db,key,default=None):
    row=db.get(InstallationSetting,key)
    return json.loads(row.value_json) if row else default

def set_value(db,key,value):
    db.merge(InstallationSetting(key=key,value_json=json.dumps(value)))

def secret(value):return cipher().encrypt(value.encode()).decode() if value else ''
def reveal(value):return cipher().decrypt(value.encode()).decode() if value else ''

def record_event(db, action, actor='system', workspace_id=None,target_id='',severity='info'):
    # Only bounded action/identity metadata; never arbitrary exception messages or request bodies.
    cutoff=db.query(SystemEvent.id).order_by(SystemEvent.id.desc()).offset(9999).scalar()
    if cutoff:db.query(SystemEvent).filter(SystemEvent.id<=cutoff).delete(synchronize_session=False)
    db.add(SystemEvent(action=action[:80],actor=actor[:80],workspace_id=workspace_id,target_id=target_id[:64],severity=severity))

def operator_session(request,db,allow_change=False,required=True):
    token=request.cookies.get(COOKIE,'')
    session=db.get(OperatorSession,hashlib.sha256(token.encode()).hexdigest()) if token else None
    user=db.get(OperatorUser,session.user_id) if session and session.expires_at>datetime.utcnow() else None
    if not user:
        if required:raise HTTPException(401,'Sign in as an installation operator.')
        return None,None
    if user.must_change_password and not allow_change:raise HTTPException(403,'Change your initial operator password first.')
    db.info['actor']={'id':user.id,'name':user.username}
    return session,user

def authorize(request,db):
    if security.settings.public:
        _,user=operator_session(request,db)
        return user
    # System operations always require a named admin, even in an unauthenticated local harness.
    return team.admin(request,db)

def actor(request,db):
    user=authorize(request,db)
    return user.username

def verify_current(request,db,password):
    user=authorize(request,db)
    from .routers.auth import rate_limit
    rate_limit(request,user.username)
    if not team.verify_password(password,user.password_hash):raise HTTPException(401,'Current password is incorrect.')
    return user
