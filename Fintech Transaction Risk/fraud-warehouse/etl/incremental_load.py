import os
import sys
import time
import argparse
import random
from datetime import datetime, timedelta
import psycopg2
from dotenv import load_dotenv
from watermark import get_watermark, update_watermark

load_dotenv()

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "fraud_warehouse")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "postgres")

SQL_DIR = os.path.join(os.path.dirname(__file__), '..', 'sql')

def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def simulate_incremental_batch(target_date_str):
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    print(f"Simulating new incremental batch for date: {target_date_str}...")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Fetch current watermark
    current_watermark = get_watermark(cursor, 'fact_transactions')
    print(f"Current High-Watermark: {current_watermark}")
    
    # Check idempotency
    if current_watermark and current_watermark >= target_dt + timedelta(days=1) - timedelta(seconds=1):
        print(f"Idempotency Warning: Batch for {target_date_str} has already been loaded past high watermark {current_watermark}. Skipping load.")
        cursor.close()
        conn.close()
        return 0
        
    # 2. Generate small batch (~5,000 new transactions)
    cursor.execute("SELECT MAX(customer_sk) FROM dim_customer WHERE is_current = TRUE;")
    max_cust = cursor.fetchone()[0] or 50000
    cursor.execute("SELECT MAX(merchant_sk) FROM dim_merchant;")
    max_merch = cursor.fetchone()[0] or 2000
    
    batch_size = 5000
    txns = []
    
    for i in range(batch_size):
        offset_secs = random.randint(0, 86399)
        txn_ts = target_dt + timedelta(seconds=offset_secs)
        
        # Filter strictly past watermark if watermark is in target day
        if current_watermark and txn_ts <= current_watermark:
            continue
            
        c_sk = random.randint(1, max_cust)
        m_sk = random.randint(1, max_merch)
        amt = round(random.uniform(5.0, 750.0), 2)
        channel = random.choice(['POS', 'Web', 'Mobile_App'])
        
        # Inject 1% fraud
        is_fraud = random.random() < 0.01
        f_type = 'velocity' if is_fraud else 'none'
        
        txns.append((c_sk, m_sk, txn_ts.strftime('%Y-%m-%d %H:%M:%S'), amt, 'USD', channel, False, is_fraud, f_type))
        
    if not txns:
        print("No new records to insert.")
        cursor.close()
        conn.close()
        return 0
        
    print(f"Inserting {len(txns):,} new incremental transactions...")
    
    insert_sql = """
        INSERT INTO fact_transactions (customer_sk, merchant_sk, transaction_ts, amount, currency, channel, is_flagged, is_actual_fraud, fraud_type)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING transaction_ts;
    """
    
    cursor.executemany(insert_sql, txns)
    
    # 3. Simulate a staging customer update
    cursor.execute("SELECT customer_id, country FROM dim_customer WHERE is_current = TRUE LIMIT 10;")
    stg_samples = cursor.fetchall()
    stg_rows = []
    for cid, country in stg_samples:
        stg_rows.append((cid, 'high', 'active', country, (target_dt + timedelta(hours=12)).strftime('%Y-%m-%d %H:%M:%S')))
        
    cursor.executemany("""
        INSERT INTO staging_customer (customer_id, risk_tier, account_status, country, updated_at)
        VALUES (%s, %s, %s, %s, %s);
    """, stg_rows)
    
    # 4. Run SCD merge
    print("Applying SCD Type 2 merge for new customer staging updates...")
    with open(os.path.join(SQL_DIR, "04_scd_merge.sql"), 'r') as f:
        cursor.execute(f.read())
        
    # 5. Refresh Materialized View Concurrently
    print("Refreshing Materialized View (mv_daily_fraud_summary)...")
    cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_fraud_summary;")
    
    # 6. Update High-Watermark
    max_ts = max(t[2] for t in txns)
    update_watermark(cursor, 'fact_transactions', max_ts)
    
    conn.commit()
    print(f"Incremental pipeline execution finished. Updated watermark to: {max_ts}")
    
    cursor.close()
    conn.close()
    return len(txns)

def main():
    parser = argparse.ArgumentParser(description="Simulate Incremental ETL Load pipeline")
    parser.add_argument("--simulate-day", type=str, default="2026-01-15", help="Simulation target date (YYYY-MM-DD)")
    args = parser.parse_args()
    
    simulate_incremental_batch(args.simulate_day)

if __name__ == "__main__":
    main()
