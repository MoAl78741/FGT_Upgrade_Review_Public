import json
from datetime import datetime, timedelta
from backend.main import app
from backend.database import get_db
from backend.models import ScrapeJob, Review
from backend import queue
from test_security import hosted


def seed(db, version='7.6.6', owner='local', **extra):
    job = ScrapeJob(from_version=version, to_version=version, owner_id=owner, source='pdf', status='completed',
                    versions_json=json.dumps([version]), all_data_json=json.dumps({version: {'known_issues': [
                        {'Bug ID': '123', 'Description': 'Original **source** text', 'markdown': 'Original **source** text'}]}}), **extra)
    db.add(job); db.commit(); db.refresh(job)
    return job.id


def local_seed(version='7.6.6'):
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try: return seed(db, version)
    finally: gen.close()


def create(client):
    r = client.post('/api/reviews', json={'title': 'Branch upgrade', 'customer': 'Example', 'expected_versions': ['7.6.5', '7.6.6']})
    assert r.status_code == 201, r.text
    return r.json()


def test_review_groups_batches_without_copying_sources(client):
    review = create(client)
    for version in ['7.6.5', '7.6.6']:
        job_id = local_seed(version)
        original = client.get('/api/jobs/' + job_id).json()
        r = client.post(f"/api/reviews/{review['id']}/jobs", json={'job_id': job_id, 'revision': review['revision']})
        assert r.status_code == 200, r.text
        review = r.json()
        assert client.get('/api/jobs/' + job_id).json() == original
    assert len(review['findings']) == 2
    assert review['missing_versions'] == []
    assert len(review['jobs']) == 2


def test_overlap_and_incomplete_import_rejected(client):
    review = create(client)
    key = review['id']
    job = local_seed()
    review = client.post(f'/api/reviews/{key}/jobs', json={'job_id': job, 'revision': 1}).json()
    assert client.post(f'/api/reviews/{key}/jobs', json={'job_id': local_seed(), 'revision': review['revision']}).status_code == 409
    pending = client.post('/api/jobs', json={'from_version': '7.4.10', 'to_version': '7.4.11'}).json()
    assert client.post(f'/api/reviews/{key}/jobs', json={'job_id': pending['id'], 'revision': review['revision']}).status_code == 409


def test_saved_decisions_conflicts_and_validation(client):
    review = create(client);key = review['id']
    review = client.post(f'/api/reviews/{key}/jobs', json={'job_id': local_seed(), 'revision': 1}).json()
    finding = review['findings'][0]['id'];url = f'/api/reviews/{key}/decisions/{finding}'
    assert client.put(url, json={'revision': 2, 'status': 'not_applicable'}).status_code == 422
    assert client.put(url, json={'revision': 2, 'status': 'reviewed', 'config': 'secret'}).status_code == 422
    assert client.put(url, json={'revision': 2, 'status': 'needs_testing', 'note': 'Verify failover'}).status_code == 200
    assert client.put(url, json={'revision': 2, 'status': 'reviewed'}).status_code == 409
    saved = client.get(f'/api/reviews/{key}').json()
    assert saved['decisions'][finding]['note'] == 'Verify failover'
    assert saved['findings'][0]['source']['Description'] == 'Original **source** text'
    assert client.put(f'/api/reviews/{key}/decisions/unknown', json={'revision': 3, 'status': 'reviewed'}).status_code == 404


def test_source_deletion_is_visible_and_review_delete_keeps_jobs(client):
    review = create(client);key = review['id'];job = local_seed()
    client.post(f'/api/reviews/{key}/jobs', json={'job_id': job, 'revision': 1})
    client.delete('/api/jobs/' + job)
    result = client.get(f'/api/reviews/{key}').json()
    assert result['unavailable_job_ids'] == [job]
    assert result['findings'] == []
    other = local_seed('7.6.5')
    client.post(f'/api/reviews/{key}/jobs', json={'job_id': other, 'revision': 2})
    assert client.delete(f'/api/reviews/{key}').status_code == 204
    assert client.get('/api/jobs/' + other).status_code == 200


def test_duplicate_is_new_review_without_old_decisions(client):
    review = create(client)
    result = client.post(f"/api/reviews/{review['id']}/duplicate").json()
    assert result['customer'] == 'Example'
    assert result['id'] != review['id']
    assert result['job_ids'] == [] and result['decisions'] == {}


def test_checklist_rejects_duplicate_ids(client):
    review = create(client)
    item = {'id': 'one', 'phase': 'before', 'text': 'Verify backup', 'done': False}
    url = f"/api/reviews/{review['id']}/checklist"
    assert client.put(url, json={'revision': 1, 'items': [item, item]}).status_code == 422
    assert client.put(url, json={'revision': 1, 'items': [item]}).json()['checklist'] == [item]


def test_public_review_ownership_and_expiry(hosted):
    a, b, sessions, _ = hosted
    for c in (a, b): c.get('/api/capabilities')
    review = create(a);key = review['id']
    assert b.get('/api/reviews').json() == []
    for method, suffix, data in [('get', '', None), ('delete', '', None), ('post', '/duplicate', None),
                                  ('post', '/jobs', {'revision': 1, 'job_id': 'foreign'})]:
        kwargs = {'json': data} if data else {}
        assert getattr(b, method)(f'/api/reviews/{key}{suffix}', **kwargs).status_code == 404
    with sessions() as db:
        original = db.get(Review, key)
        foreign = seed(db, owner='someone-else', expires_at=datetime.utcnow() + timedelta(hours=1))
        assert a.post(f'/api/reviews/{key}/jobs', json={'revision': 1, 'job_id': foreign}).status_code == 404
        original.expires_at = datetime.utcnow() - timedelta(seconds=1); db.commit()
    assert a.get(f'/api/reviews/{key}').status_code == 404
    with sessions() as db:
        queue.clean_expired(db)
        assert db.get(Review, key) is None


def test_notices_and_blocks_only_sections_are_findings(client):
    gen = app.dependency_overrides[get_db]();db = next(gen)
    try:
        job_id = seed(db)
        job = db.get(ScrapeJob, job_id)
        job.special_notices_json = json.dumps([{'version': '7.6.6', 'title': 'Universal warning', 'content': 'Read before upgrading'}])
        data = json.loads(job.all_data_json)
        data['7.6.6']['upgrade-information'] = {'title': 'Upgrade', 'blocks': [{'type': 'paragraph', 'text': 'Preserve the backup'}]}
        job.all_data_json = json.dumps(data);db.commit()
    finally: gen.close()
    review = create(client)
    result = client.post(f"/api/reviews/{review['id']}/jobs", json={'job_id': job_id, 'revision': 1}).json()
    assert len(result['findings']) == 3
    assert {f['section'] for f in result['findings']} == {'known_issues', 'special_notices', 'upgrade-information'}


def test_pdf_section_reference_and_safe_source_access(client, tmp_path):
    from backend.routers import jobs as routes
    job_id = local_seed()
    root = routes.settings.uploads / job_id;root.mkdir()
    (root / 'stored.pdf').write_bytes(b'%PDF-1.4\nsource fixture')
    gen = app.dependency_overrides[get_db]();db = next(gen)
    try:
        job = db.get(ScrapeJob, job_id)
        job.request_json = json.dumps({'files': [{'stored': 'stored.pdf', 'name': 'release-7.6.6.pdf'}]})
        job.file_outcomes_json = json.dumps([{'status': 'completed', 'version': '7.6.6', 'section_pages': {'known_issues': [4, 5]}}]);db.commit()
    finally: gen.close()
    review = create(client)
    data = client.post(f"/api/reviews/{review['id']}/jobs", json={'job_id': job_id, 'revision': 1}).json()
    ref = data['findings'][0]['reference']
    assert ref['page'] == 5 and ref['precision'] == 'section'
    assert client.get(ref['url']).content == b'%PDF-1.4\nsource fixture'
    assert client.get(f'/api/jobs/{job_id}/files/-1').status_code == 404
    gen = app.dependency_overrides[get_db]();db = next(gen)
    try:
        db.get(ScrapeJob, job_id).request_json = json.dumps({'files': [{'stored': '../outside.pdf', 'name': 'bad.pdf'}]});db.commit()
    finally: gen.close()
    assert client.get(f'/api/jobs/{job_id}/files/0').status_code == 404


def test_foreign_session_cannot_fetch_source_pdf(hosted):
    a, b, sessions, cfg = hosted
    a.get('/api/capabilities');b.get('/api/capabilities')
    import hashlib
    owner_id = hashlib.sha256(a.cookies.get('fgt_session').encode()).hexdigest()
    with sessions() as db:
        key = seed(db, owner=owner_id, expires_at=datetime.utcnow() + timedelta(hours=1))
    assert b.get(f'/api/jobs/{key}/files/0').status_code == 404


def test_review_range_persists_baseline_and_keeps_legacy_api_updates(client):
    payload={'title':'Range', 'range_from':'7.6.3', 'range_to':'7.6.6', 'range_include_from':False,
             'expected_versions':['7.6.4','7.6.5','7.6.6']}
    r=client.post('/api/reviews',json=payload);assert r.status_code==201
    review=r.json();key=review['id']
    saved=client.get('/api/reviews/'+key).json()
    assert saved['range_from']=='7.6.3' and saved['range_to']=='7.6.6' and saved['range_include_from'] is False
    r=client.put('/api/reviews/'+key,json={'title':'Renamed','revision':review['revision'],'expected_versions':payload['expected_versions']})
    assert r.status_code==200 and r.json()['range_from']=='7.6.3'
    invalid=payload|{'range_to':'7.6.2'}
    assert client.post('/api/reviews',json=invalid).status_code==422
