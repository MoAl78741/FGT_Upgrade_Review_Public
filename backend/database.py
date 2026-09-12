import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

DB_PATH = Path(os.environ.get("DB_PATH", str(Path(__file__).parent.parent / "fgt_upgrade.db")))
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations() -> None:
    """
    Safe incremental migrations — adds missing columns to existing tables
    without ever dropping data.
    """
    insp = inspect(engine)
    if 'team_users' in insp.get_table_names() and 'must_change_password' not in {c['name'] for c in insp.get_columns('team_users')}:
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE team_users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT 0'))
    if 'reviews' in insp.get_table_names():
        columns = {c['name'] for c in insp.get_columns('reviews')}
        with engine.begin() as conn:
            for name, kind in [('range_from', 'VARCHAR(20)'), ('range_to', 'VARCHAR(20)'), ('range_include_from', 'BOOLEAN')]:
                if name not in columns:
                    conn.execute(text(f'ALTER TABLE reviews ADD COLUMN {name} {kind}'))
    if "scrape_jobs" not in insp.get_table_names():
        return  # Table doesn't exist yet; create_all() will handle it

    existing = {col["name"] for col in insp.get_columns("scrape_jobs")}
    pending = [
        ("grid_url", "VARCHAR(256)"),
        ("source",   "VARCHAR(20)"), ("started_at", "DATETIME"),
        ("owner_id", "VARCHAR(64)"), ("expires_at", "DATETIME"),
        ("request_json", "TEXT"), ("file_outcomes_json", "TEXT"),
        ("provenance_json", "TEXT"), ("warnings_json", "TEXT"),
    ]
    with engine.begin() as conn:
        for col_name, col_type in pending:
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE scrape_jobs ADD COLUMN {col_name} {col_type}"))

        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_owner ON scrape_jobs (owner_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_expiry ON scrape_jobs (expires_at)"))
