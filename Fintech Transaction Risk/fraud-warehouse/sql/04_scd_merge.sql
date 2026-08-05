-- Phase 4: SCD Type 2 Merge Logic for dim_customer

-- Step 1: Close out active records for customers updated in staging_customer
UPDATE dim_customer d
SET valid_to = (s.updated_at::date - INTERVAL '1 day')::date,
    is_current = FALSE
FROM staging_customer s
WHERE d.customer_id = s.customer_id
  AND d.is_current = TRUE
  AND (
      d.risk_tier IS DISTINCT FROM s.risk_tier
   OR d.account_status IS DISTINCT FROM s.account_status
   OR d.country IS DISTINCT FROM s.country
  );

-- Step 2: Insert new dimension snapshot records
INSERT INTO dim_customer (customer_id, risk_tier, account_status, country, valid_from, valid_to, is_current)
SELECT 
    s.customer_id, 
    s.risk_tier, 
    s.account_status, 
    s.country, 
    s.updated_at::date, 
    NULL, 
    TRUE
FROM staging_customer s
WHERE EXISTS (
    SELECT 1 FROM dim_customer d
    WHERE d.customer_id = s.customer_id 
      AND d.is_current = FALSE
      AND d.valid_to = (s.updated_at::date - INTERVAL '1 day')::date
);
