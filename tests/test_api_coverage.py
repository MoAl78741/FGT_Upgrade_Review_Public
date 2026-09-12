"""GUI/API contract: public schema discovery and administrator-only workflows."""
import pytest
from test_team import named, login

# Explicit GUI requirements, independent of route registration.
OPERATIONS = {
    '/api/capabilities': 'get',
    '/api/releases': 'get',
    '/api/jobs': 'get post',
    '/api/jobs/upload': 'post',
    '/api/jobs/{job_id}': 'get delete',
    '/api/jobs/{job_id}/title': 'put',
    '/api/jobs/{job_id}/cancel': 'post',
    '/api/jobs/{job_id}/retry': 'post',
    '/api/jobs/{job_id}/files/{file_index}': 'get',
    '/api/jobs/{job_id}/view': 'post',
    '/api/jobs/{job_id}/compare': 'get',
    '/api/jobs/{job_id}/export': 'post',
    '/api/reviews': 'get post',
    '/api/reviews/{review_id}': 'get put delete',
    '/api/reviews/{review_id}/jobs': 'post',
    '/api/reviews/{review_id}/jobs/{job_id}': 'delete',
    '/api/reviews/{review_id}/decisions/{finding_id}': 'put',
    '/api/reviews/{review_id}/bulk-decisions': 'put',
    '/api/reviews/{review_id}/checklist': 'put',
    '/api/reviews/{review_id}/duplicate': 'post',
    '/api/reviews/{review_id}/completion': 'post',
    '/api/reviews/{review_id}/export': 'get',
    '/api/auth/status': 'get',
    '/api/auth/login': 'post',
    '/api/auth/logout': 'post',
    '/api/auth/password': 'post',
    '/api/auth/workspace': 'post',
    '/api/auth/users': 'get post',
    '/api/auth/users/{user_id}': 'put',
    '/api/auth/users/{user_id}/password': 'post',
    '/api/auth/workspaces': 'post',
    '/api/auth/memberships': 'get put',
    '/api/auth/memberships/{workspace_id}/{user_id}': 'delete',
    '/api/auth/audit': 'get',
    '/api/auth/admin-audit': 'get',
    '/api/settings/processing': 'get put delete',
    '/api/support/diagnostics': 'get',
    '/api/administration/status': 'get',
    '/api/administration/login': 'post',
    '/api/administration/logout': 'post',
    '/api/administration/password': 'post',
    '/api/administration/overview': 'get',
    '/api/administration/backup': 'post',
    '/api/administration/restore/preview': 'post',
    '/api/administration/restore/apply': 'post',
    '/api/administration/certificates': 'get post',
    '/api/administration/certificates/{identity}/download': 'get',
    '/api/administration/certificates/{identity}/activate': 'post',
    '/api/administration/certificates/{identity}': 'delete',
    '/api/administration/domains': 'get',
    '/api/administration/domains/{identity}': 'put',
    '/api/administration/profiles': 'get post',
    '/api/administration/profiles/{identity}': 'put delete',
    '/api/administration/logs': 'get',
    '/api/administration/syslog': 'get put',
    '/api/administration/syslog/test': 'post',
    '/api/administration/mail': 'get put',
    '/api/administration/mail/test': 'post',
    '/api/administration/schedules': 'get post',
    '/api/administration/schedules/{identity}': 'put delete',
    '/api/administration/deliveries': 'get',
    '/api/administration/deliveries/{identity}/retry': 'post',
}


def test_gui_operations_are_discoverable_in_swagger(client):
    response = client.get('/api/openapi.json')
    assert response.status_code == 200
    paths = response.json()['paths']
    for path, methods in OPERATIONS.items():
        for method in methods.split():
            assert method in paths.get(path, {}), f'{method.upper()} {path}'
            assert paths[path][method]['operationId']
    docs = client.get('/api/docs')
    assert docs.status_code == 200 and '/api/docs/init.js' in docs.text
    assert '/api/openapi.json' in client.get('/api/docs/init.js').text


@pytest.mark.parametrize('path,required', [
    ('/api/administration/restore/preview', {'file', 'password'}),
    ('/api/administration/restore/apply', {'file', 'password', 'current_password', 'sha256', 'confirmation'}),
    ('/api/administration/certificates', {'certificate', 'private_key'}),
    ('/api/jobs/upload', {'files'}),
])
def test_multipart_contract_is_usable_without_the_gui(client, path, required):
    schema = client.get('/api/openapi.json').json()
    body = schema['paths'][path]['post']['requestBody']['content']['multipart/form-data']['schema']
    if '$ref' in body:
        body = schema['components']['schemas'][body['$ref'].split('/')[-1]]
    assert required <= set(body['required'])


def test_admin_profile_and_schedule_lifecycle_via_api(named):
    client, _ = named
    login(client, 'admin')
    base = '/api/administration'
    created = client.post(base+'/profiles', json={'name':'API readers', 'permissions':['reports.read']})
    assert created.status_code == 200
    identity = created.json()['id']
    assert client.put(base+'/profiles/'+identity, json={'name':'API exporters', 'permissions':['reports.read','reports.export']}).status_code == 200
    profiles = client.get(base+'/profiles').json()['profiles']
    assert next(p for p in profiles if p['id']==identity)['name'] == 'API exporters'
    assert client.delete(base+'/profiles/'+identity).status_code == 200
    payload = {'workspace_id':'one','name':'API summary','recipients':['qa@example.com'],'interval_hours':24,'enabled':False}
    created = client.post(base+'/schedules', json=payload)
    assert created.status_code == 200
    identity = created.json()['id']
    payload['interval_hours'] = 48
    assert client.put(base+'/schedules/'+identity, json=payload).status_code == 200
    schedules = client.get(base+'/schedules').json()
    assert next(s for s in schedules if s['id']==identity)['interval_hours'] == 48
    assert client.delete(base+'/schedules/'+identity).status_code == 200
    assert client.get(base+'/schedules').json() == []
    assert client.get(base+'/deliveries').json() == []  # No email is sent.


@pytest.mark.parametrize('path', ['overview','profiles','domains','certificates','logs','syslog','mail','deliveries','schedules'])
def test_private_administration_api_denies_domain_members(named, path):
    client, _ = named
    login(client, 'reviewer')
    assert client.get('/api/administration/'+path).status_code == 403


@pytest.mark.parametrize('path,method,mime', [
    ('/api/administration/backup', 'post', 'application/octet-stream'),
    ('/api/administration/certificates/{identity}/download', 'get', 'application/x-pem-file'),
    ('/api/jobs/{job_id}/files/{file_index}', 'get', 'application/pdf'),
])
def test_binary_downloads_are_not_documented_as_json(client, path, method, mime):
    operation = client.get('/api/openapi.json').json()['paths'][path][method]
    content = operation['responses']['200']['content']
    assert set(content) == {mime}
    assert content[mime]['schema']['format'] == 'binary'


def test_pdf_timeout_is_only_advertised_on_pdf_attempts(client):
    paths = client.get('/api/openapi.json').json()['paths']
    found = {(path, method) for path, ops in paths.items() for method, op in ops.items()
             if any(p['name']=='X-PDF-Timeout-Minutes' for p in op.get('parameters', []))}
    assert found == {('/api/jobs/upload', 'post'), ('/api/jobs/{job_id}/retry', 'post')}
