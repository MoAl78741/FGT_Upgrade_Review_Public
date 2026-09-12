"""Offline private backup/restore and allowlisted support diagnostics.

Archives contain confidential source documents and password hashes. Store them securely.
Restore only into empty locations; existing installations are never overwritten.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import sqlite3
import tempfile
import zipfile

from .build_info import VERSION, BUILD_NUMBER, BUILD_REVISION
from .database import DB_PATH
from .settings import settings

MAX_ARCHIVE_BYTES = 4 * 1024**3
MAX_ARCHIVE_FILES = 20000


@contextmanager
def offline_lock(database):
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    with open(str(database) + '.worker.lock', 'a') as lease:
        try:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Stop the application before backup or restore. Its database is in use.') from None
        yield


def readonly(database):
    return sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def private_only():
    if settings.public:
        raise ValueError('Installation archives are available only for the private edition.')


def backup(destination, database=DB_PATH, uploads=None):
    private_only()
    database = Path(database).resolve(); uploads = Path(uploads or settings.uploads).resolve()
    destination = Path(destination).absolute()
    if destination.is_symlink(): raise ValueError('Backup destination must not be a symbolic link.')
    destination = destination.parent.resolve() / destination.name
    if destination.is_relative_to(uploads) or destination == database:
        raise ValueError('Choose a backup destination outside the database and uploads directory.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with offline_lock(database), tempfile.TemporaryDirectory(dir=destination.parent, prefix='.fgt-backup-') as temporary:
        stage = Path(temporary); snapshot = stage / 'database.sqlite'
        with readonly(database) as source, sqlite3.connect(snapshot) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise ValueError('Database integrity check failed. Keep the original installation for recovery.')
        files = {'database.sqlite': snapshot}
        if uploads.exists():
            for item in sorted(uploads.rglob('*')):
                if item.is_symlink() or (not item.is_file() and not item.is_dir()):
                    raise ValueError('Upload storage contains a link or special file; inspect it before backup.')
                if item.is_file(): files['uploads/' + item.relative_to(uploads).as_posix()] = item
        if len(files) > MAX_ARCHIVE_FILES or sum(p.stat().st_size for p in files.values()) > MAX_ARCHIVE_BYTES:
            raise ValueError('Installation exceeds the supported archive limit (4 GiB / 20,000 files).')
        manifest = {'format': 1, 'edition': 'private', 'version': VERSION, 'build': BUILD_NUMBER,
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'files': {name: {'bytes': p.stat().st_size, 'sha256': digest(p)} for name, p in files.items()}}
        created = False
        try:
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600); created = True
            with os.fdopen(fd, 'wb') as raw, zipfile.ZipFile(raw, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('manifest.json', json.dumps(manifest, sort_keys=True))
                for name, file in files.items(): archive.write(file, name)
        except BaseException:
            if created: destination.unlink(missing_ok=True)
            raise
    return {'files': len(files), 'bytes': destination.stat().st_size}


def unpack_verified(archive_path, stage):
    """Never extract arbitrary archive paths, links, or unbounded compressed content."""
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        names = [e.filename for e in entries]
        if len(entries) > MAX_ARCHIVE_FILES + 1 or len(names) != len(set(names)):
            raise ValueError('Archive has too many entries or duplicate names.')
        if sum(e.file_size for e in entries if e.filename != 'manifest.json') > MAX_ARCHIVE_BYTES:
            raise ValueError('Archive exceeds the expanded size limit.')
        info = archive.getinfo('manifest.json')
        if info.file_size > 8 * 1024**2: raise ValueError('Archive manifest is too large.')
        manifest = json.loads(archive.read(info))
        if not isinstance(manifest, dict) or manifest.get('format') != 1 or manifest.get('edition') != 'private':
            raise ValueError('Unsupported archive format or edition.')
        if int(str(manifest.get('version', '0')).split('.')[0]) > int(VERSION.split('.')[0]):
            raise ValueError('This archive requires a newer application version.')
        files = manifest.get('files')
        if not isinstance(files, dict) or 'database.sqlite' not in files or set(files) | {'manifest.json'} != set(names):
            raise ValueError('Archive contents do not match its manifest.')
        for entry in entries:
            name = entry.filename
            if name == 'manifest.json': continue
            parts = PurePosixPath(name).parts
            valid = name == 'database.sqlite' or (name.startswith('uploads/') and len(parts) >= 3)
            if not valid or '..' in parts or '\\' in name or name.startswith('/') or PurePosixPath(name).as_posix() != name:
                raise ValueError('Unsafe archive path.')
            mode = entry.external_attr >> 16
            if mode & 0o170000 not in (0, 0o100000) or entry.is_dir() or entry.flag_bits & 1:
                raise ValueError('Links, directories, special or encrypted entries are not supported.')
            expected = files[name]
            if not isinstance(expected, dict): raise ValueError('Invalid archive manifest entry.')
            if entry.file_size != expected.get('bytes'): raise ValueError('Archive size mismatch.')
            destination = Path(stage) / name; destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with archive.open(entry) as source, destination.open('xb') as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
            destination.chmod(0o600)
            if digest(destination) != expected.get('sha256'): raise ValueError('Archive checksum mismatch.')
    with readonly(Path(stage) / 'database.sqlite') as db:
        # The application uses ordinary tables and indexes only. A backup is data,
        # not permission to execute custom triggers or virtual-table extensions.
        db.execute('PRAGMA trusted_schema=OFF')
        tables = db.execute('PRAGMA table_list').fetchall()
        if not tables or any(row[2] in {'virtual', 'shadow', 'view'} for row in tables) or db.execute("select 1 from sqlite_master where type='trigger' limit 1").fetchone():
            raise ValueError('Archive contains unsupported views, triggers or virtual tables. Restore only an application database.')
        if db.execute('PRAGMA integrity_check').fetchone() != ('ok',): raise ValueError('Archive database is corrupt.')
        if not db.execute("select 1 from sqlite_master where type='table' and name='scrape_jobs'").fetchone():
            raise ValueError('Archive is not an application database.')
    return manifest


def restore(archive, database=DB_PATH, uploads=None):
    private_only()
    database = Path(database).absolute(); uploads = Path(uploads or settings.uploads).absolute()
    if database.is_relative_to(uploads): raise ValueError('Database must be outside upload storage.')
    with offline_lock(database):
        if database.exists() or database.is_symlink() or any(Path(str(database) + suffix).exists() for suffix in ['-wal', '-shm']):
            raise ValueError('Restore requires an empty database location. Preserve or move the existing installation first.')
        if uploads.is_symlink() or (uploads.exists() and (not uploads.is_dir() or any(uploads.iterdir()))):
            raise ValueError('Restore requires empty upload storage.')
        with tempfile.TemporaryDirectory(dir=database.parent, prefix='.fgt-restore-') as temporary:
            stage = Path(temporary); manifest = unpack_verified(archive, stage)
            # Restoring data must not revive old authenticated browser sessions.
            with sqlite3.connect(stage / 'database.sqlite') as db:
                tables = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
                for table in ['team_sessions', 'browser_sessions']:
                    if table in tables: db.execute(f'DELETE FROM {table}')
                if 'audit_events' in tables:
                    db.execute("insert into audit_events(actor_id,actor_name,action,target_id,details_json,created_at) values(?,?,?,?,?,?)",
                               ('local-operator', 'local-operator', 'installation.restored', 'installation', '{}', datetime.now(timezone.utc).replace(tzinfo=None).isoformat()))
            uploads.mkdir(parents=True, exist_ok=True, mode=0o700)
            created = []; database_created = False
            try:
                for item in (stage / 'uploads').iterdir() if (stage / 'uploads').exists() else []:
                    destination = uploads / item.name
                    created.append(destination); shutil.copytree(item, destination)
                # Publish database last, after verified source files are in place.
                with database.open('xb') as target:
                    database_created = True
                    with (stage / 'database.sqlite').open('rb') as source:
                        shutil.copyfileobj(source, target)
                database.chmod(0o600)
            except BaseException:
                if database_created: database.unlink(missing_ok=True)
                for item in created: shutil.rmtree(item, ignore_errors=True)
                raise
    return {'restored_files': len(manifest['files']), 'sessions_revoked': True}


def diagnostics(database=DB_PATH):
    """Explicit allowlist: no paths, hostnames, filenames, identities, text or logs."""
    report = {'format': 1, 'version': VERSION, 'build': BUILD_NUMBER, 'revision': BUILD_REVISION,
              'edition': settings.edition, 'platform': platform.system(), 'python': platform.python_version(),
              'team_auth': settings.team_auth and not settings.public, 'scraping': settings.scraping,
              'limits': {'workers': settings.workers, 'queued_jobs': settings.queue_size,
                         'files_per_job': settings.max_files, 'pages_per_file': settings.max_pages,
                         'timeout_seconds': settings.timeout}, 'database': {'available': False}}
    try:
        with readonly(database) as db:
            tables = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
            report['database'] = {'available': True, 'schema': {t: t in tables for t in ['scrape_jobs','reviews','team_users','audit_events']}}
            if 'scrape_jobs' in tables:
                statuses = ['pending','uploading','running','completed','partial','failed','cancelled']
                report['database']['jobs_by_status'] = {status: db.execute('select count(*) from scrape_jobs where status=?', (status,)).fetchone()[0] for status in statuses}
    except sqlite3.Error:
        report['database'] = {'available': False}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'restore', 'diagnostics'])
    parser.add_argument('archive', nargs='?', type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'diagnostics': result = diagnostics()
        elif not args.archive: parser.error('An archive path is required.')
        elif args.action == 'backup': result = backup(args.archive)
        else: result = restore(args.archive)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, sqlite3.Error, zipfile.BadZipFile, KeyError, TypeError) as exc:
        parser.exit(1, f'Maintenance failed: {exc}\n')


if __name__ == '__main__':
    main()
