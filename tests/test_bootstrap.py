import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("password", ["short", "@" * 32, " " * 40, "a" * 32 + "\n"])
def test_invalid_runtime_password_fails_before_migration(monkeypatch, password):
    from app.migrate import main

    monkeypatch.setenv("CLOUDPULSE_DB_PASSWORD", password)
    with pytest.raises(SystemExit, match="32 random URL-safe"):
        main()


def test_bootstrap_repeat_preserves_credentials(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "bootstrap.py"
    shutil.copyfile(Path(__file__).resolve().parents[1] / "scripts" / "bootstrap.py", script)

    def run():
        subprocess.run([sys.executable, str(script)], check=True, capture_output=True)

    run()
    path = tmp_path / ".env"
    original = path.read_bytes()
    run()
    assert path.read_bytes() == original
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0
    # Upgrade a legacy deployment without rotating its existing credentials.
    legacy = b"POSTGRES_PASSWORD=existing-db\nCLOUDPULSE_ADMIN_TOKEN=existing-admin\n"
    path.write_bytes(legacy)
    run()
    updated = path.read_bytes()
    assert updated.startswith(legacy)
    assert updated.count(b"CLOUDPULSE_DB_PASSWORD=") == 1
    run()
    assert path.read_bytes() == updated
