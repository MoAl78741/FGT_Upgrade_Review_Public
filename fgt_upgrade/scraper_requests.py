"""
Requests-mode scraper (default) — no browser required.

Uses requests + BeautifulSoup with a ThreadPoolExecutor for parallel fetches.
All public scrape functions mirror the interface of the Selenium equivalents
so main() can call either without special-casing beyond the initial branch.
"""

import re
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests as req_lib
    from bs4 import BeautifulSoup
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from .content import source_markdown, title_key
from .constants import CONTENT_REVISION
from .utils import parse_version, version_in_range, deduplicate


# ── SESSION ──────────────────────────────────────────────────────────────────

def make_session() -> "req_lib.Session":
    session = req_lib.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; FortiGateDashboard/1.0)"})
    def check_response(response, *args, **kwargs):
        response.raise_for_status()
        if "Web Page Blocked!" in response.text or "The URL you requested has been blocked" in response.text:
            raise RuntimeError(f"Fortinet blocked the source page: {response.url}. Retry the scrape later.")
    session.hooks["response"].append(check_response)
    return session


# ── INTERNAL HELPERS ─────────────────────────────────────────────────────────

def _soup_content(soup):
    """Return .document-content if present, else body."""
    return soup.select_one("#mc-main-content") or soup.select_one(".document-content") or soup.body


def _check_title(soup, expected_title):
    """Return False if expected_title is set but the page <h1> doesn't contain it."""
    if not expected_title:
        return True
    h1 = soup.find("h1")
    def normalized(value):
        return re.sub(r"new features (?:and|or) enhancements", "new features enhancements", " ".join(value.lower().split()))
    return bool(h1 and normalized(expected_title) in normalized(h1.get_text(" ", strip=True)))


# ── VERSION DISCOVERY ─────────────────────────────────────────────────────────

def discover_versions(session, from_ver: str, to_ver: str, include_from: bool = False) -> list:
    """Discover versions from the release index without assuming a section page ID."""
    from .scraper_full import _index_url
    url = _index_url(to_ver)
    print(f"  Loading: {url}")
    resp = session.get(url, timeout=30)
    all_found = list(set(re.findall(r'\b(\d+\.\d+\.\d+)\b', resp.text)))
    valid = [v for v in all_found if re.match(r'^\d+\.\d+\.\d+$', v)]
    in_range = sorted([v for v in valid if version_in_range(v, from_ver, to_ver)], key=parse_version)
    if include_from and from_ver not in in_range:
        in_range.append(from_ver)
        in_range.sort(key=parse_version)
    if to_ver not in in_range:
        in_range.append(to_ver)
        in_range.sort(key=parse_version)
    print(f"  Found {len(in_range)} versions: {in_range}")
    return in_range


# ── SECTION SCRAPERS ─────────────────────────────────────────────────────────

def _issue_rows(content):
    """Only outer issue-table rows; embedded tables belong to their description."""
    for row in content.select("table tr"):
        table = row.find_parent("table")
        if table is not None and table.find_parent("table") is None:
            yield row


def scrape_table(session, url: str, expected_title: str = None) -> list:
    """Scrape a two-column table page (CLI / Default Behavior / Table Size)."""
    soup = BeautifulSoup(session.get(url, timeout=30).text, "html.parser")
    if not _check_title(soup, expected_title):
        return []
    content = _soup_content(soup)
    items = []
    for row in _issue_rows(content):
        cells = row.find_all("td", recursive=False)
        if len(cells) >= 2:
            id_ = cells[0].get_text(" ", strip=True)
            desc = cells[1].get_text(" ", strip=True)
            if id_ and desc:
                items.append({"Bug ID": id_, "Description": desc, "markdown": source_markdown(cells[1], url)})
    return deduplicate(items)


def scrape_features(session, url: str, expected_title: str = None) -> list:
    """Scrape new-features pages, tracking category headings."""
    soup = BeautifulSoup(session.get(url, timeout=30).text, "html.parser")
    if not _check_title(soup, expected_title):
        return []
    content = _soup_content(soup)
    items, cat = [], "General"
    for el in content.find_all(["h2", "h3", "h4", "table"]):
        if el.find_parent("table"):
            continue
        if el.name in ("h2", "h3", "h4"):
            t = el.get_text(" ", strip=True)
            if t and len(t) < 120 and not re.search(r"new features|table of contents", t, re.I):
                cat = t
        elif el.name == "table":
            for row in _issue_rows(el):
                cells = row.find_all("td", recursive=False)
                if len(cells) >= 2:
                    fid = cells[0].get_text(" ", strip=True)
                    desc = cells[1].get_text(" ", strip=True)
                    if fid and desc:
                        items.append({"category": cat, "Feature ID": fid, "Description": desc, "markdown": source_markdown(cells[1], url)})
    return deduplicate(items)


def scrape_known_issues(session, url: str, expected_title: str = None) -> list:
    """Scrape known-issues pages, tracking category headings."""
    soup = BeautifulSoup(session.get(url, timeout=30).text, "html.parser")
    if not _check_title(soup, expected_title):
        return []
    content = _soup_content(soup)
    items, cat = [], "General"
    for el in content.find_all(["h2", "h3", "h4", "table"]):
        if el.find_parent("table"):
            continue
        if el.name in ("h2", "h3", "h4"):
            t = el.get_text(" ", strip=True)
            if t and len(t) < 120 and not re.search(r"known issues", t, re.I):
                cat = t
        elif el.name == "table":
            for row in _issue_rows(el):
                cells = row.find_all("td", recursive=False)
                if len(cells) >= 2:
                    bug_id = cells[0].get_text(" ", strip=True)
                    desc = cells[1].get_text(" ", strip=True)
                    if bug_id and desc:
                        items.append({"category": cat, "Bug ID": bug_id, "Description": desc, "markdown": source_markdown(cells[1], url)})
    return deduplicate(items)


def scrape_special_notices(session, url: str) -> list:
    """Preserve complete notice content, including lists, tables and CLI blocks."""
    from urllib.parse import urlparse
    soup = BeautifulSoup(session.get(url, timeout=30).text, "html.parser")
    content = _soup_content(soup)
    if not content:
        return []
    # The index lists child pages; links embedded inside prose are references.
    prefix = urlparse(url).path.split("/fortios-release-notes")[0] + "/fortios-release-notes/"
    links = []
    linked_pages = set()
    # Some published indexes omit a child still present in their chapter TOC.
    # Limit navigation discovery to this chapter's own subtree, never siblings.
    chapter_links = []
    for anchor in soup.select("a.toc[href]"):
        if urlparse(urljoin(url, anchor["href"])).path.rstrip("/") == urlparse(url).path.rstrip("/"):
            parent = anchor.find_parent("li")
            if parent:
                for children in parent.find_all("ul", recursive=False):
                    chapter_links.extend(children.select("a[href]"))
            break
    for a in [*chapter_links, *content.select("li a[href]")]:
        link = urljoin(url, a["href"]).split("#")[0]
        parsed = urlparse(link)
        # TOC and index links may pad the same numeric document ID differently.
        page_key = re.sub(r'(/fortios-release-notes/)0+(\d+)(?=/|$)', r'\1\2', parsed.path).rstrip('/')
        if (parsed.netloc == "docs.fortinet.com" and parsed.path.startswith(prefix)
                and link != url.split("#")[0] and page_key not in linked_pages):
            links.append(link)
            linked_pages.add(page_key)
    if links:
        notices = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            pages = pool.map(lambda link: session.get(link, timeout=30).text, links)
            for link, html in zip(links, pages):
                sub = BeautifulSoup(html, "html.parser")
                body = _soup_content(sub)
                if not body:
                    continue
                heading = sub.find("h1") or sub.find("h2")
                title = heading.get_text(" ", strip=True) if heading else "Notice"
                markdown = source_markdown(body, link, title=title)
                clone = BeautifulSoup(str(body), "html.parser")
                for h in clone.select("h1"):
                    h.decompose()
                first_heading = clone.find(["h2", "h3"])
                if first_heading and title_key(first_heading.get_text(" ", strip=True)) == title_key(title):
                    first_heading.decompose()
                if markdown:
                    notices.append({"title": title, "content": clone.get_text(" ", strip=True), "markdown": markdown})
        return notices

    notices, title, fragments = [], "", []
    def flush():
        if fragments:
            fragment = BeautifulSoup("".join(fragments), "html.parser")
            markdown = source_markdown(fragment, url)
            if markdown:
                notices.append({"title": title, "content": fragment.get_text(" ", strip=True), "markdown": markdown})
    for el in content.find_all(["h2", "h3", "h4", "p", "ul", "ol", "table", "pre"]):
        if el.find_parent(["table", "ul", "ol", "pre"]):
            continue
        if el.find_parent("table"):
            continue
        if el.name in ("h2", "h3", "h4"):
            flush()
            title, fragments = el.get_text(" ", strip=True), []
        else:
            fragments.append(str(el))
    flush()
    return notices


# ── ORCHESTRATION ─────────────────────────────────────────────────────────────

def scrape_all(session, versions: list, to_ver: str, tocs=None) -> dict:
    """
    Scrape all sections (CLI, Default, Table Size, Features, Known Issues)
    for every version in parallel.  Returns all_data keyed by version.
    """
    from .scraper_full import discover_toc, resolve_section
    if tocs is None:
        tocs = {}
    missing = [v for v in versions if v not in tocs]
    with ThreadPoolExecutor(max_workers=8) as pool:
        tocs.update(zip(missing, pool.map(lambda v: discover_toc(session, v), missing)))
    all_data = {v: {"_content_revision": {"version": CONTENT_REVISION}} for v in versions}

    sections = [
        ("changes_cli", scrape_table, "Bug ID"),
        ("changes_default", scrape_table, "Bug ID"),
        ("changes_tablesize", scrape_table, "Bug ID"),
        ("new_features", scrape_features, "Feature ID"),
        ("known_issues", scrape_known_issues, "Bug ID"),
    ]
    for version in versions:
        for key, _, _ in sections:
            all_data[version][key] = []  # Keep the original display/export order.

    # A single bounded pool overlaps sections even for a one-version import;
    # the previous section-by-section barriers left most workers idle.
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {}
        for version in versions:
            for key, scrape_fn, id_key in sections:
                entry = resolve_section(tocs.get(version, {}), key)
                if entry is None:
                    continue  # Absent in this release's TOC; do not guess a page ID.
                url, title = entry['url'], entry['title']
                futures[pool.submit(scrape_fn, session, url, title)] = (version, key, id_key)
        for future in as_completed(futures):
            version, key, id_key = futures[future]
            try:
                all_data[version][key] = deduplicate(future.result(), id_key)
            except Exception as exc:
                raise RuntimeError(f"Failed to scrape {key} for {version}: {exc}") from exc

    return all_data


def scrape_target_extras(session, to_ver: str) -> list:
    """Scrape special notices for the target version only."""
    print(f"\n  Scraping special notices for {to_ver}...")
    from .scraper_full import discover_toc, resolve_section
    entry = resolve_section(discover_toc(session, to_ver), 'special_notices')
    notices = scrape_special_notices(session, entry['url']) if entry else []
    print(f"    {len(notices)} notices found")
    return notices
