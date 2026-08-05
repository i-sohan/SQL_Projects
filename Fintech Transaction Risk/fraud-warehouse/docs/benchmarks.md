# Query Optimization & Detection Performance Benchmarks

This document records empirical performance benchmarks comparing unindexed vs indexed query execution and raw live aggregate queries vs pre-computed Materialized Views.

## 1. Summary Benchmark Matrix

| Workload / Query Type | Baseline Execution | Optimized Execution | Speedup / Optimization Mechanism |
| :--- | :--- | :--- | :--- |
| **Quarterly Window Function (Velocity Rule)** | 1543.7 ms (Seq Scan) | 181.6 ms (Partition Pruning + Index) | **8.5x Faster** |
| **6-Month Daily Category Aggregation** | 123.7 ms (Live Fact Scan) | 0.5 ms (Materialized View Scan) | **243.5x Faster** |

## 2. Fraud Detection Accuracy & Ground Truth Validation

Evaluated against injected ground truth (`is_actual_fraud`):

- **True Positives (TP)**: 669
- **False Positives (FP)**: 73,831
- **False Negatives (FN)**: 1,104
- **Precision**: **0.90%**
- **Recall**: **37.73%**

## 3. Actual EXPLAIN ANALYZE Execution Plans

### Benchmark 1: Velocity Window Query
```sql
WindowAgg  (cost=0.70..11548.50 rows=124269 width=34) (actual time=0.220..177.214 rows=124269.00 loops=1)
  Window: w1 AS (PARTITION BY fact_transactions.customer_sk ORDER BY fact_transactions.transaction_ts RANGE BETWEEN '00:10:00'::interval PRECEDING AND CURRENT ROW)
  Storage: Memory  Maximum Storage: 17kB
  Buffers: shared hit=124412
  ->  Index Scan using fact_transactions_2025_q1_customer_sk_transaction_ts_idx on fact_transactions_2025_q1 fact_transactions  (cost=0.42..9373.80 rows=124269 width=26) (actual time=0.175..90.872 rows=124269.00 loops=1)
        Index Cond: ((transaction_ts >= '2025-01-01 00:00:00'::timestamp without time zone) AND (transaction_ts < '2025-04-01 00:00:00'::timestamp without time zone))
        Index Searches: 1
        Buffers: shared hit=124412
Planning:
  Buffers: shared hit=317 read=21 dirtied=4
Planning Time: 25.651 ms
Execution Time: 181.614 ms
```

### Benchmark 2: Live Fact Aggregation
```sql
Finalize HashAggregate  (cost=8655.58..8690.58 rows=2000 width=53) (actual time=119.441..123.280 rows=1810.00 loops=1)
  Group Key: ((date_trunc('day'::text, ft.transaction_ts))::date), dm.merchant_category
  Batches: 1  Memory Usage: 977kB
  Buffers: shared hit=2528
  ->  Gather  (cost=8080.58..8595.58 rows=4800 width=53) (actual time=116.160..120.773 rows=3770.00 loops=1)
        Workers Planned: 2
        Workers Launched: 2
        Buffers: shared hit=2528
        ->  Partial HashAggregate  (cost=7080.58..7115.58 rows=2000 width=53) (actual time=82.707..83.408 rows=1256.67 loops=3)
              Group Key: (date_trunc('day'::text, ft.transaction_ts))::date, dm.merchant_category
              Batches: 1  Memory Usage: 721kB
              Buffers: shared hit=2528
              Worker 0:  Batches: 1  Memory Usage: 657kB
              Worker 1:  Batches: 1  Memory Usage: 721kB
              ->  Hash Join  (cost=61.00..6044.31 rows=103627 width=19) (actual time=1.800..57.959 rows=82901.33 loops=3)
                    Hash Cond: (ft.merchant_sk = dm.merchant_sk)
                    Buffers: shared hit=2528
                    ->  Parallel Append  (cost=0.00..5192.58 rows=103626 width=18) (actual time=0.033..27.880 rows=82901.33 loops=3)
                          Buffers: shared hit=2480
                          ->  Parallel Seq Scan on fact_transactions_2025_q2 ft_2  (cost=0.00..2337.96 rows=73197 width=18) (actual time=0.043..15.551 rows=41478.33 loops=3)
                                Filter: ((transaction_ts >= '2025-01-01 00:00:00'::timestamp without time zone) AND (transaction_ts < '2025-07-01 00:00:00'::timestamp without time zone))
                                Buffers: shared hit=1240
                          ->  Parallel Seq Scan on fact_transactions_2025_q1 ft_1  (cost=0.00..2336.49 rows=73099 width=18) (actual time=0.014..10.180 rows=62134.50 loops=2)
                                Filter: ((transaction_ts >= '2025-01-01 00:00:00'::timestamp without time zone) AND (transaction_ts < '2025-07-01 00:00:00'::timestamp without time zone))
                                Buffers: shared hit=1240
                    ->  Hash  (cost=36.00..36.00 rows=2000 width=13) (actual time=1.748..1.749 rows=2000.00 loops=3)
                          Buckets: 2048  Batches: 1  Memory Usage: 109kB
                          Buffers: shared hit=48
                          ->  Seq Scan on dim_merchant dm  (cost=0.00..36.00 rows=2000 width=13) (actual time=0.931..1.442 rows=2000.00 loops=3)
                                Buffers: shared hit=48
Planning:
  Buffers: shared hit=207 read=12
Planning Time: 14.457 ms
Execution Time: 123.677 ms
```

### Benchmark 3: Materialized View Query
```sql
Bitmap Heap Scan on mv_daily_fraud_summary  (cost=50.86..155.04 rows=1812 width=29) (actual time=0.231..0.445 rows=1810.00 loops=1)
  Recheck Cond: ((day >= '2025-01-01'::date) AND (day < '2025-07-01'::date))
  Heap Blocks: exact=20
  Buffers: shared hit=20 read=10
  ->  Bitmap Index Scan on idx_mv_daily_fraud_day_cat  (cost=0.00..50.40 rows=1812 width=0) (actual time=0.203..0.203 rows=1810.00 loops=1)
        Index Cond: ((day >= '2025-01-01'::date) AND (day < '2025-07-01'::date))
        Index Searches: 1
        Buffers: shared read=10
Planning:
  Buffers: shared hit=47 dirtied=3
Planning Time: 1.218 ms
Execution Time: 0.508 ms
```
