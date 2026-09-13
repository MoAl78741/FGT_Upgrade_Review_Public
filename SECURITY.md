# Security release status

Updated locally on 2026-09-11. Public and private application workflows have been functionally validated. Known base-image advisories remain visible; this is a targeted application review, not an independent penetration test or clearance for an Internet-hosted launch.

## Completed validation

- Backend regression/security tests pass, including session ownership, upload limits, queue limits, expiry, cancellation, restart recovery, partial imports and resumable retries.
- Frontend parity and configuration privacy/relevance checks pass. Browser config analysis made no config-derived requests and did not change browser persistence.
- Two independent browser sessions over local HTTPS verified owner access and denied unrelated list/read/cancel/delete requests. Public scraping is unavailable.
- All four supplied PDFs completed using the isolated queue, with one timeout followed by a successful retry of only the unfinished file. Extracted rows and notices equal the existing verified four-PDF report.
- A real PDF completed through the public Docker API under Linux confinement (107 known / 1 resolved issues); owner deletion was verified afterward. macOS and Linux confinement checks deny other-job access and network connections.
- Annotated standalone export: 56 PDF pages, all 107 checked descriptions present, no blank pages, zero external requests.
- Python and Node application dependency audits report no known vulnerabilities. Docker build and frontend production build pass.

## Container findings and scope

Trivy reports 56 high/critical package findings representing 20 unique advisories in the Debian 13 runtime. The image uses `python:3.12-slim-trixie` with available package upgrades. No Debian fixed package versions are listed in this scan. These findings have not been suppressed; the separate security audit workflow continues to report high/critical findings.

Some findings concern utilities or execution paths the application does not use. This is preliminary reachability context, not an approved exception: the service does not invoke Perl, gzip, infocmp, mount or nsenter; it runs non-root without capabilities; uploaded databases and FTS5 queries are not supported. Expat/font processing and other native library paths need further review. Do not infer that all base-image findings are non-applicable.

Debian confirms the current stable Expat and SQLite packages remain affected: [Expat tracking](https://security-tracker.debian.org/tracker/CVE-2026-76957), [SQLite tracking](https://security-tracker.debian.org/tracker/CVE-2026-11822). Resolve applicable findings using maintained patched packages/base images, or document reviewed evidence for narrowly scoped non-applicability decisions before a security-cleared hosted launch. Keep the findings visible.

| Advisory | Severity | Installed packages | Scanner status |
|---|---|---|---|
| CVE-2025-69720 | HIGH | libncursesw6, libtinfo6, ncurses-base, ncurses-bin | affected |
| CVE-2026-11822 | HIGH | libsqlite3-0 | affected |
| CVE-2026-11824 | HIGH | libsqlite3-0 | affected |
| CVE-2026-13221 | CRITICAL | perl-base | affected |
| CVE-2026-16742 | HIGH | libsystemd0, libudev1 | affected |
| CVE-2026-41992 | HIGH | gzip | affected |
| CVE-2026-42496 | CRITICAL | perl-base | fix_deferred |
| CVE-2026-42497 | HIGH | perl-base | fix_deferred |
| CVE-2026-48962 | HIGH | perl-base | affected |
| CVE-2026-54369 | HIGH | libacl1 | affected |
| CVE-2026-57432 | HIGH | perl-base | affected |
| CVE-2026-57433 | HIGH | perl-base | affected |
| CVE-2026-76642 | HIGH | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | affected |
| CVE-2026-76956 | HIGH | libexpat1 | affected |
| CVE-2026-76957 | HIGH | libexpat1 | affected |
| CVE-2026-78408 | HIGH | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | affected |
| CVE-2026-78409 | HIGH | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | affected |
| CVE-2026-78410 | HIGH | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | affected |
| CVE-2026-8376 | CRITICAL | perl-base | affected |
| CVE-2026-9538 | HIGH | perl-base | fix_deferred |

## Application reachability review (2026-09-11)

A fresh Trivy database scan of the current dependency-layer candidate still reports 56 HIGH/CRITICAL package findings across the same 20 advisories above. No fixed Debian package version is listed by the scanner. Python and Node dependency audits report no known vulnerabilities. Findings are not suppressed, and the image scan in CI still fails on HIGH/CRITICAL findings. Updating the source or passing functional tests does not make that scan green.

The runtime probe used candidate image `sha256:f3b2aa75a20dbead7bca43d378a586e4811e64d74a39fb32a7aee7b2e5a47664`: Linux x86_64, UID 10001, effective capabilities zero, `NoNewPrivs=1`, SQLite 3.46.1, Python's bundled Expat 2.8.3 and PyMuPDF 1.28.2. The Linux confinement probe denied network and sibling-job reads/writes while allowing the job's own files. The final release image must be scanned and confinement-tested after building; this identifier records the dependency review baseline, not a promise about arbitrary later tags.

The following conclusions are limited to this code, locked dependencies and the documented container configuration. They describe attack prerequisites and reviewed application paths; they do not assert that the installed packages are patched. Privileged containers, arbitrary operator scripts, added import formats, untrusted custom databases or dependency changes require a new review.

| Advisory / component | Prerequisite and reviewed path |
|---|---|
| [CVE-2026-76642](https://security-tracker.debian.org/tracker/CVE-2026-76642), [78408](https://security-tracker.debian.org/tracker/CVE-2026-78408), [78409](https://security-tracker.debian.org/tracker/CVE-2026-78409), [78410](https://security-tracker.debian.org/tracker/CVE-2026-78410), util-linux | Require privileged mount helpers, namespace/cgroup operations, or authorized fstab mount paths. The service runs as UID 10001 with no capabilities/no privilege escalation, exposes no mount or namespace API, and spawns fixed Python worker commands. No corresponding application entry path was found. |
| [CVE-2026-41992](https://security-tracker.debian.org/tracker/CVE-2026-41992), gzip | Requires GNU gzip processing specially ordered LZW/LZH input. Imports are PDFs; maintenance uses Python ZIP processing, with no GNU gzip command or LZH path. |
| [CVE-2025-69720](https://security-tracker.debian.org/tracker/CVE-2025-69720), ncurses | Concerns the `infocmp` utility. The server and workers do not invoke it or offer terminal-capability processing. |
| [CVE-2026-16742](https://security-tracker.debian.org/tracker/CVE-2026-16742), systemd | Requires systemd-homed and its managed local users. The image has no systemd-homed executable and runs uvicorn, not a systemd/homed service. Presence of related libraries is not evidence that this service exists. |
| [CVE-2026-54369](https://security-tracker.debian.org/tracker/CVE-2026-54369), ACL | Requires a privileged caller applying pathname-based ACL operations to attacker-controlled paths. This service has no ACL API and no privileged runtime. Archive restoration rejects links and uses ordinary file modes. |
| [CVE-2026-13221](https://security-tracker.debian.org/tracker/CVE-2026-13221), [57432](https://security-tracker.debian.org/tracker/CVE-2026-57432), [8376](https://security-tracker.debian.org/tracker/CVE-2026-8376), Perl core | Require Perl regex or pack/unpack processing of attacker input; 8376 specifically concerns 32-bit builds. Application matching and processing are Python/JavaScript, with no Perl subprocess or embedded Perl path. The reviewed container is 64-bit. |
| [CVE-2026-42496](https://security-tracker.debian.org/tracker/CVE-2026-42496), [42497](https://security-tracker.debian.org/tracker/CVE-2026-42497), [9538](https://security-tracker.debian.org/tracker/CVE-2026-9538), Perl Archive::Tar | Require calling Perl archive extraction on hostile archives. Application restore uses Python zipfile with explicit path/type/size/checksum checks; no Archive::Tar path is used. Source-package generation is a local build operation on controlled project files. |
| [CVE-2026-48962](https://security-tracker.debian.org/tracker/CVE-2026-48962), [57433](https://security-tracker.debian.org/tracker/CVE-2026-57433), Perl modules | Require IO::Compress output globs or Storable deserialization. Neither API is used by the application or its Python worker commands. |
| [CVE-2026-11822](https://security-tracker.debian.org/tracker/CVE-2026-11822), [11824](https://security-tracker.debian.org/tracker/CVE-2026-11824), SQLite | Require malicious FTS5 data and MATCH-query execution. The service has no FTS virtual tables, MATCH queries, SQL-entry API or database-upload endpoint. Offline restore now rejects views, triggers and virtual/shadow tables before integrity checking and mutation, and disables trusted schema. Tests confirm that these schemas are rejected without publishing a restored database or running a trigger. Restore is still restricted to operator-controlled application backups; checksum validation is not archive authentication. |
| [CVE-2026-76956](https://security-tracker.debian.org/tracker/CVE-2026-76956), [76957](https://security-tracker.debian.org/tracker/CVE-2026-76957), Expat | Require hostile XML (hash flooding) or custom encoding callback handling (use-after-free). Importing the PDF parser did not import Python pyexpat; code review found no ElementTree/pyexpat/XML parsing call in the application, pdfplumber/pdfminer or PyMuPDF4LLM Python paths. MuPDF uses its own [XML implementation](https://raw.githubusercontent.com/ArtifexSoftware/mupdf/1.28.2/source/fitz/xml.c); its runtime shared-library dependency list does not link Expat. Fontconfig remains a possible native XML consumer, but its configuration is installation-controlled: parser environment is rebuilt, system font configuration is read-only, and upload filenames are generated PDF names rather than font configuration paths. No input-controlled Expat path was established in this review. Because native/transitive paths require particular care, keep these findings open for independent review before an Internet-hosted pilot. |

These checks support the documented LAN validation deployment. They do not approve Internet exposure or untrusted operator tooling. In particular, Expat remains installed and its open review is not converted into a blanket exception. The baseline scan and exact image digest should accompany any later security review. New team routes are separately tested for unauthenticated access, cross-workspace reads/writes, viewer restrictions, stale-tab protection, revocation, password recovery and safe audit attribution. Maintenance tests cover corruption, traversal, links, expansion limits, executable SQLite schemas and preserving originals.

## Remaining release gates

- Complete licensing/legal/privacy review and publish the exact corresponding source and dependency notices before a hosted pilot. Publishing source/install packages does not deploy a hosted website.
- Validate the target production kernel with `python -m backend.sandbox_check`; unsupported confinement environments fail closed. Production support is the hardened Linux Docker deployment; native macOS is for development.
- Put any LAN private deployment behind a TLS reverse proxy and enable the application’s named web authentication. Do not add a second browser Basic Auth prompt; installation administration requires a named administrator. Preserve the configured Host and Origin; apply per-client request limits at the trusted proxy.
- Re-run CI and the image scan for the actual release digest. These checks are not a comprehensive penetration test.

## PDF engine migration

The earlier engine-specific evidence above is historical and does not describe
the PDFium replacement image. New builds use pdfplumber/pdfminer and PDFium,
retain the subprocess sandbox, and are built from vendored target-platform
dependencies with networking disabled. Run `scripts/audit_pdf_dependencies.py`
inside the final image and `python -m backend.sandbox_check`; the latter must
still deny network and sibling-job file access. No optional legacy engine is
installed. Re-run advisory scanning for the actual image before release.
