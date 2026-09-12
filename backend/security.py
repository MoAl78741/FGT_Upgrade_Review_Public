"""Session ownership and browser request isolation, shared by every API route."""
import hashlib
import secrets
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from .database import get_db
from .models import BrowserSession, ScrapeJob
from .settings import settings

COOKIE = 'fgt_session'

def owner(request: Request, response: Response, db: Session = Depends(get_db)) -> str:
    if not settings.public:
        from . import team
        if team.enabled():
            return team.workspace_owner(request, db)
        return 'local'
    token = request.cookies.get(COOKIE, '')
    digest = hashlib.sha256(token.encode()).hexdigest()
    session = db.get(BrowserSession, digest) if token else None
    if not session or session.expires_at <= datetime.utcnow():
        if request.url.path != '/api/capabilities':
            raise HTTPException(401, 'Session expired. Reload to start a new private session.')
        if db.query(BrowserSession).count() >= 10000:
            raise HTTPException(429, 'Session capacity reached. Try again later.')
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        db.add(BrowserSession(id=digest, expires_at=datetime.utcnow() + timedelta(hours=24)))
        db.commit()
        response.set_cookie(COOKIE, token, max_age=86400, secure=True, httponly=True, samesite='strict', path='/')
    return digest


def visible_jobs(db: Session, owner_id: str):
    q = db.query(ScrapeJob)
    if settings.public:
        q = q.filter(ScrapeJob.owner_id == owner_id, ScrapeJob.expires_at > datetime.utcnow())
    elif settings.team_auth:
        q = q.filter(ScrapeJob.owner_id == owner_id)
    return q


def owned_job(db, job_id, owner_id):
    job = visible_jobs(db, owner_id).filter(ScrapeJob.id == job_id).first()
    if job is None:
        raise HTTPException(404, 'Job not found')
    return job


class RequestSecurity:
    """Check origins and bound streamed request bodies before multipart parsing."""
    def __init__(self, app):
        self.app = app
        self.rates = OrderedDict()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        from starlette.responses import JSONResponse
        if settings.public and scope['path'].startswith('/api/'):
            now = time.monotonic()
            key = (scope.get('client') or ('unknown',))[0]
            since, count = self.rates.pop(key, (now, 0))
            if now - since >= 60:
                since, count = now, 0
            self.rates[key] = (since, count + 1)
            if len(self.rates) > 4096:
                self.rates.popitem(last=False)
            if count >= 240:
                return await JSONResponse({'detail': 'Request rate exceeded. Retry in one minute.'}, 429)(scope, receive, send)
        headers = dict(scope['headers'])
        host = headers.get(b'host', b'').decode().lower()
        allowed = {urlsplit(o).netloc.lower() for o in settings.origins}
        origin = headers.get(b'origin', b'').decode()
        mutation = scope['method'] not in {'GET', 'HEAD', 'OPTIONS'}
        if host not in allowed:
            return await JSONResponse({'detail': 'Untrusted host'}, 400)(scope, receive, send)
        if (origin and origin not in settings.origins) or (mutation and (settings.public or settings.team_auth) and origin not in settings.origins):
            return await JSONResponse({'detail': 'Untrusted origin'}, 403)(scope, receive, send)
        if mutation and headers.get(b'sec-fetch-site') == b'cross-site':
            return await JSONResponse({'detail': 'Cross-site request denied'}, 403)(scope, receive, send)
        limit = settings.total_bytes + 1024**2 if scope['path'] == '/api/jobs/upload' else 64 * 1024
        try:
            length = int(headers.get(b'content-length', b'0'))
        except ValueError:
            length = limit + 1
        if length > limit:
            return await JSONResponse({'detail': 'Request exceeds upload limit'}, 413)(scope, receive, send)
        size = 0
        async def bounded_receive():
            nonlocal size
            message = await receive()
            size += len(message.get('body', b''))
            if size > limit:
                raise HTTPException(413, 'Request exceeds upload limit')
            return message
        async def secure_send(message):
            if message['type'] == 'http.response.start':
                message.setdefault('headers', []).extend([
                    (b'x-content-type-options', b'nosniff'),
                    (b'referrer-policy', b'no-referrer'),
                    (b'x-frame-options', b'DENY'),
                    (b'cache-control', b'no-store'),
                    (b'content-security-policy', b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self' ws://localhost:5173 ws://127.0.0.1:5173; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")])
            await send(message)
        await self.app(scope, bounded_receive, secure_send)


def read_owner(request: Request, response: Response, db: Session = Depends(get_db)) -> str:
    """For explicitly read-only POST view/export operations; ownership still applies."""
    from . import team
    if not settings.public and team.enabled():
        return team.workspace_owner(request, db, read_only=True)
    return owner(request, response, db)
