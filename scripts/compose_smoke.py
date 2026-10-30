"""Test the Compose deployment through the dashboard reverse proxy."""

import os
import subprocess
import sys
from pathlib import Path

for line in Path(".env").read_text().splitlines():
    name, _, value = line.partition("=")
    if name == "CLOUDPULSE_ADMIN_TOKEN":
        os.environ.setdefault(name, value)
os.environ["CLOUDPULSE_SERVER"] = "http://127.0.0.1:8080"
subprocess.run([sys.executable, "scripts/smoke.py"], check=True)
