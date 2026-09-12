#!/usr/bin/env python3
"""Measure PDF imports and optionally retain complete results for parity checks.

Run with the application's environment:
  python scripts/benchmark_pdf.py --output /tmp/pdf-benchmark release-notes.pdf
Results contain source document text; keep the output directory private.
"""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdfs', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    started = time.perf_counter()
    from backend.pdf_parser import parse_pdf
    measurements = {'dependency_load_seconds': time.perf_counter() - started, 'files': []}
    for index, source in enumerate(args.pdfs, 1):
        print(f'[{index}/{len(args.pdfs)}] Parsing {source.name}', flush=True)
        started, cpu = time.perf_counter(), time.process_time()
        result = parse_pdf(source)
        metric = {'name': source.name, 'wall_seconds': time.perf_counter() - started,
                  'cpu_seconds': time.process_time() - cpu, 'version': result[0],
                  'rows': sum(len(v) for v in result[1].values() if isinstance(v, list))}
        # Index prevents duplicate input names from overwriting results.
        (args.output / f'{index}-result.json').write_text(json.dumps(result), encoding='utf-8')
        measurements['files'].append(metric)
        (args.output / 'metrics.json').write_text(json.dumps(measurements, indent=2) + '\n')
        print(json.dumps(metric), flush=True)


if __name__ == '__main__':
    main()
