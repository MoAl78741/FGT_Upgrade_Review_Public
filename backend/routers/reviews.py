"""Review workspaces reference immutable job content rather than copying it."""
import hashlib
import json
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Review
from ..security import owner, owned_job
from .. import security, team
from .jobs import response as job_response

router = APIRouter(prefix='/api/reviews', tags=['reviews'])


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=160)
    customer: str = Field(default='', max_length=160)
    site: str = Field(default='', max_length=160)
    prepared_by: str = Field(default='', max_length=160)
    summary: str = Field(default='', max_length=8000)
    rollback_notes: str = Field(default='', max_length=8000)
    range_from: str | None = Field(default=None, max_length=20)
    range_to: str | None = Field(default=None, max_length=20)
    range_include_from: bool | None = None
    expected_versions: list[str] = Field(default_factory=list, max_length=200)


class ReviewEdit(ReviewInput):
    revision: int = Field(ge=1)


class LinkInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    job_id: str = Field(max_length=36)


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    status: Literal['unreviewed', 'needs_testing', 'action_required', 'not_applicable', 'reviewed']
    note: str = Field(default='', max_length=4000)


class CheckItem(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=64)
    phase: Literal['before', 'after', 'rollback']
    text: str = Field(min_length=1, max_length=1000)
    done: bool = False


class ChecklistInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    items: list[CheckItem] = Field(max_length=100)


def owned_review(db, review_id, owner_id):
    q = db.query(Review).filter(Review.id == review_id, Review.owner_id == owner_id)
    if security.settings.public:
        q = q.filter(Review.expires_at > datetime.utcnow())
    review = q.first()
    if review is None:
        raise HTTPException(404, 'Review not found')
    return review


def metadata(review):
    fields = ['id', 'title', 'customer', 'site', 'prepared_by', 'summary', 'rollback_notes',
              'completed_at', 'revision', 'created_at', 'updated_at', 'expires_at', 'range_from', 'range_to', 'range_include_from']
    data = {field: getattr(review, field) for field in fields}
    for field in ['expected_versions', 'job_ids', 'decisions', 'checklist']:
        data[field] = json.loads(getattr(review, field + '_json'))
    return data


def content(db, review, owner_id):
    jobs, missing = [], []
    for job_id in json.loads(review.job_ids_json):
        try:
            jobs.append(owned_job(db, job_id, owner_id))
        except HTTPException as e:
            if e.status_code != 404:
                raise
            missing.append(job_id)
    return jobs, missing


def source_reference(job, version, section, row):
    if job.source == 'pdf':
        outcomes = json.loads(job.file_outcomes_json or '[]')
        manifest = json.loads(job.request_json or '{}').get('files', [])
        for index, outcome in enumerate(outcomes):
            if outcome.get('version') != version or outcome.get('status') != 'completed' or index >= len(manifest):
                continue
            pages = outcome.get('notice_pages', {}).get(row.get('title', ''), []) if section == 'special_notices' else outcome.get('section_pages', {}).get(section, [])
            # Parser pages are zero based; link to the first page of the section,
            # never claim an exact row location when only section evidence exists.
            page = min(p for p in pages if isinstance(p, int) and p >= 0) + 1 if any(isinstance(p, int) and p >= 0 for p in pages) else None
            return {'kind': 'pdf', 'url': f'/api/jobs/{job.id}/files/{index}' + (f'#page={page}' if page else ''),
                    'page': page, 'precision': 'section' if page else 'document', 'name': manifest[index]['name']}
    from urllib.parse import urlsplit
    sections = json.loads(job.all_data_json or '{}').get(version, {})
    url = sections.get('_section_urls', {}).get(section)
    if isinstance(url, str):
        parts = urlsplit(url)
        if parts.scheme == 'https' and parts.netloc == 'docs.fortinet.com':
            return {'kind': 'web', 'url': url, 'precision': 'section'}
    return None


def findings(jobs):
    result = []
    for job in jobs:
        for version, sections in json.loads(job.all_data_json or '{}').items():
            for section, value in sections.items():
                if section.startswith('_'):
                    continue
                rows = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
                for index, row in enumerate(rows):
                    if not isinstance(row, dict):
                        continue
                    description = row.get('Description') or row.get('description') or row.get('markdown') or row.get('blocks') or ''
                    if not description:
                        continue
                    # Full content identity prevents changed descriptions inheriting old decisions.
                    identity = json.dumps([job.id, version, section, index, row], sort_keys=True, ensure_ascii=False)
                    result.append({'id': hashlib.sha256(identity.encode()).hexdigest(), 'job_id': job.id,
                                   'version': version, 'section': section, 'source': row, 'reference': source_reference(job, version, section, row)})
        for index, notice in enumerate(json.loads(job.special_notices_json or '[]')):
            identity = json.dumps([job.id, 'special_notices', index, notice], sort_keys=True, ensure_ascii=False)
            result.append({'id': hashlib.sha256(identity.encode()).hexdigest(), 'job_id': job.id,
                           'version': notice.get('version') or job.to_version, 'section': 'special_notices', 'source': notice,
                           'reference': source_reference(job, notice.get('version') or job.to_version, 'special_notices', notice)})
    return result


def detail(db, review, owner_id):
    result = metadata(review)
    jobs, missing = content(db, review, owner_id)
    result['jobs'] = [job_response(job, True).model_dump() for job in jobs]
    result['unavailable_job_ids'] = missing
    result['findings'] = findings(jobs)
    captured = {v for job in jobs for v in json.loads(job.all_data_json or '{}')}
    result['missing_versions'] = [v for v in result['expected_versions'] if v not in captured]
    return result


def save(db, review, revision, **values):
    if 'completed_at' not in values: values['completed_at'] = None
    result = db.execute(update(Review).where(Review.id == review.id, Review.revision == revision)
                        .values(**values, revision=revision + 1, updated_at=datetime.utcnow()))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'This review changed in another tab. Reload before saving again.')
    team.audit(db, 'review.updated', review.id, workspace_id=review.owner_id, details={'revision': revision + 1, 'fields': sorted(values)})
    db.commit()
    db.refresh(review)


def input_values(data):
    import re
    values = data.model_dump(exclude={'revision'})
    if not values['title'].strip():
        raise HTTPException(422, 'A review title is required.')
    for key in ['range_from', 'range_to', 'range_include_from']:
        if values.get(key) is None:
            values.pop(key, None)
    if values.get('range_from') or values.get('range_to'):
        endpoints = [values.get('range_from', ''), values.get('range_to', '')]
        if any(not re.fullmatch(r'(0|[1-9]\d?)\.(0|[1-9]\d?)\.(0|[1-9]\d{0,2})', v) for v in endpoints):
            raise HTTPException(422, 'From and To versions must use major.minor.patch.')
        if tuple(map(int, endpoints[0].split('.'))) > tuple(map(int, endpoints[1].split('.'))):
            raise HTTPException(422, 'To version must not be older than From version.')
    versions = values.pop('expected_versions')
    if any(not re.fullmatch(r'(0|[1-9]\d?)\.(0|[1-9]\d?)\.(0|[1-9]\d{0,2})', v) for v in versions):
        raise HTTPException(422, 'Expected versions must use major.minor.patch.')
    values['expected_versions_json'] = json.dumps(sorted(set(versions), key=lambda v: tuple(map(int, v.split('.')))))
    return values


@router.get('')
def list_reviews(db: Session = Depends(get_db), owner_id=Depends(owner)):
    q = db.query(Review).filter(Review.owner_id == owner_id)
    if security.settings.public:
        q = q.filter(Review.expires_at > datetime.utcnow())
    return [metadata(r) for r in q.order_by(Review.updated_at.desc()).all()]


@router.post('', status_code=201)
def create_review(data: ReviewInput, db: Session = Depends(get_db), owner_id=Depends(owner)):
    if db.query(Review).filter(Review.owner_id == owner_id).count() >= 200:
        raise HTTPException(429, 'Review limit reached. Delete an unused review first.')
    review = Review(owner_id=owner_id, expires_at=datetime.utcnow() + timedelta(hours=24) if security.settings.public else None,
                    **input_values(data))
    db.add(review)
    db.flush()
    team.audit(db, 'review.created', review.id, workspace_id=owner_id)
    db.commit()
    db.refresh(review)
    return detail(db, review, owner_id)


@router.get('/{review_id}')
def get_review(review_id: str, db: Session = Depends(get_db), owner_id=Depends(owner)):
    return detail(db, owned_review(db, review_id, owner_id), owner_id)


@router.put('/{review_id}')
def edit_review(review_id: str, data: ReviewEdit, db: Session = Depends(get_db), owner_id=Depends(owner)):
    review = owned_review(db, review_id, owner_id)
    save(db, review, data.revision, **input_values(data))
    return detail(db, review, owner_id)


@router.post('/{review_id}/jobs')
def link_job(review_id: str, data: LinkInput, db: Session = Depends(get_db), owner_id=Depends(owner)):
    review = owned_review(db, review_id, owner_id)
    job = owned_job(db, data.job_id, owner_id)
    if job.status not in {'completed', 'partial'}:
        raise HTTPException(409, 'Wait for the import to finish before adding it to a review.')
    jobs, _ = content(db, review, owner_id)
    ids = json.loads(review.job_ids_json)
    if job.id in ids:
        raise HTTPException(409, 'This report is already included.')
    if len(ids) >= 50:
        raise HTTPException(422, 'A review can contain at most 50 import batches.')
    current = {v for j in jobs for v in json.loads(j.all_data_json or '{}')}
    overlap = current.intersection(json.loads(job.all_data_json or '{}'))
    if overlap:
        raise HTTPException(409, 'Versions already included: ' + ', '.join(sorted(overlap)) + '. Remove the earlier batch before replacing it.')
    save(db, review, data.revision, job_ids_json=json.dumps(ids + [job.id]))
    return detail(db, review, owner_id)


@router.delete('/{review_id}/jobs/{job_id}')
def unlink_job(review_id: str, job_id: str, revision: int, db: Session = Depends(get_db), owner_id=Depends(owner)):
    review = owned_review(db, review_id, owner_id)
    ids = json.loads(review.job_ids_json)
    if job_id not in ids:
        raise HTTPException(404, 'Batch not found')
    jobs, _ = content(db, review, owner_id)
    keep = {f['id'] for f in findings([j for j in jobs if j.id != job_id])}
    decisions = {k: v for k, v in json.loads(review.decisions_json).items() if k in keep}
    save(db, review, revision, job_ids_json=json.dumps([i for i in ids if i != job_id]), decisions_json=json.dumps(decisions))
    return detail(db, review, owner_id)


@router.put('/{review_id}/decisions/{finding_id}')
def decide(review_id: str, finding_id: str, data: DecisionInput, db: Session = Depends(get_db), owner_id=Depends(owner)):
    review = owned_review(db, review_id, owner_id)
    jobs, _ = content(db, review, owner_id)
    if finding_id not in {f['id'] for f in findings(jobs)}:
        raise HTTPException(404, 'Finding unavailable or source changed. Reload the review.')
    if data.status == 'not_applicable' and not data.note.strip():
        raise HTTPException(422, 'Explain why this finding is not applicable.')
    decisions = json.loads(review.decisions_json)
    decisions[finding_id] = data.model_dump(exclude={'revision'}) | {'updated_at': datetime.utcnow().isoformat(), 'reviewed_by': db.info.get('actor', {}).get('name')}
    save(db, review, data.revision, decisions_json=json.dumps(decisions))
    return metadata(review)


@router.put('/{review_id}/checklist')
def checklist(review_id: str, data: ChecklistInput, db: Session = Depends(get_db), owner_id=Depends(owner)):
    review = owned_review(db, review_id, owner_id)
    if len({i.id for i in data.items}) != len(data.items):
        raise HTTPException(422, 'Checklist item IDs must be unique.')
    save(db, review, data.revision, checklist_json=json.dumps([i.model_dump() for i in data.items]))
    return metadata(review)


@router.post('/{review_id}/duplicate', status_code=201)
def duplicate(review_id: str, db: Session = Depends(get_db), owner_id=Depends(owner)):
    original = owned_review(db, review_id, owner_id)
    # Reuse preparation metadata, but never carry decisions forward to a new upgrade.
    values = {key: getattr(original, key) for key in ['customer', 'site', 'prepared_by', 'summary', 'rollback_notes']}
    return create_review(ReviewInput(title=('Copy of ' + original.title)[:160], **values), db, owner_id)


@router.delete('/{review_id}', status_code=204)
def delete_review(review_id: str, db: Session = Depends(get_db), owner_id=Depends(owner)):
    db.delete(owned_review(db, review_id, owner_id))
    team.audit(db, 'review.deleted', review_id, workspace_id=owner_id)
    db.commit()


class CompletionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    completed: bool

@router.post('/{review_id}/completion')
def set_completion(review_id: str, data: CompletionInput, db: Session = Depends(get_db), owner_id=Depends(owner)):
    review=owned_review(db,review_id,owner_id)
    if data.completed and review.completed_at:
        if review.revision!=data.revision:raise HTTPException(409,'Review changed; reload before continuing.')
        return metadata(review)
    # Completion and queued notification commit together with the same revision guard.
    result=db.execute(update(Review).where(Review.id==review.id,Review.revision==data.revision).values(
        completed_at=datetime.utcnow() if data.completed else None,revision=data.revision+1,updated_at=datetime.utcnow()))
    if result.rowcount!=1:db.rollback();raise HTTPException(409,'Review changed; reload before continuing.')
    team.audit(db,'review.completed' if data.completed else 'review.reopened',review.id,workspace_id=owner_id)
    if data.completed:
        from ..notifications import notify
        notify(db,'review.completed',owner_id,review.id)
    db.commit();db.refresh(review);return metadata(review)
