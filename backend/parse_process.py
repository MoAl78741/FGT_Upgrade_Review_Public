"""One PDF per isolated process; no database imports or network capability."""
import json
import os
from pathlib import Path
import resource
import sys


def main():
    source = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    # Native numerical libraries otherwise allocate one thread stack per host CPU.
    # Bound them before importing PDF dependencies, including in concurrent jobs.
    for variable in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS']:
        os.environ[variable] = '1'
    metadata_only = '--metadata-only' in sys.argv[3:]
    if not metadata_only:
        from backend.pdf_parser import parse_pdf
    import pymupdf
    from backend.parser_sandbox import confine
    root = Path(__file__).resolve().parent.parent
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024**2, 100 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    resource.setrlimit(resource.RLIMIT_CPU, (int(os.environ['JOB_TIMEOUT_SECONDS']),) * 2)
    if sys.platform == 'linux':
        resource.setrlimit(resource.RLIMIT_AS, (int(os.environ['WORKER_MEMORY_BYTES']),) * 2)
        resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))
    confine(source.parent, [Path('/usr'), Path('/lib'), Path('/lib64'), Path('/etc/fonts'),
        Path('/etc/ld.so.cache'), Path('/dev/null'), Path('/dev/urandom'),
        Path(sys.prefix), Path(sys.base_prefix), root / 'backend', root / 'fgt_upgrade'])
    page_count = None
    try:
        with pymupdf.open(source) as document:
            page_count = len(document)
            if document.needs_pass:
                raise ValueError('Encrypted PDFs are not supported; export an unencrypted release-note PDF.')
            if len(document) > int(os.environ['MAX_PDF_PAGES']):
                raise ValueError('PDF exceeds the page limit.')
        if metadata_only:
            output.write_text(json.dumps({'page_count': page_count}), encoding='utf-8')
            return
        def report_progress(phase, pages_done=0, total_pages=0):
            # Small atomic sidecar; the API polls only allowlisted progress fields.
            target = source.with_suffix('.progress.json')
            temporary = target.with_suffix('.tmp')
            temporary.write_text(json.dumps({'phase': phase, 'pages_done': pages_done, 'total_pages': page_count}))
            temporary.replace(target)
        report_progress('reading', 0, page_count)
        result = parse_pdf(str(source), progress=report_progress)
        if not result[1] and not result[2]:
            raise ValueError('No release-note sections found. Upload a FortiOS release-note PDF.')
        output.write_text(json.dumps({'result': result, 'page_count': page_count}), encoding='utf-8')
    except Exception as exc:
        # Do not return parser internals or file paths to clients.
        message = str(exc) if isinstance(exc, ValueError) else 'PDF could not be parsed. Check the document and try again.'
        output.write_text(json.dumps({'error': message, 'page_count': page_count}), encoding='utf-8')

if __name__ == '__main__':
    main()
