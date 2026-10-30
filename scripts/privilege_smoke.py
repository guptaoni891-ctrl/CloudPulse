"""Run inside the backend container to verify the deployed runtime DB boundary."""

from app.db import SessionLocal
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

with SessionLocal() as db:
    role = (
        db.execute(
            text(
                "SELECT current_user AS name, rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname=current_user"
            )
        )
        .mappings()
        .one()
    )
    assert role["name"] == "cloudpulse_runtime"
    assert not role["rolsuper"] and not role["rolcreatedb"] and not role["rolcreaterole"]
    try:
        db.execute(text("CREATE TABLE public.cloudpulse_privilege_probe (id integer)"))
    except DBAPIError as exc:
        assert exc.orig.sqlstate == "42501"
        db.rollback()
    else:
        db.rollback()
        raise AssertionError("Runtime role unexpectedly allowed DDL")
    try:
        db.execute(text("SELECT * FROM alembic_version"))
    except DBAPIError as exc:
        assert exc.orig.sqlstate == "42501"
        db.rollback()
    else:
        raise AssertionError("Runtime role can access migration bookkeeping")
print(
    "PASS: API role has no superuser/create-role/create-database privilege; DDL and migration-table access denied"
)
