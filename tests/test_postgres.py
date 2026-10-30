"""PostgreSQL-only guarantees that SQLite cannot validate."""

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from app.main import app
from app.models import Host
from sqlalchemy import select
from test_api import ingest, sample

pytestmark = pytest.mark.skipif(
    not os.getenv("CLOUDPULSE_TEST_DATABASE_URL"),
    reason="requires PostgreSQL; run the Compose test profile",
)


def test_simultaneous_first_delivery_inserts_exactly_once(client, admin, registered):
    payload = sample()
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: ingest(client, registered, payload), range(8)))
    assert all(response.status_code == 202 for response in responses)
    assert sum(not response.json()["duplicate"] for response in responses) == 1
    rows = client.get(f"/api/v1/hosts/{registered['host']['id']}/metrics", headers=admin).json()
    assert len(rows) == 1 and rows[0]["network_sent_bytes"] == 12_000_000_000


def test_bad_key_does_not_wait_for_a_host_lock(client, registered):
    pool = ThreadPoolExecutor(max_workers=1)
    with app.state.test_session_factory() as db:
        db.scalar(select(Host).where(Host.id == registered["host"]["id"]).with_for_update())
        try:
            bad = {**registered, "api_key": "wrong-key"}
            future = pool.submit(ingest, client, bad, sample())
            assert future.result(timeout=3).status_code == 401
        finally:
            db.rollback()
            pool.shutdown(wait=True)


def test_migration_upgrade_downgrade_roundtrip():
    import subprocess
    import sys
    from pathlib import Path
    from uuid import uuid4

    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from sqlalchemy.schema import CreateSchema, DropSchema

    schema = "cloudpulse_migration_" + uuid4().hex
    root_url = make_url(os.environ["CLOUDPULSE_TEST_DATABASE_URL"])
    root_engine = create_engine(root_url)
    config = Path("/app/alembic.ini")
    if not config.exists():
        config = Path(__file__).resolve().parents[1] / "backend" / "alembic.ini"
    url = root_url.update_query_dict({"options": f"-csearch_path={schema}"})
    env = {**os.environ, "CLOUDPULSE_DATABASE_URL": url.render_as_string(hide_password=False)}
    with root_engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    try:
        for command in [
            ("upgrade", "head"),
            ("check",),
            ("downgrade", "base"),
            ("upgrade", "head"),
            ("check",),
        ]:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "-c", str(config), *command],
                env=env,
                capture_output=True,
                text=True,
            )
            detail = (result.stdout + result.stderr).replace(
                root_url.password or "<none>", "[redacted]"
            )
            assert result.returncode == 0, detail
    finally:
        with root_engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        root_engine.dispose()
