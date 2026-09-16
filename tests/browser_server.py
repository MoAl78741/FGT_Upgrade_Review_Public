"""Disposable HTTPS app for browser tests. Not imported or shipped as a runtime API."""
import os, sys, json, socket, secrets, shutil, ipaddress
from pathlib import Path
from datetime import datetime, timedelta, timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
sandbox=Path(os.environ['SUITE_SANDBOX']).resolve()
if not sandbox.name.startswith('fgt-suite-') or not (sandbox/'test-only').is_file():raise SystemExit('Refusing to start without an owned disposable suite directory')
port=int(os.environ['SUITE_PORT']);origin=f'https://127.0.0.1:{port}'
edition=os.environ['SUITE_EDITION']
os.environ.update(DB_PATH=str(sandbox/'browser.db'),UPLOADS_DIR=str(sandbox/'browser-uploads'),ADMIN_STATE_DIR=str(sandbox/'browser-admin'),APP_ORIGIN=origin,APP_EDITION=edition,TEAM_AUTH_ENABLED='true' if edition=='private' else 'false',ENABLE_SCRAPING='true',APP_BUILD_NUMBER='test-suite')
from backend import queue, team, models
from backend.database import Base, engine, SessionLocal
from backend.main import app
from backend.security import owner
from backend.administration import set_value
from fastapi import Request, Response, HTTPException, Depends
from fastapi.routing import APIRoute
queue.start=lambda:None;queue.stop=lambda:None
PASSWORD='test-only-correct-horse-battery';HASH=team.hash_password(PASSWORD)
# Never deliver messages or scrape externally from a browser test server.
connect=socket.socket.connect
sendto=socket.socket.sendto
def check(address):
    if isinstance(address,tuple) and not ipaddress.ip_address(address[0]).is_loopback:raise RuntimeError('External network forbidden in browser test server')
def local_connect(sock,address):check(address);return connect(sock,address)
def local_sendto(sock,data,*args):check(args[-1]);return sendto(sock,data,*args)
socket.socket.connect=local_connect;socket.socket.sendto=local_sendto

def guard(request):
    if request.headers.get('X-Test-Control')!=(sandbox/'test-only').read_text():raise HTTPException(404)

def reset_data(bootstrap=False,features=True):
    from backend.routers.auth import ATTEMPTS
    ATTEMPTS.clear()
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    shutil.rmtree(sandbox/'browser-uploads',ignore_errors=True);(sandbox/'browser-uploads').mkdir()
    with SessionLocal() as db:
        if edition=='private':
            db.add(models.Workspace(id='one',name='Synthetic workspace'))
            db.add(models.TeamUser(id='admin',username='admin',password_hash=HASH,is_admin=True,must_change_password=bootstrap))
            try:
                from backend.features import CATALOG
                set_value(db,'features',{key:features for key in CATALOG})
            except ImportError:pass
        else:
            db.add(models.OperatorUser(id='operator',username='operator',password_hash=HASH,must_change_password=False))
        try:
            from backend.packs.registry import bootstrap as packs
            packs(db)
        except ImportError:pass
        db.commit()
from reportlab.pdfgen.canvas import Canvas
canvas=Canvas(str(sandbox/'synthetic.pdf'));canvas.drawString(50,700,'FortiOS 7.6.6 synthetic release notes');canvas.save()
reset_data()
async def reset(request:Request):
    guard(request);data=await request.json();reset_data(data.get('bootstrap',False),data.get('features',True));return {'ok':True}
async def seed(request:Request,response:Response):
    guard(request)
    with SessionLocal() as db:
        own=owner(Request(dict(request.scope, path='/api/jobs', method='GET')),response,db)
        row={'Bug ID':'123456','category':'Routing','Description':'BGP source sentinel must remain unchanged.','markdown':'BGP **source sentinel** must remain unchanged.'}
        data={'7.6.5':{'known_issues':[row],'resolved-issue':[{'Bug ID':'111111','Description':'Legacy resolved sentinel'}],'additional-changes':[{'Feature ID':'GEN-1','Description':'Generic chapter sentinel','markdown':'Generic **chapter** sentinel'}]},'7.6.6':{'known_issues':[row],'resolved-issues':[{'Bug ID':'222222','Description':'Current resolved sentinel'}],'additional-changes':[{'Feature ID':'GEN-1','Description':'Generic chapter sentinel','markdown':'Generic **chapter** sentinel'}]}}
        job=models.ScrapeJob(id='fixture',owner_id=own,source='pdf',status='completed',expires_at=datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(hours=24),from_version='7.6.5',to_version='7.6.6',created_at=datetime.now(timezone.utc).replace(tzinfo=None),completed_at=datetime.now(timezone.utc).replace(tzinfo=None),versions_json=json.dumps(list(data)),all_data_json=json.dumps(data),file_outcomes_json=json.dumps([{'name':'missing.pdf','status':'completed','page_count':17,'elapsed_seconds':2.5}]),request_json=json.dumps({'files':[{'stored':'missing.pdf','name':'missing.pdf'}]}),provenance_json='{"source":"pdf","parser_revision":"synthetic-test"}')
        db.add(job);db.commit()
    return {'id':'fixture'}
app.router.routes.insert(0,APIRoute('/__test/reset',reset,methods=['POST']))
app.router.routes.insert(0,APIRoute('/__test/seed',seed,methods=['POST']))
# Self-signed TLS stays inside this disposable directory; no system trust changes.
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Disposable regression server')])
cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(datetime.now(timezone.utc)-timedelta(minutes=1)).not_valid_after(datetime.now(timezone.utc)+timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False).sign(key,hashes.SHA256())
(sandbox/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()));(sandbox/'key.pem').chmod(0o600)
(sandbox/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
import uvicorn
uvicorn.run(app,host='127.0.0.1',port=port,ssl_keyfile=str(sandbox/'key.pem'),ssl_certfile=str(sandbox/'cert.pem'),log_level='warning')
