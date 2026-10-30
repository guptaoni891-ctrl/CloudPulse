# CloudPulse implementation plan

1. Build a versioned FastAPI API, SQLAlchemy persistence, Alembic schema, and real psutil agent. Verify authenticated ingestion and host identity.
2. Build a responsive React dashboard with live host status, historical charts and authenticated admin access.
3. Add threshold rules, recovery history, bounded agent retry, retention and secure local bootstrap.
4. Package with Compose, tests, CI, architecture and Windows instructions. Run available checks and record any environment limitations.

Use PostgreSQL in deployment; SQLite is only a fast isolated test database. Never display generated metrics as actual observations. Bind published services to loopback by default.
