import os
import psycopg2

def get_watermark(cursor, table_name='fact_transactions'):
    cursor.execute("SELECT last_loaded_ts FROM etl_watermark WHERE table_name = %s;", (table_name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    return None

def update_watermark(cursor, table_name, last_loaded_ts):
    cursor.execute("""
        INSERT INTO etl_watermark (table_name, last_loaded_ts)
        VALUES (%s, %s)
        ON CONFLICT (table_name) DO UPDATE SET last_loaded_ts = EXCLUDED.last_loaded_ts;
    """, (table_name, last_loaded_ts))
