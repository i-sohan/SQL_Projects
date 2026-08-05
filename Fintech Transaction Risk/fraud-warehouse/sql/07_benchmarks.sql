-- Phase 6: Benchmarks - Queries used for EXPLAIN ANALYZE performance comparison

-- Query Benchmark 1: Velocity Window Query (Customer TS filter)
EXPLAIN ANALYZE
SELECT transaction_id, customer_sk, transaction_ts, amount,
       COUNT(*) OVER (
           PARTITION BY customer_sk ORDER BY transaction_ts
           RANGE BETWEEN INTERVAL '10 minutes' PRECEDING AND CURRENT ROW
       ) AS txns_in_10min
FROM fact_transactions
WHERE transaction_ts >= '2025-01-01' AND transaction_ts < '2025-04-01';

-- Query Benchmark 2: Daily Merchant Category Aggregation (Raw Live Aggregation)
EXPLAIN ANALYZE
SELECT 
    DATE_TRUNC('day', ft.transaction_ts)::date AS day,
    dm.merchant_category,
    COUNT(*) AS total_txns,
    SUM(ft.amount) AS total_volume
FROM fact_transactions ft
JOIN dim_merchant dm ON ft.merchant_sk = dm.merchant_sk
WHERE ft.transaction_ts >= '2025-01-01' AND ft.transaction_ts < '2025-07-01'
GROUP BY 1, 2;

-- Query Benchmark 3: Daily Merchant Category Aggregation (Materialized View Query)
EXPLAIN ANALYZE
SELECT day, merchant_category, total_txns, total_volume
FROM mv_daily_fraud_summary
WHERE day >= '2025-01-01' AND day < '2025-07-01';
