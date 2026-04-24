"""
Manulife Fabric POC — Data Quality Test Suite
==============================================

Automated tests to validate the quality and integrity of data
across Bronze, Silver, and Gold layers in the Fabric Lakehouse.

Usage in Fabric Notebook:
    %run tests/data_quality_tests

Usage locally (with PySpark):
    python tests/data_quality_tests.py

Note: When running in Fabric, replace local SparkSession creation
with the built-in `spark` session.
"""


# ---------------------------------------------------------------------------
# Test Framework
# ---------------------------------------------------------------------------
class DataQualityTestResult:
    """Stores the result of a single data quality test."""

    def __init__(self, test_name: str, layer: str, table: str,
                 passed: bool, message: str, details: str = ""):
        self.test_name = test_name
        self.layer = layer
        self.table = table
        self.passed = passed
        self.message = message
        self.details = details

    def __repr__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.layer}.{self.table} — {self.test_name}: {self.message}"


class DataQualityTestSuite:
    """Runs and collects data quality tests."""

    def __init__(self, spark):
        self.spark = spark
        self.results: list[DataQualityTestResult] = []

    def add_result(self, result: DataQualityTestResult):
        self.results.append(result)
        print(result)

    def summary(self):
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        print("\n" + "=" * 60)
        print(f"  DATA QUALITY TEST SUMMARY")
        print(f"  Total: {total}  |  Passed: {passed}  |  Failed: {failed}")
        print("=" * 60)
        if failed > 0:
            print("\nFailed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r}")
                    if r.details:
                        print(f"    Details: {r.details}")
        print()
        return passed, failed

    # -----------------------------------------------------------------------
    # Generic test methods
    # -----------------------------------------------------------------------
    def test_table_exists(self, layer: str, table: str):
        """Check that a delta table exists and has rows."""
        try:
            df = self.spark.read.format("delta").table(f"{layer}.{table}")
            count = df.count()
            self.add_result(DataQualityTestResult(
                "table_exists", layer, table,
                passed=count > 0,
                message=f"Row count: {count}"
            ))
            return count
        except Exception as e:
            self.add_result(DataQualityTestResult(
                "table_exists", layer, table,
                passed=False,
                message=f"Table not found or unreadable",
                details=str(e)[:200]
            ))
            return 0

    def test_no_nulls(self, layer: str, table: str, columns: list[str]):
        """Check that specified columns have no null values."""
        try:
            df = self.spark.read.format("delta").table(f"{layer}.{table}")
            for col in columns:
                null_count = df.filter(f"{col} IS NULL").count()
                self.add_result(DataQualityTestResult(
                    f"no_nulls({col})", layer, table,
                    passed=null_count == 0,
                    message=f"Null count: {null_count}"
                ))
        except Exception as e:
            self.add_result(DataQualityTestResult(
                "no_nulls", layer, table,
                passed=False,
                message="Could not read table",
                details=str(e)[:200]
            ))

    def test_unique(self, layer: str, table: str, column: str):
        """Check that a column has all unique values (primary key check)."""
        try:
            df = self.spark.read.format("delta").table(f"{layer}.{table}")
            total = df.count()
            distinct = df.select(column).distinct().count()
            self.add_result(DataQualityTestResult(
                f"unique({column})", layer, table,
                passed=total == distinct,
                message=f"Total: {total}, Distinct: {distinct}"
            ))
        except Exception as e:
            self.add_result(DataQualityTestResult(
                f"unique({column})", layer, table,
                passed=False,
                message="Could not read table",
                details=str(e)[:200]
            ))

    def test_referential_integrity(self, layer: str,
                                    child_table: str, child_column: str,
                                    parent_table: str, parent_column: str):
        """Check that all values in child column exist in parent column."""
        try:
            child_df = self.spark.read.format("delta").table(f"{layer}.{child_table}")
            parent_df = self.spark.read.format("delta").table(f"{layer}.{parent_table}")

            child_keys = child_df.select(child_column).distinct()
            parent_keys = parent_df.select(parent_column).distinct()

            orphans = child_keys.subtract(parent_keys).count()
            self.add_result(DataQualityTestResult(
                f"ref_integrity({child_table}.{child_column} → {parent_table}.{parent_column})",
                layer, child_table,
                passed=orphans == 0,
                message=f"Orphan records: {orphans}"
            ))
        except Exception as e:
            self.add_result(DataQualityTestResult(
                f"ref_integrity", layer, child_table,
                passed=False,
                message="Could not validate referential integrity",
                details=str(e)[:200]
            ))

    def test_value_range(self, layer: str, table: str, column: str,
                          min_val=None, max_val=None):
        """Check that numeric column values fall within expected range."""
        try:
            df = self.spark.read.format("delta").table(f"{layer}.{table}")
            from pyspark.sql.functions import min as spark_min, max as spark_max
            stats = df.agg(
                spark_min(column).alias("min_val"),
                spark_max(column).alias("max_val")
            ).collect()[0]

            actual_min = stats["min_val"]
            actual_max = stats["max_val"]

            passed = True
            if min_val is not None and actual_min is not None and actual_min < min_val:
                passed = False
            if max_val is not None and actual_max is not None and actual_max > max_val:
                passed = False

            self.add_result(DataQualityTestResult(
                f"value_range({column})", layer, table,
                passed=passed,
                message=f"Range: [{actual_min}, {actual_max}], Expected: [{min_val}, {max_val}]"
            ))
        except Exception as e:
            self.add_result(DataQualityTestResult(
                f"value_range({column})", layer, table,
                passed=False,
                message="Could not validate range",
                details=str(e)[:200]
            ))

    def test_allowed_values(self, layer: str, table: str, column: str,
                             allowed: list[str]):
        """Check that a column contains only allowed categorical values."""
        try:
            df = self.spark.read.format("delta").table(f"{layer}.{table}")
            actual_values = [row[0] for row in df.select(column).distinct().collect()]
            invalid = [v for v in actual_values if v not in allowed and v is not None]

            self.add_result(DataQualityTestResult(
                f"allowed_values({column})", layer, table,
                passed=len(invalid) == 0,
                message=f"Invalid values: {invalid}" if invalid else "All values valid"
            ))
        except Exception as e:
            self.add_result(DataQualityTestResult(
                f"allowed_values({column})", layer, table,
                passed=False,
                message="Could not validate allowed values",
                details=str(e)[:200]
            ))

    def test_row_count_range(self, layer: str, table: str,
                              min_rows: int, max_rows: int):
        """Check that table row count is within expected range."""
        try:
            df = self.spark.read.format("delta").table(f"{layer}.{table}")
            count = df.count()
            self.add_result(DataQualityTestResult(
                "row_count_range", layer, table,
                passed=min_rows <= count <= max_rows,
                message=f"Count: {count}, Expected: [{min_rows}, {max_rows}]"
            ))
        except Exception as e:
            self.add_result(DataQualityTestResult(
                "row_count_range", layer, table,
                passed=False,
                message="Could not count rows",
                details=str(e)[:200]
            ))


# ---------------------------------------------------------------------------
# POC-Specific Test Definitions
# ---------------------------------------------------------------------------
def run_bronze_tests(suite: DataQualityTestSuite):
    """Tests for Bronze layer tables."""
    print("\n--- Bronze Layer Tests ---")
    bronze_tables = [
        "customers", "policies", "claims", "products",
        "investments", "advisors", "transactions"
    ]
    for table in bronze_tables:
        suite.test_table_exists("bronze", table)


def run_silver_tests(suite: DataQualityTestSuite):
    """Tests for Silver layer tables."""
    print("\n--- Silver Layer Tests ---")
    silver_tables = [
        "customers", "policies", "claims", "products",
        "investments", "advisors", "transactions"
    ]
    for table in silver_tables:
        suite.test_table_exists("silver", table)

    # Null checks on critical columns
    suite.test_no_nulls("silver", "customers",
                        ["customer_id", "first_name", "last_name", "province"])
    suite.test_no_nulls("silver", "policies",
                        ["policy_id", "customer_id", "product_id", "policy_type", "status"])
    suite.test_no_nulls("silver", "claims",
                        ["claim_id", "policy_id", "customer_id", "claim_amount", "status"])
    suite.test_no_nulls("silver", "advisors",
                        ["advisor_id", "first_name", "last_name", "region"])

    # Uniqueness checks
    suite.test_unique("silver", "customers", "customer_id")
    suite.test_unique("silver", "policies", "policy_id")
    suite.test_unique("silver", "claims", "claim_id")
    suite.test_unique("silver", "advisors", "advisor_id")
    suite.test_unique("silver", "products", "product_id")

    # Allowed values
    suite.test_allowed_values("silver", "policies", "policy_type",
                              ["Life", "Health", "Auto", "Home", "Travel", "Disability"])
    suite.test_allowed_values("silver", "policies", "status",
                              ["Active", "Lapsed", "Cancelled", "Matured"])
    suite.test_allowed_values("silver", "claims", "status",
                              ["Submitted", "Under Review", "Approved", "Denied", "Paid", "Closed"])
    suite.test_allowed_values("silver", "customers", "customer_segment",
                              ["Retail", "High Net Worth", "Institutional"])

    # Value ranges
    suite.test_value_range("silver", "policies", "premium_amount", min_val=0)
    suite.test_value_range("silver", "policies", "coverage_amount", min_val=0)
    suite.test_value_range("silver", "claims", "claim_amount", min_val=0)
    suite.test_value_range("silver", "investments", "investment_amount", min_val=0)


def run_gold_tests(suite: DataQualityTestSuite):
    """Tests for Gold layer tables (star schema)."""
    print("\n--- Gold Layer Tests ---")

    # Dimension tables
    dims = ["dim_customer", "dim_product", "dim_advisor", "dim_date", "dim_policy", "dim_fund"]
    for dim in dims:
        suite.test_table_exists("gold", dim)

    # Fact tables
    facts = ["fact_claims", "fact_transactions", "fact_investments", "fact_policy_premiums"]
    for fact in facts:
        suite.test_table_exists("gold", fact)

    # Surrogate key uniqueness
    suite.test_unique("gold", "dim_customer", "customer_key")
    suite.test_unique("gold", "dim_product", "product_key")
    suite.test_unique("gold", "dim_advisor", "advisor_key")
    suite.test_unique("gold", "dim_date", "date_key")
    suite.test_unique("gold", "dim_policy", "policy_key")

    # Referential integrity: facts → dimensions
    suite.test_referential_integrity("gold",
        "fact_claims", "customer_key", "dim_customer", "customer_key")
    suite.test_referential_integrity("gold",
        "fact_claims", "policy_key", "dim_policy", "policy_key")
    suite.test_referential_integrity("gold",
        "fact_claims", "product_key", "dim_product", "product_key")
    suite.test_referential_integrity("gold",
        "fact_transactions", "customer_key", "dim_customer", "customer_key")
    suite.test_referential_integrity("gold",
        "fact_investments", "customer_key", "dim_customer", "customer_key")
    suite.test_referential_integrity("gold",
        "fact_investments", "advisor_key", "dim_advisor", "advisor_key")
    suite.test_referential_integrity("gold",
        "fact_policy_premiums", "product_key", "dim_product", "product_key")

    # Row count sanity checks
    suite.test_row_count_range("gold", "dim_customer", 150, 250)
    suite.test_row_count_range("gold", "dim_product", 20, 40)
    suite.test_row_count_range("gold", "dim_advisor", 20, 50)
    suite.test_row_count_range("gold", "dim_date", 2000, 3000)
    suite.test_row_count_range("gold", "fact_claims", 200, 500)
    suite.test_row_count_range("gold", "fact_transactions", 500, 1200)
    suite.test_row_count_range("gold", "fact_investments", 200, 500)


def run_document_tests(suite: DataQualityTestSuite):
    """Tests for document chunking output."""
    print("\n--- Document Chunks Tests ---")
    suite.test_table_exists("gold", "document_chunks")
    suite.test_no_nulls("gold", "document_chunks",
                        ["chunk_id", "document_name", "chunk_text"])
    suite.test_unique("gold", "document_chunks", "chunk_id")
    suite.test_value_range("gold", "document_chunks", "token_count",
                           min_val=1, max_val=600)


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------
def run_all_tests(spark):
    """Run the complete data quality test suite."""
    suite = DataQualityTestSuite(spark)

    run_bronze_tests(suite)
    run_silver_tests(suite)
    run_gold_tests(suite)
    run_document_tests(suite)

    passed, failed = suite.summary()
    return suite


# When running in a Fabric notebook, uncomment the line below:
# suite = run_all_tests(spark)

# When running locally with PySpark:
if __name__ == "__main__":
    from pyspark.sql import SparkSession
    spark = SparkSession.builder \
        .appName("ManulifePOC_DataQuality") \
        .getOrCreate()
    suite = run_all_tests(spark)
    spark.stop()
