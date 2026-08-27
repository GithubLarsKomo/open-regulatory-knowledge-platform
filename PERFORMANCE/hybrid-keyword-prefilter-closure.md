# Hybrid keyword prefilter closure

## Result

The measured `hybrid_keyword_1000` E2E workload improved from approximately **28.17 ms** median on merged `master` (`0779c2c`) to **6.08 ms** median on Python 3.12 while remaining at exactly **2 SQL statements**. That is an observational reduction of approximately **78.4%** on the equivalent SQLite CI workload.

The deterministic structural guard proves the intended work removal directly: in a 100-object workload with 10 possible keyword candidates, canonical JSON tokenization now runs **10 times instead of 100**.

## Implementation

- The existing newest-`scan_limit` window is materialized first in SQL so older matches cannot enter when newer non-matches are filtered out.
- ASCII query tokens are used only as a SQL superset prefilter over the serialized current-version payload.
- The query returns a minimal projection: UUID, current version, object type and payload.
- Exact canonical Python tokenization, coverage scoring, phrase bonus, sorting, tie-breaking and final limits remain unchanged.
- `ai_draft` objects remain excluded.
- Non-ASCII queries deliberately fall back to the previous full candidate path because JSON string serialization/escaping is backend-specific and a SQL substring predicate cannot be proven to be a lossless Unicode superset across supported databases.

## Verified behavior before final closure run

On Python 3.12 CI after the main prefilter implementation:

- pytest: **569 passed, 1 skipped**
- `hybrid_keyword_1000`: **2/2/2/2/2 SQL statements**, median **6.083 ms**
- `baseline_create_100`: unchanged **5 SQL**, median **6.432 ms**
- `per_render_docx`: unchanged **5 SQL**, median **2.492 ms**
- `graph_traceability_depth1_51`: unchanged **3 SQL**, median **4.610 ms**
- repository reads: unchanged **1 SQL**
- `create_object`: unchanged **3 SQL**
- `create_relation`: unchanged **2 SQL**

The final CI run additionally includes the Unicode fallback regression test.

## Simplification pass

The final design intentionally avoids:

- schema or index changes,
- full-text-search infrastructure,
- caching,
- background indexing,
- parallelism or async execution,
- duplicate scoring logic in SQL,
- changing hybrid ranking or API contracts.

The database performs only coarse candidate rejection; Python remains the single authoritative keyword-scoring implementation.

## Limitations

The timing evidence comes from the repository's SQLite GitHub Actions benchmark. It demonstrates reduced application work and a large same-harness improvement, but it is **not** a MariaDB/MySQL production-latency benchmark. The SQL query is written through SQLAlchemy for supported relational backends, while the Unicode fallback avoids relying on backend-specific JSON serialization behavior.

## Stop rule

This slice closes once Python 3.10 and 3.12 pass all functional, performance-harness, specification and generated-file gates on the final head. Further keyword-search work such as FTS, generated search columns or indexes requires a production-like database workload and separate evidence.