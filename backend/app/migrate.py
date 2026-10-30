"""Run privileged schema upgrades, then provision a restricted application role."""

import os
import re
import subprocess
import sys

from psycopg import sql

from .config import settings
from .db import make_engine

ROLE = "cloudpulse_runtime"


def main():
    password = os.environ.get("CLOUDPULSE_DB_PASSWORD", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,}", password):
        raise SystemExit("Set CLOUDPULSE_DB_PASSWORD to at least 32 random URL-safe characters")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    engine = make_engine(settings().database_url)
    try:
        with engine.begin() as connection:
            with connection.connection.driver_connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,))
                if not cursor.fetchone():
                    cursor.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(ROLE)))
                cursor.execute(
                    sql.SQL(
                        "ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}"
                    ).format(sql.Identifier(ROLE), sql.Literal(password))
                )
                cursor.execute(
                    sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(ROLE))
                )
                cursor.execute(
                    sql.SQL(
                        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE hosts, metrics, rules, alerts TO {}"
                    ).format(sql.Identifier(ROLE))
                )
                cursor.execute(
                    sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(
                        sql.Identifier(ROLE)
                    )
                )
    finally:
        engine.dispose()
    print("Migrations complete; restricted runtime database role provisioned")


if __name__ == "__main__":
    main()
