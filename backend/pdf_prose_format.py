"""Recover prose typography and list hierarchy from exact native text matches."""
import re
from bisect import bisect_left
from .pdf_issue_markdown import _page_lines, _normalized, _markdown, _join_inline
from .pdf_table_lists import _native_section_pages


def _without_number(text):
    return re.sub(r'^\d+[.)]\s+', '', text)


def _prose_blocks(lines):
    blocks, stack = [], []
    previous = None
    for line in lines:
        inline = re.sub(r'^\*\*(\d+[.)])\*\*\s+', r'\1 ', line['inline'])
        number = re.match(r'^(\d+)[.)]\s+(.*)', inline)
        listed = line['bullet'] or bool(number)
        x = line['x']
        if number:
            x += len(number[1]) * line['size'] * .55
        while stack and (x < stack[-1][0] - 4 or
                         (not listed and stack[-1][1]['ordered'] and x <= stack[-1][0] + 4)):
            stack.pop()
        inline_continuation = (line.get('code') and previous and not previous.get('code')
                               and previous['page'] == line['page']
                               and line['y'] - previous['y'] <= 1.55 * line['size']
                               and re.search(r'`[.,;:!?)]$', inline))
        if line.get('source_block'):
            target = stack[-1][1]['itemBlocks'][-1] if stack else blocks
            target.append(line['source_block'])
        elif line.get('code') and not inline_continuation:
            target = stack[-1][1]['itemBlocks'][-1] if stack else blocks
            if target and target[-1]['type'] == 'code':
                target[-1]['_native_lines'].append(line)
            else:
                target.append({'type': 'code', '_native_lines': [line]})
        elif listed:
            ordered = bool(number)
            start = int(number[1]) if number else 1
            if stack and abs(x - stack[-1][0]) <= 8:
                current = stack[-1][1]
                if (bool(current['ordered']) != ordered or
                        (ordered and start != current['start'] + len(current['items']))):
                    stack.pop()
            if not stack or x > stack[-1][0] + 8:
                target = stack[-1][1]['itemBlocks'][-1] if stack else blocks
                node = {'type': 'list', 'ordered': ordered, 'start': start, 'items': [], 'itemBlocks': []}
                target.append(node)
                stack.append((x, node))
            node = stack[-1][1]
            text = _without_number(line['text']) if number else line['text']
            markdown = number[2] if number else inline
            node['items'].append(text)
            node['itemBlocks'].append([{'type': 'paragraph', 'text': text, 'markdown': markdown}])
        else:
            target = stack[-1][1]['itemBlocks'][-1] if stack else blocks
            close = (previous and previous['page'] == line['page']
                     and line['y'] - previous['y'] <= 1.55 * line['size'])
            if target and target[-1]['type'] == 'paragraph' and close:
                separator = '' if re.search(r'\w-$', previous['text']) and re.match(r'\w', line['text']) else ' '
                target[-1]['text'] += separator + line['text']
                target[-1]['markdown'] = _join_inline(target[-1]['markdown'], inline, separator)
            else:
                target.append({'type': 'paragraph', 'text': line['text'], 'markdown': inline})
            if stack:
                stack[-1][1]['items'][-1] += ' ' + line['text']
        previous = line
    def finish(items):
        for item in items:
            if item['type'] == 'code' and '_native_lines' in item:
                markdown = _markdown(item.pop('_native_lines'))
                item['text'] = '\n'.join(markdown.splitlines()[1:-1])
            for children in item.get('itemBlocks', []):
                finish(children)
    finish(blocks)
    return blocks


def _block_text(block):
    return ' '.join(block.get('items', [])) if block['type'] == 'list' else block.get('text', '')


def add_prose_formatting(pdf_path, data, section_pages):
    from .pdf_document import open_document, Rect
    with open_document(pdf_path) as document:
        pages = _native_section_pages(document, data, section_pages)
        cache = {}
        for key, section in data.items():
            if not isinstance(section, dict) or not section.get('blocks'):
                continue
            lines = []
            for number in pages.get(key, []):
                if number not in cache:
                    cache[number] = _page_lines(document[number], number)
                lines.extend(cache[number])
            offsets = [0]
            for line in lines:
                offsets.append(offsets[-1] + len(_normalized(_without_number(line['text']))))
            source = ''.join(_normalized(_without_number(line['text'])) for line in lines)
            blocks, output, cursor = section['blocks'], [], 0
            changed = False
            while cursor < len(blocks):
                end = cursor
                while end < len(blocks) and blocks[end]['type'] in {'paragraph', 'list', 'code'}:
                    end += 1
                if end == cursor:
                    output.append(blocks[cursor]); cursor += 1; continue
                original = blocks[cursor:end]
                wanted = _normalized(' '.join(_block_text(b) for b in original))
                position = source.find(wanted) if wanted else -1
                first = bisect_left(offsets, position) if position >= 0 else -1
                last = bisect_left(offsets, position + len(wanted)) if position >= 0 else -1
                if (position >= 0 and offsets[first] == position and last < len(offsets)
                        and offsets[last] == position + len(wanted)):
                    selected = list(lines[first:last])
                    # Keep recognized notes atomic while recovering surrounding lists.
                    notes_matched = True
                    for block in original:
                        if not block.get('source_note'):
                            continue
                        note = _normalized(_block_text(block))
                        found = False
                        for start in range(len(selected)):
                            text = ''
                            for stop in range(start, len(selected)):
                                text += _normalized(_without_number(selected[stop]['text']))
                                if text == note:
                                    selected[start:stop + 1] = [{**selected[start], 'source_block': block}]
                                    found = True
                                    break
                                if not note.startswith(text):
                                    break
                            if text == note:
                                break
                        if not found:
                            notes_matched = False
                            break
                    if notes_matched:
                        output.extend(_prose_blocks(selected)); changed = True
                    else:
                        output.extend(original)
                else:
                    output.extend(original)
                cursor = end
            if changed:
                section['blocks'] = output
                section.pop('markdown', None)


def sync_notice_formatting(data, notices):
    """Render each notice with the same source blocks as its matching rich section."""
    from copy import deepcopy
    from .pdf_parser import _title_to_slug
    for notice in notices:
        section = data.get(_title_to_slug(notice.get('title', '')))
        if (not isinstance(section, dict) or not section.get('blocks')
                or _normalized(section.get('title', '')) != _normalized(notice.get('title', ''))):
            continue
        notice['blocks'] = deepcopy(section['blocks'])
        if section.get('markdown'):
            notice['markdown'] = section['markdown']
        else:
            notice.pop('markdown', None)
