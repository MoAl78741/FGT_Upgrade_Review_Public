"""Page Markdown built from pdfplumber geometry and our existing inline renderer."""
from .pdf_issue_markdown import _page_lines, _markdown, _normalized


def header_info(document):
    return {_normalized(title): min(6, level) for level, title, _ in document.get_toc()}


def page_markdown(document, number, headings=None):
    page = document[number]
    headings = headings or header_info(document)
    tables = page.find_tables().tables
    events = []
    for table in tables:
        # A nested table is already represented by its outer cell extraction.
        if any(other is not table and other.bbox != table.bbox and
               other.bbox[0] <= table.bbox[0] and other.bbox[1] <= table.bbox[1] and
               other.bbox[2] >= table.bbox[2] and other.bbox[3] >= table.bbox[3] for other in tables):
            continue
        rows = table.extract(x_tolerance=1, y_tolerance=3)
        if not rows: continue
        rendered = ['| ' + ' | '.join((c or '').replace('|', r'\|').replace('\n', '<br>') for c in row) + ' |' for row in rows]
        rendered.insert(1, '| ' + ' | '.join('---' for _ in rows[0]) + ' |')
        events.append((table.bbox[1], table.bbox[0], 'table', '\n'.join(rendered)))
    for line in _page_lines(page, number):
        if any(t.bbox[0] <= line['x'] < t.bbox[2] and t.bbox[1] <= line['y'] < t.bbox[3] for t in tables): continue
        level = headings.get(_normalized(line['text']))
        if level:
            events.append((line['y'], line['x'], 'heading', '#' * level + ' ' + line['inline']))
        else: events.append((line['y'], line['x'], 'line', line))
    result, paragraph = [], []
    for _, _, kind, value in sorted(events, key=lambda e:(e[0], e[1])):
        if kind == 'line': paragraph.append(value); continue
        if paragraph: result.append(_markdown(paragraph)); paragraph = []
        result.append(value)
    if paragraph: result.append(_markdown(paragraph))
    return '\n\n'.join(result)
