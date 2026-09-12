import json
import subprocess
from bs4 import BeautifulSoup
import pytest
from backend.database import get_db
from backend.main import app
from backend.models import ScrapeJob
from backend import report_renderer

@pytest.fixture
def report(client):
    gen = app.dependency_overrides[get_db](); db = next(gen)
    base = {'Bug ID':'42','category':'System','Description':'Original source <script id="attack">alert(1)</script>', 'markdown':'Original **source** <script id="attack">alert(1)</script>'}
    db.add(ScrapeJob(id='source',owner_id='local',status='completed',source='pdf',from_version='7.6.5',to_version='7.6.6',
        versions_json='["7.6.5","7.6.6"]',all_data_json=json.dumps({
        '7.6.5':{'known_issues':[base],'new_features':[{'Feature ID':'7','category':'System','Description':'Old description'}]},
        '7.6.6':{'known_issues':[base,base], 'new_features':[{'Feature ID':'7','category':'System','Description':'Changed description'}]}})))
    db.commit()
    try: yield client
    finally: gen.close()


def test_view_selection_and_export_preserve_source(report):
    before = report.get('/api/jobs/source').json()
    options = {'sections':['known_issues']}
    off = report.post('/api/jobs/source/view',json=options)
    assert off.status_code == 200, off.text
    assert off.json()['count'] == 3
    on = report.post('/api/jobs/source/view',json={**options,'consolidate_all':True}).json()
    assert on['count'] == 1 and on['source_count'] == 3
    assert on['entries'][0]['builds'] == ['7.6.5','7.6.6']
    selection = [on['entries'][0]['selection'][0]]
    r = report.post('/api/jobs/source/export',json={**options,'consolidate_all':True,'selection':selection,'format':'csv'})
    assert r.status_code == 200 and '7.6.5' in r.text and '7.6.6' not in r.text
    html = report.post('/api/jobs/source/export',json={**options,'consolidate_all':True})
    assert html.status_code == 200
    soup = BeautifulSoup(html.text,'html.parser')
    assert len(soup.select('#issues-table tbody tr')) == 1
    assert '7.6.5, 7.6.6' in soup.get_text()
    assert soup.find(id='attack') is None
    assert soup.select_one('#issues-table strong').get_text() == 'source'
    assert report.get('/api/jobs/source').json() == before


def test_catalog_comparison_and_review_export(report):
    r=report.get('/api/releases',params={'from_version':'7.6.5','to_version':'7.6.6','include_from':True})
    assert r.status_code == 200, r.text
    assert [v['version'] for v in r.json()['releases']] == ['7.6.5','7.6.6']
    assert report.get('/api/releases',params={'from_version':'7.6.5'}).status_code == 422
    r=report.get('/api/jobs/source/compare',params={'from_version':'7.6.5','to_version':'7.6.6'}).json()
    assert r['changed'] == ['7'] and len(r['changedA']) == len(r['changedB']) == 1
    review=report.post('/api/reviews',json={'title':'Test review'}).json()
    assert report.post(f"/api/reviews/{review['id']}/jobs",json={'revision':1,'job_id':'source'}).status_code == 200
    output=report.get(f"/api/reviews/{review['id']}/export")
    assert output.status_code == 200 and 'Test review' in output.text
    assert 'Source findings and reviewer annotations' in output.text


def test_validation_and_no_config_endpoint(report):
    for body in [{'raw_config':'secret'}, {'localRelevance':{}}, {'sections':['not-a-section']}, {'selection':[{'version':'7.6.5','section':'known_issues','index':99}]}]:
        assert report.post('/api/jobs/source/export',json=body).status_code == 422
    assert report.post('/api/jobs/source/view',json={'limit':5001}).status_code == 422
    assert report.post('/api/config',json={}).status_code in (404,405)


def test_swagger_is_offline_and_csp_stays_strict(client):
    r=client.get('/api/docs');soup=BeautifulSoup(r.text,'html.parser')
    assert r.status_code == 200
    assert all(s.get('src','').startswith('/api/docs/') for s in soup.find_all('script'))
    assert all(not s.string for s in soup.find_all('script'))
    assert "script-src 'self';" in r.headers['content-security-policy']
    for asset in ['swagger-ui.css','swagger-ui-bundle.js']:
        assert client.get('/api/docs/assets/'+asset).status_code == 200
    assert 'validatorUrl: null' in client.get('/api/docs/init.js').text
    schema=client.get('/api/openapi.json').json()
    assert '/api/jobs/{job_id}/export' in schema['paths']
    assert '/{full_path}' not in schema['paths']
    assert client.get('/api/docs/guide').status_code == 200
    assert any(p['name']=='X-PDF-Timeout-Minutes' for p in schema['paths']['/api/jobs/upload']['post']['parameters'])


def test_renderer_backpressure_and_timeout(monkeypatch):
    report_renderer.SLOTS.acquire()
    try:
        with pytest.raises(Exception) as e: report_renderer.render({'operation':'releases'})
        assert e.value.status_code == 429
    finally: report_renderer.SLOTS.release()
    def timeout(*args,**kwargs): raise subprocess.TimeoutExpired('node',30)
    monkeypatch.setattr(report_renderer.subprocess,'run',timeout)
    with pytest.raises(Exception) as e: report_renderer.render({'operation':'releases'})
    assert e.value.status_code == 504
