<div align="center">

# FortiGate Upgrade Review — Public Edition

### Open-source, PDF-based FortiOS release-note reviews with isolated temporary sessions.

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](docs/DEVELOPMENT.md)
[![React](https://img.shields.io/badge/React-18-149ECA?logo=react&logoColor=white)](frontend/package.json)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](frontend/package.json)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](API_GUIDE.md)
[![Docker](https://img.shields.io/badge/Deploy-Docker-2496ED?logo=docker&logoColor=white)](releases/PUBLIC.md)
[![License](https://img.shields.io/badge/License-AGPL--3.0--or--later-7C3AED)](LICENSE)

**[Features](docs/FEATURES.md) · [Installation](releases/PUBLIC.md) · [API](API_GUIDE.md) · [Security](SECURITY.md) · [Licensing](docs/LICENSING.md)**

</div>

## Purpose and audience

Bring scattered release notes into searchable reports and structured upgrade reviews. Built for network/security engineers, firewall administrators, consultants, and change reviewers who need to connect source evidence with their own assessment.

User-provided PDFs only; hosted scraping is disabled. Reports and original PDFs expire after 24 hours. Sessions are isolated; there are no named accounts or shared report libraries.

## Review workflow

1. Choose From and To releases, optionally including the starting version, and find official PDF download links.
2. Upload PDFs and follow batch progress, per-document timers, page counts, and success/failure outcomes.
3. Search sections, compare release-note descriptions, and optionally consolidate identical entries with their version lists.
4. Analyze a plaintext configuration locally for explained “Potentially relevant” annotations; raw configs and profiles never enter server requests.
5. Save review decisions and checklists, combine report batches, and export HTML/CSV/TXT or browser-printed PDF.

Source text remains separate from reviewer decisions and relevance annotations. Missing sections and partial imports remain visible. This tool does not deploy firmware, certify supported upgrade paths, or guarantee upgrade safety.

## Quick start

```sh
git clone https://github.com/MoAl78741/FGT_Upgrade_Review_Public.git
cd FGT_Upgrade_Review_Public
cp releases/public.env.example .env
# Set PUBLIC_ORIGIN and SOURCE_CODE_URL in .env.
# Configure your HTTPS reverse proxy before starting.
docker compose -p fgt-public up --build -d
```

Open your configured HTTPS origin. Keep the backend port restricted to loopback/proxy access. The public edition requires HTTPS and an exact source offer for the deployed revision.

Defaults: 100 PDFs per job, 50 MiB per PDF, 150 MiB total, 500 pages per document, 30-minute job timeout, two workers, and ten queued jobs. Limits are configurable; see the [environment example](releases/public.env.example).

## Security and privacy

Backend access checks, exact origin/host validation, bounded uploads, isolated PDF parser processes, and restricted non-root containers protect the processing workflow. Fonts and documentation assets are bundled; remote source images are not loaded automatically. Configuration analysis uses local browser memory, with no config-upload endpoint or AI provider integration.

Read [SECURITY.md](SECURITY.md) for implemented controls, open container advisories, and remaining release gates. This repository is not a security clearance for Internet exposure. [Third-party notices](THIRD_PARTY_NOTICES.md) cover source-document and licensing obligations.

## Documentation and architecture

- [Comprehensive feature showcase](docs/FEATURES.md): report views, source fidelity, relevance, review decisions, audiences, architecture, and illustrative screenshots. Screenshots currently show the inherited private interface with synthetic data.
- [API guide](API_GUIDE.md): locally bundled Swagger at `/api/docs`, OpenAPI, GUI/API coverage, and local JavaScript tools.
- [Development guide](docs/DEVELOPMENT.md): Python/Node setup, regression tests, benchmarking, and packaging.
- [Operations](OPERATIONS.md): backup/restore, diagnostics, upgrades, and rollback where applicable.
- [Repository origin](docs/REPOSITORY_ORIGIN.md): source lineage and the scope of this split.

## License

**AGPL-3.0-or-later**. See [LICENSE](LICENSE) and [licensing rationale](docs/LICENSING.md). Commercial use is permitted subject to the license; repository visibility does not replace source-sharing obligations. This independent project is not affiliated with or endorsed by Fortinet. Vendor documents retain their own copyrights and terms.
