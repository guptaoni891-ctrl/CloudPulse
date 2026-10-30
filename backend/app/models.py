from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Host(Base):
    __tablename__ = "hosts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Metric(Base):
    __tablename__ = "metrics"
    __table_args__ = (
        UniqueConstraint("host_id", "sample_id"),
        Index("ix_metrics_host_time", "host_id", "timestamp"),
        Index("ix_metrics_timestamp", "timestamp"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id"))
    sample_id: Mapped[str] = mapped_column(String(36))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cpu: Mapped[float] = mapped_column(Float)
    memory: Mapped[float] = mapped_column(Float)
    disk: Mapped[float] = mapped_column(Float)
    network_sent_bytes: Mapped[int] = mapped_column(BigInteger)
    network_recv_bytes: Mapped[int] = mapped_column(BigInteger)


class Rule(Base):
    __tablename__ = "rules"
    __table_args__ = (UniqueConstraint("host_id", "metric"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id"))
    metric: Mapped[str] = mapped_column(String(16))
    threshold: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_timestamp", "timestamp"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    host_id: Mapped[str] = mapped_column(ForeignKey("hosts.id"), index=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("rules.id"))
    metric: Mapped[str] = mapped_column(String(16))
    value: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(16))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
