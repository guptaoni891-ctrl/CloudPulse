import os
from uuid import uuid4

os.environ.setdefault("CLOUDPULSE_ADMIN_TOKEN", "test-admin-token-" + "x" * 32)
os.environ.setdefault("CLOUDPULSE_DATABASE_URL", "sqlite://")

import pytest
from app.db import Base, session
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateSchema, DropSchema


@pytest.fixture
def client():
    postgres_url = os.getenv("CLOUDPULSE_TEST_DATABASE_URL")
    schema = "cloudpulse_test_" + uuid4().hex
    if postgres_url:
        root_engine = create_engine(postgres_url, pool_pre_ping=True)
        with root_engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        engine = root_engine.execution_options(schema_translate_map={None: schema})
    else:
        root_engine = engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    Base.metadata.create_all(engine)
    runtime_engine = None
    runtime_url = os.getenv("CLOUDPULSE_TEST_RUNTIME_DATABASE_URL")
    if postgres_url and runtime_url:
        with root_engine.begin() as connection:
            # Schema names are generated UUIDs, never user input.
            for grant in (
                f"GRANT USAGE ON SCHEMA {schema} TO cloudpulse_runtime",
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO cloudpulse_runtime",
                f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO cloudpulse_runtime",
            ):
                connection.execute(text(grant))
        runtime_engine = create_engine(runtime_url, pool_pre_ping=True)
        engine = runtime_engine.execution_options(schema_translate_map={None: schema})
    factory = sessionmaker(engine, expire_on_commit=False)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[session] = override
    app.state.test_session_factory = factory
    app.state.test_engine = engine
    try:
        with TestClient(app) as test:
            yield test
    finally:
        app.dependency_overrides.clear()
        if postgres_url:
            with root_engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        if runtime_engine is not None:
            runtime_engine.dispose()
        root_engine.dispose()


@pytest.fixture
def admin():
    return {"Authorization": "Bearer " + os.environ["CLOUDPULSE_ADMIN_TOKEN"]}


@pytest.fixture
def registered(client, admin):
    response = client.post("/api/v1/hosts", headers=admin, json={"name": "test-machine"})
    assert response.status_code == 201
    return response.json()
