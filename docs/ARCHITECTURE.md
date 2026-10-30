# API and design

## Contract

All routes have `/api/v1` prefix. OpenAPI generated from explicit input/output schemas is served by FastAPI at `/openapi.json`.

| Method / route | Authentication | Behavior |
|---|---|---|
| GET `/health` | Public | SELECT 1, version and status |
| POST `/hosts` | Admin bearer | Name -> stable host UUID and one-time API key |
| GET `/hosts`, `/hosts/{id}` | Admin bearer | Status, last seen, latest actual observation |
| PATCH `/hosts/{id}` | Admin bearer | `{ "enabled": false }` revokes ingestion until re-enabled |
| POST `/hosts/{id}/rotate-key` | Admin bearer | Replaces hash, returns one-time new key |
| POST `/hosts/{id}/metrics` | `X-API-Key` | Validated sample, 202; repeats are idempotent |
| GET `/hosts/{id}/metrics` | Admin bearer | `start`, `end` ISO 8601 range, `limit` 1–5000 |
| PUT `/hosts/{id}/rules` | Admin bearer | Upsert CPU/memory/disk threshold per host |
| GET `/hosts/{id}/rules` | Admin bearer | Rule and current threshold state |
| GET `/alerts` | Admin bearer | Latest transitions, optional `host_id`, bounded `limit` |
| POST `/maintenance/retention` | Admin bearer | Delete expired metric and event records |

Sample fields: UUID `sample_id`, aware `timestamp`, percentage `cpu`, `memory`, `disk`, signed-64-bit nonnegative cumulative `network_sent_bytes` and `network_recv_bytes`. Percentages must be finite and 0–100. Unknown fields are rejected. Admin creates host identity, so agent payloads cannot impersonate another host.

## Persistence and consistency

Hosts store hashes of random 256-bit API keys, never plaintext. SHA-256 is suitable for uniformly random keys; these are not human passwords. Ingestion matches host ID, enabled state and key hash before acquiring a row lock, checks UUID uniqueness, inserts one sample and updates alert state within one transaction. `(host_id, sample_id)` uniqueness protects retries; `(host_id, timestamp)` index supports history reads. PostgreSQL serializes same-host ingestion with `FOR UPDATE`. Keep a single active agent per host identity. Rules use the same lock when updated. Latest observations sort by sample time, while last-seen is server receipt time.

Threshold state tracks the newest evaluated sample timestamp. Older arrivals persist for historical analysis but do not cause false state transitions. Only state changes add alert events. Events preserve the threshold and value at the time of transition. No hysteresis/debounce is implemented; noisy metrics may flap around a threshold.

Hourly retention is a separate lightweight process sharing the backend image. It removes expired metrics and events; failures are logged and retried next hour. There is no externally managed queue or distributed scheduler. Migrations are explicit Alembic revisions; the application does not silently create tables at startup.

## Deliberate limits

Single-user admin token, one disk volume per agent, raw bounded history (no aggregation/pagination), no offline disk spool or notifications, no automatic agent upgrade. UI polling resumes 10 seconds after each completed refresh; live processes are not required to survive cloud snapshots. Host overviews fetch latest observations in a single SQL query. Large fleets still require downsampling, pagination and capacity measurements before expanding deployment. PostgreSQL backups and TLS termination are operator responsibilities.

## Privilege and failure boundaries

Compose separates schema changes into the one-shot `migrate` service. It upgrades Alembic and provisions `cloudpulse_runtime` with DML on application tables plus sequence access. The backend and retention worker do not receive the owner password or migration rights. Migration failure prevents API startup. Existing database volumes are preserved during upgrades. Retention uses an alert-timestamp index as well as the metric-timestamp index.

The API caps even chunked requests at 16 KiB and marks responses no-store. Strict telemetry types reject strings and booleans masquerading as numeric observations. UTC normalization rejects overflowing dates with 422. Host locking serializes ingestion, rule changes, disabling and key rotation, without locking on invalid agent credentials. PostgreSQL-specific tests exercise first-delivery concurrency, unauthorized-request locking behavior and migration roundtrips in disposable schemas.

Nginx resolves the backend through Docker DNS, so replacing the API container does not permanently strand its proxy. Long-lived services have restart policies; Docker does not automatically restart a merely unhealthy process. Frontend readiness now makes a real local HTTP request. The retention worker has logs and a restart policy but no dedicated freshness/heartbeat probe.

Host pages query their own latest alert events, rather than filtering the workspace's latest 100. Historical charts use numeric timestamps so elapsed time is represented correctly. Gaps are still connected between observed points; no missing samples are synthesized. Old responses cannot repopulate a signed-out browser session. Registration keys remain one-time responses and are never written to browser storage.
