"""Pro naming keeps access policy stable; bulk decisions are atomic and authorized."""
import pytest
from test_team import named,login
from test_security import hosted

@pytest.mark.parametrize('url,expected', [('',None),('javascript:alert(1)',None),('http://example.com',None),('https://user:password@example.com',None),('https://[',None),('https://example.com/pro','https://example.com/pro')])
def test_upgrade_destination_is_operator_https_configuration(client,monkeypatch,url,expected):
    monkeypatch.setenv('PRO_UPGRADE_URL',url)
    value=client.get('/api/capabilities').json()
    assert value['edition']=='private' and value['edition_label']=='Pro'
    assert value['pro_upgrade_url']==expected


def review_with_findings(client):
    review=client.post('/api/reviews',json={'title':'API bulk review'}).json()
    response=client.post('/api/reviews/'+review['id']+'/jobs',json={'revision':review['revision'],'job_id':'one-job'})
    assert response.status_code==200,response.text
    return client.get('/api/reviews/'+review['id']).json()


def test_bulk_decisions_validation_revision_and_permissions(named):
    c,db=named;login(c,'reviewer');review=review_with_findings(c)
    path='/api/reviews/'+review['id']+'/bulk-decisions'
    payload={'revision':review['revision'],'finding_ids':[review['findings'][0]['id']], 'status':'reviewed','note':'Verified with source'}
    assert c.put(path,json={**payload,'finding_ids':payload['finding_ids']+['unavailable']}).status_code==404
    assert c.get('/api/reviews/'+review['id']).json()['decisions']=={}
    assert c.put(path,json={**payload,'status':'not_applicable','note':''}).status_code==422
    response=c.put(path,json=payload);assert response.status_code==200,response.text
    assert response.json()['revision']==payload['revision']+1
    assert c.put(path,json=payload).status_code==409
    saved=c.get('/api/reviews/'+review['id']).json()
    assert saved['decisions'][payload['finding_ids'][0]]['reviewed_by']=='reviewer'
    login(c,'viewer');assert c.put(path,json={**payload,'revision':saved['revision']}).status_code==403


def test_source_frames_retain_authentication_and_no_other_page_is_frameable(named):
    c,_=named
    response=c.get('/api/jobs/one-job/files/0')
    assert response.status_code==401
    assert response.headers['x-frame-options']=='SAMEORIGIN'
    assert "frame-ancestors 'self'" in response.headers['content-security-policy']
    response=c.get('/api/capabilities')
    assert response.headers['x-frame-options']=='DENY'
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']


def test_report_name_is_metadata_and_respects_domain_permissions(named):
    c,_=named;login(c,'reviewer')
    before=c.get('/api/jobs/one-job').json()
    assert c.put('/api/jobs/one-job/title',json={'title':'Branch lab'}).status_code==200
    after=c.get('/api/jobs/one-job').json()
    assert after['title']=='Branch lab' and after['all_data']==before['all_data']
    assert c.put('/api/jobs/two-job/title',json={'title':'Other customer'}).status_code==404
    login(c,'viewer')
    assert c.put('/api/jobs/one-job/title',json={'title':'Denied'}).status_code==403


def test_report_title_migration_preserves_existing_source(tmp_path,monkeypatch):
    from sqlalchemy import create_engine,text
    from backend import database
    engine=create_engine('sqlite:///'+str(tmp_path/'legacy.sqlite'))
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE scrape_jobs (id VARCHAR(36) PRIMARY KEY, all_data_json TEXT)'))
        conn.execute(text("INSERT INTO scrape_jobs VALUES ('existing', '{\"source\":\"unchanged\"}')"))
    monkeypatch.setattr(database,'engine',engine)
    database.run_migrations();database.run_migrations()
    with engine.connect() as conn:
        row=conn.execute(text('SELECT id,all_data_json,title FROM scrape_jobs')).one()
        assert tuple(row)==('existing','{"source":"unchanged"}',None)


def test_local_api_is_portable_and_zip_keeps_source_bytes():
    import base64,io,os,shutil,subprocess,zipfile
    from pathlib import Path
    module=Path(__file__).resolve().parents[1]/'frontend/dist/assets/local-api.mjs'
    assert module.exists(), 'Build frontend assets before running API tests.'
    script="""globalThis.fetch=()=>{throw Error('Local API attempted networking')};
const api=await import(process.argv[1]);
if(typeof api.analyzeConfig!=='function')throw Error('Missing local analyzer');
for(const name of ['../escape','/absolute']){let rejected=false;try{api.sessionZip([{name,data:new Uint8Array()}])}catch{rejected=true}if(!rejected)throw Error('Unsafe path')}
const data=new TextEncoder().encode('Unchanged source — café');
console.log(Buffer.from(await api.sessionZip([{name:'reports/source.txt',data}]).arrayBuffer()).toString('base64'));
"""
    result=subprocess.check_output([os.getenv('NODE_BINARY') or shutil.which('node') or 'node','--input-type=module','-e',script,module.as_uri()],text=True)
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(result))) as archive:
        assert archive.testzip() is None
        assert archive.read('reports/source.txt').decode()=='Unchanged source — café'


def test_pre_pro_encrypted_backup_accepts_missing_title(named,monkeypatch,tmp_path):
    import io,json,hashlib,zipfile
    from backend import installation_archive as archive
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from test_team import PASSWORD
    _,db=named
    monkeypatch.setenv('ADMIN_STATE_DIR',str(tmp_path/'admin'))
    raw=archive.pack(db,PASSWORD);i=len(archive.MAGIC);salt=raw[i:i+16];nonce=raw[i+16:i+28]
    cipher=AESGCM(archive.derive(PASSWORD,salt))
    with zipfile.ZipFile(io.BytesIO(cipher.decrypt(nonce,raw[i+28:],archive.MAGIC))) as z:
        files={n:z.read(n) for n in z.namelist() if n!='manifest.json'}
    data=json.loads(files['state.json'])
    for row in data['tables']['scrape_jobs']:row.pop('title')
    files['state.json']=json.dumps(data).encode()
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for name,content in files.items():z.writestr(name,content)
        z.writestr('manifest.json',json.dumps({name:hashlib.sha256(content).hexdigest() for name,content in files.items()}))
    import secrets
    new_nonce=secrets.token_bytes(12)
    migrated,_=archive.unpack(archive.MAGIC+salt+new_nonce+cipher.encrypt(new_nonce,out.getvalue(),archive.MAGIC),PASSWORD)
    assert all(row['title'] is None for row in migrated['tables']['scrape_jobs'])


def test_public_branding_does_not_enable_pro_capabilities(hosted,monkeypatch):
    client,_,_,_=hosted
    monkeypatch.setenv('PRO_UPGRADE_URL','https://example.com/pro')
    result=client.get('/api/capabilities').json()
    assert result['edition']=='public' and result['edition_label']=='Public'
    assert result['pro_upgrade_url']=='https://example.com/pro'
    assert result['scraping'] is False and result['team_auth'] is False
    assert client.get('/api/administration/overview').status_code==401
