# Fabric notebook source
# This is a PySpark notebook for Microsoft Fabric Lakehouse
# Import into a Fabric workspace and attach to a Lakehouse to run

# METADATA ********************
# META {
# META   "kernel_info": { "name": "synapse_pyspark" },
# META   "dependencies": { "lakehouse": { "default_lakehouse_name": "SalesLakehouse" } }
# META }

# CELL ********************
# Cell 1: Generate Sample Sales Data
# ===================================
import random
from datetime import datetime, timedelta
from pyspark.sql import Row
from pyspark.sql.types import *

print("🏪 Generating sample sales data for Fabric demo...")

# Product catalog
products = [
    ("Laptop Pro 15", "Electronics", 1299.99),
    ("Wireless Mouse", "Electronics", 29.99),
    ("USB-C Hub", "Electronics", 49.99),
    ("Standing Desk", "Furniture", 599.99),
    ("Ergonomic Chair", "Furniture", 449.99),
    ("Monitor 27inch", "Electronics", 399.99),
    ("Keyboard Mechanical", "Electronics", 89.99),
    ("Desk Lamp LED", "Furniture", 34.99),
    ("Webcam HD", "Electronics", 79.99),
    ("Notebook Pack", "Office Supplies", 12.99),
    ("Pen Set Premium", "Office Supplies", 24.99),
    ("Whiteboard 4x3", "Office Supplies", 89.99),
]

regions = ["Canada East", "Canada West", "US Northeast", "US Southeast", "US West"]
channels = ["Online", "Retail", "Partner"]

# Generate 5000 transactions over the past 90 days
random.seed(42)
base_date = datetime(2026, 3, 1)
rows = []

for i in range(5000):
    product_name, category, base_price = random.choice(products)
    region = random.choice(regions)
    channel = random.choice(channels)
    quantity = random.randint(1, 10)
    discount = random.choice([0, 0, 0, 0.05, 0.1, 0.15, 0.2])
    unit_price = round(base_price * (1 - discount), 2)
    total = round(unit_price * quantity, 2)
    order_date = base_date - timedelta(days=random.randint(0, 90))

    rows.append(Row(
        order_id=f"ORD-{10000 + i}",
        order_date=order_date.strftime("%Y-%m-%d"),
        product_name=product_name,
        category=category,
        region=region,
        channel=channel,
        quantity=quantity,
        unit_price=float(unit_price),
        discount=float(discount),
        total_amount=float(total),
    ))

df_sales = spark.createDataFrame(rows)
df_sales.write.mode("overwrite").format("delta").saveAsTable("SalesLakehouse.sales_transactions")
print(f"✅ Written {df_sales.count()} sales transactions to Delta table")
df_sales.show(10)

# CELL ********************
# Cell 2: Sales Summary by Category
# ===================================
from pyspark.sql.functions import sum, avg, count, round as spark_round

print("📊 Sales Summary by Category")
print("=" * 50)

df_sales = spark.sql("SELECT * FROM SalesLakehouse.sales_transactions")

summary = df_sales.groupBy("category").agg(
    count("order_id").alias("total_orders"),
    spark_round(sum("total_amount"), 2).alias("total_revenue"),
    spark_round(avg("total_amount"), 2).alias("avg_order_value"),
    sum("quantity").alias("units_sold"),
)
summary.orderBy("total_revenue", ascending=False).show()

# CELL ********************
# Cell 3: Regional Performance
# ===================================
from pyspark.sql.functions import desc

print("🌎 Revenue by Region")
print("=" * 50)

regional = df_sales.groupBy("region").agg(
    spark_round(sum("total_amount"), 2).alias("revenue"),
    count("order_id").alias("orders"),
).orderBy(desc("revenue"))

regional.show()

# CELL ********************
# Cell 4: Channel Mix Analysis
# ===================================
print("📱 Channel Mix")
print("=" * 50)

channel_mix = df_sales.groupBy("channel", "category").agg(
    spark_round(sum("total_amount"), 2).alias("revenue"),
    count("order_id").alias("orders"),
).orderBy("channel", desc("revenue"))

channel_mix.show(20)

# CELL ********************
# Cell 5: Top Products by Revenue
# ===================================
print("🏆 Top 10 Products by Revenue")
print("=" * 50)

top_products = df_sales.groupBy("product_name", "category").agg(
    spark_round(sum("total_amount"), 2).alias("total_revenue"),
    sum("quantity").alias("units_sold"),
    spark_round(avg("discount") * 100, 1).alias("avg_discount_pct"),
).orderBy(desc("total_revenue")).limit(10)

top_products.show(truncate=False)

# CELL ********************
# Cell 6: Daily Revenue Trend (for charting)
# ===================================
from pyspark.sql.functions import col

print("📈 Daily Revenue Trend (last 90 days)")
print("=" * 50)

daily_trend = df_sales.groupBy("order_date").agg(
    spark_round(sum("total_amount"), 2).alias("daily_revenue"),
    count("order_id").alias("daily_orders"),
).orderBy("order_date")

# Save as a table for Power BI / charting
daily_trend.write.mode("overwrite").format("delta").saveAsTable("SalesLakehouse.daily_revenue_trend")
print(f"✅ Daily trend saved ({daily_trend.count()} days)")
daily_trend.show(10)

# CELL ********************
# Cell 7: Discount Impact Analysis
# ===================================
from pyspark.sql.functions import when

print("💰 Discount Impact Analysis")
print("=" * 50)

discount_analysis = df_sales.withColumn(
    "discount_tier",
    when(col("discount") == 0, "No Discount")
    .when(col("discount") <= 0.1, "5-10%")
    .otherwise("15-20%")
).groupBy("discount_tier").agg(
    count("order_id").alias("orders"),
    spark_round(sum("total_amount"), 2).alias("revenue"),
    spark_round(avg("quantity"), 1).alias("avg_qty_per_order"),
).orderBy("discount_tier")

discount_analysis.show()

print("")
print("🎉 Fabric Demo Complete!")
print("=" * 50)
print("Tables created in SalesLakehouse:")
print("  • sales_transactions  (5,000 rows)")
print("  • daily_revenue_trend (90 days)")
print("")
print("Next: Open Power BI in this workspace to build")
print("dashboards on top of these Delta tables!")
