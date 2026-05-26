"""Inspect the 3 CTC sample Excel files - sheet names, columns, dtypes, head."""
from pathlib import Path
import pandas as pd

SRC = Path(r"C:\Users\anuragdhuria\OneDrive - Microsoft\Desktop\OneDrive_2026-05-25\Demo Data")
FILES = [
    "Synthetic_SKU_Performance.xlsx",
    "Synthetic_InSeason_Shipment.xlsx",
    "Synthetic_Connected_Inventory.xlsx",
]

for f in FILES:
    p = SRC / f
    print("=" * 80)
    print(f"FILE: {f}")
    print("=" * 80)
    xl = pd.ExcelFile(p)
    for sh in xl.sheet_names:
        df = xl.parse(sh)
        print(f"\n  Sheet: '{sh}'  rows={len(df)}  cols={len(df.columns)}")
        print(f"  Columns: {list(df.columns)}")
        print(f"  Dtypes:")
        for c, t in df.dtypes.items():
            print(f"    {c!s:40s} {t}")
        print(f"  Head:")
        print(df.head(3).to_string(index=False, max_colwidth=30))
