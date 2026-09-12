import base64
import pymupdf
from backend.pdf_callouts import add_callouts
from fgt_upgrade.content import source_table, source_markdown
from bs4 import BeautifulSoup


def test_html_note_preserves_text_and_emphasis_without_remote_icon():
    node = BeautifulSoup('<table><tr><td><img alt="Note" src="icon.png"></td><td><p>Keep <strong>all</strong> text.</p></td></tr></table>', 'html.parser').table
    block = source_table(node, 'https://example.com/')
    assert block['source_note'] and block['text'] == 'Keep all text.'
    assert block['markdown'] == '> Keep **all** text.'
    assert 'icon.png' not in source_markdown(node, 'https://example.com/')


def test_ordinary_image_table_is_not_a_note():
    node = BeautifulSoup('<table><tr><td><img alt="Diagram"></td><td>Details</td></tr></table>', 'html.parser').table
    assert source_table(node, '')['type'] == 'table'


def test_pdf_bordered_note_requires_exact_text_and_is_idempotent(tmp_path):
    path = tmp_path / 'notes.pdf'
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    pixel = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9foAAAAASUVORK5CYII=')
    page.insert_image((90, 110, 120, 140), stream=pixel)
    page.draw_line((55, 100), (555, 100))
    page.draw_line((55, 155), (555, 155))
    page.insert_text((130, 125), 'Keep all source text.', fontsize=10)
    doc.save(path)
    doc.close()
    data = {'note': {'blocks': [{'type': 'list', 'items': ['Keep all source text.']}], 'markdown': '- Keep all source text.'},
            'different': {'blocks': [{'type': 'paragraph', 'text': 'Keep some source text.'}]}}
    pages = {'note': [0], 'different': [0]}
    add_callouts(path, data, [], pages, {})
    assert data['note']['blocks'][0]['markdown'] == '> Keep all source text.'
    assert 'markdown' not in data['note']
    assert not data['different']['blocks'][0].get('source_note')
    add_callouts(path, data, [], pages, {})
    assert len(data['note']['blocks']) == 1


def test_publisher_note_table_without_icon_alt_text_is_recognized():
    node = BeautifulSoup('<table class="TableStyle-NotesTable"><tr><td><img src="Icon-Caution.png"></td><td>Retain this warning.</td></tr></table>', 'html.parser').table
    block = source_table(node, '')
    assert block['source_note']
    assert block['markdown'] == '> Retain this warning.'


def test_issue_callout_belongs_to_preceding_id_and_remains_idempotent(tmp_path):
    path = tmp_path / 'issue-note.pdf'
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((60, 85), '936747', fontsize=10)
    pixel = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9foAAAAASUVORK5CYII=')
    page.insert_image((90, 110, 120, 140), stream=pixel)
    page.draw_line((55, 100), (555, 100))
    page.draw_line((55, 155), (555, 155))
    page.insert_text((130, 125), 'Restart is required.', fontsize=10)
    page.insert_text((60, 190), '936748', fontsize=10)
    doc.save(path)
    doc.close()
    rows = [{'Bug ID': identifier, 'Description': 'Restart is required.',
             'markdown': 'Restart is required.'} for identifier in ('936747', '936748')]
    data = {'known_issues': rows}
    add_callouts(path, data, [], {}, {})
    assert rows[0]['markdown'] == '> Restart is required.'
    assert rows[1]['markdown'] == 'Restart is required.'
    add_callouts(path, data, [], {}, {})
    assert rows[0]['markdown'] == '> Restart is required.'
