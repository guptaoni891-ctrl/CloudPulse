"""Replace the backend and verify proxy recovery plus persistence of an existing sample."""

import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx

base = os.getenv("CLOUDPULSE_SERVER", "http://127.0.0.1:8080")
token = os.getenv("CLOUDPULSE_ADMIN_TOKEN")
if not token:
    token = next(
        line.partition("=")[2]
        for line in Path(".env").read_text().splitlines()
        if line.startswith("CLOUDPULSE_ADMIN_TOKEN=")
    )
with httpx.Client(
    base_url=base, headers={"Authorization": "Bearer " + token}, timeout=10
) as client:
    response = client.get("/api/v1/hosts")
    response.raise_for_status()
    host = next(h for h in response.json() if h["latest"])
    original = host["latest"]
    subprocess.run(
        ["docker", "compose", "up", "-d", "--force-recreate", "--wait", "backend"], check=True
    )
    for _ in range(20):
        try:
            response = client.get("/api/v1/health")
            if response.status_code == 200:
                break
        except httpx.TransportError:
            pass
        time.sleep(1)
    else:
        raise SystemExit("Proxy did not recover after backend replacement")
    stamp = datetime.fromisoformat(original["timestamp"])
    response = client.get(
        f"/api/v1/hosts/{host['id']}/metrics",
        params={
            "start": (stamp - timedelta(seconds=1)).isoformat(),
            "end": (stamp + timedelta(seconds=1)).isoformat(),
        },
    )
    response.raise_for_status()
    assert any(
        m["sample_id"] == original["sample_id"] and m["cpu"] == original["cpu"]
        for m in response.json()
    )
print(
    "PASS: Nginx API proxy recovered after backend replacement; existing PostgreSQL sample persisted"
)
