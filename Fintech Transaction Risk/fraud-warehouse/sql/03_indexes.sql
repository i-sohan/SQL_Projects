-- Phase 6: Performance Optimization via Indexing

-- Composite index on fact_transactions for window functions partitioned by customer & ordered by timestamp
CREATE INDEX IF NOT EXISTS idx_fact_cust_ts ON fact_transactions(customer_sk, transaction_ts);

-- Composite index on fact_transactions for merchant window operations
CREATE INDEX IF NOT EXISTS idx_fact_merch_ts ON fact_transactions(merchant_sk, transaction_ts);

-- Index on transaction_ts alone for date-based range filtering
CREATE INDEX IF NOT EXISTS idx_fact_transaction_ts ON fact_transactions(transaction_ts);

-- Partial index on is_actual_fraud and is_flagged for rapid filtering
CREATE INDEX IF NOT EXISTS idx_fact_actual_fraud ON fact_transactions(is_actual_fraud) WHERE is_actual_fraud = TRUE;

-- Index on dim_customer surrogate key & country
CREATE INDEX IF NOT EXISTS idx_dim_cust_sk_country ON dim_customer(customer_sk, country);

-- Index on staging_customer updated_at for incremental load filtering
CREATE INDEX IF NOT EXISTS idx_staging_updated_at ON staging_customer(updated_at);
