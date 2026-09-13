"""Recover native bullet structure in rich table cells using exact text matches."""
import re
from .pdf_issue_markdown import _page_lines, _normalized


def _list_blocks(lines):
    blocks = []
    stack = []
    previous = None
    for line in lines:
        text, markdown = line['text'], line['inline']
        if not line['bullet']:
            while stack and line['x'] < stack[-1][0] - 4:
                stack.pop()
        if line['bullet']:
            x = line['x']
            while stack and x < stack[-1][0] - 4:
                stack.pop()
            if not stack or x > stack[-1][0] + 8:
                target = stack[-1][1]['itemBlocks'][-1] if stack else blocks
                node = {'type': 'list', 'ordered': False, 'items': [], 'itemBlocks': []}
                target.append(node)
                stack.append((x, node))
            node = stack[-1][1]
            node['items'].append(text)
            node['itemBlocks'].append([{'type': 'paragraph', 'text': text, 'markdown': markdown}])
        elif stack:
            node = stack[-1][1]
            node['items'][-1] += ' ' + text
            paragraph = node['itemBlocks'][-1][-1]
            if paragraph['type'] == 'paragraph':
                paragraph['text'] += ' ' + text
                paragraph['markdown'] += ' ' + markdown
            else:
                node['itemBlocks'][-1].append({'type': 'paragraph', 'text': text, 'markdown': markdown})
        elif (blocks and blocks[-1]['type'] == 'paragraph'
              and (not previous or 'y' not in line
                   or line['y'] - previous['y'] <= 1.4 * line['size'])):
            blocks[-1]['text'] += ' ' + text
            blocks[-1]['markdown'] += ' ' + markdown
        else:
            blocks.append({'type': 'paragraph', 'text': text, 'markdown': markdown})
        previous = line
    return blocks


def _native_section_pages(document, data, fallback):
    from .pdf_parser import _title_to_slug, _match_section
    entries = []
    for _, title, page in document.get_toc():
        key = _match_section(title) or _title_to_slug(title)
        if key in data and isinstance(data[key], (dict, list)):
            entries.append((key, page - 1))
    pages = dict(fallback)
    for index, (key, start) in enumerate(entries):
        if not isinstance(data[key], dict):
            continue
        end = entries[index + 1][1] + 1 if index + 1 < len(entries) else len(document)
        pages[key] = list(range(start, min(end, len(document))))
    return pages


def _merge_native_fragments(blocks, row_pages):
    result = []
    for block in blocks:
        previous = result[-1] if result else None
        merge = False
        if (previous and previous.get('type') == block.get('type') == 'table'
                and not previous.get('headers') and not block.get('headers')
                and previous.get('rows') and block.get('rows')
                and len(previous['rows'][-1]) == len(block['rows'][0])):
            left = row_pages.get(tuple(_normalized(c) for c in previous['rows'][-1]), set())
            right = row_pages.get(tuple(_normalized(c) for c in block['rows'][0]), set())
            merge = len(left) == len(right) == 1 and next(iter(right)) == next(iter(left)) + 1
        if merge:
            for key in ('cellBlocks', 'cellMarkdown', 'rowSpans', 'colSpans'):
                if key in previous or key in block:
                    default = [] if key == 'cellBlocks' else '' if key == 'cellMarkdown' else 1
                    previous[key] = (previous.get(key, [[default for _ in row] for row in previous['rows']])
                                     + block.get(key, [[default for _ in row] for row in block['rows']]))
            previous['rows'].extend(block['rows'])
        else:
            result.append(block)
    return result


def add_table_lists(pdf_path, data, section_pages):
    from .pdf_document import open_document, Rect
    with open_document(pdf_path) as document:
        section_pages = _native_section_pages(document, data, section_pages)
        cache = {}
        for key, section in data.items():
            if not isinstance(section, dict):
                continue
            tables = [b for b in section.get('blocks', []) if b.get('type') == 'table']
            if not tables:
                continue
            candidates = {}
            row_pages = {}
            for number in section_pages.get(key, []):
                if number not in cache:
                    page = document[number]
                    lines = _page_lines(page, number)
                    found = {}
                    native_rows = []
                    for native in page.find_tables().tables:
                        for row in native.rows:
                            row_text = []
                            for cell in row.cells:
                                if cell is None:
                                    row_text.append('')
                                    continue
                                selected = [line for line in lines if cell[0] <= line['x'] < cell[2]
                                            and cell[1] <= line['y'] < cell[3]]
                                row_text.append(_normalized(' '.join(line['text'] for line in selected)))
                                numbered = any(re.match(r'^\d+[.)]\s+', line['text']) for line in selected)
                                paragraph_breaks = any(b['y'] - a['y'] > 1.4 * b['size']
                                                       for a, b in zip(selected, selected[1:]))
                                if ((numbered or paragraph_breaks or any(line['bullet'] or '](<' in line['inline'] for line in selected))
                                        and not any(line['code'] for line in selected)):
                                    plain = ' '.join(line['text'] for line in selected)
                                    if numbered:
                                        from .pdf_prose_format import _prose_blocks
                                        found[_normalized(plain)] = _prose_blocks(selected)
                                    else:
                                        found[_normalized(plain)] = _list_blocks(selected)
                            native_rows.append(tuple(row_text))
                    cache[number] = (found, native_rows)
                candidates.update(cache[number][0])
                for row in cache[number][1]:
                    row_pages.setdefault(row, set()).add(number)
            original_count = len(section.get('blocks', []))
            section['blocks'] = _merge_native_fragments(section.get('blocks', []), row_pages)
            if len(section['blocks']) != original_count:
                section.pop('markdown', None)
            tables = [b for b in section['blocks'] if b.get('type') == 'table']
            for table in tables:
                formatted = table.get('cellBlocks') or [[[] for cell in row] for row in table.get('rows', [])]
                changed = False
                for i, row in enumerate(table.get('rows', [])):
                    for j, cell in enumerate(row):
                        match = candidates.get(_normalized(cell))
                        if match:
                            formatted[i][j] = match
                            changed = True
                if changed:
                    # Every unmatched cell still renders its original content.
                    for i, row in enumerate(table['rows']):
                        for j, cell in enumerate(row):
                            if not formatted[i][j]:
                                markdown = (table.get('cellMarkdown') or [[] for _ in table['rows']])[i]
                                formatted[i][j] = [{'type': 'paragraph', 'text': cell,
                                                   **({'markdown': markdown[j]} if j < len(markdown) and markdown[j] else {})}]
                    table['cellBlocks'] = formatted
                    section.pop('markdown', None)
