"""Upload Interac HR CSVs to the InteracHR_Lakehouse OneLake Files area.

Uses the OneLake DFS API (ADLS Gen2 compatible) to PATCH each CSV in 3 steps:
create -> append -> flush. After upload, the user can either:
  (a) Open the lakehouse in Fabric portal and right-click each CSV ->
      "Load to tables" to convert to Delta, OR
  (b) Run the load_csvs_to_delta.ipynb notebook in this workspace.
"""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

WORKSPACE_ID = "2690ef29-1370-476c-b28c-58a505fea2bd"      # InteracHRDemo
LAKEHOUSE_ID = "454b4c50-e93e-4ce6-9c17-1d03a6ed9d6a"      # InteracHR_Lakehouse
AZ = r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"

DATA_DIR = Path(__file__).parent / "data"
TARGET_FOLDER = "csv"  # under Files/

ONELAKE = "https://onelake.dfs.fabric.microsoft.com"


def token() -> str:
    return subprocess.check_output(
        [AZ, "account", "get-access-token",
         "--resource", "https://storage.azure.com",
         "--query", "accessToken", "-o", "tsv"]
    ).decode().strip()


def call(method: str, url: str, headers: dict, data: bytes | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers, method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def upload(local_path: Path, remote_name: str):
    tok = token()
    base = f"{ONELAKE}/{WORKSPACE_ID}/{LAKEHOUSE_ID}/Files/{TARGET_FOLDER}/{remote_name}"
    auth = {"Authorization": f"Bearer {tok}"}
    data = local_path.read_bytes()
    size = len(data)

    # 1. Create (resource=file). Use PUT with x-ms-resource-type / DFS-style PUT
    s, b = call("PUT", base + "?resource=file", auth)
    if s not in (200, 201):
        print(f"  CREATE failed {s}: {b[:200]}")
        return False

    # 2. Append - single shot since files are small
    h = dict(auth)
    h["Content-Length"] = str(size)
    s, b = call("PATCH", base + "?action=append&position=0", h, data)
    if s not in (200, 202):
        print(f"  APPEND failed {s}: {b[:200]}")
        return False

    # 3. Flush
    s, b = call("PATCH", base + f"?action=flush&position={size}", auth)
    if s not in (200, 201):
        print(f"  FLUSH failed {s}: {b[:200]}")
        return False
    return True


def main():
    files = sorted(DATA_DIR.glob("*.csv"))
    if not files:
        print(f"No CSVs found in {DATA_DIR}")
        sys.exit(1)
    print(f"Uploading {len(files)} CSVs to "
          f"abfss://InteracHRDemo@onelake.dfs.fabric.microsoft.com/"
          f"InteracHR_Lakehouse.Lakehouse/Files/{TARGET_FOLDER}/\n")
    for fp in files:
        size_kb = fp.stat().st_size / 1024
        print(f"  {fp.name}  ({size_kb:,.1f} KB)", end="  ")
        ok = upload(fp, fp.name)
        print("OK" if ok else "FAIL")
    print("\nDone. Next: open the lakehouse in Fabric portal, navigate to "
          "Files/csv/, right-click each file -> Load to tables -> New table, "
          "OR run the load_csvs_to_delta notebook.")


if __name__ == "__main__":
    main()
