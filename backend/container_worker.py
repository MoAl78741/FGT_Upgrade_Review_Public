"""Queue process interface for the operator-selected container worker service."""
import json
import os
import subprocess
import time
from .worker_transport import request


def socket_path():
    return os.environ.get('PDF_RUNNER_SOCKET', '/runner/runner.sock')


def enabled():
    mode = os.environ.get('PDF_WORKER_BACKEND', 'landlock')
    if mode not in {'landlock', 'container'}:
        raise RuntimeError('PDF_WORKER_BACKEND must be landlock or container')
    return mode == 'container'


def recover():
    if enabled():
        request(socket_path(), 'POST', '/reset', {})


class ContainerProcess:
    def __init__(self, job_id, source, output, timeout, max_pages):
        self.output = output
        self.progress = source.with_suffix('.progress.json')
        self.returncode = None
        self.run_id = request(socket_path(), 'POST', '/runs', {
            'job_id': job_id, 'filename': source.name,
            'timeout': max(1, int(timeout)), 'max_pages': max_pages,
        })['id']

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        state = request(socket_path(), 'GET', '/runs/' + self.run_id)
        if state.get('progress'):
            self.progress.write_text(json.dumps(state['progress']))
        if state['done']:
            self.returncode = state['exit_code']
            if self.returncode == 0:
                result = request(socket_path(), 'GET', '/runs/' + self.run_id + '/result')
                self.output.write_text(json.dumps(result))
        return self.returncode

    def wait(self, timeout=1):
        deadline = time.monotonic() + timeout
        while self.poll() is None:
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired('container PDF worker', timeout)
            time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        return self.returncode

    def kill(self):
        request(socket_path(), 'DELETE', '/runs/' + self.run_id)
        self.returncode = -9
