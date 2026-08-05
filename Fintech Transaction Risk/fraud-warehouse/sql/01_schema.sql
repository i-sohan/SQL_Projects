-- Phase 1: Schema Setup for Fintech Transaction Risk & Fraud Analytics Warehouse

DROP TABLE IF EXISTS staging_customer CASCADE;
DROP TABLE IF EXISTS etl_watermark CASCADE;
DROP TABLE IF EXISTS fact_transactions CASCADE;
DROP TABLE IF EXISTS dim_merchant CASCADE;
DROP TABLE IF EXISTS dim_customer CASCADE;

-- Customer Dimension (SCD Type 2)
CREATE TABLE dim_customer (
    customer_sk SERIAL PRIMARY KEY,
    customer_id INT NOT NULL,
    risk_tier VARCHAR(20) NOT NULL,
    account_status VARCHAR(20) NOT NULL,
    country VARCHAR(50) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    is_current BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_dim_customer_id ON dim_customer(customer_id);

-- Merchant Dimension
CREATE TABLE dim_merchant (
    merchant_sk SERIAL PRIMARY KEY,
    merchant_id INT NOT NULL,
    merchant_category VARCHAR(50) NOT NULL,
    merchant_risk_score NUMERIC(5,2) NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE,
    is_current BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_dim_merchant_id ON dim_merchant(merchant_id);

-- Fact Transactions (Partitioned by Range on transaction_ts)
CREATE TABLE fact_transactions (
    transaction_id BIGSERIAL,
    customer_sk INT NOT NULL,
    merchant_sk INT NOT NULL,
    transaction_ts TIMESTAMP NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    channel VARCHAR(20) NOT NULL,
    is_flagged BOOLEAN DEFAULT FALSE,
    is_actual_fraud BOOLEAN DEFAULT FALSE,
    fraud_type VARCHAR(50),
    PRIMARY KEY (transaction_id, transaction_ts)
) PARTITION BY RANGE (transaction_ts);

-- Staging table for SCD updates
CREATE TABLE staging_customer (
    customer_id INT NOT NULL,
    risk_tier VARCHAR(20) NOT NULL,
    account_status VARCHAR(20) NOT NULL,
    country VARCHAR(50) NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

-- ETL Watermark table
CREATE TABLE etl_watermark (
    table_name VARCHAR(50) PRIMARY KEY,
    last_loaded_ts TIMESTAMP NOT NULL
);
