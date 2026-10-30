"""Create private local credentials; preserve existing values on repeat runs."""

import os
import secrets
from pathlib import Path

path = Path(__file__).resolve().parents[1] / ".env"
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    # Upgrade old local deployments by adding only the new runtime-role secret.
    names = {line.partition("=")[0].strip() for line in path.read_text().splitlines()}
    if "CLOUDPULSE_DB_PASSWORD" not in names:
        with path.open("a") as out:
            out.write(f"\nCLOUDPULSE_DB_PASSWORD={secrets.token_hex(24)}\n")
        print("Added runtime database credential to .env; existing values preserved")
    else:
        print(".env exists; existing credentials preserved")
else:
    with os.fdopen(fd, "w") as out:
        out.write(
            f"POSTGRES_PASSWORD={secrets.token_hex(24)}\n"
            f"CLOUDPULSE_DB_PASSWORD={secrets.token_hex(24)}\n"
            f"CLOUDPULSE_ADMIN_TOKEN={secrets.token_urlsafe(48)}\n"
            "CLOUDPULSE_RETENTION_DAYS=30\n"
        )
    print("Created .env. Read CLOUDPULSE_ADMIN_TOKEN locally to sign in. Never commit this file.")
