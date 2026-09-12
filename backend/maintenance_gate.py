"""Drain HTTP operations before installation snapshots/replacements."""
import threading
from contextlib import contextmanager
from fastapi import HTTPException
from starlette.responses import JSONResponse
LOCK=threading.Lock();ACTIVE=0;BUSY=False
class MaintenanceGate:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        global ACTIVE
        if scope['type']!='http' or not scope['path'].startswith('/api/'):
            return await self.app(scope,receive,send)
        with LOCK:
            rejected=BUSY
            if not rejected:ACTIVE+=1
        if rejected:return await JSONResponse({'detail':'Installation maintenance in progress. Retry shortly.'},status_code=503)(scope,receive,send)
        try:await self.app(scope,receive,send)
        finally:
            with LOCK:ACTIVE-=1
@contextmanager
def exclusive():
    global BUSY
    with LOCK:
        if BUSY or ACTIVE>1:raise HTTPException(409,'Other requests are active. Retry maintenance after they finish.')
        BUSY=True
    try:yield
    finally:
        with LOCK:BUSY=False
