"""Provision the referral demo into a Fabric workspace via the Fabric REST API.

Python equivalent of setup_fabric_demo.ps1, which requires PowerShell 7 for
-ResponseHeadersVariable. This runs anywhere Python and the Azure CLI are available.

    az login
    python scripts/fabric/provision_fabric_demo.py \
        --config cicd/fabric-setup.config.demo.json \
        --output cicd/fabric-setup.output.demo.json

Idempotent: existing workspaces, lakehouses, notebooks, and pipelines are updated in
place rather than duplicated.
"""
import argparse
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE = "https://api.fabric.microsoft.com/v1"


def get_token(resource="https://api.fabric.microsoft.com"):
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource,
         "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, shell=(sys.platform == "win32"),
    )
    if result.returncode != 0:
        raise SystemExit(f"az account get-access-token failed:\n{result.stderr}")
    return result.stdout.strip()


class Fabric:
    def __init__(self, token):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def request(self, method, path, **kwargs):
        url = path if path.startswith("http") else f"{BASE}{path}"
        # The Fabric endpoint intermittently resets connections mid-provision. Without
        # a retry, provisioning stops partway and later notebooks silently keep their
        # previous definition -- which looks exactly like "my fix didn't work".
        last_error = None
        for attempt in range(4):
            try:
                response = self.session.request(method, url, timeout=180, **kwargs)
                break
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as error:
                last_error = error
                wait = 2 ** attempt
                print(f"  transient {type(error).__name__} on {method} {url.split('/')[-1]}; "
                      f"retry {attempt + 1}/3 in {wait}s")
                time.sleep(wait)
        else:
            raise RuntimeError(f"{method} {url} failed after 4 attempts: {last_error}")
        if response.status_code == 202:
            return self._poll(response)
        if not response.ok:
            raise RuntimeError(f"{method} {url} -> {response.status_code}\n{response.text[:900]}")
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    def _poll(self, response, timeout=900):
        """Follow a long-running operation to completion."""
        location = response.headers.get("Location")
        if not location:
            return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(int(response.headers.get("Retry-After", 5)))
            status = self.session.get(location, timeout=120)
            if not status.ok:
                raise RuntimeError(f"LRO poll failed: {status.status_code}\n{status.text[:500]}")
            body = status.json() if status.content else {}
            state = body.get("status")
            if state in ("Succeeded", "Completed"):
                result = self.session.get(location.rstrip("/") + "/result", timeout=120)
                if result.ok and result.content:
                    try:
                        return result.json()
                    except ValueError:
                        return body
                return body
            if state in ("Failed", "Cancelled"):
                raise RuntimeError(f"Long-running operation {state}: {json.dumps(body)[:600]}")
        raise TimeoutError("Long-running operation did not complete in time")

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body):
        return self.request("POST", path, data=json.dumps(body))

    def list_all(self, path, key="value"):
        items, url = [], path
        while url:
            page = self.get(url)
            items.extend(page.get(key, []))
            token = page.get("continuationToken")
            url = f"{path}?continuationToken={token}" if token else None
        return items


def inline_part(path, content_bytes):
    return {
        "path": path,
        "payload": base64.b64encode(content_bytes).decode("ascii"),
        "payloadType": "InlineBase64",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--capacity-id", default="")
    parser.add_argument("--skip-environment", action="store_true",
                        help="Reuse the already-published environment instead of "
                             "republishing it. Use for notebook-only changes.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    fabric = Fabric(get_token())

    # ---------------------------------------------------------------- capacity
    capacity_id = args.capacity_id or config.get("capacityId") or ""
    if not capacity_id:
        active = [c for c in fabric.list_all("/capacities")
                  if str(c.get("state", "")).lower() == "active"]
        if not active:
            raise SystemExit("No active Fabric capacity found. Resume one and retry.")
        capacity_id = active[0]["id"]
        print(f"Auto-detected capacity: {active[0].get('displayName')} ({capacity_id})")

    # --------------------------------------------------------------- workspace
    workspace_name = config["workspaceName"]
    workspaces = fabric.list_all("/workspaces")
    workspace = next((w for w in workspaces if w["displayName"] == workspace_name), None)
    if workspace:
        print(f"Workspace exists: {workspace_name} ({workspace['id']})")
    else:
        workspace = fabric.post("/workspaces", {
            "displayName": workspace_name,
            "description": config.get("workspaceDescription", ""),
        })
        print(f"Created workspace: {workspace_name} ({workspace['id']})")
    workspace_id = workspace["id"]

    if workspace.get("capacityId", "").lower() != capacity_id.lower():
        fabric.post(f"/workspaces/{workspace_id}/assignToCapacity", {"capacityId": capacity_id})
        print(f"  assigned to capacity {capacity_id}")

    existing_items = fabric.list_all(f"/workspaces/{workspace_id}/items")
    by_type_name = {(i["type"], i["displayName"]): i["id"] for i in existing_items}

    # ------------------------------------------------------------- environment
    # Inline `%pip install` raises MagicUsageError when a notebook runs from a pipeline
    # in tenants where inline installation is disabled. A published Environment carries
    # the libraries instead, and resolves them once rather than per session.
    environment_id = None
    environment_config = config.get("environment")
    if environment_config and args.skip_environment:
        # Republishing costs ~20 minutes of live capacity, so skip it when only notebook
        # content changed. The existing published environment stays bound to the
        # notebooks below.
        existing_environment = by_type_name.get(("Environment", environment_config["displayName"]))
        if existing_environment:
            environment_id = existing_environment
            print(f"Environment reused (publish skipped): "
                  f"{environment_config['displayName']} ({environment_id})")
        else:
            raise SystemExit("--skip-environment was passed but no published environment "
                             f"named {environment_config['displayName']} exists yet.")
    elif environment_config:
        name = environment_config["displayName"]
        environment_id = by_type_name.get(("Environment", name))
        if environment_id:
            print(f"Environment exists: {name} ({environment_id})")
        else:
            created = fabric.post(f"/workspaces/{workspace_id}/environments", {
                "displayName": name,
                "description": environment_config.get("description", ""),
            })
            environment_id = created["id"]
            print(f"Created environment: {name} ({environment_id})")

        # Fabric accepts .jar, .py, .whl, .tar.gz, or environment.yml here. A plain
        # requirements.txt is rejected with EnvironmentValidationFailed, and the
        # filename -- not just the content -- is what gets validated.
        requirements = root / environment_config["requirements"]
        upload_url = (f"{BASE}/workspaces/{workspace_id}/environments/{environment_id}"
                      "/staging/libraries")
        upload = requests.post(
            upload_url,
            headers={"Authorization": fabric.session.headers["Authorization"]},
            files={"file": (requirements.name, requirements.read_bytes(),
                            "application/octet-stream")},
            timeout=300,
        )
        if not upload.ok:
            raise SystemExit(f"Library upload failed: {upload.status_code}\n{upload.text[:600]}")
        print(f"  uploaded {requirements.name}")

        fabric.post(f"/workspaces/{workspace_id}/environments/{environment_id}/staging/publish", {})
        print("  publishing environment (this takes several minutes) ...")
        deadline = time.time() + 45 * 60
        while time.time() < deadline:
            state = (fabric.get(f"/workspaces/{workspace_id}/environments/{environment_id}")
                     .get("properties", {}).get("publishDetails", {}).get("state", "Unknown"))
            if state in ("Success", "Succeeded"):
                print("  environment published")
                break
            if state in ("Failed", "Cancelled"):
                raise SystemExit(f"Environment publish {state}. Check the portal for details.")
            time.sleep(30)
        else:
            raise SystemExit("Environment publish did not finish in 45 minutes.")

    # -------------------------------------------------------------- lakehouses
    lakehouse_ids = {}
    for lakehouse in config["lakehouses"]:
        name = lakehouse["displayName"]
        item_id = by_type_name.get(("Lakehouse", name))
        if item_id:
            print(f"Lakehouse exists: {name} ({item_id})")
        else:
            created = fabric.post(f"/workspaces/{workspace_id}/lakehouses", {
                "displayName": name, "description": lakehouse.get("description", ""),
            })
            item_id = created["id"]
            print(f"Created lakehouse: {name} ({item_id})")
        lakehouse_ids[name] = item_id

    # --------------------------------------------------------------- notebooks
    notebook_ids = {}
    for notebook in config["notebooks"]:
        name = notebook["displayName"]
        source = root / notebook["localPath"]
        if not source.exists():
            print(f"  SKIP {name}: {source} not found")
            continue

        content = json.loads(source.read_text(encoding="utf-8"))
        dependencies = {}
        lakehouse_name = notebook.get("lakehouse")
        if lakehouse_name and lakehouse_name in lakehouse_ids:
            # Relative saveAsTable / spark.read.table calls fail without a bound default
            # lakehouse, and the Spark session is cancelled rather than erroring cleanly.
            dependencies["lakehouse"] = {
                "default_lakehouse": lakehouse_ids[lakehouse_name],
                "default_lakehouse_name": lakehouse_name,
                "default_lakehouse_workspace_id": workspace_id,
            }
        if environment_id:
            dependencies["environment"] = {
                "environmentId": environment_id,
                "workspaceId": workspace_id,
            }
        if dependencies:
            content.setdefault("metadata", {})["dependencies"] = dependencies
        payload = json.dumps(content, ensure_ascii=False).encode("utf-8")
        definition = {"format": "ipynb",
                      "parts": [inline_part("notebook-content.ipynb", payload)]}

        item_id = by_type_name.get(("Notebook", name))
        if item_id:
            fabric.post(f"/workspaces/{workspace_id}/notebooks/{item_id}/updateDefinition",
                        {"definition": definition})
            print(f"Updated notebook: {name} ({item_id})  [default lakehouse: {lakehouse_name}]")
        else:
            created = fabric.post(f"/workspaces/{workspace_id}/notebooks", {
                "displayName": name, "definition": definition,
            })
            item_id = created["id"]
            print(f"Created notebook: {name} ({item_id})  [default lakehouse: {lakehouse_name}]")
        notebook_ids[name] = item_id

    # ----------------------------------------------------------- data pipeline
    pipeline_result = None
    pipeline_config = config.get("dataPipeline")
    if pipeline_config:
        raw = (root / pipeline_config["localPath"]).read_text(encoding="utf-8")
        raw = raw.replace("{{WORKSPACE_ID}}", workspace_id)
        for name, item_id in notebook_ids.items():
            raw = raw.replace("{{NOTEBOOK_ID:" + name + "}}", item_id)
        leftover = sorted(set(part.split("}}")[0] + "}}"
                              for part in raw.split("{{")[1:] if "}}" in part))
        if leftover:
            raise SystemExit(f"Unresolved pipeline tokens (no matching notebook): {leftover}")

        name = pipeline_config["displayName"]
        definition = {"parts": [inline_part("pipeline-content.json", raw.encode("utf-8"))]}
        item_id = by_type_name.get(("DataPipeline", name))
        if item_id:
            fabric.post(f"/workspaces/{workspace_id}/items/{item_id}/updateDefinition",
                        {"definition": definition})
            print(f"Updated data pipeline: {name} ({item_id})")
        else:
            created = fabric.post(f"/workspaces/{workspace_id}/items", {
                "displayName": name, "type": "DataPipeline",
                "description": pipeline_config.get("description", ""),
                "definition": definition,
            })
            item_id = created["id"]
            print(f"Created data pipeline: {name} ({item_id})")
        pipeline_result = {"displayName": name, "id": item_id}

    output = {
        "workspace": {"displayName": workspace_name, "id": workspace_id,
                      "capacityId": capacity_id},
        "lakehouses": [{"displayName": n, "id": i} for n, i in lakehouse_ids.items()],
        "notebooks": [{"displayName": n, "id": i} for n, i in notebook_ids.items()],
        "dataPipeline": pipeline_result,
    }
    Path(args.output).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {args.output}")
    print(f"Workspace URL: https://app.fabric.microsoft.com/groups/{workspace_id}")


if __name__ == "__main__":
    main()
