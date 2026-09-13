# Licensing and source availability

This application is licensed under GNU AGPL version 3 or later; see LICENSE.
Copyright (c) 2026 FGT Upgrade Review contributors.

Distributions must include corresponding source, build instructions, dependency
lockfiles, license texts and notices. Hosted modified versions must provide the
source offer required by the AGPL. Set SOURCE_CODE_URL to the exact release's
public corresponding-source URL before a public launch, and keep it available.

PDF extraction uses pdfplumber and pdfminer.six (MIT). Document metadata,
bookmarks, page counts and rendering use pypdfium2 (Apache-2.0 OR BSD-3-Clause)
and its bundled PDFium binary (BSD-style license and accompanying third-party
notices). This distribution contains no PyMuPDF, MuPDF, PyMuPDF4LLM or PyMuPDF-Layout
package. The test fixture writer is ReportLab (BSD).

The exact vendored package/version/license inventory is in
`licenses/DEPENDENCIES.json`. Original license files are retained under
`licenses/python` and `licenses/npm`, including PDFium's platform-specific
`BUILD_LICENSES` for all bundled native components. The wrapper's CC-BY-4.0
documentation notice is retained alongside its Apache/BSD license texts.
`vendor/MANIFEST.json` binds the vendored artifacts to SHA-256 digests.
Debian packages and pinned base images retain their own notices, available in
the image under `/usr/share/doc` and in their bundled archives. GNU-licensed
system utilities remain independently licensed components.

Other principal components include
FastAPI (MIT), SQLAlchemy (MIT), Requests (Apache-2.0), pdfplumber (MIT),
React (MIT), Vite (MIT), Swagger UI (Apache-2.0), Node.js (MIT and bundled dependency licenses), and the Outfit and JetBrains Mono fonts (SIL OFL-1.1).
Dependency packages retain their own license files. CI produces a dependency
inventory; review its licenses and redistribute required notices with releases.

Fortinet/FortiGate/FortiOS are third-party marks. This independent project is
not affiliated with or endorsed by Fortinet. Fortinet documentation remains
subject to its own terms and copyright. No release notes or user configurations
are included in the distributed image or packaged source. The private regression
corpus is excluded from both. Preserve source notices when
creating private reports. User-provided files do not grant redistribution rights.

Public-launch gate: review document processing, hosting terms, privacy/retention,
trademarks, and third-party license obligations with qualified counsel. The
software cannot guarantee legal clearance. Hosted scraping is disabled.
