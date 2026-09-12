"""Private-edition identities and workspace authorization. No config data is stored."""
import hashlib
import hmac
import json
import secrets
from datetime import datetime
from fastapi import HTTPException
from .models import TeamUser, TeamSession, Workspace, WorkspaceMember, AuditEvent
from . import security

COOKIE = 'fgt_team_session'
ITERATIONS = 600_000


def enabled():
    return security.settings.team_auth and not security.settings.public


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${digest}'


def verify_password(password, encoded):
    try:
        algorithm, iterations, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2_sha256' or int(iterations) != ITERATIONS:
            return False
        computed = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(computed, expected)
    except (ValueError, TypeError):
        return False


# Same expensive verification path for unknown users. This hash never authenticates one.
DUMMY_HASH = 'pbkdf2_sha256$600000$' + '00' * 16 + '$' + '00' * 32


def session_user(request, db, required=True, allow_password_change=False):
    token = request.cookies.get(COOKIE, '')
    session = db.get(TeamSession, hashlib.sha256(token.encode()).hexdigest()) if token else None
    user = db.get(TeamUser, session.user_id) if session and session.expires_at > datetime.utcnow() else None
    if not user or not user.active:
        if required:
            raise HTTPException(401, 'Sign in to continue.')
        return None, None
    if user.must_change_password and not allow_password_change:
        raise HTTPException(403, 'Change your initial password before continuing.')
    db.info['actor'] = {'id': user.id, 'name': user.username}
    return session, user


def workspace_role(db, user, workspace_id):
    if not workspace_id or not db.get(Workspace, workspace_id):
        return None
    if user.is_admin:
        return 'admin'
    membership = db.get(WorkspaceMember, (workspace_id, user.id))
    return membership.role if membership else None


def workspace_owner(request, db, *, read_only=False):
    session, user = session_user(request, db)
    role = workspace_role(db, user, session.workspace_id)
    if not role:
        raise HTTPException(403, 'Select an assigned customer workspace.')
    selected = request.headers.get('x-workspace-id')
    if selected and selected != session.workspace_id:
        raise HTTPException(409, 'Workspace changed in another tab. Reload before continuing.')
    if not read_only and request.method not in {'GET', 'HEAD', 'OPTIONS'} and role == 'viewer':
        raise HTTPException(403, 'Viewer access does not allow changes.')
    db.info['workspace'] = session.workspace_id
    return session.workspace_id


def admin(request, db):
    if not enabled():
        raise HTTPException(404, 'Team administration is not enabled.')
    _, user = session_user(request, db)
    if not user.is_admin:
        raise HTTPException(403, 'Administrator access required.')
    return user


def audit(db, action, target, workspace_id=None, details=None):
    if not enabled():
        return
    actor = db.info.get('actor')
    if not actor:
        return
    db.add(AuditEvent(actor_id=actor['id'], actor_name=actor['name'], action=action,
                      target_id=str(target), workspace_id=workspace_id or db.info.get('workspace'),
                      details_json=json.dumps(details or {})))


def ensure_initial_admin(db, allow_existing=False):
    """Initialize once; never restore a default password to an existing account."""
    if not enabled():
        return False
    from sqlalchemy import text
    from .models import ScrapeJob
    db.execute(text('BEGIN IMMEDIATE'))
    count = db.query(TeamUser).count()
    if (count and not allow_existing) or db.query(TeamUser).filter(TeamUser.username == 'admin').first():
        db.rollback()
        return False
    if not db.get(Workspace, 'local'):
        db.add(Workspace(id='local', name='Existing installation'))
    user = TeamUser(username='admin', password_hash=hash_password('password'), is_admin=True, must_change_password=True)
    db.add(user); db.flush()
    if not count:
        db.query(ScrapeJob).filter(ScrapeJob.owner_id.is_(None)).update({'owner_id': 'local'})
    db.add(AuditEvent(actor_id=user.id, actor_name='local-operator', action='admin.initialized', target_id=user.id, workspace_id='local'))
    db.commit()
    return True
