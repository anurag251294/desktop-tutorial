"""Provision the Azure AI Foundry side of the geohazard demo.

Creates an AI Foundry (AIServices) account, enables a managed identity, creates a
Foundry project, and deploys a chat model — picking a model/SKU that is actually
deployable in the target region and subscription.

    az login
    python scripts/foundry/provision_foundry.py \
        --resource-group rg-fabric-demo --location canadacentral \
        --account geohazard-foundry-mcap --project geohazard-project

Three things bite here, and all three are handled below:

1. The model catalogue lies. `az cognitiveservices model list` will happily report
   GlobalStandard support for a model the subscription has no quota for, and the
   deployment then fails with "not supported in this region". The only reliable test is
   to attempt the deployment, so this script walks a candidate list.
2. Projects require a managed identity on the *account*, and the error message says so
   even after you enable one — because `az resource create` does not send an `identity`
   block for the project resource itself. It has to be a raw ARM PUT.
3. The `accounts/projects` API versions move fast. Old preview versions (2025-*) are
   rejected outright; query the provider for a current one.
"""
import argparse
import json
import subprocess
import sys

SHELL = sys.platform == "win32"


def az(*args, check=True, parse=True):
    result = subprocess.run(["az", *args], capture_output=True, text=True, shell=SHELL)
    if check and result.returncode != 0:
        raise SystemExit(f"az {' '.join(args)} failed:\n{result.stderr[:1200]}")
    if not parse:
        return result
    output = result.stdout.strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except ValueError:
        return output


# Ordered best-first. Each entry is (model, version, sku, capacity). The first that the
# subscription will actually accept wins.
MODEL_CANDIDATES = [
    ("gpt-4.1-mini", "2025-04-14", "GlobalStandard", 50),
    ("gpt-4.1-mini", "2025-04-14", "Standard", 10),
    ("gpt-5.4-mini", "2026-03-17", "GlobalStandard", 50),
    ("gpt-5.4", "2026-03-05", "GlobalStandard", 50),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--location", default="canadacentral")
    parser.add_argument("--account", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--subscription", default=None)
    parser.add_argument("--output", default="cicd/foundry-setup.output.json")
    args = parser.parse_args()

    scope = ["--subscription", args.subscription] if args.subscription else []
    subscription_id = args.subscription or az("account", "show", "--query", "id", "-o", "tsv")

    # --------------------------------------------------------------- account
    existing = az("cognitiveservices", "account", "show", "-g", args.resource_group,
                  "-n", args.account, *scope, check=False)
    if isinstance(existing, dict) and existing.get("name"):
        print(f"Account exists: {args.account}")
    else:
        print(f"Creating AIServices account {args.account} in {args.location} ...")
        az("cognitiveservices", "account", "create", "-g", args.resource_group,
           "-n", args.account, "-l", args.location, "--kind", "AIServices",
           "--sku", "S0", "--custom-domain", args.account, "--yes", *scope, parse=False)

    # Projects are refused without a managed identity on the account.
    az("cognitiveservices", "account", "identity", "assign", "-g", args.resource_group,
       "-n", args.account, *scope, check=False, parse=False)
    account = az("cognitiveservices", "account", "show", "-g", args.resource_group,
                 "-n", args.account, *scope)
    print(f"  identity: {account.get('identity', {}).get('type')}  "
          f"endpoint: {account['properties']['endpoint']}")

    # --------------------------------------------------------------- project
    api_versions = az("provider", "show", "-n", "Microsoft.CognitiveServices", *scope,
                      "--query", "resourceTypes[?resourceType=='accounts/projects'].apiVersions[0]",
                      "-o", "json")
    api_version = (api_versions or ["2026-07-01"])[0]
    print(f"  using accounts/projects api-version {api_version}")

    project_url = (f"https://management.azure.com/subscriptions/{subscription_id}"
                   f"/resourceGroups/{args.resource_group}/providers/Microsoft.CognitiveServices"
                   f"/accounts/{args.account}/projects/{args.project}?api-version={api_version}")
    body = {
        "location": args.location,
        # `az resource create` omits this block, which is what produces the misleading
        # "you must enable a managed identity" error even once the account has one.
        "identity": {"type": "SystemAssigned"},
        "properties": {"displayName": args.project, "description": "Geohazard report agent"},
    }
    project = az("rest", "--method", "put", "--url", project_url,
                 "--body", json.dumps(body), *scope)
    project_endpoint = project["properties"]["endpoints"]["AI Foundry API"]
    print(f"Project ready: {project_endpoint}")

    # ------------------------------------------------------------ deployment
    deployments = az("cognitiveservices", "account", "deployment", "list",
                     "-g", args.resource_group, "-n", args.account, *scope) or []
    if deployments:
        chosen = deployments[0]["name"]
        print(f"Deployment exists: {chosen}")
    else:
        chosen = None
        for model, version, sku, capacity in MODEL_CANDIDATES:
            name = model.replace(".", "-")
            print(f"  trying {model} {version} / {sku} ...")
            result = az("cognitiveservices", "account", "deployment", "create",
                        "-g", args.resource_group, "-n", args.account,
                        "--deployment-name", name, "--model-name", model,
                        "--model-version", version, "--model-format", "OpenAI",
                        "--sku-name", sku, "--sku-capacity", str(capacity),
                        *scope, check=False, parse=False)
            if result.returncode == 0:
                chosen = name
                print(f"  deployed {model} as '{name}'")
                break
            reason = next((line for line in result.stderr.splitlines() if "Message:" in line), "")
            print(f"    rejected: {reason.strip()[:140]}")
        if not chosen:
            raise SystemExit("No candidate model could be deployed. Check quota with "
                             "`az cognitiveservices usage list -l <region>`.")

    output = {
        "subscriptionId": subscription_id,
        "resourceGroup": args.resource_group,
        "location": args.location,
        "account": args.account,
        "accountEndpoint": account["properties"]["endpoint"],
        "project": args.project,
        "projectEndpoint": project_endpoint,
        "modelDeploymentName": chosen,
    }
    with open(args.output, "w", encoding="utf-8") as stream:
        json.dump(output, stream, indent=2)
    print(f"\nWrote {args.output}")
    print("Next: publish the Fabric data agent, then add it as a tool on the Foundry")
    print("agent. The Fabric tool uses user identity passthrough and does NOT support")
    print("service principals — use the deterministic handoff contract for unattended runs.")


if __name__ == "__main__":
    main()
