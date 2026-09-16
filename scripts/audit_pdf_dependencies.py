#!/usr/bin/env python3
"""Fail closed if an installed distribution/module contains the removed engine.

Emits installed versions, declared licenses and shipped license-file paths.
Run inside the final image as well as the development environment. This is a
component inventory and engine exclusion check, not a legal opinion.
"""
import importlib.metadata as metadata
import importlib.util
import json
import re
from pathlib import Path
import sys

FORBIDDEN = re.compile(r'(^|[/_.-])(pymupdf(?:4llm|-layout)?|(?:lib)?mupdf|fitz)(?=$|[/_.-])', re.I)


def audit():
    packages, violations = [], []
    for dist in metadata.distributions():
        name = dist.metadata.get('Name', '')
        files = [str(f) for f in dist.files or []]
        if FORBIDDEN.search(name): violations.append(name)
        violations.extend(f'{name}:{f}' for f in files if FORBIDDEN.search(f))
        packages.append({'name': name, 'version': dist.version,
                         'license': dist.metadata.get('License-Expression') or dist.metadata.get('License') or
                                    '; '.join(v for v in dist.metadata.get_all('Classifier', []) if v.startswith('License ::')),
                         'license_files': [f for f in files if re.search(r'license|copyright|notice', f, re.I)]})
    for module in ('fitz', 'pymupdf', 'pymupdf4llm', 'pymupdf_layout'):
        if importlib.util.find_spec(module) is not None: violations.append(f'importable:{module}')
    for directory in {Path(dist.locate_file('')).resolve() for dist in metadata.distributions()}:
        violations.extend(str(p) for p in directory.iterdir() if FORBIDDEN.search(p.name))
    result = {'python': sys.version, 'engine_exclusion_passed': not violations,
              'violations': sorted(set(violations)), 'packages': sorted(packages, key=lambda p:p['name'].lower())}
    print(json.dumps(result, indent=2))
    return not violations


if __name__ == '__main__':
    raise SystemExit(0 if audit() else 1)
