from tests.pdf_factory import Document
from backend.pdf_heading_levels import align_heading_levels


def test_explicit_outline_levels_update_blocks_and_markdown(tmp_path):
    path = tmp_path / 'headings.pdf'
    doc = Document();doc.new_page();doc.set_toc([[1, 'Introduction', 1], [2, 'Supported models', 1], [3, 'Special branch supported models', 1]])
    doc.save(path);doc.close()
    data = {'intro': {'blocks': [{'type': 'heading', 'level': 2, 'text': 'Special branch supported models'}],
                      'markdown': '## Special branch supported models\n\nUnchanged text.'}}
    align_heading_levels(path, data)
    assert data['intro']['blocks'][0]['level'] == 3
    assert data['intro']['markdown'] == '### Special branch supported models\n\nUnchanged text.'


def test_ambiguous_or_unlisted_heading_keeps_its_existing_level(tmp_path):
    path = tmp_path / 'headings.pdf';doc = Document();doc.new_page()
    doc.set_toc([[1, 'Chapter', 1], [2, 'Details', 1], [3, 'Details', 1]])
    doc.save(path);doc.close()
    data = {'chapter': {'blocks': [{'type': 'heading', 'level': 2, 'text': 'Details'}, {'type': 'heading', 'level': 4, 'text': 'Other'}]}}
    align_heading_levels(path, data)
    assert [b['level'] for b in data['chapter']['blocks']] == [2, 4]


def test_heading_text_inside_a_code_fence_is_unchanged(tmp_path):
    path = tmp_path / 'headings.pdf';doc = Document();doc.new_page()
    doc.set_toc([[1, 'Chapter', 1], [2, 'Parent', 1], [3, 'Details', 1]])
    doc.save(path);doc.close()
    data = {'chapter': {'markdown': '## Details\n\n```\n## Details\n```\n', 'blocks': []}}
    align_heading_levels(path, data)
    assert data['chapter']['markdown'] == '### Details\n\n```\n## Details\n```\n'


def test_table_caption_keeps_its_level_when_it_repeats_a_chapter_title(tmp_path):
    path = tmp_path / 'headings.pdf';doc = Document();doc.new_page()
    doc.set_toc([[1, 'Chapter', 1], [2, 'Language support', 1]])
    doc.save(path);doc.close()
    data = {'language-support': {'blocks': [{'type': 'heading', 'level': 6, 'text': 'Language support'}], 'markdown': '###### Language support'}}
    align_heading_levels(path, data)
    assert data['language-support']['blocks'][0]['level'] == 6
    assert data['language-support']['markdown'] == '###### Language support'
