import uuid

from sqlalchemy import Integer, Boolean, Column, DateTime, String, Text
from sqlalchemy.sql import func

from .database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    title = Column(String(160), nullable=True)
    from_version = Column(String(20), nullable=False)
    to_version = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    use_selenium = Column(Boolean, default=False)
    grid_url = Column(String(256), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    log = Column(Text, nullable=False, default="")

    # "scrape" (default) or "pdf"
    source = Column(String(20), nullable=True, default="scrape")

    # Populated on completion
    versions_json = Column(Text, nullable=True)
    all_data_json = Column(Text, nullable=True)
    special_notices_json = Column(Text, nullable=True)

    owner_id = Column(String(64), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    request_json = Column(Text, nullable=True)
    file_outcomes_json = Column(Text, nullable=True)
    provenance_json = Column(Text, nullable=True)
    warnings_json = Column(Text, nullable=True)


class BrowserSession(Base):
    __tablename__ = "browser_sessions"
    id = Column(String(64), primary_key=True)
    expires_at = Column(DateTime, nullable=False)


class Review(Base):
    __tablename__ = 'reviews'
    id = Column(String(36), primary_key=True, default=_new_uuid)
    owner_id = Column(String(64), nullable=False, index=True)
    title = Column(String(160), nullable=False)
    customer = Column(String(160), nullable=False, default='')
    site = Column(String(160), nullable=False, default='')
    prepared_by = Column(String(160), nullable=False, default='')
    summary = Column(Text, nullable=False, default='')
    rollback_notes = Column(Text, nullable=False, default='')
    range_from = Column(String(20), nullable=True)
    range_to = Column(String(20), nullable=True)
    range_include_from = Column(Boolean, nullable=True)
    expected_versions_json = Column(Text, nullable=False, default='[]')
    job_ids_json = Column(Text, nullable=False, default='[]')
    decisions_json = Column(Text, nullable=False, default='{}')
    checklist_json = Column(Text, nullable=False, default='[]')
    completed_at = Column(DateTime, nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())
    expires_at = Column(DateTime, nullable=True, index=True)


class TeamUser(Base):
    __tablename__ = 'team_users'
    id = Column(String(36), primary_key=True, default=_new_uuid)
    username = Column(String(80), nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    must_change_password = Column(Boolean, nullable=False, default=False, server_default='0')
    is_admin = Column(Boolean, nullable=False, default=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class Workspace(Base):
    __tablename__ = 'workspaces'
    id = Column(String(64), primary_key=True, default=_new_uuid)
    name = Column(String(160), nullable=False)
    description = Column(Text, nullable=False, default='', server_default='')
    firmware_branch = Column(String(20), nullable=False, default='', server_default='')
    state = Column(String(20), nullable=False, default='active', server_default='active')
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class WorkspaceMember(Base):
    __tablename__ = 'workspace_members'
    workspace_id = Column(String(64), primary_key=True)
    user_id = Column(String(36), primary_key=True)
    role = Column(String(20), nullable=False, default='reviewer')


class TeamSession(Base):
    __tablename__ = 'team_sessions'
    id = Column(String(64), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)
    workspace_id = Column(String(64), nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)


class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String(64), nullable=True, index=True)
    actor_id = Column(String(36), nullable=False)
    actor_name = Column(String(80), nullable=False)
    action = Column(String(80), nullable=False)
    target_id = Column(String(64), nullable=False)
    details_json = Column(Text, nullable=False, default='{}')
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class InstallationSetting(Base):
    __tablename__ = 'installation_settings'
    key = Column(String(80), primary_key=True)
    value_json = Column(Text, nullable=False)


class AccessProfile(Base):
    __tablename__ = 'access_profiles'
    id = Column(String(20), primary_key=True)
    name = Column(String(80), nullable=False, unique=True)
    permissions_json = Column(Text, nullable=False, default='[]')


class OperatorUser(Base):
    __tablename__ = 'operator_users'
    id = Column(String(36), primary_key=True, default=_new_uuid)
    username = Column(String(80), nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    must_change_password = Column(Boolean, nullable=False, default=True)


class OperatorSession(Base):
    __tablename__ = 'operator_sessions'
    id = Column(String(64), primary_key=True)
    user_id = Column(String(36), nullable=False)
    expires_at = Column(DateTime, nullable=False)


class SystemEvent(Base):
    __tablename__ = 'system_events'
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    severity = Column(String(16), nullable=False, default='info')
    action = Column(String(80), nullable=False)
    actor = Column(String(80), nullable=False, default='system')
    workspace_id = Column(String(64), nullable=True)
    target_id = Column(String(64), nullable=False, default='')
    forwarded = Column(Boolean, nullable=False, default=False)
    forward_error = Column(String(160), nullable=True)


class Delivery(Base):
    __tablename__ = 'notification_deliveries'
    id = Column(String(36), primary_key=True, default=_new_uuid)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    workspace_id = Column(String(64), nullable=True)
    subject = Column(String(160), nullable=False)
    recipients_json = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default='pending')
    error = Column(String(160), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt = Column(DateTime, nullable=False, server_default=func.now())
    schedule_id = Column(String(36), nullable=True)


class ReportSchedule(Base):
    __tablename__ = 'report_schedules'
    id = Column(String(36), primary_key=True, default=_new_uuid)
    workspace_id = Column(String(64), nullable=False)
    name = Column(String(120), nullable=False)
    recipients_json = Column(Text, nullable=False)
    interval_hours = Column(Integer, nullable=False, default=24)
    enabled = Column(Boolean, nullable=False, default=True)
    next_run = Column(DateTime, nullable=False)
