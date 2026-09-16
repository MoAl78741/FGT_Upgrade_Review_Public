#!/usr/bin/env python3
"""Inventory vendored artifacts and retain their original notices without extraction."""
import email
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NOTICE = re.compile(r'license|licence|copying|copyright|notice', re.I)
BAD = re.compile(r'pymupdf|(?:^|[-_])mupdf|^fitz$', re.I)


def safe(value): return re.sub(r'[^a-zA-Z0-9_.-]', '_', value)


def keep(destination, name, content):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts: raise ValueError('Unsafe notice path')
    target = destination.joinpath(*path.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def main():
    packages = []
    for wheel in sorted((ROOT/'vendor/python').rglob('*.whl')):
        with zipfile.ZipFile(wheel) as archive:
            info = email.message_from_bytes(archive.read(next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))))
            name, version = info['Name'], info['Version']
            if BAD.search(name): raise ValueError(f'Forbidden vendored dependency: {name}')
            dest = ROOT/'licenses/python'/wheel.parent.name/safe(f'{name}-{version}')
            notices = [n for n in archive.namelist() if NOTICE.search(n) and not n.endswith('/')]
            for n in notices: keep(dest,n,archive.read(n))
            packages.append({'ecosystem':'python','name':name,'version':version,'platform':wheel.parent.name,
                             'license':info['License-Expression'] or info['License'] or '; '.join(v for v in info.get_all('Classifier',[]) if v.startswith('License ::')),
                             'artifact':str(wheel.relative_to(ROOT)), 'notices':[str((dest/n).relative_to(ROOT)) for n in notices]})
    for blob in sorted((ROOT/'vendor/npm/_cacache/content-v2').rglob('*')):
        if not blob.is_file():continue
        try: archive=tarfile.open(blob,'r:gz')
        except tarfile.TarError:continue
        with archive:
            try: package=json.load(archive.extractfile('package/package.json'))
            except (KeyError,TypeError,json.JSONDecodeError):continue
            name,version=package['name'],package['version']
            if BAD.search(name):raise ValueError(f'Forbidden npm dependency: {name}')
            dest=ROOT/'licenses/npm'/safe(f'{name}-{version}')
            notices=[]
            for entry in archive.getmembers():
                if entry.isfile() and NOTICE.search(PurePosixPath(entry.name).name):
                    keep(dest,entry.name,archive.extractfile(entry).read());notices.append(str((dest/entry.name).relative_to(ROOT)))
            packages.append({'ecosystem':'npm','name':name,'version':version,'license':package.get('license'),
                             'artifact':str(blob.relative_to(ROOT)), 'notices':notices})
    inventory = {'packages':packages, 'artifacts':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted((ROOT/'vendor').rglob('*')) if p.is_file() and p.name != 'MANIFEST.json'}}
    (ROOT/'vendor/MANIFEST.json').write_text(json.dumps(inventory,indent=2)+'\n')
    (ROOT/'licenses/DEPENDENCIES.json').write_text(json.dumps(packages,indent=2)+'\n')
    print(f'{len(packages)} package artifacts inventoried with retained notices')


if __name__ == '__main__': main()
