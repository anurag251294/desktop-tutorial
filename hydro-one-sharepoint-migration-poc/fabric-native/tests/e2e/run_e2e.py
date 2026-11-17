"""Run the real migration notebook in Fabric against a simulated SharePoint.

Builds a notebook from fake_graph.py + the cells of Migrate_SharePoint_Content/notebook.py
(minus its entry-point cell) + driver.py, deploys it to the workspace with a Lakehouse, runs
it as a Fabric notebook job and prints the checks it wrote to Files/_e2e/results.json.

    python run_e2e.py <workspace-id> [path-to-notebook.py]

The notebook defaults to this repo's notebooks/Migrate_SharePoint_Content/notebook.py.

Needs `az login` with Contributor on the workspace.
"""
import base64, json, re, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = "https://api.fabric.microsoft.com/v1"
WS = sys.argv[1]
NOTEBOOK_PY = (Path(sys.argv[2]) if len(sys.argv) > 2 else
               HERE.parents[1] / "notebooks" / "Migrate_SharePoint_Content" / "notebook.py")
LAKEHOUSE, NB_NAME = "HydroOneE2E", "E2E_Migrate_Harness"


def token(resource):
    return subprocess.run(["az", "account", "get-access-token", "--resource", resource, "--query", "accessToken",
                           "-o", "tsv"], capture_output=True, text=True, check=True, shell=True).stdout.strip()


def call(method, url, body=None, resource="https://api.fabric.microsoft.com", raw=False):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token(resource)}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            data = r.read()
            return r.status, dict(r.headers), (data if raw else (json.loads(data) if data else None))
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode(errors="replace")


def wait_op(status, headers):
    if status != 202:
        return
    url = headers.get("Location") or headers.get("Operation-Location")
    while url:
        time.sleep(int(headers.get("Retry-After", 3)))
        status, headers, body = call("GET", url)
        if isinstance(body, dict) and body.get("status") in ("Succeeded", "Failed"):
            if body["status"] == "Failed":
                raise SystemExit(f"operation failed: {body}")
            return


def items(kind):
    return {i["displayName"]: i["id"] for i in call("GET", f"{API}/workspaces/{WS}/items?type={kind}")[2]["value"]}


# --- Lakehouse
lh = items("Lakehouse").get(LAKEHOUSE)
if not lh:
    wait_op(*call("POST", f"{API}/workspaces/{WS}/items", {"displayName": LAKEHOUSE, "type": "Lakehouse"})[:2])
    for _ in range(20):
        lh = items("Lakehouse").get(LAKEHOUSE)
        if lh:
            break
        time.sleep(3)
print("lakehouse", lh)

# --- Notebook: fake Graph + the real notebook's cells + the driver
src = NOTEBOOK_PY.read_text(encoding="utf-8")
cells = re.split(r"(?m)^# CELL .*$", src)[1:]
assert cells[-1].lstrip().startswith("# Entry point"), "expected the entry-point cell last"
cells = cells[:-1]
driver = (HERE / "driver.py").read_text(encoding="utf-8").replace("__WORKSPACE_ID__", WS).replace("__LAKEHOUSE_ID__", lh)
sources = [(HERE / "fake_graph.py").read_text(encoding="utf-8")] + cells + [driver]


def cell(text):
    lines = text.strip("\r\n").replace("\r\n", "\n").split("\n")
    return {"cell_type": "code", "metadata": {}, "outputs": [], "execution_count": None,
            "source": [l + "\n" for l in lines[:-1]] + [lines[-1]]}


nb = {"cells": [cell(s) for s in sources], "nbformat": 4, "nbformat_minor": 5,
      "metadata": {"language_info": {"name": "python"},
                   "kernelspec": {"name": "synapse_pyspark", "display_name": "Synapse PySpark"},
                   "dependencies": {"lakehouse": {"default_lakehouse": lh, "default_lakehouse_name": LAKEHOUSE,
                                                  "default_lakehouse_workspace_id": WS,
                                                  "known_lakehouses": [{"id": lh}]}}}}
definition = {"format": "ipynb", "parts": [{"path": "notebook-content.ipynb", "payloadType": "InlineBase64",
                                            "payload": base64.b64encode(json.dumps(nb).encode()).decode()}]}
nb_id = items("Notebook").get(NB_NAME)
if nb_id:
    wait_op(*call("POST", f"{API}/workspaces/{WS}/items/{nb_id}/updateDefinition", {"definition": definition})[:2])
else:
    wait_op(*call("POST", f"{API}/workspaces/{WS}/items", {"displayName": NB_NAME, "type": "Notebook",
                                                          "definition": definition})[:2])
    for _ in range(20):
        nb_id = items("Notebook").get(NB_NAME)
        if nb_id:
            break
        time.sleep(3)
print("notebook", nb_id, f"({len(sources)} cells)")

# --- Clear earlier results and state, so every run starts from an empty Lakehouse
for path in ("Files/_e2e", "Files/sites_E2E", "Tables/migration_audit", "Tables/migration_watermark",
             "Tables/sharepoint_inventory"):
    call("DELETE", f"https://onelake.dfs.fabric.microsoft.com/{WS}/{lh}/{path}?recursive=true",
         resource="https://storage.azure.com")

# --- Run it
status, headers, body = call("POST", f"{API}/workspaces/{WS}/items/{nb_id}/jobs/instances?jobType=RunNotebook", {})
job = headers["Location"]
print("job", job)
while True:
    time.sleep(20)
    s = call("GET", job)[2]
    print(time.strftime("%H:%M:%S"), s.get("status"))
    if s.get("status") in ("Completed", "Failed", "Cancelled", "Deduped"):
        if s.get("failureReason"):
            print(json.dumps(s["failureReason"])[:3000])
        break

status, _, data = call("GET", f"https://onelake.dfs.fabric.microsoft.com/{WS}/{lh}/Files/_e2e/results.json",
                       resource="https://storage.azure.com", raw=True)
if status != 200:
    raise SystemExit(f"no results.json (HTTP {status}): {data}")
res = json.loads(data)
for r in res["results"]:
    print(("PASS" if r["ok"] else "FAIL"), f"[{r['scenario']}]", r["check"], "" if r["ok"] else f"\n      {r['detail']}")
print(f"\n{res['passed']} passed, {res['failed']} failed")
sys.exit(1 if res["failed"] else 0)
