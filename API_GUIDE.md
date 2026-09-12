# GUI and API access

Open **Settings → API documentation (Swagger)**, or `/api/docs`. The JSON schema remains at `/api/openapi.json`. Swagger UI is locally bundled, including its stylesheet, and its external schema validator is disabled. It uses the installation's existing same-origin cookies and security policy. Self-hosting follows FastAPI's [custom docs assets guidance](https://fastapi.tiangolo.com/how-to/custom-docs-ui-assets/).

## Authentication and workspace selection

Public clients call `GET /api/capabilities` once and retain the secure session cookie. Reports remain session-owned and expire after 24 hours. Private clients call `POST /api/auth/login`, change a temporary password using `POST /api/auth/password`, and select a workspace using `POST /api/auth/workspace`. `GET /api/auth/status` returns available workspaces and account state.

Send an `Origin` header equal to the exact installation origin for mutations, including read-only POST view/export requests. Browser Swagger requests do this automatically. `X-Workspace-ID` is an optional stale-workspace guard, **not** a way to select another workspace. Its value must match the session's selected workspace. Viewers may read/export; reviewers may change reports/reviews; administrators manage accounts and installation settings.

For scripts, use a cookie jar, the local CA, and your own credentials. Do not put passwords in committed scripts. Example after login/bootstrap:

```sh
curl --cacert installation-ca.crt -b cookies.txt \
  -H 'Origin: https://10.8.9.11:8442' -H 'Content-Type: application/json' \
  -d '{"sections":["known_issues"],"consolidate_all":true}' \
  'https://10.8.9.11:8442/api/jobs/REPORT_ID/view'
```

## GUI/API coverage

| GUI action | API operation |
| --- | --- |
| Edition, build, limits | `GET /api/capabilities` |
| Find PDFs using From/To and include-start | `GET /api/releases?from_version=7.6.5&to_version=7.6.6&include_from=true` (omit range for catalog) |
| Upload PDFs | `POST /api/jobs/upload`, multipart repeated `files` fields |
| Scrape, include-start, force refresh, Selenium toggle | `POST /api/jobs`; deployment capabilities still enforced |
| List/read reports, logs, progress, per-file elapsed time/pages, provenance/completeness | `GET /api/jobs`, `GET /api/jobs/{id}` |
| Retry/cancel/delete | `POST /api/jobs/{id}/retry`, `POST /api/jobs/{id}/cancel`, `DELETE /api/jobs/{id}` |
| View original PDF | `GET /api/jobs/{id}/files/{file_index}` |
| Search/filter and consolidate per section or globally | `POST /api/jobs/{id}/view` |
| Compare feature release-note descriptions | `GET /api/jobs/{id}/compare?from_version=…&to_version=…` |
| Select rows and export report | `POST /api/jobs/{id}/export` with `format` of `html`, `json`, `csv`, or `txt` |
| Print / save PDF | Export self-contained HTML, then print/save PDF using a browser, just as the GUI does; there is no server PDF renderer |
| Create/list/read/edit/delete/duplicate reviews | `/api/reviews` and `/api/reviews/{id}`; `POST /api/reviews/{id}/duplicate` |
| Add/remove report batches in a review | `POST /api/reviews/{id}/jobs`, `DELETE /api/reviews/{id}/jobs/{job_id}?revision=…` |
| Save decisions and reviewer notes | `PUT /api/reviews/{id}/decisions/{finding_id}` |
| Save checklist | `PUT /api/reviews/{id}/checklist` |
| Export saved review package | `GET /api/reviews/{id}/export` |
| Customer/project details, range, summary and rollback notes | `PUT /api/reviews/{id}` |
| Login/logout/password/workspace selection | `/api/auth/login`, `/logout`, `/password`, `/workspace`, `/status` |
| Accounts, password resets, workspaces, membership roles | `/api/auth/users`, `/users/{id}`, `/users/{id}/password`, `/workspaces`, `/memberships` |
| Audit history | `GET /api/auth/audit`, `GET /api/auth/admin-audit` |
| Installation processing settings, defaults/reset | `GET`, `PUT`, `DELETE /api/settings/processing` |
| Per-attempt PDF timeout | `X-PDF-Timeout-Minutes` on upload/retry, within installation limits |
| Diagnostics/download | `GET /api/support/diagnostics` |
| Local configuration analysis/manual feature corrections/relevance annotations | Local JavaScript API described below; never HTTP |
| Theme, unsaved filters/selections and browser preferences | Client state; no server-side setting or shared user data |

Review writes retain revision conflict checks. Use the latest `revision` from the returned review. Public/private policies and authentication are identical for API and GUI access; installing the API tools does not enable hosted scraping.

## Report options

`view` and `export` accept `sections` (source keys, such as `known_issues`), `versions`, `search`, `category`, `consolidate` (source section keys), `consolidate_all` (default false), and optional `selection`. Empty section/version lists mean all. `selection: null` means all matching entries; `selection: []` means no source entries. Each returned view entry includes unchanged `source`, unique `builds`, and `selection` coordinates (`version`, `section`, `index`). Pass these coordinates back to export only selected occurrences, including partial selections from a consolidated group.

`view` supports `offset` and `limit` (default 1000, maximum 5000). `count` describes all matching groups before pagination, and `source_count` describes matching original occurrences. Rich chapters group only as whole identical chapters. Changed IDs/categories/text/formatting stay separate. Source reports are never rewritten.

HTML uses the GUI's React source renderer, bundled fonts, source warnings and print styles. CSV and tab-separated TXT include section, builds, category, ID and source description; use HTML when source formatting matters. Rendering uses one bounded slot per application process, a 512 MiB JavaScript heap limit, and 64 MiB input/output limits. Full HTML/review exports have a 120-second timeout; JSON views, comparisons and catalog lookups have a 30-second timeout. A busy renderer returns 429; choose fewer versions/sections after size/time-limit errors. Node.js 22 is included in Docker; source installations need Node.js 22 (or set the operator-only `NODE_BINARY` path) and `npm run build` in `frontend`.

## Local programming interface and privacy

`/assets/local-api.mjs` is an ES module with the actual GUI analysis and export functions. It works in browsers or Node.js and makes no requests or storage writes. Download the module once for offline scripts. Never send raw configs, identifiers, extracted profiles, or manually corrected profiles to HTTP endpoints.

```js
import {analyzeConfig, relevance, reportHtml, emptyProfile} from './local-api.mjs';
const profile = analyzeConfig(configText); // plaintext, <=10 MiB, in local memory
profile['SD-WAN'] = 'disabled';            // manual correction; still local
const reasons = relevance(noteText, profile);
const html = reportHtml({...reportJson, localRelevance: profile}, {
  consolidate: ['known_issues']
});
// Write html locally, or print it using your browser. Discard configText/profile
// when finished; emptyProfile() provides the same unknown-state reset as the GUI.
```

Also exported: `FEATURES`, `RULE_VERSION`, `reportView`, `reportDelimited`, `compareFeatures`, `pdfReleaseRange`, `pdfCatalog`, `reviewPackageHtml`, `generateHtml`, and `getAvailableSections`. HTTP export schemas reject config/profile fields. If relevance annotations are wanted, apply them locally after retrieving your authorized report JSON.
