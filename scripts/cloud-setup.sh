#!/usr/bin/env bash
set -euo pipefail
cd /workspace/CloudPulse
python -m venv .venv
.venv/bin/python -m pip install --cache-dir /workspace/.pip-cache -r requirements-dev.lock
npm ci --prefix frontend --cache /workspace/.npm-cache
npm run build --prefix frontend
.venv/bin/python scripts/bootstrap.py
mkdir -p .local
.venv/bin/python - <<'PY'
import json
from pathlib import Path
config = {
    "secrets": {"proxy_ca": {"file": "/etc/ssl/certs/ca-certificates.crt"}},
    "services": {name: {"build": {"secrets": ["proxy_ca"]}} for name in ("backend", "frontend", "retention", "migrate", "test")},
}
Path('.local/compose-cloud.json').write_text(json.dumps(config))
PY
docker compose -f compose.yaml -f .local/compose-cloud.json build
