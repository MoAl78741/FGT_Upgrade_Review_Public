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

## System administration

See the [administration guide](docs/ADMINISTRATION.md) for GUI encrypted backup/restore, certificate management, public operator access, and private domain profiles, syslog, email notifications and scheduled summaries. These operations are also exposed in Swagger.

## Administration automation reference

All paths below start with `/api/administration`. Use the private named administrator session or the separate public operator session. Private-only endpoints remain unavailable to public operators. JSON requests use `Content-Type: application/json`; multipart uploads must let the client set the boundary.

| Action | Method and path | Request / result |
| --- | --- | --- |
| Check operator login | `GET /status` | Edition, authenticated state, initial-password requirement |
| Public operator login | `POST /login` | `username`, `password`; retain returned cookie |
| Public operator password change | `POST /password` | `current_password`, `new_password` |
| Public operator logout | `POST /logout` | Revokes operator session |
| System overview | `GET /overview` | Build, backup scope, uploaded certificates, delivery counts |
| Download encrypted backup | `POST /backup` | JSON `password`; response is binary `.fgtbackup`, not JSON |
| Preview restore | `POST /restore/preview` | Multipart `file`, `password`; returns archive `sha256`, scope/counts |
| Apply restore | `POST /restore/apply` | Multipart same `file`, `password`, `current_password`, preview `sha256`, `confirmation: RESTORE` |
| List uploaded certificates | `GET /certificates` | Public metadata only; no private keys |
| Upload certificate | `POST /certificates` | Multipart `certificate`, `private_key`, optional `key_password` |
| Download public PEM chain | `GET /certificates/{identity}/download` | PEM response, not JSON |
| Activate certificate | `POST /certificates/{identity}/activate` | Uses the operator-configured proxy connection |
| Delete unused certificate | `DELETE /certificates/{identity}` | Active certificate deletion is rejected |
| List domains (private) | `GET /domains` | Domain IDs, metadata, state, membership counts |
| Edit domain (private) | `PUT /domains/{identity}` | `name`, `description`, `firmware_branch`, `state` |
| List permissions/profiles (private) | `GET /profiles` | Allowed permission names and built-in/custom profiles |
| Create/copy profile (private) | `POST /profiles` | `name`, `permissions`; copy by submitting an existing profile's permissions under a new name |
| Update/delete profile (private) | `PUT /profiles/{identity}`, `DELETE /profiles/{identity}` | PUT takes `name`, `permissions`; assigned/built-in deletion rejected |
| View/download event page | `GET /logs?before=123&action=review&severity=info` | Latest 100 matching events; save response as JSON, use last ID for next page |
| Read/update syslog (private) | `GET /syslog`, `PUT /syslog` | `enabled`, `host`, `port`, `transport`, `retention_days` |
| Test syslog (private) | `POST /syslog/test` | Queues metadata event; inspect `/logs` for forwarding outcome |
| Read/update SMTP (private) | `GET /mail`, `PUT /mail` | See fields below; saved password is never returned |
| Test email (private) | `POST /mail/test` | `recipient`; queues real delivery when enabled |
| Inspect delivery history (private) | `GET /deliveries` | Latest 100 statuses/errors/attempt counts |
| Retry failed delivery (private) | `POST /deliveries/{identity}/retry` | Queues retry; verify uncertain deliveries before retrying |
| List/create schedules (private) | `GET /schedules`, `POST /schedules` | POST takes fields below; returns `id` |
| Update/delete schedule (private) | `PUT /schedules/{identity}`, `DELETE /schedules/{identity}` | PUT takes complete schedule fields; `enabled: false` pauses it |

SMTP PUT fields are `enabled`, `host`, `port`, `security` (`starttls`, `tls`, or local-test-only `plain`), `sender`, `username`, `password`, `clear_password`, `events` (`job.failed`, `review.completed`), and `workspace_recipients` (domain ID → email-address array). Read responses return `password_set` instead of a password. A blank password preserves the existing secret; `clear_password: true` removes it. PUT supplies the complete desired configuration; omitted optional fields revert to their defaults.

Schedule fields are `workspace_id`, `name`, `recipients`, `interval_hours`, and `enabled`. These are summary emails with authorized links, not PDF attachments. Updating a schedule recalculates its next run. The overview/history endpoints provide the same delivery feedback as the GUI.

Create a domain with `POST /api/auth/workspaces` (`name`), then update its metadata using `PUT /api/administration/domains/{identity}`. Assign a custom profile using `PUT /api/auth/memberships` with `workspace_id`, `user_id`, and `role` set to the returned profile ID. Remove assignment with `DELETE /api/auth/memberships/{workspace_id}/{user_id}`. Select a domain using `POST /api/auth/workspace` before accessing its reports/reviews.

Mark a review complete or reopen it with `POST /api/reviews/{review_id}/completion`, JSON `revision` and `completed` (boolean). Use the latest revision from GET; stale writes return 409. Completion queues the configured notification exactly as the GUI does.

### Script authentication

This Python example prompts for credentials, validates TLS, and retains the secure cookie. It only reads administration status and overview; it sends no email and changes no settings.

```python
import getpass
import requests

origin = 'https://10.8.9.11:8442'  # Public operator: change to port 8443
public_operator = False
session = requests.Session()
session.verify = '/absolute/path/to/fgt-v3-local-ca.crt'
session.headers['Origin'] = origin
prefix = '/api/administration' if public_operator else '/api/auth'
response = session.post(origin + prefix + '/login', json={
    'username': input('Username: '),
    'password': getpass.getpass('Password: '),
}, timeout=30)
response.raise_for_status()
try:
    status = session.get(origin + prefix + '/status', timeout=30)
    status.raise_for_status()
    print(status.json())
    # A temporary password must first be changed through prefix + '/password'.
    response = session.get(origin + '/api/administration/overview', timeout=30)
    response.raise_for_status()
    print(response.json())
finally:
    session.post(origin + prefix + '/logout', timeout=30).raise_for_status()
```

For backup download, save `response.content` from POST `/backup`. For restore use `files={'file': open(archive_path, 'rb')}` and `data={...}` with the fields above; reopen the file for the apply request. Restore replaces installation data and revokes sessions, so it requires explicit archive hash and current-password confirmation. Do not put secrets into command-line arguments, source control, or logs.

`401` requires login; `403` indicates permission, origin, or mandatory password-change restrictions; `404` can mean unavailable edition or inaccessible object; `409` indicates a state/revision conflict; `413` means upload size exceeded; `422` means invalid input. Processing/render capacity limits may return `429`. Consult the returned `detail` and current settings before retrying.

### Coverage checks

`tests/test_api_coverage.py` checks that GUI operations are discoverable in OpenAPI, required upload fields remain documented, profiles and schedules can be managed entirely through HTTP, and domain members cannot access installation administration. The administration, security, team, and presentation suites cover authorization, restore, certificate validation, delivery, source parity, and export behavior.

Browser-only presentation settings (theme, temporary selection) remain client state. Configuration analysis and relevance annotations use `/assets/local-api.mjs` locally. PDF printing uses the exported HTML with a local browser; there is no HTTP endpoint accepting raw configurations or a server-side PDF renderer.
