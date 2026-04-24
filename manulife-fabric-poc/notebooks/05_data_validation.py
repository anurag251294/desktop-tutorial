# Databricks notebook source / Microsoft Fabric Notebook
# MAGIC %md
# MAGIC # 05 - Data Validation & Business Queries
# MAGIC **Manulife Fabric POC**
# MAGIC
# MAGIC This notebook validates the Gold layer tables and runs sample business queries
# MAGIC to demonstrate the POC answering key questions.
# MAGIC
# MAGIC **Validation checks:**
# MAGIC - Row counts per table
# MAGIC - Null checks on critical columns
# MAGIC - Referential integrity between facts and dimensions
# MAGIC - Value range validation
# MAGIC
# MAGIC **Business queries:**
# MAGIC - Top customers by claim volume
# MAGIC - Claims ratio by policy type
# MAGIC - Investment inflows by region
# MAGIC - Advisor AUM rankings

# COMMAND ----------

from pyspark.sql import SparkSession, DataFrame, Row
from pyspark.sql.functions import (
    col, count, sum as spark_sum, avg, min as spark_min, max as spark_max,
    when, isnan, isnull, lit, round as spark_round, desc, asc,
    current_timestamp, countDistinct
)
import traceback

# COMMAND ----------

# MAGIC %md
# MAGIC ## Validation Framework

# COMMAND ----------

validation_results = []


def add_result(check_name: str, table_name: str, status: str, detail: str, metric_value=None):
    """Record a validation result."""
    result = {
        "check_name": check_name,
        "table_name": table_name,
        "status": status,  # PASS or FAIL
        "detail": detail,
        "metric_value": str(metric_value) if metric_value is not None else "",
    }
    validation_results.append(result)
    icon = "PASS" if status == "PASS" else "FAIL"
    print(f"  [{icon}] {check_name} | {table_name} | {detail}")


def check_row_count(table_name: str, min_expected: int = 1):
    """Validate that a table has at least min_expected rows."""
    try:
        df = spark.table(table_name)
        row_count = df.count()
        status = "PASS" if row_count >= min_expected else "FAIL"
        add_result(
            "row_count", table_name, status,
            f"Expected >= {min_expected}, got {row_count:,}",
            row_count,
        )
        return row_count
    except Exception as e:
        add_result("row_count", table_name, "FAIL", f"Table not found: {e}", 0)
        return 0


def check_nulls(table_name: str, columns: list):
    """Check for null values in critical columns."""
    try:
        df = spark.table(table_name)
        for col_name in columns:
            if col_name not in df.columns:
                add_result("null_check", table_name, "FAIL", f"Column '{col_name}' not found")
                continue
            null_count = df.filter(col(col_name).isNull()).count()
            total = df.count()
            pct = (null_count / total * 100) if total > 0 else 0
            status = "PASS" if null_count == 0 else ("FAIL" if pct > 10 else "PASS")
            add_result(
                "null_check", table_name, status,
                f"{col_name}: {null_count:,} nulls ({pct:.1f}%)",
                null_count,
            )
    except Exception as e:
        add_result("null_check", table_name, "FAIL", f"Error: {e}")


def check_referential_integrity(
    fact_table: str, fact_col: str,
    dim_table: str, dim_col: str,
):
    """Check that all foreign keys in the fact table exist in the dimension table."""
    try:
        df_fact = spark.table(fact_table)
        df_dim = spark.table(dim_table)

        if fact_col not in df_fact.columns:
            add_result("ref_integrity", fact_table, "FAIL", f"Column '{fact_col}' not in {fact_table}")
            return
        if dim_col not in df_dim.columns:
            add_result("ref_integrity", dim_table, "FAIL", f"Column '{dim_col}' not in {dim_table}")
            return

        # Find orphan keys
        orphans = (
            df_fact.select(col(fact_col).alias("fk"))
            .distinct()
            .join(
                df_dim.select(col(dim_col).alias("dk")).distinct(),
                col("fk") == col("dk"),
                "left_anti",
            )
            .count()
        )

        total_keys = df_fact.select(fact_col).distinct().count()
        status = "PASS" if orphans == 0 else "FAIL"
        add_result(
            "ref_integrity", f"{fact_table}->{dim_table}", status,
            f"{fact_col}->{dim_col}: {orphans} orphan keys out of {total_keys:,} distinct",
            orphans,
        )
    except Exception as e:
        add_result("ref_integrity", f"{fact_table}->{dim_table}", "FAIL", f"Error: {e}")


def check_value_range(table_name: str, column: str, min_val=None, max_val=None):
    """Validate that numeric values fall within an expected range."""
    try:
        df = spark.table(table_name)
        if column not in df.columns:
            add_result("value_range", table_name, "FAIL", f"Column '{column}' not found")
            return

        stats = df.agg(
            spark_min(col(column)).alias("min_val"),
            spark_max(col(column)).alias("max_val"),
        ).collect()[0]

        actual_min = stats["min_val"]
        actual_max = stats["max_val"]

        issues = []
        if min_val is not None and actual_min is not None and actual_min < min_val:
            issues.append(f"min {actual_min} < expected {min_val}")
        if max_val is not None and actual_max is not None and actual_max > max_val:
            issues.append(f"max {actual_max} > expected {max_val}")

        status = "PASS" if not issues else "FAIL"
        detail = f"{column}: range [{actual_min}, {actual_max}]"
        if issues:
            detail += " | " + "; ".join(issues)
        add_result("value_range", table_name, status, detail, f"[{actual_min}, {actual_max}]")
    except Exception as e:
        add_result("value_range", table_name, "FAIL", f"Error: {e}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run Validation Checks

# COMMAND ----------

print("=" * 70)
print("GOLD LAYER VALIDATION")
print("=" * 70)

# --- Row Count Checks ---
print("\n--- Row Count Checks ---")
gold_tables = [
    "gold_dim_date", "gold_dim_customer", "gold_dim_product",
    "gold_dim_advisor", "gold_dim_policy", "gold_dim_fund",
    "gold_fact_claims", "gold_fact_transactions",
    "gold_fact_investments", "gold_fact_policy_premiums",
]

for t in gold_tables:
    check_row_count(t, min_expected=1)

# COMMAND ----------

# --- Null Checks ---
print("\n--- Null Checks on Critical Columns ---")
check_nulls("gold_dim_customer", ["customer_id", "customer_sk"])
check_nulls("gold_dim_product", ["product_id", "product_sk"])
check_nulls("gold_dim_advisor", ["advisor_id", "advisor_sk"])
check_nulls("gold_dim_policy", ["policy_id", "policy_sk", "customer_id"])
check_nulls("gold_dim_date", ["date_key", "date_sk", "year", "month"])
check_nulls("gold_fact_claims", ["claim_id", "policy_id"])
check_nulls("gold_fact_transactions", ["transaction_id"])
check_nulls("gold_fact_investments", ["investment_id", "customer_id"])
check_nulls("gold_fact_policy_premiums", ["policy_id", "customer_id"])

# COMMAND ----------

# --- Referential Integrity ---
print("\n--- Referential Integrity Checks ---")
check_referential_integrity("gold_fact_claims", "policy_id", "gold_dim_policy", "policy_id")
check_referential_integrity("gold_fact_policy_premiums", "customer_id", "gold_dim_customer", "customer_id")
check_referential_integrity("gold_fact_investments", "customer_id", "gold_dim_customer", "customer_id")

# COMMAND ----------

# --- Value Range Checks ---
print("\n--- Value Range Checks ---")
check_value_range("gold_fact_claims", "claim_amount", min_val=0)
check_value_range("gold_fact_claims", "processing_days", min_val=0, max_val=3650)
check_value_range("gold_fact_policy_premiums", "premium_amount", min_val=0)
check_value_range("gold_fact_policy_premiums", "annualized_premium", min_val=0)
check_value_range("gold_dim_customer", "age", min_val=0, max_val=150)
check_value_range("gold_dim_date", "year", min_val=2020, max_val=2026)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Validation Results Summary

# COMMAND ----------

df_results = spark.createDataFrame([Row(**r) for r in validation_results])
df_results = df_results.withColumn("_validation_timestamp", current_timestamp())

# Write validation results to a delta table
df_results.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("validation_results")

display(df_results)

total_checks = len(validation_results)
passed = sum(1 for r in validation_results if r["status"] == "PASS")
failed = sum(1 for r in validation_results if r["status"] == "FAIL")

print(f"\n{'='*70}")
print(f"VALIDATION SUMMARY: {passed}/{total_checks} passed, {failed}/{total_checks} failed")
print(f"{'='*70}")

if failed > 0:
    print("\nFailed checks:")
    for r in validation_results:
        if r["status"] == "FAIL":
            print(f"  - {r['check_name']} | {r['table_name']} | {r['detail']}")

# COMMAND ----------

# MAGIC %md
# MAGIC ---
# MAGIC # Business Queries
# MAGIC The following queries demonstrate answering key POC business questions
# MAGIC using the Gold layer star schema.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Query 1: Top Customers by Claim Volume

# COMMAND ----------

print("Top 20 Customers by Number of Claims and Total Claim Amount")
try:
    df_top_claimants = (
        spark.table("gold_fact_claims").alias("fc")
        .join(
            spark.table("gold_dim_customer").alias("dc"),
            col("fc.customer_id") == col("dc.customer_id"),
            "inner",
        )
        .groupBy(
            col("dc.customer_id"),
            col("dc.first_name"),
            col("dc.last_name"),
            col("dc.age_band"),
        )
        .agg(
            count("*").alias("claim_count"),
            spark_round(spark_sum("fc.claim_amount"), 2).alias("total_claim_amount"),
            spark_round(avg("fc.claim_amount"), 2).alias("avg_claim_amount"),
            spark_round(avg("fc.processing_days"), 1).alias("avg_processing_days"),
        )
        .orderBy(desc("claim_count"), desc("total_claim_amount"))
        .limit(20)
    )
    display(df_top_claimants)
except Exception as e:
    print(f"Query error: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Query 2: Claims Ratio by Policy Type

# COMMAND ----------

print("Claims Ratio by Policy Type (Claims Amount / Premium Amount)")
try:
    df_claims_agg = (
        spark.table("gold_fact_claims").alias("fc")
        .join(
            spark.table("gold_dim_policy").alias("dp"),
            col("fc.policy_id") == col("dp.policy_id"),
            "inner",
        )
        .groupBy(coalesce(col("dp.policy_type"), lit("Unknown")).alias("policy_type"))
        .agg(
            count("*").alias("claim_count"),
            spark_round(spark_sum("fc.claim_amount"), 2).alias("total_claims"),
        )
    )

    df_premiums_agg = (
        spark.table("gold_fact_policy_premiums").alias("fp")
        .groupBy(coalesce(col("fp.policy_type"), lit("Unknown")).alias("policy_type"))
        .agg(
            count("*").alias("policy_count"),
            spark_round(spark_sum("fp.annualized_premium"), 2).alias("total_premium"),
        )
    )

    df_claims_ratio = (
        df_claims_agg.alias("c")
        .join(df_premiums_agg.alias("p"), col("c.policy_type") == col("p.policy_type"), "full_outer")
        .select(
            coalesce(col("c.policy_type"), col("p.policy_type")).alias("policy_type"),
            col("policy_count"),
            col("claim_count"),
            col("total_premium"),
            col("total_claims"),
            spark_round(
                when(col("total_premium") > 0, col("total_claims") / col("total_premium"))
                .otherwise(lit(None)),
                4,
            ).alias("claims_ratio"),
        )
        .orderBy(desc("claims_ratio"))
    )
    display(df_claims_ratio)
except Exception as e:
    print(f"Query error: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Query 3: Investment Inflows by Region

# COMMAND ----------

print("Investment Inflows by Region")
try:
    # Try to join with customer for region, fall back to investment region column
    df_investments = spark.table("gold_fact_investments").alias("fi")
    df_customers = spark.table("gold_dim_customer").alias("dc")

    region_col = None
    if "region" in df_investments.columns:
        region_col = col("fi.region")
    elif "region" in df_customers.columns:
        region_col = col("dc.region")
    elif "province" in df_customers.columns:
        region_col = col("dc.province")

    if region_col is not None:
        df_inflows = (
            df_investments
            .join(df_customers, col("fi.customer_id") == col("dc.customer_id"), "left")
            .groupBy(region_col.alias("region"))
            .agg(
                count("*").alias("investment_count"),
                countDistinct("fi.customer_id").alias("unique_investors"),
                spark_round(spark_sum("fi.investment_amount"), 2).alias("total_inflows"),
                spark_round(avg("fi.investment_amount"), 2).alias("avg_investment"),
            )
            .orderBy(desc("total_inflows"))
        )
    else:
        # Fallback: aggregate without region
        df_inflows = (
            df_investments
            .agg(
                count("*").alias("investment_count"),
                countDistinct("customer_id").alias("unique_investors"),
                spark_round(spark_sum("investment_amount"), 2).alias("total_inflows"),
                spark_round(avg("investment_amount"), 2).alias("avg_investment"),
            )
        )

    display(df_inflows)
except Exception as e:
    print(f"Query error: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Query 4: Advisor AUM Rankings

# COMMAND ----------

print("Advisor Rankings by Assets Under Management (AUM)")
try:
    df_advisors = spark.table("gold_dim_advisor").alias("da")
    df_investments = spark.table("gold_fact_investments").alias("fi")

    # Determine AUM column (current_value or market_value or investment_amount)
    aum_col = None
    for candidate in ["current_value", "market_value", "investment_amount"]:
        if candidate in df_investments.columns:
            aum_col = candidate
            break

    if "advisor_id" in df_investments.columns and aum_col:
        df_aum = (
            df_investments
            .join(df_advisors, col("fi.advisor_id") == col("da.advisor_id"), "inner")
            .groupBy(
                col("da.advisor_id"),
                *[col(f"da.{c}") for c in df_advisors.columns
                  if c in ["advisor_name", "first_name", "last_name", "region", "branch", "tier"]],
            )
            .agg(
                spark_round(spark_sum(f"fi.{aum_col}"), 2).alias("total_aum"),
                countDistinct("fi.customer_id").alias("client_count"),
                count("*").alias("investment_count"),
                spark_round(avg(f"fi.{aum_col}"), 2).alias("avg_investment_size"),
            )
            .orderBy(desc("total_aum"))
            .limit(20)
        )
        display(df_aum)
    else:
        # Fallback: use policy premiums as a proxy for AUM
        print("  Note: advisor_id not found in investments. Using policy premiums as proxy.")
        df_policies = spark.table("gold_fact_policy_premiums").alias("fp")

        if "advisor_id" in df_policies.columns:
            df_aum = (
                df_policies
                .join(df_advisors, col("fp.advisor_id") == col("da.advisor_id"), "inner")
                .groupBy(
                    col("da.advisor_id"),
                    *[col(f"da.{c}") for c in df_advisors.columns
                      if c in ["advisor_name", "first_name", "last_name", "region", "branch"]],
                )
                .agg(
                    spark_round(spark_sum("fp.annualized_premium"), 2).alias("total_premium_book"),
                    countDistinct("fp.customer_id").alias("client_count"),
                    count("*").alias("policy_count"),
                )
                .orderBy(desc("total_premium_book"))
                .limit(20)
            )
            display(df_aum)
        else:
            print("  Cannot compute advisor rankings: no advisor_id linkage found.")

except Exception as e:
    print(f"Query error: {e}")
    traceback.print_exc()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Final Summary

# COMMAND ----------

print(f"\n{'='*70}")
print("MANULIFE FABRIC POC - VALIDATION & BUSINESS QUERIES COMPLETE")
print(f"{'='*70}")
print(f"\nValidation: {passed}/{total_checks} checks passed")
print(f"Business queries executed: 4")
print(f"\nGold tables available for reporting:")
for t in gold_tables:
    try:
        c = spark.table(t).count()
        print(f"  {t}: {c:,} rows")
    except Exception:
        print(f"  {t}: unavailable")
print(f"\n{'='*70}")
