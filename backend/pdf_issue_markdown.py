"""Recover issue typography from native PDF spans without changing source text."""
import re
import unicodedata
from bisect import bisect_left

_CODE = re.compile(r'consolas|courier|mono(?:space)?|source.?code', re.I)
_SECTIONS = {
    'known issues': 'known_issues', 'resolved issues': 'resolved-issues',
    'new features or enhancements': 'new_features',
    'new features and enhancements': 'new_features',
    'changes in cli': 'changes_cli', 'changes in default behavior': 'changes_default',
    'changes in table size': 'changes_tablesize',
    'changes in gui behavior': 'changes-in-gui-behavior',
    'changes in default values': 'changes-in-default-values',
}


def _normalized(text):
    return re.sub(r'\W+', '', unicodedata.normalize('NFKC', text)).lower()


def _escape(text):
    return re.sub(r'([\\`*_[\]<>&])', r'\\\1', text)


def _inline(spans, links=()):
    groups = []
    for span in spans:
        font = span['font'].lower()
        bold, italic = 'bold' in font, bool(re.search(r'italic|oblique', font))
        style = ('code' if _CODE.search(font) else 'bolditalic' if bold and italic
                 else 'bold' if bold else 'italic' if italic else 'plain')
        target = None
        if 'bbox' in span:
            x0, y0, x1, y1 = span['bbox']
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            for link in links:
                rect = link['from']
                if link.get('uri') and rect[0] <= cx <= rect[2] and rect[1] <= cy <= rect[3]:
                    target = link['uri']
                    break
        if groups and groups[-1][0] == style and groups[-1][2] == target:
            groups[-1][1] += span['text']
        else:
            groups.append([style, span['text'], target])
    parts = []
    for style, text, target in groups:
        body = text.strip()
        if not body:
            parts.append(text)
            continue
        left = text[:len(text) - len(text.lstrip())]
        right = text[len(text.rstrip()):]
        if style == 'code':
            fence = '`' * (max([len(s) for s in re.findall(r'`+', body)] or [0]) + 1)
            body = fence + ' ' + body + ' ' + fence
        else:
            body = _escape(body)
            if style == 'bold':
                body = '**' + body + '**'
            elif style == 'italic':
                body = '*' + body + '*'
            elif style == 'bolditalic':
                body = '***' + body + '***'
        if target:
            url = target.replace('<', '%3C').replace('>', '%3E').replace(' ', '%20')
            body = '[' + body + '](<' + url + '>)'
        parts.append(left + body + right)
    return ''.join(parts).strip()


def _page_lines(page, page_number, embedded_tables=False):
    lines = []
    links = page.get_links()
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            original = line['spans']
            bullet = any('wingdings' in s['font'].lower() for s in original)
            spans = [s for s in original if 'wingdings' not in s['font'].lower()]
            raw_text = ''.join(s['text'] for s in spans)
            text = raw_text.strip()
            if not text or line['bbox'][1] < 65:
                continue
            if text == str(page_number + 1) and line['bbox'][1] > page.rect.height - 60:
                continue
            if re.match(r'^(FortiOS\s+[\d.]+\s+Release\s+Notes|Fortinet\s+Inc\.?$)', text):
                continue
            if text.lower() in {'bug id', 'feature id', 'description', 'cve references'}:
                continue
            code_chars = sum(len(s['text'].strip()) for s in spans if _CODE.search(s['font']))
            chars = sum(len(s['text'].strip()) for s in spans)
            lines.append({'text': text, 'leading_space': raw_text[:len(raw_text) - len(raw_text.lstrip())], 'inline': _inline(spans, links), 'bullet': bullet,
                          'code': bool(chars and code_chars == chars and not bullet),
                          'page': page_number, 'x': min(s['bbox'][0] for s in spans),
                          'bbox': line['bbox'], 'y': line['bbox'][1], 'size': max(s['size'] for s in spans)})
    if embedded_tables:
        tables = page.find_tables().tables
        for table in tables:
            rect = table.bbox
            if not any(other is not table and other.bbox != rect
                       and other.bbox[0] <= rect[0] and other.bbox[1] <= rect[1]
                       and other.bbox[2] >= rect[2] and other.bbox[3] >= rect[3] for other in tables):
                continue
            indexes = [i for i, line in enumerate(lines)
                       if rect[0] <= line['x'] <= rect[2] and rect[1] <= line['y'] <= rect[3]]
            if not indexes:
                continue
            raw = table.extract()
            rendered = []
            for row in table.rows:
                cells = []
                for cell in row.cells:
                    native = page.get_text('dict', clip=cell)['blocks'] if cell else []
                    text = ' '.join(_inline(line['spans'], links) for block in native for line in block.get('lines', []))
                    cells.append(text.replace('|', r'\|'))
                rendered.append('| ' + ' | '.join(cells) + ' |')
            if not rendered:
                continue
            rendered.insert(1, '| ' + ' | '.join('---' for _ in table.rows[0].cells) + ' |')
            event = dict(lines[indexes[0]], text=' '.join(str(c or '') for row in raw for c in row), table_markdown='\n'.join(rendered))
            lines = [line for i, line in enumerate(lines) if i not in indexes[:]]
            lines.insert(indexes[0], event)
    return lines


def _join_inline(left, right, separator=' '):
    # Native line wrapping can split one inline code span in two. Joining its
    # closing/opening fences directly would render literal backticks.
    end = re.search(r'(?<!`)(`+) ([^`]*?) \1$', left)
    start = re.match(r'(`+) ([^`]*?) \1(?!`)', right)
    if end and start and end[1] == start[1]:
        return left[:end.start()] + end[1] + ' ' + end[2] + separator + start[2] + ' ' + end[1] + right[start.end():]
    return left + separator + right


def _markdown(lines):
    blocks = []
    previous = None
    for line in lines:
        # A bold list marker is still numbering, not paragraph emphasis.
        inline = re.sub(r'^\*\*(\d+[.)])\*\*\s+', r'\1 ', line['inline'])
        numbered = re.match(r'^(\d+)[.)]\s+(.*)', inline)
        if line.get('table_markdown'):
            blocks.append({'kind': 'table', 'text': line['table_markdown']})
        elif line['code']:
            if blocks and blocks[-1]['kind'] == 'code':
                blocks[-1]['lines'].append(line)
            else:
                blocks.append({'kind': 'code', 'lines': [line]})
        elif line['bullet'] or numbered:
            start = int(numbered[1]) if numbered else None
            if (not blocks or blocks[-1]['kind'] != 'list'
                    or (blocks[-1].get('start') is None) != (start is None)
                    or (start is not None and start != blocks[-1].get('start', 0) + len(blocks[-1]['items']))):
                blocks.append({'kind': 'list', 'items': [], 'start': start})
            blocks[-1]['items'].append(numbered[2] if numbered else line['inline'])
        else:
            close = (previous and previous['page'] == line['page']
                     and line['y'] - previous['y'] <= 1.55 * line['size'])
            separator = '' if previous and re.search(r'\w-$', previous['text']) and re.match(r'\w', line['text']) else ' '
            if blocks and blocks[-1]['kind'] == 'list' and close:
                blocks[-1]['items'][-1] = _join_inline(blocks[-1]['items'][-1], line['inline'], separator)
            elif blocks and blocks[-1]['kind'] == 'paragraph' and close:
                blocks[-1]['text'] = _join_inline(blocks[-1]['text'], line['inline'], separator)
            else:
                blocks.append({'kind': 'paragraph', 'text': line['inline']})
        previous = line
    result = []
    for block in blocks:
        if block['kind'] == 'code':
            origin = min(line['x'] for line in block['lines'])
            text = '\n'.join(' ' * max(0, round((line['x'] - origin) / (line['size'] * .55))) + line.get('leading_space', '') + line['text'] for line in block['lines'])
            fence = '`' * max(3, max([len(s) + 1 for s in re.findall(r'`+', text)] or [3]))
            result.append(fence + '\n' + text + '\n' + fence)
        elif block['kind'] == 'list':
            start = block.get('start')
            result.append('\n'.join((str(start + i) + '. ' if start is not None else '- ') + item for i, item in enumerate(block['items'])))
        else:
            result.append(block['text'])
    return '\n\n'.join(result)


def add_issue_markdown(pdf_path, data):
    """Only attach Markdown when an entire description matches native source lines.

    Chapter bounds keep repeated text associated with the right source section.
    Unmatched descriptions retain their existing text for inspection.
    """
    from .pdf_document import open_document
    with open_document(pdf_path) as doc:
        chapters = [entry for entry in doc.get_toc() if entry[0] == 1]
        bounds = {}
        for i, (_, title, start) in enumerate(chapters):
            key = _SECTIONS.get(title.lower())
            if key:
                bounds[key] = (start - 1, chapters[i + 1][2] - 1 if i + 1 < len(chapters) else len(doc))
        issue_pages = {page for start, end in bounds.values() for page in range(start, end)}
        page_lines = [_page_lines(page, i, embedded_tables=i in issue_pages) for i, page in enumerate(doc)]
        work = list(data.items())
        rich_tables = []
        for key, section in data.items():
            if not isinstance(section, dict):
                continue
            for table in section.get('blocks', []):
                if table.get('type') != 'table' or table.get('headers') not in (['Bug ID', 'Description'], ['Feature ID', 'Description']):
                    continue
                if any(len(row) != 2 for row in table.get('rows', [])):
                    continue
                rows = [{'Bug ID': row[0], 'Description': row[1]} for row in table['rows']]
                work.append((key, rows))
                rich_tables.append((section, table, rows))
        for key, rows in work:
            if not isinstance(rows, list):
                continue
            start, end = bounds.get(key, (0, len(doc)))
            lines = [line for page in page_lines[start:end] for line in page]
            offsets = [0]
            for line in lines:
                offsets.append(offsets[-1] + len(_normalized(line['text'])))
            source = ''.join(_normalized(line['text']) for line in lines)
            for row in rows:
                desc = _normalized(row.get('Description', ''))
                if not desc:
                    continue
                identifier = _normalized(row.get('Bug ID', row.get('Feature ID', '')))
                anchor = source.find(identifier) if identifier else -1
                pos = source.find(desc, anchor + len(identifier)) if anchor >= 0 else source.find(desc)
                if pos < 0:
                    # Some PDF content streams place the ID column after the text.
                    pos = source.find(desc)
                if pos < 0:
                    continue
                first = bisect_left(offsets, pos)
                last = bisect_left(offsets, pos + len(desc))
                if first >= len(offsets) or last >= len(offsets) or offsets[first] != pos or offsets[last] != pos + len(desc):
                    continue
                row['markdown'] = _markdown(lines[first:last])

        for section, table, rows in rich_tables:
            if any(row.get('markdown') for row in rows):
                table['cellMarkdown'] = [['', row.get('markdown', '')] for row in rows]
                section.pop('markdown', None)
