from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", allow_inf_nan=False)


class HostCreate(Schema):
    name: str = Field(min_length=1, max_length=100, pattern=r"\S")


class HostUpdate(Schema):
    enabled: bool


class Sample(Schema):
    sample_id: UUID
    timestamp: datetime
    cpu: float = Field(ge=0, le=100)
    memory: float = Field(ge=0, le=100)
    disk: float = Field(ge=0, le=100)
    network_sent_bytes: int = Field(ge=0, le=9223372036854775807)
    network_recv_bytes: int = Field(ge=0, le=9223372036854775807)

    @field_validator("timestamp")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("timestamp must include timezone")
        return value


class MetricOut(Sample):
    id: int
    host_id: str


class HostOut(Schema):
    id: str
    name: str
    enabled: bool
    last_seen: datetime | None
    online: bool
    latest: MetricOut | None


class Registration(Schema):
    host: HostOut
    api_key: str


class RuleInput(Schema):
    metric: Literal["cpu", "memory", "disk"]
    threshold: float = Field(gt=0, le=100)


class RuleOut(RuleInput):
    id: int
    host_id: str
    active: bool


class AlertOut(Schema):
    id: int
    host_id: str
    rule_id: int
    metric: str
    value: float
    threshold: float
    state: str
    timestamp: datetime
