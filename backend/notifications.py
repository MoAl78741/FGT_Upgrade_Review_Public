"""Private notification outbox and bounded local/syslog delivery. No parser network access."""
import json,logging,smtplib,socket,ssl,threading,time
from datetime import datetime,timedelta,timezone
from email.message import EmailMessage
from .database import SessionLocal
from .models import SystemEvent,Delivery,ReportSchedule,ScrapeJob,Review,Workspace
from .administration import get_value,reveal,record_event
from . import security,queue
STOP=threading.Event();THREAD=None;LOCK=threading.RLock()
LOGGER=logging.getLogger('fgt.events')

def queue_mail(db,workspace_id,subject,body,recipients,schedule_id=None):
    if db.query(Delivery).filter(Delivery.status.in_(['pending','sending'])).count()>=500:
        record_event(db,'email.queue_full',workspace_id=workspace_id,severity='warning');return
    db.add(Delivery(workspace_id=workspace_id,subject=subject[:160],body=body[:24000],recipients_json=json.dumps(recipients),schedule_id=schedule_id))

def notify(db,event,workspace_id,target_id):
    if security.settings.public:return
    config=get_value(db,'mail',{})
    recipients=config.get('workspace_recipients',{}).get(workspace_id,[])
    if not config.get('enabled') or event not in config.get('events',[]) or not recipients:return
    # Event messages carry identifiers and same-origin authenticated links, never configs or source text.
    path='/reports/' if event=='job.failed' else '/reviews/'
    queue_mail(db,workspace_id,'Upgrade Review: '+event,
      f'{event}\nDomain: {workspace_id}\nReference: {target_id}\n{security.settings.origin}{path}{target_id}\nSign in with authorized domain access to view details.',recipients)

def smtp_send(config,delivery):
    mode=config.get('security','starttls');host=config['host'];port=config['port']
    context=ssl.create_default_context()
    client=smtplib.SMTP_SSL(host,port,timeout=10,context=context) if mode=='tls' else smtplib.SMTP(host,port,timeout=10)
    with client:
        client.ehlo()
        if mode=='starttls':client.starttls(context=context);client.ehlo()
        if config.get('username'):client.login(config['username'],reveal(config.get('password_encrypted','')))
        msg=EmailMessage();msg['From']=config['sender'];msg['To']=', '.join(json.loads(delivery.recipients_json));msg['Subject']=delivery.subject
        msg.set_content(delivery.body)
        refused=client.send_message(msg)
        if refused:raise RuntimeError('One or more recipients were refused.')

def syslog_send(config,event):
    host=config['host'];port=config['port'];mode=config.get('transport','tls')
    priority=16*8+({'error':3,'warning':4}.get(event.severity,6))
    stamp=event.created_at.replace(tzinfo=timezone.utc).isoformat()
    # JSON encoding prevents CR/LF injection into RFC5424 structured message content.
    message=f'<{priority}>1 {stamp} fgt-upgrade fgt - audit - '+json.dumps({'id':event.id,'action':event.action,'actor':event.actor,'domain':event.workspace_id,'target':event.target_id},ensure_ascii=True)
    payload=message.encode()
    if mode=='udp':
        info=socket.getaddrinfo(host,port,type=socket.SOCK_DGRAM)[0]
        with socket.socket(info[0],socket.SOCK_DGRAM) as s:s.settimeout(5);s.sendto(payload,info[4])
    else:
        with socket.create_connection((host,port),timeout=5) as raw:
            if mode=='tls':
                with ssl.create_default_context().wrap_socket(raw,server_hostname=host) as s:s.sendall(str(len(payload)).encode()+b' '+payload)
            else:raw.sendall(str(len(payload)).encode()+b' '+payload)

def tick():
    if security.settings.public:return
    with SessionLocal() as db:
        log=get_value(db,'syslog',{})
        events=db.query(SystemEvent).filter(SystemEvent.forwarded.is_(False)).order_by(SystemEvent.id).limit(3).all()
        for event in events:
            LOGGER.info(json.dumps({'event':event.action,'severity':event.severity,'domain':event.workspace_id,'actor':event.actor,'target':event.target_id}))
            if log.get('enabled'):
                try:syslog_send(log,event);event.forward_error=None
                except Exception:event.forward_error='Syslog delivery failed; check transport, destination and receiver trust.'
            event.forwarded=True # bounded best-effort syslog; local event remains even on failure
        days=log.get('retention_days',30)
        db.query(SystemEvent).filter(SystemEvent.created_at<datetime.utcnow()-timedelta(days=days)).delete(synchronize_session=False)
        # Bound local storage independently of retention.
        cutoff=db.query(SystemEvent.id).order_by(SystemEvent.id.desc()).offset(9999).scalar()
        if cutoff:db.query(SystemEvent).filter(SystemEvent.id<cutoff).delete(synchronize_session=False)
        mail=get_value(db,'mail',{})
        now=datetime.utcnow()
        if mail.get('enabled'):
            for schedule in db.query(ReportSchedule).filter(ReportSchedule.enabled.is_(True),ReportSchedule.next_run<=now).all():
                space=db.get(Workspace,schedule.workspace_id)
                if space and space.state=='active':
                    jobs=db.query(ScrapeJob).filter_by(owner_id=space.id).all()
                    reviews=db.query(Review).filter_by(owner_id=space.id).all()
                    body=f'Domain summary: {space.name}\nReports: {len(jobs)}\nFailed/incomplete reports: {sum(j.status in ("failed","partial") for j in jobs)}\nUpgrade reviews: {len(reviews)}\n'
                    body+='\n'.join(f'{r.title}: {security.settings.origin}/reviews/{r.id}' for r in reviews[:50])
                    queue_mail(db,space.id,'Scheduled review summary: '+schedule.name,body,json.loads(schedule.recipients_json),schedule.id)
                schedule.next_run=now+timedelta(hours=schedule.interval_hours)
        db.commit()
        if not mail.get('enabled'):return
        deliveries=db.query(Delivery).filter(Delivery.status=='pending',Delivery.next_attempt<=now).order_by(Delivery.created_at).limit(1).all()
        for delivery in deliveries:
            delivery.status='sending';delivery.attempts+=1;db.commit()
            try:smtp_send(mail,delivery);delivery.status='sent';delivery.error=None
            except Exception:
                delivery.error='SMTP delivery failed. Check destination, TLS trust, credentials and recipients.'
                delivery.status='failed' if delivery.attempts>=3 else 'pending'
                delivery.next_attempt=now+timedelta(minutes=5*delivery.attempts)
            db.commit()
        db.query(Delivery).filter(Delivery.created_at<now-timedelta(days=30),Delivery.status!='pending').delete(synchronize_session=False);db.commit()

def start():
    global THREAD
    if security.settings.public:return
    STOP.clear()
    with SessionLocal() as db:
        # An interrupted send may have reached the recipient; do not silently duplicate it.
        db.query(Delivery).filter_by(status='sending').update({'status':'failed','error':'Delivery interrupted; recipient receipt is unknown. Review before retrying.'});db.commit()
    def run():
        while not STOP.wait(10):
            try:
                with LOCK:tick()
            except Exception:LOGGER.error('Administration delivery worker failed; will check again.')
    THREAD=threading.Thread(target=run,daemon=True,name='administration-delivery');THREAD.start()

def stop():
    STOP.set()
    if THREAD:THREAD.join(timeout=15)
