"""Persisted private installation preferences and bounded per-attempt PDF limits."""
import json
from dataclasses import replace
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .models import InstallationSetting


class ProcessingInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    timeout_minutes: int = Field(ge=1, le=120)
    max_files: int = Field(ge=1, le=100)
    max_pages: int = Field(ge=1, le=2000)
    workers: int = Field(ge=1, le=8)


def effective(db, base):
    if base.public:
        return base
    row = db.get(InstallationSetting, 'processing')
    if not row:
        return base
    value = ProcessingInput.model_validate_json(row.value_json)
    return replace(base, timeout=value.timeout_minutes * 60, max_files=value.max_files,
                   max_pages=value.max_pages, workers=min(value.workers, base.workers))


def values(cfg):
    return dict(timeout_minutes=cfg.timeout // 60, max_files=cfg.max_files,
                max_pages=cfg.max_pages, workers=cfg.workers)


def snapshot(request, cfg):
    raw = request.headers.get('x-pdf-timeout-minutes')
    timeout = cfg.timeout
    if raw is not None:
        try:
            minutes = int(raw)
        except ValueError:
            raise HTTPException(422, 'PDF timeout must be a whole number of minutes.')
        if not 1 <= minutes <= cfg.timeout // 60:
            raise HTTPException(422, f'PDF timeout must be between 1 and {cfg.timeout // 60} minutes. Reload Settings for current limits.')
        timeout = minutes * 60
    return {'timeout_seconds': timeout, 'max_pages': cfg.max_pages}


def attempt(job, cfg):
    value = json.loads(job.request_json or '{}').get('processing', {})
    return replace(cfg, timeout=value.get('timeout_seconds', cfg.timeout), max_pages=value.get('max_pages', cfg.max_pages))
