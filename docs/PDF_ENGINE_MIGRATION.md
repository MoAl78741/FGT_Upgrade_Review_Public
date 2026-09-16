# PDF engine replacement audit

## Phase 0 gate

Baseline commit: `ccacf5c`. Five real documents, 274 pages, 1,444 parsed rows.
The unchanged pipeline passed a full repeat comparison. See the private golden
README for the narrowly scoped intermediate-Markdown empty-line exception.
Existing PDF regressions: 56 passed. Content parity: 24 passed. Baseline contract:
2 passed. Runtime parser and dependencies were unchanged at the baseline commit.

## Phase 1 inventory (completed before replacement)

Both maintained editions have the same PDF call sites. Recursive tracked-source
search covered `fitz`, `pymupdf`, and `pdf2image` case-insensitively, including
backend, CLI, tests, scripts, requirements, documentation and deployment files.
No active `fitz` or `pdf2image` imports or rasterization calls were found. A
historical security URL contains `/fitz/`; that is not a runtime dependency.

| Existing API | Call sites | Purpose | Replacement |
|---|---|---|---|
| `open`, context manager, indexing, iteration, `len`, `close` | `pdf_parser`, all eight `pdf_*` formatting helpers, `parse_process`, golden harness | Document/page lifecycle and count | Shared job-local document abstraction; PDFium count/lifecycle, pdfplumber page data |
| `Document.needs_pass` | `parse_process` | Reject encrypted uploads | PDFium password/load error, including empty-password encryption policy |
| `Document.metadata` | golden harness | Record source metadata | PDFium metadata |
| `Document.get_toc` | parser, issue Markdown, heading levels, table lists/prose/continuations | Chapter bounds, unknown-title discovery, heading hierarchy | PDFium bookmarks and destinations |
| `Page.get_text('dict')`, including `clip` | `pdf_issue_markdown._page_lines`; all typography helpers through this function | Ordered lines, spans, fonts, sizes and bounding boxes | pdfplumber characters grouped into original text-flow lines |
| `Page.get_text()` | golden diagnostics | Full native per-page text | pdfplumber text, with engine-order differences reported |
| `Page.get_links`, `get_textbox` | parser page Markdown and issue inline rendering | URI annotations and exact anchor labels | pdfplumber hyperlinks and bounded characters |
| `Page.find_tables().tables`, `.rows`, `.cells`, `.bbox`, `.extract` | issue Markdown, table formatting/lists | Nested tables, code cells and list recovery | pdfplumber table geometry/extraction |
| `Page.get_image_info` | callouts | Identify note-icon locations, not render remote images | pdfplumber image bounds |
| `Page.get_drawings`, path `rect`, `items` (`re`, `l`) | callouts and table continuations | Bordered notes and partial table rows | pdfplumber rectangles, curves and edges |
| `Rect`, width/height/x0/y0/x1/y1, `Page.rect` | callouts, continuations, issue formatting | Geometry and relative page limits | Application-owned geometry values; PDFium page dimensions |
| `pymupdf4llm.use_layout(False)` | parser import | Select legacy Markdown engine | Removed; no layout engine dependency |
| `pymupdf4llm.IdentifyHeaders` | parser rich formatting | Document-wide heading detection | PDF outline and pdfplumber font evidence |
| `pymupdf4llm.to_markdown` | parser rich formatting | Page Markdown for rich sections/notices | Application-owned serializer using pdfplumber text/tables and existing block renderers |
| `new_page`, `insert_text`, `draw_rect`, `draw_line`, `new_shape`, `draw_polyline`, `finish`, `commit`, `insert_image`, `set_toc`, `save` | Synthetic fixtures in 10 PDF/performance/generalization test modules | Generate typography, geometry and outline regression PDFs | ReportLab test fixture builder (BSD); no engine fallback |
| PyMuPDF test imports/`importorskip`, `PYMUPDF4LLM_AVAILABLE` monkeypatch | PDF tests | Fixture setup / disable rich Markdown | Replacement fixture builder and engine-neutral formatting flag |

Dependency inventory: direct `pymupdf4llm`; locked `pymupdf`, `pymupdf-layout`
and `pymupdf4llm` at 1.28.2, with layout-only transitive dependencies. Regenerate
the lock from roots rather than deleting three lines. `pypdfium2` is already
transitive through pdfplumber and becomes explicit. Runtime Docker target on
this Mac is **linux/amd64**, Python 3.12; macOS wheels cannot satisfy that build.

Documentation references needing updates: THIRD_PARTY_NOTICES, FEATURES,
LICENSING, historical SECURITY evidence. Release packaging currently walks all
tests and must explicitly exclude the private golden corpus. Docker already
excludes tests. No third-party engine implementation may be copied into the new
adapter or serializer. Historical baseline references do not ship engine code.

## Non-negotiable constraints

No PyMuPDF, MuPDF, layout package, or Markdown wrapper in the maintained runtime,
development/test dependency tree, vendored wheels, or new image layers. No
optional extraction fallback. Keep the isolated subprocess, resource limits,
and network/filesystem confinement. Audit PDFium's bundled third-party notices
as well as its wrapper license. Public AGPL licensing remains unchanged; removing
a dependency alone does not establish rights to relicense all application code.

## Phase 3 reconciliation

The final clean-environment rerun passes against the replacement capture, while
`test_pdf_migration.py` checks every result change against the immutable baseline.
Page counts, metadata, outlines, original pdfplumber page text, source entries,
IDs/descriptions/categories, section keys and boundaries are unchanged for all
five documents. Independent benchmark results also match the clean captures.

| Version | Pages | Rows | Reviewed JSON changes |
|---|---:|---:|---:|
| 6.4.2 | 63 | 483 | 5 |
| 7.0.14 | 52 | 173 | 24 |
| 7.2.8 | 76 | 601 | 3 |
| 7.4.11 | 40 | 108 | 0 |
| 7.6.6 | 43 | 79 | 0 |

Every accepted result change includes exact before/after values and justification
in the private `tests/golden/approved-pdf-differences.json`. Source pages were
rendered with PDFium and visually inspected. Accepted changes recover table-cell
paragraphs, italics/bullets, separate bold product lines, and two command lines
that the old engine split at same-baseline span boundaries. One Markdown value
loses a redundant space after a nonbreaking space; its original Description is
unchanged. No source rows are dropped, added or rewritten.

Raw page diagnostics necessarily differ between engines. The manifest records
changed page indexes and before/after hashes; both complete captures are kept.
New page text exactly equals the pre-existing pdfplumber page text for every page.
Final scoped report output is checked separately, so diagnostic differences cannot
hide changes to displayed source data. The original baseline is never regenerated.

## Performance and confinement

On this Mac, using the same Linux AMD64 container limits (two CPUs, 2 GiB, no
network, dropped capabilities, read-only root), the 76-page 7.2.8 PDF took about
153 seconds with the previous image and 198 seconds with the replacement, about
29% longer. These are single-run measurements under variable host load, not a
capacity guarantee. Both outputs matched their respective goldens exactly.

The existing 30-minute job limit and two-worker default remain unchanged. A large
batch can exceed 30 minutes even though each PDF is within limits. For a batch
near 19 long PDFs, allow additional margin (for example 90 minutes, subject to
operator resource policy) or split it. Pro administrators can change Processing
settings; public operators control the maximum with JOB_TIMEOUT_SECONDS. Public
visitors can only choose a per-attempt value within that operator maximum.

The new image's sandbox probe still denies networking and sibling-job reads and
writes. Malformed PDFs produce an actionable message. Password-protected and
empty-user-password encrypted PDFs are rejected. PDF parsing remains inside the
existing isolated subprocess; no new config-upload or network capability exists.

## Dependency and distribution evidence

The Linux candidate built successfully with `docker build --network=none` using
vendored wheels, npm cache and Debian packages. Matching pinned base-image archives
are included for offline loading. The wheel target is Linux AMD64, not a Mac wheel
assumed portable. Separate Intel macOS development wheels/lock are supplied.

The built-image inventory and fresh development environments report no forbidden
engine distribution, module or installed filename. Original Python/npm notices,
including PDFium BUILD_LICENSES, accompany the exact vendored versions. CI repeats
the engine audit and sandbox probe, alongside advisory scanning. See OFFLINE_BUILD.md.

Validation: 63 PDF/worker-focused tests; 181 Pro security, rendering/API parity,
worker and packaging tests; 238 corresponding public checks; four private golden
contract/reconciliation checks; complete five-PDF rerun. The corrected command
lines also passed through the real standalone HTML/print renderer without remote
assets. These counts overlap and should not be added together.
