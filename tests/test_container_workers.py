import json
import os
from pathlib import Path
import uuid
import pytest
from backend.runner_service import validate, read_file, worker_spec, Runner
from backend import container_worker


def payload():
    return {'job_id': str(uuid.uuid4()), 'filename': uuid.uuid4().hex+'-v7.6.6.pdf', 'timeout': 1800, 'max_pages': 500}


@pytest.mark.parametrize('key,value', [('job_id','../other'),('job_id','/etc'),('filename','../../secret.pdf'),('filename','a.pdf'),('filename','/etc/passwd'),('timeout',True),('timeout',7201),('max_pages',0),('max_pages',2001),('image','evil'),('command',['sh']),('mounts',['/'])])
def test_rejects_untrusted_launch_options(key,value):
    data=payload();data[key]=value
    with pytest.raises((ValueError, TypeError, AttributeError)): validate(data)


def test_valid_limits_and_generic_upload_name():
    data=payload();data['filename']=uuid.uuid4().hex+'-vfile-1.pdf'
    assert validate(data)==data


def test_rejects_links_and_special_files(tmp_path):
    (tmp_path/'secret').write_text('secret')
    (tmp_path/'link').symlink_to(tmp_path/'secret')
    with pytest.raises(OSError):read_file(tmp_path,'link',100)
    os.link(tmp_path/'secret',tmp_path/'hard')
    with pytest.raises(ValueError):read_file(tmp_path,'hard',100)
    os.mkfifo(tmp_path/'fifo')
    with pytest.raises(ValueError):read_file(tmp_path,'fifo',100)
    (tmp_path/'big').write_bytes(b'x'*11)
    with pytest.raises(ValueError):read_file(tmp_path,'big',10)
    directory=tmp_path/'dir';directory.mkdir()
    (tmp_path/'alias').symlink_to(directory,target_is_directory=True)
    with pytest.raises(OSError):read_file(tmp_path/'alias','file',10)


def test_worker_has_only_its_stage_and_no_secrets_or_host_privilege():
    data=payload()
    spec=worker_spec('sha256:verified','/volume/run','public','run',data,2*1024**3)
    assert spec['Cmd'][0]=='/job/'+data['filename']  # Preserve parser filename fallback.
    assert spec['Healthcheck']=={'Test':['NONE']}
    host=spec['HostConfig']
    assert spec['NetworkDisabled'] and host['NetworkMode']=='none'
    assert spec['User']=='10001:10001' and host['ReadonlyRootfs']
    assert host['CapDrop']==['ALL'] and host['SecurityOpt']==['no-new-privileges:true']
    assert host['Memory']==host['MemorySwap']==2*1024**3
    assert host['PidsLimit']==64 and host['NanoCpus']==1000000000
    assert host['Mounts']==[{'Type':'bind','Source':'/volume/run','Target':'/job','ReadOnly':False,'BindOptions':{'Propagation':'rslave'}}]
    assert not any('PASSWORD' in item or 'DB_PATH' in item or 'RUNNER' in item for item in spec['Env'])
    assert host['RestartPolicy']=={'Name':'no'} and host['LogConfig']=={'Type':'none'}


def test_explicit_backend_and_no_automatic_fallback(monkeypatch):
    monkeypatch.delenv('PDF_WORKER_BACKEND',raising=False)
    assert container_worker.enabled() is False
    monkeypatch.setenv('PDF_WORKER_BACKEND','container');assert container_worker.enabled()
    monkeypatch.setenv('PDF_WORKER_BACKEND','disabled')
    with pytest.raises(RuntimeError):container_worker.enabled()


def test_client_progress_result_and_cancel(tmp_path,monkeypatch):
    calls=[]
    def rpc(sock,method,path,data=None):
        calls.append((method,path,data))
        if method=='POST':return {'id':'a'*32}
        if path.endswith('/result'):return {'page_count':2,'result':['7.6.6',{},[],{},{}]}
        if method=='GET':return {'done':True,'exit_code':0,'progress':{'phase':'finalizing','pages_done':2,'total_pages':2}}
        return {'ok':True}
    monkeypatch.setattr(container_worker,'request',rpc)
    source=tmp_path/'source.pdf';output=tmp_path/'output.json'
    worker=container_worker.ContainerProcess(str(uuid.uuid4()),source,output,60,500)
    assert worker.wait()==0 and json.loads(output.read_text())['page_count']==2
    assert json.loads(source.with_suffix('.progress.json').read_text())['total_pages']==2
    worker.kill();assert calls[-1][0]=='DELETE'


def test_reset_only_touches_this_installations_workers(tmp_path):
    import threading
    runner=Runner.__new__(Runner)
    runner.identity='public';runner.lock=threading.RLock();runner.runs={};runner.state=tmp_path
    calls=[]
    def docker(method,path,data=None):
        calls.append((method,path))
        return [{'Id':'one'}] if method=='GET' else None
    runner.docker=docker
    runner.reset()
    assert 'io.fgt.pdf-runner' in calls[0][1] and 'public' in calls[0][1]
    assert calls[1]==('DELETE','/containers/one?force=true&v=true')
