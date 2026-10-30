# Verification report — 30 October 2026

This follow-up review supersedes the initial 17-test implementation report. Linux: Python 3.12.14, Node 24.19.0, Docker 28.4.0, Compose 2.40.3; frontend container builds use Node 22. See [production assessment](PRODUCTION_REVIEW.md) for findings and limits.

| Check | Observed result |
|---|---|
| `.venv/bin/pytest -q tests` | 55 passed, 3 PostgreSQL-only checks skipped |
| Compose PostgreSQL test profile | 58 passed, none skipped; API tests execute under the restricted runtime role in disposable schemas |
| Ruff lint and format checks | Passed for backend, agent, tests and scripts |
| `pip check` | Passed |
| Frontend typecheck + Vite production build | Passed |
| Full Compose image builds and `up -d --wait` | Passed; DB/API/frontend readiness verified, migrator exits successfully, retention runs |
| Migration/schema verification | Upgrade/check/downgrade-to-base/upgrade/check passed in an isolated PostgreSQL schema; deployed schema is revision `0002` |
| `scripts/privilege_smoke.py` inside backend | Runtime role has no superuser/role/database creation privilege; DDL and migration-table reads denied |
| `scripts/compose_smoke.py` | Real psutil/agent CLI ingestion, persistent history, eight concurrent duplicate retries and firing/recovery transitions passed |
| `scripts/browser_smoke.py` | Actual agent CLI → direct PostgreSQL rows → equal REST data → matching metric cards and three chart series; desktop/mobile, rules, auth/sign-out passed with no browser runtime errors |
| `scripts/browser_regressions.py` | Delayed registration response cannot expose a key after sign-out/re-login |
| `scripts/restart_smoke.py` | Backend replacement followed by Nginx API recovery; previously stored observation still queryable |
| Nginx configuration | `nginx -t` passed |
| npm audit | Zero known vulnerabilities in locked frontend packages |
| Python audit against `constraints.txt` | Zero known vulnerabilities after pytest upgrade (PyPI advisory service) |

Reproduce the PostgreSQL suite locally with `docker compose --profile test run --build --rm test`. In the managed proxy environment add `-f compose.yaml -f .local/compose-cloud.json`. Tests use generated schemas and always drop them in cleanup; do not provide unrelated production database credentials. The admin test connection prepares schema/grants, while API requests use the runtime account.

The three PostgreSQL-only tests cover simultaneous first delivery, bad-key requests while another transaction holds the host lock, and migration roundtrips. SQLite cannot establish these properties. A Starlette deprecation warning remains for its current httpx TestClient adapter; all tests execute and complete successfully.

The strengthened browser smoke requires the optional `requirements-browser.txt`, an available Chromium executable, Docker access and a running Compose deployment. Screenshots default to ignored `.local/review-screenshots`. It creates a unique real-reading registration and disables it afterward. No fabricated production measurements are used.

Not claimed: Windows runtime execution, remote CI success, remote TLS deployment, internet production safety, image/OS scanning, load capacity, backup restoration or fresh-task snapshot restoration. No push/PR was attempted in this review; changes are committed locally.
