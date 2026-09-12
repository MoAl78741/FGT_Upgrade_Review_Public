"""Integration checks for chapter/category ambiguity in native PDF extraction."""
import pytest
from backend import pdf_parser


def test_limitations_issue_category_does_not_end_resolved_chapter(tmp_path, monkeypatch):
    pymupdf = pytest.importorskip('pymupdf')
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 100), 'Resolved issues', fontsize=27)
    page.insert_text((50, 160), 'Limitations', fontsize=21)
    for x in (50, 150, 550):
        page.draw_line((x, 200), (x, 250))
    for y in (200, 225, 250):
        page.draw_line((50, y), (550, y))
    for x, y, text in [(60, 217, 'Bug ID'), (160, 217, 'Description'),
                       (60, 242, '961992'), (160, 242, 'The buffer limitation is resolved.')]:
        page.insert_text((x, y), text, fontsize=10)
    page = doc.new_page()
    page.insert_text((50, 100), 'Limitations', fontsize=27)
    page.insert_text((50, 150), 'This is the actual limitations chapter.', fontsize=10)
    path = tmp_path / 'fortios-v7.2.8-release-notes.pdf'
    doc.save(path)
    doc.close()
    monkeypatch.setattr(pdf_parser, 'PYMUPDF4LLM_AVAILABLE', False)
    _, data, _, _, _ = pdf_parser.parse_pdf(path)
    assert data['resolved-issues'] == [{
        'category': 'Limitations', 'Bug ID': '961992',
        'Description': 'The buffer limitation is resolved.',
        'markdown': 'The buffer limitation is resolved.',
    }]
    assert 'actual limitations chapter' in str(data['limitations'])


def test_wrapped_comma_separated_ids_stay_with_one_description(tmp_path, monkeypatch):
    pymupdf = pytest.importorskip('pymupdf')
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 100), 'Resolved issues', fontsize=27)
    page.insert_text((50, 150), 'Proxy', fontsize=21)
    page.insert_text((50, 175), 'Issues fixed in this release.', fontsize=10)
    # The source table detector sometimes finds only the description column.
    for x in (150, 550):
        page.draw_line((x, 200), (x, 260))
    for y in (200, 225, 260):
        page.draw_line((150, y), (550, y))
    for x, y, text in [(160, 217, 'Description'), (160, 242, 'One fix addresses both bug IDs.'),
                       (60, 242, '727629,'), (60, 254, '901296')]:
        page.insert_text((x, y), text, fontsize=10)
    path = tmp_path / 'fortios-v7.2.8-release-notes.pdf'
    doc.save(path)
    doc.close()
    monkeypatch.setattr(pdf_parser, 'PYMUPDF4LLM_AVAILABLE', False)
    _, data, _, _, _ = pdf_parser.parse_pdf(path)
    assert data['resolved-issues'] == [{
        'category': 'Proxy', 'Bug ID': '727629, 901296',
        'Description': 'One fix addresses both bug IDs.',
        'markdown': 'One fix addresses both bug IDs.',
    }]
