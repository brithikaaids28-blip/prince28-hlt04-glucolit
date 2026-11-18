\## Database Migrations



\### Migration 1: Create documents and pages

\- Revision: `1d1bad238490`

\- Created `documents` and `pages` tables.

\- Applied successfully to Neon PostgreSQL.



\### Migration 2: Add GIN index on metadata

\- Revision: `38174267d419`

\- Previous revision: `1d1bad238490`

\- Created `ix\_documents\_metadata\_gin` using `jsonb\_path\_ops`.



\### Migration Verification



\- `uv run alembic upgrade head` — Passed

\- `uv run alembic downgrade -1` — Passed

\- `uv run alembic current` — Returned `1d1bad238490` after downgrade

\- `uv run alembic upgrade head` — Passed again

\- `uv run alembic history` — Passed



\### Migration History



```text

1d1bad238490 -> 38174267d419 (head), add gin index on metadata

<base> -> 1d1bad238490, create documents and pages tables

```



The downgrade and upgrade test confirmed that the migration can be rolled back and reapplied successfully.



### Idempotent Loader Test Results

Tested using `uv run python scripts/load_db.py`.

**Test 1 – Existing records unchanged**
```text
records=2 inserted=0 updated=0 unchanged=2
```

**Test 2 – Modified one record**
```text
records=2 inserted=0 updated=1 unchanged=1
```

**Test 3 – Restored original record**
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
