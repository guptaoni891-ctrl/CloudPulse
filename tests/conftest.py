import os

os.environ.setdefault("CLOUDPULSE_ADMIN_TOKEN", "test-admin-token-" + "x" * 32)
os.environ.setdefault("CLOUDPULSE_DATABASE_URL", "sqlite://")

import pytest
from app.db import Base, session
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[session] = override
    with TestClient(app) as test:
        yield test
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def admin():
    return {"Authorization": "Bearer " + os.environ["CLOUDPULSE_ADMIN_TOKEN"]}


@pytest.fixture
def registered(client, admin):
    response = client.post("/api/v1/hosts", headers=admin, json={"name": "test-machine"})
    assert response.status_code == 201
    return response.json()
