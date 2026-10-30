# Security

CloudPulse is a local portfolio application, not a hardened hosted multi-tenant service. Keep published ports on loopback. A shared random admin token protects dashboard data and management routes; it has no expiry, user roles, or session revocation. Rotate it by replacing the configured token and restarting the API/retention services.

Use the bootstrap script to generate unique credentials. It preserves existing `.env` values and adds the runtime DB password when missing; new files use Unix mode 0600. On Windows apply appropriate file ACLs. Agent keys are shown only at registration/rotation and stored as hashes. Do not log authorization headers, commit `.env`, or share the dashboard token. Use HTTPS with valid certificates for remote access; the agent enforces that requirement outside loopback. Nginx adds browser security headers.

The agent sends resource percentages and cumulative network counters; it does not collect processes, command lines, files, or packet contents. Collected host names and operational metrics may still be sensitive. Remove expired data with retention and maintain backups according to your needs. Dependencies and container base images need regular maintenance.

Report vulnerabilities privately to the repository owner using GitHub's private vulnerability reporting when enabled. Do not include real tokens or private machine information in public issues.

The API and retention worker use `cloudpulse_runtime`, which has DML/sequence access to the four application tables and no superuser, role/database creation, schema DDL, or migration-table access. A separate one-shot migrator holds the database-owner credential for Alembic and role grants. The test profile holds admin credentials only to prepare/drop isolated test schemas; never expose or run it as an application service. Protect operator access to Docker and `.env`.

The backend bounds request bodies at 16 KiB (including chunked requests), validates finite numeric metric types, normalizes UTC ranges, and emits `Cache-Control: no-store`. Invalid ingestion credentials cannot lock a host row. The dashboard clears transient data on sign-out and rejects delayed responses from an older browser session. Nginx limits request bodies and locally probes its listener without sending loopback requests to an outbound proxy.

These controls do not constitute production sign-off: user identity/session lifecycle, edge authentication throttling, TLS deployment, backups with restore drills, load testing, and container-image scanning remain unverified or unimplemented. See [the production review](docs/PRODUCTION_REVIEW.md).
