"""Small bounded HTTP client for local Unix sockets; no TCP or Docker SDK."""
import http.client
import json
import socket


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path, timeout=15):
        super().__init__('localhost', timeout=timeout)
        self.path = str(path)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def request(socket_path, method, path, data=None, limit=101 * 1024**2):
    connection = UnixHTTP(socket_path)
    try:
        body = json.dumps(data).encode() if data is not None else None
        connection.request(method, path, body, {'Content-Type': 'application/json'})
        response = connection.getresponse()
        content = response.read(limit + 1)
        if len(content) > limit:
            raise RuntimeError('Worker response exceeds the size limit')
        if response.status >= 400:
            raise RuntimeError(f'Worker service request failed ({response.status})')
        return json.loads(content) if content else None
    finally:
        connection.close()
