"""Installation GUI/API administration; private domain profiles and delivery services."""
import hashlib,json,secrets
from datetime import datetime,timedelta
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Request,Response,UploadFile,File,Form
from fastapi.responses import Response as RawResponse
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import OperatorUser,OperatorSession,AccessProfile,Workspace,WorkspaceMember,SystemEvent,Delivery,ReportSchedule
from .. import administration as admin,security,team,certificates,installation_archive,notifications
from ..permissions import PERMISSIONS,BUILTINS
from .auth import Credentials,PasswordChange,rate_limit
router=APIRouter(prefix='/api/administration',tags=['installation administration'])

class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Password(Strict):password:str=Field(min_length=14,max_length=256)
class Profile(Strict):
    name:str=Field(min_length=1,max_length=80)
    permissions:list[str]=Field(max_length=30)
    @field_validator('permissions')
    @classmethod
    def valid_permissions(cls,v):
        if set(v)-set(PERMISSIONS):raise ValueError('Unknown permission.')
        if any(x.startswith('reports.') for x in v) and 'reports.read' not in v:raise ValueError('Report permissions require reports.read.')
        if any(x.startswith('reviews.') for x in v) and not {'reviews.read','reports.read'}<=set(v):raise ValueError('Review permissions require reviews.read and reports.read.')
        return sorted(set(v))
class Domain(Strict):
    name:str=Field(min_length=1,max_length=160)
    description:str=Field(default='',max_length=1000)
    firmware_branch:str=Field(default='',pattern=r'^(?:\d{1,2}\.\d{1,2})?$')
    state:Literal['active','read_only','archived']='active'
class Destination(Strict):
    host:str=Field(default='',max_length=253,pattern=r'^[A-Za-z0-9.:-]*$')
    port:int=Field(default=6514,ge=1,le=65535)
class Syslog(Destination):
    enabled:bool=False
    transport:Literal['udp','tcp','tls']='tls'
    retention_days:int=Field(default=30,ge=1,le=365)
    @model_validator(mode='after')
    def host_required(self):
        if self.enabled and not self.host:raise ValueError('A destination host is required.')
        return self

def emails(v):
    import re
    if len(v)>20 or any(not re.fullmatch(r'[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}',e) or len(e)>254 for e in v):raise ValueError('Provide at most 20 valid email addresses.')
    return sorted(set(v))
class Mail(Destination):
    port:int=Field(default=587,ge=1,le=65535)
    enabled:bool=False
    security:Literal['starttls','tls','plain']='starttls'
    sender:str=Field(default='',max_length=254)
    username:str=Field(default='',max_length=254)
    password:str=Field(default='',max_length=1024)
    clear_password:bool=False
    events:list[Literal['job.failed','review.completed']]=Field(default_factory=lambda:['job.failed','review.completed'])
    workspace_recipients:dict[str,list[str]]=Field(default_factory=dict,max_length=200)
    @model_validator(mode='after')
    def validate(self):
        if self.enabled and (not self.host or not self.sender):raise ValueError('Host and sender are required to enable delivery.')
        if self.sender:emails([self.sender])
        if self.security=='plain' and self.host not in ('localhost','127.0.0.1','::1','mailpit'):raise ValueError('Plain SMTP is restricted to the local test mail sink. Use verified TLS for delivery.')
        for v in self.workspace_recipients.values():emails(v)
        return self
class Schedule(Strict):
    workspace_id:str=Field(max_length=64)
    name:str=Field(min_length=1,max_length=120)
    recipients:list[str]=Field(min_length=1,max_length=20)
    interval_hours:int=Field(default=24,ge=1,le=8760)
    enabled:bool=True
    @field_validator('recipients')
    @classmethod
    def valid(cls,v):return emails(v)
class TestMail(Strict):
    recipient:str
    @field_validator('recipient')
    @classmethod
    def valid(cls,v):return emails([v])[0]

def private(request,db):
    if security.settings.public:raise HTTPException(404,'Domain and delivery administration is private-edition only.')
    return admin.authorize(request,db)
def event(db,action,user,target=''):
    admin.record_event(db,action,actor=user.username,target_id=target);db.commit()

@router.get('/status')
def status(request:Request,db:Session=Depends(get_db)):
    if security.settings.public:
        _,u=admin.operator_session(request,db,allow_change=True,required=False)
        return {'edition':'public','authenticated':bool(u),'provisioned':bool(db.query(OperatorUser).count()),'must_change_password':bool(u and u.must_change_password),'username':u.username if u else None}
    try:u=team.admin(request,db)
    except HTTPException:return {'edition':'private','authenticated':False,'provisioned':True}
    return {'edition':'private','authenticated':True,'must_change_password':False,'username':u.username}

@router.post('/login')
def login(data:Credentials,request:Request,response:Response,db:Session=Depends(get_db)):
    if not security.settings.public:raise HTTPException(404,'Use the private web login.')
    rate_limit(request,data.username)
    u=db.query(OperatorUser).filter_by(username=data.username.lower()).first()
    if not team.verify_password(data.password,u.password_hash if u else team.DUMMY_HASH) or not u:
        admin.record_event(db,'operator.login_failed',severity='warning');db.commit();raise HTTPException(401,'Invalid username or password.')
    token=secrets.token_urlsafe(32)
    db.query(OperatorSession).filter(OperatorSession.expires_at<=datetime.utcnow()).delete()
    previous=db.query(OperatorSession).filter_by(user_id=u.id).order_by(OperatorSession.expires_at).all()
    for s in previous[:-4]:db.delete(s)
    db.add(OperatorSession(id=hashlib.sha256(token.encode()).hexdigest(),user_id=u.id,expires_at=datetime.utcnow()+timedelta(hours=1)))
    event(db,'operator.login',u)
    response.set_cookie(admin.COOKIE,token,max_age=3600,httponly=True,secure=True,samesite='strict',path='/')
    return {'authenticated':True}

@router.post('/logout')
def logout(request:Request,response:Response,db:Session=Depends(get_db)):
    s,u=admin.operator_session(request,db,allow_change=True)
    db.delete(s);event(db,'operator.logout',u);response.delete_cookie(admin.COOKIE,path='/');return {'authenticated':False}

@router.post('/password')
def password(data:PasswordChange,request:Request,db:Session=Depends(get_db)):
    s,u=admin.operator_session(request,db,allow_change=True);rate_limit(request,u.username)
    if not team.verify_password(data.current_password or '',u.password_hash):raise HTTPException(401,'Current password is incorrect.')
    if team.verify_password(data.new_password,u.password_hash):raise HTTPException(422,'Choose a different password.')
    u.password_hash=team.hash_password(data.new_password);u.must_change_password=False
    db.query(OperatorSession).filter(OperatorSession.user_id==u.id,OperatorSession.id!=s.id).delete();event(db,'operator.password_changed',u)
    return {'changed':True}

@router.get('/overview')
def overview(request:Request,db:Session=Depends(get_db)):
    admin.authorize(request,db)
    from ..build_info import VERSION,BUILD_NUMBER
    return {'edition':security.settings.edition,'version':VERSION,'build':BUILD_NUMBER,'certificates':certificates.inventory(),
      'certificate_activation_configured':bool(__import__('os').getenv('CADDY_ADMIN_URL') and __import__('os').getenv('CADDY_CONFIG_TEMPLATE')),
      'backup_scope':'installation settings, operator accounts and certificates; no visitor content' if security.settings.public else 'installation settings, accounts, domains, reports, reviews, source PDFs and certificates',
      'backup_max_mib':256,'pending_deliveries':db.query(Delivery).filter_by(status='pending').count(),
      'failed_deliveries':db.query(Delivery).filter_by(status='failed').count()}

@router.get('/profiles')
def profiles(request:Request,db:Session=Depends(get_db)):
    private(request,db)
    return {'permissions':PERMISSIONS,'profiles':[{'id':k,'name':k.title(),'permissions':v,'builtin':True} for k,v in BUILTINS.items()]+[{'id':p.id,'name':p.name,'permissions':json.loads(p.permissions_json),'builtin':False} for p in db.query(AccessProfile).all()]}
@router.post('/profiles')
def create_profile(data:Profile,request:Request,db:Session=Depends(get_db)):
    u=private(request,db)
    if db.query(AccessProfile).count()>=100:raise HTTPException(409,'Access profile limit reached.')
    if db.query(AccessProfile).filter_by(name=data.name.strip()).first():raise HTTPException(409,'Profile name already exists.')
    p=AccessProfile(id=secrets.token_hex(8),name=data.name.strip(),permissions_json=json.dumps(data.permissions));db.add(p);event(db,'profile.created',u,p.id);return {'id':p.id}
@router.put('/profiles/{identity}')
def edit_profile(identity:str,data:Profile,request:Request,db:Session=Depends(get_db)):
    u=private(request,db);p=db.get(AccessProfile,identity)
    if not p:raise HTTPException(404,'Custom profile not found; built-ins cannot be changed.')
    if db.query(AccessProfile).filter(AccessProfile.name==data.name.strip(),AccessProfile.id!=identity).first():raise HTTPException(409,'Profile name already exists.')
    p.name=data.name.strip();p.permissions_json=json.dumps(data.permissions);event(db,'profile.updated',u,identity);return {'id':identity}
@router.delete('/profiles/{identity}')
def delete_profile(identity:str,request:Request,db:Session=Depends(get_db)):
    u=private(request,db);p=db.get(AccessProfile,identity)
    if not p:raise HTTPException(404,'Custom profile not found.')
    if db.query(WorkspaceMember).filter_by(role=identity).count():raise HTTPException(409,'Reassign members before deleting this profile.')
    db.delete(p);event(db,'profile.deleted',u,identity);return {'deleted':True}

@router.get('/domains')
def domains(request:Request,db:Session=Depends(get_db)):
    private(request,db)
    return [{'id':w.id,'name':w.name,'description':w.description,'firmware_branch':w.firmware_branch,'state':w.state,'members':db.query(WorkspaceMember).filter_by(workspace_id=w.id).count()} for w in db.query(Workspace).order_by(Workspace.name).all()]
@router.put('/domains/{identity}')
def edit_domain(identity:str,data:Domain,request:Request,db:Session=Depends(get_db)):
    u=private(request,db);w=db.get(Workspace,identity)
    if not w:raise HTTPException(404,'Domain not found.')
    if data.state!='active':
        from ..models import ScrapeJob
        if db.query(ScrapeJob).filter(ScrapeJob.owner_id==identity,ScrapeJob.status.in_(['pending','running','uploading'])).count():raise HTTPException(409,'Finish or cancel active jobs before making a domain read-only.')
    for k,v in data.model_dump().items():setattr(w,k,v)
    event(db,'domain.updated',u,identity);return data.model_dump()

@router.post('/backup')
def backup(data:Password,request:Request,db:Session=Depends(get_db)):
    u=admin.authorize(request,db)
    try:raw=installation_archive.pack(db,data.password)
    except ValueError as e:raise HTTPException(422,str(e)) from None
    event(db,'installation.backup_created',u)
    return RawResponse(raw,media_type='application/octet-stream',headers={'Content-Disposition':'attachment; filename="upgrade-review-'+security.settings.edition+'.fgtbackup"','Cache-Control':'no-store'})
async def read_archive(file):
    chunks=[];total=0
    while chunk:=await file.read(1024**2):
        total+=len(chunk)
        if total>installation_archive.MAX_BYTES:raise HTTPException(413,'Archive exceeds 256 MiB.')
        chunks.append(chunk)
    return b''.join(chunks)
@router.post('/restore/preview')
async def restore_preview(request:Request,file:UploadFile=File(...),password:str=Form(...),db:Session=Depends(get_db)):
    admin.authorize(request,db);raw=await read_archive(file)
    from starlette.concurrency import run_in_threadpool
    try:return await run_in_threadpool(installation_archive.preview,raw,password)
    except Exception as e:
        if isinstance(e,HTTPException):raise
        raise HTTPException(422,'Backup could not be validated. Check password, archive integrity, edition and schema.') from None
@router.post('/restore/apply')
async def restore_apply(request:Request,file:UploadFile=File(...),password:str=Form(...),current_password:str=Form(...),sha256:str=Form(...),confirmation:str=Form(...),db:Session=Depends(get_db)):
    admin.verify_current(request,db,current_password)
    if confirmation!='RESTORE':raise HTTPException(422,'Type RESTORE to confirm replacement.')
    raw=await read_archive(file)
    if hashlib.sha256(raw).hexdigest()!=sha256:raise HTTPException(409,'Backup changed. Preview it again.')
    from starlette.concurrency import run_in_threadpool
    try:return await run_in_threadpool(installation_archive.restore,db,raw,password)
    except HTTPException:raise
    except Exception:raise HTTPException(422,'Restore failed validation or could not be committed; inspect installation logs before retrying.') from None

@router.get('/certificates')
def certs(request:Request,db:Session=Depends(get_db)):
    admin.authorize(request,db);return certificates.inventory()
@router.post('/certificates')
async def upload_cert(request:Request,certificate:UploadFile=File(...),private_key:UploadFile=File(...),key_password:str=Form(''),db:Session=Depends(get_db)):
    u=admin.authorize(request,db)
    chain=await certificate.read(256*1024+1);key=await private_key.read(64*1024+1)
    try:result=certificates.upload(chain,key,key_password)
    except Exception:raise HTTPException(422,'Invalid PEM certificate/key: verify key matching, chain signatures, dates, server usage and hostname SAN.') from None
    event(db,'certificate.uploaded',u,result['id']);return result
@router.get('/certificates/{identity}/download')
def download_cert(identity:str,request:Request,db:Session=Depends(get_db)):
    admin.authorize(request,db);p=certificates.get_path(identity)
    return RawResponse((p/'chain.pem').read_bytes(),media_type='application/x-pem-file',headers={'Content-Disposition':'attachment; filename="certificate-chain.pem"'})
@router.post('/certificates/{identity}/activate')
def activate_cert(identity:str,request:Request,db:Session=Depends(get_db)):
    u=admin.authorize(request,db);result=certificates.activate(identity);event(db,'certificate.activated',u,identity);return result
@router.delete('/certificates/{identity}')
def delete_cert(identity:str,request:Request,db:Session=Depends(get_db)):
    u=admin.authorize(request,db);p=certificates.get_path(identity)
    if any(c['id']==identity and c['active'] for c in certificates.inventory()):raise HTTPException(409,'Activate a replacement before deleting this certificate.')
    __import__('shutil').rmtree(p);event(db,'certificate.deleted',u,identity);return {'deleted':True}

@router.get('/logs')
def logs(request:Request,before:int|None=None,action:str='',severity:str='',db:Session=Depends(get_db)):
    admin.authorize(request,db);q=db.query(SystemEvent)
    if before:q=q.filter(SystemEvent.id<before)
    if action:q=q.filter(SystemEvent.action.contains(action[:80],autoescape=True))
    if severity:q=q.filter(SystemEvent.severity==severity)
    return [{c.name:getattr(e,c.name) for c in SystemEvent.__table__.columns} for e in q.order_by(SystemEvent.id.desc()).limit(100)]
@router.get('/syslog')
def read_syslog(request:Request,db:Session=Depends(get_db)):
    private(request,db);return admin.get_value(db,'syslog',Syslog().model_dump())
@router.put('/syslog')
def write_syslog(data:Syslog,request:Request,db:Session=Depends(get_db)):
    u=private(request,db);admin.set_value(db,'syslog',data.model_dump());event(db,'syslog.settings_updated',u);return data.model_dump()
@router.post('/syslog/test')
def test_syslog(request:Request,db:Session=Depends(get_db)):
    u=private(request,db)
    if not admin.get_value(db,'syslog',{}).get('enabled'):raise HTTPException(409,'Save and enable syslog first.')
    event(db,'syslog.test',u);return {'queued':True,'message':'Check local logs for forwarding outcome.'}

def mail_view(db):
    data=admin.get_value(db,'mail',Mail().model_dump());data=dict(data);data['password_set']=bool(data.pop('password_encrypted',''));data.pop('password',None);data.pop('clear_password',None);return data
@router.get('/mail')
def read_mail(request:Request,db:Session=Depends(get_db)):
    private(request,db);return mail_view(db)
@router.put('/mail')
def write_mail(data:Mail,request:Request,db:Session=Depends(get_db)):
    u=private(request,db)
    if any(not db.get(Workspace,k) for k in data.workspace_recipients):raise HTTPException(422,'Recipient mapping references an unknown domain.')
    value=data.model_dump(exclude={'password','clear_password'});old=admin.get_value(db,'mail',{})
    value['password_encrypted']='' if data.clear_password else admin.secret(data.password) if data.password else old.get('password_encrypted','')
    admin.set_value(db,'mail',value);event(db,'email.settings_updated',u);return mail_view(db)
@router.post('/mail/test')
def test_mail(data:TestMail,request:Request,db:Session=Depends(get_db)):
    u=private(request,db)
    if not admin.get_value(db,'mail',{}).get('enabled'):raise HTTPException(409,'Save and enable SMTP settings first.')
    notifications.queue_mail(db,None,'Upgrade Review email delivery test','This is an operator-requested test message. No report content is included.',[data.recipient]);event(db,'email.test_queued',u);return {'queued':True}
@router.get('/deliveries')
def deliveries(request:Request,db:Session=Depends(get_db)):
    private(request,db)
    return [{c:getattr(d,c) for c in ('id','created_at','workspace_id','subject','status','error','attempts')} for d in db.query(Delivery).order_by(Delivery.created_at.desc()).limit(100)]
@router.post('/deliveries/{identity}/retry')
def retry_delivery(identity:str,request:Request,db:Session=Depends(get_db)):
    u=private(request,db);d=db.get(Delivery,identity)
    if not d or d.status!='failed':raise HTTPException(409,'Only failed deliveries can be retried.')
    d.status='pending';d.attempts=0;d.next_attempt=datetime.utcnow();event(db,'email.retry_queued',u,identity);return {'queued':True}
@router.get('/schedules')
def schedules(request:Request,db:Session=Depends(get_db)):
    private(request,db)
    return [{'id':s.id,'workspace_id':s.workspace_id,'name':s.name,'recipients':json.loads(s.recipients_json),'interval_hours':s.interval_hours,'enabled':s.enabled,'next_run':s.next_run} for s in db.query(ReportSchedule).all()]
@router.post('/schedules')
def create_schedule(data:Schedule,request:Request,db:Session=Depends(get_db)):
    u=private(request,db)
    if not db.get(Workspace,data.workspace_id):raise HTTPException(404,'Domain not found.')
    if db.query(ReportSchedule).count()>=100:raise HTTPException(409,'Schedule limit reached.')
    s=ReportSchedule(**data.model_dump(exclude={'recipients'}),recipients_json=json.dumps(data.recipients),next_run=datetime.utcnow()+timedelta(hours=data.interval_hours));db.add(s);db.flush();event(db,'schedule.created',u,s.id);return {'id':s.id}
@router.put('/schedules/{identity}')
def update_schedule(identity:str,data:Schedule,request:Request,db:Session=Depends(get_db)):
    u=private(request,db);s=db.get(ReportSchedule,identity)
    if not s or not db.get(Workspace,data.workspace_id):raise HTTPException(404,'Schedule or domain not found.')
    for k,v in data.model_dump(exclude={'recipients'}).items():setattr(s,k,v)
    s.recipients_json=json.dumps(data.recipients);s.next_run=datetime.utcnow()+timedelta(hours=data.interval_hours);event(db,'schedule.updated',u,identity);return {'id':identity}
@router.delete('/schedules/{identity}')
def remove_schedule(identity:str,request:Request,db:Session=Depends(get_db)):
    u=private(request,db);s=db.get(ReportSchedule,identity)
    if not s:raise HTTPException(404,'Schedule not found.')
    db.delete(s);event(db,'schedule.deleted',u,identity);return {'deleted':True}
