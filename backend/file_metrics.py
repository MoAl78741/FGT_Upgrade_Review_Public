"""Per-document attempt measurements stored with existing file outcomes."""
import json
from datetime import datetime, timezone


def stamp(now=None):
    return (now or datetime.now(timezone.utc)).isoformat().replace('+00:00', 'Z')


def elapsed(start, now=None):
    if not start:
        return None
    value = datetime.fromisoformat(start.replace('Z', '+00:00'))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return round(max(0, ((now or datetime.now(timezone.utc)) - value).total_seconds()), 3)


def pending_file(value):
    return {'name': value['name'], 'status': 'pending',
            **({'page_count': value['page_count']} if value.get('page_count') is not None else {})}


def finish_files(job, status, reason, interrupted=False):
    if job.source != 'pdf':
        return
    now = datetime.now(timezone.utc)
    files = json.loads(job.file_outcomes_json or '[]')
    for item in files:
        if item.get('status') not in {'pending', 'running'}:
            continue
        if item.get('started_at'):
            if interrupted:
                # A crash has no known stop time. Retain only the last measured duration.
                item['duration_is_partial'] = True
            else:
                item['elapsed_seconds'] = elapsed(item['started_at'], now)
                item['completed_at'] = stamp(now)
        else:
            item['not_processed'] = True
        item.update(status=status, error=reason)
    job.file_outcomes_json = json.dumps(files)
