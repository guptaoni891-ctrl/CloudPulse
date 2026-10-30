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


def test_offset_history_uses_utc(client, admin, registered):
    moment = datetime.now(UTC) - timedelta(minutes=10)
    assert ingest(client, registered, sample(timestamp=moment.isoformat())).status_code == 202
    from datetime import timezone

    zone = timezone(timedelta(hours=4))
    response = client.get(
        f"/api/v1/hosts/{registered['host']['id']}/metrics",
        headers=admin,
        params={
            "start": (moment - timedelta(seconds=1)).astimezone(zone).isoformat(),
            "end": (moment + timedelta(seconds=1)).astimezone(zone).isoformat(),
        },
    )
    assert len(response.json()) == 1


@pytest.mark.parametrize("timestamp", ["0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00"])
def test_extreme_timestamps_are_validation_errors(client, registered, timestamp):
    assert ingest(client, registered, sample(timestamp=timestamp)).status_code == 422


@pytest.mark.parametrize(
    "changes",
    [{"cpu": True}, {"memory": "20"}, {"network_sent_bytes": False}, {"network_recv_bytes": "100"}],
)
def test_telemetry_types_are_strict(client, registered, changes):
    assert ingest(client, registered, sample(**changes)).status_code == 422


def test_sensitive_responses_are_not_cacheable(client, admin, registered):
    for response in [
        client.get("/api/v1/hosts", headers=admin),
        client.get("/api/v1/hosts"),
        client.post(f"/api/v1/hosts/{registered['host']['id']}/rotate-key", headers=admin),
    ]:
        assert response.headers["cache-control"] == "no-store"


def test_request_body_is_bounded(client, admin):
    result = client.post("/api/v1/hosts", headers=admin, content=b" " * 17000)
    assert result.status_code == 413
    assert result.headers["cache-control"] == "no-store"


def test_host_overview_uses_one_query(client, admin, registered):
    from sqlalchemy import event

    for index in range(3):
        client.post("/api/v1/hosts", headers=admin, json={"name": f"host-{index}"})
    statements = []

    def record(*args):
        statements.append(args[2])

    event.listen(app.state.test_engine, "before_cursor_execute", record)
    try:
        result = client.get("/api/v1/hosts", headers=admin)
    finally:
        event.remove(app.state.test_engine, "before_cursor_execute", record)
    assert result.status_code == 200 and len(result.json()) == 4
    assert len(statements) == 1


def test_chunked_request_body_cannot_bypass_size_limit(client, admin):
    result = client.post("/api/v1/hosts", headers=admin, content=iter([b" " * 9000, b" " * 9000]))
    assert result.status_code == 413


@pytest.mark.parametrize("boundary", ["0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00"])
def test_extreme_history_bounds_return_422(client, admin, registered, boundary):
    path = f"/api/v1/hosts/{registered['host']['id']}/metrics"
    params = {"start": boundary} if boundary.startswith("0001") else {"end": boundary}
    assert client.get(path, headers=admin, params=params).status_code == 422


def test_agent_keys_are_scoped_to_one_host(client, admin, registered):
    other = client.post("/api/v1/hosts", headers=admin, json={"name": "other-host"}).json()
    result = client.post(
        f"/api/v1/hosts/{other['host']['id']}/metrics",
        headers={"X-API-Key": registered["api_key"]},
        json=sample(),
    )
    assert result.status_code == 401
    assert client.get(f"/api/v1/hosts/{other['host']['id']}/metrics", headers=admin).json() == []


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", "/alerts", None),
        ("get", "/hosts/{id}/rules", None),
        ("put", "/hosts/{id}/rules", {"metric": "cpu", "threshold": 90}),
        ("patch", "/hosts/{id}", {"enabled": False}),
        ("post", "/hosts/{id}/rotate-key", None),
        ("post", "/maintenance/retention", None),
    ],
)
def test_management_routes_require_admin(client, registered, method, path, payload):
    path = path.format(id=registered["host"]["id"])
    response = client.request(
        method, "/api/v1" + path, json=payload, headers={"X-API-Key": registered["api_key"]}
    )
    assert response.status_code == 401


def test_invalid_configuration_never_echoes_secrets():
    from app.config import Settings
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as error:
        Settings(admin_token="secret-short-value")
    assert "secret-short-value" not in str(error.value)
