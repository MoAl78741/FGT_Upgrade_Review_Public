#!/usr/bin/env python3
"""Verify every vendored artifact before an offline install/build."""
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'vendor/MANIFEST.json').read_text())
for name,expected in manifest['artifacts'].items():
    path=(root/name).resolve()
    if root not in path.parents:raise SystemExit('Unsafe manifest path')
    if not path.is_file():raise SystemExit(f'Missing vendored artifact: {name}')
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    if digest.hexdigest()!=expected:raise SystemExit(f'Vendored artifact checksum mismatch: {name}')
print(f"Verified {len(manifest['artifacts'])} vendored artifacts")
