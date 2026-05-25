"""Build CSVs from the 3 Excel files. Split SKU attributes into dim_sku;
keep 3 fact tables sharing the SKU key. Also generate a small dim_date and
dim_vendor for richer Copilot drilldowns.
"""
from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

SRC = Path(r"C:\Users\anuragdhuria\OneDrive - Microsoft\Desktop\OneDrive_2026-05-25\Demo Data")
OUT = Path(__file__).parent / "csv"
OUT.mkdir(exist_ok=True)

SEED = 20260525
random.seed(SEED)


def read(name):
    return pd.read_excel(SRC / name, sheet_name="Sheet1")


sku_perf = read("Synthetic_SKU_Performance.xlsx")
inseason = read("Synthetic_InSeason_Shipment.xlsx")
conn_inv = read("Synthetic_Connected_Inventory.xlsx")

print(f"sku_perf={len(sku_perf)} rows  inseason={len(inseason)} rows  conn_inv={len(conn_inv)} rows")

# 1. dim_sku - product master from SKU_Performance
dim_sku = sku_perf[[
    "SKU", "SKU_Name", "Category", "Subcategory",
    "Fineline", "Fineline_Name", "Vendor", "Brand",
    "New_SKU_Flag", "Status", "Retail_Price", "Cost", "Store_Count",
]].copy()
dim_sku["Margin_Per_Unit"] = (dim_sku["Retail_Price"] - dim_sku["Cost"]).round(2)
dim_sku.to_csv(OUT / "dim_sku.csv", index=False)
print(f"dim_sku: {len(dim_sku)} rows")

# 2. fact_sku_performance - fact rows minus dim columns
fact_perf_cols = [
    "SKU",
    "TY_POS_Units", "LY_POS_Units",
    "TY_POS_Dollars", "LY_POS_Dollars",
    "TY_RVS", "LY_RVS",
    "TY_EGM_Dollars", "LY_EGM_Dollars",
    "TY_EGM_Pct", "LY_EGM_Pct",
    "QTD_POS_Dollars", "YTD_POS_Dollars", "R12_POS_Dollars",
]
sku_perf[fact_perf_cols].to_csv(OUT / "fact_sku_performance.csv", index=False)
print(f"fact_sku_performance: {len(sku_perf)} rows")

# 3. fact_in_season - keep facts, drop redundant dim attributes
inseason_facts = inseason[[
    "SKU", "Season",
    "YTD_TY_POS", "YTD_LY_POS",
    "YTD_TY_Ship", "YTD_LY_Ship",
    "Retail_Inv_TY", "Corp_Inv_TY",
    "Current_POS_Forecast", "Current_Ship_Forecast",
    "Open_PO_Qty", "Planned_Purchase_Qty",
    "Weeks_of_Supply",
]].copy()
inseason_facts.to_csv(OUT / "fact_in_season.csv", index=False)
print(f"fact_in_season: {len(inseason_facts)} rows")

# 4. fact_connected_inventory
conn_inv_facts = conn_inv[[
    "SKU",
    "Corp_Inv_Units_TY", "Corp_Inv_Units_LY",
    "Retail_Inv_Units_TY", "Retail_Inv_Units_LY",
    "YTD_POS_TY", "YTD_POS_LY", "YTD_POS_Change_Pct",
    "R8_POS_TY", "R8_POS_LY", "R8_POS_Change_Pct",
    "YTD_Lost_Sales_Pct", "Vendor_Fill_Rate_Pct",
    "Ship_Units_TY", "Ship_Units_LY", "DDF_Units",
]].copy()
conn_inv_facts.to_csv(OUT / "fact_connected_inventory.csv", index=False)
print(f"fact_connected_inventory: {len(conn_inv_facts)} rows")

# 5. dim_vendor - vendor enrichment (lead times, scorecard category)
vendors = sorted(dim_sku["Vendor"].dropna().unique())
vendor_rows = []
random.seed(SEED)
for v in vendors:
    vendor_rows.append({
        "Vendor": v,
        "Vendor_Country": random.choice(["Canada", "USA", "Mexico", "China"]),
        "Lead_Time_Weeks": random.randint(4, 12),
        "Scorecard_Tier": random.choice(["Gold", "Silver", "Bronze"]),
        "Onboarding_Year": random.randint(2005, 2024),
        "Sustainability_Index": round(random.uniform(0.45, 0.95), 2),
    })
dim_vendor = pd.DataFrame(vendor_rows)
dim_vendor.to_csv(OUT / "dim_vendor.csv", index=False)
print(f"dim_vendor: {len(dim_vendor)} rows")

# 6. dim_season - tiny lookup for Season values
seasons = sorted(inseason["Season"].dropna().unique())
season_rows = []
for s in seasons:
    season_rows.append({
        "Season_Code": s,
        "Season_Name": s.split(" ", 1)[-1] if " " in s else s,
        "Season_Start": "2026-03-01",
        "Season_End": "2026-05-31",
        "Display_Order": int(s[1]) if s[1].isdigit() else 0,
    })
pd.DataFrame(season_rows).to_csv(OUT / "dim_season.csv", index=False)
print(f"dim_season: {len(season_rows)} rows")

# 7. dim_date - weekly grain spanning LY-TY for trend visuals
dates = pd.date_range("2024-01-07", "2026-05-25", freq="W-SUN")
dim_date = pd.DataFrame({
    "Week_End_Date": dates.strftime("%Y-%m-%d"),
    "Year": dates.year,
    "Quarter": "Q" + ((dates.month - 1) // 3 + 1).astype(str),
    "Year_Quarter": dates.year.astype(str) + "-Q" + ((dates.month - 1) // 3 + 1).astype(str),
    "Year_Month": dates.strftime("%Y-%m"),
    "Week_Number": dates.isocalendar().week,
    "Fiscal_Year_Label": "FY" + dates.year.astype(str).str[-2:],
})
dim_date.to_csv(OUT / "dim_date.csv", index=False)
print(f"dim_date: {len(dim_date)} rows")

print(f"\nAll CSVs in: {OUT}")
