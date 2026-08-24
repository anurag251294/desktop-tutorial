# Deploying into another tenant

Notes from deploying this into a customer tenant on 2026-08-21, where the operator held
**Reader** at the ARM level and **Member** on an existing Fabric workspace. That split
turns out to define what is and is not possible, so it is the first thing to establish.

## Establish what you actually hold, before creating anything

Fabric and ARM are separate permission systems and you can easily have one without the
other.

```bash
az login --tenant "<tenant-id>"
az role assignment list --assignee-object-id "<your-object-id>" --all \
    --subscription "<sub>" --query "[].{role:roleDefinitionName, scope:scope}" -o table
```

If the Graph query fails with *"Insufficient privileges"*, you are a guest — pass
`--assignee-object-id` explicitly, since name lookup needs directory read.

Then check the Fabric side independently:

```bash
curl -H "Authorization: Bearer $(az account get-access-token \
    --resource https://api.fabric.microsoft.com --query accessToken -o tsv)" \
    https://api.fabric.microsoft.com/v1/workspaces
```

**Reader at ARM plus Member on a workspace is enough to deploy the entire Fabric half**
— lakehouses, notebooks, environment, pipeline — and to run it. It is not enough for
anything under `Microsoft.CognitiveServices`.

## Pin the capacity ID. Do not let it auto-detect

`provision_fabric_demo.py` auto-detects a capacity when `capacityId` is blank, and the
Fabric API only lists capacities you **administer**. In a customer tenant you usually
administer none of theirs, so auto-detect picks something else — a trial or PPU capacity —
and the provisioner then calls `assignToCapacity`, **moving the customer's workspace off
their own capacity**.

Read their workspace first and pass its existing capacity back in, which makes the
reassignment check a no-op:

```bash
python scripts/fabric/provision_fabric_demo.py \
    --config cicd/fabric-setup.config.tenant-template.json \
    --output cicd/fabric-setup.output.customer.json \
    --capacity-id "<their-capacity-guid>"
```

Set `workspaceName` to their **existing** workspace. The provisioner matches on display
name and reuses it. Drop the `deploymentPipeline` block — creating one needs rights you
will not have.

## Size the AOI to the capacity

The analysis grid is 10 m, so cost scales with the square of the analysis radius:

| `ANALYSIS_RADIUS_KM` | Grid | Pixels | Observed |
| --- | --- | --- | --- |
| 3.0 | 600 x 600 | 360,000 | ~15 min on **F64** |
| 1.5 | 300 x 300 | 90,000 | ~27 min on **F2** |

An **F2 completed the full nine-activity pipeline at 1.5 km**, which is worth knowing
before anyone asks a customer to scale up. Bronze is metadata only, so the 20 km catalog
radius is cheap and can stay.

The result held up at the smaller AOI — Low 42.09 / Moderate 20.64 / High 33.12 /
Extreme 4.15%, ten ranked hotspots, forty-five evidence records, and the same single
Sentinel-1 GRD data gap.

## Two tenant-level blockers to raise early

Both need a customer administrator, and both are invisible until you hit them.

**1. Foundry needs two separate roles, and the obvious one is wrong.**

Deploying a model fails with:

```text
AuthorizationFailed: Microsoft.CognitiveServices/accounts/deployments/write
```

**Azure AI Developer does not fix this.** Its actions are
`Microsoft.MachineLearningServices/workspaces/*`, `Microsoft.Authorization/*/read`, and
`Microsoft.Resources/deployments/*` — nothing under `Microsoft.CognitiveServices` at all,
so it can never deploy into an AIServices account. Granted and retried live to confirm.
The built-in role carrying `accounts/deployments/write` is **Cognitive Services OpenAI
Contributor**.

Separately, the agents **data plane** returns `401 PermissionDenied` until a role carrying
`Microsoft.CognitiveServices/*` **data actions** is assigned at **project** scope. Roles
that qualify: **Foundry User**, Foundry Project Manager, Cognitive Services User,
Cognitive Services Data Contributor (Preview). Neither Cognitive Services OpenAI
Contributor nor Cognitive Services Contributor qualifies — their data actions are empty or
scoped to `accounts/OpenAI/*`, a different surface from `accounts/AIServices/agents/*`.

```bash
az role assignment create --assignee-object-id "<oid>" --assignee-principal-type User \
  --role "Foundry User" \
  --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>"
```

Assign at project scope specifically. In the first tenant an account-scope assignment
returned 401 indefinitely and looked exactly like propagation delay.

**1b. `gpt-4.1-mini` is not deployable in canadacentral — in either tenant tested.**

Both the regional catalogue and the account-scoped `list-models` advertise it on
GlobalStandard. Every attempt is rejected:

```text
InvalidResourceProperties: The specified SKU 'GlobalStandard' for model
'gpt-4.1-mini 2025-04-14' is not supported in this region 'canadacentral'.
```

GlobalStandard, Standard, and DeveloperTier all fail. `gpt-5.4-mini` GlobalStandard
deploys first time. Treat the model catalogue as advertising rather than availability, and
deploy from a candidate list instead of a single name.

**2. The Fabric data agent needs two tenant switches, not a bigger SKU.**

Creating a data agent fails with:

```text
TenantSwitchDisabled: Tenant setting not enabled for Azure OpenAI usage: Disallowed
```

Fabric admin portal, **Tenant settings → Copilot and Azure AI**. Enabling the first
toggle changes the error rather than clearing it:

```text
TenantSwitchDisabled: ... DisallowedForStoreDataCrossGeo
```

A second toggle sits directly beneath it — *"Data sent to Azure OpenAI can be processed
outside your capacity's geographic region, compliance boundary, or national cloud
instance"* — and if the settings are scoped to a security group, that group must be on
both. Neither has anything to do with capacity size: an F2 hosts a data agent fine.

Raise the second one as a data-residency decision rather than a checkbox. For a customer
on a Canada Central capacity it means prompts leaving the country, and their compliance
owner should see that sentence.

**3. The Fabric tool inside Foundry: creatable, but not usable on this project type.**

Two earlier conclusions here were wrong, both now retested end to end in a second tenant.

*Wrong: "the ARM connections API rejects every Fabric category, so it is portal-only."*
It does not. The rejection came from using preview API versions. At **`2025-06-01`** ARM
creates it happily:

```bash
az account get-access-token --resource https://management.azure.com
PUT .../accounts/<account>/projects/<project>/connections/fabric_geohazard?api-version=2025-06-01
{"properties": {"category": "MicrosoftFabric", "authType": "AAD",
                "target": "https://api.fabric.microsoft.com/v1/workspaces/<ws>/aiskills/<agent>",
                "metadata": {"ResourceId": "<agent>", "workspace_id": "<ws>"}}}
```

Read an existing working connection and clone its shape rather than inventing a payload.
Creating one needs `accounts/projects/connections/write` — **Foundry Project Manager** is
the narrowest built-in role that grants it.

*Still true, and now confirmed twice:* the connection attaches to an agent (`200`), and
every **run** then fails:

```text
missing_required_parameter: AML connections are required for Fabric tool.
```

The runtime resolves Fabric tool connections through an Azure ML workspace connection
store, which a `Microsoft.CognitiveServices/accounts/projects` project does not have. A
**hub-based** project is required. Tested in two tenants, with the connection created
correctly and four roles held. This is a platform limitation, not configuration.

It costs nothing architecturally: the pipeline hands the agent a bounded evidence
contract, so what crosses the boundary is fixed and auditable before the model sees it.
Live questioning is served by the Fabric data agent in the workspace itself.

**Role summary.** These are different jobs and no single role covers them:

| Need | Role | Scope |
| --- | --- | --- |
| Deploy a model | Cognitive Services OpenAI Contributor | resource group |
| Use the agents data plane | Foundry User | **project** |
| Create a connection | Foundry Project Manager | **project** |
| Create Fabric items | workspace **Member** | Fabric workspace |

Azure AI Developer grants none of these — its actions are
`Microsoft.MachineLearningServices/*` only. Query role definitions for the exact action
rather than matching on role names; the names are misleading.

## Check the data sources reach the customer's geography

The Planetary Computer sources are global. The geology, faults, and SIFT soil survey all
come from **DataBC, which is British Columbia only**. Point the AOI anywhere else and
those three return empty — reported honestly as data gaps, but the surveyed soil layer is
the only direct ground truth, so hotspot attribution loses its evidence.

For a customer outside BC, the real porting work is finding their provincial equivalents,
not swapping the raster source.

## Keep customer identifiers out of a public repo

Workspace, capacity, and item GUIDs are customer infrastructure detail. Keep the real
config and provisioning output local; commit
`cicd/fabric-setup.config.tenant-template.json` with placeholders. `.gitignore` covers
`cicd/*.customer.json` and the named customer files.
