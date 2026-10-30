# Managed cloud development

Work in the existing `/workspace/CloudPulse` checkout. Each cloud task is isolated; do not create a Git worktree unless explicitly requested.

- Install/refresh: `bash scripts/cloud-setup.sh`.
- Start and validate services: `bash scripts/cloud-start.sh`.
- Tests: `.venv/bin/pytest -q tests`; lint: `.venv/bin/ruff check backend agent tests scripts`.
- Dashboard build: `npm run build --prefix frontend`.

These helpers assume Python 3.12+, Node 22+, npm, and the managed Docker daemon. Preserve inherited proxy and TLS settings. Docker builds receive the combined CA bundle through an optional BuildKit secret from ignored `.local/compose-cloud.json`. Session trust data is never copied into images. The normal local workflow uses `compose.yaml` alone and does not require cloud-specific configuration.

Some command sandboxes restrict all socket access, including FastAPI's test client and Docker; use the platform's supported command escalation when needed. Do not disable verification or bypass the proxy.

Generated `.env`, installed dependencies, images, and PostgreSQL data must remain private. Live containers do not necessarily survive snapshots; rerun the start helper. Scripts generate no new credentials if `.env` exists. The smoke creates a clearly named real-reading host and disables it afterward. No preview links are provided by this onboarding workflow.

Environment configuration drafts store installation and startup instructions separately from the runtime. Saving a draft does not publish a filesystem snapshot or validate restoration in a new task.
