from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.db import session
from app.main import app
from app.models import Host, Metric
from sqlalchemy import select


def sample(**changes):
    return {
        "sample_id": str(uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "cpu": 20,
        "memory": 40,
        "disk": 50,
        "network_sent_bytes": 12_000_000_000,
        "network_recv_bytes": 20_000_000_000,
        **changes,
    }


def ingest(client, reg, payload):
    return client.post(
        f"/api/v1/hosts/{reg['host']['id']}/metrics",
        headers={"X-API-Key": reg["api_key"]},
        json=payload,
    )


def test_health_and_auth(client, admin):
    assert client.get("/api/v1/health").json()["status"] == "ok"
    assert client.get("/api/v1/hosts").status_code == 401
    assert client.post("/api/v1/hosts", json={"name": "x"}).status_code == 401
    assert client.get("/api/v1/hosts", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/v1/hosts", headers=admin).json() == []


def test_ingestion_is_persistent_and_keys_are_hashed(client, admin, registered):
    reg = registered
    path = f"/api/v1/hosts/{reg['host']['id']}"
    assert (
        client.post(path + "/metrics", json=sample(), headers={"X-API-Key": "wrong"}).status_code
        == 401
    )
    assert ingest(client, reg, sample()).status_code == 202
    result = client.get(path, headers=admin).json()
    assert result["online"] and result["latest"]["cpu"] == 20
    assert result["latest"]["network_sent_bytes"] == 12_000_000_000
    assert "key_hash" not in str(result)
    with next(app.dependency_overrides[session]()) as db:
        host = db.get(Host, reg["host"]["id"])
        assert len(host.key_hash) == 64 and host.key_hash != reg["api_key"]
        assert db.scalar(select(Metric)).host_id == host.id


@pytest.mark.parametrize(
    "changes",
    [
        {"cpu": 101},
        {"memory": -1},
        {"disk": 101},
        {"network_sent_bytes": -1},
        {"timestamp": "2026-01-01T00:00:00"},
        {"sample_id": "invalid"},
        {"extra": True},
    ],
)
def test_invalid_samples(client, registered, changes):
    assert ingest(client, registered, sample(**changes)).status_code == 422


def test_duplicate_and_history_range(client, admin, registered):
    timestamp = datetime.now(UTC) - timedelta(minutes=10)
    payload = sample(timestamp=timestamp.isoformat())
    assert ingest(client, registered, payload).json()["duplicate"] is False
    assert ingest(client, registered, payload).json()["duplicate"] is True
    assert ingest(client, registered, sample()).status_code == 202
    path = f"/api/v1/hosts/{registered['host']['id']}/metrics"
    response = client.get(
        path,
        headers=admin,
        params={
            "start": (timestamp - timedelta(minutes=1)).isoformat(),
            "end": (timestamp + timedelta(minutes=1)).isoformat(),
        },
    )
    assert len(response.json()) == 1
    assert (
        client.get(path, headers=admin, params={"start": "2026-01-01T00:00:00"}).status_code == 422
    )
    assert client.get(path).status_code == 401
    assert client.get(path, headers=admin, params={"limit": 5001}).status_code == 422


def test_alert_transitions_and_out_of_order(client, admin, registered):
    path = f"/api/v1/hosts/{registered['host']['id']}"
    assert (
        client.put(
            path + "/rules", headers=admin, json={"metric": "cpu", "threshold": 80}
        ).status_code
        == 200
    )
    t = datetime.now(UTC) - timedelta(minutes=1)
    for i, value in enumerate([90, 95, 20, 10]):
        assert (
            ingest(
                client,
                registered,
                sample(cpu=value, timestamp=(t + timedelta(seconds=i)).isoformat()),
            ).status_code
            == 202
        )
    # A delayed old breach must not reopen a recovered alert.
    ingest(client, registered, sample(cpu=99, timestamp=(t - timedelta(seconds=1)).isoformat()))
    alerts = client.get("/api/v1/alerts", headers=admin).json()
    assert [a["state"] for a in alerts] == ["recovered", "firing"]
    assert client.get(path + "/rules", headers=admin).json()[0]["active"] is False
    assert (
        client.put(
            path + "/rules", headers=admin, json={"metric": "network", "threshold": 80}
        ).status_code
        == 422
    )


def test_disable_rotate_and_offline(client, admin, registered):
    path = f"/api/v1/hosts/{registered['host']['id']}"
    assert client.get(path, headers=admin).json()["online"] is False
    client.patch(path, headers=admin, json={"enabled": False})
    assert ingest(client, registered, sample()).status_code == 401
    client.patch(path, headers=admin, json={"enabled": True})
    new = client.post(path + "/rotate-key", headers=admin).json()["api_key"]
    assert ingest(client, registered, sample()).status_code == 401
    registered["api_key"] = new
    assert ingest(client, registered, sample()).status_code == 202
    with next(app.dependency_overrides[session]()) as db:
        db.get(Host, registered["host"]["id"]).last_seen = datetime.now(UTC) - timedelta(minutes=2)
        db.commit()
    assert client.get(path, headers=admin).json()["online"] is False


def test_future_and_retention(client, admin, registered):
    assert (
        ingest(
            client,
            registered,
            sample(timestamp=(datetime.now(UTC) + timedelta(hours=1)).isoformat()),
        ).status_code
        == 422
    )
    assert (
        ingest(
            client,
            registered,
            sample(timestamp=(datetime.now(UTC) - timedelta(days=40)).isoformat()),
        ).status_code
        == 422
    )
    ingest(client, registered, sample())
    with next(app.dependency_overrides[session]()) as db:
        db.scalar(select(Metric)).timestamp = datetime.now(UTC) - timedelta(days=40)
        db.commit()
    assert client.post("/api/v1/maintenance/retention").status_code == 401
    result = client.post("/api/v1/maintenance/retention", headers=admin).json()
    assert result["deleted_metrics"] == 1
