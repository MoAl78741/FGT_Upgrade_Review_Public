# Public edition · 3.0.0

This is the PDF-only hosted application. It provides temporary cookie sessions,
not visitor accounts or a shared library. A separate named operator administers settings, backups and certificates. Reports and PDFs expire after 24 hours;
configuration analysis stays in the browser. Scraping is always disabled.

Requirements: Docker with Compose v2, Linux Landlock support, at least 5 GiB
available to the container, a domain, and a TLS reverse proxy. This source bundle
is built from the independent public repository and retains inherited code and license notices.

1. Extract the archive and open a terminal in its directory.
2. Copy `releases/public.env.example` to `.env`.
3. Set `PUBLIC_ORIGIN` to the exact HTTPS origin without a path or trailing slash.
4. Set `SOURCE_CODE_URL` to a downloadable copy of the exact corresponding source
   you are deploying, including modifications and build instructions.
5. Configure your TLS proxy to forward to `127.0.0.1:8001` (or `HOST_PORT`),
   preserving the public Host and browser Origin headers. Allow request bodies
   up to 151 MiB and apply client request limits at the proxy.
6. Run `docker compose -p fgt-public -f docker-compose.yml -f compose.public.yml up --build -d`.
7. Open the HTTPS site and verify it says PDFs and reports expire after 24 hours.
   There must be no Scrape tab. Test upload, report export, and deletion.

The API port is bound to loopback and should not be exposed directly. If your
reverse proxy runs inside a different container, configure its connection to the
application deliberately; `127.0.0.1` inside that proxy is the proxy itself.

For diagnostics, use the same Compose options with `logs --tail=100`.
To stop, use those options with `down`; do not use `--volumes` unless intentionally
removing temporary sessions and reports. Do not back up public uploaded content
or enable infrastructure snapshots that outlive the advertised retention period.

For operator provisioning, encrypted settings/certificate backup and restore, and the optional managed HTTPS proxy, follow [Administration](../docs/ADMINISTRATION.md). Public visitor content is excluded from these backups. Private domains, custom team roles, syslog and email delivery remain unavailable in the public edition.

Publish source and notices and complete the legal review before inviting public
users. Remaining container advisory remediation is deferred in SECURITY.md;
this bundle is not a security clearance or an endorsement by Fortinet.
