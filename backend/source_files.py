"""Resolve retained originals without trusting stored path strings."""
import json

def source_path(job, index, uploads):
    files=json.loads(job.request_json or '{}').get('files', [])
    if job.source != 'pdf' or index < 0 or index >= len(files):return None
    stored=files[index].get('stored')
    if not isinstance(stored,str):return None
    root=(uploads/job.id).resolve();path=(root/stored).resolve()
    return path if path.parent == root and path.suffix.lower() == '.pdf' and path.is_file() else None
