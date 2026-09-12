"""Offline Swagger UI; no CDN scripts or relaxed script CSP."""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, Response, PlainTextResponse

router = APIRouter()
ROOT = Path(__file__).resolve().parent.parent

@router.get('/docs', include_in_schema=False)
def old_docs():
    return RedirectResponse('/api/docs')

@router.get('/openapi.json', include_in_schema=False)
def old_schema():
    return RedirectResponse('/api/openapi.json')

@router.get('/api/docs/guide', include_in_schema=False, response_class=PlainTextResponse)
def guide():
    return (ROOT / 'API_GUIDE.md').read_text()

@router.get('/api/docs', include_in_schema=False, response_class=HTMLResponse)
def docs():
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Release Note Review API — Swagger UI</title><link rel="stylesheet" href="/api/docs/assets/swagger-ui.css"></head><body><div id="swagger-ui"></div><script src="/api/docs/assets/swagger-ui-bundle.js"></script><script src="/api/docs/init.js"></script></body></html>'''

@router.get('/api/docs/assets/{name}', include_in_schema=False)
def asset(name: str):
    if name not in {'swagger-ui.css', 'swagger-ui-bundle.js'}:
        raise HTTPException(404)
    for directory in [ROOT / 'frontend/dist/api-docs', ROOT / 'frontend/node_modules/swagger-ui-dist']:
        path = directory / name
        if path.is_file():
            return FileResponse(path)
    raise HTTPException(503, 'Build frontend assets to install offline Swagger UI.')

@router.get('/api/docs/init.js', include_in_schema=False)
def initialize():
    return Response('''window.ui = SwaggerUIBundle({
      url: '/api/openapi.json', dom_id: '#swagger-ui', deepLinking: true,
      presets: [SwaggerUIBundle.presets.apis], layout: 'BaseLayout',
      validatorUrl: null, persistAuthorization: false, withCredentials: true,
      requestInterceptor: async function(request) {
        const target = new URL(request.url, location.origin);
        if (target.origin !== location.origin) throw new Error('Only this installation may be called.');
        if (!target.pathname.endsWith('/capabilities') && !target.pathname.endsWith('/openapi.json')) {
          await fetch('/api/capabilities', {credentials: 'same-origin'});
        }
        request.credentials = 'same-origin';
        return request;
      }
    });''', media_type='application/javascript')


def configure_schema(app):
    from fastapi.openapi.utils import get_openapi
    def schema():
        if app.openapi_schema:
            return app.openapi_schema
        result = get_openapi(title=app.title, version=app.version, routes=app.routes,
            description='''Use **Try it out** below. Docs and assets work offline.

**Public sessions:** first call GET /api/capabilities and retain the HttpOnly cookie.
**Private teams:** call POST /api/auth/login; change a temporary password with POST /api/auth/password before proceeding. Select a workspace using POST /api/auth/workspace ; X-Workspace-ID guards against stale workspace selection. Swagger uses your existing browser login. Viewer roles may read and export; changes require reviewer/admin access.
**Public operators:** use POST /api/administration/login and /password for the separate operator account. Ordinary visitor cookies cannot administer the installation. Domain profiles, SMTP, syslog and scheduled summaries require a private installation administrator.
**Scripts:** retain cookies (e.g. curl -c cookies.txt -b cookies.txt), send Origin matching the installation's exact HTTPS origin on POST/PUT/DELETE requests, and use your installation's trusted CA. UUIDs do not grant access.

Report exports use the same source renderer as the GUI. HTML exports are self-contained and print-ready; print them to PDF, as in the GUI. Filtering and consolidation never alter stored reports.

**Local-only API:** /assets/local-api.mjs exports analyzeConfig, relevance, emptyProfile, reportView, reportHtml, compareFeatures, pdfReleaseRange and reviewPackageHtml. Import this module in your own browser or Node application. Config contents, feature profiles, manual feature corrections, and local appearance preferences stay on the client. No config-upload endpoint exists. See the [GUI/API map and examples](/api/docs/guide), also included as API_GUIDE.md in the corresponding source.''')
        for path, methods in result['paths'].items():
            for method, op in methods.items():
                if method not in {'get', 'post', 'put', 'patch', 'delete', 'head', 'options'}:
                    continue
                if not op.get('tags'):
                    op['tags'] = ['processing settings' if '/settings/' in path else 'reports' if '/jobs' in path else 'installation']
                params = op.setdefault('parameters', [])
                if path.startswith(('/api/jobs', '/api/reviews')):
                    params.append({'in':'header', 'name':'X-Workspace-ID', 'required':False, 'schema':{'type':'string'}, 'description':'Optional stale-workspace guard; must match the selected workspace. Select with POST /api/auth/workspace.'})
                if path in {'/api/jobs/upload', '/api/jobs/{job_id}/retry'}:
                    params.append({'in':'header','name':'X-PDF-Timeout-Minutes','required':False,'schema':{'type':'integer','minimum':1,'maximum':120}, 'description':'Attempt timeout; cannot exceed the effective installation limit.'})
        # Uploads intentionally parse multipart only after authentication/queue reservation.
        # Describe their body explicitly without introducing eager FastAPI File parsing.
        result['paths']['/api/jobs/upload']['post']['requestBody'] = {
            'required': True,
            'content': {'multipart/form-data': {'schema': {
                'type': 'object', 'required': ['files'],
                'properties': {'files': {'type': 'array', 'minItems': 1,
                    'items': {'type': 'string', 'format': 'binary'},
                    'description': 'One PDF per version. Repeat the files field; filenames must include the FortiOS version. Effective count and byte limits are returned by GET /api/capabilities.'}}
            }}}
        }
        for path, method, mime, description in [
            ('/api/administration/backup', 'post', 'application/octet-stream', 'Encrypted .fgtbackup archive; save the binary response.'),
            ('/api/administration/certificates/{identity}/download', 'get', 'application/x-pem-file', 'Public PEM certificate chain; private key is never returned.'),
            ('/api/jobs/{job_id}/files/{file_index}', 'get', 'application/pdf', 'Original source PDF, subject to report ownership and retention.'),
        ]:
            result['paths'][path][method]['responses']['200'] = {
                'description': description,
                'content': {mime: {'schema': {'type': 'string', 'format': 'binary'}}},
            }
        app.openapi_schema = result
        return result
    app.openapi = schema
