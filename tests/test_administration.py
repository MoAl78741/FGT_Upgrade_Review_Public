"""Administration boundaries use synthetic certificates, domains and local receivers."""
import hashlib,json,io,zipfile,socket,threading
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from backend import administration as admin,certificates,installation_archive,notifications,security,team
from backend.models import OperatorUser,AccessProfile,WorkspaceMember,Workspace,SystemEvent,InstallationSetting,Delivery,ReportSchedule,Review
from test_team import named,login,PASSWORD,PASSWORD_HASH
from test_security import hosted

@pytest.fixture(autouse=True)
def isolated_admin_files(monkeypatch,tmp_path):monkeypatch.setenv('ADMIN_STATE_DIR',str(tmp_path/'admin'))

def test_operator_is_separate_from_public_session_and_private_accounts(hosted):
    a,b,sessions,_=hosted
    a.get('/api/capabilities');b.get('/api/capabilities')
    assert a.get('/api/administration/overview').status_code==401
    with sessions() as db:db.add(OperatorUser(id='operator',username='admin',password_hash=PASSWORD_HASH,must_change_password=True));db.commit()
    response=a.post('/api/administration/login',json={'username':'admin','password':PASSWORD})
    assert response.status_code==200
    assert all(s in response.headers['set-cookie'].lower() for s in ['secure','httponly','samesite=strict'])
    assert a.get('/api/administration/overview').status_code==403
    assert a.post('/api/administration/password',json={'current_password':PASSWORD,'new_password':PASSWORD+'-new'}).status_code==200
    assert a.get('/api/administration/overview').status_code==200
    assert b.get('/api/administration/overview').status_code==401
    assert a.get('/api/administration/mail').status_code==404
    assert a.post('/api/administration/backup',headers={'Origin':'https://evil.example'},json={'password':PASSWORD}).status_code==403
    assert a.get('/api/auth/status').json()['enabled'] is False


def test_custom_profile_checks_every_operation_and_changes_apply_immediately(named):
    c,db=named;login(c,'admin')
    result=c.post('/api/administration/profiles',json={'name':'Import without deletion','permissions':['reports.read','reports.import']})
    assert result.status_code==200,result.text
    identity=result.json()['id']
    assert c.put('/api/auth/memberships',json={'workspace_id':'one','user_id':'reviewer','role':identity}).status_code==200
    login(c,'reviewer')
    assert c.get('/api/jobs/one-job').status_code==200
    assert c.delete('/api/jobs/one-job').status_code==403
    assert c.post('/api/jobs/one-job/export',json={}).status_code==403
    assert c.get('/api/reviews').status_code==403
    assert c.get('/api/administration/overview').status_code==403
    assert c.get('/api/jobs/two-job').status_code==404
    profile=db.get(AccessProfile,identity);profile.permissions_json='[]';db.commit()
    assert c.get('/api/jobs/one-job').status_code==403


def test_profiles_cannot_escalate_or_be_deleted_while_assigned(named):
    c,db=named;login(c,'admin')
    assert c.post('/api/administration/profiles',json={'name':'Bad','permissions':['system.admin']}).status_code==422
    assert c.put('/api/auth/memberships',json={'workspace_id':'one','user_id':'reviewer','role':'admin'}).status_code==422
    p=AccessProfile(id='custom',name='Custom',permissions_json='["reports.read"]');db.add(p);db.get(WorkspaceMember,('one','reviewer')).role='custom';db.commit()
    assert c.delete('/api/administration/profiles/custom').status_code==409
    assert c.delete('/api/administration/profiles/viewer').status_code==404


def test_readonly_domain_denies_writes_but_preserves_reads(named):
    c,db=named;login(c,'admin')
    assert c.put('/api/administration/domains/one',json={'name':'Domain One','state':'read_only','description':'Test','firmware_branch':'7.6'}).status_code==200
    login(c,'reviewer')
    assert c.get('/api/jobs/one-job').status_code==200
    assert c.post('/api/jobs/one-job/retry').status_code==403
    assert c.delete('/api/jobs/one-job').status_code==403


def test_private_backup_encryption_preview_restore_and_wrong_password(named):
    c,db=named;login(c,'admin')
    result=c.post('/api/administration/backup',json={'password':PASSWORD})
    assert result.status_code==200,result.text
    raw=result.content;assert raw.startswith(installation_archive.MAGIC) and b'Customer One' not in raw
    preview=c.post('/api/administration/restore/preview',files={'file':('backup.fgtbackup',raw)},data={'password':PASSWORD})
    assert preview.status_code==200,preview.text
    assert preview.json()['records']['scrape_jobs']==2
    assert c.post('/api/administration/restore/preview',files={'file':('backup.fgtbackup',raw)},data={'password':PASSWORD+'wrong'}).status_code==422
    db.get(Workspace,'one').name='Changed';db.commit()
    restored=c.post('/api/administration/restore/apply',files={'file':('backup.fgtbackup',raw)},data={'password':PASSWORD,'current_password':PASSWORD,'sha256':hashlib.sha256(raw).hexdigest(),'confirmation':'RESTORE'})
    assert restored.status_code==200,restored.text
    db.expire_all();assert db.get(Workspace,'one').name=='Customer One'
    assert c.get('/api/jobs').status_code==401


def test_public_backup_excludes_visitors_and_restore_preserves_them(hosted):
    a,b,sessions,_=hosted;a.get('/api/capabilities')
    from backend.models import ScrapeJob
    with sessions() as db:
        db.add(OperatorUser(id='operator',username='admin',password_hash=PASSWORD_HASH,must_change_password=False))
        db.add(ScrapeJob(id='visitor',owner_id='visitor-session',from_version='7.6.5',to_version='7.6.6',status='completed',all_data_json='{"secret":"visitor source"}'));db.commit()
    assert a.post('/api/administration/login',json={'username':'admin','password':PASSWORD}).status_code==200
    result=a.post('/api/administration/backup',json={'password':PASSWORD});assert result.status_code==200,result.text
    data,entries=installation_archive.unpack(result.content,PASSWORD)
    assert set(data['tables'])=={'installation_settings','operator_users'}
    assert not any(k.startswith('uploads/') for k in entries)
    assert 'visitor source' not in json.dumps(data)
    with sessions() as db:
        installation_archive.restore(db,result.content,PASSWORD)
        assert db.get(ScrapeJob,'visitor').all_data_json=='{"secret":"visitor source"}'


def make_certificate(host='testserver',expired=False):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,host)])
    now=datetime.now(timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
      .not_valid_before(now-timedelta(days=10)).not_valid_after(now+timedelta(days=-1 if expired else 30))
      .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]),critical=False).sign(key,hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM),key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())

def test_certificate_validation_and_private_key_never_returned(named):
    c,_=named;login(c,'admin');chain,key=make_certificate()
    result=c.post('/api/administration/certificates',files={'certificate':('chain.pem',chain),'private_key':('key.pem',key)})
    assert result.status_code==200,result.text
    identity=result.json()['id']
    assert 'PRIVATE KEY' not in result.text
    assert c.get('/api/administration/certificates/'+identity+'/download').content==chain
    assert c.post('/api/administration/certificates/'+identity+'/activate').status_code==409
    _,wrong=make_certificate()
    assert c.post('/api/administration/certificates',files={'certificate':('chain.pem',chain),'private_key':('key.pem',wrong)}).status_code==422
    chain,key=make_certificate('wrong.example')
    assert c.post('/api/administration/certificates',files={'certificate':('chain.pem',chain),'private_key':('key.pem',key)}).status_code==422
    chain,key=make_certificate(expired=True)
    assert c.post('/api/administration/certificates',files={'certificate':('chain.pem',chain),'private_key':('key.pem',key)}).status_code==422


def test_mail_secret_redaction_and_schedule_domain_validation(named):
    c,db=named;login(c,'admin')
    config={'enabled':False,'host':'smtp.example.com','sender':'sender@example.com','password':'synthetic-mail-secret','workspace_recipients':{'one':['recipient@example.com']}}
    result=c.put('/api/administration/mail',json=config);assert result.status_code==200,result.text
    assert result.json()['password_set'] is True and 'synthetic-mail-secret' not in result.text
    row=db.get(InstallationSetting,'mail');assert 'synthetic-mail-secret' not in row.value_json
    assert admin.reveal(json.loads(row.value_json)['password_encrypted'])=='synthetic-mail-secret'
    assert c.put('/api/administration/mail',json={**config,'security':'plain'}).status_code==422
    assert c.post('/api/administration/schedules',json={'workspace_id':'missing','name':'Daily','recipients':['recipient@example.com']}).status_code==404
    assert c.post('/api/administration/schedules',json={'workspace_id':'one','name':'Daily','recipients':['x\r\nBcc: hidden@example.com']}).status_code==422


def test_review_completion_outbox_is_revision_guarded_and_reopening_edits(named):
    c,db=named;login(c,'admin')
    admin.set_value(db,'mail',{'enabled':True,'events':['review.completed'],'workspace_recipients':{'one':['recipient@example.com']}});db.commit()
    c.post('/api/auth/workspace',json={'workspace_id':'one'})
    review=c.post('/api/reviews',json={'title':'Example review'}).json();identity=review['id']
    response=c.post('/api/reviews/'+identity+'/completion',json={'revision':review['revision'],'completed':True})
    assert response.status_code==200,response.text
    assert response.json()['completed_at']
    assert db.query(Delivery).count()==1
    assert c.post('/api/reviews/'+identity+'/completion',json={'revision':review['revision'],'completed':True}).status_code==409
    assert db.query(Delivery).count()==1
    login(c,'viewer')
    assert c.post('/api/reviews/'+identity+'/completion',json={'revision':response.json()['revision'],'completed':False}).status_code==403


def test_udp_syslog_uses_local_receiver_without_line_injection():
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as receiver:
        receiver.bind(('127.0.0.1',0));receiver.settimeout(2)
        e=SystemEvent(id=1,created_at=datetime.utcnow(),action='test\ninjection',actor='operator',target_id='fixture',severity='info')
        notifications.syslog_send({'host':'127.0.0.1','port':receiver.getsockname()[1],'transport':'udp'},e)
        packet=receiver.recv(8192);assert packet.startswith(b'<134>1 ') and b'\n' not in packet and b'test\\ninjection' in packet

def test_file_database_restore_rolls_back_on_file_swap_failure(monkeypatch,tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from backend.models import Base,TeamUser
    from dataclasses import replace
    uploads=tmp_path/'uploads';uploads.mkdir()
    cfg=replace(security.settings,edition='private',uploads=uploads)
    monkeypatch.setattr(security,'settings',cfg)
    engine=create_engine('sqlite:///'+str(tmp_path/'installation.sqlite'))
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(TeamUser(id='admin',username='admin',password_hash=PASSWORD_HASH,is_admin=True,active=True))
        db.add(Workspace(id='domain',name='Original'));db.commit()
        original=installation_archive.pack(db,PASSWORD)
        db.get(Workspace,'domain').name='Keep on rollback';db.commit()
        real=installation_archive.os.replace;failed=False
        def fail_once(src,dst):
            nonlocal failed
            if Path(dst)==uploads and not failed:
                failed=True;raise OSError('Synthetic disk failure')
            return real(src,dst)
        monkeypatch.setattr(installation_archive.os,'replace',fail_once)
        with pytest.raises(OSError):installation_archive.restore(db,original,PASSWORD)
        db.expire_all();assert db.get(Workspace,'domain').name=='Keep on rollback'
        assert uploads.exists()
        assert not list(tmp_path.glob('*.restore.json'))
    engine.dispose()


def test_restore_journal_recovers_interrupted_commit_boundary(tmp_path):
    from sqlalchemy import create_engine,text
    from sqlalchemy.orm import Session
    from backend import restore_journal
    import os
    database=tmp_path/'journal.sqlite';engine=create_engine('sqlite:///'+str(database))
    with engine.begin() as c:c.execute(text('create table fixture (value text)'));c.execute(text("insert into fixture values ('before')"))
    base=tmp_path/'files';base.mkdir();(base/'marker').write_text('before')
    stage=tmp_path/'stage';stage.mkdir();(stage/'marker').write_text('after');old=tmp_path/'old'
    with Session(engine) as db:
        token=restore_journal.begin(db,[(base,stage,old)])
        os.replace(base,old);os.replace(stage,base)
        db.execute(text("update fixture set value='after'"));db.commit()
        # Process dies after SQL commit but before committing its journal.
    restore_journal.recover(database)
    with engine.connect() as c:assert c.execute(text('select value from fixture')).scalar()=='before'
    assert (base/'marker').read_text()=='before' and not old.exists()
    engine.dispose()


def test_smtp_delivery_uses_local_mail_sink_only(monkeypatch):
    import socketserver
    captured=[]
    class Sink(socketserver.StreamRequestHandler):
        def handle(self):
            self.wfile.write(b'220 localhost test SMTP\r\n');data=False;body=[]
            while line:=self.rfile.readline():
                if data:
                    if line==b'.\r\n':captured.append(b''.join(body));data=False;self.wfile.write(b'250 accepted\r\n')
                    else:body.append(line)
                elif line.upper().startswith(b'EHLO'):self.wfile.write(b'250 localhost\r\n')
                elif line.upper().startswith(b'DATA'):data=True;self.wfile.write(b'354 send data\r\n')
                elif line.upper().startswith(b'QUIT'):self.wfile.write(b'221 bye\r\n');break
                else:self.wfile.write(b'250 ok\r\n')
    with socketserver.TCPServer(('127.0.0.1',0),Sink) as server:
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            delivery=Delivery(subject='Synthetic test',body='No real recipients or source data.',recipients_json='["fixture@example.com"]')
            notifications.smtp_send({'host':'127.0.0.1','port':server.server_address[1],'security':'plain','sender':'sender@example.com'},delivery)
            assert len(captured)==1 and b'Synthetic test' in captured[0]
        finally:server.shutdown();worker.join()


def test_schedule_tick_enqueues_summary_without_cross_domain_content(named,monkeypatch):
    c,db=named
    admin.set_value(db,'mail',{'enabled':True,'host':'localhost','sender':'sender@example.com'})
    db.add(Review(id='visible',owner_id='one',title='Allowed review'))
    db.add(Review(id='hidden',owner_id='two',title='Other customer secret'))
    db.add(ReportSchedule(id='schedule',workspace_id='one',name='Daily',recipients_json='["fixture@example.com"]',interval_hours=24,next_run=datetime.utcnow()-timedelta(minutes=1)))
    db.commit()
    from sqlalchemy.orm import sessionmaker
    monkeypatch.setattr(notifications,'SessionLocal',sessionmaker(bind=db.get_bind()))
    captured=[];monkeypatch.setattr(notifications,'smtp_send',lambda cfg,d:captured.append(d.body))
    notifications.tick()
    assert len(captured)==1 and 'Allowed review' in captured[0] and 'Other customer secret' not in captured[0]
    notifications.tick();assert len(captured)==1
