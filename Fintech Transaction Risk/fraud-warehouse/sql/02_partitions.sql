-- Phase 2: Partitioning Setup for fact_transactions (Quarterly Range Partitions 2024 - 2025)

-- 2024 Partitions
CREATE TABLE fact_transactions_2024_q1 PARTITION OF fact_transactions
    FOR VALUES FROM ('2024-01-01 00:00:00') TO ('2024-04-01 00:00:00');

CREATE TABLE fact_transactions_2024_q2 PARTITION OF fact_transactions
    FOR VALUES FROM ('2024-04-01 00:00:00') TO ('2024-07-01 00:00:00');

CREATE TABLE fact_transactions_2024_q3 PARTITION OF fact_transactions
    FOR VALUES FROM ('2024-07-01 00:00:00') TO ('2024-10-01 00:00:00');

CREATE TABLE fact_transactions_2024_q4 PARTITION OF fact_transactions
    FOR VALUES FROM ('2024-10-01 00:00:00') TO ('2025-01-01 00:00:00');

-- 2025 Partitions
CREATE TABLE fact_transactions_2025_q1 PARTITION OF fact_transactions
    FOR VALUES FROM ('2025-01-01 00:00:00') TO ('2025-04-01 00:00:00');

CREATE TABLE fact_transactions_2025_q2 PARTITION OF fact_transactions
    FOR VALUES FROM ('2025-04-01 00:00:00') TO ('2025-07-01 00:00:00');

CREATE TABLE fact_transactions_2025_q3 PARTITION OF fact_transactions
    FOR VALUES FROM ('2025-07-01 00:00:00') TO ('2025-10-01 00:00:00');

CREATE TABLE fact_transactions_2025_q4 PARTITION OF fact_transactions
    FOR VALUES FROM ('2025-10-01 00:00:00') TO ('2026-01-01 00:00:00');

-- Catch-all Default Partition for out-of-range dates
CREATE TABLE fact_transactions_default PARTITION OF fact_transactions DEFAULT;

-- Function to dynamically create future quarterly partitions
CREATE OR REPLACE FUNCTION create_quarterly_partition(start_date DATE)
RETURNS VOID AS $$
DECLARE
    end_date DATE;
    partition_name TEXT;
    qtr_num INT;
    yr_num INT;
BEGIN
    yr_num := EXTRACT(YEAR FROM start_date);
    qtr_num := EXTRACT(QUARTER FROM start_date);
    end_date := start_date + INTERVAL '3 months';
    partition_name := 'fact_transactions_' || yr_num || '_q' || qtr_num;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = partition_name
    ) THEN
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF fact_transactions FOR VALUES FROM (%L) TO (%L);',
            partition_name, start_date, end_date
        );
        RAISE NOTICE 'Created partition %', partition_name;
    ELSE
        RAISE NOTICE 'Partition % already exists', partition_name;
    END IF;
END;
$$ LANGUAGE plpgsql;
