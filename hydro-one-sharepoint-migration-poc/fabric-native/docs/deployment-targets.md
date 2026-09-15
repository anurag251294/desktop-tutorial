# Deployment targets

Reference IDs for known deployments. These are Fabric **resource identifiers**
(GUIDs), not credentials — no secrets are stored here. Secrets live in Key Vault;
auth is via `az login` in the *owning* tenant.

## Hydro One — Kevin's tenant

> ⚠️ This workspace lives in **Kevin's tenant**, not ours. Deploys/updates must be
> run by an identity signed in to that tenant (`az login`). Our corp identity
> cannot see it (the Fabric API returns `WorkspaceNotFound`).

| Item | Name | ID |
|------|------|----|
| Workspace | *(Kevin's)* | `b0aa3297-5a0d-4b1b-82db-123c3003e905` |
| Notebook  | `Migrate_SharePoint_Content` | `dbf749a8-9d5e-4a08-896a-dc81b4161ed2` |

**To apply the latest notebook (incl. the native `sharepoint_inventory` build)**,
from Kevin's machine after `git pull`:

```powershell
az login   # Kevin's tenant
.\fabric-native\scripts\Deploy-FabricNative.ps1 `
  -WorkspaceId "b0aa3297-5a0d-4b1b-82db-123c3003e905" `
  -ConfigPath .\fabric-native\config\fabric-native.json
```

The deploy is idempotent — it runs `updateDefinition` on the existing notebook and
leaves everything else in place.
