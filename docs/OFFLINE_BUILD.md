# Offline PDFium builds

The vendored build target is **Linux AMD64, Python 3.12, Node 22**. The included
PDFium wheel and Debian packages are platform-specific. Do not use this wheel
set for ARM64 or Windows. Produce and test a separate wheel/base-image set before
claiming another supported offline target.

From the repository root, with Docker and Python 3 available:

```sh
BUILD_NUMBER=local IMAGE_TAG=local sh scripts/build_offline.sh
```

The script verifies SHA-256 checksums, loads the included pinned base images,
and builds with `--network=none`. Docker uses vendored Debian packages,
`pip --no-index --require-hashes`, and `npm ci --offline`. There is no package
installation or remote asset fetch at application startup. The installation
includes original dependency notices; see THIRD_PARTY_NOTICES.md and
licenses/DEPENDENCIES.json.

The runtime dependency lock is `requirements.lock`. Test-only additions are
`requirements-test.lock`; install them after the runtime lock from the same
vendored Linux wheel directory. Development on this Intel Mac uses a separate
`requirements-dev-macos.lock` and `vendor/python/macos-amd64`. This retains the
baseline's cryptography 48.0.1 because cryptography 50 no longer supplies Intel
macOS wheels; the Linux image retains its existing 50.0.1 pin. No source-build
fallback or package downgrade is performed silently.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links vendor/python/macos-amd64 \
  --require-hashes -r requirements-dev-macos.lock
.venv/bin/python scripts/audit_pdf_dependencies.py
.venv/bin/python -m pip check
```

The vendored root contains all application/runtime build packages and base-image
archives, plus target-specific test dependencies. Python/Docker host tools and
optional online vulnerability-scanning tools are prerequisites, not installed
at application runtime. Updating packages is a deliberate online maintenance
step: regenerate locks, download the correct-platform artifacts, regenerate
`vendor/MANIFEST.json` and notices with `scripts/vendor_inventory.py`, then repeat
the offline build, engine audit, sandbox checks and corpus comparison.

The real Fortinet corpus is private test data and excluded from distributed
source packages and Docker images. Synthetic PDF regression tests use ReportLab,
not a removed engine. Existing report data is not reparsed or migrated by this
engine change. New PDF imports record parser revision `8-pdfplumber-pdfium`.
