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

**Rollback Test**
- Status: SUCCESS
- Previous working commit: `25815651c150f28d4f87eb32186b4a433620d001`
- Production health check: HTTP 200
- Verified production version: `25815651c150f28d4f87eb32186b4a433620d001`

**Roll-forward Test**
- Status: SUCCESS
- Latest commit: `e4f3c027f0eeb7a37b30edfde66f87bed38e0df6`
- Production health check: HTTP 200
- Verified production version: `e4f3c027f0eeb7a37b30edfde66f87bed38e0df6`

**Final Result**
- Rollback deployment: Passed
- Roll-forward deployment: Passed
- Production health verification: Passed
- Both deployment versions verified successfully.

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

## D06 · Collecting the corpus

- Start target: 500 full-text papers
- Collected today: 18 files, 200 estimated pages, 1.88 MiB (from DATASET.md)
- Doors used: URL list, Git repository, PMC Open Access services

### Licence check

| Source | Licence or terms, in my words | May I show full text in answers? |
|---|---|---|
| PMC articles | CC BY 4.0: reuse allowed with attribution and licence notice | Yes, with attribution and licence conditions |
| PMC articles | CC BY-NC: reuse restricted to non-commercial purposes | Only if the use is non-commercial and conditions are met |
| PMC articles | CC BY-NC-SA: non-commercial reuse with share-alike conditions | Only if the use is non-commercial and conditions are met |
| PMC articles | CC BY-NC-ND: non-commercial use; no derivatives | Do not reproduce or adapt full text; these were skipped |

### robots.txt

- Site: PMC (https://pmc.ncbi.nlm.nih.gov/). The downloader checks robots.txt before requesting articles.
- Was anything blocked for my bot? Two NoDerivatives licence entries were skipped by the downloader. These were licence restrictions, not confirmed robots.txt blocks.

### Kill and resume

- Run 1: Ctrl+C test: not recorded; verify whether this test was performed.
- Run 2: downloaded=10, skipped=2 (from the collection run).
- Run 3: not yet verified; run the downloader again to confirm resume behaviour.

### Capacity (from docs/CAPACITY.md)

- Tokens per page, estimated: 619.
- Full corpus: 34.38 M tokens, 68,757 chunks, embedding about Rs 653.19, vectors 268.58 MiB.
- The number that surprised me most, and why: The estimated embedding cost is relatively low for 5,000 papers. Vector storage is also manageable, but actual database storage must be checked.

### One thing that went wrong today, and how I fixed it

- The downloader skipped two NoDerivatives articles. I kept them out of the downloaded corpus according to the licence policy and continued with eligible papers.

## D07 · Parsing the corpus

### Corpus parsing results

- Downloaded XML articles available: 60
- Articles successfully parsed: 60
- Articles failed: 0
- Total extracted pages: 889
- Parsing format: JATS XML
- Parser used: GlucoLit JATS parser
- Database: PostgreSQL (Neon)
- Document external ID format: `parsed:PMC...`

### Database verification

| Check | Result |
|---|---:|
| Parsed documents | 60 |
| Parsed pages | 889 |
| Parsing failures | 0 |

### Testing

- Unit tests: 60 passed
- Integration tests: 10 passed
- Ruff lint: Passed
- Ruff formatting: Passed

### What went well

- Successfully parsed all 60 downloaded research articles.
- Extracted article titles, abstracts, sections and page text.
- Stored parsed documents and pages in PostgreSQL.
- Verified database counts.
- No parsing failures were recorded.

### Known limitations

- Current corpus contains XML articles; PDF and HTML parser comparisons were not performed.
- Page divisions for XML articles are generated from extracted text rather than original PDF page boundaries.
- Nested JATS structures may need additional parser improvements.

### One thing learned

I learned how to parse research articles, extract structured text, store pages in PostgreSQL and verify the complete corpus.
### Parser comparison: JATS vs Trafilatura

- Articles compared: 10 largest XML files.
- Selection method: XML file size used as a proxy for parsing difficulty.
- JATS average extraction: 16,199 words per article.
- Trafilatura average extraction: 19,694 words per article.
- JATS average processing time: 0.084 seconds.
- Trafilatura average processing time: 0.645 seconds.
- JATS detected headings in all 10 articles.
- Trafilatura heading count: 0.

### Comparison conclusion

The JATS parser was approximately 7.7 times faster than Trafilatura
and preserved structured headings and page divisions. Trafilatura
extracted more words in 8 out of 10 articles, but higher word counts
do not necessarily indicate better extraction quality.

The JATS parser was retained as the primary parser because the corpus
uses JATS XML and structured document extraction is required.

The 10 largest files were used as a reproducible proxy for difficult
articles; they were not independently verified as the 10 hardest.
### Prompt comparison

Test set: 20 questions across docs, personal, and off_topic.

| Prompt version | Accuracy | Input tokens | Output tokens |
|---|---:|---:|---:|
| classify_v1 | 55.0% (11/20) | 2,299 | 2,281 |
| classify_v2 | 100.0% (20/20) | 5,399 | 1,599 |
| classify_v3 | 100.0% (20/20) | 7,539 | 1,314 |
| classify_v4 | 100.0% (20/20) | 6,559 | 1,349 |

**Best router prompt:** classify_v2.md. It achieved 100% accuracy with the lowest input-token count among the prompts scoring 100%.

**V4 change:** Added an explicit distinction between general diabetes research questions (docs) and personalized medical advice based on an individual's history, test results, or current condition (personal).

**Remaining misclassifications:** None for v2, v3, or v4. V1 had 9 misclassifications.

**Changed label:** No changes required for v2, v3, or v4.

**Input-token comparison:** v1 used 2,299 input tokens; the best prompt, v2, used 5,399 input tokens.

**Leak check:** No LEAK lines were reported.

**Cache:** v1–v3 reused 20 cached answers each; v4 generated 20 new answers.

**Cost:** The script displayed 0.0000 INR for all versions. This value is unverified because the configured model may not match the gateway pricing table.

## D08 · LLM Gateway and API Deployment

### LLM Gateway

- Implemented a centralized LLM gateway for GlucoLit.
- Configured Gemini as the primary provider and Groq as the fallback provider.
- Added retry handling, backoff and circuit-breaker behavior.
- Implemented streaming and non-streaming chat responses.
- Added fallback handling when the primary provider is unavailable.
- Added LLM usage recording, including provider, model, token counts and estimated cost.

### API endpoints

- `/health` – API health check.
- `/ready` – Database readiness check.
- `/v1/chat` – Chat endpoint with optional streaming.
- `/v1/usage` – Daily LLM usage and estimated cost.
- `/v1/documents` – Document search and metadata filtering.

### Deployment and verification

- Deployed the FastAPI application on Render.
- Connected the application to Neon PostgreSQL.
- Verified database readiness.
- Verified the live API on 27 November 2026.

| Endpoint | Live result |
|---|---|
| `/v1/chat` | HTTP 200 OK |
| `/v1/usage` | HTTP 200 OK |
| `/v1/documents?doc_kind=guideline&limit=3` | HTTP 200 OK |

- Chat response successfully generated using Groq fallback.
- Live usage statistics were returned successfully.
- Document endpoint returned a guideline with extracted metadata.

### One thing learned

I learned how to build an LLM gateway with provider fallback, expose chat and usage APIs using FastAPI, record LLM usage and deploy the application on Render.

## D09 · Versioned Prompts and Metadata Extraction

### Metadata extraction implementation

- Created DocMeta using Pydantic validation with extra fields forbidden.
- Five common fields: `doc_kind`, `year`, `language`, `summary`, `topics`.
- Five project-specific fields: `pmcid`, `journal`, `study_type`, `population`, `sample_size`.
- Extra fields are forbidden.
- Created versioned extraction prompts: `extract_v1.md` and `extract_v2.md`.
- Active extraction prompt: `extract_v2`.
- Implemented JSON parsing, validation error reporting and retry handling.
- Extraction uses the first two article pages, with a maximum of 4,000 characters.
- Extracted metadata is merged into existing document metadata, preserving parser information.

### Extraction results

| Metric | Result |
|---|---:|
| Parsed documents in Neon | 491 |
| Successfully extracted | 103 |
| Remaining without successful extraction | 388 |
| Latest batch processed | 50 |
| Latest batch successful | 48 |
| Latest batch failed | 2 |
| Previously completed records skipped | 55 |

- Extraction coverage: approximately 21%.
- The minimum 50-document extraction requirement was exceeded.
- Metadata was stored in Neon PostgreSQL.
- Prompt version recorded: `extract_v2`.

### Provider issues

- Gemini returned HTTP 403 because billing was not enabled for the project.
- Groq successfully handled most requests.
- Groq occasionally returned HTTP 429 due to rate limits.
- The latest batch encountered the Groq daily token limit.
- One document returned invalid JSON after two extraction attempts.
- Two documents failed in the latest batch and can be retried when provider capacity is available.

### Cost limitation

- The script displayed ₹0.0 for extraction calls.
- This is not confirmed as the actual API cost because the fallback model may not have a configured pricing entry.
- Actual API cost needs separate verification.

### Testing

- Unit extraction tests passed.
- Integration test verified that parser metadata is preserved and extracted metadata is stored.
- Ruff lint checks passed.
- Ruff formatting passed.

### One thing learned

I learned how to use versioned prompts, validate LLM-generated JSON using Pydantic, retry invalid responses, handle provider rate limits and store structured metadata in PostgreSQL.
## Day 10 — Background Ingestion Queue

### Completed
- Added ARQ and Redis for background ingestion jobs.
- Added `IngestJob` and `IngestItem` database models.
- Created and applied Alembic migration `77f4ec15cf13`.
- Added Redis queue helpers in `src/glucolit/ingest/queue.py`.
- Implemented the background worker in `src/glucolit/ingest/worker.py`.
- Added admin-token-protected ingestion API endpoints:
  - `POST /v1/ingest`
  - `GET /v1/ingest/{job_id}`
- Registered the ingestion router in the FastAPI application.
- Added unit tests for ingestion API and worker behavior.

### Verification
- Redis connection: Passed (`PONG`).
- Database connection: Passed.
- API health and readiness checks: Passed.
- ARQ worker startup: Passed.
- Queue submission and worker execution: Passed.
- Admin-token configuration: Verified.
- Ingestion status endpoint authentication and not-found handling: Passed.
- Full test suite: 128 passed.
- Ruff lint and formatting checks: Passed (90 files formatted).

### Notes
- Redis runs locally through Docker Compose.
- FastAPI and ARQ worker run as separate processes.
- A dummy queue job was used for integration testing; no real article ingestion was triggered during that test.
