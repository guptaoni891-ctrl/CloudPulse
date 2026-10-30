"""Cross-platform collector. Configuration is explicit; no secret files are written."""

import argparse
import json
import logging
import os
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4

import httpx
import psutil

log = logging.getLogger("cloudpulse-agent")


def server_url(value: str) -> str:
    parsed = urlparse(value)
    # Accessing .port also validates malformed/non-numeric port values.
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("CLOUDPULSE_SERVER has an invalid port") from exc
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or any(char.isspace() or ord(char) < 32 for char in value)
        or port == 0
    ):
        raise ValueError(
            "CLOUDPULSE_SERVER must be an HTTP(S) base URL without credentials, query or fragment"
        )
    if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Use HTTPS when sending credentials to a remote server")
    return value.rstrip("/")


def collect(disk_path: str) -> dict:
    network = psutil.net_io_counters()
    return {
        "sample_id": str(uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "cpu": psutil.cpu_percent(interval=1),
        "memory": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage(disk_path).percent,
        "network_sent_bytes": network.bytes_sent,
        "network_recv_bytes": network.bytes_recv,
    }


def send(client, url, sample, attempts=5, sleep=time.sleep):
    for attempt in range(attempts):
        try:
            response = client.post(url, json=sample)
            if 300 <= response.status_code < 500 and response.status_code not in (408, 429):
                raise RuntimeError(
                    f"Ingestion rejected ({response.status_code}); check agent configuration and clock"
                )
            response.raise_for_status()
            return True
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            log.warning(
                json.dumps(
                    {
                        "event": "send_retry",
                        "attempt": attempt + 1,
                        "error_type": type(exc).__name__,
                    }
                )
            )
            if attempt + 1 < attempts:
                sleep(min(30, 2**attempt) + random.uniform(0, 1))
    log.error(json.dumps({"event": "sample_dropped", "sample_id": sample["sample_id"]}))
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        base = server_url(os.getenv("CLOUDPULSE_SERVER", "http://127.0.0.1:8000"))
    except ValueError as exc:
        parser.error(str(exc))
    host_id = os.getenv("CLOUDPULSE_HOST_ID", "")
    key = os.getenv("CLOUDPULSE_AGENT_KEY", "")
    try:
        host_id = str(UUID(host_id))
        interval = float(os.getenv("CLOUDPULSE_INTERVAL", "10"))
        if not 2 <= interval <= 3600:
            raise ValueError()
    except ValueError:
        parser.error("Set a valid CLOUDPULSE_HOST_ID and interval between 2 and 3600 seconds")
    if not key:
        parser.error("Set CLOUDPULSE_AGENT_KEY to the registration key")
    disk_path = os.getenv("CLOUDPULSE_DISK_PATH", Path.home().anchor)
    url = f"{base}/api/v1/hosts/{host_id}/metrics"
    try:
        with httpx.Client(headers={"X-API-Key": key}, timeout=10, follow_redirects=False) as client:
            while True:
                tick = time.monotonic()
                ok = send(client, url, collect(disk_path))
                if args.once:
                    raise SystemExit(0 if ok else 1)
                time.sleep(max(0, interval - (time.monotonic() - tick)))
    except KeyboardInterrupt:
        log.info(json.dumps({"event": "agent_stopped"}))
    except (RuntimeError, OSError, psutil.Error) as exc:
        log.error(json.dumps({"event": "agent_failed", "error": str(exc)}))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
