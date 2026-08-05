# Project Brief: Fintech Transaction Risk & Fraud Analytics Warehouse

> **How to use this doc:** Paste this whole file into Antigravity (or Cursor/Claude Code/any agentic dev tool) as the task spec. It's written so an agent can execute it phase by phase without needing extra clarification. Each phase has a clear deliverable and acceptance criteria so you (or the agent) know when it's done.

---

## 1. Project Summary

Build a realistic, industry-grade data warehouse simulating a fintech company's transaction system, including:
- A star schema with Slowly Changing Dimensions (SCD Type 2)
- Partitioned fact tables at multi-million-row scale
- Synthetic but realistic data generation (with injected fraud patterns)
- SQL-based fraud detection logic (no ML required)
- An incremental ETL/load simulation with watermarking
- Materialized views for BI performance
- Documented query optimization with before/after benchmarks
- A lightweight Python/Streamlit dashboard on top, to make results demoable

**End goal:** A GitHub repo + short write-up that can be shown in interviews and linked from a resume, demonstrating senior analytics-engineer-level SQL and data pipeline skills.

**Target stack:** PostgreSQL 15+, Python 3.11+, Docker Compose (for reproducibility), Streamlit (for the demo dashboard), dbt (optional stretch goal, see Phase 7).

---

## 2. Repository Structure (target)

```
fraud-warehouse/
├── docker-compose.yml
├── README.md
├── .env.example
├── sql/
│   ├── 01_schema.sql
│   ├── 02_partitions.sql
│   ├── 03_indexes.sql
│   ├── 04_scd_merge.sql
│   ├── 05_fraud_queries.sql
│   ├── 06_materialized_views.sql
│   └── 07_benchmarks.sql
├── etl/
│   ├── generate_synthetic_data.py
│   ├── load_initial.py
│   ├── incremental_load.py
│   └── watermark.py
├── dashboard/
│   └── app.py
├── notebooks/
│   └── exploration.ipynb
├── docs/
│   ├── architecture.md
│   ├── benchmarks.md
│   └── erd.png
└── tests/
    └── test_data_quality.py
```

---

## 3. Phase 1 — Environment & Schema Setup

**Goal:** Reproducible Postgres environment with the full star schema.

### Tasks
1. Create `docker-compose.yml` running Postgres 15 with a persisted volume, exposing port 5432.
2. Create `.env.example` with `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`.
3. Write `sql/01_schema.sql` implementing:

```sql
CREATE TABLE dim_customer (
    customer_sk SERIAL PRIMARY KEY,
    customer_id INT NOT NULL,
    risk_tier VARCHAR(20),
    account_status VARCHAR(20),
    country VARCHAR(50),
    valid_from DATE,
    valid_to DATE,
    is_current BOOLEAN DEFAULT TRUE
);

CREATE TABLE dim_merchant (
    merchant_sk SERIAL PRIMARY KEY,
    merchant_id INT NOT NULL,
    merchant_category VARCHAR(50),
    merchant_risk_score NUMERIC(5,2),
    valid_from DATE,
    valid_to DATE,
    is_current BOOLEAN DEFAULT TRUE
);

CREATE TABLE fact_transactions (
    transaction_id BIGSERIAL,
    customer_sk INT REFERENCES dim_customer(customer_sk),
    merchant_sk INT REFERENCES dim_merchant(merchant_sk),
    transaction_ts TIMESTAMP NOT NULL,
    amount NUMERIC(12,2),
    currency VARCHAR(3),
    channel VARCHAR(20),
    is_flagged BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (transaction_id, transaction_ts)
) PARTITION BY RANGE (transaction_ts);

CREATE TABLE staging_customer (
    customer_id INT,
    risk_tier VARCHAR(20),
    account_status VARCHAR(20),
    country VARCHAR(50),
    updated_at TIMESTAMP
);

CREATE TABLE etl_watermark (
    table_name VARCHAR(50) PRIMARY KEY,
    last_loaded_ts TIMESTAMP
);
```

### Acceptance Criteria
- `docker compose up -d` starts Postgres cleanly.
- `psql` connection succeeds and all tables above exist with correct FK constraints.
- Note: `transaction_id` must be part of the primary key alongside `transaction_ts` — this is a Postgres requirement for partitioned tables (partition key must be part of any unique constraint).

---

## 4. Phase 2 — Partitioning

**Goal:** Fact table partitioned by quarter, covering 2 years of synthetic history.

### Tasks
1. Write `sql/02_partitions.sql` creating 8 quarterly partitions covering the synthetic data's date range (e.g., 2024-01-01 through 2025-12-31).
2. Add a default/catch-all partition for any out-of-range dates to avoid load failures:

```sql
CREATE TABLE fact_transactions_default PARTITION OF fact_transactions DEFAULT;
```

3. Write a short script or SQL block that auto-generates future quarterly partitions (agent should implement as a `plpgsql` function `create_quarterly_partition(start_date DATE)`).

### Acceptance Criteria
- `\d+ fact_transactions` in psql shows all partitions.
- Inserting a row with a date outside declared ranges lands in the default partition without error.

---

## 5. Phase 3 — Synthetic Data Generation

**Goal:** Realistic, large-scale, fraud-pattern-injected dataset.

### Tasks
Write `etl/generate_synthetic_data.py` using `faker`, `numpy`, and `pandas`:

1. **Customers (~50,000 rows):**
   - `customer_id`, `signup_date`, `country` (weighted distribution, e.g. 60% US, 15% UK, etc.), `risk_tier` (mostly 'low', some 'medium', few 'high').
   - Generate 2-3 historical versions per ~10% of customers to simulate SCD changes (e.g., risk_tier upgraded after a flagged event) — write these to `staging_customer` with `updated_at` timestamps spread across the load period.

2. **Merchants (~2,000 rows):**
   - `merchant_id`, `merchant_category` (categorical: retail, travel, gambling, electronics, crypto, etc.), `merchant_risk_score` (some categories like 'crypto'/'gambling' skewed higher).

3. **Transactions (~3-5 million rows):**
   - Realistic time-of-day/day-of-week distribution (e.g., more transactions during daytime, fewer at 3am).
   - Amount distributions realistic per merchant category (lognormal distribution works well).
   - **Inject explicit fraud patterns** at a known rate (e.g., 0.5-1% of transactions) so your detection queries have something real to find:
     - **Velocity fraud:** pick ~200 customers, generate 5-10 transactions within a 10-minute window.
     - **Geo-impossibility fraud:** pick ~150 customers, generate two transactions in different "countries" (simulate via customer's dimension snapshot) within 1-2 hours of each other.
     - **Amount-spike fraud:** pick ~100 customers with historically low average transaction amounts, inject one transaction 10-20x their average.
   - Store ground truth in a separate column/table (`is_actual_fraud`) so you can later calculate precision/recall of your SQL detection rules against known fraud — this is a huge credibility booster for the project.

### Acceptance Criteria
- Script runs end-to-end and outputs CSVs (or directly loads via `psycopg2`/`COPY`) in under ~10 minutes for 5M rows.
- A data quality check (in `tests/test_data_quality.py`) confirms: no orphaned foreign keys, no negative amounts, injected fraud counts match expected rates within tolerance.

---

## 6. Phase 4 — Initial Load & SCD Type 2 Logic

**Goal:** Load dimension and fact data with correct SCD Type 2 handling.

### Tasks
1. `etl/load_initial.py`: bulk load customers/merchants into dimension tables (all as `is_current = TRUE`, `valid_from` = signup/creation date, `valid_to = NULL`).
2. `sql/04_scd_merge.sql`: implement the merge pattern below and have the agent write a Python wrapper (`etl/incremental_load.py`) that runs it against `staging_customer`:

```sql
-- Step 1: close out changed records
UPDATE dim_customer d
SET valid_to = s.updated_at::date - INTERVAL '1 day',
    is_current = FALSE
FROM staging_customer s
WHERE d.customer_id = s.customer_id
  AND d.is_current = TRUE
  AND (d.risk_tier IS DISTINCT FROM s.risk_tier
       OR d.account_status IS DISTINCT FROM s.account_status);

-- Step 2: insert new versions
INSERT INTO dim_customer (customer_id, risk_tier, account_status, country, valid_from, valid_to, is_current)
SELECT s.customer_id, s.risk_tier, s.account_status, s.country, s.updated_at::date, NULL, TRUE
FROM staging_customer s
WHERE EXISTS (
    SELECT 1 FROM dim_customer d
    WHERE d.customer_id = s.customer_id AND d.is_current = FALSE
      AND d.valid_to = s.updated_at::date - INTERVAL '1 day'
);
```

3. Bulk load `fact_transactions` using `COPY` (much faster than row-by-row inserts for millions of rows) — agent should benchmark `COPY` vs `INSERT` and note the difference in `docs/benchmarks.md`.

### Acceptance Criteria
- Querying `dim_customer WHERE customer_id = X ORDER BY valid_from` shows multiple historical rows with non-overlapping valid_from/valid_to ranges and exactly one `is_current = TRUE` row.
- Fact table load completes and row counts match the generated data.

---

## 7. Phase 5 — Fraud Detection Queries

**Goal:** SQL-only fraud signal detection, validated against injected ground truth.

Write `sql/05_fraud_queries.sql` with these five queries (all from the earlier design, refined):

1. **Velocity check** (time-based window frame):
```sql
WITH txn_windows AS (
    SELECT transaction_id, customer_sk, transaction_ts, amount,
           COUNT(*) OVER (
               PARTITION BY customer_sk ORDER BY transaction_ts
               RANGE BETWEEN INTERVAL '10 minutes' PRECEDING AND CURRENT ROW
           ) AS txns_in_10min
    FROM fact_transactions
)
SELECT * FROM txn_windows WHERE txns_in_10min >= 5;
```

2. **Geo-impossibility check** (LAG across dimension join).
3. **Amount-spike check** (compare each transaction to customer's own rolling average via window function `AVG(...) OVER (PARTITION BY customer_sk ORDER BY transaction_ts ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING)`).
4. **Merchant risk exposure rollup** (`RANK() OVER (...)` + `FILTER (WHERE ...)`).
5. **Combined fraud score view** — a `CREATE VIEW v_fraud_candidates AS` that UNIONs all flagged transaction_ids from the above with a `flag_reason` column.

### Validation step (important, do not skip)
Write a query comparing `v_fraud_candidates` against the known `is_actual_fraud` ground truth column to compute precision and recall:

```sql
SELECT
    COUNT(*) FILTER (WHERE fc.transaction_id IS NOT NULL AND ft.is_actual_fraud) AS true_positives,
    COUNT(*) FILTER (WHERE fc.transaction_id IS NOT NULL AND NOT ft.is_actual_fraud) AS false_positives,
    COUNT(*) FILTER (WHERE fc.transaction_id IS NULL AND ft.is_actual_fraud) AS false_negatives
FROM fact_transactions ft
LEFT JOIN v_fraud_candidates fc ON ft.transaction_id = fc.transaction_id;
```

Report precision/recall/F1 in `docs/benchmarks.md`. This turns the project from "wrote some SQL" into "built a detection system with measured accuracy" — genuinely rare in portfolios.

### Acceptance Criteria
- All 5 queries run without error against the full dataset.
- Precision/recall numbers are computed and documented (they don't need to be perfect — document why false positives/negatives occur, that's a legitimate analytical insight).

---

## 8. Phase 6 — Materialized Views, Indexing & Benchmarks

**Goal:** Demonstrate real query optimization with evidence.

### Tasks
1. `sql/03_indexes.sql`: add composite index `(customer_sk, transaction_ts)` and any others needed by the fraud queries.
2. `sql/06_materialized_views.sql`:
```sql
CREATE MATERIALIZED VIEW mv_daily_fraud_summary AS
SELECT DATE_TRUNC('day', transaction_ts) AS day,
       dm.merchant_category,
       COUNT(*) AS total_txns,
       COUNT(*) FILTER (WHERE is_flagged) AS flagged_txns,
       SUM(amount) AS total_volume
FROM fact_transactions ft
JOIN dim_merchant dm ON ft.merchant_sk = dm.merchant_sk
GROUP BY 1, 2;

CREATE UNIQUE INDEX ON mv_daily_fraud_summary (day, merchant_category);
```
3. `sql/07_benchmarks.sql` + a short Python script: run `EXPLAIN ANALYZE` on key queries before and after indexing, and before/after using the materialized view vs. live aggregation. Capture actual timings.

### Acceptance Criteria
- `docs/benchmarks.md` contains a table with at least 3 before/after comparisons (e.g., "raw aggregation: 4.2s → materialized view: 12ms") with the actual `EXPLAIN ANALYZE` output pasted in for credibility.

---

## 9. Phase 7 — Incremental Load Simulation (Watermarking)

**Goal:** Show you understand production ETL patterns, not just one-time loads.

### Tasks
1. `etl/watermark.py`: implement read/update of `etl_watermark` table.
2. `etl/incremental_load.py`: simulate a "new day" of data — generate a small batch of new transactions and staged customer changes, then:
   - Pull only rows with `updated_at > last_loaded_ts`.
   - Apply the SCD merge from Phase 4.
   - Refresh `mv_daily_fraud_summary` with `REFRESH MATERIALIZED VIEW CONCURRENTLY`.
   - Update the watermark.
3. Wrap this in a simple CLI so the agent (or you) can run `python etl/incremental_load.py --simulate-day 2026-01-15` repeatedly to simulate an ongoing pipeline.

### Acceptance Criteria
- Running the incremental script twice in a row does not duplicate data (idempotency check).
- Watermark value updates correctly after each run.

---

## 10. Phase 8 — Demo Dashboard (Streamlit)

**Goal:** A visual, clickable artifact for interviews — not just raw SQL output.

### Tasks
Build `dashboard/app.py` with:
- A fraud summary panel (reads from `mv_daily_fraud_summary`) with a date-range filter.
- A "flagged transactions" table with `flag_reason` from `v_fraud_candidates`.
- A precision/recall scorecard (static or live-computed).
- A merchant risk leaderboard (from the ranking query in Phase 5).

Keep it simple — `streamlit`, `pandas`, `psycopg2` or `sqlalchemy`, a couple of charts via `plotly` or `altair`. This does not need to be fancy; it needs to *exist* so you have something to screen-share in interviews.

### Acceptance Criteria
- `streamlit run dashboard/app.py` launches and successfully queries live Postgres data.

---

## 11. Phase 9 (Stretch Goal) — dbt Layer

If time allows, wrap the SCD merge and materialized views in dbt models instead of raw SQL scripts:
- `dbt snapshot` for the SCD Type 2 logic (replaces Phase 4's manual merge).
- dbt models for the fraud detection views.
- This lets you honestly say "built using dbt" on your resume, which is a highly recognized tool in real data teams.

---

## 12. Documentation Deliverables

- `README.md`: project overview, architecture diagram (can be a simple draw.io/Mermaid diagram), setup instructions (`docker compose up`, run generator, run loads, launch dashboard).
- `docs/architecture.md`: explain the star schema design decisions (why SCD Type 2, why partitioning, why materialized views).
- `docs/benchmarks.md`: all before/after performance numbers.
- `docs/erd.png`: entity-relationship diagram (can be generated via a tool like `dbdiagram.io` or `schemaspy`).

---

## 13. Resume-Ready Summary Line (fill in your actual final numbers)

> "Designed and built a partitioned, SCD Type 2 data warehouse in PostgreSQL simulating a fintech transaction system (5M+ rows across 2 years), implementing SQL-based fraud detection (velocity, geo-impossibility, and amount-spike rules) achieving [X]% precision / [Y]% recall against injected ground truth, incremental ETL with watermarking, and materialized views reducing dashboard query time from [X]s to [Y]ms."

---

## 14. Suggested Build Order for an Agent

1. Phase 1 (schema) → 2 (partitions) → 3 (data gen) → 4 (initial load + SCD)
2. Phase 5 (fraud queries) — validate against ground truth before moving on
3. Phase 6 (indexes/mat views/benchmarks)
4. Phase 7 (incremental load)
5. Phase 8 (dashboard)
6. Phase 9 (dbt) only if time remains
7. Documentation last, once all numbers/benchmarks are real

Each phase should be committed as a separate git commit so the repo history itself tells the story of how the project was built — useful to walk through in interviews.
