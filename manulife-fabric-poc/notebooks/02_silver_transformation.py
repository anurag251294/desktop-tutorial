# Databricks notebook source / Microsoft Fabric Notebook
# MAGIC %md
# MAGIC # 02 - Silver Layer Transformation
# MAGIC **Manulife Fabric POC**
# MAGIC
# MAGIC This notebook reads Bronze delta tables, applies data cleansing and enrichment,
# MAGIC then writes cleansed/conformed data to Silver delta tables.
# MAGIC
# MAGIC **Cleansing operations:**
# MAGIC - Standardize date formats
# MAGIC - Trim whitespace on string columns
# MAGIC - Handle nulls with defaults
# MAGIC - Validate data types
# MAGIC - Deduplicate records
# MAGIC
# MAGIC **Enrichments:**
# MAGIC - Age calculation from date_of_birth
# MAGIC - Age bands (18-25, 26-35, 36-45, 46-55, 56-65, 65+)
# MAGIC - Claim processing days
# MAGIC - Premium annualization

# COMMAND ----------

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, trim, upper, lower, when, lit, current_timestamp, current_date,
    to_date, to_timestamp, datediff, months_between, floor, round as spark_round,
    year, month, dayofmonth, coalesce, count, sum as spark_sum, avg,
    row_number, regexp_replace, initcap
)
from pyspark.sql.window import Window
from pyspark.sql.types import *
from datetime import datetime
import traceback

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helper Functions

# COMMAND ----------

def trim_string_columns(df: DataFrame) -> DataFrame:
    """Trim leading/trailing whitespace from all string columns."""
    for field in df.schema.fields:
        if isinstance(field.dataType, StringType):
            df = df.withColumn(field.name, trim(col(field.name)))
    return df


def standardize_dates(df: DataFrame, date_columns: list, date_format: str = "yyyy-MM-dd") -> DataFrame:
    """
    Convert date columns to a standard date type.
    Tries multiple common formats before falling back to null.
    """
    for col_name in date_columns:
        if col_name in df.columns:
            df = df.withColumn(
                col_name,
                coalesce(
                    to_date(col(col_name), date_format),
                    to_date(col(col_name), "MM/dd/yyyy"),
                    to_date(col(col_name), "dd-MM-yyyy"),
                    to_date(col(col_name), "yyyy/MM/dd"),
                    to_date(col(col_name)),  # Fallback to default parsing
                )
            )
    return df


def deduplicate(df: DataFrame, key_columns: list, order_col: str = "_ingestion_timestamp") -> DataFrame:
    """
    Remove duplicate records, keeping the most recently ingested row.
    """
    window = Window.partitionBy(*key_columns).orderBy(col(order_col).desc())
    return (
        df
        .withColumn("_row_num", row_number().over(window))
        .filter(col("_row_num") == 1)
        .drop("_row_num")
    )


def add_data_quality_flag(df: DataFrame, critical_columns: list) -> DataFrame:
    """
    Add a _dq_flag column: 'PASS' if all critical columns are non-null, else 'FAIL'.
    """
    condition = lit(True)
    for c in critical_columns:
        if c in df.columns:
            condition = condition & col(c).isNotNull()
    return df.withColumn("_dq_flag", when(condition, lit("PASS")).otherwise(lit("FAIL")))


def print_quality_summary(df: DataFrame, table_name: str):
    """Print data quality summary for a transformed table."""
    total = df.count()
    if "_dq_flag" in df.columns:
        pass_count = df.filter(col("_dq_flag") == "PASS").count()
        fail_count = total - pass_count
        pct = (pass_count / total * 100) if total > 0 else 0
        print(f"  {table_name}: {total:,} rows | DQ Pass: {pass_count:,} ({pct:.1f}%) | DQ Fail: {fail_count:,}")
    else:
        print(f"  {table_name}: {total:,} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Transform: Customers

# COMMAND ----------

print("Transforming: customers")
try:
    df_customers = spark.table("bronze_customers")

    df_customers = trim_string_columns(df_customers)
    df_customers = standardize_dates(df_customers, ["date_of_birth", "registration_date"])
    df_customers = deduplicate(df_customers, ["customer_id"])

    # Enrichments
    df_customers = (
        df_customers
        .withColumn("age", floor(months_between(current_date(), col("date_of_birth")) / 12))
        .withColumn(
            "age_band",
            when(col("age").between(18, 25), "18-25")
            .when(col("age").between(26, 35), "26-35")
            .when(col("age").between(36, 45), "36-45")
            .when(col("age").between(46, 55), "46-55")
            .when(col("age").between(56, 65), "56-65")
            .when(col("age") > 65, "65+")
            .otherwise("Unknown")
        )
        # Standardize name casing
        .withColumn("first_name", initcap(col("first_name")) if "first_name" in df_customers.columns else col("first_name"))
        .withColumn("last_name", initcap(col("last_name")) if "last_name" in df_customers.columns else col("last_name"))
        # Standardize province/state to uppercase
        .withColumn("province", upper(col("province")) if "province" in df_customers.columns else lit(None))
    )

    # Data quality flags
    df_customers = add_data_quality_flag(df_customers, ["customer_id", "date_of_birth"])

    # Add Silver metadata
    df_customers = df_customers.withColumn("_silver_timestamp", current_timestamp())

    # Write to Silver
    df_customers.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver_customers")
    print_quality_summary(df_customers, "silver_customers")
    display(df_customers.limit(5))

except Exception as e:
    print(f"ERROR transforming customers: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Transform: Policies

# COMMAND ----------

print("Transforming: policies")
try:
    df_policies = spark.table("bronze_policies")

    df_policies = trim_string_columns(df_policies)
    df_policies = standardize_dates(df_policies, [
        "start_date", "end_date", "effective_date", "issue_date"
    ])
    df_policies = deduplicate(df_policies, ["policy_id"])

    # Enrichments: premium annualization
    df_policies = df_policies.withColumn(
        "annualized_premium",
        when(lower(col("payment_frequency")) == "monthly", col("premium_amount") * 12)
        .when(lower(col("payment_frequency")) == "quarterly", col("premium_amount") * 4)
        .when(lower(col("payment_frequency")) == "semi-annual", col("premium_amount") * 2)
        .when(lower(col("payment_frequency")) == "annual", col("premium_amount"))
        .otherwise(col("premium_amount") * 12)  # Default to monthly
    )

    # Policy duration in days
    df_policies = df_policies.withColumn(
        "policy_duration_days",
        datediff(
            coalesce(col("end_date"), current_date()),
            coalesce(col("start_date"), col("effective_date"), col("issue_date"))
        )
    )

    df_policies = add_data_quality_flag(df_policies, ["policy_id", "customer_id", "premium_amount"])
    df_policies = df_policies.withColumn("_silver_timestamp", current_timestamp())

    df_policies.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver_policies")
    print_quality_summary(df_policies, "silver_policies")
    display(df_policies.limit(5))

except Exception as e:
    print(f"ERROR transforming policies: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Transform: Claims

# COMMAND ----------

print("Transforming: claims")
try:
    df_claims = spark.table("bronze_claims")

    df_claims = trim_string_columns(df_claims)
    df_claims = standardize_dates(df_claims, [
        "claim_date", "submission_date", "settlement_date", "incident_date"
    ])
    df_claims = deduplicate(df_claims, ["claim_id"])

    # Enrichment: claim processing days
    df_claims = df_claims.withColumn(
        "processing_days",
        datediff(
            coalesce(col("settlement_date"), current_date()),
            coalesce(col("submission_date"), col("claim_date"))
        )
    )

    # Enrichment: claim status categorization
    df_claims = df_claims.withColumn(
        "claim_status_category",
        when(lower(col("status")).isin("approved", "settled", "paid"), "Resolved")
        .when(lower(col("status")).isin("pending", "under review", "in progress"), "Open")
        .when(lower(col("status")).isin("denied", "rejected"), "Denied")
        .otherwise("Other")
    )

    df_claims = add_data_quality_flag(df_claims, ["claim_id", "policy_id", "claim_amount"])
    df_claims = df_claims.withColumn("_silver_timestamp", current_timestamp())

    df_claims.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver_claims")
    print_quality_summary(df_claims, "silver_claims")
    display(df_claims.limit(5))

except Exception as e:
    print(f"ERROR transforming claims: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Transform: Products

# COMMAND ----------

print("Transforming: products")
try:
    df_products = spark.table("bronze_products")

    df_products = trim_string_columns(df_products)
    df_products = standardize_dates(df_products, ["launch_date", "effective_date"])
    df_products = deduplicate(df_products, ["product_id"])

    df_products = add_data_quality_flag(df_products, ["product_id", "product_name"])
    df_products = df_products.withColumn("_silver_timestamp", current_timestamp())

    df_products.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver_products")
    print_quality_summary(df_products, "silver_products")
    display(df_products.limit(5))

except Exception as e:
    print(f"ERROR transforming products: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Transform: Investments

# COMMAND ----------

print("Transforming: investments")
try:
    df_investments = spark.table("bronze_investments")

    df_investments = trim_string_columns(df_investments)
    df_investments = standardize_dates(df_investments, [
        "investment_date", "maturity_date", "purchase_date", "valuation_date"
    ])
    df_investments = deduplicate(df_investments, ["investment_id"])

    df_investments = add_data_quality_flag(df_investments, ["investment_id", "customer_id"])
    df_investments = df_investments.withColumn("_silver_timestamp", current_timestamp())

    df_investments.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver_investments")
    print_quality_summary(df_investments, "silver_investments")
    display(df_investments.limit(5))

except Exception as e:
    print(f"ERROR transforming investments: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Transform: Advisors

# COMMAND ----------

print("Transforming: advisors")
try:
    df_advisors = spark.table("bronze_advisors")

    df_advisors = trim_string_columns(df_advisors)
    df_advisors = standardize_dates(df_advisors, ["hire_date", "certification_date", "start_date"])
    df_advisors = deduplicate(df_advisors, ["advisor_id"])

    # Standardize names
    if "advisor_name" in df_advisors.columns:
        df_advisors = df_advisors.withColumn("advisor_name", initcap(col("advisor_name")))

    df_advisors = add_data_quality_flag(df_advisors, ["advisor_id"])
    df_advisors = df_advisors.withColumn("_silver_timestamp", current_timestamp())

    df_advisors.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver_advisors")
    print_quality_summary(df_advisors, "silver_advisors")
    display(df_advisors.limit(5))

except Exception as e:
    print(f"ERROR transforming advisors: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Transform: Transactions

# COMMAND ----------

print("Transforming: transactions")
try:
    df_transactions = spark.table("bronze_transactions")

    df_transactions = trim_string_columns(df_transactions)
    df_transactions = standardize_dates(df_transactions, [
        "transaction_date", "effective_date", "posting_date"
    ])
    df_transactions = deduplicate(df_transactions, ["transaction_id"])

    # Standardize transaction type
    if "transaction_type" in df_transactions.columns:
        df_transactions = df_transactions.withColumn(
            "transaction_type", upper(trim(col("transaction_type")))
        )

    df_transactions = add_data_quality_flag(df_transactions, ["transaction_id", "transaction_amount"])
    df_transactions = df_transactions.withColumn("_silver_timestamp", current_timestamp())

    df_transactions.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("silver_transactions")
    print_quality_summary(df_transactions, "silver_transactions")
    display(df_transactions.limit(5))

except Exception as e:
    print(f"ERROR transforming transactions: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Silver Layer Summary

# COMMAND ----------

silver_tables = [
    "silver_customers", "silver_policies", "silver_claims",
    "silver_products", "silver_investments", "silver_advisors",
    "silver_transactions"
]

print(f"\n{'='*60}")
print("SILVER LAYER TRANSFORMATION COMPLETE")
print(f"{'='*60}")
print(f"\n{'Table':<30} {'Rows':>10} {'DQ Pass':>10} {'DQ Fail':>10}")
print("-" * 62)

for table_name in silver_tables:
    try:
        df = spark.table(table_name)
        total = df.count()
        if "_dq_flag" in df.columns:
            pass_ct = df.filter(col("_dq_flag") == "PASS").count()
            fail_ct = total - pass_ct
        else:
            pass_ct = total
            fail_ct = 0
        print(f"{table_name:<30} {total:>10,} {pass_ct:>10,} {fail_ct:>10,}")
    except Exception as e:
        print(f"{table_name:<30} {'ERROR':>10}")

print(f"\n{'='*60}")
