# Fintech Transaction Risk & Fraud Analytics Warehouse Architecture

## 1. Architecture Overview & Design Rationale

The data warehouse architecture models high-volume fintech credit/debit transaction streams and automated risk monitoring. It is designed around a **Star Schema** optimized for analytical processing (OLAP), featuring **Slowly Changing Dimensions (SCD Type 2)**, **Partitioned Fact Tables**, **SQL-driven Fraud Rule Processing**, and **Concurrent Materialized Views**.

```
                          [ Synthetic Data Generator ]
                                       │
                                       ▼
                             [ Staging Customer ]
                                       │
                                       ▼ (SCD Type 2 Merge)
┌──────────────────────────────────────┴─────────────────────────────────────┐
│                             PostgreSQL Warehouse                           │
│                                                                            │
│   ┌────────────────────┐   ┌──────────────────────────┐   ┌──────────────┐ │
│   │    dim_customer    │   │    fact_transactions     │   │ dim_merchant │ │
│   │    (SCD Type 2)    ├──►│  (Partitioned Range Qtr) ◄───┤  (Current)   │ │
│   └────────────────────┘   └─────────────┬────────────┘   └──────────────┘ │
│                                          │                                 │
│                                          ▼                                 │
│                            [ v_fraud_candidates (View) ]                   │
│                                          │                                 │
│                                          ▼                                 │
│                       [ mv_daily_fraud_summary (Mat View) ]                │
└──────────────────────────────────────────┬─────────────────────────────────┘
                                           │
                                           ▼
                                [ Streamlit Dashboard ]
```

---

## 2. Dimensional Model (Star Schema)

### Customer Dimension (`dim_customer`) - SCD Type 2
In credit risk and fraud analysis, a customer's risk profile (`risk_tier`) and account status change over time (e.g., upgraded from 'low' to 'high' risk after a flagged breach). 

To ensure point-in-time accuracy without mutating historical facts:
- **Surrogate Key (`customer_sk`)**: Primary key for unique version snapshots.
- **Natural Key (`customer_id`)**: Identifies the customer entity across versions.
- **`valid_from` / `valid_to` / `is_current`**: Effective date range flags enabling historical point-in-time point joins.

### Merchant Dimension (`dim_merchant`)
Captures merchant categorization (`crypto`, `gambling`, `retail`, `luxury`, etc.) and a dynamically computed `merchant_risk_score` (1.00 to 99.99).

### Fact Table (`fact_transactions`)
Contains immutable atomic transactions.
- **Partition Key**: `transaction_ts` (Range partitioned quarterly).
- **Composite Primary Key**: `(transaction_id, transaction_ts)`. PostgreSQL requires partition keys to be included in unique/primary key constraints.
- **Ground Truth Ground Column**: `is_actual_fraud` (Boolean) and `fraud_type` (String) used to compute Precision, Recall, and F1 metrics against SQL detection queries.

---

## 3. Partitioning Strategy

High-scale transaction tables quickly suffer from degraded index trees and slow table scans. 

- **Range Partitioning**: `fact_transactions` is range-partitioned quarterly (e.g., `fact_transactions_2024_q1`, `fact_transactions_2024_q2`).
- **Partition Pruning**: PostgreSQL query planner automatically eliminates non-matching quarter tables when filtering by `transaction_ts >= '2025-01-01'`.
- **Catch-All Default Partition**: `fact_transactions_default` captures edge case timestamps to prevent bulk load failures.
- **Dynamic Partition Management**: Automating future partition allocation via `create_quarterly_partition(start_date DATE)` PL/pgSQL stored function.

---

## 4. SQL Fraud Detection Rules

1. **Velocity Rule**: Window function `COUNT(*) OVER (PARTITION BY customer_sk ORDER BY transaction_ts RANGE BETWEEN INTERVAL '10 minutes' PRECEDING AND CURRENT ROW) >= 5`.
2. **Geo-Impossibility Rule**: Window `LAG(country)` over customer history detecting consecutive transactions occurring in different countries within 2 hours.
3. **Amount Spike Rule**: Window `AVG(amount)` over `ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING` identifying transactions $\ge 10\times$ rolling average.
4. **High Risk Merchant Exposure**: Filtering high-risk merchants ($>80.0$ risk score or high-risk categories like crypto/gambling with large amounts).
5. **Candidates Rollup View (`v_fraud_candidates`)**: `UNION ALL` aggregation grouping by `transaction_id` and concatenating string flag reasons via `STRING_AGG()`.

---

## 5. Incremental ETL & Watermarking

Production data pipelines run incrementally. The incremental pipeline in `etl/incremental_load.py`:
- Tracks `last_loaded_ts` in `etl_watermark`.
- Processes only new records where `transaction_ts > last_loaded_ts`.
- Merges customer changes from `staging_customer` into `dim_customer`.
- Executes `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_fraud_summary`.
- Guarantees **idempotency**: duplicate CLI runs on the same date produce zero duplicate records.
