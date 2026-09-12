# Release-note parser rules

Parsing must depend on source structure, not on an uploaded file's identity.
The PDF and HTML parsers support selectable-text FortiOS release notes. A future
publisher redesign may need new structural support; the parser must not invent
text to make two editions agree.

## Allowed evidence

- PDF outlines, heading sizes, page order, drawn cell boundaries, native text,
  font styles, link annotations, and observed list indentation.
- HTML headings, lists, tables, cell spans, code elements, and publisher CSS
  conventions that identify a kind of content across documents.
- Stable section names used to map release-note concepts into the application
  schema, such as Known issues and Changes in CLI. Other chapters remain rich
  source sections; they do not require a new title allowlist.
- Each web release's own table of contents and URLs. Historical numeric page IDs
  in `constants.py` are legacy export-link defaults, not scraping fallbacks.

## Prohibited shortcuts

Do not branch on a particular version, filename, document hash, issue ID, page
number, or known paragraph to substitute, delete, move, or format its content.
Do not merge code-example rows merely because their headers say Before upgrade
and After upgrade. Preserve the native rows and their font-derived code blocks.
Do not force a named subsection into another chapter to hide a difference
between the website and the PDF. Preserve source headings and their content.

Historical report annotations may identify specific revisions or duplicates.
Those are observations stored with the affected reports, not parser rules, and
must not be applied to unrelated imports.

## Regression requirements

For an extraction fix, add a fixture that describes the structural failure and
vary its content. Relevant variations include unfamiliar chapter/category names,
unseen version strings and issue IDs, renamed table headers, different command
verbs, changed page dimensions, and newly assigned web page IDs. Include a
negative case where the evidence is insufficient for the transformation.

Real source fixtures are useful regressions, but a version-specific fixture alone
is insufficient evidence that a rule generalizes. Compare both structured output
and rendered text so moving content between sections does not hide a loss.
Selenium fetches HTML through a browser transport and uses the same Python
parsers as requests mode; do not add a second independent content parser there.

Primary regression coverage is in `tests/test_parser_generalization.py`, the
`test_pdf_*` modules, `test_scraper_html.py`, and `test_content_parity.py`.
