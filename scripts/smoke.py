"""Exercise a running API using a real psutil reading. Reads token from environment."""

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from cloudpulse_agent.main import collect

base = os.getenv("CLOUDPULSE_SERVER", "http://127.0.0.1:8000")
headers = {"Authorization": "Bearer " + os.environ["CLOUDPULSE_ADMIN_TOKEN"]}
with httpx.Client(base_url=base, timeout=15) as client:
    for _attempt in range(60):
        try:
            if client.get("/api/v1/health").status_code == 200:
                break
        except httpx.TransportError:
            pass
        time.sleep(1)
    else:
        raise SystemExit("API health check never succeeded")
    response = client.post("/api/v1/hosts", headers=headers, json={"name": "smoke-real-machine"})
    response.raise_for_status()
    reg = response.json()
    path = "/api/v1/hosts/" + reg["host"]["id"]
    payload = collect(Path.home().anchor)
    response = client.post(path + "/metrics", headers={"X-API-Key": reg["api_key"]}, json=payload)
    response.raise_for_status()
    response = client.get(path + "/metrics", headers=headers)
    response.raise_for_status()
    assert response.json()[-1]["sample_id"] == payload["sample_id"]
    assert client.get(path, headers=headers).json()["online"]

    # Concurrent retries must insert exactly one copy of the same real sample.
    def retry(_):
        result = client.post(path + "/metrics", headers={"X-API-Key": reg["api_key"]}, json=payload)
        result.raise_for_status()
        return result.json()

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(result["duplicate"] for result in pool.map(retry, range(8)))
    assert len(client.get(path + "/metrics", headers=headers).json()) == 1
    # Evaluate actual memory readings against deliberately low/high thresholds.
    for threshold in (0.01, 100):
        client.put(
            path + "/rules", headers=headers, json={"metric": "memory", "threshold": threshold}
        ).raise_for_status()
        reading = collect(Path.home().anchor)
        assert 0.01 < reading["memory"] < 100, (
            "Smoke requires a machine with nonzero free/used memory"
        )
        client.post(
            path + "/metrics", headers={"X-API-Key": reg["api_key"]}, json=reading
        ).raise_for_status()
    transitions = client.get(
        "/api/v1/alerts", headers=headers, params={"host_id": reg["host"]["id"]}
    ).json()
    assert [event["state"] for event in transitions] == ["recovered", "firing"]
    subprocess.run(
        [sys.executable, "-m", "cloudpulse_agent.main", "--once"],
        env={
            **os.environ,
            "CLOUDPULSE_SERVER": base,
            "CLOUDPULSE_HOST_ID": reg["host"]["id"],
            "CLOUDPULSE_AGENT_KEY": reg["api_key"],
        },
        check=True,
    )
    assert len(client.get(path + "/metrics", headers=headers).json()) == 4
    client.patch(path, headers=headers, json={"enabled": False}).raise_for_status()
print(
    "PASS: real psutil -> authenticated ingestion -> PostgreSQL history, concurrent retries, alert firing/recovery, online status"
)
