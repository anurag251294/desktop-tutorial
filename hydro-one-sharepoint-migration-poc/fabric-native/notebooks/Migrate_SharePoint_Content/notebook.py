# Migrate_SharePoint_Content
#
# Fabric-native SharePoint -> OneLake content migration (Spark).
#
# Downloads each document's binary content from Microsoft Graph and writes it into
# the workspace Lakehouse Files area (OneLake) via the OneLake ABFS path -- no
# external storage account and no dependency on the /lakehouse POSIX mount (which
# is not present in headless RunNotebook jobs). Per-file results and per-library
# delta watermarks are recorded in Delta tables so re-runs are incremental and
# idempotent.
#
# Cells are separated by the marker below; Deploy-FabricNative.ps1 splits on it
# and assembles the .ipynb, injecting the default-lakehouse metadata.

# CELL ========================================================================
# Parameters (this cell is tagged "parameters" -- the pipeline overrides these)
workspace_id     = ""        # Fabric workspace GUID (deploy injects default)
lakehouse_id     = ""        # Lakehouse item GUID (deploy injects default)

tenant_id        = ""        # Entra tenant GUID
client_id        = ""        # App registration (Graph Sites.Read.All / Files.Read.All)
key_vault_uri    = ""        # e.g. https://hydroone-kv.vault.azure.net/
client_secret_name = "graph-client-secret"   # secret name in Key Vault
client_secret    = ""        # optional: pass directly instead of Key Vault (testing only)

site_url         = ""        # e.g. https://contoso.sharepoint.com/sites/Engineering
library_name     = "Documents"
mode             = "incremental"   # "full" or "incremental"

audit_table      = "migration_audit"
watermark_table  = "migration_watermark"

# CELL ========================================================================
# OneLake paths + Graph helpers
import os, json, datetime, urllib.parse, tempfile, requests

# notebookutils is auto-injected in Fabric notebook runtimes; importing it
# explicitly also makes the code run under raw Spark/Livy sessions.
import notebookutils

GRAPH = "https://graph.microsoft.com/v1.0"

def _abfss():
    return (f"abfss://{workspace_id}@onelake.dfs.fabric.microsoft.com/{lakehouse_id}")

def files_uri(*parts):
    return "/".join([f"{_abfss()}/Files", *[p.strip('/') for p in parts if p]])

def table_uri(name):
    return f"{_abfss()}/Tables/{name}"

def _now():
    return datetime.datetime.utcnow().isoformat()

def get_secret():
    """Resolve the Graph client secret: explicit param first, else Key Vault."""
    if client_secret:
        return client_secret
    if not key_vault_uri:
        raise ValueError("No client_secret and no key_vault_uri provided.")
    return notebookutils.credentials.getSecret(key_vault_uri, client_secret_name)

def graph_token():
    resp = requests.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data={
            "client_id": client_id,
            "client_secret": get_secret(),
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def graph_get(url, token, **kwargs):
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=120, **kwargs)
    r.raise_for_status()
    return r

def resolve_drive(token):
    """site_url -> (siteId, driveId) for the named document library."""
    parsed = urllib.parse.urlparse(site_url)
    site = graph_get(f"{GRAPH}/sites/{parsed.netloc}:{parsed.path}", token).json()
    drives = graph_get(f"{GRAPH}/sites/{site['id']}/drives", token).json()["value"]
    drive = next((d for d in drives if d["name"] == library_name), None)
    if not drive:
        raise ValueError(f"Library '{library_name}' not found in site {site_url}")
    return site["id"], drive["id"]

# CELL ========================================================================
# Delta state helpers (audit + watermark), written to OneLake Tables via ABFS
from pyspark.sql import Row
from delta.tables import DeltaTable

def _table_exists(name):
    try:
        spark.read.format("delta").load(table_uri(name))
        return True
    except Exception:
        return False

def read_watermark(key):
    if not _table_exists(watermark_table):
        return None
    rows = (spark.read.format("delta").load(table_uri(watermark_table))
            .where(f"site_key = '{key}'").collect())
    return rows[0]["delta_link"] if rows else None

def write_watermark(key, delta_link):
    df = spark.createDataFrame([Row(site_key=key, delta_link=delta_link, updated_utc=_now())])
    uri = table_uri(watermark_table)
    if not _table_exists(watermark_table):
        df.write.format("delta").save(uri)
        return
    tgt = DeltaTable.forPath(spark, uri)
    (tgt.alias("t").merge(df.alias("s"), "t.site_key = s.site_key")
        .whenMatchedUpdateAll().whenNotMatchedInsertAll().execute())

def write_audit(records):
    if not records:
        return
    (spark.createDataFrame([Row(**r) for r in records])
        .write.mode("append").format("delta").save(table_uri(audit_table)))

# CELL ========================================================================
# Core migration: enumerate (delta or full) and stream content into OneLake Files
def site_key():
    return f"{site_url}::{library_name}"

def enumerate_items(token, site_id, drive_id):
    """Yield driveItems. Uses Graph delta for incremental, children for full."""
    key = site_key()
    if mode == "incremental":
        url = read_watermark(key) or f"{GRAPH}/sites/{site_id}/drives/{drive_id}/root/delta"
    else:
        url = f"{GRAPH}/sites/{site_id}/drives/{drive_id}/root/children"
    while url:
        page = graph_get(url, token).json()
        for it in page.get("value", []):
            yield it
        if "@odata.nextLink" in page:
            url = page["@odata.nextLink"]
        else:
            if mode == "incremental" and "@odata.deltaLink" in page:
                write_watermark(key, page["@odata.deltaLink"])
            url = None

def dest_rel(item):
    # Preserve SharePoint folder structure under Files/<site>/<library>/...
    site_seg = urllib.parse.urlparse(site_url).path.strip("/").replace("/", "_")
    parent = item.get("parentReference", {}).get("path", "")
    sub = parent.split("root:", 1)[1].lstrip("/") if "root:" in parent else ""
    return [p for p in [site_seg, library_name, sub, item["name"]] if p]

def migrate():
    token = graph_token()
    site_id, drive_id = resolve_drive(token)
    audit, copied, skipped = [], 0, 0
    for it in enumerate_items(token, site_id, drive_id):
        if it.get("deleted") or "file" not in it:   # skip folders & tombstones
            skipped += 1
            continue
        dest = files_uri(*dest_rel(it))
        try:
            # Stream download to a local temp file, then copy into OneLake.
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                resp = graph_get(it["@microsoft.graph.downloadUrl"], token, stream=True)
                for chunk in resp.iter_content(chunk_size=4 * 1024 * 1024):
                    tmp.write(chunk)
                tmp_path = tmp.name
            notebookutils.fs.cp("file://" + tmp_path, dest, True)
            os.remove(tmp_path)
            copied += 1
            status = "copied"
        except Exception as e:   # noqa: BLE001 - record and continue
            status = f"error: {e}"
        audit.append(dict(site=site_url, library=library_name, name=it["name"],
                          item_id=it["id"], size=it.get("size", 0),
                          status=status, dest=dest, ts_utc=_now()))
        if len(audit) >= 200:
            write_audit(audit); audit = []
    write_audit(audit)
    return copied, skipped

# CELL ========================================================================
# Entry point
if site_url:
    copied, skipped = migrate()
    result = {"site": site_url, "library": library_name, "mode": mode,
              "copied": copied, "skipped": skipped}
    print(json.dumps(result))
    notebookutils.notebook.exit(json.dumps(result))
else:
    # No site configured -> smoke mode: prove the OneLake write path works.
    notebookutils.fs.put(files_uri("_smoketest", "hello.txt"),
                         "onelake write ok @ " + _now(), True)
    (spark.createDataFrame([Row(check="onelake_write", status="ok", ts_utc=_now())])
        .write.mode("overwrite").option("overwriteSchema", "true")
        .format("delta").save(table_uri("migration_smoke")))
    print("SMOKE_OK")
    notebookutils.notebook.exit("SMOKE_OK")
