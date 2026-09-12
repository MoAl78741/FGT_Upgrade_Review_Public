"""Named private-edition accounts, workspace membership, and safe audit metadata."""
import hashlib
import json
import secrets
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import TeamUser, TeamSession, Workspace, WorkspaceMember, AuditEvent
from .. import team, security

router = APIRouter(prefix='/api/auth', tags=['team'])
ATTEMPTS = OrderedDict()
ATTEMPT_LOCK = threading.Lock()


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_.@-]+$')
    password: str = Field(min_length=1, max_length=256)


class NewUser(Credentials):
    password: str = Field(min_length=14, max_length=256)
    is_admin: bool = False


class UserEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    active: bool
    is_admin: bool


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    current_password: str | None = Field(default=None, min_length=1, max_length=256)
    new_password: str = Field(min_length=14, max_length=256)


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra='forbid')
    new_password: str = Field(min_length=14, max_length=256)


class WorkspaceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=160)


class SelectWorkspace(BaseModel):
    model_config = ConfigDict(extra='forbid')
    workspace_id: str = Field(min_length=1, max_length=64)


class MembershipInput(SelectWorkspace):
    user_id: str = Field(min_length=1, max_length=36)
    role: str = Field(min_length=1, max_length=20)


def require_enabled():
    if not team.enabled():
        raise HTTPException(404, 'Named accounts are available only when private team authentication is enabled.')


def rate_limit(request, username=''):
    # Bound memory and slow password work before hashing; never log credentials.
    now = time.monotonic()
    keys = [('ip', request.client.host if request.client else 'unknown'), ('user', username.lower())]
    with ATTEMPT_LOCK:
        for key in keys:
            since, count = ATTEMPTS.get(key, (now, 0))
            if now - since >= 60:
                since, count = now, 0
            if count >= (20 if key[0] == 'ip' else 5):
                raise HTTPException(429, 'Too many sign-in attempts. Try again in one minute.')
            ATTEMPTS[key] = (since, count + 1)
            ATTEMPTS.move_to_end(key)
        while len(ATTEMPTS) > 4096:
            ATTEMPTS.popitem(last=False)


def user_view(user):
    return {'id': user.id, 'username': user.username, 'is_admin': user.is_admin, 'active': user.active, 'must_change_password': user.must_change_password}


def available_workspaces(db, user):
    all_spaces = db.query(Workspace).order_by(Workspace.name).all()
    return [{'id': w.id, 'name': w.name, 'role': role, 'description': w.description, 'firmware_branch': w.firmware_branch, 'state': w.state} for w in all_spaces if (role := team.workspace_role(db, user, w.id))]


def admin_transaction(request, db):
    team.admin(request, db)
    db.commit()
    db.execute(text('BEGIN IMMEDIATE'))
    db.expire_all()
    return team.admin(request, db)


@router.get('/status')
def status(request: Request, db: Session = Depends(get_db)):
    if not team.enabled():
        return {'enabled': False, 'authenticated': False}
    session, user = team.session_user(request, db, required=False, allow_password_change=True)
    if not user:
        return {'enabled': True, 'authenticated': False, 'setup_required': not db.query(TeamUser).count()}
    spaces = [] if user.must_change_password else available_workspaces(db, user)
    return {'enabled': True, 'authenticated': True, 'user': user_view(user), 'workspaces': spaces,
            'permissions': [] if user.must_change_password or not session.workspace_id else __import__('backend.permissions', fromlist=['profile_permissions']).profile_permissions(db, team.workspace_role(db, user, session.workspace_id)) or [],
            'workspace_id': None if user.must_change_password else session.workspace_id, 'role': None if user.must_change_password else team.workspace_role(db, user, session.workspace_id)}


@router.post('/login')
def login(data: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    require_enabled(); rate_limit(request, data.username)
    user = db.query(TeamUser).filter(TeamUser.username == data.username.lower()).first()
    valid = team.verify_password(data.password, user.password_hash if user else team.DUMMY_HASH)
    if not valid or not user or not user.active:
        from ..administration import record_event
        record_event(db, 'session.login_failed', severity='warning');db.commit()
        raise HTTPException(401, 'Invalid username or password.')
    token = secrets.token_urlsafe(32)
    spaces = [] if user.must_change_password else available_workspaces(db, user)
    db.query(TeamSession).filter(TeamSession.expires_at <= datetime.utcnow()).delete()
    # Avoid unlimited session growth while retaining several devices/tabs.
    previous = db.query(TeamSession).filter(TeamSession.user_id == user.id).order_by(TeamSession.expires_at).all()
    for session in previous[:-9]: db.delete(session)
    session = TeamSession(id=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id,
                          workspace_id=spaces[0]['id'] if spaces else None,
                          expires_at=datetime.utcnow() + timedelta(hours=8))
    db.add(session); db.info['actor'] = {'id': user.id, 'name': user.username}
    team.audit(db, 'session.login', user.id)
    db.commit()
    response.set_cookie(team.COOKIE, token, max_age=8 * 3600, secure=security.settings.origin.startswith('https://'),
                        httponly=True, samesite='strict', path='/')
    return {'authenticated': True}


@router.post('/logout', status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    require_enabled()
    session, user = team.session_user(request, db, required=False, allow_password_change=True)
    if session:
        db.delete(session); team.audit(db, 'session.logout', user.id); db.commit()
    response.delete_cookie(team.COOKIE, path='/')


@router.post('/workspace')
def select_workspace(data: SelectWorkspace, request: Request, db: Session = Depends(get_db)):
    require_enabled(); session, user = team.session_user(request, db)
    if not team.workspace_role(db, user, data.workspace_id):
        raise HTTPException(404, 'Workspace not found.')
    session.workspace_id = data.workspace_id
    team.audit(db, 'workspace.select', data.workspace_id, workspace_id=data.workspace_id)
    db.commit()
    return {'workspace_id': data.workspace_id}


@router.post('/password', status_code=204)
def change_password(data: PasswordChange, request: Request, db: Session = Depends(get_db)):
    require_enabled(); session, user = team.session_user(request, db, allow_password_change=True)
    rate_limit(request, user.username)
    if (not user.must_change_password or data.current_password is not None) and not team.verify_password(data.current_password or '', user.password_hash):
        raise HTTPException(401, 'Current password is incorrect.')
    if team.verify_password(data.new_password, user.password_hash):
        raise HTTPException(422, 'Choose a different password.')
    user.password_hash = team.hash_password(data.new_password)
    user.must_change_password = False
    if not session.workspace_id:
        spaces = available_workspaces(db, user)
        session.workspace_id = spaces[0]['id'] if spaces else None
    db.query(TeamSession).filter(TeamSession.user_id == user.id, TeamSession.id != session.id).delete()
    team.audit(db, 'user.password_changed', user.id); db.commit()


@router.get('/users')
def users(request: Request, db: Session = Depends(get_db)):
    team.admin(request, db)
    return [user_view(u) for u in db.query(TeamUser).order_by(TeamUser.username).all()]


@router.post('/users', status_code=201)
def create_user(data: NewUser, request: Request, db: Session = Depends(get_db)):
    team.admin(request, db)
    password_hash = team.hash_password(data.password)
    admin_transaction(request, db)
    if db.query(TeamUser).count() >= 200:
        raise HTTPException(429, 'Account limit reached.')
    if db.query(TeamUser).filter(TeamUser.username == data.username.lower()).first():
        raise HTTPException(409, 'Username is already in use.')
    user = TeamUser(username=data.username.lower(), password_hash=password_hash, is_admin=data.is_admin)
    db.add(user); db.flush(); team.audit(db, 'user.created', user.id, details={'admin': user.is_admin}); db.commit()
    return user_view(user)


@router.put('/users/{user_id}')
def edit_user(user_id: str, data: UserEdit, request: Request, db: Session = Depends(get_db)):
    admin_transaction(request, db)
    user = db.get(TeamUser, user_id)
    if not user: raise HTTPException(404, 'User not found.')
    if user.active and user.is_admin and not (data.active and data.is_admin):
        if db.query(TeamUser).filter(TeamUser.active.is_(True), TeamUser.is_admin.is_(True)).count() <= 1:
            raise HTTPException(409, 'Keep at least one active administrator.')
    user.active, user.is_admin = data.active, data.is_admin
    db.query(TeamSession).filter(TeamSession.user_id == user.id).delete()
    team.audit(db, 'user.access_changed', user.id, details=data.model_dump()); db.commit()
    return user_view(user)


@router.post('/users/{user_id}/password', status_code=204)
def reset_password(user_id: str, data: PasswordReset, request: Request, db: Session = Depends(get_db)):
    team.admin(request, db); password_hash = team.hash_password(data.new_password)
    admin_transaction(request, db)
    user = db.get(TeamUser, user_id)
    if not user: raise HTTPException(404, 'User not found.')
    user.password_hash = password_hash
    db.query(TeamSession).filter(TeamSession.user_id == user.id).delete()
    team.audit(db, 'user.password_reset', user.id); db.commit()


@router.post('/workspaces', status_code=201)
def create_workspace(data: WorkspaceInput, request: Request, db: Session = Depends(get_db)):
    admin_transaction(request, db)
    if not data.name.strip(): raise HTTPException(422, 'Workspace name is required.')
    if db.query(Workspace).count() >= 200: raise HTTPException(429, 'Workspace limit reached.')
    workspace = Workspace(name=data.name.strip()); db.add(workspace); db.flush()
    team.audit(db, 'workspace.created', workspace.id, workspace_id=workspace.id); db.commit()
    return {'id': workspace.id, 'name': workspace.name}


@router.get('/memberships')
def memberships(request: Request, db: Session = Depends(get_db)):
    team.admin(request, db)
    return [{'workspace_id': m.workspace_id, 'user_id': m.user_id, 'role': m.role} for m in db.query(WorkspaceMember).all()]


@router.put('/memberships')
def grant_membership(data: MembershipInput, request: Request, db: Session = Depends(get_db)):
    admin_transaction(request, db)
    if not db.get(TeamUser, data.user_id) or not db.get(Workspace, data.workspace_id):
        raise HTTPException(404, 'User or workspace not found.')
    from ..permissions import profile_permissions
    if data.role == 'admin' or profile_permissions(db, data.role) is None: raise HTTPException(422, 'Unknown access profile.')
    db.merge(WorkspaceMember(**data.model_dump()))
    team.audit(db, 'membership.granted', data.user_id, workspace_id=data.workspace_id, details={'role': data.role}); db.commit()
    return data.model_dump()


@router.delete('/memberships/{workspace_id}/{user_id}', status_code=204)
def revoke_membership(workspace_id: str, user_id: str, request: Request, db: Session = Depends(get_db)):
    admin_transaction(request, db)
    member = db.get(WorkspaceMember, (workspace_id, user_id))
    if not member: raise HTTPException(404, 'Membership not found.')
    db.delete(member);team.audit(db, 'membership.revoked', user_id, workspace_id=workspace_id);db.commit()


@router.get('/audit')
def audit_events(request: Request, target_id: str | None = None, before: int | None = None, db: Session = Depends(get_db)):
    require_enabled()
    workspace_id = team.workspace_owner(request, db)
    query = db.query(AuditEvent).filter(AuditEvent.workspace_id == workspace_id)
    if target_id: query = query.filter(AuditEvent.target_id == target_id)
    if before is not None: query = query.filter(AuditEvent.id < before)
    entries = query.order_by(AuditEvent.id.desc()).limit(100).all()
    return [{'id': e.id, 'actor_name': e.actor_name, 'action': e.action, 'target_id': e.target_id,
             'details': json.loads(e.details_json), 'created_at': e.created_at} for e in entries]


@router.get('/admin-audit')
def admin_audit(request: Request, before: int | None = None, db: Session = Depends(get_db)):
    team.admin(request, db)
    query = db.query(AuditEvent)
    if before is not None: query = query.filter(AuditEvent.id < before)
    return [{'id': e.id, 'actor_name': e.actor_name, 'action': e.action, 'target_id': e.target_id,
             'workspace_id': e.workspace_id, 'details': json.loads(e.details_json), 'created_at': e.created_at}
            for e in query.order_by(AuditEvent.id.desc()).limit(100).all()]
