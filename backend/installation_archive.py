"""Encrypted, allowlisted installation archives; no uploaded SQLite is ever executed."""
import io,json,os,shutil,zipfile,hashlib,secrets,tempfile
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
from contextlib import contextmanager
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from sqlalchemy import text,DateTime
from fastapi import HTTPException
from . import models,security,queue
from .maintenance_gate import exclusive
from .administration import state_dir,record_event

MAX_BYTES=256*1024**2
MAGIC=b'FGTBACKUP1\n'
COMMON=[models.InstallationSetting,models.OperatorUser]
PRIVATE=[models.TeamUser,models.Workspace,models.WorkspaceMember,models.AccessProfile,models.ScrapeJob,models.Review,models.ReportSchedule]

def tables():return COMMON+([] if security.settings.public else PRIVATE)
def derive(password,salt):
    if not 14<=len(password)<=256:raise ValueError('Use a backup password of 14–256 characters.')
    return Scrypt(salt=salt,length=32,n=2**15,r=8,p=1).derive(password.encode())

def idle(db):
    if not security.settings.public and db.query(models.ScrapeJob).filter(models.ScrapeJob.status.in_(['uploading','pending','running'])).count():
        raise HTTPException(409,'Wait for queued jobs to finish or cancel them before backup/restore.')

def pack(db,password):
    # BEGIN IMMEDIATE excludes concurrent writers while the DB and file set are captured.
    from .notifications import LOCK as notification_lock
    with exclusive(), notification_lock, queue.LOCK:
        db.commit();db.execute(text('BEGIN IMMEDIATE'));idle(db)
        try:
            data={'format':1,'edition':security.settings.edition,'created_at':datetime.now(timezone.utc).isoformat(),'tables':{}}
            for model in tables():
                data['tables'][model.__tablename__]=[{c.name:(getattr(row,c.name).isoformat() if isinstance(getattr(row,c.name),datetime) else getattr(row,c.name)) for c in model.__table__.columns} for row in db.query(model).all()]
            entries={'state.json':json.dumps(data).encode()}
            for base,prefix in [(state_dir(),'administration')]+([] if security.settings.public else [(security.settings.uploads,'uploads')]):
                for p in base.rglob('*'):
                    if p.is_symlink():raise ValueError('Storage contains a symbolic link; inspect it before backup.')
                    if not p.is_file():continue
                    rel=p.relative_to(base).as_posix()
                    if prefix=='administration' and not (rel=='secret.key' or rel.startswith('certificates/')):continue
                    if prefix=='uploads' and not p.name.endswith('.pdf'):continue
                    if len(entries)>=20000 or sum(map(len,entries.values()))+p.stat().st_size>MAX_BYTES-1024**2:raise ValueError('GUI backup exceeds 256 MiB; use the offline backup tool for larger private installations.')
                    entries[prefix+'/'+rel]=p.read_bytes()
            manifest={n:hashlib.sha256(v).hexdigest() for n,v in entries.items()}
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('manifest.json',json.dumps(manifest))
                for n,v in entries.items():z.writestr(n,v)
            salt=secrets.token_bytes(16);nonce=secrets.token_bytes(12)
            return MAGIC+salt+nonce+AESGCM(derive(password,salt)).encrypt(nonce,out.getvalue(),MAGIC)
        finally:db.rollback()

def unpack(raw,password):
    if len(raw)>MAX_BYTES or not raw.startswith(MAGIC):raise ValueError('Not a supported encrypted installation backup (256 MiB maximum).')
    i=len(MAGIC);salt=raw[i:i+16];nonce=raw[i+16:i+28]
    try:plain=AESGCM(derive(password,salt)).decrypt(nonce,raw[i+28:],MAGIC)
    except (InvalidTag,ValueError):raise ValueError('Backup password is incorrect or the archive is damaged.') from None
    entries={}
    with zipfile.ZipFile(io.BytesIO(plain)) as z:
        infos=z.infolist()
        if len(infos)>20001 or sum(i.file_size for i in infos)>MAX_BYTES:raise ValueError('Archive expansion limit exceeded.')
        for info in infos:
            path=PurePosixPath(info.filename)
            if info.filename in entries or path.is_absolute() or '..' in path.parts or '\\' in info.filename or info.is_dir() or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Unsafe or duplicate archive entry.')
            if info.filename not in ('state.json','manifest.json','administration/secret.key','administration/certificates/active'):
                import re
                cert=bool(re.fullmatch(r'administration/certificates/[0-9a-f-]{36}/(?:chain|key)\.pem',info.filename))
                pdf=not security.settings.public and bool(re.fullmatch(r'uploads/[0-9a-f-]{36}/[A-Za-z0-9_.-]+\.pdf',info.filename))
                if not (cert or pdf):raise ValueError('Archive includes an unsupported file.')
            entries[info.filename]=z.read(info)
    manifest=json.loads(entries.pop('manifest.json'))
    if manifest!={n:hashlib.sha256(v).hexdigest() for n,v in entries.items()}:raise ValueError('Archive checksum mismatch.')
    data=json.loads(entries['state.json'])
    expected={m.__tablename__ for m in tables()}
    if data.get('format')!=1 or data.get('edition')!=security.settings.edition or set(data.get('tables',{}))!=expected:raise ValueError('Backup format or edition does not match this installation.')
    if sum(len(v) for v in data['tables'].values())>50000:raise ValueError('Archive has too many records.')
    for model in tables():
        columns={c.name for c in model.__table__.columns}
        for row in data['tables'][model.__tablename__]:
            if not isinstance(row,dict) or set(row)!=columns:raise ValueError('Backup schema does not match this version.')
            for c in model.__table__.columns:
                if isinstance(c.type,DateTime) and row[c.name] is not None:row[c.name]=datetime.fromisoformat(row[c.name])
    if not security.settings.public:
        if any(j['status'] in ('pending','running','uploading') for j in data['tables']['scrape_jobs']):raise ValueError('Backups containing active jobs cannot be restored.')
        if not any(u['active'] and u['is_admin'] for u in data['tables']['team_users']):raise ValueError('Backup must retain an active private administrator.')
    if security.settings.public and not data['tables']['operator_users']:raise ValueError('Backup must retain an operator account.')
    return data,entries

def preview(raw,password):
    data,entries=unpack(raw,password)
    return {'sha256':hashlib.sha256(raw).hexdigest(),'edition':data['edition'],'created_at':data['created_at'],
      'records':{n:len(v) for n,v in data['tables'].items()},'pdf_files':sum(n.startswith('uploads/') for n in entries),
      'certificates':sum(n.endswith('/chain.pem') for n in entries),'warning':'Replaces installation settings and backed-up private data. Restored account passwords apply. All administrator sessions end. Certificates must be explicitly activated after restore.'}

def restore(db,raw,password):
    data,entries=unpack(raw,password)
    # The filesystem remains recoverable until the SQL transaction commits. Old source files are
    # retained under generated names on rollback, never discarded before a successful commit.
    from .notifications import LOCK as notification_lock
    with exclusive(), notification_lock, queue.LOCK:
        db.commit();db.execute(text('BEGIN IMMEDIATE'));idle(db)
        swaps=[];journal=None
        from . import restore_journal
        try:
            for base,prefix in [(state_dir(),'administration')]+([] if security.settings.public else [(security.settings.uploads,'uploads')]):
                stage=Path(tempfile.mkdtemp(prefix='.restore-',dir=base.parent));os.chmod(stage,0o700)
                for name,value in entries.items():
                    if name.startswith(prefix+'/'):
                        dest=stage/name[len(prefix)+1:];dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                        dest.write_bytes(value);dest.chmod(0o600)
                # Proxy activation is an explicit post-restore operation.
                if prefix=='administration':
                    (stage/'certificates'/'active').unlink(missing_ok=True)
                    current=base/'certificates'/'active'
                    if current.exists():
                        identity=current.read_text()
                        from .certificates import get_path
                        active_path=get_path(identity)
                        target=stage/'certificates'/identity
                        if target.exists():shutil.rmtree(target)
                        shutil.copytree(active_path,target)
                        (stage/'certificates'/'active').write_text(identity)

                old=base.with_name(base.name+'.previous-'+secrets.token_hex(8))
                swaps.append((base,stage,old))
            journal=restore_journal.begin(db,swaps)
            for model in reversed(tables()):db.query(model).delete(synchronize_session=False)
            db.flush()
            for model in tables():
                if data['tables'][model.__tablename__]:db.execute(model.__table__.insert(),data['tables'][model.__tablename__])
            db.query(models.OperatorSession).delete()
            db.query(models.Delivery).filter(models.Delivery.status.in_(['pending','sending'])).update({'status':'failed','error':'Cancelled by installation restore.'},synchronize_session=False)
            if not security.settings.public:db.query(models.TeamSession).delete()
            for base,stage,old in swaps:
                if base.exists():os.replace(base,old)
                os.replace(stage,base)
            record_event(db,'installation.restored',actor='operator')
            db.commit()
            restore_journal.commit(journal)
        except BaseException:
            db.rollback()
            if journal:
                restore_journal.recover(journal[1]['database'])
            else:
                for base,stage,old in reversed(swaps):
                    if old.exists():
                        if base.exists():shutil.rmtree(base)
                        os.replace(old,base)
                    if stage.exists():shutil.rmtree(stage)
            raise
        for base,stage,old in swaps:
            if old.exists():shutil.rmtree(old)
        restore_journal.finish(journal)
    return {'restored':True,'sign_in_required':True,'certificate_activation_required':True}
