"""Deployment policy: fail closed for hosted operation."""
import os
from pathlib import Path
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    team_auth: bool = os.getenv('TEAM_AUTH_ENABLED', 'false').lower() == 'true'
    source_code_url: str = os.getenv('SOURCE_CODE_URL', 'https://github.com/MoAl78741/FGT_Upgrade_Review_Public')
    edition: str = os.getenv('APP_EDITION', 'private')
    origin: str = os.getenv('APP_ORIGIN', 'http://127.0.0.1:8000').rstrip('/')
    scrape_enabled: bool = os.getenv('ENABLE_SCRAPING', 'false').lower() == 'true'
    grid_url: str | None = os.getenv('SELENIUM_GRID_URL')
    uploads: Path = Path(os.getenv('UPLOADS_DIR', 'uploads')).resolve()
    max_files: int = int(os.getenv('MAX_PDF_FILES', '100' if os.getenv('APP_EDITION', 'private') == 'public' else '4'))
    file_bytes: int = int(os.getenv('MAX_PDF_MIB', '50')) * 1024**2
    total_bytes: int = int(os.getenv('MAX_UPLOAD_MIB', '150')) * 1024**2
    max_pages: int = int(os.getenv('MAX_PDF_PAGES', '500'))
    timeout: int = int(os.getenv('JOB_TIMEOUT_SECONDS', '1800'))
    workers: int = int(os.getenv('MAX_WORKERS', '2'))
    queue_size: int = int(os.getenv('MAX_QUEUED_JOBS', '10'))
    storage_bytes: int = int(os.getenv('MAX_STORAGE_MIB', '2048')) * 1024**2
    memory_bytes: int = int(os.getenv('WORKER_MEMORY_MIB', '2048')) * 1024**2

    @property
    def public(self):
        return self.edition == 'public'

    @property
    def scraping(self):
        return not self.public and self.scrape_enabled

    @property
    def origins(self):
        if self.public or (self.team_auth and self.origin.startswith('https://')):
            return {self.origin}
        return {self.origin, 'http://localhost:5173', 'http://127.0.0.1:5173',
                'http://localhost:8000', 'http://127.0.0.1:8000'}

settings = Settings()
if settings.edition not in {'public', 'private'}:
    raise RuntimeError('APP_EDITION must be public or private')
if settings.public and not settings.origin.startswith('https://'):
    raise RuntimeError('Public edition requires an HTTPS APP_ORIGIN')
