"""Lossless source content shared by scrape results and report renderers."""
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from markdownify import MarkdownConverter
from copy import deepcopy
import re


def title_key(text):
    return ' '.join(text.split()).casefold()


def _note_body(table):
    rows = [row for row in table.find_all('tr') if row.find_parent('table') is table]
    if len(rows) != 1:
        return None
    cells = rows[0].find_all(['td', 'th'], recursive=False)
    if len(cells) != 2 or cells[0].get_text(strip=True):
        return None
    image = cells[0].find('img')
    if image and (re.fullmatch(r'Note|Warning|Caution|Tip', image.get('alt') or image.get('title', ''), re.I)
                  or 'TableStyle-NotesTable' in table.get('class', [])):
        return cells[1]
    return None


def source_markdown(element, url: str, *, omit_title: bool = True, title: str | None = None) -> str:
    # Work on a copy: callers still need the original tree for structured rows.
    content = BeautifulSoup('', 'html.parser')
    if getattr(element, 'name', None) in ('td', 'th', '[document]'):
        for child in element.contents:
            content.append(deepcopy(child))
    elif getattr(element, 'name', None):
        content.append(deepcopy(element))
    else:
        content = BeautifulSoup(str(element), 'html.parser')
    for node in content.select('script, style, nav, .breadcrumb'):
        node.decompose()
    if omit_title:
        heading = content.find(['h1', 'h2', 'h3'])
        if heading and (
            heading.name == 'h1'
            or (title and title_key(heading.get_text(' ', strip=True)) == title_key(title))
        ):
            heading.decompose()
    # Fortinet also marks commands with CSS classes instead of semantic code tags.
    # Keep command cells monospace just as their PDF counterparts are rendered.
    for node in content.find_all('p'):
        children = [child for child in node.contents if str(child).strip()]
        if len(children) == 1 and getattr(children[0], 'name', None) == 'code':
            node.name = 'pre'
            continue
        if (any(re.fullmatch(r'CLI_\d+', cls) for cls in node.get('class', []))
                and (node.find_parent(['td', 'th']) is not None or getattr(element, 'name', None) in ('td', 'th'))):
            node.name = 'code'
    for table in list(content.find_all('table')):
        body = _note_body(table)
        if body is not None:
            quote = content.new_tag('blockquote')
            for child in list(body.contents):
                quote.append(child.extract())
            table.replace_with(quote)
    for node in content.select('a[href], img[src]'):
        attr = 'href' if node.name == 'a' else 'src'
        node[attr] = urljoin(url, node[attr])
    return MarkdownConverter(heading_style='ATX', bullets='-', strip=['script', 'style']).convert_soup(content).strip()


def source_table(table, url: str) -> dict:
    """Keep HTML cell spans and inline content in a rectangular source table."""
    body = _note_body(table)
    if body is not None:
        markdown = source_markdown(body, url, omit_title=False)
        return {'type': 'paragraph', 'text': body.get_text(' ', strip=True),
                'markdown': '\n'.join('> ' + line for line in markdown.splitlines()), 'source_note': True}
    grid = []
    occupied = {}
    header = False
    for index, tr in enumerate(table.find_all('tr')):
        if tr.find_parent('table') is not table:
            continue
        cells = tr.find_all(['th', 'td'], recursive=False)
        if not cells:
            continue
        if not grid:
            header = bool(tr.find_parent('thead') or any(c.name == 'th' for c in cells)
                          or all(re.search(r'font-weight\s*:\s*(?:bold|[6-9]00)\b', c.get('style', ''), re.I)
                                 for c in cells))
        row = {}
        for column, remaining in list(occupied.items()):
            if remaining:
                row[column] = ('', '', 0, 0, [])
                occupied[column] -= 1
        column = 0
        for cell in cells:
            while column in row:
                column += 1
            def span(name):
                try:
                    return max(1, int(cell.get(name, 1)))
                except (ValueError, TypeError):
                    return 1
            rowspan, colspan = span('rowspan'), span('colspan')
            row[column] = (cell.get_text(' ', strip=True), source_markdown(cell, url, omit_title=False), rowspan, colspan, source_blocks(cell, url))
            for offset in range(colspan):
                if offset:
                    row[column + offset] = ('', '', 0, 0, [])
                occupied[column + offset] = rowspan - 1
            column += colspan
        grid.append(row)
    width = max((max(row, default=-1) + 1 for row in grid), default=0)
    matrix = [[row.get(i, ('', '', 1, 1, [])) for i in range(width)] for row in grid]
    head = matrix[0] if header and matrix else []
    body = matrix[1:] if header else matrix
    result = {'type': 'table', 'headers': [c[0] for c in head], 'rows': [[c[0] for c in row] for row in body],
              'headerMarkdown': [c[1] for c in head], 'cellMarkdown': [[c[1] for c in row] for row in body],
              'cellBlocks': [[c[4] for c in row] for row in body]}
    if any(c[2] != 1 for row in body for c in row):
        result['rowSpans'] = [[c[2] for c in row] for row in body]
    if any(c[3] != 1 for row in body for c in row):
        result['colSpans'] = [[c[3] for c in row] for row in body]
    if any(c[3] != 1 for c in head):
        result['headerColSpans'] = [c[3] for c in head]
    return result


def source_blocks(container, url: str) -> list[dict]:
    """Preserve nested HTML block structure; use Markdown only for inline text."""
    from bs4 import Tag, Comment
    from html import escape
    blocks, inline = [], []
    block_tags = {'p', 'pre', 'table', 'ul', 'ol', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
    wrappers = {'div', 'section', 'article', 'main', 'body', 'li', 'td', 'th'}

    def paragraph(node):
        text = node.get_text(' ', strip=True)
        if text or node.find('img'):
            block = {'type': 'paragraph', 'text': text,
                     'markdown': source_markdown(node, url, omit_title=False)}
            bold = ''.join(n.get_text() for n in node.find_all(['strong', 'b'])).strip()
            if bold and len(bold) >= len(text) * .8:
                block['bold'] = True
            blocks.append(block)

    def flush():
        if inline:
            paragraph(BeautifulSoup('<p>' + ''.join(inline) + '</p>', 'html.parser').p)
            inline.clear()

    for node in container.children:
        if isinstance(node, Comment):
            continue
        if not isinstance(node, Tag):
            inline.append(escape(str(node)))
            continue
        if node.name in {'script', 'style', 'nav'}:
            continue
        if node.name not in block_tags and node.name not in wrappers:
            inline.append(str(node))
            continue
        flush()
        if node.name in wrappers:
            blocks.extend(source_blocks(node, url))
        elif node.name == 'table':
            blocks.append(source_table(node, url))
        elif node.name in {'ul', 'ol'}:
            items = []
            item_blocks = []
            for child in node.children:
                if not isinstance(child, Tag):
                    continue
                if child.name == 'li':
                    items.append(child.get_text(' ', strip=True))
                    item_blocks.append(source_blocks(child, url))
                elif child.name in {'ul', 'ol'} and item_blocks:
                    # Fortinet sometimes places a nested list after </li>.
                    # Keep it under the preceding item without inventing a bullet.
                    item_blocks[-1].extend(source_blocks(BeautifulSoup(str(child), 'html.parser'), url))
                    items[-1] += ' ' + child.get_text(' ', strip=True)
            try:
                start = int(node.get('start', 1))
            except (ValueError, TypeError):
                start = 1
            blocks.append({'type': 'list', 'ordered': node.name == 'ol', 'start': start,
                           'items': items, 'itemBlocks': item_blocks})
        elif node.name == 'pre':
            lines = [line.rstrip() for line in node.get_text().splitlines()]
            while lines and not lines[0].strip():lines.pop(0)
            while lines and not lines[-1].strip():lines.pop()
            blocks.append({'type': 'code', 'text': '\n'.join(lines)})
        elif node.name.startswith('h') and len(node.name) == 2:
            blocks.append({'type': 'heading', 'level': int(node.name[1]),
                           'text': node.get_text(' ', strip=True),
                           'markdown': source_markdown(node, url, omit_title=False)})
        else:
            paragraph(node)
    flush()
    return _merge_adjacent_lists(blocks)


def _merge_adjacent_lists(blocks):
    """Adjacent lists without intervening content share a continuous sequence."""
    result = []
    for block in blocks:
        if block.get('type') == 'list' and block.get('itemBlocks'):
            block['itemBlocks'] = [_merge_adjacent_lists(items) for items in block['itemBlocks']]
        previous = result[-1] if result else None
        if (previous and previous.get('type') == block.get('type') == 'list'
                and bool(previous.get('ordered')) == bool(block.get('ordered'))
                and (not block.get('ordered') or block.get('start', 1) ==
                     previous.get('start', 1) + len(previous.get('items', [])))):
            previous['items'].extend(block['items'])
            previous['itemBlocks'].extend(block['itemBlocks'])
        else:
            result.append(block)
    return result
