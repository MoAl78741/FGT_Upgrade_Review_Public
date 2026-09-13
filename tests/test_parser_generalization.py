"""Unseen titles, IDs and versions must follow source structure, not fixtures.

The 99.x versions below are synthetic labels, not claims about Fortinet releases.
"""
from types import SimpleNamespace
import pytest
from tests.pdf_factory import Document
from backend import pdf_parser
from fgt_upgrade.scraper_full import scrape_version_full
from fgt_upgrade.scraper_requests import scrape_all


@pytest.mark.parametrize('version', ['8.12.34', '99.20.123'])
@pytest.mark.parametrize('title', ['Future platform support', 'New operational constraints'])
def test_unseen_pdf_chapter_and_category_follow_outline(tmp_path, monkeypatch, version, title):
    path = tmp_path / 'unrelated-upload-name.pdf'
    doc = Document()
    page = doc.new_page()
    page.insert_text((50, 100), f'FortiOS {version}', fontsize=18)
    page.insert_text((50, 150), 'Release Notes', fontsize=12)
    page = doc.new_page()
    page.insert_text((50, 100), title, fontsize=24)
    page.insert_text((50, 150), 'A previously unseen chapter retains this sentence.', fontsize=10)
    page = doc.new_page()
    page.insert_text((50, 100), 'Resolved issues', fontsize=24)
    # A familiar chapter name at the category level must stay a category.
    page.insert_text((50, 155), 'Upgrade information', fontsize=18)
    for x in (50, 160, 550):
        page.draw_line((x, 190), (x, 250))
    for y in (190, 220, 250):
        page.draw_line((50, y), (550, y))
    for x, y, text in [(60, 210, 'Bug ID'), (170, 210, 'Description'),
                       (60, 240, '987654321'), (170, 240, 'An unseen issue description.')]:
        page.insert_text((x, y), text, fontsize=10)
    doc.set_toc([[1, title, 2], [1, 'Resolved issues', 3], [2, 'Upgrade information', 3]])
    doc.save(path); doc.close()
    monkeypatch.setattr(pdf_parser, 'RICH_MARKDOWN_ENABLED', False)
    detected, data, *_ = pdf_parser.parse_pdf(path)
    assert detected == version
    assert 'previously unseen chapter' in str(data[pdf_parser._title_to_slug(title)])
    assert data['resolved-issues'][0]['Bug ID'] == '987654321'
    assert data['resolved-issues'][0]['category'] == 'Upgrade information'


def test_bookmark_recovery_is_not_a_section_title_allowlist(tmp_path):
    path = tmp_path / 'outline.pdf'
    doc = Document()
    for _ in range(4): doc.new_page()
    doc.set_toc([[1, 'Unfamiliar chapter', 1], [2, 'Novel support matrix', 2],
                 [1, 'Known issues', 3], [2, 'Unfamiliar category', 3],
                 [1, 'Future appendix', 4]])
    doc.save(path); doc.close()
    data, pages = {}, {}
    pdf_parser._add_bookmarked_sections(path, data, pages)
    assert set(data) == {'unfamiliar-chapter', 'novel-support-matrix', 'future-appendix'}
    assert pages['novel-support-matrix'] == [1, 2]


@pytest.mark.parametrize('title', ['Virtualization environments', 'Future execution environments'])
def test_scrape_preserves_embedded_heading_without_title_specific_reparenting(title):
    html = f'<h1>Product integration and support</h1><main id="mc-main-content"><p>Introduction.</p><h2>{title}</h2><table><tr><td>Future platform</td><td>Supported</td></tr></table></main>'
    session = SimpleNamespace(get=lambda *a, **kw: SimpleNamespace(text=html))
    toc = {'product-integration-and-support': {'title': 'Product integration and support', 'url': 'https://docs.fortinet.com/example'}}
    data = scrape_version_full(session, '99.20.123', toc)
    assert set(data) == {'product-integration-and-support', '_section_urls'}
    blocks = data['product-integration-and-support']['blocks']
    assert blocks[1]['text'] == title
    assert blocks[2]['rows'] == [['Future platform', 'Supported']]


@pytest.mark.parametrize('version,page_id', [('8.12.34', '87654321'), ('99.20.123', '11112222')])
def test_scrape_discovers_new_page_ids_and_section_aliases(version, page_id):
    prefix = f'https://docs.fortinet.com/document/fortigate/{version}/fortios-release-notes'
    feature_url = f'{prefix}/{page_id}/new-features-or-enhancements'
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        if url == prefix:
            return SimpleNamespace(text=f'<a href="{feature_url}">New features or enhancements</a>')
        assert url == feature_url, 'Parser guessed a historical page ID'
        return SimpleNamespace(text='<h1>New features or enhancements</h1><main id="mc-main-content"><h2>Future category</h2><table><tr><td>99887766</td><td>A new feature.</td></tr></table></main>')
    data = scrape_all(SimpleNamespace(get=get), [version], version)
    assert data[version]['new_features'][0]['Feature ID'] == '99887766'
    assert data[version]['known_issues'] == []
    assert calls == [prefix, feature_url]


def test_selenium_uses_same_discovery_and_content_parser(monkeypatch):
    from fgt_upgrade import scraper_selenium
    version = '99.20.123'
    prefix = f'https://docs.fortinet.com/document/fortigate/{version}/fortios-release-notes'
    section = prefix + '/87654321/changes-in-cli'
    responses = {
        prefix: f'<a href="{section}">Changes in CLI</a>',
        section: '<h1>Changes in CLI</h1><main id="mc-main-content"><table><tr><td>99988776</td><td>New commands:<table><tr><td>show future</td><td>Inspect state.</td></tr></table></td></tr></table></main>',
    }
    calls = []
    class Driver:
        def get(self, url): assert url == prefix
        def execute_async_script(self, script, url, timeout):
            calls.append(url)
            return {'text': responses[url]}
    monkeypatch.setattr(scraper_selenium.time, 'sleep', lambda _: None)
    actual = scraper_selenium.scrape_all(Driver(), [version], version)
    expected = scrape_all(SimpleNamespace(get=lambda url, **kw: SimpleNamespace(text=responses[url])), [version], version)
    assert actual == expected
    assert calls == [prefix, section]
    assert len(actual[version]['changes_cli']) == 1
    assert 'show future' in actual[version]['changes_cli'][0]['markdown']


@pytest.mark.parametrize('result', [None, {'error': 'HTTP 503'}, {'text': 'Web Page Blocked!'}])
def test_browser_fetch_failures_are_explicit(result):
    from fgt_upgrade.scraper_selenium import _BrowserSession
    driver = SimpleNamespace(execute_async_script=lambda *a: result)
    with pytest.raises(RuntimeError):
        _BrowserSession(driver).get('https://docs.fortinet.com/example')


@pytest.mark.parametrize('top,height', [(80, 600), (145, 1000)])
def test_continuation_geometry_is_not_tied_to_one_page_template(tmp_path, top, height):
    from backend.pdf_table_continuations import restore_table_continuations
    path = tmp_path / 'another-layout.pdf'
    doc = Document()
    page = doc.new_page(width=650, height=height)
    page.insert_text((60, height - 100), 'Previous'); page.insert_text((240, height - 100), 'Value')
    page = doc.new_page(width=650, height=height)
    # The 145pt row is outside the former hard-coded 65..110pt window.
    for left, right in [(50, 220), (220, 600)]: page.draw_rect((left, top, right, top + 40))
    page.insert_text((60, top + 25), 'New row'); page.insert_text((240, top + 25), 'New value')
    doc.save(path); doc.close()
    table = {'type': 'table', 'headers': [], 'rows': [['Previous', 'Value']]}
    data = {'future': {'blocks': [table, {'type': 'paragraph', 'text': 'New row New value'}]}}
    restore_table_continuations(path, data, {'future': [0, 1]})
    assert table['rows'] == [['Previous', 'Value'], ['New row', 'New value']]
