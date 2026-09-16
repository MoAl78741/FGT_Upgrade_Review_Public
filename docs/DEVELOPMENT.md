# Development and release guide

[← Project overview](../README.md)

## Source setup

The reload script uses the inherited local development harness. To test public session behavior, run the public Docker configuration behind HTTPS; public mode refuses an HTTP origin. This repository's Dockerfile and Compose defaults select public mode.


Use Python 3.12 and Node.js 22.12+ from a checkout of this version. Run backend commands from the repository root so `fgt_upgrade` is importable. Linux parser isolation requires Landlock (kernel 5.13+) and libseccomp; native macOS uses Seatbelt. Use Docker on Windows.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
(cd frontend && npm ci && npm run build)
./scripts/dev.sh
```

The script starts FastAPI on port 8000 and Vite on port 5173 with automatic reload. Stop both with Ctrl+C. Vite proxies API requests to the backend. The frontend build also generates the shared Node report renderer and local JavaScript API; source installations need these assets for API exports.

For separate terminals:

```sh
.venv/bin/python -m uvicorn backend.main:app --reload --port 8000
# In another terminal:
(cd frontend && npm run dev)
```

Local development defaults to a Development build identity. Runtime data and uploaded documents must stay out of Git.

## Source map

| Path | Responsibility |
| --- | --- |
| `backend/` | API, ownership/authentication, persistence, job dispatch, parser isolation, reviews, and maintenance. |
| `backend/administration.py`, `permissions.py`, `notifications.py` | Operator authentication, domain permissions, event forwarding and mail delivery. |
| `backend/installation_archive.py`, `restore_journal.py`, `certificates.py` | Encrypted backups, interrupted-restore recovery and HTTPS certificate integration. |
| `backend/routers/` | HTTP endpoints and request-level access checks. |
| `backend/pdf_parser.py` | PDF structure and rich-content extraction. |
| `fgt_upgrade/` | Documentation scraping and shared extraction helpers. |
| `frontend/src/pages/` | Import, source-report, review, and account workflows. |
| `frontend/src/components/dashboard/` | Report sections, source rendering, print, and downloads. |
| `frontend/src/config/` | Local configuration parser, feature rules, and browser worker. |
| `frontend/src/utils/` | Shared content, consolidation, comparison, and export helpers. |
| `tests/`, `frontend/tests/` | Backend and browser/content regressions. |
| `scripts/` | Development, catalog refresh, benchmarks, and release tooling. |
| `releases/` | Edition installation guides and environment examples. |

Do not modify historical directories prefixed with `v#`.

## Validation

Install test dependencies into the virtual environment:

```sh
.venv/bin/python -m pip install pytest httpx
```

A focused source-fidelity and presentation check:

```sh
(cd frontend && npm run build && npm run test:content)
.venv/bin/python -m pytest tests/test_content_parity.py tests/test_scraper_html.py tests/test_pdf_parser_units.py tests/test_presentation_api.py -q
```

For security, accounts, reviews, and packaging changes:

```sh
.venv/bin/python -m pytest tests/test_api_coverage.py tests/test_administration.py tests/test_security.py tests/test_team.py tests/test_reviews.py tests/test_maintenance.py tests/test_release_packaging.py -q
```

The [CI workflow](../.github/workflows/security.yml) is the maintained list of automated release checks, including dependency and container scans. Some legacy tools/tests expect a live application or local documents; use the named regression suites rather than assuming every historical script is an isolated unit test.

Verify Linux confinement in a built image:

```sh
docker run --rm --cap-drop ALL --security-opt no-new-privileges \
  fgt-upgrade-review-public:3.0.0 python -m backend.sandbox_check
```

See [SECURITY.md](../SECURITY.md) for open findings. A successful application test or sandbox probe does not clear dependency advisories.

## PDF performance and fidelity

```sh
.venv/bin/python scripts/benchmark_pdf.py \
  --output ./work/pdf-benchmark path/to/release-notes.pdf
```

Multiple PDF paths are accepted. Results include elapsed time, CPU time, row counts, and extracted content for comparisons. Keep outputs private: they contain document text. Compare content as well as timing when changing the parser; throughput improvements must not silently omit sections or alter wording.

Fresh imports use the current parser. Existing reports retain their saved content. An explicitly requested new import or force re-scrape is needed to refresh extraction; deployment alone does not reparse old reports.

## PDF download catalog

The bundled catalog contains version numbers, official document links, and a visible check date. It is a release-note checklist, not a supported firmware upgrade path. Unknown endpoints produce a warning instead of silently dropping releases.

An operator can refresh it before a release:

```sh
.venv/bin/python scripts/update_pdf_catalog.py
```

Review the changes to `frontend/src/data/pdfReleases.json`, then rebuild. This maintenance command needs external networking. Normal PDF imports do not, and the public edition does not scrape documentation to populate the checklist at request time.

## Build identity and source archives

The header and `/api/capabilities` expose the running backend's version, edition, build number, and source revision. Use a unique build number for a release image:

```sh
docker build \
  --build-arg BUILD_NUMBER=20260911.12 \
  --build-arg BUILD_REVISION="$(git rev-parse HEAD)" \
  -t fgt-upgrade-review-public:3.0.0 .
```

The number above is an example; choose a new identity for a new build. Package the current public source tree (one edition archive):

```sh
.venv/bin/python scripts/package_releases.py --output ./dist/releases
# Optionally include a prebuilt image and its platform/identity manifest:
.venv/bin/python scripts/package_releases.py --output ./dist/releases \
  --docker-image fgt-upgrade-review-public:3.0.0
```

Archives include source, documentation, locks, notices, checksums, a file manifest, and edition-specific `START-HERE.md` instructions. Runtime databases, uploaded PDFs, environment credentials, and configuration backups are excluded. Review archive contents and dependency notices before publication. Offline image transfer and installation are covered in the [release guides](../releases/DOWNLOADS.md).

Hash-locked Python requirements can be regenerated with `pip-compile --generate-hashes --output-file=requirements.lock requirements.txt` in an appropriate dependency-maintenance environment. Review dependency changes and their licenses before committing the regenerated lock.

## Legacy CLI

The original command-line dashboard remains available for compatibility:

```sh
.venv/bin/python fortigate_dashboard.py 7.2.8 7.4.11
.venv/bin/python fortigate_dashboard.py 7.2.8 7.4.11 --save-data ./data/
.venv/bin/python fortigate_dashboard.py 7.2.8 7.4.11 --load-data ./data/scraped_7.2.8_to_7.4.11.json
```

Its scraping behavior is local operator tooling. Prefer the current web/API workflow for edition controls, persistent jobs, team reviews, and current exports. Evaluate source-document terms before collecting documentation.

## Data consistency regression checks

Run `node frontend/tests/run-content-parity.cjs` and the Python test suite before releasing. The shared screen/export renderer must retain both legacy `resolved-issue` and current `resolved-issues` content without changing stored source JSON. Generic row chapters retain identifiers and Markdown in normal and consolidated views. Archive tests verify single-snapshot JSON/HTML, attachment hashes, unavailable attachments, and authorization failures.

The legacy live harness is disabled by default. It requires all three explicit settings: `RUN_LEGACY_LIVE_API=1`, `LEGACY_API_DISPOSABLE=1`, and `LEGACY_API_URL=http://<disposable-test-server>/api`. Never point it at a development or production installation with retained reports. Tests create jobs and clean up their own IDs. Normal tests use isolated databases and clients.

Detailed PDF job responses include `file_outcomes[].source_available`. PDF review references include `available`. These describe retained attachment availability, independently of successful extraction. Missing originals add response warnings without modifying saved extraction/provenance.

Session ZIP exports use one response snapshot for each JSON/HTML pair, preserve available original PDFs, validate recorded PDF SHA-256 hashes, and include a `manifest.json` of entry hashes and warnings. Missing originals do not discard extracted reports. Authentication failures or checksum mismatches stop the archive. Archives with partial/unfinished reports or missing originals are explicitly marked incomplete. They are personal exports, not installation restore backups.
