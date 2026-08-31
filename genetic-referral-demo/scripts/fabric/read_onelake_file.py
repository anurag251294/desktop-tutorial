"""Download a file from a lakehouse's Files/ area.

    python scripts/fabric/read_onelake_file.py --output cicd/fabric-setup.output.json \
        --lakehouse gold_lakehouse --path Files/report/numbers.json

OneLake speaks the ADLS Gen2 DFS API, so this is a plain GET against
onelake.dfs.fabric.microsoft.com -- but the token has to be issued for
`https://storage.azure.com`, not for the Fabric API. A Fabric-audience token here
returns 401 with no body, which reads like a permissions problem and is not one.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

ONELAKE = "https://onelake.dfs.fabric.microsoft.com"


def token(resource="https://storage.azure.com"):
    out = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=(sys.platform == "win32"))
    if out.returncode:
        sys.exit(f"az account get-access-token failed: {out.stderr.strip()}")
    return out.stdout.strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", required=True)
    ap.add_argument("--lakehouse", required=True)
    ap.add_argument("--path", required=True, help="e.g. Files/report/numbers.json")
    ap.add_argument("--save", help="local destination; prints to stdout if omitted")
    args = ap.parse_args()

    setup = json.loads(Path(args.output).read_text(encoding="utf-8"))
    workspace = setup["workspace"]["id"]
    lakehouses = {l["displayName"]: l["id"] for l in setup["lakehouses"]}
    if args.lakehouse not in lakehouses:
        sys.exit(f"unknown lakehouse {args.lakehouse}; have {sorted(lakehouses)}")

    url = f"{ONELAKE}/{workspace}/{lakehouses[args.lakehouse]}/{args.path.lstrip('/')}"
    response = requests.get(url, headers={"Authorization": f"Bearer {token()}"},
                            timeout=120)
    if response.status_code != 200:
        sys.exit(f"{response.status_code} {url}\n{response.text[:400]}")

    if args.save:
        Path(args.save).write_bytes(response.content)
        print(f"{url}\n  -> {args.save}  ({len(response.content):,} bytes)")
    else:
        sys.stdout.write(response.text)


if __name__ == "__main__":
    main()
