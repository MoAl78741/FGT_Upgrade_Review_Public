"""
Selenium-mode scraper (opt-in via --selenium flag).

Launches Chrome via WebDriver and fetches source HTML in the browser.
Document discovery and content extraction share the requests-mode parser.

Requires: selenium>=4.0.0, Google Chrome, and a matching ChromeDriver (or Grid).
"""

import json
import time
import re

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

from .constants import LOAD_WAIT
from .utils import parse_version, version_in_range


# ── DRIVER SETUP ──────────────────────────────────────────────────────────────

def setup_driver(grid_url: str = "http://10.0.10.221:4444", headless: bool = False):
    """
    Configure Chrome WebDriver.
    Tries Selenium Grid first; falls back to a locally installed ChromeDriver.
    """
    options = Options()
    options.page_load_strategy = "eager"
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,900")

    try:
        print(f"  Connecting to Selenium Grid at {grid_url}...")
        driver = webdriver.Remote(grid_url, options=options)
        print("  ✓ Connected to Selenium Grid")
    except Exception as e:
        print(f"  Grid unavailable ({e.__class__.__name__}), falling back to local ChromeDriver")
        driver = webdriver.Chrome(options=options)
        print("  ✓ Local ChromeDriver started")

    driver.set_page_load_timeout(60)
    driver.set_script_timeout(120)
    return driver


# ── VERSION DISCOVERY ─────────────────────────────────────────────────────────

def discover_versions(driver, from_ver: str, to_ver: str, include_from: bool = False) -> list:
    """
    Navigate to the Fortinet docs page for to_ver and extract all versions
    that fall between from_ver (exclusive) and to_ver (inclusive).
    Uses four JS extraction strategies plus a page-source regex fallback.
    """
    from .scraper_full import _index_url
    start_url = _index_url(to_ver)
    print(f"  Loading: {start_url}")
    driver.get(start_url)
    time.sleep(LOAD_WAIT)

    js = """
    const results = new Set();

    // Strategy 1: <select> elements with semver-looking options
    document.querySelectorAll('select').forEach(sel => {
        [...sel.options].forEach(opt => {
            const v = (opt.value || opt.textContent).trim();
            if (/^\\d+\\.\\d+\\.\\d+$/.test(v)) results.add(v);
        });
    });

    // Strategy 2: version links in page nav / sidebar
    document.querySelectorAll('a[href*="/document/fortigate/"]').forEach(a => {
        const m = a.href.match(/\\/fortigate\\/(\\d+\\.\\d+\\.\\d+)\\//);
        if (m) results.add(m[1]);
    });

    // Strategy 3: button / list-item text matching version pattern
    document.querySelectorAll('button, li, span').forEach(el => {
        const t = el.textContent.trim();
        if (/^\\d+\\.\\d+\\.\\d+$/.test(t)) results.add(t);
    });

    // Strategy 4: data attributes
    document.querySelectorAll('[data-version], [value]').forEach(el => {
        const v = el.dataset.version || el.getAttribute('value') || '';
        if (/^\\d+\\.\\d+\\.\\d+$/.test(v.trim())) results.add(v.trim());
    });

    return JSON.stringify([...results]);
    """

    raw = driver.execute_script(js)
    all_found = json.loads(raw)

    if not all_found:
        print("  JS strategies found nothing — scanning page source...")
        matches = re.findall(r'\b(\d+\.\d+\.\d+)\b', driver.page_source)
        all_found = list(set(matches))

    valid = [v for v in all_found if re.match(r'^\d+\.\d+\.\d+$', v)]
    in_range = [v for v in valid if version_in_range(v, from_ver, to_ver)]
    in_range.sort(key=parse_version)

    if include_from and from_ver not in in_range:
        in_range.append(from_ver)
        in_range.sort(key=parse_version)
    if to_ver not in in_range:
        in_range.append(to_ver)
        in_range.sort(key=parse_version)

    print(f"  Found {len(in_range)} versions: {in_range}")
    return in_range


class _BrowserSession:
    """Use the same document discovery/parser with a browser fetch transport."""
    def __init__(self, driver):
        from threading import Lock
        self.driver, self.lock = driver, Lock()

    def get(self, url, timeout=30):
        from types import SimpleNamespace
        from urllib.parse import urlparse
        if urlparse(url).netloc != 'docs.fortinet.com':
            raise ValueError('Only Fortinet documentation can be fetched')
        with self.lock:
            result = self.driver.execute_async_script("""
                const [url, timeout, done] = arguments;
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), timeout * 1000);
                fetch(url, {signal: controller.signal}).then(async response => {
                    if (!response.ok) throw new Error('HTTP ' + response.status);
                    done({text: await response.text()});
                }).catch(error => done({error: String(error)})).finally(() => clearTimeout(timer));
            """, url, timeout)
        if not result or result.get('error'):
            raise RuntimeError(f"Could not fetch {url}: {(result or {}).get('error', 'No response')}")
        if 'Web Page Blocked!' in result['text'] or 'The URL you requested has been blocked' in result['text']:
            raise RuntimeError(f'Fortinet blocked the source page: {url}')
        return SimpleNamespace(text=result['text'])


# ── ORCHESTRATION ─────────────────────────────────────────────────────────────

def _session(driver, version):
    from .scraper_full import _index_url
    driver.get(_index_url(version))
    time.sleep(LOAD_WAIT)
    return _BrowserSession(driver)


def scrape_all(driver, versions: list, target_ver: str) -> dict:
    from .scraper_requests import scrape_all as parse_all
    return parse_all(_session(driver, target_ver), versions, target_ver)


def scrape_target_extras(driver, target_ver: str) -> list:
    from .scraper_requests import scrape_target_extras as parse_notices
    return parse_notices(_session(driver, target_ver), target_ver)
