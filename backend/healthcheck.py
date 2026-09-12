"""Probe the local listener using the configured external Host allowlist."""
import json
import os
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main():
    origin = os.getenv('APP_ORIGIN', 'http://127.0.0.1:8000')
    request = Request('http://127.0.0.1:8000/api/health', headers={'Host': urlsplit(origin).netloc})
    with urlopen(request, timeout=10) as response:
        if json.load(response).get('status') != 'ok':
            raise RuntimeError('Application is not healthy')


if __name__ == '__main__':
    main()
