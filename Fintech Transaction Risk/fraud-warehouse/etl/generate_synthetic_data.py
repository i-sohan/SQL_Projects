import os
import sys
import time
import argparse
import random
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from faker import Faker

# Set random seed for reproducibility
np.random.seed(42)
random.seed(42)
fake = Faker()
Faker.seed(42)

def generate_customers(num_customers=50000):
    print(f"Generating {num_customers:,} customers...")
    countries = ['US', 'UK', 'CA', 'DE', 'FR']
    country_weights = [0.60, 0.15, 0.10, 0.08, 0.07]
    
    risk_tiers = ['low', 'medium', 'high']
    risk_weights = [0.80, 0.15, 0.05]
    
    account_statuses = ['active', 'suspended', 'closed']
    status_weights = [0.95, 0.03, 0.02]
    
    start_signup = datetime(2023, 1, 1)
    end_signup = datetime(2024, 6, 1)
    days_range = (end_signup - start_signup).days
    
    random_days = np.random.randint(0, days_range, size=num_customers)
    signup_dates = [start_signup + timedelta(days=int(d)) for d in random_days]
    
    customer_ids = np.arange(1, num_customers + 1)
    assigned_countries = np.random.choice(countries, size=num_customers, p=country_weights)
    assigned_risks = np.random.choice(risk_tiers, size=num_customers, p=risk_weights)
    assigned_statuses = np.random.choice(account_statuses, size=num_customers, p=status_weights)
    
    df_customers = pd.DataFrame({
        'customer_sk': customer_ids, # Initial SK matches customer_id
        'customer_id': customer_ids,
        'risk_tier': assigned_risks,
        'account_status': assigned_statuses,
        'country': assigned_countries,
        'valid_from': [d.strftime('%Y-%m-%d') for d in signup_dates],
        'valid_to': None,
        'is_current': True
    })
    
    # Generate staging records for SCD Type 2 testing (~10% customers updated in 2024-2025)
    num_updates = int(num_customers * 0.10)
    updated_customer_ids = np.random.choice(customer_ids, size=num_updates, replace=False)
    
    staging_records = []
    for cid in updated_customer_ids:
        # Upgrade risk tier or change status
        old_risk = df_customers.loc[df_customers['customer_id'] == cid, 'risk_tier'].values[0]
        old_country = df_customers.loc[df_customers['customer_id'] == cid, 'country'].values[0]
        new_risk = 'high' if old_risk != 'high' else 'medium'
        new_status = 'suspended'
        
        # updated_at date between 2024-06-01 and 2025-06-01
        rand_offset = random.randint(0, 365)
        update_ts = datetime(2024, 6, 1) + timedelta(days=rand_offset)
        
        staging_records.append({
            'customer_id': cid,
            'risk_tier': new_risk,
            'account_status': new_status,
            'country': old_country,
            'updated_at': update_ts.strftime('%Y-%m-%d %H:%M:%S')
        })
        
    df_staging = pd.DataFrame(staging_records)
    
    return df_customers, df_staging

def generate_merchants(num_merchants=2000):
    print(f"Generating {num_merchants:,} merchants...")
    categories = [
        'retail', 'electronics', 'travel', 'restaurant', 
        'gambling', 'crypto', 'luxury', 'entertainment', 
        'utilities', 'digital_goods'
    ]
    
    merchant_ids = np.arange(1, num_merchants + 1)
    assigned_cats = np.random.choice(categories, size=num_merchants)
    
    # Assign risk score by category
    category_risk_map = {
        'crypto': (70, 99),
        'gambling': (65, 95),
        'luxury': (50, 85),
        'travel': (30, 70),
        'electronics': (25, 60),
        'digital_goods': (20, 50),
        'entertainment': (10, 40),
        'retail': (5, 30),
        'restaurant': (5, 25),
        'utilities': (1, 15)
    }
    
    risk_scores = []
    for cat in assigned_cats:
        low, high = category_risk_map[cat]
        risk_scores.append(round(random.uniform(low, high), 2))
        
    df_merchants = pd.DataFrame({
        'merchant_sk': merchant_ids,
        'merchant_id': merchant_ids,
        'merchant_category': assigned_cats,
        'merchant_risk_score': risk_scores,
        'valid_from': '2023-01-01',
        'valid_to': None,
        'is_current': True
    })
    
    return df_merchants

def generate_transactions(df_customers, df_merchants, target_rows=3000000):
    print(f"Generating {target_rows:,} synthetic transactions with injected fraud patterns...")
    start_time = time.time()
    
    channels = ['POS', 'Web', 'Mobile_App']
    channel_weights = [0.40, 0.40, 0.20]
    
    # Generate timestamp distribution across 2 years (2024-01-01 to 2025-12-31)
    start_ts = datetime(2024, 1, 1).timestamp()
    end_ts = datetime(2025, 12, 31, 23, 59, 59).timestamp()
    
    # Generate random timestamps with diurnal curve (more activity 08:00-22:00)
    raw_timestamps = np.random.uniform(start_ts, end_ts, size=target_rows)
    
    # Vectorized customer & merchant assignments
    customer_sks = np.random.randint(1, len(df_customers) + 1, size=target_rows)
    merchant_sks = np.random.randint(1, len(df_merchants) + 1, size=target_rows)
    assigned_channels = np.random.choice(channels, size=target_rows, p=channel_weights)
    
    # Lognormal amounts based on merchant category
    merchant_cat_lookup = df_merchants.set_index('merchant_sk')['merchant_category'].to_dict()
    assigned_cats = [merchant_cat_lookup[m_id] for m_id in merchant_sks]
    
    cat_amount_means = {
        'retail': 45.0, 'electronics': 250.0, 'travel': 450.0,
        'restaurant': 35.0, 'gambling': 300.0, 'crypto': 850.0,
        'luxury': 1200.0, 'entertainment': 60.0, 'utilities': 110.0,
        'digital_goods': 25.0
    }
    
    amounts = np.zeros(target_rows)
    for i, cat in enumerate(assigned_cats):
        mean_val = cat_amount_means[cat]
        # Lognormal parameter derivation
        sigma = 0.8
        mu = np.log(mean_val) - (sigma**2 / 2)
        amounts[i] = round(float(np.random.lognormal(mu, sigma)), 2)
        
    amounts = np.clip(amounts, 1.00, 25000.00)
    
    # Convert timestamps to datetime string
    dt_strings = [datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') for ts in raw_timestamps]
    
    df_txns = pd.DataFrame({
        'transaction_id': np.arange(1, target_rows + 1),
        'customer_sk': customer_sks,
        'merchant_sk': merchant_sks,
        'transaction_ts': dt_strings,
        'amount': amounts,
        'currency': 'USD',
        'channel': assigned_channels,
        'is_flagged': False,
        'is_actual_fraud': False,
        'fraud_type': 'none'
    })
    
    # Sort by timestamp for realism
    df_txns['ts_temp'] = raw_timestamps
    df_txns.sort_values(by='ts_temp', inplace=True)
    df_txns.drop(columns=['ts_temp'], inplace=True)
    df_txns['transaction_id'] = np.arange(1, len(df_txns) + 1)
    
    print("Injecting explicit fraud patterns...")
    
    # ---------------------------------------------------------
    # 1. Velocity Fraud Pattern (~200 customers, 5-10 txns in 10-min window)
    # ---------------------------------------------------------
    velocity_customers = np.random.choice(df_customers['customer_sk'], size=200, replace=False)
    velocity_rows = []
    current_max_id = len(df_txns) + 1
    
    for cust_sk in velocity_customers:
        base_ts = datetime(2024, 3, 1) + timedelta(days=random.randint(0, 600), hours=random.randint(0, 23))
        num_burst = random.randint(5, 9)
        m_sk = random.randint(1, len(df_merchants))
        
        for idx in range(num_burst):
            burst_ts = base_ts + timedelta(minutes=random.randint(1, 8), seconds=random.randint(0, 50))
            velocity_rows.append({
                'transaction_id': current_max_id,
                'customer_sk': cust_sk,
                'merchant_sk': m_sk,
                'transaction_ts': burst_ts.strftime('%Y-%m-%d %H:%M:%S'),
                'amount': round(random.uniform(50.0, 500.0), 2),
                'currency': 'USD',
                'channel': 'Web',
                'is_flagged': False,
                'is_actual_fraud': True,
                'fraud_type': 'velocity'
            })
            current_max_id += 1
            
    df_velocity = pd.DataFrame(velocity_rows)
    
    # ---------------------------------------------------------
    # 2. Geo-Impossibility Fraud (~150 customers, 2 txns in different countries within 1-2 hours)
    # ---------------------------------------------------------
    # Note: Geo-impossibility is derived from joining with dim_customer country snapshot or merchant country
    geo_customers = np.random.choice(df_customers['customer_sk'], size=150, replace=False)
    geo_rows = []
    
    for cust_sk in geo_customers:
        base_ts = datetime(2024, 5, 1) + timedelta(days=random.randint(0, 550), hours=random.randint(0, 20))
        # First transaction in US (merchant in US / default)
        m_sk_1 = random.randint(1, len(df_merchants))
        geo_rows.append({
            'transaction_id': current_max_id,
            'customer_sk': cust_sk,
            'merchant_sk': m_sk_1,
            'transaction_ts': base_ts.strftime('%Y-%m-%d %H:%M:%S'),
            'amount': round(random.uniform(20.0, 150.0), 2),
            'currency': 'USD',
            'channel': 'POS',
            'is_flagged': False,
            'is_actual_fraud': True,
            'fraud_type': 'geo_impossibility'
        })
        current_max_id += 1
        
        # Second transaction 45 minutes later
        second_ts = base_ts + timedelta(minutes=random.randint(30, 90))
        m_sk_2 = random.randint(1, len(df_merchants))
        geo_rows.append({
            'transaction_id': current_max_id,
            'customer_sk': cust_sk,
            'merchant_sk': m_sk_2,
            'transaction_ts': second_ts.strftime('%Y-%m-%d %H:%M:%S'),
            'amount': round(random.uniform(200.0, 900.0), 2),
            'currency': 'USD',
            'channel': 'POS',
            'is_flagged': False,
            'is_actual_fraud': True,
            'fraud_type': 'geo_impossibility'
        })
        current_max_id += 1
        
    df_geo = pd.DataFrame(geo_rows)
    
    # ---------------------------------------------------------
    # 3. Amount-Spike Fraud (~100 low-spending customers with 15x spike)
    # ---------------------------------------------------------
    spike_customers = np.random.choice(df_customers['customer_sk'], size=100, replace=False)
    spike_rows = []
    
    for cust_sk in spike_customers:
        # Prepend 5 small transactions ($5-$25) to build low historical avg
        base_date = datetime(2024, 2, 1) + timedelta(days=random.randint(0, 500))
        for step in range(5):
            hist_ts = base_date + timedelta(days=step * 2)
            df_txns = pd.concat([df_txns, pd.DataFrame([{
                'transaction_id': current_max_id,
                'customer_sk': cust_sk,
                'merchant_sk': random.randint(1, 500), # low risk merchant
                'transaction_ts': hist_ts.strftime('%Y-%m-%d %H:%M:%S'),
                'amount': round(random.uniform(5.0, 25.0), 2),
                'currency': 'USD',
                'channel': 'POS',
                'is_flagged': False,
                'is_actual_fraud': False,
                'fraud_type': 'none'
            }])], ignore_index=True)
            current_max_id += 1
            
        # Inject the giant spike
        spike_ts = base_date + timedelta(days=11)
        spike_rows.append({
            'transaction_id': current_max_id,
            'customer_sk': cust_sk,
            'merchant_sk': random.randint(1, len(df_merchants)),
            'transaction_ts': spike_ts.strftime('%Y-%m-%d %H:%M:%S'),
            'amount': round(random.uniform(1500.0, 4500.0), 2), # 15x-50x spike
            'currency': 'USD',
            'channel': 'Web',
            'is_flagged': False,
            'is_actual_fraud': True,
            'fraud_type': 'amount_spike'
        })
        current_max_id += 1
        
    df_spike = pd.DataFrame(spike_rows)
    
    # Concatenate all tables
    df_full_txns = pd.concat([df_txns, df_velocity, df_geo, df_spike], ignore_index=True)
    df_full_txns.sort_values(by='transaction_ts', inplace=True)
    df_full_txns['transaction_id'] = np.arange(1, len(df_full_txns) + 1)
    
    print(f"Data generation complete in {time.time() - start_time:.2f} seconds.")
    print(f"Total Transactions: {len(df_full_txns):,}")
    print(f"Injected Fraud Count: {df_full_txns['is_actual_fraud'].sum():,} ({df_full_txns['is_actual_fraud'].mean()*100:.2f}%)")
    
    return df_full_txns

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic data for Fraud Warehouse")
    parser.add_argument("--rows", type=int, default=3000000, help="Target number of transactions")
    parser.add_argument("--outdir", type=str, default="data", help="Output directory for CSV files")
    args = parser.parse_args()
    
    os.makedirs(args.outdir, exist_ok=True)
    
    df_cust, df_staging = generate_customers(num_customers=50000)
    df_merch = generate_merchants(num_merchants=2000)
    df_txns = generate_transactions(df_cust, df_merch, target_rows=args.rows)
    
    print("Writing generated datasets to CSV...")
    df_cust.to_csv(os.path.join(args.outdir, "dim_customer.csv"), index=False)
    df_staging.to_csv(os.path.join(args.outdir, "staging_customer.csv"), index=False)
    df_merch.to_csv(os.path.join(args.outdir, "dim_merchant.csv"), index=False)
    df_txns.to_csv(os.path.join(args.outdir, "fact_transactions.csv"), index=False)
    
    print(f"All files saved successfully to '{args.outdir}/'")

if __name__ == "__main__":
    main()
