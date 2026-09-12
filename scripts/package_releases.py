#!/usr/bin/env python3
"""Package the current source tree, never runtime reports, PDFs, or credentials."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import subprocess

ROOT = Path(__file__).resolve().parent.parent
VERSION = '3.0.0'
TREES = ('backend', 'fgt_upgrade', 'frontend/src', 'frontend/tests', 'tests', 'scripts', 'licenses', 'releases', 'docs', '.github')
FILES = ('Dockerfile', '.dockerignore', '.gitignore', 'docker-compose.yml', 'compose.public.yml',
         'EDITION', 'LICENSE', 'README.md', 'API_GUIDE.md', 'TEAM_INSTALLATION.md', 'OPERATIONS.md', 'SECURITY.md', 'THIRD_PARTY_NOTICES.md', 'requirements.txt',
         'requirements.lock', 'fortigate_dashboard.py',
         'frontend/package.json', 'frontend/package-lock.json', 'frontend/index.html',
         'frontend/tsconfig.json', 'frontend/tsconfig.node.json', 'frontend/vite.config.ts',
         'frontend/postcss.config.js', 'frontend/tailwind.config.js')


def source_files():
    paths = {ROOT / name for name in FILES}
    for name in TREES:
        paths.update(p for p in (ROOT / name).rglob('*') if p.is_file())
    for path in sorted(paths):
        rel = path.relative_to(ROOT)
        if path.is_symlink() or any(x in rel.parts for x in ('__pycache__', '.pytest_cache', 'node_modules', 'dist')):
            continue
        if path.suffix in {'.pyc', '.pdf', '.db', '.log', '.tsbuildinfo'} or path.name.startswith('.env'):
            continue
        yield rel.as_posix(), path.read_bytes(), 0o755 if path.suffix == '.sh' else 0o644


def file_hash(path: Path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024**2), b''):
            digest.update(chunk)
    return digest.hexdigest()


def export_image(output: Path, docker_image: str):
    metadata = json.loads(subprocess.check_output(['docker', 'image', 'inspect', docker_image]))[0]
    if metadata['Os'] != 'linux' or metadata['Architecture'] not in {'amd64', 'arm64'}:
        raise ValueError('Release images must target Linux AMD64 or ARM64')
    expected = f'fgt-upgrade-review-public:{VERSION}'
    if expected not in metadata.get('RepoTags', []):
        raise ValueError(f'Tag the release image as {expected} before packaging')
    name = f'fgt-upgrade-review-{VERSION}-linux-{metadata["Architecture"]}-image.tar'
    path = output / name
    temporary = output / (name + '.tmp')
    try:
        subprocess.run(['docker', 'save', expected, '-o', str(temporary)], check=True)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path, {'id': metadata['Id'], 'platform': f'linux/{metadata["Architecture"]}', 'tag': expected}


def package(output: Path, docker_image: str | None = None):
    output = output.resolve()
    for tree in TREES:
        if output == ROOT / tree or ROOT / tree in output.parents:
            raise ValueError('Choose an output outside the packaged source directories, such as dist/releases')
    output.mkdir(parents=True, exist_ok=True)
    entries = list(source_files())
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data, _ in entries}
    checksums = []
    for edition in ((ROOT / 'EDITION').read_text().strip(),):
        prefix = f'fgt-upgrade-review-{VERSION}-{edition}'
        archive = output / f'{prefix}.tar.gz'
        generated = {'version': VERSION, 'edition': edition, 'files': manifest}
        contents = entries + [('RELEASE-MANIFEST.json', (json.dumps(generated, indent=2) + '\n').encode(), 0o644),
                              ('START-HERE.md', (ROOT / 'releases' / f'{edition.upper()}.md').read_bytes(), 0o644)]
        with archive.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as gz, tarfile.open(fileobj=gz, mode='w|') as tar:
            for name, data, mode in contents:
                info = tarfile.TarInfo(f'{prefix}/{name}')
                info.size, info.mode, info.mtime = len(data), mode, 0
                tar.addfile(info, io.BytesIO(data))
        checksums.append(f'{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}')
        print(archive)
    image_metadata = None
    if docker_image:
        path, image_metadata = export_image(output, docker_image)
        checksums.append(f'{file_hash(path)}  {path.name}')
        image_instructions = f"""Load the included {image_metadata['platform']} image:

```sh
docker load -i {path.name}
```

Then use `--no-build --pull never` instead of `--build` in the installation guide.
On other CPU architectures, build from source or use supported Docker emulation.
"""
    else:
        image_instructions = 'This source-only package does not include a Docker image. Build using the installation guide.\n'
    instructions = (ROOT / 'releases/DOWNLOADS.md').read_text().replace('{{VERSION}}', VERSION).replace('{{IMAGE_INSTRUCTIONS}}', image_instructions)
    (output / 'INSTALL.md').write_text(instructions)
    (output / 'BUILD-MANIFEST.json').write_text(json.dumps({'version': VERSION, 'source_files': manifest, 'image': image_metadata}, indent=2) + '\n')
    for name in ('INSTALL.md', 'BUILD-MANIFEST.json'):
        checksums.append(f'{file_hash(output / name)}  {name}')
    (output / 'SHA256SUMS').write_text('\n'.join(checksums) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--docker-image', help='Include this locally built image, tagged fgt-upgrade-review-public:' + VERSION)
    args = parser.parse_args()
    package(args.output, args.docker_image)
