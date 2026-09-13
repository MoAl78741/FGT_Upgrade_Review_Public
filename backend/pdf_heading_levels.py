"""Preserve the document's explicit bookmark heading hierarchy."""
import re
from .pdf_issue_markdown import _normalized


def align_heading_levels(pdf_path, data):
    from .pdf_document import open_document, Rect
    levels = {}
    with open_document(pdf_path) as document:
        for level, title, _ in document.get_toc():
            levels.setdefault(_normalized(title), set()).add(min(6, max(1, level)))
    unique = {title: next(iter(values)) for title, values in levels.items() if len(values) == 1}
    def markdown(text):
        output, fence = [], None
        for line in text.splitlines(keepends=True):
            marker = re.match(r'^\s*(`{3,}|~{3,})', line)
            if marker:
                if fence is None:
                    fence = marker[1]
                elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                    fence = None
                output.append(line)
                continue
            match = re.match(r'^(#{1,6})\s+(.+?)(\r?\n)?$', line) if fence is None else None
            level = unique.get(_normalized(match[2])) if match and len(match[1]) != 6 else None
            output.append('#' * level + ' ' + match[2] + (match[3] or '') if level else line)
        return ''.join(output)
    for section in data.values():
        if not isinstance(section, dict):
            continue
        for block in section.get('blocks', []):
            if block.get('type') == 'heading' and block.get('level') != 6:
                level = unique.get(_normalized(block.get('text', '')))
                if level:
                    block['level'] = level
                    if block.get('markdown'):
                        block['markdown'] = markdown(block['markdown'])
        if section.get('markdown'):
            section['markdown'] = markdown(section['markdown'])
