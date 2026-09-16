"""Crash recovery for GUI restore: roll back to the pre-restore DB/files unless committed."""
import json,os,sqlite3,shutil,secrets
from pathlib import Path

def write(path,value):
    temp=Path(str(path)+'.tmp')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump(value,f);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def begin(db,swaps):
    database=db.get_bind().url.database
    if not database or database==':memory:':return None
    database=Path(database).resolve();journal=Path(str(database)+'.restore.json')
    snapshot=Path(str(database)+'.restore-'+secrets.token_hex(8)+'.sqlite')
    fd=os.open(snapshot,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(snapshot) as target:source.backup(target)
    snapshot.chmod(0o600)
    value={'database':str(database),'snapshot':str(snapshot),'committed':False,'swaps':[[str(p) for p in row] for row in swaps]}
    write(journal,value);return journal,value

def commit(token):
    if token:
        path,value=token;value['committed']=True;write(path,value)

def finish(token):
    if token:
        path,value=token;Path(value['snapshot']).unlink(missing_ok=True);path.unlink(missing_ok=True)

def recover(database):
    path=Path(str(Path(database).resolve())+'.restore.json')
    if not path.exists():return
    value=json.loads(path.read_text())
    # Journal is generated locally with owner-only permissions; never read from an uploaded archive.
    if not value['committed']:
        snapshot=Path(value['snapshot'])
        if not snapshot.exists():raise RuntimeError('Restore recovery snapshot is missing. Preserve installation files and inspect the restore journal.')
        with sqlite3.connect(snapshot.as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(database) as target:source.backup(target)
        for base,stage,old in reversed(value['swaps']):
            base,stage,old=map(Path,(base,stage,old))
            if old.exists():
                if base.exists():shutil.rmtree(base)
                os.replace(old,base)
            if stage.exists():shutil.rmtree(stage)
    else:
        for base,stage,old in value['swaps']:
            for p in (Path(stage),Path(old)):
                if p.exists():shutil.rmtree(p)
    finish((path,value))
