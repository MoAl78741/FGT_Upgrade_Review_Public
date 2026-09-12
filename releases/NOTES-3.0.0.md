# Public and private editions

Version 3.0.0 provides two editions from one AGPL source tree:

- **Private Docker:** local reports, offline PDF import, and optional operator-enabled scraping.
- **Public hosted software:** user-provided PDFs, temporary sessions and 24-hour report expiry. Scraping is disabled. Hosting is configured by the operator; this release does not create a live website.
- **Both:** browser-only FortiOS configuration relevance, unchanged source text, separate export annotations, report provenance, per-file outcomes and resumable retries.

Download the public or private source archive and read `START-HERE.md`. For an
offline installation, also download the Linux AMD64 Docker image. `INSTALL.md`
explains installation and checksum verification. `BUILD-MANIFEST.json` records
the image identity and corresponding source hashes.

## Validation

The local regression suite, frontend production build, source-to-screen/export
parity, public HTTPS browser sessions, offline private PDF import and restart
persistence were verified. The four supplied PDFs retain all 1,283 extracted
rows; source documents are not included in these downloads.

## Known remaining work

Base-image security advisory remediation is deferred at the project owner's
request and remains documented in `SECURITY.md`. This is a functional release,
not a security-clearance claim. A hosted public launch still requires a hosting
target, applicable legal/privacy review and corresponding-source availability.

When upgrading an existing private Docker installation, retain its Compose
project name and back up its data and uploads volumes together before starting
the new image. Do not delete named volumes during a normal upgrade.
