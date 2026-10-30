# Production readiness review — 30 October 2026

## Decision

**Verified for local, single-user operation. Not approved for internet-facing production.** The application genuinely collects, stores and renders system metrics. Passing functional checks does not establish availability, safe internet exposure, disaster recovery or fleet capacity.

## Findings corrected

| Severity | Finding | Correction and evidence |
|---|---|---|
| High | API and retention connected as a PostgreSQL superuser | Separate one-shot owner/migrator and restricted `cloudpulse_runtime` credentials. Deployed runtime role checked for no superuser/create-role/create-database privileges; table creation and migration-bookkeeping access rejected. Real ingestion/alerts still pass. |
| Medium | Extreme timezone offsets caused 500s; offset history windows returned incorrect results in SQLite | Normalize samples/ranges to UTC, reject overflowing values with 422. Failing regressions reproduced before the fix. |
| Medium | Boolean/string telemetry silently became numeric measurements | Strict finite numeric fields and signed-64-bit counter bounds; adversarial validation tests. |
| Medium | API bodies could be buffered without an application limit | 16 KiB backend limit counts received bytes, including chunked bodies; matching Nginx limit and request-body timeout. Oversized requests return 413. |
| Medium | Management and one-time key responses lacked cache restrictions | API responses emit `Cache-Control: no-store`; authentication and key-rotation responses checked. |
| Medium | Invalid agent credentials could acquire a host lock | Match key hash/enabled state before `FOR UPDATE`. PostgreSQL test holds a real host lock and proves bad-key requests return without waiting. Disable, rotation and rule changes use the same serialization boundary. |
| Medium | In-flight registration could restore a key after sign-out/re-login | Session generations discard old results; sign-out clears transient state. Browser regression delays a real registration response across two sessions and verifies no key notice reappears. |
| Medium | Nginx could retain a replaced backend's address | Docker DNS re-resolution; replacement smoke verifies proxy recovery and persistence of a pre-existing metric. |
| Medium (development dependency) | Audit found CVE-2025-71176 in pytest 8.4.2 | Upgrade to pytest 9.0.3, update declaration/locks, rerun suites and audit. No known advisories reported for final pinned Python constraints. |
| Correctness | Host events were filtered from only the workspace's latest 100 | Request host-filtered alert history from the API. |
| Correctness | Chart samples were equally spaced regardless of elapsed time | Numeric time axis; actual agent samples render three series and card values matching independent SQL results. Lines still connect observations across gaps; missing samples are not synthesized. |
| Reliability | Slow polling could continually supersede its own results; host overview issued N+1 queries | Poll after completion; fetch host/latest observations in one SQL query, checked by a query-count regression. |
| Reliability | Agent accepted malformed URLs and noncanonical UUIDs, and retried permanent errors | Validate base URL/port/query/fragment, canonicalize UUIDs, fail fast on redirects/permanent HTTP errors, retain bounded transport/408/429 retries. |
| Operations | Frontend had no real readiness check; services had no restart policy | Local HTTP health check and long-lived service restart policies. Probe tested with the managed proxy; retention remains a log-monitored worker without a freshness probe. |

## Real-data evidence

`scripts/browser_smoke.py` registers a unique machine through the browser and runs the actual Python agent CLI three times with real psutil readings. It independently queries PostgreSQL inside the backend container, checks the database dialect, sample IDs and values, compares the REST response to those rows, and checks rendered CPU/memory/disk card values plus all three Recharts series. Two additional real agent readings exercise rendered disk firing/recovery events after threshold changes. It also exercises history range selection, rule editing, mobile layout, disabling, sign-out and failed authentication. Credentials are held in process memory and are never placed in screenshots or test output.

The separate Compose smoke verifies duplicate retries, real memory readings causing firing/recovery after threshold changes, and the agent's `--once` command. The PostgreSQL pytest profile prepares disposable schemas with an admin connection but executes API operations as the restricted runtime role; migration roundtrips use a separate admin-only schema. Production monitoring tables are not dropped by these tests.

See [verification commands and outcomes](VERIFICATION.md). Current review screenshots are under ignored `.local/review-screenshots`; committed screenshots illustrate observed readings, not seeded/demo data.

## Remaining production gates

1. **Identity and edge security:** the shared admin bearer token has no per-user identity, expiry, revocation, RBAC or MFA. Browser sign-out only forgets the token locally. No edge authentication throttling/rate limiting has been deployed. Keep loopback bindings; for wider access, deploy and test a trusted identity/TLS boundary and abuse limits.
2. **Recovery and availability:** PostgreSQL backups, restore drills, host/volume loss, alerting on monitoring failure and retention-worker freshness are not verified. Restart policies do not provide high availability or restart merely unhealthy containers. This is one API/DB deployment.
3. **Capacity:** host lists are unpaginated, history is capped to the latest 5,000 raw samples per query, and retention deletes in a single transaction. No fleet load test, query-plan benchmark, sustained storage-growth test, downsampling or outage spool exists. Failed delivery is logged and drops a sample after bounded retries.
4. **Deployment assurance:** Windows execution, remote HTTPS agent delivery, remote GitHub Actions, container/base-OS vulnerability scanning and fresh cloud-snapshot restoration have not been verified. Package audits are point-in-time checks, not a penetration test or an image audit.
5. **Credential operations:** protect Docker/operator access and `.env`. The migrator necessarily holds privileged database credentials. Runtime roles cannot run Alembic; use the migrator for schema operations and rotate secrets through the documented process. Agent keys are random and hashed but have no automatic expiry.

These are explicit deployment gates, not completed features. No remote deployment, merge or publication was performed during this review.
