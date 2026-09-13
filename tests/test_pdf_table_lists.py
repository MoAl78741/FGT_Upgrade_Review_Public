from backend.pdf_table_lists import _list_blocks


def test_table_list_keeps_native_nesting_and_wrapped_lines():
    def line(text, x, bullet=True):
        return {'text': text, 'inline': text, 'x': x, 'bullet': bullet}
    blocks = _list_blocks([line('Supported platforms:', 100, False), line('Platform A', 112),
        line('Version 1', 124), line('continued', 124, False), line('Version 2', 124), line('Platform B', 112)])
    assert blocks[0]['text'] == 'Supported platforms:'
    assert blocks[1]['items'] == ['Platform A', 'Platform B']
    nested = blocks[1]['itemBlocks'][0][1]
    assert nested['items'] == ['Version 1 continued', 'Version 2']
    assert nested['itemBlocks'][0][0]['text'] == 'Version 1 continued'


def test_left_aligned_paragraph_ends_a_table_list():
    lines = [{'text': 'Chrome', 'inline': 'Chrome', 'x': 220, 'bullet': True},
             {'text': 'Other browsers are unsupported.', 'inline': 'Other browsers are unsupported.', 'x': 210, 'bullet': False}]
    blocks = _list_blocks(lines)
    assert [b['type'] for b in blocks] == ['list', 'paragraph']
    assert blocks[0]['items'] == ['Chrome']


def test_native_bookmark_includes_first_page_missing_from_legacy_tracking():
    from types import SimpleNamespace
    from backend.pdf_table_lists import _native_section_pages
    class Document:
        def get_toc(self):return [[1, 'Product integration and support', 24], [2, 'Virtualization environments', 25]]
        def __len__(self):return 50
    data = {'product-integration-and-support': {}, 'virtualization-environments': {}}
    pages = _native_section_pages(Document(), data, {'product-integration-and-support': [24]})
    assert pages['product-integration-and-support'] == [23, 24]


def test_parent_item_can_continue_after_its_nested_list():
    lines = [{'text': text, 'inline': text, 'x': x, 'bullet': bullet}
             for text, x, bullet in [('Parent', 112, True), ('Child', 124, True), ('Parent continuation', 112, False)]]
    blocks = _list_blocks(lines)
    children = blocks[0]['itemBlocks'][0]
    assert [b['type'] for b in children] == ['paragraph', 'list', 'paragraph']
    assert children[-1]['text'] == 'Parent continuation'


def test_headerless_fragments_merge_only_with_unique_consecutive_source_pages():
    from backend.pdf_table_lists import _merge_native_fragments
    from copy import deepcopy
    blocks = [{'type': 'table', 'headers': [], 'rows': [['A', 'First']]},
              {'type': 'table', 'headers': [], 'rows': [['B', 'Second']]}]
    pages = {('a', 'first'): {1}, ('b', 'second'): {2}}
    merged = _merge_native_fragments(deepcopy(blocks), pages)
    assert merged[0]['rows'] == [['A', 'First'], ['B', 'Second']]
    assert len(merged) == 1
    assert len(_merge_native_fragments(deepcopy(blocks), {('a', 'first'): {1}, ('b', 'second'): {1}})) == 2
    assert len(_merge_native_fragments(deepcopy(blocks), {('a', 'first'): {1, 3}, ('b', 'second'): {2}})) == 2


def test_plain_cell_paragraphs_preserve_native_spacing(tmp_path):
    from tests.pdf_factory import Document
    from backend.pdf_table_lists import add_table_lists
    path=tmp_path/'paragraphs.pdf';doc=Document();page=doc.new_page()
    page.draw_rect((50,90,550,220));page.draw_line((200,90),(200,220));page.draw_line((50,125),(550,125))
    page.insert_text((60,110),'System',fontsize=10);page.insert_text((210,110),'Browsers',fontsize=10)
    page.insert_text((60,145),'Platform',fontsize=10)
    for text,y in [('First browser',145),('Second browser with a',165),('wrapped description',177)]:
        page.insert_text((210,y),text,fontsize=10)
    doc.save(path);doc.close()
    table={'type':'table','headers':['System','Browsers'],'rows':[['Platform','First browser Second browser with a wrapped description']]}
    data={'support':{'blocks':[table]}}
    add_table_lists(path,data,{'support':[0]})
    assert [b['text'] for b in table['cellBlocks'][0][1]]==['First browser','Second browser with a wrapped description']


def test_issue_chapter_bounds_preceding_rich_section():
    from backend.pdf_table_lists import _native_section_pages
    class Document:
        def get_toc(self):return [[1,'SSL VPN support',32],[1,'Known issues',34],[1,'Resolved issues',50]]
        def __len__(self):return 80
    data={'ssl-vpn-support':{'blocks':[]},'known_issues':[],'resolved-issues':[]}
    pages=_native_section_pages(Document(),data,{})
    assert pages['ssl-vpn-support']==[31,32,33]
    assert 'known_issues' not in pages
