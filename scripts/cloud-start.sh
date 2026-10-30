#!/usr/bin/env bash
set -euo pipefail
cd /workspace/CloudPulse
docker compose -f compose.yaml -f .local/compose-cloud.json up -d --wait
.venv/bin/python scripts/compose_smoke.py
