"""Trusted, fixed-policy Docker launcher. Never expose this Unix service to users.

Only this service receives the host Docker socket. PDFs run in disposable
containers with a private staging directory, never the uploads or state volumes.
"""
import json
import os
from pathlib import Path
import re
import shutil
import socketserver
import stat
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler
from urllib.parse import quote
from .worker_transport import request

LABEL = 'io.fgt.pdf-runner'
MAX_RESULT = 100 * 1024**2


def read_file(directory, name, limit):
    """Reject symlinks, hard links, devices, oversized files and traversal."""
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,180}', name):
        raise ValueError('Invalid filename')
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
                raise ValueError('Invalid file')
            value = stream.read(limit + 1)
            if len(value) > limit:
                raise ValueError('File exceeds limit')
            return value
    finally:
        os.close(parent)


def validate(data):
    if not isinstance(data, dict) or set(data) != {'job_id', 'filename', 'timeout', 'max_pages'}:
        raise ValueError('Invalid request fields')
    if not isinstance(data['job_id'], str) or str(uuid.UUID(data['job_id'])) != data['job_id']:
        raise ValueError('Invalid job identifier')
    if not isinstance(data['filename'], str) or not re.fullmatch(r'[0-9a-f]{32}-v[A-Za-z0-9][A-Za-z0-9._-]{0,79}\.pdf', data['filename']):
        raise ValueError('Invalid stored PDF name')
    for key, maximum in [('timeout', 7200), ('max_pages', 2000)]:
        if type(data[key]) is not int or not 1 <= data[key] <= maximum:
            raise ValueError('Invalid processing limit')
    return data


def worker_spec(image, host_path, identity, run_id, data, memory):
    return {
        'Image': image, 'User': '10001:10001', 'WorkingDir': '/job',
        'Entrypoint': ['python', '-m', 'backend.parse_process'],
        'Cmd': ['/job/' + data['filename'], '/job/result.json'],
        'Healthcheck': {'Test': ['NONE']},
        'Env': ['PYTHONPATH=/app', 'PYTHONDONTWRITEBYTECODE=1',
                'FGT_CONTAINER_WORKER=1', 'HOME=/job', 'TMPDIR=/job',
                f'JOB_TIMEOUT_SECONDS={data["timeout"]}', f'MAX_PDF_PAGES={data["max_pages"]}',
                f'WORKER_MEMORY_BYTES={memory}'],
        'Labels': {LABEL: identity, 'io.fgt.pdf-run': run_id},
        'NetworkDisabled': True,
        'HostConfig': {
            'NetworkMode': 'none', 'ReadonlyRootfs': True,
            'CapDrop': ['ALL'], 'SecurityOpt': ['no-new-privileges:true'],
            'Memory': memory, 'MemorySwap': memory, 'PidsLimit': 64,
            'NanoCpus': 1000000000, 'RestartPolicy': {'Name': 'no'},
            'LogConfig': {'Type': 'none'},
            'Mounts': [{'Type': 'bind', 'Source': host_path, 'Target': '/job',
                        'ReadOnly': False, 'BindOptions': {'Propagation': 'rslave'}}],
            'Ulimits': [{'Name': 'core', 'Soft': 0, 'Hard': 0},
                        {'Name': 'nofile', 'Soft': 128, 'Hard': 128}],
        },
    }


class Runner:
    def __init__(self):
        self.identity = os.environ['RUNNER_ID']
        if not re.fullmatch(r'[a-z0-9-]{1,60}', self.identity):
            raise ValueError('Invalid runner identity')
        self.state = Path('/state')
        self.uploads = Path('/uploads')
        volume = os.environ['RUNNER_STATE_VOLUME']
        state_volume = self.docker('GET', '/volumes/' + quote(volume, safe=''))
        options = state_volume.get('Options') or {}
        if options.get('type') != 'tmpfs' or not re.search(r'(?:^|,)size=512m(?:,|$)', options.get('o', '')):
            raise ValueError('Runner state requires a size=512m tmpfs volume')
        self.host_state = state_volume['Mountpoint']
        self.image = self.docker('GET', '/images/' + quote(os.environ['RUNNER_IMAGE'], safe='') + '/json')['Id']
        self.memory = int(os.environ.get('WORKER_MEMORY_MIB', '2048')) * 1024**2
        self.maximum = int(os.environ.get('MAX_WORKERS', '2'))
        if not 256*1024**2 <= self.memory <= 8*1024**3 or not 1 <= self.maximum <= 8:
            raise ValueError('Invalid operator resource limits')
        self.lock = threading.RLock()
        self.runs = {}
        self.reset()

    def docker(self, method, path, data=None):
        return request('/var/run/docker.sock', method, '/v1.42' + path, data)

    def reset(self):
        with self.lock:
            filters = quote(json.dumps({'label': [LABEL + '=' + self.identity]}), safe='')
            for container in self.docker('GET', '/containers/json?all=1&filters=' + filters):
                self.docker('DELETE', '/containers/' + container['Id'] + '?force=true&v=true')
            for path in self.state.iterdir():
                if re.fullmatch(r'[0-9a-f]{32}', path.name) and path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
            self.runs.clear()

    def start(self, payload):
        data = validate(payload)
        with self.lock:
            # Completed results are also bounded until acknowledged/deleted.
            if len(self.runs) >= self.maximum:
                raise ValueError('Worker capacity reached')
            directory = self.uploads / data['job_id']
            pdf = read_file(directory, data['filename'], 50 * 1024**2)
            if not pdf.startswith(b'%PDF-'):
                raise ValueError('Invalid PDF')
            try:
                pack = read_file(directory, 'pack.json', 4 * 1024**2)
                if not isinstance(json.loads(pack), dict): raise ValueError('Invalid pack')
            except FileNotFoundError:
                pack = None
            key = uuid.uuid4().hex
            stage = self.state/key
            stage.mkdir(mode=0o700)
            os.chown(stage, 10001, 10001)
            container_id = None
            try:
                for name, content in [(data['filename'], pdf), ('pack.json', pack)]:
                    if content is not None:
                        (stage/name).write_bytes(content)
                        os.chown(stage/name, 10001, 10001)
                        (stage/name).chmod(0o400)
                config = worker_spec(self.image, self.host_state + '/' + key, self.identity, key, data, self.memory)
                container_id = self.docker('POST', '/containers/create', config)['Id']
                self.docker('POST', '/containers/' + container_id + '/start')
                self.runs[key] = {'container': container_id, 'deadline': time.monotonic()+data['timeout'], 'stage': stage, 'done': None,
                                  'progress': Path(data['filename']).with_suffix('.progress.json').name}
                return {'id': key}
            except BaseException:
                if container_id:
                    self.docker('DELETE', '/containers/' + container_id + '?force=true&v=true')
                shutil.rmtree(stage)
                raise

    def status(self, key):
        with self.lock:
            value = self.runs[key]
            state = self.docker('GET', '/containers/' + value['container'] + '/json')['State']
            done = not state['Running']
            if done and value['done'] is None: value['done'] = time.monotonic()
            result = {'done': done, 'exit_code': state['ExitCode'] if done else None}
            try:
                progress = json.loads(read_file(value['stage'], value['progress'], 4096))
                if (isinstance(progress, dict) and progress.get('phase') in {'reading','formatting','finalizing'}
                    and type(progress.get('pages_done')) is int and type(progress.get('total_pages')) is int
                    and 0 <= progress['pages_done'] <= progress['total_pages'] <= 2000):
                    result['progress'] = {k: progress[k] for k in ['phase','pages_done','total_pages']}
            except (OSError, ValueError): pass
            return result

    def result(self, key):
        with self.lock:
            if not self.status(key)['done']: raise ValueError('Worker is still running')
            result = json.loads(read_file(self.runs[key]['stage'], 'result.json', MAX_RESULT))
            if not isinstance(result, dict): raise ValueError('Invalid result')
            return result

    def delete(self, key):
        with self.lock:
            value = self.runs.get(key)
            if value:
                self.docker('DELETE', '/containers/' + value['container'] + '?force=true&v=true')
                shutil.rmtree(value['stage'])
                del self.runs[key]

    def reap(self):
        with self.lock:
            for key, value in list(self.runs.items()):
                # Limit aggregate writable storage too, not just each output file.
                total = 0
                for path in value['stage'].rglob('*'):
                    try:
                        total += path.lstat().st_size
                    except FileNotFoundError:
                        # Parser progress is atomically renamed while we scan.
                        # A vanished entry must not crash every active worker.
                        continue
                if time.monotonic() > value['deadline']+15 or total > 256*1024**2:
                    self.delete(key)


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def log_message(self, *args): pass  # No filenames or config in service logs.

    def handle_request(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 4096 or self.headers.get('Transfer-Encoding'):
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(length)) if length else None
            runner = self.server.runner
            if self.command == 'POST' and self.path == '/runs':
                result = runner.start(data)
            elif self.command == 'POST' and self.path == '/reset' and data == {}:
                runner.reset(); result = {'ok': True}
            elif self.command == 'GET' and self.path == '/health':
                result = {'ok': True}
            else:
                match = re.fullmatch(r'/runs/([0-9a-f]{32})(/result)?', self.path)
                if not match: raise ValueError('Unknown operation')
                key = match[1]
                if self.command == 'GET': result = runner.result(key) if match[2] else runner.status(key)
                elif self.command == 'DELETE' and not match[2]: runner.delete(key); result = {'ok': True}
                else: raise ValueError('Unknown operation')
            body = json.dumps(result).encode()
            self.send_response(200)
        except (ValueError, OSError, KeyError, RuntimeError):
            body = b'{"error":"Worker request rejected or unavailable"}'
            self.send_response(400)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = do_DELETE = handle_request


def main():
    runner = Runner()
    path = Path('/runner/runner.sock')
    path.unlink(missing_ok=True)
    # Serial requests keep the privileged control plane bounded.
    server = socketserver.UnixStreamServer(str(path), Handler)
    server.runner = runner
    os.chown(path, 10001, 10001); path.chmod(0o600)
    server.timeout = 1
    while True:
        server.handle_request()
        runner.reap()


if __name__ == '__main__':
    main()
