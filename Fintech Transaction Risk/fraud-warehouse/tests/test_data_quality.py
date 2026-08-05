import os
import pytest
import pandas as pd
import numpy as np

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

def test_csv_files_exist():
    assert os.path.exists(os.path.join(DATA_DIR, 'dim_customer.csv'))
    assert os.path.exists(os.path.join(DATA_DIR, 'dim_merchant.csv'))
    assert os.path.exists(os.path.join(DATA_DIR, 'fact_transactions.csv'))
    assert os.path.exists(os.path.join(DATA_DIR, 'staging_customer.csv'))

def test_data_quality_metrics():
    df_cust = pd.read_csv(os.path.join(DATA_DIR, 'dim_customer.csv'))
    df_merch = pd.read_csv(os.path.join(DATA_DIR, 'dim_merchant.csv'))
    df_txns = pd.read_csv(os.path.join(DATA_DIR, 'fact_transactions.csv'))
    df_staging = pd.read_csv(os.path.join(DATA_DIR, 'staging_customer.csv'))
    
    # 1. Row count assertions
    assert len(df_cust) >= 50000
    assert len(df_merch) >= 2000
    assert len(df_txns) >= 1000000 # Minimum baseline test
    assert len(df_staging) >= 1000
    
    # 2. No orphan foreign keys
    cust_sks = set(df_cust['customer_sk'])
    merch_sks = set(df_merch['merchant_sk'])
    
    assert set(df_txns['customer_sk']).issubset(cust_sks), "Found orphan customer_sk in transactions!"
    assert set(df_txns['merchant_sk']).issubset(merch_sks), "Found orphan merchant_sk in transactions!"
    
    # 3. No negative transaction amounts
    assert (df_txns['amount'] > 0).all(), "Found non-positive transaction amounts!"
    
    # 4. Injected fraud rates within expected tolerances (0.01% - 5.0%)
    fraud_rate = df_txns['is_actual_fraud'].mean()
    assert 0.0001 <= fraud_rate <= 0.05, f"Fraud rate {fraud_rate} outside expected range!"
    
    # 5. Check expected fraud types are present
    fraud_types = set(df_txns[df_txns['is_actual_fraud']]['fraud_type'].unique())
    assert 'velocity' in fraud_types
    assert 'geo_impossibility' in fraud_types
    assert 'amount_spike' in fraud_types
