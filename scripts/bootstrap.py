"""Create local random credentials without overwriting an existing .env."""

import os
import secrets
from pathlib import Path

path = Path(__file__).resolve().parents[1] / ".env"
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit(".env exists; leaving it unchanged. Use your existing credentials.") from None
with os.fdopen(fd, "w") as out:
    out.write(
        f"POSTGRES_PASSWORD={secrets.token_hex(24)}\nCLOUDPULSE_ADMIN_TOKEN={secrets.token_urlsafe(48)}\nCLOUDPULSE_RETENTION_DAYS=30\n"
    )
print("Created .env. Read CLOUDPULSE_ADMIN_TOKEN locally to sign in. Never commit this file.")
