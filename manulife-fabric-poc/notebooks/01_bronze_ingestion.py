# Databricks notebook source / Microsoft Fabric Notebook
# MAGIC %md
# MAGIC # 01 - Bronze Layer Ingestion
# MAGIC **Manulife Fabric POC**
# MAGIC
# MAGIC This notebook reads raw CSV files from the lakehouse Files/raw/structured/ area
# MAGIC and loads them into Bronze delta tables with ingestion metadata.
# MAGIC
# MAGIC **Tables ingested:**
# MAGIC - customers, policies, claims, products, investments, advisors, transactions
# MAGIC
# MAGIC **Metadata columns added:**
# MAGIC - `_ingestion_timestamp` - when the record was ingested
# MAGIC - `_source_file` - original file path
# MAGIC - `_batch_id` - unique batch identifier for this run

# COMMAND ----------

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    current_timestamp, lit, input_file_name, col, monotonically_increasing_id
)
from pyspark.sql.types import *
from datetime import datetime
import uuid
import traceback

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

# Batch ID for this ingestion run
BATCH_ID = str(uuid.uuid4())
INGESTION_TIMESTAMP = datetime.now().isoformat()

# Source and target paths (Fabric lakehouse conventions)
RAW_BASE_PATH = "Files/raw/structured"
BRONZE_SCHEMA = "bronze"

# Tables to ingest - map of table name to CSV filename
TABLES = {
    "customers": "customers.csv",
    "policies": "policies.csv",
    "claims": "claims.csv",
    "products": "products.csv",
    "investments": "investments.csv",
    "advisors": "advisors.csv",
    "transactions": "transactions.csv",
}

print(f"Batch ID: {BATCH_ID}")
print(f"Ingestion Timestamp: {INGESTION_TIMESTAMP}")
print(f"Tables to ingest: {list(TABLES.keys())}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helper Functions

# COMMAND ----------

def read_csv_with_metadata(
    spark: SparkSession,
    file_path: str,
    batch_id: str,
) -> DataFrame:
    """
    Read a CSV file with schema inference and add ingestion metadata columns.

    Parameters:
        spark: SparkSession
        file_path: Path to the CSV file in the lakehouse
        batch_id: Unique batch identifier

    Returns:
        DataFrame with metadata columns appended
    """
    df = (
        spark.read
        .option("header", "true")
        .option("inferSchema", "true")
        .option("multiLine", "true")
        .option("escape", '"')
        .csv(file_path)
    )

    # Add metadata columns
    df_with_metadata = (
        df
        .withColumn("_ingestion_timestamp", current_timestamp())
        .withColumn("_source_file", input_file_name())
        .withColumn("_batch_id", lit(batch_id))
    )

    return df_with_metadata


def write_bronze_table(
    df: DataFrame,
    table_name: str,
    mode: str = "overwrite",
) -> int:
    """
    Write a DataFrame to a Bronze delta table.

    Parameters:
        df: DataFrame to write
        table_name: Target table name (will be prefixed with bronze_)
        mode: Write mode - 'overwrite' or 'append'

    Returns:
        Row count written
    """
    full_table_name = f"bronze_{table_name}"
    row_count = df.count()

    (
        df.write
        .format("delta")
        .mode(mode)
        .option("overwriteSchema", "true")
        .saveAsTable(full_table_name)
    )

    print(f"  Wrote {row_count:,} rows to {full_table_name}")
    return row_count

# COMMAND ----------

# MAGIC %md
# MAGIC ## Ingest All Tables

# COMMAND ----------

ingestion_results = []

for table_name, file_name in TABLES.items():
    file_path = f"{RAW_BASE_PATH}/{file_name}"
    print(f"\n{'='*60}")
    print(f"Processing: {table_name}")
    print(f"Source: {file_path}")
    print(f"{'='*60}")

    try:
        # Read CSV with metadata
        df = read_csv_with_metadata(spark, file_path, BATCH_ID)

        # Display schema for verification
        print(f"\n  Schema for {table_name}:")
        df.printSchema()

        # Show sample data
        print(f"\n  Sample data ({table_name}):")
        display(df.limit(5))

        # Write to Bronze delta table
        row_count = write_bronze_table(df, table_name)

        ingestion_results.append({
            "table": table_name,
            "status": "SUCCESS",
            "row_count": row_count,
            "columns": len(df.columns) - 3,  # Exclude metadata columns
        })

    except Exception as e:
        error_msg = str(e)
        print(f"  ERROR ingesting {table_name}: {error_msg}")
        traceback.print_exc()
        ingestion_results.append({
            "table": table_name,
            "status": "FAILED",
            "row_count": 0,
            "columns": 0,
            "error": error_msg,
        })

# COMMAND ----------

# MAGIC %md
# MAGIC ## Ingestion Summary

# COMMAND ----------

from pyspark.sql import Row

summary_df = spark.createDataFrame([Row(**r) for r in ingestion_results])
display(summary_df)

total_rows = sum(r["row_count"] for r in ingestion_results)
success_count = sum(1 for r in ingestion_results if r["status"] == "SUCCESS")
fail_count = sum(1 for r in ingestion_results if r["status"] == "FAILED")

print(f"\n{'='*60}")
print(f"INGESTION COMPLETE")
print(f"  Batch ID:    {BATCH_ID}")
print(f"  Successful:  {success_count}/{len(TABLES)}")
print(f"  Failed:      {fail_count}/{len(TABLES)}")
print(f"  Total rows:  {total_rows:,}")
print(f"{'='*60}")

if fail_count > 0:
    print("\nWARNING: Some tables failed to ingest. Check errors above.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify Bronze Tables

# COMMAND ----------

# Quick verification - read back each Bronze table and show counts
print("Bronze Table Verification:")
print(f"{'Table':<30} {'Count':>10}")
print("-" * 42)

for table_name in TABLES.keys():
    try:
        full_name = f"bronze_{table_name}"
        count = spark.table(full_name).count()
        print(f"{full_name:<30} {count:>10,}")
    except Exception as e:
        print(f"{full_name:<30} {'ERROR':>10} - {e}")
