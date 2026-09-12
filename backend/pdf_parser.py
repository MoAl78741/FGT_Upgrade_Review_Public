"""
PDF parser for FortiGate release notes.
Converts PDF content into the same data structures produced by the web scrapers.

Expected output per call to parse_pdf():
  (version: str | None, version_data: dict, special_notices: list)

version_data keys that may be populated:
  new_features      – list of {category, Feature ID, Description}
  known_issues      – list of {category, Bug ID, Description}
  resolved-issues   – list of {category, Bug ID, Description}
  changes_cli       – list of {Bug ID, Description}
  changes_default   – list of {Bug ID, Description}
  changes_tablesize – list of {Bug ID, Description}

special_notices:
  list of {title, content}
"""

import re
from pathlib import Path
from typing import Optional

try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import pymupdf4llm as _pymupdf4llm
    # Release notes already contain selectable text. Avoid OCR / model-based
    # layout inference, which is unnecessary and costly for these documents.
    if hasattr(_pymupdf4llm, "use_layout"):
        _pymupdf4llm.use_layout(False)
    PYMUPDF4LLM_AVAILABLE = True
except ImportError:
    PYMUPDF4LLM_AVAILABLE = False


# ──────────────────────────────────────────────────────────────────────────────
# Section detection
# ──────────────────────────────────────────────────────────────────────────────

# (pattern, section_key) — ordered from most-specific to least
_SECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^what['']?s new\b", re.I),                                          "new_features"),
    (re.compile(r"^new features?\b", re.I),                                            "new_features"),
    (re.compile(r"^changes?\s+(?:in|to)\s+cli\b", re.I),                              "changes_cli"),
    (re.compile(r"^changes?\s+in\s+gui\b", re.I),                                     "changes-in-gui-behavior"),
    (re.compile(r"^changes?\s+(?:in|to)\s+default\s+(?:behavior|behaviour|settings?)$", re.I),
                                                                                       "changes_default"),
    (re.compile(r"^changes?\s+(?:in|to)\s+default\s+values$", re.I), "changes-in-default-values"),
    (re.compile(r"^changes?\s+(?:in|to)\s+table\s+size$", re.I),                      "changes_tablesize"),
    (re.compile(r"^special\s+notices?$", re.I),                                        "special_notices"),
    (re.compile(r"^known\s+issues?$", re.I),                                           "known_issues"),
    (re.compile(r"^resolved\s+issues?$", re.I),                                        "resolved-issues"),
    (re.compile(r"^change\s*log$", re.I),                                              "change-log"),
    # Rich prose sections → stored as RichSection dicts under slug keys
    (re.compile(r"^introduction(?:\s+and\s+supported\s+models)?$", re.I),              "introduction-and-supported-models"),
    (re.compile(r"^upgrade\s+information$", re.I),                                     "upgrade-information"),
    (re.compile(r"^product\s+integration\s+and\s+support$", re.I),                     "product-integration-and-support"),
    (re.compile(r"^ssl[ -]vpn\s+support$", re.I),                                     "ssl-vpn-support"),
    (re.compile(r"^built-in\s+av\s+engine$", re.I),                                   "built-in-av-engine"),
    (re.compile(r"^built-in\s+ips\s+engine$", re.I),                                  "built-in-ips-engine"),
    (re.compile(r"^limitations$", re.I),                                               "limitations"),
]

# Sections we don't want to capture at all
_SKIP_RE = re.compile(
    r"^(introduction|"
    r"downgrade\s+information|limitations?|appendix|table\s+of\s+contents?|"
    r"fortios[^\n]{0,40}release\s+notes|contents?)$",
    re.I,
)

# Section keys that produce RichSection prose content (not table-based)
_RICH_KEYS: frozenset = frozenset({
    "introduction-and-supported-models",
    "upgrade-information",
    "product-integration-and-support",
    "change-log",
    "changes-in-gui-behavior",
    "changes-in-default-values",
    "ssl-vpn-support",
    "built-in-av-engine",
    "built-in-ips-engine",
    "limitations",
})


def _match_section(line: str) -> Optional[str]:
    """Return section key if line is a recognized section heading, else None."""
    line = line.strip()
    if re.search(r"\s+\d+\s*$", line):
        return None  # A table-of-contents entry, not the chapter itself.
    for pat, key in _SECTION_PATTERNS:
        if pat.match(line):
            return key
    return None


def _is_skippable(line: str) -> bool:
    return bool(_SKIP_RE.match(line.strip()))


# Monospace / code fonts used by Fortinet in PDF code blocks
_CODE_FONT_RE = re.compile(r'consolas|courier|mono(?:space)?|source.?code|lucida.?console', re.I)
# Bold (non-code) fonts used for in-text bold phrases
_BOLD_FONT_RE = re.compile(r'bold', re.I)

# Bullet characters used by Fortinet PDFs (including Symbol/Wingdings private-use glyphs)
_BULLET_CHAR_RE = re.compile(
    r'^[\u2022\u2023\u25E6\u2043\u2219\u00B7\u25CF\u25AA\u2714\u2713'
    r'\uf0b7\uf0a7\uf0d8\uf0fc\uf0cf\u00b7•·●○◆▪▫►▶◦‣⁃]\s*',
    re.UNICODE,
)

# Numbered list items: "1.", "2.", "(1)", etc.
_NUMBERED_ITEM_RE = re.compile(r'^(\d+[\.\)]|\(\d+\))\s+')

# Page-footer lines that appear on every page of FortiGate PDFs
_PDF_FOOTER_RE = re.compile(
    r'^(FortiOS\s+[\d\.]+\s+Release\s+Notes|Fortinet\s+Inc\.?\s*$)',
    re.I,
)


def _fix_pipe_lists(blocks: list[dict]) -> list[dict]:
    """
    Convert pipe-prefixed paragraph blocks into list blocks.

    Fortinet PDFs render hyperlink lists as text items prefixed with '|'
    (e.g. "| FortiGate 6000 ... | FortiGate 7000E ... | FortiGate 7000F ...").
    These may appear as individual lines or pre-merged into a single paragraph.
    """
    result = []
    for block in blocks:
        if block.get("type") == "paragraph":
            text = block["text"]
            if text.startswith("|"):
                parts = [p.strip() for p in text.split("|") if p.strip()]
                if parts:
                    result.append({"type": "list", "items": parts})
                    continue
        result.append(block)
    return result


def _is_category_like(line: str) -> bool:
    """
    Heuristic: is this line a category heading within a section?
    (e.g. "Firewall", "SD-WAN", "Security Fabric")
    """
    line = line.strip()
    if not line or len(line) > 80:
        return False
    if line[0].isdigit():
        return False
    if "|" in line or re.search(r"\d{5,}", line):
        return False
    # Don't treat lines that are probably part of sentences
    if line.endswith((".",":",",",";")):
        return False
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Version detection
# ──────────────────────────────────────────────────────────────────────────────

def detect_version_from_filename(filename: str) -> Optional[str]:
    """Extract '7.4.11' from 'fortios-v7.4.11-release-notes.pdf'."""
    m = re.search(r"v?(\d+\.\d+\.\d+)", filename, re.I)
    return m.group(1) if m else None


def detect_version_from_text(text: str) -> Optional[str]:
    """Extract FortiOS version from the first page text."""
    for pat in [
        r"FortiOS\s+v?(\d+\.\d+\.\d+)",
        r"FortiGate[^\n]{0,40}?(\d+\.\d+\.\d+)",
        r"Release\s+Notes[^\n]{0,40}?(\d+\.\d+\.\d+)",
        r"[Vv]ersion\s+(\d+\.\d+\.\d+)",
    ]:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Table row parsing
# ──────────────────────────────────────────────────────────────────────────────

def _clean(v) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v)).strip()


def _title_to_slug(title: str) -> str:
    """Convert a section title to a URL-style slug (lowercase, hyphens)."""
    slug = re.sub(r"[^a-z0-9\s]", " ", re.sub("[’']", "", title.lower()))
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug


def _looks_like_id(text: str) -> bool:
    """Return True if text looks like a standalone Bug/Feature ID (4-10 digit number)."""
    return bool(re.match(r'^\d{4,10}(?:,\s*\d{4,10})*$', text.strip()))


# Matches a standalone numeric ID as it appears alone in the left-column text stream
# (Bug IDs and Feature IDs in FortiGate PDFs are 5-10 digit numbers).
_STANDALONE_ID_RE = re.compile(r'^\d{5,10}(?:,\s*\d{5,10})*,?$')


def _split_id_from_text(text: str) -> tuple[str, str]:
    """
    If text begins with a numeric ID followed by whitespace, split it.
    Returns (id, rest_of_description). If no leading numeric ID, returns ("", text).
    """
    m = re.match(r'^(\d{4,10})\s+(.*)', text.strip(), re.DOTALL)
    if m:
        return m.group(1), m.group(2).strip()
    return "", text.strip()


def _parse_id_desc_table(
    rows: "list[list] | list[tuple[float, list]]",
    id_key: str = "Bug ID",
) -> list[dict]:
    """
    Convert raw pdfplumber table rows → list of {id_key: ..., Description: ..., _first_y: float}.

    Accepts two row formats:
      • list[list]                 — plain cells (tests, fallback path)
      • list[tuple[float, list]]   — (row_y, cells) from _extract_table_rows

    Handles:
      - Header row detection and skip
      - Multi-line rows (empty id cell = continuation)
      - Merged first-column cells (e.g. "890776 Description text" in one cell)
      - Description-only tables (no numeric IDs — id_key set to "")
    """
    if not rows:
        return []

    # Detect rows_with_y format: list of (float, list) tuples
    has_y = isinstance(rows[0], tuple)

    def _cells(item):
        return item[1] if has_y else item

    def _y(item) -> float:
        return float(item[0]) if has_y else 0.0

    # Detect and skip header row
    start = 0
    first = [_clean(c).lower() for c in (_cells(rows[0]) or [])]
    header_kws = {"bug id", "feature id", "description", "cve references", "id", "number"}
    if any(cell in header_kws for cell in first):
        start = 1

    results: list[dict] = []
    cur_id: Optional[str] = None
    cur_desc_parts: list[str] = []
    cur_first_y: float = 0.0
    continuation = False

    def _flush():
        if cur_id is None:
            return
        # Skip rows that are just leftover header text
        if cur_id.lower() in ("bug id", "feature id", "id", "number"):
            return
        # Allow empty-ID rows (description-only sections) as long as there's content
        desc = " ".join(cur_desc_parts)
        if cur_id == "" and not desc:
            return
        results.append({
            id_key: cur_id,
            "Description": desc,
            "_first_y": cur_first_y,
            **({"_continuation": True} if continuation else {}),
        })

    for item in rows[start:]:
        row = _cells(item)
        row_y = _y(item)
        if not row:
            continue
        # Pad to at least 2 cells
        row = list(row) + [""] * max(0, 2 - len(row))

        c0 = _clean(row[0])
        c1 = " ".join(_clean(c) for c in row[1:] if _clean(c))

        if not c0 and not c1:
            continue

        if not c0:
            # Continuation line — description text in remaining columns
            if cur_id is None:
                cur_id = ""
                cur_first_y = row_y
                continuation = True
            cur_desc_parts.append(c1)
        elif _looks_like_id(c0):
            # Clean numeric ID in column 0 — normal case
            _flush()
            continuation = False
            cur_id = c0
            cur_desc_parts = [c1] if c1 else []
            cur_first_y = row_y
        else:
            # Column 0 is NOT a plain numeric ID.
            # Two sub-cases:
            #   (a) Merged cell: "890776 Description text" — split leading ID off
            #   (b) No ID at all: pure description text
            extracted_id, rest = _split_id_from_text(c0)
            if extracted_id:
                # Case (a): numeric ID was merged with description
                _flush()
                continuation = False
                cur_id = extracted_id
                # Combine the rest of the merged cell with any additional columns
                full_desc = (rest + " " + c1).strip() if c1 else rest
                cur_desc_parts = [full_desc] if full_desc else []
                cur_first_y = row_y
            else:
                # Case (b): no ID — treat entire row as a description-only entry
                _flush()
                continuation = False
                cur_id = ""
                full_desc = (c0 + " " + c1).strip() if c1 else c0
                cur_desc_parts = [full_desc] if full_desc else []
                cur_first_y = row_y

    _flush()
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Word → line grouping
# ──────────────────────────────────────────────────────────────────────────────


def _complete_left_column(page, table):
    """Recover a column whose horizontal borders exist but outer border does not."""
    from types import SimpleNamespace
    x0, top, x1, bottom = table.bbox
    edges = [e for e in page.edges if e.get("orientation") == "h"
             and abs(e["x1"] - x0) < 1 and e["x0"] < x0 - 10
             and top - 1 <= e["top"] <= bottom + 1]
    if not edges:
        return table
    left = min(e["x0"] for e in edges)
    boundaries = [e["top"] for e in edges if abs(e["x0"] - left) < 1]
    if not all(any(abs(y - edge) < 1 for edge in boundaries) for y in (top, bottom)):
        return table
    first_bottom = table.rows[0].bbox[3]
    header = page.crop((left, top, x0, first_bottom)).extract_text() or ""
    # Issue tables have a separate, already-tested ID/description association.
    if re.sub(r"\W+", "", header).lower() in {"bugid", "featureid"}:
        return table
    rows = []
    for row in table.rows:
        _, row_top, _, row_bottom = row.bbox
        cell_top = max((y for y in boundaries if y <= row_top + 1), default=None)
        cell_bottom = min((y for y in boundaries if y >= row_bottom - 1), default=None)
        if cell_top is None or cell_bottom is None:
            return table
        cell = (left, cell_top, x0, cell_bottom) if abs(cell_top - row_top) < 1 else None
        rows.append(SimpleNamespace(cells=[cell, *row.cells], bbox=(left, row_top, x1, row_bottom)))
    return SimpleNamespace(bbox=(left, top, x1, bottom), rows=rows)



def _table_row_spans(table):
    """Map PDF cells spanning row boundaries to HTML-style row spans."""
    starts = [min(c[1] for c in row.cells if c is not None) for row in table.rows]
    result = []
    covering = {}
    for i, row in enumerate(table.rows):
        spans = []
        for column, cell in enumerate(row.cells):
            if cell is None:
                spans.append(0 if covering.get(column, -1) > starts[i] + 1 else 1)
            else:
                count = sum(cell[1] - 1 <= y < cell[3] - 1 for y in starts)
                spans.append(max(1, count))
                covering[column] = cell[3]
        result.append(spans)
    return result


def _join_cell_words(words):
    """Rejoin identifiers wrapped after a hyphen or underscore across lines."""
    text = ""
    previous = None
    for word in words:
        wrapped_identifier = (previous is not None and previous["text"].endswith(("-", "_"))
                              and word.get("top", 0) > previous.get("top", 0) + 3)
        text += ("" if not text or wrapped_identifier else " ") + word["text"]
        previous = word
    return text


class _CellTextIndex:
    """Index page characters by vertical band without changing crop semantics."""

    def __init__(self, page):
        from math import floor
        self.page = page
        self.chars = page.chars
        self.bands = {}
        self.spanning = []
        for index, char in enumerate(self.chars):
            first = floor(max(char["top"], page.bbox[1]) / 32)
            last = floor(min(char["bottom"], page.bbox[3]) / 32)
            if last - first > 128:
                self.spanning.append(index)
                continue
            for band in range(first, last + 1):
                self.bands.setdefault(band, []).append(index)

    def words(self, bbox):
        from math import floor
        from pdfplumber import utils
        from pdfplumber.page import test_proposed_bbox
        test_proposed_bbox(bbox, self.page.bbox)
        indices = set(self.spanning)
        first, last = floor(bbox[1] / 32), floor(bbox[3] / 32)
        # Iterate occupied bands, not potentially enormous PDF coordinates.
        for band, members in self.bands.items():
            if first <= band <= last:
                indices.update(members)
        # Use pdfplumber's exact clipping and word grouping, including partial
        # characters at a cell edge. Retain the original character order.
        chars = utils.crop_to_bbox([self.chars[i] for i in sorted(indices)], bbox)
        return utils.extract_words(chars, x_tolerance=1, y_tolerance=3, extra_attrs=["fontname"])


def _extract_table_rows(page, tbl_obj, text_index=None) -> list[tuple[float, list]]:
    """
    Extract table rows using per-cell word extraction so that spaces are
    correctly inserted between words.  Falls back to the raw cell text when
    cropping fails.

    Returns a list of (row_y, cells) tuples where row_y is the top-edge
    y-coordinate of the row — used later to pair text-column IDs with
    table-column descriptions by proximity.
    """
    rows_with_y: list[tuple[float, list]] = []
    try:
        for row in tbl_obj.rows:
            row_y = 0.0
            for cell in row.cells:
                if cell is not None:
                    row_y = float(cell[1])
                    break
            cells: list = []
            for cell in row.cells:
                if cell is None:
                    cells.append(None)
                    continue
                try:
                    x0, top, x1, bottom = cell
                    # Small inset to avoid picking up border lines
                    bbox = (x0 + 1, top + 1, x1 - 1, bottom - 1)
                    if text_index is not None:
                        words = text_index.words(bbox)
                    else:
                        words = page.crop(bbox).extract_words(x_tolerance=1, y_tolerance=3, extra_attrs=["fontname"])
                    words = [w for w in words if not ("wingdings" in w.get("fontname", "").lower() and w["text"] == "l")]
                    cells.append(_join_cell_words(words))
                except Exception:
                    cells.append("")
            rows_with_y.append((row_y, cells))
    except Exception:
        raw = tbl_obj.extract()
        rows_with_y = [(float(i), row or []) for i, row in enumerate(raw or [])]
    return rows_with_y


def _table_has_header(page, table):
    """Distinguish a bold header row from a headerless label/value table."""
    cells = [cell for cell in table.rows[0].cells if cell is not None]
    if not cells:
        return False
    bbox = (min(c[0] for c in cells), min(c[1] for c in cells),
            max(c[2] for c in cells), max(c[3] for c in cells))
    words = page.crop(bbox).extract_words(extra_attrs=["fontname"])
    if not words:
        return False
    return sum(len(w["text"]) for w in words if _BOLD_FONT_RE.search(w.get("fontname", ""))) / max(sum(len(w["text"]) for w in words), 1) >= .8

def _words_to_lines(
    words: list[dict],
    tolerance: float = 3.0,
) -> list[tuple[float, list[dict]]]:
    """Group words by y-coordinate into sorted lines."""
    buckets: dict[int, list[dict]] = {}
    for w in words:
        key = round(w["top"] / tolerance)
        buckets.setdefault(key, []).append(w)
    return sorted(
        ((k * tolerance, sorted(ws, key=lambda x: x["x0"])) for k, ws in buckets.items()),
        key=lambda t: t[0],
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────────

def _append_numbered_item(blocks, line):
    """Keep source numbering, including lists starting after item one."""
    match = _NUMBERED_ITEM_RE.match(line)
    number = int(re.search(r"\d+", match.group(1)).group())
    text = line[match.end():].strip()
    previous = blocks[-1] if blocks else {}
    if (previous.get("type") == "list" and previous.get("ordered")
            and previous.get("start", 1) + len(previous["items"]) == number):
        previous["items"].append(text)
    else:
        blocks.append({"type": "list", "ordered": True, "start": number, "items": [text]})


def _indent_code_events(events):
    """Restore code whitespace from PDF positions within each consecutive block."""
    group = []
    def flush():
        if group:
            left = min(event["x0"] for event in group)
            for event in group:
                spaces = round((event["x0"] - left) / max(event.get("char_width", 6), 1))
                event["code_text"] = " " * max(0, spaces) + event["text"]
            group.clear()
    for event in events:
        if event.get("is_code"):
            group.append(event)
        else:
            flush()
    flush()


def _merge_continued_tables(blocks):
    """Join adjacent table fragments across PDF pages with matching headers."""
    result = []
    previous_page = None
    for source in blocks:
        block = dict(source)
        page = block.pop("_source_page", None)
        if (result and block.get("type") == "table" and result[-1].get("type") == "table"
                and block.get("headers") and block["headers"] == result[-1].get("headers")
                and page is not None and previous_page is not None and page == previous_page + 1):
            if result[-1].get("rowSpans") or block.get("rowSpans"):
                result[-1]["rowSpans"] = (
                    result[-1].get("rowSpans", [[1] * len(r) for r in result[-1].get("rows", [])])
                    + block.get("rowSpans", [[1] * len(r) for r in block.get("rows", [])]))
            result[-1]["rows"] = result[-1].get("rows", []) + block.get("rows", [])
        else:
            result.append(block)
        previous_page = page
    return result


def _repair_split_table_columns(blocks):
    """Join a borderless first column back to its detected description table."""
    result = []
    i = 0
    while i < len(blocks):
        table = blocks[i]
        following = blocks[i + 1:i + 3]
        if (table.get("type") == "table" and table.get("headers") == ["Description"]
                and not table.get("rowSpans") and i + 1 < len(blocks)):
            first = blocks[i + 1]
            header = re.fullmatch(r"(Bug ID|Feature ID)\s+(.+)", first.get("text", ""))
            if first.get("type") == "paragraph" and header and _looks_like_id(header[2]):
                labels = [header[2]]
                cursor = i + 2
                rows = table.get("rows", [])
                while cursor < len(blocks) and len(labels) < len(rows):
                    candidate = blocks[cursor]
                    if candidate.get("type") != "paragraph" or not _looks_like_id(candidate.get("text", "")):
                        break
                    labels.append(candidate["text"])
                    cursor += 1
                if len(labels) == len(rows) and all(len(row) == 1 for row in rows):
                    result.append({**table, "headers": [header[1], "Description"],
                                   "rows": [[label, *row] for label, row in zip(labels, rows)]})
                    i = cursor
                    continue
        if (table.get("type") == "table" and table.get("headers") == ["Description"]
                and len(following) == 2 and following[0].get("type") == "paragraph"
                and following[0].get("bold") and following[1].get("type") == "code"):
            labels = following[1].get("text", "").splitlines()
            rows = table.get("rows", [])
            if len(labels) == len(rows) and all(len(r) == 1 for r in rows):
                result.append({"type": "table", "headers": [following[0]["text"], "Description"],
                               "rows": [[label, *row] for label, row in zip(labels, rows)]})
                i += 3
                continue
        result.append(table)
        i += 1
    return result


def _markdown_preserves_structure(markdown, blocks):
    """Do not replace structured content with Markdown that drops data/formatting."""
    if any(b.get("rowSpans") for b in blocks):
        return False  # GFM tables cannot preserve merged rows.
    def tokens(text):
        return set(re.findall(r"[a-z0-9]+", text.lower()))
    rendered_tokens = tokens(markdown)
    for block in blocks:
        kind = block.get("type")
        if kind == "heading":
            continue  # The section title is rendered separately.
        if kind == "table":
            text = " ".join(block.get("headers", []) + [c for row in block.get("rows", []) for c in row])
            if "|" not in markdown or not tokens(text).issubset(rendered_tokens):
                return False
        elif kind == "code":
            if "```" not in markdown or not tokens(block.get("text", "")).issubset(rendered_tokens):
                return False
        elif kind == "list":
            if block.get("ordered") and not re.search(r"(?m)^\s*" + str(block.get("start", 1)) + r"\. ", markdown):
                return False
            if (not re.search(r"(?m)^\s*(?:[-*+] |\d+\. )", markdown)
                    or not tokens(" ".join(block.get("items", []))).issubset(rendered_tokens)):
                return False
        elif kind == "paragraph":
            if not tokens(block.get("text", "")).issubset(rendered_tokens):
                return False
    return True


def _remove_repeated_section_title(section):
    """The report supplies the section title; keep it out of the body once."""
    blocks = section.get("blocks", [])
    title = re.sub(r"[^a-z0-9]", "", section.get("title", "").lower())
    if (blocks and title and blocks[0].get("type") == "heading"
            and re.sub(r"[^a-z0-9]", "", blocks[0].get("text", "").lower()) == title):
        section["blocks"] = blocks[1:]
    blocks = section.get("blocks", [])
    for index, block in enumerate(blocks[:-1]):
        if (block.get("type") == "paragraph" and block.get("bold")
                and blocks[index + 1].get("type") == "table"
                and re.sub(r"[^a-z0-9]", "", block.get("text", "").lower()) == title):
            blocks[index] = {"type": "heading", "level": 6, "text": block["text"]}


def _normalize_section_boundaries(sections):
    """Remove running headers and a next-section title stranded at a page break."""
    key = lambda text: re.sub(r"[^a-z0-9]", "", text.lower())
    titles = {key(section.get("title", "")) for section in sections}
    for section in sections:
        _remove_repeated_section_title(section)
        own = key(section.get("title", ""))
        blocks = [block for block in section.get("blocks", [])
                  if not (block.get("type") == "paragraph" and not block.get("bold")
                          and own and key(block.get("text", "")) == own)]
        if (blocks and blocks[-1].get("type") in {"paragraph", "heading"}
                and key(blocks[-1].get("text", "")) in titles - {own, ""}):
            blocks.pop()
        merged = []
        for block in blocks:
            if (merged and block.get("type") == "list" and merged[-1].get("type") == "list"
                    and bool(block.get("ordered")) == bool(merged[-1].get("ordered"))
                    and (not block.get("ordered") or block.get("start", 1) == merged[-1].get("start", 1) + len(merged[-1].get("items", [])))):
                merged[-1] = {**merged[-1], "items": merged[-1].get("items", []) + block.get("items", [])}
            else:
                merged.append(block)
        section["blocks"] = merged


def _add_bookmarked_sections(pdf_path, version_data, section_pages):
    """Discover rich sections from this document's outline, not a title allowlist.

    Descendants of issue chapters are categories, not independent rich sections.
    Truncated or ambiguous bookmark labels cannot safely rename extracted text.
    """
    import pymupdf
    from collections import Counter
    with pymupdf.open(str(pdf_path)) as doc:
        toc = doc.get_toc()
        counts = Counter(_title_to_slug(title) for _, title, _ in toc)
        ancestors = []
        entries = []
        issue_keys = {"new_features", "known_issues", "resolved-issues",
                      "changes_cli", "changes_default", "changes_tablesize"}
        for level, title, first_page in toc:
            while ancestors and ancestors[-1][0] >= level:
                ancestors.pop()
            key = _match_section(title) or _title_to_slug(title)
            category = any(parent_key in issue_keys for _, parent_key in ancestors)
            ancestors.append((level, key))
            if not (1 <= first_page <= len(doc)):
                continue
            if category or key in issue_keys or key == "special_notices":
                entries.append((None, title, first_page))
                continue
            if title.rstrip().endswith(('...', '…')) or counts[_title_to_slug(title)] != 1:
                continue
            existing = version_data.get(key)
            if existing is not None and not isinstance(existing, dict):
                continue
            if existing is None:
                version_data[key] = {"title": title, "blocks": []}
            else:
                existing['title'] = title
            entries.append((key, title, first_page))
        # Include the boundary page: two sections may share it. Markdown is
        # subsequently scoped by heading, never assigned from a whole page.
        for i, (key, _, start) in enumerate(entries):
            if key is not None:
                end = entries[i + 1][2] if i + 1 < len(entries) else len(doc)
                section_pages[key] = list(range(start - 1, min(end, len(doc))))


def _repair_link_spans(markdown, anchors):
    """Use PDF annotation text to correct overly broad Markdown link labels."""
    def replace(match):
        label, target = match.group(1), match.group(2)
        candidates = [text for url, text in anchors if url == target and text.strip()]
        for text in sorted(candidates, key=len, reverse=True):
            pattern = r"\s+".join(re.escape(word) for word in text.split())
            found = re.search(pattern, label)
            if found:
                return label[:found.start()] + "[" + found.group() + "](" + target + ")" + label[found.end():]
        return match.group()
    return re.sub(r"\[([^\]]+)\]\(([^\s)]+)\)", replace, markdown)


def _extract_page_markdown(pdf_path, page_number, *, document=None, header_info=None):
    import pymupdf
    if document is None:
        with pymupdf.open(str(pdf_path)) as opened:
            return _extract_page_markdown(pdf_path, page_number, document=opened,
                                          header_info=header_info)
    markdown = _pymupdf4llm.to_markdown(document, pages=[page_number], hdr_info=header_info)
    page = document[page_number]
    anchors = [(link["uri"], page.get_textbox(link["from"]))
               for link in page.get_links() if link.get("uri")]
    return _repair_link_spans(markdown, anchors)


def _scope_markdown(markdown: str, title: str, section_titles: list[str]) -> Optional[str]:
    """Return only the requested heading's content, never an entire shared page.

    If a heading cannot be identified, callers retain their scoped blocks instead
    of displaying text from an uncertain page range.
    """
    def key(text):
        return re.sub(r"[^a-z0-9]", "", text.lower())
    wanted = key(title)
    if not wanted:
        return None
    boundaries = {key(t) for t in section_titles if key(t) != wanted}
    lines = markdown.splitlines()
    start, level = None, None
    for i, line in enumerate(lines):
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line.strip())
        label = heading.group(2) if heading else line.strip().strip("*")
        if key(label) == wanted:
            start, level = i + 1, len(heading.group(1)) if heading else None
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start, len(lines)):
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", lines[i].strip())
        label = heading.group(2) if heading else lines[i].strip().strip("*")
        if key(label) == wanted:
            continue  # Repeated page header in a multi-page section.
        if key(label) in boundaries or (heading and level and len(heading.group(1)) <= level):
            end = i
            break
    return "\n".join(line for line in lines[start:end] if key(line) not in {wanted} and not _PDF_FOOTER_RE.match(line.strip().strip("*"))).strip() or None


def _pair_issue_descriptions(
    ids: list[tuple[int, float, Optional[str], str]],
    descs: list[tuple[int, float, Optional[str], str]],
) -> list[tuple[Optional[str], str, Optional[str]]]:
    """
    Pair each (page, y, cat, id) with the closest description row on the same
    page by y-distance.  Returns [(id_cat, desc, tbl_cat)] in the same order
    as `ids`.  Consumed description rows are removed so they cannot be reused.
    """
    desc_pool = list(descs)
    result = []
    for id_page, id_y, id_cat, _id in ids:
        best_i, best_dist = -1, float("inf")
        for i, (d_page, d_y, _d_cat, _desc) in enumerate(desc_pool):
            if d_page == id_page:
                dist = abs(d_y - id_y)
                if dist < best_dist:
                    best_dist, best_i = dist, i
        if best_i >= 0:
            _, _, tbl_cat, desc = desc_pool.pop(best_i)
        else:
            tbl_cat, desc = id_cat, ""
        result.append((id_cat, desc, tbl_cat))
    # Headerless continuation rows have no ID on the new page. Nearest-row
    # matching above leaves them unconsumed; attach only rows preceding every
    # ID on that page to the final issue on an earlier page of this section.
    for d_page, d_y, d_cat, desc in sorted(desc_pool, key=lambda item: (item[0], item[1])):
        same_page = [y for page, y, _, _ in ids if page == d_page]
        if same_page and d_y >= min(same_page):
            continue
        earlier = [i for i, (page, _, _, _) in enumerate(ids) if page < d_page]
        if not earlier:
            continue
        index = max(earlier, key=lambda i: (ids[i][0], ids[i][1]))
        id_cat, text, table_cat = result[index]
        result[index] = (id_cat, (text + " " + desc).strip(), table_cat)
    return result


def parse_pdf(pdf_path, progress=None) -> tuple[Optional[str], dict, list, dict, dict]:
    """
    Parse a FortiGate release notes PDF.

    Returns
    -------
    version : str | None
    version_data : dict  (same shape as scraper output for one version)
    special_notices : list of {title, content}
    section_pages : dict[slug, list[int]]  — page indices used by each rich section
    notice_pages : dict[title, list[int]]  — page indices used by each special notice
    """
    if not PDF_AVAILABLE:
        raise RuntimeError("pdfplumber not installed — run: pip install pdfplumber")

    pdf_path = Path(pdf_path)
    version: Optional[str] = detect_version_from_filename(pdf_path.name)

    # This document's top-level bookmarks also define chapters with new names.
    import pymupdf
    with pymupdf.open(pdf_path) as document:
        outline = document.get_toc()
    root_level = min((entry[0] for entry in outline), default=1)
    document_chapters = {" ".join(title.split()).casefold(): (_match_section(title) or _title_to_slug(title))
                         for level, title, _ in outline if level == root_level}
    rich_keys = _RICH_KEYS | {key for key in document_chapters.values()
                              if key not in {"new_features", "known_issues", "resolved-issues", "changes_cli",
                                             "changes_default", "changes_tablesize", "special_notices"}}

    # State machine
    current_section: Optional[str] = None
    current_section_font_size: float = 0
    current_category: Optional[str] = None
    current_skip: bool = False

    # Accumulate (page_idx, category, rows_with_y) per section key
    section_tables: dict[str, list[tuple[int, Optional[str], list]]] = {}
    # Rich prose sections: slug → {title, blocks}
    rich_sections: dict[str, dict] = {}
    current_rich_slug: Optional[str] = None   # active sub-section slug
    pending_rich_heading: Optional[str] = None  # accumulates multi-line headings
    # Formatting state for rich sections
    rich_base_x0: float = 57.0   # left margin of body text (calibrated per section)
    last_rich_y: Optional[float] = None   # y of previous body-text event
    last_list_item_x0: float = 57.0  # x0 of the line that started the current list item
    # Standalone numeric IDs (Bug ID / Feature ID) found in the left text column,
    # in order of appearance: section → [(page_idx, y, category, id_str)]
    section_text_ids: dict[str, list[tuple[int, float, Optional[str], str]]] = {}
    # Special notices: title → [text lines]
    notice_buckets: dict[str, list[str]] = {}
    current_notice_title: Optional[str] = None
    # Page tracking for image rendering
    current_page_num: int = -1
    section_pages: dict[str, list[int]] = {}   # slug → [page indices containing content]
    notice_pages: dict[str, list[int]] = {}    # notice title → [page indices]

    def _track_section(slug: Optional[str]) -> None:
        if slug:
            lst = section_pages.setdefault(slug, [])
            if current_page_num not in lst:
                lst.append(current_page_num)

    def _track_notice(title: Optional[str]) -> None:
        if title:
            lst = notice_pages.setdefault(title, [])
            if current_page_num not in lst:
                lst.append(current_page_num)

    with pdfplumber.open(str(pdf_path)) as pdf:
        if not version and pdf.pages:
            version = detect_version_from_text(pdf.pages[0].extract_text() or "")

        for page_idx, page in enumerate(pdf.pages):
            if progress:
                progress('reading', page_idx, len(pdf.pages))
            current_page_num = page_idx
            # Record continuation pages for already-active sections/notices
            if current_section == "special_notices":
                _track_notice(current_notice_title)
                _track_section(current_rich_slug)
            elif current_section in rich_keys:
                _track_section(current_rich_slug)
            # ── Locate tables on this page ────────────────────────────────────
            try:
                tbl_objs = [_complete_left_column(page, table) for table in page.find_tables()]
                text_index = _CellTextIndex(page) if tbl_objs else None
                tables_with_pos: list[tuple[Optional[tuple], list]] = [
                    (t.bbox, _extract_table_rows(page, t, text_index)) for t in tbl_objs
                ]
                table_headers = {t.bbox: _table_has_header(page, t) for t in tbl_objs}
                table_spans = {t.bbox: _table_row_spans(t) for t in tbl_objs}
            except Exception:
                # Fallback: no positional info — synthesise fake y-positions
                tables_with_pos = [
                    (None, [(float(i), row or []) for i, row in enumerate(raw or [])])
                    for raw in (page.extract_tables() or [])
                ]
                table_headers = {}
                table_spans = {}

            table_bboxes = [b for b, _ in tables_with_pos if b is not None]

            # ── Extract words outside table areas ─────────────────────────────
            # Use x_tolerance=1 so that narrow inter-word gaps (common in
            # Fortinet PDFs) are treated as word boundaries rather than merged.
            try:
                words = page.extract_words(extra_attrs=["size", "fontname"], x_tolerance=1)
            except Exception:
                words = page.extract_words(x_tolerance=1)

            # Wingdings encodes bullets as ordinary letters. Normalize the glyph
            # using its font, and align it with the adjacent text before grouping.
            for word in words:
                if "wingdings" in word.get("fontname", "").lower() and word["text"] in {"l", "n"}:
                    word["text"] = "•"
                    candidates = [w for w in words if w["x0"] > word["x1"] and abs(w["top"] - word["top"]) < 5]
                    if candidates:
                        word["top"] = min(candidates, key=lambda w: w["x0"])["top"]

            if table_bboxes:
                def _in_any_table(w, bboxes=table_bboxes):
                    wx0, wx1 = w.get("x0", 0), w.get("x1", 0)
                    wt, wb = w.get("top", 0), w.get("bottom", 0)
                    for bx0, by0, bx1, by1 in bboxes:
                        if wx0 >= bx0 - 2 and wt >= by0 - 2 and wx1 <= bx1 + 2 and wb <= by1 + 2:
                            return True
                    return False
                words = [w for w in words if not _in_any_table(w)]

            # ── Build an ordered event list (text + tables sorted by y) ───────
            sizes = [w.get("size", 10) for w in words if w.get("size")]
            median_sz = sorted(sizes)[len(sizes) // 2] if sizes else 10

            events: list[dict] = []

            for y_pos, lwords in _words_to_lines(words):
                text = " ".join(w["text"] for w in lwords).strip()
                if not text:
                    continue
                max_sz = max((w.get("size", 0) for w in lwords), default=0)
                # Filter tiny single-character bullet markers (Symbol/Wingdings fonts).
                # These appear as a separate sub-5pt glyph ('l', 'n', etc.) alongside
                # the actual list-item text; the text line itself carries all the content.
                if max_sz < 5 and len(text) <= 3:
                    continue
                x0 = min(w["x0"] for w in lwords)

                # Classify line by font: code (Consolas etc.) or bold (Inter-Bold etc.)
                n = len(lwords)
                code_n = sum(1 for w in lwords if _CODE_FONT_RE.search(w.get("fontname", "")))
                bold_n = sum(
                    1 for w in lwords
                    if _BOLD_FONT_RE.search(w.get("fontname", ""))
                    and not _CODE_FONT_RE.search(w.get("fontname", ""))
                )
                is_code_line = n > 0 and code_n / n >= 0.8
                is_bold_line = n > 0 and bold_n / n >= 0.8 and not is_code_line

                events.append({
                    "y": y_pos,
                    "kind": "text",
                    "text": text,
                    "large": max_sz > median_sz * 1.08,
                    "font_size": max_sz,
                    "x0": x0,
                    "is_code": is_code_line,
                    "char_width": sum((w["x1"] - w["x0"]) for w in lwords) / max(sum(len(w["text"]) for w in lwords), 1),
                    "is_bold": is_bold_line,
                })

            for bbox, rwy in tables_with_pos:
                if rwy:
                    events.append({
                        "y": bbox[1] if bbox else 9999,
                        "kind": "table",
                        "rows_with_y": rwy,
                        "rows": [cells for _, cells in rwy],
                        "has_header": table_headers.get(bbox, True),
                        "rowSpans": table_spans.get(bbox, []),
                    })

            events.sort(key=lambda e: e["y"])
            _indent_code_events(events)

            # ── Process events in vertical order ─────────────────────────────
            for ev in events:
                if ev["kind"] == "text":
                    line = ev["text"]

                    # ── Special-notices title continuation check ───────────────
                    # Must happen BEFORE _match_section / _is_skippable so that
                    # words like "limitations" or "addresses" — which would
                    # otherwise match skip patterns — are correctly appended to
                    # an in-progress multi-line title.
                    if (current_section == "special_notices"
                            and current_notice_title is not None
                            and not notice_buckets.get(current_notice_title)
                            and ev["large"] and len(line) < 120
                            and ev.get("font_size", 0) < current_section_font_size):
                        new_title = current_notice_title + " " + line
                        notice_buckets[new_title] = notice_buckets.pop(
                            current_notice_title, []
                        )
                        current_notice_title = new_title
                        # Also rename the in-progress rich section
                        if current_rich_slug and current_rich_slug in rich_sections:
                            old = rich_sections.pop(current_rich_slug)
                            new_slug = _title_to_slug(new_title)
                            old["title"] = new_title
                            if old["blocks"] and old["blocks"][0].get("type") == "heading":
                                old["blocks"][0]["text"] = new_title
                            rich_sections[new_slug] = old
                            current_rich_slug = new_slug
                        continue

                    sec = document_chapters.get(" ".join(line.split()).casefold()) or _match_section(line)
                    if sec and ev["y"] < 65 and ev.get("font_size", 0) < 14:
                        continue  # Running page header, not a new chapter.
                    if (sec is not None
                            and current_section in {"known_issues", "resolved-issues", "new_features"}
                            and ev.get("font_size", 0) < current_section_font_size):
                        current_category = line
                        continue  # A smaller heading inside an issue chapter is a category.
                    if sec is not None:
                        if sec == "_skip":
                            # Known sections we intentionally ignore (e.g. GUI behavior)
                            current_skip = True
                            current_section = None
                            current_notice_title = None
                            pending_rich_heading = None
                        elif sec == current_section:
                            # Same heading as the active section — this is a repeated
                            # page-continuation header (Fortinet prints the chapter name
                            # at the top of every page).  Ignore it so that content on
                            # subsequent pages flows into the correct sub-section.
                            pass
                        else:
                            current_section = sec
                            current_section_font_size = ev.get("font_size", 0)
                            current_category = None
                            current_skip = False
                            current_notice_title = None
                            section_tables.setdefault(sec, [])
                            if sec in rich_keys:
                                # Initialise a default slug for section intro content
                                current_rich_slug = sec
                                _track_section(sec)
                                pending_rich_heading = None
                                last_rich_y = None
                                rich_base_x0 = 57.0
                                last_list_item_x0 = 57.0
                                rich_sections.setdefault(sec, {
                                    "title": line,
                                    "blocks": [],
                                })
                            elif sec == "special_notices":
                                # Reset rich state — special_notices uses dual-mode parsing
                                current_rich_slug = None
                                pending_rich_heading = None
                                last_rich_y = None
                                rich_base_x0 = 57.0
                                last_list_item_x0 = 57.0
                            else:
                                pending_rich_heading = None
                        continue

                    if _is_skippable(line):
                        current_skip = True
                        current_section = None
                        current_notice_title = None
                        continue

                    if current_skip or current_section is None:
                        continue

                    if current_section == "special_notices":
                        # Skip page-footer lines
                        if _PDF_FOOTER_RE.match(line):
                            continue
                        # Larger-than-body text = sub-notice title.
                        # (Multi-line title continuation is handled before this block.)
                        if ev["large"] and len(line) < 120:
                            current_notice_title = line
                            notice_buckets.setdefault(line, [])
                            _track_notice(line)
                            # Also start a rich section so notice appears in More Sections
                            slug = _title_to_slug(line)
                            current_rich_slug = slug
                            _track_section(slug)
                            rich_sections[slug] = {
                                "title": line,
                                "blocks": [{"type": "heading", "level": 2, "text": line}],
                            }
                            last_rich_y = None
                            rich_base_x0 = 57.0
                            last_list_item_x0 = 57.0
                        elif current_notice_title is not None:
                            notice_buckets.setdefault(current_notice_title, []).append(line)
                            # Also classify as a rich block for More Sections
                            if current_rich_slug and current_rich_slug in rich_sections:
                                blocks = rich_sections[current_rich_slug]["blocks"]
                                x0 = ev.get("x0", rich_base_x0)
                                y = ev["y"]
                                if last_rich_y is not None and y > last_rich_y:
                                    y_gap = y - last_rich_y
                                else:
                                    y_gap = 999
                                last_rich_y = y
                                is_code = ev.get("is_code", False)
                                is_bold = ev.get("is_bold", False)
                                bullet_m = _BULLET_CHAR_RE.match(line)
                                numbered_m = _NUMBERED_ITEM_RE.match(line)
                                is_indented = x0 > rich_base_x0 + 10
                                if is_code:
                                    if blocks and blocks[-1]["type"] == "code":
                                        blocks[-1]["text"] += "\n" + ev.get("code_text", line)
                                    else:
                                        blocks.append({"type": "code", "text": ev.get("code_text", line)})
                                elif bullet_m:
                                    clean = _BULLET_CHAR_RE.sub("", line).strip()
                                    if blocks and blocks[-1]["type"] == "list" and not blocks[-1].get("ordered"):
                                        blocks[-1]["items"].append(clean)
                                    else:
                                        blocks.append({"type": "list", "items": [clean]})
                                elif numbered_m:
                                    last_list_item_x0 = x0
                                    _append_numbered_item(blocks, line)
                                elif (is_indented and blocks and (
                                        (blocks[-1].get("ordered") and y_gap >= 20)
                                        or (blocks[-1]["type"] == "paragraph" and x0 > rich_base_x0 + 50))):
                                    # A separately positioned warning after a numbered
                                    # list is prose, not an invented next numbered item.
                                    if blocks[-1]["type"] == "paragraph" and y_gap < 20:
                                        blocks[-1]["text"] += " " + line
                                    else:
                                        blocks.append({"type": "paragraph", "text": line})
                                elif is_indented:
                                    is_continuation = (
                                        blocks and blocks[-1]["type"] == "list"
                                        and blocks[-1]["items"]
                                        and y_gap < 20
                                        and x0 > last_list_item_x0 + 8
                                    )
                                    if is_continuation:
                                        blocks[-1]["items"][-1] += " " + line
                                    elif blocks and blocks[-1]["type"] == "list":
                                        last_list_item_x0 = x0
                                        blocks[-1]["items"].append(line)
                                    else:
                                        last_list_item_x0 = x0
                                        blocks.append({"type": "list", "items": [line]})
                                elif line.startswith("|"):
                                    # Pipe-prefixed link item (Fortinet hyperlink lists)
                                    clean = line.lstrip("|").strip()
                                    if clean:
                                        if blocks and blocks[-1]["type"] == "list":
                                            blocks[-1]["items"].append(clean)
                                        else:
                                            blocks.append({"type": "list", "items": [clean]})
                                elif is_bold:
                                    if (blocks and blocks[-1]["type"] == "paragraph"
                                            and blocks[-1].get("bold") and y_gap < 20):
                                        blocks[-1]["text"] += " " + line
                                    else:
                                        blocks.append({"type": "paragraph", "text": line, "bold": True})
                                else:
                                    last_para_text = blocks[-1]["text"] if blocks and blocks[-1]["type"] == "paragraph" else ""
                                    sentence_break = (
                                        last_para_text.endswith((".", "!", "?"))
                                        and line and line[0].isupper()
                                        and y_gap > 13
                                    )
                                    if y_gap > 20 or not blocks or blocks[-1]["type"] != "paragraph" or sentence_break:
                                        blocks.append({"type": "paragraph", "text": line})
                                    else:
                                        blocks[-1]["text"] += " " + line
                        else:
                            # No title yet — use a placeholder
                            notice_buckets.setdefault("__default__", []).append(line)
                    elif current_section in rich_keys:
                        # ── Rich prose section ───────────────────────────────
                        # Skip page-footer lines that appear on every PDF page
                        if _PDF_FOOTER_RE.match(line):
                            continue

                        if ev["large"]:
                            # Sub-section heading (may span multiple lines)
                            if pending_rich_heading is not None:
                                pending_rich_heading += " " + line
                            else:
                                pending_rich_heading = line
                            last_rich_y = None  # reset paragraph tracking
                        else:
                            # Body text
                            if pending_rich_heading is not None:
                                # Commit the accumulated heading as a new sub-section
                                slug = _title_to_slug(pending_rich_heading)
                                current_rich_slug = slug
                                _track_section(slug)
                                rich_sections[slug] = {
                                    "title": pending_rich_heading,
                                    "blocks": [{
                                        "type": "heading",
                                        "level": 2,
                                        "text": pending_rich_heading,
                                    }],
                                }
                                pending_rich_heading = None
                                # Calibrate base indentation from first body line
                                rich_base_x0 = ev.get("x0", 57.0)
                                last_rich_y = None
                                last_list_item_x0 = rich_base_x0

                            if current_rich_slug:
                                blocks = rich_sections[current_rich_slug]["blocks"]
                                x0 = ev.get("x0", rich_base_x0)
                                y = ev["y"]
                                # Negative gap means we crossed a page boundary
                                # (y resets to the top of the new page); treat
                                # it the same as a large gap → new block.
                                if last_rich_y is not None and y > last_rich_y:
                                    y_gap = y - last_rich_y
                                else:
                                    y_gap = 999
                                last_rich_y = y

                                # ── Classify the line ──────────────────────
                                is_code = ev.get("is_code", False)
                                is_bold = ev.get("is_bold", False)
                                bullet_m = _BULLET_CHAR_RE.match(line)
                                numbered_m = _NUMBERED_ITEM_RE.match(line)
                                # Indented beyond normal left margin →
                                # bullet-list item or wrapped numbered-item text
                                is_indented = x0 > rich_base_x0 + 10

                                if is_code:
                                    # Code block — merge consecutive code lines with newline
                                    if blocks and blocks[-1]["type"] == "code":
                                        blocks[-1]["text"] += "\n" + ev.get("code_text", line)
                                    else:
                                        blocks.append({"type": "code", "text": ev.get("code_text", line)})

                                elif bullet_m:
                                    # Explicit bullet character — strip it
                                    clean = _BULLET_CHAR_RE.sub("", line).strip()
                                    if blocks and blocks[-1]["type"] == "list" and not blocks[-1].get("ordered"):
                                        blocks[-1]["items"].append(clean)
                                    else:
                                        blocks.append({"type": "list", "items": [clean]})

                                elif numbered_m:
                                    last_list_item_x0 = x0
                                    _append_numbered_item(blocks, line)
                                elif (is_indented and blocks and (
                                        (blocks[-1].get("ordered") and y_gap >= 20)
                                        or (blocks[-1]["type"] == "paragraph" and x0 > rich_base_x0 + 50))):
                                    # A separately positioned warning after a numbered
                                    # list is prose, not an invented next numbered item.
                                    if blocks[-1]["type"] == "paragraph" and y_gap < 20:
                                        blocks[-1]["text"] += " " + line
                                    else:
                                        blocks.append({"type": "paragraph", "text": line})
                                elif is_indented:
                                    # A line is a wrapped CONTINUATION of the previous item
                                    # only when it is indented DEEPER than the line that
                                    # started that item (e.g. "below." after "1. If …").
                                    # When it is at the SAME x0 as the previous item starter
                                    # it is always a new item — this correctly handles
                                    # bullet lists where every item starts at the same indent.
                                    is_continuation = (
                                        blocks and blocks[-1]["type"] == "list"
                                        and blocks[-1]["items"]
                                        and y_gap < 20
                                        and x0 > last_list_item_x0 + 8
                                    )
                                    if is_continuation:
                                        blocks[-1]["items"][-1] += " " + line
                                    elif blocks and blocks[-1]["type"] == "list":
                                        last_list_item_x0 = x0
                                        blocks[-1]["items"].append(line)
                                    else:
                                        last_list_item_x0 = x0
                                        blocks.append({"type": "list", "items": [line]})

                                elif line.startswith("|"):
                                    # Pipe-prefixed link item (Fortinet hyperlink lists)
                                    clean = line.lstrip("|").strip()
                                    if clean:
                                        if blocks and blocks[-1]["type"] == "list":
                                            blocks[-1]["items"].append(clean)
                                        else:
                                            blocks.append({"type": "list", "items": [clean]})

                                elif is_bold:
                                    # Bold callout / inline heading paragraph.
                                    # Merge wrapped bold lines (y_gap < 20) into one block.
                                    if (blocks and blocks[-1]["type"] == "paragraph"
                                            and blocks[-1].get("bold") and y_gap < 20):
                                        blocks[-1]["text"] += " " + line
                                    else:
                                        blocks.append({"type": "paragraph", "text": line, "bold": True})

                                else:
                                    # Regular paragraph text.
                                    # New paragraph when y-gap is large enough,
                                    # otherwise concatenate (PDF line-wrap).
                                    last_para_text = blocks[-1]["text"] if blocks and blocks[-1]["type"] == "paragraph" else ""
                                    sentence_break = (
                                        last_para_text.endswith((".", "!", "?"))
                                        and line and line[0].isupper()
                                        and y_gap > 13
                                    )
                                    if y_gap > 20 or not blocks or blocks[-1]["type"] != "paragraph" or sentence_break:
                                        blocks.append({"type": "paragraph", "text": line})
                                    else:
                                        blocks[-1]["text"] += " " + line
                    else:
                        # Category heading detection: large text within a section
                        if ev["large"] and _is_category_like(line):
                            current_category = line
                        # Standalone numeric ID in the left column — collect for pairing
                        # with description rows from the right-column table.
                        elif _STANDALONE_ID_RE.match(line):
                            ids = section_text_ids.setdefault(current_section, [])
                            if (ids and ids[-1][0] == current_page_num and ids[-1][3].endswith(",")
                                    and ids[-1][2] == current_category):
                                pg, y, category, prefix = ids[-1]
                                ids[-1] = (pg, y, category, prefix + " " + line.strip())
                            else:
                                ids.append((current_page_num, ev["y"], current_category, line.strip()))

                elif ev["kind"] == "table":
                    if current_section and not current_skip:
                        if current_section in rich_keys or (
                            current_section == "special_notices" and current_rich_slug
                        ):
                            # Rich section table → add as table block
                            rwy = ev.get("rows_with_y", [])
                            if current_rich_slug and rwy and current_rich_slug in rich_sections:
                                rows = [cells for _, cells in rwy]
                                has_header = ev.get("has_header", True)
                                hdrs = [_clean(c) for c in (rows[0] or [])] if has_header else []
                                data_indices = [i for i in range(1 if has_header else 0, len(rows))
                                                if any(_clean(c) for c in (rows[i] or []))]
                                data = [[_clean(c) for c in (rows[i] or [])] for i in data_indices]
                                if hdrs or data:
                                    rich_sections[current_rich_slug]["blocks"].append({
                                        "type": "table",
                                        "_source_page": current_page_num,
                                        "headers": hdrs,
                                        "rows": data,
                                        **({"rowSpans": [ev["rowSpans"][i] for i in data_indices]}
                                           if any(n != 1 for row in ev.get("rowSpans", []) for n in row) else {}),
                                    })
                        else:
                            section_tables.setdefault(current_section, []).append(
                                (current_page_num, current_category, ev.get("rows_with_y") or
                                 [(float(i), row) for i, row in enumerate(ev.get("rows", []))])
                            )

            # The report retains extracted text, not pdfplumber page objects.
            # Release layout/character caches before processing the next page.
            page.close()

    # ── Build final data structures ───────────────────────────────────────────
    version_data: dict = {}

    # ── Helper: extract flat description list from section tables ────────────────
    def _flat_descs(sec_key: str, id_key: str) -> list[tuple[int, float, Optional[str], str]]:
        """Return [(page_idx, first_y, table_category, description)] for all parsed rows."""
        out: list[tuple[int, float, Optional[str], str]] = []
        for page_idx, cat, rows_with_y in section_tables.get(sec_key, []):
            for item in _parse_id_desc_table(rows_with_y, id_key):
                if item.get("_continuation") and out:
                    previous_page, previous_y, previous_category, text = out[-1]
                    out[-1] = (previous_page, previous_y, previous_category, text + " " + item["Description"])
                else:
                    out.append((page_idx, item["_first_y"], cat, item["Description"]))
        return out

    # ── New features ──────────────────────────────────────────────────────────
    if "new_features" in section_tables:
        feat_ids = section_text_ids.get("new_features", [])
        all_descs = _flat_descs("new_features", "Feature ID")
        feats: list[dict] = []
        if feat_ids:
            for (id_cat, desc, tbl_cat), (_, _, _, fid) in zip(
                _pair_issue_descriptions(feat_ids, all_descs), feat_ids
            ):
                feats.append({
                    "category": id_cat or tbl_cat or "General",
                    "Feature ID": fid,
                    "Description": desc,
                })
        else:
            # Fallback: no IDs collected (unusual PDF layout)
            for _pg, cat, rows_with_y in section_tables["new_features"]:
                for item in _parse_id_desc_table(rows_with_y, "Feature ID"):
                    feats.append({
                        "category": cat or "General",
                        "Feature ID": item["Feature ID"],
                        "Description": item["Description"],
                    })
        if feats:
            version_data["new_features"] = feats

    # ── Issues sections (known / resolved) ────────────────────────────────────
    for sec_key in ("known_issues", "resolved-issues"):
        if sec_key not in section_tables:
            continue
        bug_ids = section_text_ids.get(sec_key, [])
        all_descs = _flat_descs(sec_key, "Bug ID")
        issues: list[dict] = []
        if bug_ids:
            for (id_cat, desc, tbl_cat), (_, _, _, bid) in zip(
                _pair_issue_descriptions(bug_ids, all_descs), bug_ids
            ):
                issues.append({
                    "category": id_cat or tbl_cat or "General",
                    "Bug ID": bid,
                    "Description": desc,
                })
        else:
            # Fallback
            for _pg, cat, rows_with_y in section_tables[sec_key]:
                for item in _parse_id_desc_table(rows_with_y, "Bug ID"):
                    issues.append({
                        "category": cat or "General",
                        "Bug ID": item["Bug ID"],
                        "Description": item["Description"],
                    })
        if issues:
            version_data[sec_key] = issues

    # ── Simple changes sections ───────────────────────────────────────────────
    for sec_key in ("changes_cli", "changes_default", "changes_tablesize"):
        if sec_key not in section_tables:
            continue
        bug_ids = section_text_ids.get(sec_key, [])
        all_descs = _flat_descs(sec_key, "Bug ID")
        items: list[dict] = []
        if bug_ids:
            for (_id_cat, desc, _tbl_cat), (_, _, _, bid) in zip(
                _pair_issue_descriptions(bug_ids, all_descs), bug_ids
            ):
                items.append({"Bug ID": bid, "Description": desc})
        else:
            # Fallback
            for _pg, _, rows_with_y in section_tables[sec_key]:
                for item in _parse_id_desc_table(rows_with_y, "Bug ID"):
                    items.append({"Bug ID": item["Bug ID"], "Description": item["Description"]})
        if items:
            version_data[sec_key] = items

    # ── Rich prose sections (More Sections) ──────────────────────────────────
    # Safety-net: skip slugs whose title ends with a bare page number —
    # these were created from TOC entries (e.g. "Resolved issues 34")
    # that slipped past the section-pattern guard.
    _trailing_num_re = re.compile(r'\s+\d+\s*$')
    for slug, section in rich_sections.items():
        if section.get("blocks") and not _trailing_num_re.search(section.get("title", "")):
            section["blocks"] = _repair_split_table_columns(_merge_continued_tables(_fix_pipe_lists(section["blocks"])))
            version_data[slug] = section

    # Special notices
    # Drop __default__ — it collects pre-title text (typically a TOC list) that
    # should not be rendered as a notice entry.
    notice_buckets.pop("__default__", None)
    special_notices: list[dict] = []
    for title, lines in notice_buckets.items():
        content = " ".join(lines).strip()
        if title or content:
            notice = {"title": title, "content": content}
            blocks = rich_sections.get(_title_to_slug(title), {}).get("blocks", [])
            if blocks:
                notice["blocks"] = blocks[1:] if blocks[0].get("type") == "heading" else blocks
            special_notices.append(notice)

    # ── Upgrade rich sections and notices to markdown via pymupdf4llm ─────────
    # pymupdf4llm extracts proper GFM markdown (headings, tables, code blocks,
    # lists) from specific page ranges — far more accurate than the pdfplumber
    # block extraction above, and searchable unlike the old PNG image approach.
    if progress:
        progress('formatting')
    if PYMUPDF4LLM_AVAILABLE:
        _add_bookmarked_sections(pdf_path, version_data, section_pages)
        import pymupdf
        # Header detection scans the entire document. Reuse its result and the
        # open document across pages, preserving the same document-wide rules.
        with pymupdf.open(str(pdf_path)) as document:
            try:
                header_info = _pymupdf4llm.IdentifyHeaders(document)
            except Exception:
                header_info = None  # Keep the existing per-section fallback.
            # Extract each page once. A page can contain several notices, so assigning
            # its full Markdown to every notice duplicates unrelated source content.
            page_markdown: dict[int, str] = {}
            titles = [v.get("title", "") for v in version_data.values() if isinstance(v, dict)]
            titles += [n.get("title", "") for n in special_notices]
            def scoped_markdown(title, pages):
                try:
                    for page in pages:
                        if page not in page_markdown:
                            page_markdown[page] = _extract_page_markdown(pdf_path, page, document=document, header_info=header_info)
                    return _scope_markdown("\n\n".join(page_markdown[p] for p in pages), title, titles)
                except Exception:
                    return None  # Retain the section-scoped structured extraction.

            for slug, section in version_data.items():
                if isinstance(section, dict) and "blocks" in section:
                    md = scoped_markdown(section.get("title", ""), section_pages.get(slug, []))
                    if md and _markdown_preserves_structure(md, section["blocks"]):
                        section["markdown"] = md
            for notice in special_notices:
                md = scoped_markdown(notice.get("title", ""), notice_pages.get(notice.get("title", ""), []))
                if md and _markdown_preserves_structure(md, notice.get("blocks", [])):
                    notice["markdown"] = md

    _normalize_section_boundaries([section for section in [*version_data.values(), *special_notices]
                                   if isinstance(section, dict) and 'blocks' in section])
    if progress:
        progress('finalizing')
    from .pdf_issue_markdown import add_issue_markdown
    add_issue_markdown(pdf_path, version_data)
    from .pdf_table_format import add_table_formatting
    from .pdf_table_lists import add_table_lists, _native_section_pages
    import pymupdf
    with pymupdf.open(pdf_path) as document:
        section_pages = _native_section_pages(document, version_data, section_pages)
    add_table_formatting(pdf_path, version_data, section_pages)
    from .pdf_callouts import add_callouts
    add_callouts(pdf_path, version_data, special_notices, section_pages, notice_pages)
    add_table_lists(pdf_path, version_data, section_pages)
    from .pdf_table_continuations import restore_table_continuations
    restore_table_continuations(pdf_path, version_data, section_pages)
    from .pdf_prose_format import add_prose_formatting, sync_notice_formatting
    add_prose_formatting(pdf_path, version_data, section_pages)
    from .pdf_heading_levels import align_heading_levels
    align_heading_levels(pdf_path, version_data)
    sync_notice_formatting(version_data, special_notices)
    return version, version_data, special_notices, section_pages, notice_pages
