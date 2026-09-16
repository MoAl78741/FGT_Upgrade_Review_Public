# Regression requirements

Use `.venv/bin/python scripts/check.py` before concluding a source change. The runner uses disposable state and must never target a deployed server. During development, `--feature <id>` narrows backend/browser checks; `--list` shows IDs. Run the complete check before handoff. Do not start Docker Desktop on an operator workstation to run these tests.

Read docs/TESTING.md for offline setup and release-only checks. Add every new feature, API operation, and backend test module to tests/feature_matrix.json with substantive tests. The map is accounting, not evidence by itself. Preserve original release-note text and test both positive and negative authorization paths.

Do not edit source while the final suite runs, suppress failures, update goldens automatically, or describe omitted checks as passing. Use release mode with a sealed external corpus for parser changes; keep publisher PDFs outside distributable source. Container sandbox/image checks belong on the Linux CI/deployment test host, never against production data. Report exact failures and exclusions.
