# Repeatable regression testing

Run from the repository root. No LLM is needed to interpret success: **exit code 0 and a current PASSED summary** are required. Fix a failed assertion, rerun its feature, then run the full suite before merging. There are no automatic retries or automatic golden updates.

## Everyday commands

```sh
.venv/bin/python scripts/check.py
.venv/bin/python scripts/check.py --list
.venv/bin/python scripts/check.py --feature report_content --feature exports
.venv/bin/python scripts/check.py quick
```

`check` runs coverage accounting, TypeScript, deterministic frontend contracts, production UI/API renderer builds, every current backend test module, and real Chromium browser workflows. `quick` omits Chromium and is only an iteration aid. A feature selection narrows backend/browser cases; shared frontend contracts still run. Features without browser scenarios rely on their API/unit contracts; selecting those does not invent browser coverage.

Each invocation writes a new directory beneath `test-results/latest/`; `LATEST` contains its absolute path. Open `SUMMARY.md` for stage results/timing, `summary.json` for automation, and `browser-report/index.html` for browser details. Failed browsers retain screenshots and traces; backend and browser results include JUnit XML. Logs remain local, contain only synthetic test data, and are ignored by Git. Source changes during a run invalidate its result. Stop editing before final verification.

## First-time setup

Use Python 3.12 and Node.js 22.12 or newer. Create `.venv` with Python 3.12. Choose the matching vendored wheel directory (`linux-amd64`, `linux-arm64`, or the available matching `macos-amd64` directory); do not mix architectures.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links vendor/python/linux-amd64 --require-hashes -r requirements.lock
.venv/bin/python -m pip install --no-index --find-links vendor/python/linux-amd64 --no-deps --require-hashes -r requirements-test.lock
(cd frontend && npm ci --offline --cache ../vendor/npm)
node frontend/node_modules/@playwright/test/cli.js install --with-deps chromium
```

The last command is **test-machine setup**, and downloads the pinned browser plus operating-system dependencies. Application startup never installs dependencies. If the pinned browser is absent, the runner can discover an installed system Chromium/Chrome, and records the executable in its summary. CI uses the pinned browser. For an offline workstation, provision the corresponding Playwright browser cache during machine setup, or set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to an installed compatible Chromium/Chrome executable. CI uses the pinned Playwright browser. Application images exclude the test browser. The npm test runner itself and its notices are vendored.

The suite creates an isolated HTTPS server, temporary certificate, database, uploads and synthetic accounts, then removes them. It never changes system certificate trust. No production URL, SMTP credentials, SSH account or Docker daemon is needed. Python fixtures reject external connections and connections to pre-existing local services; explicitly bound local mail/syslog sinks are permitted. Browser traffic is restricted to the disposable loopback server. These are safeguards for trusted test code, not an OS sandbox for hostile tests.

## What each layer proves

- **Backend/API:** ownership and role denial paths, validation, lifecycle, persistence, queue/worker behavior, backup rollback, local mail/syslog deliveries, source parsing and API export contracts. These exercise actual application services with isolated storage and controlled external dependencies.
- **Frontend contracts:** deterministic configuration parsing, feature matching, raw source immutability, rendering/export consistency, release ranges, duplicate handling and progress calculations. Synthetic source fixtures have independently asserted expected values.
- **Browser:** actual built UI, HTTP APIs, cookies, Web Worker and downloads. Navigation, source formatting, missing-source archive warnings, per-file metrics, review decision/checklist persistence, configuration privacy, Swagger and administration panel wiring are covered. Pro adds bootstrap, feature gates and settings persistence; Public adds independent browser-session authorization. Panel smoke checks complement backend mutation tests; they do not prove a real certificate proxy reload or real external mail delivery.
- **Coverage tripwire:** unclassified test modules, API methods/paths and Pro switches fail immediately. Adding a mapping alone is insufficient: add positive, negative, boundary and persistence tests appropriate to the behavior.

Browser jobs use deterministic seeded outcomes and a stopped queue. Real PDF extraction and worker lifecycle are tested in the backend/corpus layers. Browser tests do not claim to validate container memory/network isolation. No test proves every possible input or vendor document.

## Release and parser changes

```sh
.venv/bin/python scripts/check.py release --corpus /absolute/path/to/sealed-corpus
```

Release mode adds distributable packaging, vendored-artifact verification and exact real-document extraction comparison. It refuses to run without an external corpus, or with narrowed features. Keep publisher documents and their extracted goldens outside public/distributable repositories. A corpus is a separately reviewed input, never an output that the command silently regenerates.

The bundle contains `manifest.json`:

```json
{"schema":1,"cases":[{"id":"fortios-7.6.6","family":"7.6","pdf":{"path":"source.pdf","sha256":"64 hex characters"},"golden":{"path":"expected.json","sha256":"64 hex characters"}}]}
```

Provide at least one verified release in each of 6.4, 7.0, 7.2, 7.4 and 7.6. Each golden is the reviewed extraction snapshot with `sha256` (source PDF), `page_count`, and `result` (complete JSON-serialized `parse_pdf` result). File paths must stay inside the bundle. Changed seals, pages, source text, field types, row order, missing sections or extra fields fail. Reports include bounded difference paths and per-file timing without copying proprietary text into CI logs. Review intentional changes against the original documents; document approval before replacing any baseline. The optional private product-pack golden tests additionally replay sealed FortiManager PDFs and cached web pages; run `RUN_PACK_CORPUS=1 .venv/bin/python -m pytest tests/test_product_pack_golden.py -q` when that private evidence is present.

Release mode is not a production deployment test. Linux CI separately builds the image with networking disabled, audits dependencies, scans the image, and checks the worker sandbox. Certificates/proxy reload, HTTP redirects, durable volumes across restart, actual SMTP/syslog destinations and target-host limits require a disposable deployment on the target Linux architecture before a release. These checks must not be reported as passing based on local browser tests.

Legacy `test_api.py` and `test_scrape_issues.py` target external servers and is deliberately excluded. Historical PDF migration baselines are separately classified; current release regression uses the reviewed replacement corpus. Missing confidential corpora are not silently accepted by release mode.

## Maintaining useful tests

Prefer a reproducible bug fixture and an independent expected result. Assert original source text before and after decisions/consolidation/export. For writes, check persistence after reopening; for authorization, test a different session/workspace and a direct API call. Test time limits with controlled clocks and worker results rather than long sleeps. Use local sinks for delivery and injected failures for rollback. Avoid selectors tied to CSS, arbitrary waits, snapshots of timestamps and tests that merely repeat implementation logic.

When a failure occurs, read the failed stage log first. For UI failures open the trace using `node frontend/node_modules/@playwright/test/cli.js show-trace <trace.zip>`. A missing browser or wheel is a setup failure, not a passing test. Do not add retries to hide races. Keep new endpoints and tests mapped below and in `tests/feature_matrix.json`.

## Feature coverage ownership

| Feature | Required behavior | Backend modules (shared where appropriate) |
|---|---|---|
| navigation | Find home, edition/build identity, responsive navigation and theme | `test_usability.py` |
| release_selection | Official PDF links, From/To ranges, include-start and invalid endpoints | `test_range_notices.py`, `test_scrape_baseline.py`, `test_presentation_api.py` |
| pdf_import | PDF byte/file/page limits, duplicate versions, malformed/encrypted files and offline parsing | `test_security.py`, `test_pdf_engine_security.py`, `test_pdf_parser_units.py` |
| job_lifecycle | Queue ownership, cancel/retry, partial outcomes, expiry and restart recovery | `test_security.py`, `test_pdf_worker.py`, `test_api_client.py` |
| workers | No-network worker policy, aggregate limits, progress rename race and isolation | `test_container_workers.py`, `test_pdf_worker.py`, `test_performance_paths.py` |
| progress | Per-file elapsed time, page counts, monotonic progress and terminal outcomes | `test_file_metrics.py`, `test_pdf_worker.py` |
| scraping | Scoped content capture, requests/Selenium policy and release baselines | `test_scraper_html.py`, `test_scrape_issues.py`, `test_scrape_baseline.py`, `test_fgt_utils.py` |
| report_content | Source text/formatting, sections, tables, headings, notices and historical aliases | `test_content_parity.py`, `test_parser_generalization.py`, `test_pdf_section_boundaries.py`, `test_pdf_issue_markdown.py`, `test_pdf_callouts.py`, `test_pdf_heading_levels.py`, `test_pdf_prose_format.py`, `test_pdf_table_format.py`, `test_pdf_table_lists.py`, `test_pdf_table_continuations.py` |
| exports | GUI/API/HTML/print parity, source selection and script-injection safety | `test_presentation_api.py`, `test_content_parity.py` |
| consolidation | Exact-content-only deduplication, all sections, original coordinates and source immutability | `test_presentation_api.py` |
| comparison | Added/changed descriptions without claiming runtime feature removal | `test_presentation_api.py` |
| archives | Single-snapshot JSON/HTML, hashes, missing PDFs and bounded session ZIP | `test_source_availability.py`, `test_usability.py` |
| config_analysis | Local-only parsing, nested configuration, corrections, relevance and clearing | `test_presentation_api.py` |
| reviews | Multi-import reviews, decisions, revision conflicts, bulk changes, completion and checklists | `test_reviews.py`, `test_usability.py` |
| authentication | Bootstrap password change, secure sessions, logout, throttling and authorization | `test_team.py`, `test_security.py` |
| workspaces | Customer isolation, membership revocation and stale workspace tabs | `test_team.py`, `test_administration.py` |
| team_accounts | Account lifecycle, last-admin protection and password/session revocation | `test_team.py` |
| custom_roles | Granular permissions, escalation rejection and readonly domains | `test_administration.py`, `test_team.py` |
| backups | Encrypted backup, restore preview/commit, tamper rejection and atomic rollback | `test_maintenance.py`, `test_administration.py` |
| certificates | Key/certificate validation, expiry, secret redaction and activation authorization | `test_administration.py` |
| event_logs | Actor attribution, privacy and installation/domain audit separation | `test_team.py`, `test_administration.py` |
| syslog | Local receiver delivery and newline injection protection | `test_administration.py` |
| email | Local SMTP sink, secret redaction, event outbox and retry ownership | `test_administration.py` |
| scheduled_reports | Domain scoping, deadlines, deduplication and disabled schedules | `test_administration.py` |
| support | Diagnostics exclude private source fields and require operator access | `test_maintenance.py`, `test_team.py` |
| processing_settings | Bounds, persistence, overrides, reset and permission checks | `test_processing_settings.py` |
| api_documentation | GUI operations discoverable, multipart/binary schema and offline Swagger | `test_api_coverage.py`, `test_presentation_api.py` |
| security | Cross-session denial, CSRF/origin/host checks, export injection and no config endpoint | `test_security.py`, `test_content_parity.py`, `test_presentation_api.py` |
| feature_gates | Optional module discovery and server-enforced dependency rules | `test_usability.py` |
| suite_infrastructure | Coverage drift, safe test boundaries and release packaging classification | `test_suite_contract.py` |

## GitHub CI/CD gates

`regression.yml` runs the full suite on every push and pull request, or manually from Actions. Logs, JUnit, screenshots and browser traces are retained for 14 days. `security.yml` independently checks dependency advisories, the offline image build, excluded PDF engines, the container sandbox and Trivy; it also runs weekly.

`release.yml` runs on `main` pushes or manual dispatch. It calls those same reusable workflows at the current commit and will build/upload the edition's source-and-image bundle only if **both** succeed. It checks packaging, builds from the generated source archive, and verifies checksums. Build numbers include the workflow run and attempt. No registry push, GitHub release publication, SSH connection, or Portainer rollout is enabled. Production deployments therefore remain unchanged.

The release pipeline retains the image security gate: current base-image scan findings must be resolved or explicitly triaged before an artifact can pass that gate. Private publisher corpus replays remain separate operator-run release checks described above; confidential PDFs are not uploaded to ordinary GitHub runners. Branch protection rules are not modified by these workflow files; repository administrators can make `regression / regression` and `security / tests` required checks using the names shown by GitHub.
