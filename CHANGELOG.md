# Changelog

## 3.0.0 — build 20260912.3

- Renamed the private-facing product to Pro while retaining compatible API and deployment identifiers. Public has an Upgrade to Pro benefits page with an optional operator-configured HTTPS destination.
- Simplified imports, added a synthetic example, filename-version correction, a searchable report library, report names and deletion confirmation.
- Added expiry guidance, bounded session ZIP downloads, export previews and source-PDF comparison in reviews.
- Added unsaved-edit protection, save status, Save and next, atomic bulk decisions, permission-aware controls and consolidated administration navigation.

## 3.0.0 — build 20260912.2

- Verified 76 GUI HTTP operations in the OpenAPI contract; added regression checks to both CI workflows.
- Fixed Swagger PDF uploads by documenting multipart file fields while preserving authentication and queue reservation before parsing.
- Documented binary backup, certificate and source-PDF downloads. Limited the PDF timeout header to PDF upload/retry operations.
- Expanded API examples for operator login, backup/restore, certificates, domains, custom profiles, logs, syslog, SMTP, schedules and review completion.
- Validation: 53 API coverage, administration and security tests passed per edition; live Swagger PDF file pickers and both HTTPS deployments checked.

## 3.0.0 — build 20260912.1

- Added encrypted GUI/API installation backup, restore preview/confirmation and interrupted-restore recovery.
- Added separate public operator authentication. Public backups exclude temporary visitor reports and PDFs.
- Added PEM certificate inventory, validation, chain download and activation through a dedicated per-edition Caddy proxy.
- Private: domain metadata/read-only/archive states, custom permission profiles, local event logging and syslog forwarding.
- Private: SMTP job-failure alerts, completed-review notifications, scheduled domain summary emails and delivery history/retry. SMTP is disabled until configured; schedules do not attach PDF reports.
- Preserved existing report data, identifiers, accounts and additive database migrations.

## Documentation follow-up

Updated README, feature showcase, installation/operations, team access, administration and developer guidance to reflect these builds. Historical release notes and dated security findings retain their original scope. Application tests do not clear outstanding security or licensing release gates. Build identity in `/api/capabilities` identifies the deployed source revision; later documentation commits do not alter that identity.
