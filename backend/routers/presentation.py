"""Read-only report tools with the same ownership checks as source reports."""
from typing import Literal, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from ..database import get_db
from ..security import owner, read_owner, owned_job
from ..report_renderer import render
from .jobs import response as job_response
from .reviews import owned_review, detail

router = APIRouter(prefix='/api', tags=['report tools'])

class Coordinate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: str = Field(max_length=20)
    section: str = Field(max_length=200)
    index: int = Field(ge=0)

class ReportOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sections: list[str] = Field(default_factory=list, max_length=200, description='Source section keys; empty means all. Obtain keys from the view response.')
    versions: list[str] = Field(default_factory=list, max_length=200)
    search: str = Field(default='', max_length=1000)
    category: str = Field(default='', max_length=200)
    consolidate: list[str] = Field(default_factory=list, max_length=200, description='Consolidate exact duplicates only in these source sections. Default off.')
    consolidate_all: bool = False
    selection: list[Coordinate] | None = Field(default=None, max_length=1000, description='Optional original source coordinates from view entries. Null selects all matching content; [] selects none.')

class ViewOptions(ReportOptions):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=1000, ge=1, le=5000)

class ExportOptions(ReportOptions):
    format: Literal['html','json','csv','txt'] = 'html'


class ViewEntry(BaseModel):
    section: str
    builds: list[str]
    source: dict[str, Any]
    selection: list[Coordinate]

class ViewResponse(BaseModel):
    job_id: str
    source_count: int
    count: int
    sections: list[str]
    entries: list[ViewEntry]


def job_data(db, job_id, owner_id, options=None):
    job = job_response(owned_job(db, job_id, owner_id), True).model_dump()
    if options:
        versions = job['versions'] or []
        sections = {'special_notices'} | {key for data in (job['all_data'] or {}).values() for key in data if not key.startswith('_')}
        if set(options.versions) - set(versions) or (set(options.sections) | set(options.consolidate)) - sections:
            raise HTTPException(422, 'Unknown report version or section.')
        for c in options.selection or []:
            if c.section == 'special_notices':
                rows = job['special_notices'] or []
                if c.index >= len(rows) or c.version != (rows[c.index].get('version') or ''):
                    raise HTTPException(422, 'Unknown source selection.')
            else:
                value = (job['all_data'] or {}).get(c.version, {}).get(c.section)
                if value is None or c.section.startswith('_') or c.index >= (len(value) if isinstance(value,list) else 1):
                    raise HTTPException(422, 'Unknown source selection.')
    return job

@router.get('/releases', summary='List the PDF catalog or find download links for a version range')
def releases(from_version: str | None = Query(None, max_length=20), to_version: str | None = Query(None, max_length=20), include_from: bool = False):
    if bool(from_version) != bool(to_version):
        raise HTTPException(422, 'Provide both From and To, or neither for the complete catalog.')
    return render({'operation':'releases', 'from':from_version, 'to':to_version, 'include_from':include_from})

@router.post('/jobs/{job_id}/view', summary='Search, filter, select and optionally consolidate source entries', response_model=ViewResponse)
def view_report(job_id: str, options: ViewOptions, db: Session = Depends(get_db), owner_id=Depends(read_owner)):
    job = job_data(db, job_id, owner_id, options)
    return render({'operation':'view','job':job, 'options':options.model_dump(), 'offset':options.offset, 'limit':options.limit})

@router.get('/jobs/{job_id}/compare', summary='Compare release-note feature descriptions between two versions')
def compare_report(job_id: str, from_version: str, to_version: str, db: Session = Depends(get_db), owner_id=Depends(owner)):
    job = job_data(db, job_id, owner_id)
    if from_version not in job['versions'] or to_version not in job['versions']:
        raise HTTPException(422, 'Choose versions present in this report.')
    return render({'operation':'compare','job':job,'from':from_version,'to':to_version})

@router.post('/jobs/{job_id}/export', summary='Export a filtered report using the GUI renderer', responses={200: {'description':'Self-contained HTML, JSON view, CSV or tab-separated TXT.', 'content': {mime:{'schema':{'type':'object' if mime == 'application/json' else 'string'}} for mime in ['application/json','text/html','text/csv','text/plain']}}})
def export_report(job_id: str, options: ExportOptions, db: Session = Depends(get_db), owner_id=Depends(read_owner)):
    job = job_data(db, job_id, owner_id, options)
    result = render({'operation':'view' if options.format == 'json' else options.format, 'job':job, 'options':options.model_dump()})
    if options.format == 'json':
        return result
    mime = {'html':'text/html', 'csv':'text/csv', 'txt':'text/plain'}[options.format]
    return Response(result, media_type=mime, headers={'Content-Disposition':f'attachment; filename="release-note-report.{options.format}"'})

@router.get('/reviews/{review_id}/export', summary='Download the saved review package as print-ready HTML', response_class=Response, responses={200:{'content':{'text/html':{'schema':{'type':'string'}}}}})
def export_review(review_id: str, db: Session = Depends(get_db), owner_id=Depends(owner)):
    review = detail(db, owned_review(db, review_id, owner_id), owner_id)
    result = render({'operation':'review','review':review})
    return Response(result, media_type='text/html', headers={'Content-Disposition':'attachment; filename="upgrade-review.html"'})
