## Database Migrations

### Migration 1: Create documents and pages

- Revision: `1d1bad238490`
- Created `documents` and `pages` tables.
- Applied successfully to Neon PostgreSQL.

### Migration 2: Add GIN index on metadata

- Revision: `38174267d419`
- Previous revision: `1d1bad238490`
- Created `ix_documents_metadata_gin` using `jsonb_path_ops`.

### Migration Verification

- `uv run alembic upgrade head` — Passed
- `uv run alembic downgrade -1` — Passed
- `uv run alembic current` — Returned `1d1bad238490` after downgrade
- `uv run alembic upgrade head` — Passed again
- `uv run alembic history` — Passed

### Migration History

```text
1d1bad238490 -> 38174267d419 (head), add gin index on metadata
<base> -> 1d1bad238490, create documents and pages tables
```

The downgrade and upgrade test confirmed that the migration can be rolled back and reapplied successfully.

## Idempotent Loader Test Results

Tested using `uv run python scripts/load_db.py`.

**Test 1 — Existing records unchanged**

```text
records=2 inserted=0 updated=0 unchanged=2
```

**Test 2 — Modified one record**

```text
records=2 inserted=0 updated=1 unchanged=1
```

**Test 3 — Restored original record**

```text
records=2 inserted=0 updated=1 unchanged=1
```

**Final verification**

```text
records=2 inserted=0 updated=0 unchanged=2
```

Result: SHA-256 fingerprint-based loading successfully detects changes, updates modified records, and skips unchanged records.

## GIN Index EXPLAIN Test

### Query: pmcid=PMC11937334

```text
-- 1) What the planner chooses on its own:
Seq Scan on documents  (cost=0.00..11.00 rows=1 width=36) (actual time=0.709..0.710 rows=1.00 loops=1)
  Filter: (metadata @> '{"pmcid": "PMC11937334"}'::jsonb)
  Rows Removed by Filter: 1
  Buffers: shared read=1 dirtied=1
Planning:
  Buffers: shared hit=143 read=8 dirtied=1
Planning Time: 6.124 ms
Execution Time: 0.738 ms

-- 2) Seq scan switched off:
Bitmap Heap Scan on documents  (cost=12.81..16.82 rows=1 width=36) (actual time=1.763..1.765 rows=1.00 loops=1)
  Recheck Cond: (metadata @> '{"pmcid": "PMC11937334"}'::jsonb)
  Heap Blocks: exact=1
  Buffers: shared hit=2 read=2
  ->  Bitmap Index Scan on ix_documents_metadata_gin  (cost=0.00..12.81 rows=1 width=0) (actual time=1.728..1.728 rows=1.00 loops=1)
        Index Cond: (metadata @> '{"pmcid": "PMC11937334"}'::jsonb)
        Index Searches: 1
        Buffers: shared hit=1 read=2
Planning:
  Buffers: shared hit=1
Planning Time: 0.080 ms
Execution Time: 1.820 ms
```

## Day 04 - Docker Build Results

- First Docker build: 114.4 seconds
- Cached rebuild: 41.3 seconds
- Docker image: `glucolit:dev`
- Image disk usage: 300 MB
- Container user: `app` (UID 999)
- Dependency installation steps successfully cached.
- Cache test: modified health endpoint docstring and restored it.

## Day 05 - Docker Compose Stack Results

- Docker Compose stack started successfully.
- PostgreSQL: Healthy.
- Redis: Healthy.
- Migration container: Exited (0).
- API container: Healthy.
- Initial migration: 2 records inserted, 0 updated, 0 unchanged.
- API documentation: `/docs` loaded successfully.
- GET `/v1/documents`: Returned 2 documents.
- Database stopped: `/health` returned `ok`.
- Database stopped: `/ready` returned `not ready`.
- Database restarted: `/ready` returned `ready`.
- Second migration: 2 records, 0 inserted, 0 updated, 2 unchanged.
- PostgreSQL data persisted after `docker compose down` and restart.

## D04 - Docker, Compose and Tests

### Clean Clone Verification

Created a fresh clone using:

```cmd
git clone . ..\prince28-hlt04-glucolit-check
```

Successfully ran `docker compose up --build -d` without relying on the original local `.env` or `.venv`.

- API: healthy
- PostgreSQL: healthy
- Redis: healthy
- Migrations: exited with code 0
- Fresh database: 2 records inserted, 0 updated, 0 unchanged

### Clean Clone Container Status

```text
NAME                 IMAGE                    SERVICE   STATUS
glucolit-api-1       glucolit-api             api       Up (healthy)
glucolit-db-1        pgvector/pgvector:pg17   db        Up (healthy)
glucolit-migrate-1   glucolit-migrate         migrate   Exited (0)
glucolit-redis-1     redis:7-alpine           redis     Up (healthy)
```

### Clean Clone Migration Logs

```text
Running upgrade -> 1d1bad238490, create documents and pages tables
Running upgrade 1d1bad238490 -> 38174267d419, add gin index on metadata
records=2 inserted=2 updated=0 unchanged=0
```

### Image and Docker Security Evidence

```text
Image: glucolit:dev
Disk usage: 300 MB
Target: under 400 MB

uid=999(app) gid=999(app) groups=999(app)
```

### Tests and Coverage

```text
Unit tests:
16 passed

Integration tests:
7 passed

Unit-only coverage:
TOTAL 80%

Combined coverage:
TOTAL 93%

Combined tests:
23 passed in 15.69s
```

### Uncovered Code

- `src/glucolit/api/middleware.py:23-28` — middleware edge cases.
- `src/glucolit/logging_setup.py:11-21` — logging configuration paths.

These are not test failures. They are areas where additional tests could improve coverage.

### Readiness and Liveness

```text
Database stopped:
  /health -> ok
  /ready  -> not ready

Database started:
  /ready  -> ready
```

A load balancer should stop sending traffic to an instance that is not ready because it cannot safely serve database-dependent requests. It should not restart the application because restarting the app will not fix an unavailable database.

### Build Evidence

- First build: 114.4 seconds.
- Cached rebuild: 41.3 seconds.
- Docker image disk usage: 300 MB.
- Container runs as non-root user `app` (UID 999).

Docker build cache reuses unchanged layers, avoiding unnecessary dependency installation and reducing rebuild time.

## Day 05 - CI/CD and Production Deployment

### GitHub Actions

- CI workflow: `.github/workflows/ci.yml`
- CI runs linting, tests, and Docker image build.
- Docker image is published to GitHub Container Registry (GHCR).
- CD workflow runs after CI succeeds.
- Production migrations and deployment smoke tests are included in CD.

### Production Deployment

- Hosting platform: Render
- Service: `glucolit-api`
- Live API: https://glucolit-main.onrender.com
- Health endpoint: https://glucolit-main.onrender.com/health
- Readiness endpoint: https://glucolit-main.onrender.com/ready
- Database: Neon PostgreSQL

### Production Health Verification

Latest verified health response:

```json
{
  "status": "ok",
  "app": "glucolit",
  "env": "production",
  "version": "cb723a3"
}
```

- Health endpoint: HTTP 200.
- Readiness endpoint: database readiness checked.
- UptimeRobot monitor: UP.
- Monitor interval: 5 minutes.

### Automated Quality Checks

```text
Ruff check: Passed
Ruff format check: Passed
Pytest: 17 passed, 7 skipped
```

### Deployment Rollback Verification

- Rollback test: Pending verification.
- Roll-forward test: Pending verification.
- Record the deployment versions and test results here after completing both tests.
## D03 · PostgreSQL

### Migration log
- Migration revisions: `1d1bad238490` and `38174267d419`
- Tested migration downgrade, upgrade, current revision and history.
- Confirmed migrations run successfully.

### Database loader
- First run: 2 unchanged records.
- Modified record test: 1 updated, 1 unchanged.
- Restored record test: 1 unchanged.
- Confirmed the loader is idempotent.

### EXPLAIN
Command:
`uv run python scripts/explain.py pmcid PMC11937334`

- Initial query: Seq Scan.
- After indexing: Bitmap Index Scan on `ix_documents_metadata_gin`.
- The index improved the query plan.
## D05 · CI/CD and Deployment

### Deployment
- CI workflow validates code changes.
- CD workflow deploys the application.
- Live health endpoint: https://glucolit-main.onrender.com/health
- Smoke test: `uv run python scripts/smoke.py`
- Result: Passed; production health endpoint returned HTTP 200.

### Rollback drill
- Previous deployment version: Record the previous working commit/version.
- Rollback procedure: Redeploy the previous working commit through Render.
- Verify rollback using the `/health` endpoint.

### Lead time
- Lead time: Record the time between pushing a code change and successful production deployment.
- Deployment verification: Smoke test passed.
