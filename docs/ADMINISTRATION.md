# System administration

Open **System administration** in the private edition, or **Operator login** in the public edition. Interactive API documentation includes the same operations under `/api/administration`.

## Access boundaries

Private system operations require a named installation administrator, even when an operator has disabled ordinary local team authentication. Domain members cannot change installation settings or export an installation backup.

Public visitors keep their temporary session cookies and report isolation. Public operators use a separate Secure, HttpOnly, SameSite cookie with a one-hour lifetime. There is no anonymous operator-creation API or default public operator password. Provision or recover an operator locally:

```sh
docker compose exec fgt-upgrade python -m backend.manage_operator --username admin
```

The command prompts for a password without placing it in shell arguments. Sign in at `/administration`; change the initial password before using system operations. Changing it revokes other operator sessions. Private accounts continue using the existing single web login.

## Domains and access profiles (private)

A domain is the existing customer workspace, presented as an administrative domain. Existing workspace IDs, reports, reviews, memberships, and accounts survive the additive migration.

- Switch domains in the header. Accounts only see assigned domains; installation administrators see all domains.
- Manage name, description, optional firmware-branch metadata, and active/read-only/archived state in **Domains**. Archived domains remain readable. Finish or cancel active jobs before changing a domain to read-only.
- Create or copy an **Access profile**, then assign it to an account/domain pair under **Account & access**.
- Permissions separately control report reading, importing, processing controls, deletion, exporting, review reading/writing/deletion/export, and domain audit history.
- Unchecked and unknown permissions are denied server-side. Profile changes and membership revocation apply on the next request. Assigned profiles cannot be deleted; built-ins cannot be edited.
- Domain profiles do not grant installation-wide account, certificate, backup, or SMTP administration. Those remain restricted to installation administrators. This release does not implement delegated system-administrator profiles, SSO, or MFA.

The interaction is inspired by FortiManager's domain/profile organization, without implying device management or Fortinet compatibility. Firmware metadata does not certify an upgrade path or limit imports to one branch.

## Encrypted backup and restore

GUI archives use authenticated AES-256-GCM encryption with a per-archive random salt/nonce and a scrypt-derived key. Keep the backup password separately; the server cannot recover it. The GUI archive limit is **256 MiB**. Larger private installations should use the existing offline archive tools described in [Operations](../OPERATIONS.md).

Private GUI backups include installation settings, accounts, domains, memberships, custom profiles, reports, reviews, original PDFs, report schedules, certificates/private keys, and the key used to encrypt saved SMTP credentials. They exclude login sessions, transient parser artifacts, delivery bodies/history, and audit/event history. Keep operational/audit exports separately if required.

Public GUI backups include installation settings, operator accounts, and certificates/keys. They **never include public visitor sessions, reports, or PDFs**. Restoring public settings leaves current visitor data under its existing expiry policy. Do not use infrastructure snapshots to retain visitor data beyond 24 hours.

1. Download an encrypted backup with a password of 14–256 characters.
2. Upload it under **Restore installation**, enter its password, and preview record/file counts, edition and creation time.
3. Enter your current administrator password and type `RESTORE` to apply that exact previewed archive.
4. Sign in using the restored account credentials. All administrator sessions end. Pending email deliveries are cancelled.

Private processing must be idle before backup/restore. A maintenance gate drains HTTP activity, while queue and delivery locks exclude background changes. Uploaded archives contain allowlisted JSON records and files, not executable SQLite databases. Path/link/expansion checks and authenticated encryption are validated before replacement. A locally generated recovery journal rolls back an interrupted database/file swap before startup processing resumes.

The certificate currently serving HTTPS is preserved during restore, even when it is absent from the archive. Restored certificates are available for an explicit activation afterward. GUI restore does not modify operator-owned Compose files, origins, proxy templates, external DNS, or host trust stores. Archive schemas currently must match the running version.

## Certificates and HTTPS proxy

Upload a PEM certificate chain (leaf first, then intermediates) and a matching PEM private key. Encrypted keys are supported with an input password. The application checks key matching, chain signatures, validity dates, server usage, and hostname/IP SANs. RSA keys require at least 2048 bits; EC keys require at least 256 bits. Certificate trust remains the client/device's responsibility.

The inventory shows names, issuer, expiry, days remaining, SHA-256 fingerprint, and active status. Downloading returns only the public chain. Private keys are stored with owner-only permissions and are only included in encrypted installation backups. Unused certificates can be deleted. Certificates expiring within 30 days appear on the overview.

Activation requires a **dedicated proxy for each edition**, using the provided management integration:

```sh
python scripts/configure_proxy.py --origin https://review.example.com:8443
# In .env set APP_ORIGIN to that exact origin, TLS_PORT=8443,
# and PUBLIC_ORIGIN to the same origin when running the public edition.
# Public also needs its exact deployed SOURCE_CODE_URL.
docker compose -f docker-compose.yml -f compose.administration.yml up --build -d
```

The generated `deployment/caddy.json` is operator configuration and is excluded from Git and source archives. The proxy defaults to a loopback listener. Set `TLS_BIND` deliberately for LAN access. Caddy starts with a locally issued certificate; no system trust store is changed automatically. Distribute its public CA certificate only if you choose to trust it on client devices.

The backend receives trusted `CADDY_ADMIN_URL`, `CADDY_CONFIG_TEMPLATE`, and `CADDY_CERTIFICATE_MOUNT` deployment values. Request bodies cannot change the control endpoint or proxy template. The admin port is internal to the Compose network and is never published to the host. Do not attach untrusted containers to that network. The proxy mounts only the dedicated administration volume, not application databases or uploads; its mount is read-only.

Caddy applies configuration atomically and retains its previous configuration on rejection. Persistent proxy data/config volumes and `--resume` retain the last successful activation over restart. A connection timeout means the activation result is uncertain: inspect the proxy before retrying. Uploaded certificate trust is not installed on browsers automatically. Using an unrelated/shared proxy requires a deliberate integration; do not point an edition at another service's Caddy admin port.

The proxy Dockerfile removes Caddy's file capability before running non-root with all capabilities dropped. It listens on an unprivileged internal port. See [Caddy API documentation](https://caddyserver.com/docs/api) for reload and persistence behavior.

## Local logs and syslog (private)

System events record bounded action/actor/domain/reference metadata. Passwords, configuration data, PDF text, and reviewer-note bodies are excluded. View/filter/paginate events and download the current page as JSON. This is an operational log, not an immutable compliance ledger.

Private local events are retained for the configured 1–365 days (30 by default), with an independent maximum of 10,000 events. Structured messages also go to application logging. Public operator events are bounded to the latest 10,000; public does not expose private syslog or email controls.

Configure UDP, TCP, or verified TLS forwarding in **Syslog**. Messages use RFC 5424; TCP/TLS uses octet-counted framing. UDP/TCP are unencrypted. TLS uses system trust and cannot disable certificate verification. Forwarding is bounded, best effort, and not a guaranteed archival transport. Failed forwards remain marked in local event history. Saving settings does not replay already processed history. Test delivery generates a new metadata-only event.

## Email and scheduled summaries (private)

Email starts disabled. Configure an SMTP host/port, sender, credentials if required, and verified STARTTLS or implicit TLS. Plain SMTP is restricted to localhost or the explicit local `mailpit` test sink. Passwords are encrypted at rest; GET responses reveal only whether a password is set. A blank password preserves the existing value; the remove-password checkbox clears it.

Choose recipients independently per domain for:

- Failed or partially successful PDF/scrape jobs.
- Reviews explicitly marked **Complete review**. Completion and notification enqueueing use one guarded transaction. Editing a completed review reopens it; completion is a review milestone, not proof of upgrade safety.

Scheduled reports are **domain summary emails** containing report/review counts, incomplete-job counts, review names and authenticated links. This release does not attach PDFs or full source documents to email. Select a domain, recipients, and interval in hours. Schedules persist; missed runs coalesce into one summary after restart. Read-only/archived domains do not generate scheduled summaries.

The outbox retains delivery status and generic errors, retries failures up to three times with backoff, and marks interrupted sends as uncertain for manual review. A timeout or partial SMTP acceptance may already have delivered mail: inspect recipients before retrying uncertain deliveries. Pending messages are bounded to 500; completed history is retained for 30 days. Disabling SMTP pauses pending deliveries. A queued message uses the recipients selected when it was created.

Use **Send test email** only with a recipient you intend to contact. Automated development checks use a local test server and synthetic addresses; deployment does not send real mail until configured and enabled.

## API map

| GUI operation | API |
| --- | --- |
| Operator status/login/password/logout | `/api/administration/status`, `/login`, `/password`, `/logout` |
| System overview | `GET /api/administration/overview` |
| Encrypted backup | `POST /api/administration/backup` |
| Restore preview/apply | `POST /api/administration/restore/preview`, `/restore/apply` (multipart) |
| Certificate inventory/upload/download/activate/delete | `/api/administration/certificates` and `/{id}` operations |
| Domain metadata/state | `GET /api/administration/domains`, `PUT /domains/{id}` |
| Domain creation and assignments | Existing `/api/auth/workspaces` and `/api/auth/memberships` |
| Custom access profiles | `GET/POST /api/administration/profiles`, `PUT/DELETE /profiles/{id}` |
| Event log | `GET /api/administration/logs` |
| Syslog settings/test | `GET/PUT /api/administration/syslog`, `POST /syslog/test` |
| SMTP settings/test | `GET/PUT /api/administration/mail`, `POST /mail/test` |
| Scheduled summaries | `/api/administration/schedules` and `/{id}` |
| Delivery history/retry | `GET /api/administration/deliveries`, `POST /deliveries/{id}/retry` |
| Review completion/reopening | `POST /api/reviews/{id}/completion` with `revision` and `completed` |

Existing exact-origin, cookie, ownership, and edition restrictions apply. The new management upload paths authenticate before multipart spooling. No configuration-analysis upload endpoint has been added.
