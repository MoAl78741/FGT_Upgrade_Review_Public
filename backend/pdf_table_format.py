"""Retain native CLI formatting in rich-section table cells."""
from statistics import median
from .pdf_issue_markdown import _page_lines, _markdown, _normalized


def _cell_code_markdown(lines):
    """Retain blank code lines indicated by the native baseline spacing."""
    markdown = _markdown(lines)
    parts = markdown.splitlines()
    if len(parts) != len(lines) + 2:
        return markdown
    steps = [b['y'] - a['y'] for a, b in zip(lines, lines[1:])
             if a['page'] == b['page'] and 0 < b['y'] - a['y'] < 2 * a['size']]
    if not steps:
        return markdown
    spacing = median(steps)
    body = []
    for i, text in enumerate(parts[1:-1]):
        if i and lines[i]['page'] == lines[i - 1]['page']:
            gap = lines[i]['y'] - lines[i - 1]['y']
            if gap > 1.65 * spacing:
                body.extend([''] * max(1, round(gap / spacing) - 1))
        body.append(text)
    return '\n'.join([parts[0], *body, parts[-1]])


def add_table_formatting(pdf_path, data, section_pages):
    from .pdf_document import open_document, Rect
    with open_document(pdf_path) as document:
        page_cache = {}
        for key, section in data.items():
            if not isinstance(section, dict):
                continue
            tables = [block for block in section.get('blocks', []) if block.get('type') == 'table']
            if not tables:
                continue
            candidates = {}
            for number in section_pages.get(key, []):
                if number not in page_cache:
                    page = document[number]
                    lines = _page_lines(page, number)
                    found = {}
                    for table in page.find_tables().tables:
                        for row in table.rows:
                            for cell in row.cells:
                                if cell is None:
                                    continue
                                selected = [line for line in lines if cell[0] <= line['x'] < cell[2]
                                            and cell[1] <= line['y'] < cell[3]]
                                if selected and all(line['code'] for line in selected):
                                    plain = ' '.join(line['text'] for line in selected)
                                    found[_normalized(plain)] = _cell_code_markdown(selected)
                    page_cache[number] = found
                candidates.update(page_cache[number])
            for table in tables:
                cells = [[candidates.get(_normalized(cell), "") for cell in row] for row in table['rows']]
                if not any(cell for row in cells for cell in row):
                    continue
                table['cellMarkdown'] = cells
                blocks = [[[{'type': 'code', 'text': '\n'.join(cell.splitlines()[1:-1])}] if cell else [{'type': 'paragraph', 'text': table['rows'][i][j]}] for j, cell in enumerate(row)] for i, row in enumerate(cells)]
                table['cellBlocks'] = blocks
                # Preserve the source's row boundaries, irrespective of header wording.
                section.pop('markdown', None)
