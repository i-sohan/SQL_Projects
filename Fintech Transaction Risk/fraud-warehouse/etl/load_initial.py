import os
import time
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "fraud_warehouse")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "postgres")

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
SQL_DIR = os.path.join(os.path.dirname(__file__), '..', 'sql')

def ensure_database_exists():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname='postgres',
            user=DB_USER,
            password=DB_PASS
        )
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (DB_NAME,))
        if not cursor.fetchone():
            print(f"Creating database '{DB_NAME}'...")
            cursor.execute(f"CREATE DATABASE {DB_NAME};")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Database check/creation warning: {e}")

def get_connection():
    ensure_database_exists()
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def execute_sql_file(cursor, filepath):
    print(f"Executing SQL file: {os.path.basename(filepath)}")
    with open(filepath, 'r') as f:
        sql = f.read()
    cursor.execute(sql)

def copy_csv_to_table(cursor, filepath, table_name, columns):
    start = time.time()
    print(f"Bulk loading {table_name} via COPY from {os.path.basename(filepath)}...")
    cols_str = f"({', '.join(columns)})"
    copy_sql = f"COPY {table_name} {cols_str} FROM STDIN WITH (FORMAT csv, HEADER true)"
    
    with open(filepath, 'r', encoding='utf-8') as f:
        cursor.copy_expert(copy_sql, f)
        
    duration = time.time() - start
    print(f"Loaded {table_name} in {duration:.3f} seconds.")
    return duration

def main():
    print("Connecting to PostgreSQL database...")
    conn = get_connection()
    conn.autocommit = False
    cursor = conn.cursor()
    
    try:
        # Step 1: Run schema and partitions
        execute_sql_file(cursor, os.path.join(SQL_DIR, "01_schema.sql"))
        execute_sql_file(cursor, os.path.join(SQL_DIR, "02_partitions.sql"))
        conn.commit()
        
        # Step 2: COPY dimensions and staging
        copy_csv_to_table(cursor, os.path.join(DATA_DIR, "dim_customer.csv"), "dim_customer", 
                          ["customer_sk", "customer_id", "risk_tier", "account_status", "country", "valid_from", "valid_to", "is_current"])
        
        copy_csv_to_table(cursor, os.path.join(DATA_DIR, "dim_merchant.csv"), "dim_merchant", 
                          ["merchant_sk", "merchant_id", "merchant_category", "merchant_risk_score", "valid_from", "valid_to", "is_current"])
        
        copy_csv_to_table(cursor, os.path.join(DATA_DIR, "staging_customer.csv"), "staging_customer", 
                          ["customer_id", "risk_tier", "account_status", "country", "updated_at"])
        conn.commit()

        # Update SERIAL sequences for dimension primary keys
        cursor.execute("SELECT setval('dim_customer_customer_sk_seq', (SELECT MAX(customer_sk) FROM dim_customer));")
        cursor.execute("SELECT setval('dim_merchant_merchant_sk_seq', (SELECT MAX(merchant_sk) FROM dim_merchant));")
        conn.commit()

        # Step 3: COPY fact transactions
        fact_duration = copy_csv_to_table(cursor, os.path.join(DATA_DIR, "fact_transactions.csv"), "fact_transactions", 
                          ["transaction_id", "customer_sk", "merchant_sk", "transaction_ts", "amount", "currency", "channel", "is_flagged", "is_actual_fraud", "fraud_type"])
        cursor.execute("SELECT setval('fact_transactions_transaction_id_seq', (SELECT MAX(transaction_id) FROM fact_transactions));")
        conn.commit()

        # Step 4: Run SCD Type 2 merge from staging
        print("Running SCD Type 2 merge logic...")
        execute_sql_file(cursor, os.path.join(SQL_DIR, "04_scd_merge.sql"))
        conn.commit()

        # Step 5: Initialize watermark
        cursor.execute("""
            INSERT INTO etl_watermark (table_name, last_loaded_ts)
            SELECT 'fact_transactions', MAX(transaction_ts) FROM fact_transactions
            ON CONFLICT (table_name) DO UPDATE SET last_loaded_ts = EXCLUDED.last_loaded_ts;
        """)
        conn.commit()

        # Query counts
        cursor.execute("SELECT COUNT(*) FROM dim_customer;")
        cust_cnt = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM fact_transactions;")
        txn_cnt = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM dim_customer WHERE is_current = FALSE;")
        scd_cnt = cursor.fetchone()[0]

        print("==========================================")
        print("Initial Warehouse Load Completed Successfully!")
        print(f"Total Customer Records (incl. SCD2 historical): {cust_cnt:,}")
        print(f"Historical Inactive Customer Snapshots: {scd_cnt:,}")
        print(f"Total Fact Transactions Loaded: {txn_cnt:,}")
        print(f"Fact Table Bulk COPY Throughput: {txn_cnt / fact_duration:,.0f} rows/sec")
        print("==========================================")

    except Exception as e:
        conn.rollback()
        print(f"Error during initial warehouse load: {e}")
        raise e
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    main()
