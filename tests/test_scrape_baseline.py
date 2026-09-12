from types import SimpleNamespace
from fgt_upgrade.scraper_requests import discover_versions
from backend.schemas import CreateJobRequest
from backend.routers.jobs import response
from backend.models import ScrapeJob
from datetime import datetime
import pytest

@pytest.mark.parametrize('include,expected', [(False,['7.4.1','7.4.2']), (True,['7.4.0','7.4.1','7.4.2'])])
def test_starting_release_included_even_when_not_in_page_catalog(include, expected):
    session=SimpleNamespace(get=lambda *a,**kw: SimpleNamespace(text='7.2.9 7.4.1 7.4.2 7.6.0'))
    assert discover_versions(session,'7.4.0','7.4.2',include_from=include)==expected

def test_baseline_not_duplicated_and_numeric_order():
    session=SimpleNamespace(get=lambda *a,**kw: SimpleNamespace(text='7.4.9 7.4.10 7.4.9 7.4.11'))
    assert discover_versions(session,'7.4.9','7.4.11',include_from=True)==['7.4.9','7.4.10','7.4.11']

@pytest.mark.parametrize('include',[False,True])
def test_selection_persists_in_request_and_response(include):
    req=CreateJobRequest(from_version='7.4.0',to_version='7.4.2',include_from=include)
    job=ScrapeJob(id='fixture',from_version=req.from_version,to_version=req.to_version,source='scrape',status='pending',use_selenium=False,created_at=datetime.utcnow(),request_json=req.model_dump_json())
    assert response(job).include_from is include
    assert CreateJobRequest.model_validate_json(job.request_json).include_from is include

def test_legacy_request_defaults_to_excluding_baseline():
    assert not CreateJobRequest(from_version='7.4.0',to_version='7.4.2').include_from
