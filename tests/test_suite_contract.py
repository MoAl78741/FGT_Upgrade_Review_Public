"""Coverage accounting is a tripwire, not a claim of code-coverage completeness."""
import ast,json,re
from pathlib import Path
from backend.main import app
ROOT=Path(__file__).resolve().parents[1]
MATRIX=json.loads((ROOT/'tests/feature_matrix.json').read_text())

def test_every_backend_module_is_accounted_for():
    actual={'tests/'+p.name for p in (ROOT/'tests').glob('test_*.py')}
    classified={p for f in MATRIX['features'] for p in f['backend']}|{'tests/'+p for p in MATRIX['separate']}
    assert actual==classified, f'Update feature_matrix.json for test modules: missing={actual-classified}, stale={classified-actual}'
    assert all(f['backend'] for f in MATRIX['features'])

def test_every_api_operation_has_a_feature_owner():
    actual={m.upper()+' '+p for p,methods in app.openapi()['paths'].items() for m in methods}
    listed=[op for f in MATRIX['features'] for op in f['operations']]
    assert len(set(listed))==len(listed), 'An API operation has multiple feature owners'
    assert actual==set(listed), f'Classify new/changed API operations: missing={actual-set(listed)}, stale={set(listed)-actual}'

def test_every_pro_switch_has_coverage():
    try:from backend.features import CATALOG
    except ImportError:return
    assert set(CATALOG)<={f['id'] for f in MATRIX['features']}

def test_coverage_references_real_test_modules_and_browser_tags():
    ids={f['id'] for f in MATRIX['features']}
    assert len(ids)==len(MATRIX['features'])
    for f in MATRIX['features']:
        for name in f['backend']:
            tree=ast.parse((ROOT/name).read_text())
            assert any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_') for n in ast.walk(tree)),name
    # Browser module cases contain the same declared IDs; regex covers static tags.
    browser=(ROOT/'tests/browser/features.spec.cjs').read_text()
    assert set(re.findall(r'@feature:([a-z_]+)',browser))<=ids


def test_network_guard_rejects_external_and_existing_local_services():
    import socket,pytest
    for address in [('192.0.2.1',443),('127.0.0.1',8000)]:
        with socket.socket() as connection:
            with pytest.raises(AssertionError,match='External networking'):
                connection.connect(address)
    with pytest.raises(AssertionError,match='External networking'):
        socket.getaddrinfo('publisher.example',443)


def test_network_guard_permits_a_test_owned_local_sink():
    import socket
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as receiver, socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
        receiver.bind(('127.0.0.1',0));receiver.settimeout(1)
        sender.sendto(b'synthetic audit event',receiver.getsockname())
        assert receiver.recv(100)==b'synthetic audit event'


def test_corpus_comparator_catches_source_loss_reordering_and_schema_drift():
    from scripts.check_corpus import changes
    original={'known_issues':[{'Bug ID':'100001','Description':'Keep **exact** text.'},{'Bug ID':'100002','Description':'Second row'}]}
    import copy
    same=copy.deepcopy(original)
    assert changes(original,same)==[]
    same['known_issues'][0]['Description']='Keep exact text.'
    assert changes(original,same)==['$.known_issues[0].Description']
    assert changes(original,{'known_issues':original['known_issues'][:1]})==['$.known_issues.length']
    assert changes(original,{'known_issues':list(reversed(original['known_issues']))})
    assert changes(original,dict(original,unreviewed_field=True))==['$.unreviewed_field']


def test_corpus_rejects_changed_seals_and_paths_outside_bundle(tmp_path):
    import hashlib,pytest
    from scripts.check_corpus import sealed
    root=tmp_path/'bundle';root.mkdir();source=root/'original.pdf';source.write_bytes(b'synthetic source')
    item={'path':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    assert sealed(root,item)==source
    source.write_bytes(b'different source')
    with pytest.raises(ValueError,match='seal mismatch'):sealed(root,item)
    with pytest.raises(ValueError,match='stay inside'):sealed(root,dict(item,path='../outside.pdf'))


def test_frontend_source_is_not_hidden_from_clean_checkouts():
    import subprocess
    if not (ROOT/'.git').exists():return  # Distributable archives intentionally omit Git metadata.
    sources=[str(p.relative_to(ROOT)) for p in (ROOT/'frontend/src').rglob('*') if p.is_file()]
    result=subprocess.run(['git','check-ignore','--stdin'],cwd=ROOT,input='\n'.join(sources)+'\n',text=True,capture_output=True)
    assert result.returncode in (0,1),result.stderr
    assert not result.stdout.strip(), 'Frontend source excluded from Git: '+result.stdout


def test_distributed_suite_fingerprints_source_without_git(tmp_path,monkeypatch):
    from scripts import check
    monkeypatch.setattr(check,'ROOT',tmp_path)
    source=tmp_path/'README.md';source.write_text('Reviewed source')
    plain=check.fingerprint();source.write_text('Changed source')
    assert check.fingerprint()!=plain
    (tmp_path/'RELEASE-MANIFEST.json').write_text(json.dumps({'files':{'README.md':'seal'}}))
    sealed=check.fingerprint()
    results=tmp_path/'test-results';results.mkdir();(results/'run.log').write_text('Generated diagnostics')
    assert check.fingerprint()==sealed
    source.write_text('Another source change')
    assert check.fingerprint()!=sealed


def test_release_pipeline_requires_both_checks_and_correct_edition():
    import yaml
    # BaseLoader keeps YAML's `on` key as a string instead of YAML 1.1 boolean True.
    workflows=ROOT/'.github/workflows'
    release=yaml.load((workflows/'release.yml').read_text(),Loader=yaml.BaseLoader)
    jobs=release['jobs']
    assert set(jobs['bundles']['needs'])=={'regression','security'}
    assert 'if' not in jobs['bundles'], 'Never override the default successful-dependencies gate'
    for name in ('regression','security'):
        assert jobs[name]['uses']==f'./.github/workflows/{name}.yml'
        reusable=yaml.load((workflows/f'{name}.yml').read_text(),Loader=yaml.BaseLoader)
        assert 'workflow_call' in reusable['on']
        assert '${{ github.workflow }}' in reusable['concurrency']['group']
    text=(workflows/'release.yml').read_text()
    edition=(ROOT/'EDITION').read_text().strip()
    image='pro' if edition=='private' else 'public'
    assert f'fgt-upgrade-review-${{VERSION}}-{edition}.tar.gz' in text
    assert f'fgt-upgrade-review-{image}:${{VERSION}}' in text
    assert 'continue-on-error' not in text
