# Databricks notebook source / Microsoft Fabric Notebook
# MAGIC %md
# MAGIC # 03 - Gold Curated Layer
# MAGIC **Manulife Fabric POC**
# MAGIC
# MAGIC This notebook reads Silver tables and creates a star schema Gold layer with:
# MAGIC
# MAGIC **Dimension tables:**
# MAGIC - dim_customer, dim_product, dim_advisor, dim_date, dim_policy, dim_fund
# MAGIC
# MAGIC **Fact tables:**
# MAGIC - fact_claims, fact_transactions, fact_investments, fact_policy_premiums
# MAGIC
# MAGIC **Features:**
# MAGIC - Surrogate key generation
# MAGIC - Date spine (2020-01-01 to 2026-12-31)
# MAGIC - SCD Type 1 (overwrite) for dimensions
# MAGIC - Table optimization (OPTIMIZE, ZORDER)

# COMMAND ----------

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, lit, current_timestamp, monotonically_increasing_id, row_number,
    concat, lpad, year, month, dayofmonth, quarter, dayofweek, weekofyear,
    date_format, when, coalesce, explode, sequence, to_date, expr,
    sha2, concat_ws, upper, floor, months_between, current_date
)
from pyspark.sql.window import Window
from pyspark.sql.types import *
from datetime import date
import traceback

# COMMAND ----------

# MAGIC %md
# MAGIC ## Surrogate Key Generator

# COMMAND ----------

def generate_surrogate_key(df: DataFrame, key_column: str, prefix: str = "") -> DataFrame:
    """
    Generate integer surrogate keys for a dimension table.
    Uses row_number() for deterministic, sequential keys.
    """
    window = Window.orderBy(col(key_column))
    sk_col = f"{key_column.replace('_id', '')}_sk" if "_id" in key_column else f"{key_column}_sk"
    return df.withColumn(sk_col, row_number().over(window))


def write_gold_table(df: DataFrame, table_name: str, mode: str = "overwrite"):
    """Write a DataFrame to a Gold delta table with SCD Type 1 (overwrite)."""
    full_name = f"gold_{table_name}"
    df_out = df.withColumn("_gold_timestamp", current_timestamp())
    df_out.write.format("delta").mode(mode).option("overwriteSchema", "true").saveAsTable(full_name)
    count = df_out.count()
    print(f"  Written: {full_name} ({count:,} rows)")
    return count

# COMMAND ----------

# MAGIC %md
# MAGIC ## dim_date - Date Spine

# COMMAND ----------

print("Creating: dim_date")
try:
    # Generate date spine from 2020-01-01 to 2026-12-31
    start_date = date(2020, 1, 1)
    end_date = date(2026, 12, 31)

    df_date_spine = (
        spark.range(1)
        .select(
            explode(
                sequence(lit(start_date), lit(end_date))
            ).alias("date_key")
        )
    )

    df_dim_date = (
        df_date_spine
        .withColumn("date_sk", row_number().over(Window.orderBy("date_key")))
        .withColumn("year", year("date_key"))
        .withColumn("quarter", quarter("date_key"))
        .withColumn("month", month("date_key"))
        .withColumn("month_name", date_format("date_key", "MMMM"))
        .withColumn("month_short", date_format("date_key", "MMM"))
        .withColumn("day", dayofmonth("date_key"))
        .withColumn("day_of_week", dayofweek("date_key"))
        .withColumn("day_name", date_format("date_key", "EEEE"))
        .withColumn("week_of_year", weekofyear("date_key"))
        .withColumn("is_weekend", when(dayofweek("date_key").isin(1, 7), True).otherwise(False))
        .withColumn("year_month", date_format("date_key", "yyyy-MM"))
        .withColumn("year_quarter", concat(year("date_key"), lit("-Q"), quarter("date_key")))
        .withColumn(
            "fiscal_year",
            when(month("date_key") >= 4, year("date_key") + 1).otherwise(year("date_key"))
        )
        .withColumn(
            "fiscal_quarter",
            when(quarter("date_key") >= 2, quarter("date_key") - 1)
            .otherwise(quarter("date_key") + 3)
        )
    )

    write_gold_table(df_dim_date, "dim_date")
    display(df_dim_date.limit(10))

except Exception as e:
    print(f"ERROR creating dim_date: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## dim_customer

# COMMAND ----------

print("Creating: dim_customer")
try:
    df_silver_customers = spark.table("silver_customers")

    df_dim_customer = (
        df_silver_customers
        .select(
            col("customer_id"),
            col("first_name"),
            col("last_name"),
            col("date_of_birth"),
            col("age"),
            col("age_band"),
            *[col(c) for c in df_silver_customers.columns
              if c in ["email", "phone", "address", "city", "province", "postal_code",
                        "country", "gender", "segment", "risk_profile", "region"]],
        )
        .dropDuplicates(["customer_id"])
    )

    df_dim_customer = generate_surrogate_key(df_dim_customer, "customer_id")

    write_gold_table(df_dim_customer, "dim_customer")
    display(df_dim_customer.limit(5))

except Exception as e:
    print(f"ERROR creating dim_customer: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## dim_product

# COMMAND ----------

print("Creating: dim_product")
try:
    df_silver_products = spark.table("silver_products")

    df_dim_product = (
        df_silver_products
        .select(
            col("product_id"),
            *[col(c) for c in df_silver_products.columns
              if c in ["product_name", "product_type", "product_category", "description",
                        "risk_level", "min_investment", "max_investment", "launch_date",
                        "status", "line_of_business"]],
        )
        .dropDuplicates(["product_id"])
    )

    df_dim_product = generate_surrogate_key(df_dim_product, "product_id")

    write_gold_table(df_dim_product, "dim_product")
    display(df_dim_product.limit(5))

except Exception as e:
    print(f"ERROR creating dim_product: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## dim_advisor

# COMMAND ----------

print("Creating: dim_advisor")
try:
    df_silver_advisors = spark.table("silver_advisors")

    df_dim_advisor = (
        df_silver_advisors
        .select(
            col("advisor_id"),
            *[col(c) for c in df_silver_advisors.columns
              if c in ["advisor_name", "first_name", "last_name", "region", "branch",
                        "hire_date", "certification", "license_type", "status",
                        "specialization", "tier"]],
        )
        .dropDuplicates(["advisor_id"])
    )

    df_dim_advisor = generate_surrogate_key(df_dim_advisor, "advisor_id")

    write_gold_table(df_dim_advisor, "dim_advisor")
    display(df_dim_advisor.limit(5))

except Exception as e:
    print(f"ERROR creating dim_advisor: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## dim_policy

# COMMAND ----------

print("Creating: dim_policy")
try:
    df_silver_policies = spark.table("silver_policies")

    df_dim_policy = (
        df_silver_policies
        .select(
            col("policy_id"),
            col("customer_id"),
            *[col(c) for c in df_silver_policies.columns
              if c in ["policy_type", "policy_status", "status", "start_date", "end_date",
                        "effective_date", "issue_date", "payment_frequency",
                        "coverage_amount", "deductible", "product_id", "advisor_id"]],
        )
        .dropDuplicates(["policy_id"])
    )

    df_dim_policy = generate_surrogate_key(df_dim_policy, "policy_id")

    write_gold_table(df_dim_policy, "dim_policy")
    display(df_dim_policy.limit(5))

except Exception as e:
    print(f"ERROR creating dim_policy: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## dim_fund
# MAGIC Creates a distinct fund dimension from investment data.

# COMMAND ----------

print("Creating: dim_fund")
try:
    df_silver_investments = spark.table("silver_investments")

    # Extract distinct fund info from investments
    fund_columns = [c for c in df_silver_investments.columns
                    if c in ["fund_id", "fund_name", "fund_type", "fund_category",
                             "asset_class", "risk_rating", "management_fee", "currency"]]

    if "fund_id" in df_silver_investments.columns:
        df_dim_fund = (
            df_silver_investments
            .select(*[col(c) for c in fund_columns])
            .dropDuplicates(["fund_id"])
        )
        df_dim_fund = generate_surrogate_key(df_dim_fund, "fund_id")
    else:
        # If no fund_id, create a placeholder dimension
        df_dim_fund = spark.createDataFrame(
            [(1, "General Fund", "Mixed", "Default")],
            ["fund_sk", "fund_name", "fund_type", "fund_category"]
        )
        print("  NOTE: No fund_id in investments; created placeholder dim_fund.")

    write_gold_table(df_dim_fund, "dim_fund")
    display(df_dim_fund.limit(5))

except Exception as e:
    print(f"ERROR creating dim_fund: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_claims

# COMMAND ----------

print("Creating: fact_claims")
try:
    df_silver_claims = spark.table("silver_claims")

    df_fact_claims = (
        df_silver_claims
        .select(
            col("claim_id"),
            col("policy_id"),
            *[col(c) for c in df_silver_claims.columns
              if c in ["customer_id", "claim_date", "submission_date", "settlement_date",
                        "claim_amount", "settlement_amount", "approved_amount",
                        "status", "claim_type", "claim_status_category",
                        "processing_days", "incident_date", "cause"]],
        )
    )

    df_fact_claims = generate_surrogate_key(df_fact_claims, "claim_id")

    write_gold_table(df_fact_claims, "fact_claims")
    display(df_fact_claims.limit(5))

except Exception as e:
    print(f"ERROR creating fact_claims: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_transactions

# COMMAND ----------

print("Creating: fact_transactions")
try:
    df_silver_transactions = spark.table("silver_transactions")

    df_fact_transactions = (
        df_silver_transactions
        .select(
            col("transaction_id"),
            *[col(c) for c in df_silver_transactions.columns
              if c in ["policy_id", "customer_id", "investment_id", "advisor_id",
                        "transaction_date", "transaction_type", "transaction_amount",
                        "units", "unit_price", "fee_amount", "net_amount",
                        "currency", "channel"]],
        )
    )

    df_fact_transactions = generate_surrogate_key(df_fact_transactions, "transaction_id")

    write_gold_table(df_fact_transactions, "fact_transactions")
    display(df_fact_transactions.limit(5))

except Exception as e:
    print(f"ERROR creating fact_transactions: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_investments

# COMMAND ----------

print("Creating: fact_investments")
try:
    df_silver_investments = spark.table("silver_investments")

    df_fact_investments = (
        df_silver_investments
        .select(
            col("investment_id"),
            col("customer_id"),
            *[col(c) for c in df_silver_investments.columns
              if c in ["fund_id", "advisor_id", "investment_date", "purchase_date",
                        "maturity_date", "valuation_date", "investment_amount",
                        "current_value", "market_value", "units", "unit_price",
                        "return_rate", "investment_type", "status", "currency",
                        "region"]],
        )
    )

    df_fact_investments = generate_surrogate_key(df_fact_investments, "investment_id")

    write_gold_table(df_fact_investments, "fact_investments")
    display(df_fact_investments.limit(5))

except Exception as e:
    print(f"ERROR creating fact_investments: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## fact_policy_premiums

# COMMAND ----------

print("Creating: fact_policy_premiums")
try:
    df_silver_policies = spark.table("silver_policies")

    df_fact_premiums = (
        df_silver_policies
        .select(
            col("policy_id"),
            col("customer_id"),
            *[col(c) for c in df_silver_policies.columns
              if c in ["product_id", "advisor_id", "premium_amount",
                        "annualized_premium", "payment_frequency",
                        "start_date", "end_date", "effective_date",
                        "policy_type", "policy_status", "status",
                        "coverage_amount", "policy_duration_days"]],
        )
    )

    df_fact_premiums = generate_surrogate_key(df_fact_premiums, "policy_id")

    write_gold_table(df_fact_premiums, "fact_policy_premiums")
    display(df_fact_premiums.limit(5))

except Exception as e:
    print(f"ERROR creating fact_policy_premiums: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Optimize Gold Tables

# COMMAND ----------

gold_tables_config = {
    "gold_dim_date": "year, month",
    "gold_dim_customer": "customer_id",
    "gold_dim_product": "product_id",
    "gold_dim_advisor": "advisor_id",
    "gold_dim_policy": "policy_id",
    "gold_dim_fund": None,
    "gold_fact_claims": "claim_date",
    "gold_fact_transactions": "transaction_date",
    "gold_fact_investments": "customer_id",
    "gold_fact_policy_premiums": "policy_id",
}

print("Optimizing Gold tables...")
for table_name, zorder_cols in gold_tables_config.items():
    try:
        spark.sql(f"OPTIMIZE {table_name}")
        if zorder_cols:
            spark.sql(f"OPTIMIZE {table_name} ZORDER BY ({zorder_cols})")
        print(f"  Optimized: {table_name}" + (f" (ZORDER: {zorder_cols})" if zorder_cols else ""))
    except Exception as e:
        print(f"  SKIP optimize {table_name}: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Gold Layer Summary

# COMMAND ----------

all_gold_tables = list(gold_tables_config.keys())

print(f"\n{'='*60}")
print("GOLD LAYER BUILD COMPLETE")
print(f"{'='*60}")
print(f"\n{'Table':<35} {'Rows':>10}")
print("-" * 47)

for table_name in all_gold_tables:
    try:
        count = spark.table(table_name).count()
        print(f"{table_name:<35} {count:>10,}")
    except Exception as e:
        print(f"{table_name:<35} {'ERROR':>10}")

print(f"\n{'='*60}")
