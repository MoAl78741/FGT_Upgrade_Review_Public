"""Validated PEM inventory and trusted Caddy activation with rollback."""
import hashlib,json,os,shutil,ssl,uuid
from datetime import datetime,timezone
from urllib.parse import urlsplit
from pathlib import Path
import requests
from urllib3.util.ssl_match_hostname import match_hostname
from cryptography import x509
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import rsa,ec
from fastapi import HTTPException
from .administration import state_dir,record_event
from . import security

def directory():
    p=state_dir()/'certificates';p.mkdir(exist_ok=True,mode=0o700);return p

def cert_info(cert):
    try:sans=cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:sans=[]
    return {'subject':cert.subject.rfc4514_string(),'issuer':cert.issuer.rfc4514_string(),
      'serial':str(cert.serial_number),'fingerprint_sha256':cert.fingerprint(hashes.SHA256()).hex(),
      'not_before':cert.not_valid_before_utc.isoformat(),'not_after':cert.not_valid_after_utc.isoformat(),
      'days_remaining':(cert.not_valid_after_utc-datetime.now(timezone.utc)).days,
      'names':[str(v.value) for v in sans]}

def inventory():
    result=[];active=(directory()/'active').read_text() if (directory()/'active').exists() else None
    for p in directory().glob('*/chain.pem'):
        try:result.append({'id':p.parent.name,'active':p.parent.name==active,**cert_info(x509.load_pem_x509_certificate(p.read_bytes()))})
        except ValueError:continue
    return result

def upload(chain,key,password=''):
    if len(chain)>256*1024 or len(key)>64*1024:raise ValueError('Certificate chain or private key exceeds the size limit.')
    certs=x509.load_pem_x509_certificates(chain)
    if not 1<=len(certs)<=12:raise ValueError('Provide a PEM leaf certificate followed by its intermediate chain.')
    private=serialization.load_pem_private_key(key,password=password.encode() if password else None)
    if isinstance(private,rsa.RSAPrivateKey) and private.key_size<2048:raise ValueError('RSA keys must be at least 2048 bits.')
    if isinstance(private,ec.EllipticCurvePrivateKey) and private.key_size<256:raise ValueError('EC keys must be at least 256 bits.')
    if not isinstance(private,(rsa.RSAPrivateKey,ec.EllipticCurvePrivateKey)):raise ValueError('Use an RSA or EC server key.')
    public=lambda k:k.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    if public(private.public_key())!=public(certs[0].public_key()):raise ValueError('The private key does not match the leaf certificate.')
    now=datetime.now(timezone.utc)
    if any(c.not_valid_before_utc>now or c.not_valid_after_utc<=now for c in certs):raise ValueError('The certificate chain is expired or not yet valid.')
    for leaf,issuer in zip(certs,certs[1:]):leaf.verify_directly_issued_by(issuer)
    try:
        eku=certs[0].extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        if x509.oid.ExtendedKeyUsageOID.SERVER_AUTH not in eku:raise ValueError('Certificate does not allow TLS server authentication.')
    except x509.ExtensionNotFound:pass
    # Hostname validation uses SANs; subject CN alone is insufficient.
    san=certs[0].extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    names=[('DNS',v.value) if isinstance(v,x509.DNSName) else ('IP Address',str(v.value)) for v in san if isinstance(v,(x509.DNSName,x509.IPAddress))]
    match_hostname({'subjectAltName':names},urlsplit(security.settings.origin).hostname.encode('idna').decode())
    if len(inventory())>=20:raise ValueError('Delete an unused certificate before uploading another (20 maximum).')
    identity=str(uuid.uuid4());p=directory()/identity;p.mkdir(mode=0o700)
    for name,data in [('chain.pem',chain),('key.pem',private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))]:
        fd=os.open(p/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(data)
    return {'id':identity,**cert_info(certs[0])}

def get_path(identity):
    try:
        if str(uuid.UUID(identity))!=identity:raise ValueError()
    except ValueError:raise HTTPException(404,'Certificate not found.')
    p=directory()/identity
    if not (p/'chain.pem').exists():raise HTTPException(404,'Certificate not found.')
    return p

def activate(identity):
    p=get_path(identity)
    endpoint=os.getenv('CADDY_ADMIN_URL','').rstrip('/')
    template=os.getenv('CADDY_CONFIG_TEMPLATE','')
    if not endpoint or not template:raise HTTPException(409,'Certificate activation needs the documented Caddy management connection. Upload and inspection remain available.')
    # Template and control endpoint are deployment-owned, never accepted from a request.
    config=json.loads(Path(template).read_text())
    mount=os.getenv('CADDY_CERTIFICATE_MOUNT','/certificates').rstrip('/')
    config.setdefault('apps',{}).setdefault('tls',{})['certificates']={'load_files':[{'certificate':f'{mount}/{identity}/chain.pem','key':f'{mount}/{identity}/key.pem'}]}
    now=datetime.now(timezone.utc)
    if x509.load_pem_x509_certificate((p/'chain.pem').read_bytes()).not_valid_after_utc<=now:raise HTTPException(422,'Certificate has expired.')
    session=requests.Session();session.trust_env=False
    try:
        # Caddy /load applies atomically and preserves its running configuration on rejection.
        response=session.post(endpoint+'/load',json=config,timeout=10,allow_redirects=False)
        if response.status_code!=200:raise HTTPException(502,'Proxy rejected certificate activation; its previous configuration remains active.')
    except requests.RequestException:raise HTTPException(502,'Unable to confirm proxy activation. Inspect the proxy before retrying.') from None
    finally:session.close()
    temp=directory()/'active.tmp';temp.write_text(identity);os.replace(temp,directory()/'active')
    return {'active':identity}
