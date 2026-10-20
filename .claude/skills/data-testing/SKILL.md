---
name: data-testing
description: How to test data and pipelines (ETL/ELT, data warehouse/lakehouse, batch and streaming) — data quality by dimension (completeness, uniqueness, validity, accuracy, consistency, referential integrity, freshness/timeliness, distribution), source↔target reconciliation (counts, checksums, row by row by key), schema and data contract validation (types, nullability, enums, ranges, schema changes/drift), transformations (business rules, deduplication, SCD type 1/2, joins that inflate or lose rows, time zone and formats), idempotency and reprocessing (re-running the pipeline doesn't duplicate), incremental vs. full loads and late-arriving data, partitions and backfills, nulls and default values, duplicates and keys, PII and masking, lineage and traceability, orchestration (Airflow/dbt/Spark) and what to look at when a job fails or runs late; how to automate it (read-only queries with data-verifier, dbt tests / Great Expectations, reconciliation by counts and hashes), typical bugs and questions for the team. Used by the data-tester; relies on data-verifier.
---

# Data and pipeline testing (ETL / data quality)

Here the product **is the data**: what matters is that it arrives **complete, correct and on time** from source to target, and that the pipeline is **repeatable** without duplicating or losing anything. It is different from testing an app: you test with **queries and reconciliation**, not clicks. It relies on the `data-verifier` (read-only queries to PostgreSQL, MySQL, SQL Server, MongoDB).

## 1. Data quality dimensions

- **Completeness**: no missing rows or required values (nulls where there shouldn't be).
- **Uniqueness**: no duplicates by business key; the PK is unique.
- **Validity**: types, formats, enums, ranges (a date that isn't in the future, an amount ≥ 0, an email shaped like an email).
- **Accuracy**: the value is correct (against the source or a source of truth).
- **Consistency**: coherent across tables/systems (the total of a table = sum of the detail).
- **Referential integrity**: FKs exist; no orphans.
- **Freshness (timeliness)**: the data is up to date within the expected window (today's job ran).
- **Distribution**: the row count and the values are within the historical range (a drop to 10% or a spike to 500% is an anomaly).

## 2. Source ↔ target reconciliation

- **Counts**: rows in source vs. target (with the expected filtering logic).
- **Checksums**: sum of amounts, minimums/maximums, distinct counts per key column.
- **Row by row by key**: for a sample, each target record matches the source after the transformations.
- Expected differences (filters, deduplication) must be **documented**; if not, it is an `MI-XX`.

## 3. Schema and data contract

- **Schema validation**: types, nullability, enums, lengths; a column that changes type breaks downstream.
- **Schema drift**: the source adds/removes/renames a column; the pipeline must handle it (ignore, fail clearly) and not load garbage.
- **Data contract**: if one exists, the producer complies with the agreed schema (see `contract-testing`).

## 4. Transformations

- **Business rules** applied correctly (calculations, mappings, categorizations), with edge cases.
- **Deduplication** and **SCD** (Slowly Changing Dimensions): type 1 (overwrites) vs. type 2 (versions with validity dates); verify the history is built correctly.
- **Joins**: they must not **inflate** rows (fan-out from a badly handled 1:N relation) or **lose** them (an inner join that discards unintentionally).
- **Time zone and formats**: dates in UTC vs. local, decimal separators, encoding; one of the most common causes of bad data.

## 5. Idempotency, incremental loads and late data

- **Idempotency**: re-running the pipeline (same input) **doesn't duplicate** or change the result. Try reprocessing a partition.
- **Incremental vs. full**: an incremental load neither loses nor duplicates compared with a full one; the **watermark** moves correctly.
- **Late-arriving data**: data that arrives late (from a previous day) is loaded into the correct partition and isn't lost.
- **Backfills**: reloading a historical range gives the same result and doesn't overwrite what it shouldn't.

## 6. PII and security

- **PII** masked/anonymized where appropriate (in the analytics warehouse, in non-production environments); no sensitive data in clear text or in logs.
- Restricted access; don't copy production to QA without masking.

## 7. Lineage and orchestration

- **Lineage**: where each field comes from (for auditing and for the impact of a change).
- **Orchestration** (Airflow, dbt, Spark, Dagster): a job that **fails** or **runs late** doesn't leave half-loaded data; correct dependencies and retries; alerts when something doesn't run.

## 8. Automate

- **Read-only** queries with the `data-verifier` (counts, sums, duplicates, nulls, orphans) on source and target.
- **dbt tests** (unique, not_null, relationships, accepted_values) and **Great Expectations / Soda** for declarative expectations.
- Reconciliation by **counts and hashes** of key columns; row-by-row sampling for accuracy.

## 9. Typical data bugs

- Join that inflates rows (duplicates amounts) or inner join that loses records.
- Incremental load that duplicates on reprocessing (not idempotent).
- Dates in the wrong time zone; numbers with the wrong decimal separator.
- Nulls in required columns; orphan FKs.
- Source schema drift that loads corrupt data without warning.
- SCD type 2 with overlapping validity dates or gaps.
- Source≠target counts without a documented reason.
- Production PII copied to QA without masking.
- Job that fails and leaves the table half-loaded (no transaction/atomicity).

## 10. Typical questions for the team

When it is not written down, they are `MI-XX`:

- What are the source and the target, and which transformations/filters are applied (expected differences in the counts)?
- Is the load full or incremental? What is the watermark/incremental key?
- What is the business key for detecting duplicates?
- Which freshness window is expected (how often does it run)?
- Is there SCD? Type 1 or 2 per table?
- Which data is PII and how must it be masked in QA/analytics?
