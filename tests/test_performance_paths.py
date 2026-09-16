"""Keep optimized extraction and bounded fetching equivalent to the serial paths."""
from threading import Barrier, Lock


def test_cell_index_matches_pdfplumber_crops(tmp_path):
    from tests.pdf_factory import Document
    import pdfplumber
    from backend.pdf_parser import _CellTextIndex
    source = tmp_path / 'cells.pdf'
    doc = Document()
    page = doc.new_page()
    for y in range(40, 700, 24):
        page.insert_text((40, y), '123456 Text with spaces, punctuation and wrapped cells.')
    doc.save(source)
    doc.close()
    with pdfplumber.open(source) as pdf:
        page = pdf.pages[0]
        index = _CellTextIndex(page)
        # Full rows, partial glyphs, band boundaries, and empty areas.
        for bbox in [(30, 20, 400, 70), (45, 31, 110, 36), (30, 60, 400, 96),
                     (30, 96, 400, 300), (500, 40, 580, 200)]:
            expected = page.crop(bbox).extract_words(x_tolerance=1, y_tolerance=3, extra_attrs=['fontname'])
            assert index.words(bbox) == expected


def test_extended_sections_overlap_but_preserve_document_order(monkeypatch):
    from fgt_upgrade import scraper_full as scraper
    barrier = Barrier(4)
    lock = Lock()
    active = peak = 0
    def fetch(session, url, title):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait(timeout=10)
        with lock:
            active -= 1
        return {'title': title, 'blocks': [{'type': 'paragraph', 'text': url}]}
    monkeypatch.setattr(scraper, 'scrape_rich_section', fetch)
    toc = {f'section-{i}': {'url': f'https://example.test/{i}', 'title': f'Section {i}'} for i in range(8)}
    result = scraper.scrape_version_full(None, '7.4.11', toc)
    assert peak == 4
    assert list(result) == [*toc, '_section_urls']
    assert result['_section_urls'] == {slug: info['url'] for slug, info in toc.items()}
    for slug, info in toc.items():
        assert result[slug] == {'title': info['title'], 'blocks': [{'type': 'paragraph', 'text': info['url']}]}


def test_extended_scrape_reuses_supplied_toc(monkeypatch):
    from fgt_upgrade import scraper_full as scraper
    def unexpected(*args):
        raise AssertionError('TOC was fetched twice')
    monkeypatch.setattr(scraper, 'discover_toc', unexpected)
    monkeypatch.setattr(scraper, 'scrape_rich_section', lambda *args: {'blocks': []})
    data = scraper.scrape_all_extended(None, ['7.4.11'], {},
        tocs={'7.4.11': {'upgrade-information': {'url': 'https://example.test/upgrade', 'title': 'Upgrade'}}})
    assert data['7.4.11']['_section_urls']['upgrade-information'] == 'https://example.test/upgrade'


def test_main_sections_fetch_concurrently_and_reuse_toc(monkeypatch):
    from fgt_upgrade import scraper_requests as scraper
    from fgt_upgrade import scraper_full
    barrier = Barrier(5)
    def fetch(*args):
        barrier.wait(timeout=15)
        return [{'Bug ID': '123456', 'Feature ID': '123456', 'Description': 'Exact text.'}]
    for name in ['scrape_table', 'scrape_features', 'scrape_known_issues']:
        monkeypatch.setattr(scraper, name, fetch)
    def unexpected(*args):
        raise AssertionError('Supplied TOC should be reused')
    monkeypatch.setattr(scraper_full, 'discover_toc', unexpected)
    from fgt_upgrade.constants import PAGE_IDS
    toc = {slug: {'url': 'https://example.test/' + slug, 'title': title}
           for _, slug, title in PAGE_IDS.values()}
    result = scraper.scrape_all(None, ['7.4.11'], '7.4.11', tocs={'7.4.11': toc})
    assert list(result['7.4.11']) == ['_content_revision', 'changes_cli', 'changes_default',
                                      'changes_tablesize', 'new_features', 'known_issues']
    for key in ['changes_cli', 'changes_default', 'changes_tablesize', 'new_features', 'known_issues']:
        assert result['7.4.11'][key][0]['Description'] == 'Exact text.'


def test_extended_fetch_failure_is_not_silently_dropped(monkeypatch):
    import pytest
    from fgt_upgrade import scraper_full as scraper
    def fail(*args):
        raise RuntimeError('Source unavailable')
    monkeypatch.setattr(scraper, 'scrape_rich_section', fail)
    with pytest.raises(RuntimeError, match='Source unavailable'):
        scraper.scrape_version_full(None, '7.4.11', {
            'upgrade-information': {'url': 'https://example.test/upgrade', 'title': 'Upgrade'}})


def test_markdown_conversion_does_not_mutate_source_tree():
    from bs4 import BeautifulSoup
    from fgt_upgrade.content import source_markdown
    source = BeautifulSoup('<div><h1>Heading</h1><p>A <a href="/doc">link</a> &amp; <code>x</code>.</p><script>inert()</script></div>', 'html.parser')
    original = str(source)
    assert source_markdown(source.div, 'https://example.test') == 'A [link](https://example.test/doc) & `x`.'
    assert str(source) == original
