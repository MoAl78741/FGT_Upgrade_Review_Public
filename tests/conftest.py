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

# Tests must never inherit a deployment database or contact an external service.
import os, tempfile, atexit, shutil, socket, ipaddress
_suite_runtime = tempfile.TemporaryDirectory(prefix='fgt-pytest-')
atexit.register(_suite_runtime.cleanup)
for _key,_relative in [('DB_PATH','unit.db'),('UPLOADS_DIR','uploads'),('ADMIN_STATE_DIR','administration')]:
    os.environ[_key]=str(Path(_suite_runtime.name)/_relative)
os.environ.update(APP_EDITION='private',APP_ORIGIN='http://testserver',TEAM_AUTH_ENABLED='false',ENABLE_SCRAPING='false')

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
    try:
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    """Local SMTP/syslog sinks and TestClient are allowed; production/network calls fail."""
    original_connect=socket.socket.connect
    original_connect_ex=socket.socket.connect_ex
    original_sendto=socket.socket.sendto
    original_bind=socket.socket.bind
    original_dns=socket.getaddrinfo
    ports=set()
    def bind(sock,address):
        result=original_bind(sock,address)
        if isinstance(address,tuple):ports.add(sock.getsockname()[1])
        return result
    def local(address):
        if not isinstance(address,tuple):return  # Unix-domain sockets
        host=address[0]
        if host=='localhost' and address[1] in ports:return
        try:
            if ipaddress.ip_address(host).is_loopback and address[1] in ports:return
        except ValueError:pass
        raise AssertionError('External networking is forbidden in regression tests; use an isolated fixture or local sink.')
    def connect(sock,address):local(address);return original_connect(sock,address)
    def connect_ex(sock,address):local(address);return original_connect_ex(sock,address)
    def sendto(sock,data,*args):local(args[-1]);return original_sendto(sock,data,*args)
    def dns(host,port,*args,**kwargs):
        local((host,port));return original_dns(host,port,*args,**kwargs)
    monkeypatch.setattr(socket.socket,'bind',bind)
    monkeypatch.setattr(socket,'getaddrinfo',dns)
    monkeypatch.setattr(socket.socket,'connect_ex',connect_ex)
    monkeypatch.setattr(socket.socket,'connect',connect)
    monkeypatch.setattr(socket.socket,'sendto',sendto)
