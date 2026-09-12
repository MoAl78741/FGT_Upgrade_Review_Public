"""Refresh bundled release-note links at build time; never run in hosted requests."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests

SOURCE = 'https://docs.fortinet.com/document/fortigate/7.6.6/fortios-release-notes/760203/introduction-and-supported-models'
DEST = Path(__file__).resolve().parents[1] / 'frontend/src/data/pdfReleases.json'


def catalog(html):
    entries = {}
    for a in BeautifulSoup(html, 'html.parser').select('a[href]'):
        url = urljoin(SOURCE, a['href'])
        match = re.fullmatch(r'https://docs\.fortinet\.com/document/fortigate/(\d+\.\d+\.\d+)/fortios-release-notes/\d+(?:/[a-z0-9-]+)?', url)
        if match and a.get_text(strip=True) == match[1]:
            entries[match[1]] = {'version': match[1], 'url': url}
    if len(entries) < 10 or '7.6.6' not in entries:
        raise ValueError('Release selector missing or incomplete; existing catalog left unchanged.')
    return {'checked_at': datetime.now(timezone.utc).date().isoformat(), 'source': SOURCE,
            'releases': sorted(entries.values(), key=lambda e: tuple(map(int, e['version'].split('.'))))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, help='Use an already downloaded source page')
    args = parser.parse_args()
    if args.html:
        html = args.html.read_text()
    else:
        r = requests.get(SOURCE, headers={'User-Agent': 'Mozilla/5.0 (compatible; FortiGateDashboard/1.0)'}, timeout=30)
        r.raise_for_status()
        html = r.text
    data = catalog(html)
    DEST.write_text(json.dumps(data, indent=2) + '\n')
    print(f"Saved {len(data['releases'])} release links to {DEST}")
