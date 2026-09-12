"""Regression checks against silent source-text and formatting loss."""
from unittest.mock import Mock
from bs4 import BeautifulSoup
from fgt_upgrade.content import source_markdown
from fgt_upgrade.scraper_requests import scrape_table, scrape_features, scrape_special_notices
from fgt_upgrade.scraper_full import scrape_rich_section
from fgt_upgrade.utils import clean_text, deduplicate


def session(html):
    return Mock(get=Mock(return_value=Mock(text=html)))


def test_full_description_survives_scrape_and_normalization():
    text = 'A complete description. ' * 100 + 'END OF SOURCE'
    rows = scrape_table(session(f'<body><table><tr><td>123</td><td><p>{text}</p><pre>config system\n    end</pre></td></tr></table></body>'), 'https://docs.fortinet.com/example')
    row = deduplicate(rows)[0]
    assert 'END OF SOURCE' in row['Description']
    assert 'config system\n    end' in row['markdown']
    assert len(clean_text(text)) > 600


def test_rich_sections_keep_short_and_repeated_blocks_and_every_table():
    html = '<body><h1>Upgrade</h1><div class="document-content"><h2>First</h2><p>Warning</p><h2>Second</h2><p>Warning</p><ol><li>First step</li><li>Second step</li></ol><table><tr><td>One</td></tr></table><table><tr><td>Two</td></tr></table></div></body>'
    result = scrape_rich_section(session(html), 'https://docs.fortinet.com/example')
    assert [b['text'] for b in result['blocks'] if b['type'] == 'paragraph'] == ['Warning', 'Warning']
    assert len([b for b in result['blocks'] if b['type'] == 'table']) == 2
    rendered_blocks = '\n'.join(b.get('markdown', '') for b in result['blocks'])
    assert any(b['type'] == 'list' and b['ordered'] and b['items'][0] == 'First step' for b in result['blocks'])
    assert rendered_blocks.count('Warning') == 2


def test_inline_formatting_links_and_nested_lists_survive():
    html = BeautifulSoup('<div><p>Set <code>foo</code> to <strong>enabled</strong>.</p><ol><li>Parent<ul><li>Child</li></ul></li></ol><a href="/doc">Reference</a></div>', 'html.parser')
    md = source_markdown(html, 'https://docs.fortinet.com/example')
    assert '`foo`' in md and '**enabled**' in md
    assert '[Reference](https://docs.fortinet.com/doc)' in md
    assert 'Parent' in md and 'Child' in md


def test_notices_keep_long_content_and_short_paragraphs():
    text = 'Notice text. ' * 150 + 'LAST WORD'
    html = f'<body><h1>Special notices</h1><h2>Warning</h2><p>{text}</p><p>Stop.</p><pre>config system\nend</pre></body>'
    notice = scrape_special_notices(session(html), 'https://docs.fortinet.com/example')[0]
    assert 'LAST WORD' in notice['content']
    assert 'Stop.' in notice['markdown']
    assert 'config system\nend' in notice['markdown']


def test_pdf_markdown_does_not_include_adjacent_notices():
    from backend.pdf_parser import _scope_markdown
    md = '# Notices\n## First notice\nFirst text.\n### Detail\nMore detail.\n## Second notice\nSecond text.'
    assert _scope_markdown(md, 'First notice', ['First notice', 'Second notice']) == 'First text.\n### Detail\nMore detail.'
    assert _scope_markdown(md, 'Missing heading', ['First notice']) is None


def test_scrape_uses_document_body_not_navigation():
    from fgt_upgrade.scraper_requests import _soup_content
    html = BeautifulSoup('<div class="document-content"><div id="mc-main-content"><p>Release content.</p></div><footer>Previous Next Legal</footer></div>', 'html.parser')
    md = source_markdown(_soup_content(html), 'https://docs.fortinet.com/example')
    assert md == 'Release content.'


def test_pdf_continuation_header_does_not_truncate_section():
    from backend.pdf_parser import _scope_markdown
    md = '## First\nFirst page.\n## First\nSecond page.\n## Second\nOther section.'
    assert _scope_markdown(md, 'First', ['First', 'Second']) == 'First page.\nSecond page.'


def test_pdf_table_and_code_cannot_be_replaced_with_plain_markdown():
    from backend.pdf_parser import _repair_split_table_columns, _markdown_preserves_structure
    blocks = [
        {'type': 'table', 'headers': ['Description'], 'rows': [['Signed.'], ['Optional.']]},
        {'type': 'paragraph', 'text': 'Option', 'bold': True},
        {'type': 'code', 'text': 'enable\ndisable'},
    ]
    fixed = _repair_split_table_columns(blocks)
    assert fixed == [{'type': 'table', 'headers': ['Option', 'Description'], 'rows': [['enable', 'Signed.'], ['disable', 'Optional.']]}]
    assert not _markdown_preserves_structure('Plain text without the table.', fixed)
    assert not _markdown_preserves_structure('config system end', [{'type':'code','text':'config system\nend'}])


def test_page_title_can_be_h2_without_being_duplicated():
    html = BeautifulSoup('<div><h2>Notice</h2><p>Body</p><h3>Detail</h3></div>', 'html.parser')
    assert source_markdown(html, 'https://example.com', title='Notice') == 'Body\n\n### Detail'


def test_pdf_code_indentation_uses_glyph_positions():
    from backend.pdf_parser import _indent_code_events
    events = [dict(is_code=True, x0=x, char_width=5, text=t) for x, t in [(50, "config system"), (70, "set enabled"), (50, "end")]]
    _indent_code_events(events)
    assert [e["code_text"] for e in events] == ["config system", "    set enabled", "end"]


def test_repeated_ids_in_different_categories_and_short_text_survive():
    from fgt_upgrade.scraper_requests import scrape_known_issues
    html = '<body><h2>System</h2><table><tr><td>123</td><td>OK</td></tr></table><h2>VPN</h2><table><tr><td>123</td><td>OK</td></tr></table></body>'
    rows = scrape_known_issues(session(html), 'https://docs.fortinet.com/example')
    assert [(r['category'], r['Description']) for r in rows] == [('System', 'OK'), ('VPN', 'OK')]
    assert deduplicate(rows + rows) == rows


def test_extended_issue_pages_preserve_short_rows_and_repeated_ids():
    from fgt_upgrade.scraper_full import scrape_issues_section
    html = '<body><h1>Resolved issues</h1><h2>System</h2><table><tr><td>123</td><td>OK</td></tr></table><h2>VPN</h2><table><tr><td>123</td><td>OK</td></tr></table></body>'
    rows = scrape_issues_section(session(html), 'https://docs.fortinet.com/example')
    assert [(r['category'], r['Description']) for r in rows] == [('System', 'OK'), ('VPN', 'OK')]


def test_pdf_ordered_lists_keep_start_number_and_restarts():
    from backend.pdf_parser import _append_numbered_item
    blocks = []
    for line in ['3. Third step', '4. Fourth step', '1. Restart']:
        _append_numbered_item(blocks, line)
    assert blocks == [
        {'type': 'list', 'ordered': True, 'start': 3, 'items': ['Third step', 'Fourth step']},
        {'type': 'list', 'ordered': True, 'start': 1, 'items': ['Restart']},
    ]


def test_child_notice_plain_text_excludes_separately_rendered_title():
    url = 'https://docs.fortinet.com/document/fortigate/7.4.11/fortios-release-notes/1/special-notices'
    index = '<body><ul><li><a href="2/notice">Notice</a></li></ul></body>'
    child = '<body><div id="mc-main-content"><h2>Notice</h2><p>Keep this content.</p><h3>Details</h3><p>Keep details.</p></div></body>'
    client = Mock(get=Mock(side_effect=[Mock(text=index), Mock(text=child)]))
    notice = scrape_special_notices(client, url)[0]
    assert notice['title'] == 'Notice'
    assert notice['content'] == 'Keep this content. Details Keep details.'
    assert notice['markdown'] == 'Keep this content.\n\n### Details\n\nKeep details.'


def test_notice_cache_skips_old_extraction_revisions():
    import json
    from types import SimpleNamespace
    from backend.scrape_worker import _load_special_notices_cache
    from fgt_upgrade.constants import CONTENT_REVISION
    def job(revision, text):
        return SimpleNamespace(all_data_json=json.dumps({'7.4.11': {'_content_revision': {'version': revision}}}), special_notices_json=json.dumps([{'title':'Notice','markdown':text}]))
    db = Mock()
    query = db.query.return_value.filter.return_value.order_by.return_value
    query.all.return_value = [job('old', 'Stale'), job(CONTENT_REVISION, 'Complete')]
    assert _load_special_notices_cache(db, '7.4.11')[0]['markdown'] == 'Complete'


def test_pdf_borderless_left_column_recovered_from_horizontal_edges():
    from types import SimpleNamespace
    from backend.pdf_parser import _complete_left_column
    rows = [SimpleNamespace(bbox=(100, y, 300, y+20), cells=[(100,y,300,y+20)]) for y in [10,30]]
    table = SimpleNamespace(bbox=(100,10,300,50),rows=rows)
    page = Mock(edges=[{'orientation':'h','x0':50,'x1':100,'top':y} for y in [10,30,50]])
    page.crop.return_value.extract_text.return_value='FortiGate'
    fixed = _complete_left_column(page,table)
    assert fixed.bbox == (50,10,300,50)
    assert fixed.rows[1].cells == [(50,30,100,50),(100,30,300,50)]
    page.crop.return_value.extract_text.return_value='Bug ID'
    assert _complete_left_column(page,table) is table


def test_pdf_table_continuations_merge_only_across_pages():
    from backend.pdf_parser import _merge_continued_tables
    def table(page, value):
        return {'type':'table','headers':['Language','GUI'],'rows':[[value,'Yes']], '_source_page':page}
    blocks = _merge_continued_tables([table(1,'English'),table(2,'French'),table(2,'German')])
    assert len(blocks)==2
    assert blocks[0]['rows']==[['English','Yes'],['French','Yes']]
    assert all('_source_page' not in b for b in blocks)


def test_pdf_link_annotations_limit_link_to_source_phrase():
    from backend.pdf_parser import _repair_link_spans
    md = '[See the compatibility guide for details.](https://example.com/guide)'
    assert _repair_link_spans(md, [('https://example.com/guide','compatibility guide')]) == 'See the [compatibility guide](https://example.com/guide) for details.'
    assert _repair_link_spans(md, [('https://other.example','compatibility guide')]) == md


def test_pdf_wrapped_identifiers_do_not_gain_spaces():
    from backend.pdf_parser import _join_cell_words
    assert _join_cell_words([{'text':'build0005_','top':10},{'text':'AU.out','top':22}]) == 'build0005_AU.out'
    assert _join_cell_words([{'text':'FG-','top':10},{'text':'1001F','top':22}]) == 'FG-1001F'
    assert _join_cell_words([{'text':'normal','top':10},{'text':'prose','top':22}]) == 'normal prose'
    assert _join_cell_words([{'text':'setting_','top':10},{'text':'description','top':10}]) == 'setting_ description'


def test_pdf_borderless_column_keeps_merged_rows():
    from types import SimpleNamespace
    from backend.pdf_parser import _complete_left_column, _table_row_spans, _markdown_preserves_structure
    rows = [SimpleNamespace(bbox=(100,y,300,y+20),cells=[(100,y,300,y+20)]) for y in [10,30,50]]
    table = SimpleNamespace(bbox=(100,10,300,70), rows=rows)
    page = Mock(edges=[{'orientation':'h','x0':50,'x1':100,'top':y} for y in [10,30,70]])
    page.crop.return_value.extract_text.return_value='FortiGate'
    fixed = _complete_left_column(page, table)
    assert fixed.rows[1].cells[0] == (50,30,100,70)
    assert fixed.rows[2].cells[0] is None
    spans = _table_row_spans(fixed)
    assert spans == [[1,1],[2,1],[0,1]]
    assert not _markdown_preserves_structure('| header | value |', [{'type':'table','rowSpans':spans}])


def test_scraped_merged_table_preserves_structure_and_inline_content():
    from fgt_upgrade.scraper_full import scrape_rich_section
    session = Mock()
    session.get.return_value.text = '''<div id="mc-main-content"><h1>Upgrade information</h1>
    <p>Keep <strong>this warning</strong> and <a href="/guide">the guide</a>.</p>
    <table><thead><tr><th>Device</th><th>Option</th></tr></thead><tbody>
    <tr><td rowspan="2">Individual devices</td><td><code>manual</code></td></tr>
    <tr><td><a href="/auto">Automatic</a></td></tr></tbody></table></div>'''
    result = scrape_rich_section(session, 'https://example.com/upgrade')
    assert 'markdown' not in result
    assert '**this warning**' in result['blocks'][0]['markdown']
    table = result['blocks'][1]
    assert table['rowSpans'] == [[2,1],[0,1]]
    assert table['rows'] == [['Individual devices','manual'],['','Automatic']]
    assert table['cellMarkdown'][1][1] == '[Automatic](https://example.com/auto)'


def test_scraped_table_cells_keep_lists_and_code_without_merged_cells():
    from fgt_upgrade.scraper_full import scrape_rich_section
    session = Mock()
    session.get.return_value.text = '''<div id="mc-main-content"><h1>Compatibility</h1>
    <table><tr><td><ul><li>First item</li><li>Second item</li></ul>
    <pre>config system\n    end</pre></td></tr></table></div>'''
    result = scrape_rich_section(session, 'https://example.com/compatibility')
    assert 'markdown' not in result
    cell = result['blocks'][0]['cellMarkdown'][0][0]
    assert '- First item\n- Second item' in cell
    assert '```\nconfig system\n    end\n```' in cell


def test_nested_table_in_numbered_step_is_not_duplicated():
    from bs4 import BeautifulSoup
    from fgt_upgrade.content import source_blocks
    tree = BeautifulSoup('<div><ol><li>Step one<table><tr><td><pre>config system\n    end</pre><ul><li>Nested item</li></ul></td></tr></table></li></ol></div>', 'html.parser')
    blocks = source_blocks(tree.div, 'https://example.com')
    step = blocks[0]['itemBlocks'][0]
    assert [b['type'] for b in step] == ['paragraph','table']
    cell = step[1]['cellBlocks'][0][0]
    assert [b['type'] for b in cell] == ['code','list']
    assert cell[0]['text'] == 'config system\n    end'
    assert cell[1]['itemBlocks'][0][0]['text'] == 'Nested item'


def test_source_nested_list_after_closed_item_keeps_its_items():
    from bs4 import BeautifulSoup
    from fgt_upgrade.content import source_blocks
    html = '<div><ul><li>Supported formats:</li><ul><li>XVA</li><li>VHD</li></ul><li>Next instruction.</li></ul></div>'
    blocks = source_blocks(BeautifulSoup(html,'html.parser').div, 'https://example.com')
    assert len(blocks[0]['itemBlocks']) == 2
    assert blocks[0]['itemBlocks'][0][1]['items'] == ['XVA','VHD']
    assert blocks[0]['itemBlocks'][1][0]['text'] == 'Next instruction.'
