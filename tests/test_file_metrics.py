import json
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from test_security import hosted, upload
from backend import queue
from backend.models import ScrapeJob
from backend.file_metrics import finish_files, pending_file, stamp


def test_completed_measurement_retains_page_count_and_progress(hosted, monkeypatch):
    a,_,sessions,_=hosted
    key=upload(a).json()['id']
    with sessions() as db: db.get(ScrapeJob,key).status='running';db.commit()
    def parse(*args):
        with sessions() as db:
            job=db.get(ScrapeJob,key);files=json.loads(job.file_outcomes_json)
            assert files[0]['started_at'].endswith('Z')
            files[0].update(page_count=17,progress={'phase':'reading','pages_done':16,'total_pages':17})
            job.file_outcomes_json=json.dumps(files);db.commit()
        return '7.4.11',{'known_issues':[]},[],{},{}
    monkeypatch.setattr(queue,'parse_isolated',parse)
    queue.run_pdf(key)
    item=a.get('/api/jobs/'+key).json()['file_outcomes'][0]
    assert item['status']=='completed' and item['page_count']==17
    assert item['elapsed_seconds']>=0 and item['completed_at']>=item['started_at']
    assert item['progress']['total_pages']==17


def test_failure_has_duration_and_retry_resets_only_failed_metrics(hosted, monkeypatch):
    a,_,sessions,_=hosted
    key=upload(a).json()['id']
    with sessions() as db:db.get(ScrapeJob,key).status='running';db.commit()
    def fail(*args):raise ValueError('Invalid document')
    monkeypatch.setattr(queue,'parse_isolated',fail);queue.run_pdf(key)
    item=a.get('/api/jobs/'+key).json()['file_outcomes'][0]
    assert item['status']=='failed' and item['elapsed_seconds']>=0
    with sessions() as db:
        j=db.get(ScrapeJob,key);files=json.loads(j.file_outcomes_json);files[0]['page_count']=4;j.file_outcomes_json=json.dumps(files);db.commit()
    retried=a.post('/api/jobs/'+key+'/retry').json()['file_outcomes'][0]
    assert retried=={'name':item['name'],'status':'pending','page_count':4}


def test_cancel_stops_live_timer_and_marks_waiting_documents(hosted):
    a,_,sessions,_=hosted;key=upload(a).json()['id']
    with sessions() as db:
        job=db.get(ScrapeJob,key);job.status='running';job.file_outcomes_json=json.dumps([
            {'name':'done','status':'completed','elapsed_seconds':5,'page_count':2},
            {'name':'active','status':'running','started_at':stamp(datetime.now(timezone.utc)-timedelta(seconds=10)),'page_count':9},
            {'name':'waiting','status':'pending'}]);db.commit()
    files=a.post('/api/jobs/'+key+'/cancel').json()['file_outcomes']
    assert files[0]=={'name':'done','status':'completed','elapsed_seconds':5,'page_count':2}
    assert files[1]['status']=='cancelled' and files[1]['elapsed_seconds']>=10 and files[1]['completed_at']
    assert files[2]['not_processed'] and files[2]['status']=='cancelled'


def test_restart_does_not_invent_time_during_downtime():
    job=SimpleNamespace(source='pdf',file_outcomes_json=json.dumps([{'name':'x','status':'running','started_at':'2020-01-01T00:00:00Z','elapsed_seconds':12}]))
    finish_files(job,'interrupted','Restart',interrupted=True)
    item=json.loads(job.file_outcomes_json)[0]
    assert item['elapsed_seconds']==12 and item['duration_is_partial']
    assert 'completed_at' not in item and item['status']=='interrupted'
    assert pending_file(item)=={'name':'x','status':'pending'}


def test_deadline_before_file_start_reports_not_processed(hosted, monkeypatch):
    a,_,sessions,_=hosted;key=upload(a).json()['id']
    with sessions() as db:
        job=db.get(ScrapeJob,key);job.status='running';args=json.loads(job.request_json);args['processing']['timeout_seconds']=0;job.request_json=json.dumps(args);db.commit()
    def forbidden(*args):raise AssertionError('Parser must not start after deadline')
    monkeypatch.setattr(queue,'parse_isolated',forbidden);queue.run_pdf(key)
    item=a.get('/api/jobs/'+key).json()['file_outcomes'][0]
    assert item['status']=='failed' and item['not_processed'] and 'started_at' not in item


def test_shutdown_measurement_is_not_overwritten_by_parser_completion(hosted, monkeypatch):
    import threading
    a,_,sessions,_=hosted;key=upload(a).json()['id']
    monkeypatch.setattr(queue,'STOP',threading.Event())
    with sessions() as db:db.get(ScrapeJob,key).status='running';db.commit()
    def shutting_down(*args):
        queue.STOP.set()
        with sessions() as db:
            job=db.get(ScrapeJob,key);finish_files(job,'interrupted','Shutdown');db.commit()
        return '7.4.11',{'known_issues':[]},[],{},{}
    monkeypatch.setattr(queue,'parse_isolated',shutting_down);queue.run_pdf(key)
    with sessions() as db:
        job=db.get(ScrapeJob,key);item=json.loads(job.file_outcomes_json)[0]
        assert item['status']=='interrupted' and item['elapsed_seconds']>=0
        assert job.all_data_json is None
