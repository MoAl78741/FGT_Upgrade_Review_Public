"""Bounded subprocess for the same trusted renderer used by the browser.

Inputs are scoped report data, never raw configuration or executable code.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

ROOT = Path(__file__).resolve().parent.parent
SLOTS = threading.BoundedSemaphore(1)
MAX_BYTES = 64 * 1024**2


def render(payload):
    node = os.environ.get('NODE_BINARY') or shutil.which('node')
    if not node or not (ROOT / 'frontend/dist/server-renderer.cjs').is_file():
        raise HTTPException(503, 'Report renderer unavailable. Install Node.js 22 and run the frontend build.')
    if not SLOTS.acquire(blocking=False):
        raise HTTPException(429, 'Report rendering is busy. Retry shortly.')
    timeout = 120 if payload.get('operation') in {'html', 'review'} else 30
    try:
        data = json.dumps(jsonable_encoder(payload), ensure_ascii=False).encode()
        if len(data) > MAX_BYTES:
            raise HTTPException(413, 'Report too large to export at once. Select fewer sections or versions.')
        with tempfile.TemporaryFile() as output:
            # Fixed executable and entry point; no shell, user-supplied code or paths.
            result = subprocess.run([node, '--max-old-space-size=512', '--permission',
                '--allow-fs-read=' + str(ROOT / 'backend/render_cli.cjs'),
                '--allow-fs-read=' + str(ROOT / 'frontend/dist/server-renderer.cjs'),
                str(ROOT / 'backend/render_cli.cjs')], input=data, stdout=output, stderr=subprocess.DEVNULL,
                timeout=timeout, cwd=ROOT, env={'LANG':'C.UTF-8', 'TZ':'UTC', 'NODE_ENV':'production'})
            if output.tell() > MAX_BYTES:
                raise HTTPException(413, 'Export too large. Select fewer sections or versions.')
            output.seek(0)
            try:
                body = json.load(output)
            except (ValueError, UnicodeDecodeError):
                raise HTTPException(503, 'Report renderer could not complete this request.')
            if result.returncode or 'error' in body:
                # Never expose report content or internal stack traces on failure.
                raise HTTPException(422, 'Unable to render the requested content. Check versions and section choices.')
            return body['result']
    except subprocess.TimeoutExpired:
        raise HTTPException(504, f'Report rendering exceeded {timeout} seconds. Select fewer sections or versions.')
    except OSError:
        raise HTTPException(503, 'Report renderer could not start.')
    finally:
        SLOTS.release()
