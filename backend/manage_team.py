"""Local-only administrator bootstrap/recovery. Never accepts passwords in arguments."""
import argparse
import getpass
import re
import stat
from pathlib import Path
from sqlalchemy import text
from .database import engine, SessionLocal, run_migrations
from .models import Base, TeamUser, TeamSession, Workspace, ScrapeJob, AuditEvent
from .team import hash_password


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['bootstrap', 'reset-password', 'initialize-admin'])
    parser.add_argument('--username')
    parser.add_argument('--password-file', type=Path)
    args = parser.parse_args()
    from .settings import settings
    if settings.public:
        parser.error('Team account setup is only available for a private installation.')
    if args.action == 'initialize-admin':
        from . import team
        if not team.enabled():
            parser.error('Enable private TEAM_AUTH_ENABLED before initializing the initial administrator.')
        run_migrations(); Base.metadata.create_all(engine)
        with SessionLocal() as db:
            created = team.ensure_initial_admin(db, allow_existing=True)
        print('Initial administrator created; password change required.' if created else 'Existing administrator left unchanged.')
        return
    if not args.username:
        parser.error('--username is required for bootstrap or recovery.')
    username = args.username.lower()
    if not re.fullmatch(r'[a-z0-9_.@-]{1,80}', username):
        parser.error('Username must contain only letters, numbers, periods, underscores, @ or hyphens.')
    if args.password_file:
        info = args.password_file.stat()
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
            parser.error('Password file must be a regular owner-only file (chmod 600).')
        password = args.password_file.read_text().rstrip('\r\n')
    else:
        password = getpass.getpass('Password (at least 14 characters): ')
        if password != getpass.getpass('Confirm password: '): parser.error('Passwords do not match.')
    if not 14 <= len(password) <= 256 or '\n' in password or '\r' in password:
        parser.error('Use a password of 14–256 characters on one line.')
    encoded = hash_password(password)
    run_migrations(); Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.execute(text('BEGIN IMMEDIATE'))
        if args.action == 'bootstrap':
            if db.query(TeamUser).count(): parser.error('Accounts already exist; use reset-password for recovery.')
            if not db.get(Workspace, 'local'): db.add(Workspace(id='local', name='Existing installation'))
            user = TeamUser(username=username, password_hash=encoded, is_admin=True)
            db.add(user); db.flush()
            # Assign only unowned legacy private data to its existing workspace.
            db.query(ScrapeJob).filter(ScrapeJob.owner_id.is_(None)).update({'owner_id': 'local'})
            db.add(AuditEvent(actor_id=user.id, actor_name=username, action='admin.bootstrap', target_id=user.id, workspace_id='local'))
        else:
            user = db.query(TeamUser).filter(TeamUser.username == username).first()
            if not user: parser.error('Account not found.')
            user.password_hash = encoded; user.active = True
            db.query(TeamSession).filter(TeamSession.user_id == user.id).delete()
            db.add(AuditEvent(actor_id=user.id, actor_name='local-operator', action='user.password_recovered', target_id=user.id))
        db.commit()
    print('Account updated. Configure TEAM_AUTH_ENABLED=true for the private edition and restart the application.')


if __name__ == '__main__':
    main()
