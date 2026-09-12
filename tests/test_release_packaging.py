"""Distribution checks: extractable builds, complete manifests, no runtime content."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('package_releases', ROOT / 'scripts/package_releases.py')
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)


def test_edition_archives_are_complete_reproducible_and_exclude_runtime(tmp_path):
    packaging.package(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    packaging.package(tmp_path)
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    for edition in ((packaging.ROOT / 'EDITION').read_text().strip(),):
        archive = tmp_path / f'fgt-upgrade-review-{packaging.VERSION}-{edition}.tar.gz'
        with tarfile.open(fileobj=io.BytesIO(archive.read_bytes())) as tar:
            members = tar.getmembers()
            names = {m.name.split('/', 1)[1]: m for m in members}
            assert all(m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in members)
            assert not any(n.endswith(('.db', '.pdf', '.pyc')) or '/node_modules/' in n or n.startswith(('uploads/', 'data/')) for n in names)
            assert not any(Path(n).name.startswith('.env') for n in names)
            for required in ('Dockerfile', 'requirements.lock', 'frontend/package-lock.json', 'backend/main.py', 'frontend/src/main.tsx', 'LICENSE', 'TEAM_INSTALLATION.md', 'OPERATIONS.md', 'backend/maintenance.py', 'START-HERE.md', 'releases/public.env.example', 'compose.public.yml'):
                assert required in names
            manifest = json.load(tar.extractfile(names['RELEASE-MANIFEST.json']))
            assert manifest['edition'] == edition
            for name, digest in manifest['files'].items():
                assert hashlib.sha256(tar.extractfile(names[name]).read()).hexdigest() == digest
            assert f'# {edition.title()} edition'.encode() in tar.extractfile(names['START-HERE.md']).read()


def test_image_bundle_manifest_and_all_checksums(tmp_path, monkeypatch):
    metadata = {'Os': 'linux', 'Architecture': 'amd64', 'Id': 'sha256:test-image', 'RepoTags': ['fgt-upgrade-review-public:3.0.0']}
    monkeypatch.setattr(packaging.subprocess, 'check_output', lambda args: json.dumps([metadata]).encode())
    def save_image(args, check):
        assert args[:3] == ['docker', 'save', 'fgt-upgrade-review-public:3.0.0']
        Path(args[-1]).write_bytes(b'synthetic image archive')
    monkeypatch.setattr(packaging.subprocess, 'run', save_image)
    packaging.package(tmp_path, 'fgt-upgrade-review-public:3.0.0')
    manifest = json.loads((tmp_path / 'BUILD-MANIFEST.json').read_text())
    assert manifest['image'] == {'id': 'sha256:test-image', 'platform': 'linux/amd64', 'tag': 'fgt-upgrade-review-public:3.0.0'}
    checked = set()
    for line in (tmp_path / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == digest
        checked.add(name)
    assert checked == {p.name for p in tmp_path.iterdir() if p.name != 'SHA256SUMS'}
    assert 'docker load -i fgt-upgrade-review-3.0.0-linux-amd64-image.tar' in (tmp_path / 'INSTALL.md').read_text()


def test_reject_wrong_image_tag_before_export(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(packaging.subprocess, 'check_output', lambda args: json.dumps([{'Os': 'linux', 'Architecture': 'amd64', 'RepoTags': ['unrelated:latest']}]).encode())
    with pytest.raises(ValueError, match='Tag the release image'):
        packaging.export_image(tmp_path, 'unrelated:latest')
    assert not list(tmp_path.iterdir())
