"""Pull the Data Dictionary sheet from each Excel and dump as JSON
for use as TMDL column/measure descriptions (boosts Copilot quality)."""
import json
from pathlib import Path
import pandas as pd

SRC = Path(r"C:\Users\anuragdhuria\OneDrive - Microsoft\Desktop\OneDrive_2026-05-25\Demo Data")
OUT = Path(__file__).parent / "data_dict.json"

mapping = {}
for f in ["Synthetic_SKU_Performance.xlsx",
          "Synthetic_InSeason_Shipment.xlsx",
          "Synthetic_Connected_Inventory.xlsx"]:
    df = pd.read_excel(SRC / f, sheet_name="Data Dictionary")
    for _, row in df.iterrows():
        var = str(row["Variable"]).strip()
        acro = str(row["Acronym / Full Name"]).strip()
        desc = str(row["Description"]).strip()
        if var and var != "nan":
            mapping[var] = {"full_name": acro, "description": desc}

OUT.write_text(json.dumps(mapping, indent=2))
print(f"Wrote {len(mapping)} entries to {OUT}")
for k, v in list(mapping.items())[:8]:
    print(f"  {k}: {v['full_name']} - {v['description'][:60]}")
