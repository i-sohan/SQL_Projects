-- Phase 6: Materialized Views for BI Dashboard Aggregation

DROP MATERIALIZED VIEW IF EXISTS mv_daily_fraud_summary CASCADE;

CREATE MATERIALIZED VIEW mv_daily_fraud_summary AS
SELECT 
    DATE_TRUNC('day', ft.transaction_ts)::date AS day,
    dm.merchant_category,
    COUNT(*) AS total_txns,
    COUNT(*) FILTER (WHERE ft.is_actual_fraud) AS actual_fraud_txns,
    COUNT(*) FILTER (WHERE ft.is_flagged OR ft.is_actual_fraud) AS flagged_txns,
    SUM(ft.amount) AS total_volume,
    SUM(CASE WHEN (ft.is_flagged OR ft.is_actual_fraud) THEN ft.amount ELSE 0 END) AS flagged_volume
FROM fact_transactions ft
JOIN dim_merchant dm ON ft.merchant_sk = dm.merchant_sk
GROUP BY 1, 2;

-- Unique index required for REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_daily_fraud_day_cat ON mv_daily_fraud_summary (day, merchant_category);
