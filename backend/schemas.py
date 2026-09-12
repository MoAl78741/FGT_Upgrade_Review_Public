from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class CreateJobRequest(BaseModel):
    from_version: str
    to_version: str
    include_from: bool = False
    use_selenium: bool = False
    model_config = {"extra": "forbid"}
    force_rescrape: bool = False


class JobResponse(BaseModel):
    id: str
    from_version: str
    to_version: str
    status: str
    use_selenium: bool
    source: Optional[str] = "scrape"
    include_from: bool = False
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    log: Optional[str] = None
    expires_at: Optional[datetime] = None
    processing_timeout_seconds: Optional[int] = None
    file_outcomes: list[dict] = []
    warnings: list[str] = []
    provenance: dict = {}

    model_config = {"from_attributes": True}


class JobDetailResponse(JobResponse):
    versions: Optional[list] = None
    all_data: Optional[dict[str, Any]] = None
    special_notices: Optional[list] = None
