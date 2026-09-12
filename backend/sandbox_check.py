"""Executable isolation smoke check used inside the release image."""
import os
from pathlib import Path
import socket
import tempfile
from .parser_sandbox import confine

if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as outer:
        root = Path(outer)
        own = root / 'own'
        own.mkdir()
        other = root / 'other-secret'
        other.write_text('sentinel')
        confine(own, [Path('/usr'), Path('/lib'), Path('/lib64')])
        (own / 'result').write_text('allowed')
        for operation in [lambda: other.read_text(), lambda: other.write_text('bad'), lambda: socket.create_connection(('127.0.0.1', 9), timeout=1)]:
            try:
                operation()
            except PermissionError:
                pass
            else:
                raise AssertionError('Sandbox did not deny access')
        print('Sandbox denies network and other-job files; own-job files remain accessible.', flush=True)
        # Cleanup parent cannot run once filesystem access is confined.
        os._exit(0)
