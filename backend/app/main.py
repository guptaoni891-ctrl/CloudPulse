import hashlib
import hmac
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from .config import settings
from .db import session
from .middleware import RequestSafetyMiddleware
from .models import Alert, Host, Metric, Rule
from .schemas import (
    AlertOut,
    HostCreate,
    HostOut,
    HostUpdate,
    MetricOut,
    Registration,
    RuleInput,
    RuleOut,
    Sample,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("cloudpulse")
app = FastAPI(title="CloudPulse", version="0.1.0")
app.add_middleware(RequestSafetyMiddleware)
DB = Annotated[Session, Depends(session)]


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def now():
    return datetime.now(UTC)


def admin(authorization: Annotated[str | None, Header()] = None):
    expected = "Bearer " + settings().admin_token.get_secret_value()
    if not authorization or not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(401, "Admin authentication required")


Admin = Depends(admin)


def get_host(db, host_id, *, lock=False):
    query = select(Host).where(Host.id == host_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    host = db.scalar(query)
    if not host:
        raise HTTPException(404, "Host not found")
    return host


def host_out(db, host):
    latest = db.scalar(
        select(Metric)
        .where(Metric.host_id == host.id)
        .order_by(Metric.timestamp.desc(), Metric.id.desc())
        .limit(1)
    )
    return serialize_host(host, latest)


def serialize_host(host, latest):
    return HostOut(
        id=host.id,
        name=host.name,
        enabled=host.enabled,
        last_seen=utc(host.last_seen) if host.last_seen else None,
        online=bool(
            host.enabled
            and host.last_seen
            and utc(host.last_seen) > now() - timedelta(seconds=settings().offline_seconds)
        ),
        latest=metric_out(latest) if latest else None,
    )


def metric_out(metric):
    values = {name: getattr(metric, name) for name in MetricOut.model_fields}
    values["timestamp"] = utc(metric.timestamp)
    return MetricOut.model_validate(values)


@app.get("/api/v1/health")
def health(db: DB):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "version": app.version}


@app.exception_handler(Exception)
async def unexpected(request, exc):
    log.error(
        json.dumps(
            {"event": "request_failed", "path": request.url.path, "error_type": type(exc).__name__}
        )
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/v1/hosts", response_model=Registration, status_code=201, dependencies=[Admin])
def register(payload: HostCreate, db: DB):
    key = secrets.token_urlsafe(32)
    host = Host(
        id=str(uuid4()), name=payload.name, key_hash=hashlib.sha256(key.encode()).hexdigest()
    )
    db.add(host)
    db.commit()
    return {"host": host_out(db, host), "api_key": key}


@app.get("/api/v1/hosts", response_model=list[HostOut], dependencies=[Admin])
def hosts(db: DB):
    latest_id = (
        select(Metric.id)
        .where(Metric.host_id == Host.id)
        .order_by(Metric.timestamp.desc(), Metric.id.desc())
        .limit(1)
        .correlate(Host)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Host, Metric).outerjoin(Metric, Metric.id == latest_id).order_by(Host.name, Host.id)
    )
    return [serialize_host(host, latest) for host, latest in rows]


@app.get("/api/v1/hosts/{host_id}", response_model=HostOut, dependencies=[Admin])
def host_detail(host_id: str, db: DB):
    return host_out(db, get_host(db, host_id))


@app.patch("/api/v1/hosts/{host_id}", response_model=HostOut, dependencies=[Admin])
def update_host(host_id: str, payload: HostUpdate, db: DB):
    host = get_host(db, host_id, lock=True)
    host.enabled = payload.enabled
    db.commit()
    return host_out(db, host)


@app.post("/api/v1/hosts/{host_id}/rotate-key", dependencies=[Admin])
def rotate_key(host_id: str, db: DB):
    host = get_host(db, host_id, lock=True)
    key = secrets.token_urlsafe(32)
    host.key_hash = hashlib.sha256(key.encode()).hexdigest()
    db.commit()
    return {"api_key": key}


@app.post("/api/v1/hosts/{host_id}/metrics", status_code=202)
def ingest(
    host_id: str, payload: Sample, db: DB, x_api_key: Annotated[str | None, Header()] = None
):
    # Invalid credentials never acquire a host row lock. PostgreSQL rechecks
    # this predicate after waiting for concurrent disable/key rotation updates.
    if not x_api_key:
        raise HTTPException(401, "Invalid agent credentials")
    host = db.scalar(
        select(Host)
        .where(
            Host.id == host_id,
            Host.enabled.is_(True),
            Host.key_hash == hashlib.sha256(x_api_key.encode()).hexdigest(),
        )
        .with_for_update()
    )
    if host is None:
        raise HTTPException(401, "Invalid agent credentials")
    timestamp = utc(payload.timestamp)
    if timestamp > now() + timedelta(minutes=5) or timestamp < now() - timedelta(
        days=settings().retention_days
    ):
        raise HTTPException(422, "Sample timestamp outside accepted retention window")
    exists = db.scalar(
        select(Metric.id).where(
            Metric.host_id == host_id, Metric.sample_id == str(payload.sample_id)
        )
    )
    host.last_seen = now()
    if exists:
        db.commit()
        return {"accepted": True, "duplicate": True}
    data = payload.model_dump()
    data.update(sample_id=str(payload.sample_id), timestamp=timestamp)
    db.add(Metric(host_id=host_id, **data))
    for rule in db.scalars(select(Rule).where(Rule.host_id == host_id)):
        if rule.evaluated_at and timestamp <= utc(rule.evaluated_at):
            continue
        value = getattr(payload, rule.metric)
        active = value >= rule.threshold
        if active != rule.active:
            db.add(
                Alert(
                    host_id=host_id,
                    rule_id=rule.id,
                    metric=rule.metric,
                    value=value,
                    threshold=rule.threshold,
                    state="firing" if active else "recovered",
                    timestamp=timestamp,
                )
            )
        rule.active, rule.evaluated_at = active, timestamp
    db.commit()
    log.info(json.dumps({"event": "metric_ingested", "host_id": host_id}))
    return {"accepted": True, "duplicate": False}


@app.get("/api/v1/hosts/{host_id}/metrics", response_model=list[MetricOut], dependencies=[Admin])
def history(
    host_id: str,
    db: DB,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(1000, ge=1, le=5000),
):
    get_host(db, host_id)
    start, end = start or now() - timedelta(hours=1), end or now()
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise HTTPException(422, "Use timezone-aware start < end")
    try:
        start, end = utc(start), utc(end)
    except (OverflowError, ValueError) as exc:
        raise HTTPException(422, "Time range outside supported UTC range") from exc
    rows = list(
        db.scalars(
            select(Metric)
            .where(Metric.host_id == host_id, Metric.timestamp >= start, Metric.timestamp <= end)
            .order_by(Metric.timestamp.desc(), Metric.id.desc())
            .limit(limit)
        )
    )
    return [metric_out(m) for m in reversed(rows)]


@app.put("/api/v1/hosts/{host_id}/rules", response_model=RuleOut, dependencies=[Admin])
def put_rule(host_id: str, payload: RuleInput, db: DB):
    get_host(db, host_id, lock=True)
    rule = db.scalar(select(Rule).where(Rule.host_id == host_id, Rule.metric == payload.metric))
    if rule is None:
        rule = Rule(host_id=host_id, metric=payload.metric, threshold=payload.threshold)
        db.add(rule)
    else:
        rule.threshold = payload.threshold
    db.commit()
    return rule


@app.get("/api/v1/hosts/{host_id}/rules", response_model=list[RuleOut], dependencies=[Admin])
def rules(host_id: str, db: DB):
    get_host(db, host_id)
    return list(db.scalars(select(Rule).where(Rule.host_id == host_id)))


@app.get("/api/v1/alerts", response_model=list[AlertOut], dependencies=[Admin])
def alerts(db: DB, host_id: str | None = None, limit: int = Query(100, ge=1, le=1000)):
    query = select(Alert)
    if host_id:
        query = query.where(Alert.host_id == host_id)
    rows = list(db.scalars(query.order_by(Alert.timestamp.desc(), Alert.id.desc()).limit(limit)))
    return [
        AlertOut.model_validate(a).model_copy(update={"timestamp": utc(a.timestamp)}) for a in rows
    ]


@app.post("/api/v1/maintenance/retention", dependencies=[Admin])
def retention(db: DB):
    cutoff = now() - timedelta(days=settings().retention_days)
    metrics = db.execute(delete(Metric).where(Metric.timestamp < cutoff)).rowcount
    alerts = db.execute(delete(Alert).where(Alert.timestamp < cutoff)).rowcount
    db.commit()
    return {"deleted_metrics": metrics, "deleted_alerts": alerts}
