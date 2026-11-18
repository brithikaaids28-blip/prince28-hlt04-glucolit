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
