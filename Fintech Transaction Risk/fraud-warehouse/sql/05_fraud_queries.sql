-- Phase 5: SQL-Based Fraud Detection Rules & Precision/Recall Evaluation

-- Rule 1: Velocity Check (5+ txns in rolling 10-minute window)
CREATE OR REPLACE VIEW v_fraud_velocity AS
WITH txn_windows AS (
    SELECT 
        transaction_id, customer_sk, merchant_sk, transaction_ts, amount, channel,
        COUNT(*) OVER (
            PARTITION BY customer_sk ORDER BY transaction_ts
            RANGE BETWEEN INTERVAL '10 minutes' PRECEDING AND CURRENT ROW
        ) AS txns_in_10min
    FROM fact_transactions
)
SELECT transaction_id, customer_sk, merchant_sk, transaction_ts, amount, 
       'velocity'::text AS flag_reason
FROM txn_windows 
WHERE txns_in_10min >= 5;

-- Rule 2: Geo-Impossibility Check (Customer transacts in 2 different countries within 2 hours)
CREATE OR REPLACE VIEW v_fraud_geo_impossibility AS
WITH txn_geo AS (
    SELECT 
        ft.transaction_id, ft.customer_sk, ft.merchant_sk, ft.transaction_ts, ft.amount,
        dc.country,
        LAG(dc.country) OVER (PARTITION BY ft.customer_sk ORDER BY ft.transaction_ts) AS prev_country,
        LAG(ft.transaction_ts) OVER (PARTITION BY ft.customer_sk ORDER BY ft.transaction_ts) AS prev_ts
    FROM fact_transactions ft
    JOIN dim_customer dc ON ft.customer_sk = dc.customer_sk
)
SELECT transaction_id, customer_sk, merchant_sk, transaction_ts, amount,
       'geo_impossibility'::text AS flag_reason
FROM txn_geo
WHERE prev_country IS NOT NULL 
  AND country <> prev_country
  AND transaction_ts - prev_ts <= INTERVAL '2 hours';

-- Rule 3: Amount-Spike Check (Transaction amount >= 10x customer's 30-txn historical average)
CREATE OR REPLACE VIEW v_fraud_amount_spike AS
WITH txn_stats AS (
    SELECT 
        transaction_id, customer_sk, merchant_sk, transaction_ts, amount,
        AVG(amount) OVER (
            PARTITION BY customer_sk 
            ORDER BY transaction_ts 
            ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING
        ) AS rolling_avg_amount,
        COUNT(amount) OVER (
            PARTITION BY customer_sk 
            ORDER BY transaction_ts 
            ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING
        ) AS hist_txn_count
    FROM fact_transactions
)
SELECT transaction_id, customer_sk, merchant_sk, transaction_ts, amount,
       'amount_spike'::text AS flag_reason
FROM txn_stats
WHERE hist_txn_count >= 3 
  AND amount >= (rolling_avg_amount * 10.0)
  AND amount >= 500.0;

-- Rule 4: High-Risk Merchant Exposure
CREATE OR REPLACE VIEW v_fraud_merchant_risk AS
SELECT 
    ft.transaction_id, ft.customer_sk, ft.merchant_sk, ft.transaction_ts, ft.amount,
    'high_risk_merchant_exposure'::text AS flag_reason
FROM fact_transactions ft
JOIN dim_merchant dm ON ft.merchant_sk = dm.merchant_sk
WHERE (dm.merchant_risk_score >= 80.0 AND ft.amount > 500.0)
   OR (dm.merchant_category IN ('crypto', 'gambling') AND ft.amount > 1500.0);

-- Rule 5: Combined Fraud Candidates View (UNION ALL of all flagged rules)
CREATE OR REPLACE VIEW v_fraud_candidates AS
SELECT 
    transaction_id,
    MIN(customer_sk) AS customer_sk,
    MIN(merchant_sk) AS merchant_sk,
    MIN(transaction_ts) AS transaction_ts,
    MIN(amount) AS amount,
    STRING_AGG(flag_reason, ', ' ORDER BY flag_reason) AS flag_reasons,
    COUNT(flag_reason) AS flag_count
FROM (
    SELECT transaction_id, customer_sk, merchant_sk, transaction_ts, amount, flag_reason FROM v_fraud_velocity
    UNION ALL
    SELECT transaction_id, customer_sk, merchant_sk, transaction_ts, amount, flag_reason FROM v_fraud_geo_impossibility
    UNION ALL
    SELECT transaction_id, customer_sk, merchant_sk, transaction_ts, amount, flag_reason FROM v_fraud_amount_spike
    UNION ALL
    SELECT transaction_id, customer_sk, merchant_sk, transaction_ts, amount, flag_reason FROM v_fraud_merchant_risk
) combined
GROUP BY transaction_id;

-- Rule 6: Merchant Risk Exposure Ranking Rollup
CREATE OR REPLACE VIEW v_merchant_risk_leaderboard AS
SELECT 
    dm.merchant_id,
    dm.merchant_category,
    dm.merchant_risk_score,
    COUNT(ft.transaction_id) AS total_transactions,
    COUNT(fc.transaction_id) AS flagged_fraud_txns,
    SUM(ft.amount) AS total_volume_usd,
    SUM(CASE WHEN fc.transaction_id IS NOT NULL THEN ft.amount ELSE 0 END) AS flagged_volume_usd,
    RANK() OVER (ORDER BY COUNT(fc.transaction_id) DESC, SUM(ft.amount) DESC) AS risk_rank
FROM dim_merchant dm
JOIN fact_transactions ft ON dm.merchant_sk = ft.merchant_sk
LEFT JOIN v_fraud_candidates fc ON ft.transaction_id = fc.transaction_id
GROUP BY dm.merchant_id, dm.merchant_category, dm.merchant_risk_score;

-- Ground Truth Validation Query (Precision, Recall, F1 Evaluation)
-- Execute this query to calculate accuracy metrics against injected ground truth
SELECT 
    COUNT(*) FILTER (WHERE fc.transaction_id IS NOT NULL AND ft.is_actual_fraud) AS true_positives,
    COUNT(*) FILTER (WHERE fc.transaction_id IS NOT NULL AND NOT ft.is_actual_fraud) AS false_positives,
    COUNT(*) FILTER (WHERE fc.transaction_id IS NULL AND ft.is_actual_fraud) AS false_negatives,
    COUNT(*) FILTER (WHERE fc.transaction_id IS NULL AND NOT ft.is_actual_fraud) AS true_negatives,
    ROUND(
        COUNT(*) FILTER (WHERE fc.transaction_id IS NOT NULL AND ft.is_actual_fraud)::numeric / 
        NULLIF(COUNT(*) FILTER (WHERE fc.transaction_id IS NOT NULL), 0) * 100, 2
    ) AS precision_pct,
    ROUND(
        COUNT(*) FILTER (WHERE fc.transaction_id IS NOT NULL AND ft.is_actual_fraud)::numeric / 
        NULLIF(COUNT(*) FILTER (WHERE ft.is_actual_fraud), 0) * 100, 2
    ) AS recall_pct,
    ROUND(
        2 * (
            (COUNT(*) FILTER (WHERE fc.transaction_id IS NOT NULL AND ft.is_actual_fraud)::numeric / NULLIF(COUNT(*) FILTER (WHERE fc.transaction_id IS NOT NULL), 0)) *
            (COUNT(*) FILTER (WHERE fc.transaction_id IS NOT NULL AND ft.is_actual_fraud)::numeric / NULLIF(COUNT(*) FILTER (WHERE ft.is_actual_fraud), 0))
        ) / NULLIF(
            (COUNT(*) FILTER (WHERE fc.transaction_id IS NOT NULL AND ft.is_actual_fraud)::numeric / NULLIF(COUNT(*) FILTER (WHERE fc.transaction_id IS NOT NULL), 0)) +
            (COUNT(*) FILTER (WHERE fc.transaction_id IS NOT NULL AND ft.is_actual_fraud)::numeric / NULLIF(COUNT(*) FILTER (WHERE ft.is_actual_fraud), 0)), 0
        ) * 100, 2
    ) AS f1_score_pct
FROM fact_transactions ft
LEFT JOIN v_fraud_candidates fc ON ft.transaction_id = fc.transaction_id;
