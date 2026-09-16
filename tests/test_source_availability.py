import json
from datetime import datetime
from backend.source_files import source_path
from backend.routers import jobs
from backend.models import ScrapeJob

def test_retained_original_availability_and_paths(tmp_path,monkeypatch):
    job=ScrapeJob(id='example',from_version='7.6.6',to_version='7.6.6',created_at=datetime.utcnow(),status='completed',source='pdf',use_selenium=False,
      request_json=json.dumps({'files':[{'name':'source.pdf','stored':'original.pdf'}]}),file_outcomes_json=json.dumps([{'name':'source.pdf','status':'completed'}]))
    from dataclasses import replace
    monkeypatch.setattr(jobs,'settings',replace(jobs.settings,uploads=tmp_path))
    result=jobs.response(job,True)
    assert result.file_outcomes[0]['source_available'] is False
    assert any('Original source PDF unavailable' in w for w in result.warnings)
    assert 'source_available' not in job.file_outcomes_json
    folder=tmp_path/job.id;folder.mkdir();(folder/'original.pdf').write_bytes(b'%PDF-test')
    assert source_path(job,0,tmp_path)==folder/'original.pdf'
    assert jobs.response(job,True).file_outcomes[0]['source_available'] is True
    for stored in ['../escape.pdf',str(tmp_path/'escape.pdf')]:
        (tmp_path/'escape.pdf').write_bytes(b'outside')
        job.request_json=json.dumps({'files':[{'stored':stored}]})
        assert source_path(job,0,tmp_path) is None
    assert source_path(job,-1,tmp_path) is None
