"""Recover single-row page continuations using their drawn cell borders."""
from .pdf_issue_markdown import _page_lines, _normalized
from .pdf_table_lists import _list_blocks, _native_section_pages


def _single_rows(page, number):
    groups = {}
    for drawing in page.get_drawings():
        rect = drawing['rect']
        # Continuations start near the top of a page. Scale the search window
        # with the page rather than assuming one PDF's Letter/A4 coordinates.
        if not (0 < rect.y0 < page.rect.height * .25
                and 0 < rect.height < page.rect.height * .25
                and rect.width > page.rect.width * .025):
            continue
        horizontal = []
        for item in drawing['items']:
            if item[0] == 're' and tuple(item[1]) == tuple(rect):
                horizontal.extend([rect.y0, rect.y1])
            if item[0] == 'l':
                a, b = item[1:3]
                if abs(a.y - b.y) < .5 and abs(abs(a.x - b.x) - rect.width) < 1:
                    horizontal.append(a.y)
        if not (any(abs(y - rect.y0) < .5 for y in horizontal)
                and any(abs(y - rect.y1) < .5 for y in horizontal)):
            continue
        groups.setdefault((round(rect.y0, 1), round(rect.y1, 1)), []).append(rect)
    if not groups:
        return
    lines = _page_lines(page, number)
    for rects in groups.values():
        rects = sorted({tuple(rect): rect for rect in rects}.values(), key=lambda rect: rect.x0)
        if len(rects) < 2 or any(abs(a.x1 - b.x0) > 1 for a, b in zip(rects, rects[1:])):
            continue
        cells = [[line for line in lines if rect.x0 <= line['x'] < rect.x1
                  and rect.y0 <= line['y'] < rect.y1] for rect in rects]
        if all(cells):
            yield cells


def restore_table_continuations(pdf_path, data, section_pages):
    import pymupdf
    with pymupdf.open(pdf_path) as doc:
        pages = _native_section_pages(doc, data, section_pages)
        cache = {}
        previous_cache = {}
        for key, section in data.items():
            if not isinstance(section, dict) or not section.get('blocks'):
                continue
            blocks = section['blocks']
            if not any(block.get('type') == 'table' for block in blocks):
                continue
            candidates = []
            for number in pages.get(key, []):
                if number not in cache:
                    cache[number] = list(_single_rows(doc[number], number))
                candidates.extend((number, cells) for cells in cache[number] if number > 0)
            index = 0
            while index < len(blocks):
                table = blocks[index]
                index += 1
                if table.get('type') != 'table' or not table.get('rows'):
                    continue
                for number, cells in candidates:
                    if len(cells) != len(table['rows'][-1]):
                        continue
                    if number not in previous_cache:
                        previous = doc[number - 1]
                        previous_cache[number] = _normalized(' '.join(line['text'] for line in _page_lines(previous, number - 1)
                                                                      if line['y'] > previous.rect.height / 2))
                    previous_text = previous_cache[number]
                    if _normalized(' '.join(table['rows'][-1])) not in previous_text:
                        continue
                    values = [' '.join(line['text'] for line in cell) for cell in cells]
                    wanted = _normalized(' '.join(values))
                    collected = ''
                    end = index
                    while end < len(blocks) and blocks[end].get('type') in {'paragraph', 'list'}:
                        block = blocks[end]
                        text = ' '.join(block.get('items', [])) if block['type'] == 'list' else block.get('text', '')
                        collected += _normalized(text)
                        end += 1
                        if collected == wanted:
                            count = len(table['rows'])
                            table['rows'].append(values)
                            for field, default in [('cellMarkdown', ''), ('rowSpans', 1), ('colSpans', 1)]:
                                if field in table:
                                    table[field].append([default] * len(cells))
                            if 'cellBlocks' not in table:
                                table['cellBlocks'] = [[[{'type': 'paragraph', 'text': value}] for value in row]
                                                       for row in table['rows'][:count]]
                            table['cellBlocks'].append([_list_blocks(cell) for cell in cells])
                            del blocks[index:end]
                            section.pop('markdown', None)
                            break
                        if not wanted.startswith(collected):
                            break
