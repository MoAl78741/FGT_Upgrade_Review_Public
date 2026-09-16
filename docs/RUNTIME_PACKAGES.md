# Runtime package review

Reviewed 2026-09-16 from Dockerfiles, vendored Debian artifacts and parser confinement code. No runtime packages were removed in this CI policy change.

| Package group | Role and disposition |
| --- | --- |
| libc6, libc-bin, libsqlite3-0 | Native Python/runtime and SQLite dependencies; retain. |
| libfontconfig1, fontconfig-config, fonts-dejavu-core, fonts-dejavu-mono, libfreetype6, libpng16-16t64, libbrotli1, libexpat1 | Font discovery/rendering libraries and fonts; preserve until PDFium rendering and export parity are validated without them. Presence alone does not establish an exploitable XML path. |
| base-files, bash, gzip, libaudit-common, libaudit1, libcap2, libpcre2-8-0, perl-base, tzdata | Vendored base distribution updates/support packages. Candidates for image minimization, but removing an update archive alone can leave the older vulnerable base package installed. |
| libseccomp.so.2 | Explicitly loaded by backend/parser_sandbox.py. Required for Linux syscall confinement; do not remove. |
| Node runtime | Copied from frontend builder for server-side report rendering; retain. |

The frontend build stage is separate from the runtime image; its npm cache is not copied into runtime. Vendored Python wheels and Debian archives are removed after offline installation. Many scanner findings come from the pinned Python base image, rather than newly added application packages.

A smaller runtime should be evaluated as a separate image change: capture `dpkg-query` inventory and native shared-library dependencies on Linux; identify essential packages and reverse dependencies before removal; then repeat offline builds, sandbox checks, browser/PDF export tests and the sealed real-document corpus. Do not purge Debian essential packages or remove font libraries solely to reduce a scanner count. Refresh the vendored package hashes and notices whenever the actual dependency tree changes.
