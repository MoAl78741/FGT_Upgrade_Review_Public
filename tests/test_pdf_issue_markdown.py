from backend.pdf_issue_markdown import _inline, _markdown


def line(text, y, **kwargs):
    return dict(text=text, inline=text, y=y, x=100, size=10, page=0,
                bullet=False, code=False) | kwargs


def test_lists_code_indentation_and_paragraphs_are_preserved():
    md = _markdown([
        line('Before the command:', 100),
        line('config system npu', 120, code=True),
        line('set option enable', 132, code=True, x=122),
        line('end', 144, code=True),
        line('First option', 170, bullet=True),
        line('continues on this line.', 183, x=116),
        line('Second option.', 200, bullet=True),
        line('Separate warning.', 230),
    ])
    assert '```\nconfig system npu\n    set option enable\nend\n```' in md
    assert '- First option continues on this line.\n- Second option.' in md
    assert md.endswith('\n\nSeparate warning.')


def test_inline_formatting_does_not_interpret_literal_markdown():
    md = _inline([
        {'text': 'A *literal* and ', 'font': 'Inter-Regular'},
        {'text': 'bold', 'font': 'Inter-Bold'},
        {'text': ' command ', 'font': 'Consolas'},
        {'text': '<name>', 'font': 'Inter-Regular'},
    ])
    assert r'\*literal\*' in md
    assert '**bold**' in md
    assert '` command `' in md
    assert r'\<name\>' in md


def test_native_link_annotation_preserves_label_and_destination():
    md = _inline([
        {'text': 'Read ', 'font': 'Inter-Regular', 'bbox': (0, 0, 20, 10)},
        {'text': 'the guide', 'font': 'Inter-Regular', 'bbox': (21, 0, 70, 10)},
    ], [{'from': (20, 0, 71, 11), 'uri': 'https://example.com/guide'}])
    assert md == 'Read [the guide](<https://example.com/guide>)'


def test_numbered_steps_keep_their_start_and_restart():
    md = _markdown([line('3. Third step.', 100), line('4. Fourth step.', 120),
                    line('1. Restart.', 150)])
    assert md == '3. Third step.\n4. Fourth step.\n\n1. Restart.'


def test_literal_html_entity_is_not_decoded_by_markdown():
    assert _inline([{'text': 'Network &gt; Diagnostics', 'font': 'Inter-Regular'}]) == r'Network \&gt; Diagnostics'


def test_embedded_table_preserves_cells_and_markdown():
    import pymupdf
    from backend.pdf_issue_markdown import _page_lines
    doc = pymupdf.open()
    page = doc.new_page()
    # An issue table enclosing a two-column command table.
    for x0,y0,x1,y1 in [(50,90,550,290),(130,90,130,290),(50,115,550,115),
                         (150,165,520,260),(330,165,330,260),(150,195,520,195),(150,225,520,225)]:
        if x0==x1 or y0==y1:page.draw_line((x0,y0),(x1,y1))
        else:page.draw_rect((x0,y0,x1,y1))
    for x,y,text in [(60,106,'Bug ID'),(140,106,'Description'),(60,140,'123456'),
                     (140,140,'Commands added:'),(160,183,'Command'),(340,183,'Description'),
                     (160,215,'config system test'),(340,215,'Configure test.'),
                     (160,246,'config system example'),(340,246,'Configure example.')]:
        page.insert_text((x,y),text,fontsize=10)
    lines = _page_lines(page,0,embedded_tables=True)
    tables = [line for line in lines if line.get('table_markdown')]
    assert len(tables)==1
    assert '| Command | Description |' in _markdown(tables)
    assert '| config system test | Configure test. |' in _markdown(tables)
    assert '| config system example | Configure example. |' in _markdown(tables)
    doc.close()


def test_page_number_does_not_break_cross_page_description_matching():
    import pymupdf
    from backend.pdf_issue_markdown import _page_lines
    doc=pymupdf.open();page=doc.new_page(width=612,height=792)
    page.insert_text((60,150),'1',fontsize=10)
    page.insert_text((560,750),'1',fontsize=10)
    lines=_page_lines(page,0)
    assert [line['text'] for line in lines]==['1']
    assert lines[0]['y'] < 200
    doc.close()


def test_bold_number_markers_render_as_an_ordered_list():
    from backend.pdf_issue_markdown import _markdown
    lines = [{'text': f'{i}. {text}', 'inline': f'**{i}.** {text}', 'code': False,
              'bullet': False, 'page': 0, 'y': 100 + i * 20, 'size': 10, 'x': 150}
             for i, text in [(1, 'First step'), (2, 'Second step')]]
    assert _markdown(lines) == '1. First step\n2. Second step'


def test_wrapped_hyphenated_issue_text_stays_one_word():
    assert _markdown([line('The mgmt-', 100), line('VDOM is affected.', 113)]) == 'The mgmt-VDOM is affected.'


def test_native_italic_and_bold_italic_are_preserved():
    assert _inline([{'text': 'System > FortiGuard', 'font': 'Inter-Italic'}]) == r'*System \> FortiGuard*'
    assert _inline([{'text': 'Warning', 'font': 'Inter-BoldItalic'}]) == '***Warning***'


def test_inline_code_with_prose_punctuation_is_not_a_code_block():
    import pymupdf
    from backend.pdf_issue_markdown import _page_lines
    doc = pymupdf.open();page = doc.new_page()
    page.insert_text((100, 100), 'accept', fontname='cour', fontsize=10)
    page.insert_text((136, 100), '.', fontname='helv', fontsize=10)
    lines = _page_lines(page, 0)
    assert len(lines) == 1
    assert not lines[0]['code']
    assert _markdown(lines) == '` accept `.'
    doc.close()


def test_wrapped_inline_code_does_not_expose_markdown_fences():
    md = _markdown([line('The message-', 100, inline='The ` message- `'),
                    line('authentication attribute.', 112, inline='` authentication ` attribute.')])
    assert md == 'The ` message-authentication ` attribute.'
