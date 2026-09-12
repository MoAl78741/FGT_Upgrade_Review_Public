"""
Shared pytest fixtures.

The `client` fixture spins up a FastAPI TestClient backed by an in-memory
SQLite database, overriding the normal get_db dependency.  No live server
or network connection is required.
"""

import sys
from pathlib import Path

# Ensure the project root is on the path so backend/ and fgt_upgrade/ are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.database import get_db
from backend import models


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """
    FastAPI TestClient with an isolated in-memory SQLite database.
    Each test function gets a fresh, empty database.
    """
    from backend import queue, security
    from backend.routers import jobs
    from dataclasses import replace
    cfg = replace(security.settings, edition='private', origin='http://testserver', scrape_enabled=True, uploads=tmp_path)
    for module in [queue, security, jobs]:
        monkeypatch.setattr(module, 'settings', cfg)
    monkeypatch.setattr(queue, 'start', lambda: None)
    monkeypatch.setattr(queue, 'stop', lambda: None)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
