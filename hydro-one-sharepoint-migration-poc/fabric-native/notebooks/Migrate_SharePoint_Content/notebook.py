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
# Things this notebook has to handle because Graph behaves this way at scale:
#   * The delta feed does NOT return parentReference.path, so each item's folder is
#     resolved from its parent id (cached per folder). Without that, every file
#     landed flat in the library root and same-named files in different folders
#     overwrote each other.
#   * The same item can appear more than once in one delta feed; the last one wins.
#   * Renaming or moving a folder returns only the folder, not its contents. Earlier
#     copies are moved to the new location in OneLake and the inventory paths under
#     it are rewritten; a renamed or moved file has its old copy removed once the new
#     one is in place.
#   * App-only tokens expire after about an hour; they are refreshed before expiry
#     and on a 401, so a long migration does not fail every file after the first hour.
#   * Graph throttles large jobs (429) and has transient 5xx; those are retried,
#     honouring Retry-After.
#   * A saved delta link can expire (410 Gone); the run restarts a full enumeration
#     from the Location Graph returns instead of failing.
#
# Deliberately NOT done: a file deleted in SharePoint loses its inventory row, but its
# migrated copy stays in OneLake. A migration should not destroy data because the
# source changed.
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
inventory_table  = "sharepoint_inventory"   # built natively from Graph -- no SharePoint connection needed

# CELL ========================================================================
# OneLake paths + Graph helpers
import os, json, time, datetime, urllib.parse, tempfile, requests

# notebookutils is auto-injected in Fabric notebook runtimes; importing it
# explicitly also makes the code run under raw Spark/Livy sessions.
import notebookutils

GRAPH = "https://graph.microsoft.com/v1.0"

# Retried with the server's Retry-After when present, otherwise exponential backoff.
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 6

def _abfss():
    return (f"abfss://{workspace_id}@onelake.dfs.fabric.microsoft.com/{lakehouse_id}")

def files_uri(*parts):
    return "/".join([f"{_abfss()}/Files", *[p.strip('/') for p in parts if p]])

def table_uri(name):
    return f"{_abfss()}/Tables/{name}"

def _now():
    return datetime.datetime.utcnow().isoformat()

def require_onelake_target():
    if not workspace_id or not lakehouse_id:
        raise ValueError("workspace_id and lakehouse_id must both be set "
                         "(the deploy script injects them as defaults).")

def require_run_parameters():
    """Fail with a readable message instead of a 404 from a malformed token URL."""
    require_onelake_target()
    missing = [name for name, value in (("tenant_id", tenant_id), ("client_id", client_id))
               if not value]
    if not client_secret and not key_vault_uri:
        missing.append("key_vault_uri (or client_secret for testing)")
    if missing:
        raise ValueError("Missing notebook parameters: " + ", ".join(missing))
    if mode not in ("full", "incremental"):
        raise ValueError(f"mode must be 'full' or 'incremental', not '{mode}'")

def get_secret():
    """Resolve the Graph client secret: explicit param first, else Key Vault."""
    if client_secret:
        return client_secret
    if not key_vault_uri:
        raise ValueError("No client_secret and no key_vault_uri provided.")
    return notebookutils.credentials.getSecret(key_vault_uri, client_secret_name)

class GoneError(Exception):
    """Graph returned 410 Gone for a delta link; carries the URL to restart from."""
    def __init__(self, restart_url):
        super().__init__("delta link expired (410 Gone)")
        self.restart_url = restart_url

_token_cache = {"value": None, "expires_at": 0.0}

def graph_token(force_refresh=False):
    """App-only Graph token, refreshed five minutes before it expires."""
    now = time.time()
    if (not force_refresh and _token_cache["value"]
            and now < _token_cache["expires_at"] - 300):
        return _token_cache["value"]
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
    body = resp.json()
    _token_cache["value"] = body["access_token"]
    _token_cache["expires_at"] = now + int(body.get("expires_in", 3599))
    return _token_cache["value"]

def graph_get(url, stream=False):
    """GET against Graph with token refresh on 401, throttling retries, and a
    distinct GoneError for an expired delta link."""
    refreshed = False
    for attempt in range(1, MAX_ATTEMPTS + 1):
        r = requests.get(url, headers={"Authorization": f"Bearer {graph_token()}"},
                         timeout=120, stream=stream)
        if r.status_code == 401 and not refreshed:
            r.close()
            graph_token(force_refresh=True)
            refreshed = True
            continue
        if r.status_code == 410:
            restart = r.headers.get("Location")
            r.close()
            raise GoneError(restart)
        if r.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
            try:
                delay = float(r.headers.get("Retry-After"))
            except (TypeError, ValueError):
                delay = 2 ** attempt
            r.close()
            time.sleep(min(delay, 120))
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r

def resolve_drive():
    """site_url -> (siteId, driveId) for the named document library."""
    parsed = urllib.parse.urlparse(site_url.strip())
    path = parsed.path.rstrip("/")
    # The root site has no server-relative path: /sites/{host}, not /sites/{host}:
    site_ref = f"{parsed.netloc}:{path}" if path else parsed.netloc
    site = graph_get(f"{GRAPH}/sites/{site_ref}").json()
    drives, url = [], f"{GRAPH}/sites/{site['id']}/drives"
    while url:
        page = graph_get(url).json()
        drives.extend(page.get("value", []))
        url = page.get("@odata.nextLink")
    drive = next((d for d in drives if d["name"] == library_name), None)
    if not drive:
        raise ValueError(f"Library '{library_name}' not found in site {site_url}")
    return site["id"], drive["id"]

_folder_paths = {}

def folder_path(drive_id, folder_id):
    """Path of a folder relative to the library root, e.g. 'Specs/2024'.

    Resolved from the folder's id with a plain GET, which (unlike the delta feed)
    does return parentReference.path. Cached, so this costs one call per folder,
    not per file."""
    if not folder_id:
        return ""
    if folder_id in _folder_paths:
        return _folder_paths[folder_id]
    item = graph_get(f"{GRAPH}/drives/{drive_id}/items/{folder_id}"
                     "?$select=id,name,root,parentReference").json()
    if "root" in item:
        rel = ""
    else:
        parent = item.get("parentReference") or {}
        parent_path = parent.get("path") or ""
        if "root:" in parent_path:
            base = urllib.parse.unquote(parent_path.split("root:", 1)[1]).strip("/")
        else:
            base = folder_path(parent.get("driveId") or drive_id, parent.get("id"))
        rel = "/".join(p for p in [base, item.get("name", "")] if p)
    _folder_paths[folder_id] = rel
    return rel

def relative_folder(item, drive_id):
    """Folder an item sits in, relative to the library root."""
    parent = item.get("parentReference") or {}
    path = parent.get("path") or ""
    if "root:" in path:   # present on non-delta responses; percent-encoded
        return urllib.parse.unquote(path.split("root:", 1)[1]).strip("/")
    return folder_path(parent.get("driveId") or drive_id, parent.get("id"))

# CELL ========================================================================
# Delta state helpers (audit + watermark + inventory), written to OneLake Tables via ABFS
from pyspark.sql import Row, functions as F
from pyspark.sql.types import StructType, StructField, StringType, LongType
from delta.tables import DeltaTable

# Explicit schemas: inferring from a batch fails outright when a column is null in
# every row of that batch (for example a small incremental run).
AUDIT_SCHEMA = StructType([
    StructField("site", StringType()), StructField("library", StringType()),
    StructField("name", StringType()), StructField("item_id", StringType()),
    StructField("size", LongType()), StructField("status", StringType()),
    StructField("dest", StringType()), StructField("ts_utc", StringType()),
])
INVENTORY_SCHEMA = StructType([
    StructField("item_id", StringType()), StructField("site", StringType()),
    StructField("library", StringType()), StructField("name", StringType()),
    StructField("kind", StringType()), StructField("size", LongType()),
    StructField("relative_path", StringType()), StructField("web_url", StringType()),
    StructField("last_modified", StringType()), StructField("created", StringType()),
    StructField("synced_utc", StringType()),
])

def _frame(rows, schema):
    return spark.createDataFrame(
        [tuple(r.get(f.name) for f in schema.fields) for r in rows], schema)

def _table_exists(name):
    try:
        spark.read.format("delta").load(table_uri(name))
        return True
    except Exception:
        return False

def _this_library():
    return (F.col("site") == site_url) & (F.col("library") == library_name)

def read_watermark(key):
    if not _table_exists(watermark_table):
        return None
    # A column expression, not an interpolated SQL string: a library called
    # "Bob's Files" broke the old f"site_key = '{key}'" filter.
    rows = (spark.read.format("delta").load(table_uri(watermark_table))
            .where(F.col("site_key") == key).collect())
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
    _frame(records, AUDIT_SCHEMA).write.mode("append").format("delta").save(table_uri(audit_table))

def write_inventory(events, replace_scope):
    """Apply inventory changes to Delta.

    events maps item_id -> inventory row, or None when Graph reported the item
    deleted. Keyed by id so the last occurrence wins: Graph documents that one item
    can appear more than once in a delta feed, and a MERGE with two source rows for
    the same key fails.

    replace_scope=True after a complete, error-free enumeration: rows for this
    site/library are rebuilt, so items deleted before a full run (which a fresh
    enumeration never reports as tombstones) do not linger forever."""
    uri = table_uri(inventory_table)
    upserts = [row for row in events.values() if row is not None]
    deletes = [item_id for item_id, row in events.items() if row is None]
    exists = _table_exists(inventory_table)
    if replace_scope and exists:
        DeltaTable.forPath(spark, uri).delete(_this_library())
    if upserts:
        df = _frame(upserts, INVENTORY_SCHEMA)
        if not exists:
            df.write.format("delta").save(uri)
        else:
            (DeltaTable.forPath(spark, uri).alias("t")
                .merge(df.alias("s"), "t.item_id = s.item_id")
                .whenMatchedUpdateAll().whenNotMatchedInsertAll().execute())
    if deletes and exists:
        DeltaTable.forPath(spark, uri).delete(F.col("item_id").isin(deletes))

def relocated_items(events):
    """Items whose path differs from the last recorded inventory.

    Returns (item_id, kind, old_path, new_path) tuples. Joined in Spark rather than
    collected to the driver, so a full run over a very large library only brings back
    the items that actually moved."""
    current = [(item_id, row["relative_path"], row["kind"])
               for item_id, row in events.items() if row is not None]
    if not current or not _table_exists(inventory_table):
        return []
    now = spark.createDataFrame(current, "item_id string, new_path string, kind string")
    before = (spark.read.format("delta").load(table_uri(inventory_table))
              .where(_this_library())
              .select("item_id", F.col("relative_path").alias("old_path")))
    rows = (now.join(before, "item_id")
            .where(F.col("old_path") != F.col("new_path"))
            .collect())
    return [(r["item_id"], r["kind"], r["old_path"], r["new_path"]) for r in rows]

def rewrite_descendant_paths(old, new):
    """Point inventory rows under a renamed or moved folder at its new path. Graph
    does not return those items, so nothing else would ever update them."""
    if not _table_exists(inventory_table):
        return
    prefix = old + "/"
    DeltaTable.forPath(spark, table_uri(inventory_table)).update(
        condition=_this_library() & F.col("relative_path").startswith(prefix),
        set={"relative_path": F.concat(
            F.lit(new + "/"), F.expr(f"substring(relative_path, {len(prefix) + 1})"))})

# CELL ========================================================================
# Core migration: enumerate (delta or full) and stream content into OneLake Files
def site_key():
    return f"{site_url}::{library_name}"

def enumerate_items(site_id, drive_id, state):
    """Yield driveItems. Both modes use the Graph /delta endpoint, which is
    RECURSIVE (every item in the drive, including nested folders). 'full' starts
    fresh; 'incremental' resumes from the saved delta link. The final delta link is
    captured in state['delta_link'] so the caller advances the watermark only after
    a clean run (failed files get retried)."""
    fresh = f"{GRAPH}/sites/{site_id}/drives/{drive_id}/root/delta"
    saved = read_watermark(site_key()) if mode == "incremental" else None
    url = saved or fresh
    state["full_enumeration"] = not saved
    state["resynced"] = False
    while url:
        try:
            page = graph_get(url).json()
        except GoneError as gone:
            if state["resynced"]:
                raise
            # The saved link expired. Graph returns a Location that starts a fresh
            # enumeration; its result is the complete current state.
            url = gone.restart_url or fresh
            state["full_enumeration"] = True
            state["resynced"] = True
            continue
        for it in page.get("value", []):
            yield it
        if "@odata.nextLink" in page:
            url = page["@odata.nextLink"]
        else:
            state["delta_link"] = page.get("@odata.deltaLink")
            url = None

def dest_parts(folder, name):
    # Preserve SharePoint folder structure under Files/<site>/<library>/...
    site_seg = urllib.parse.urlparse(site_url).path.strip("/").replace("/", "_")
    return [p for p in [site_seg, library_name, folder, name] if p]

def onelake_path(rel):
    """OneLake URI for a path relative to the library root."""
    return files_uri(*dest_parts(rel, None))

def inventory_row(item, folder):
    # One inventory record per drive item (files and folders), straight from Graph.
    kind = "folder" if "folder" in item else ("file" if "file" in item else "other")
    return dict(
        item_id=item["id"],
        site=site_url,
        library=library_name,
        name=item.get("name"),
        kind=kind,
        size=int(item.get("size") or 0),
        relative_path="/".join([p for p in [folder, item.get("name")] if p]),
        web_url=item.get("webUrl"),
        last_modified=item.get("lastModifiedDateTime"),
        created=item.get("createdDateTime"),
        synced_utc=_now(),
    )

def move_tree(src, dst):
    """Move a OneLake folder. If the destination already exists (files copied there
    earlier in this run), merge into it; those files are newer, so they win."""
    fs = notebookutils.fs
    if not fs.exists(src):
        return
    if not fs.exists(dst):
        fs.mv(src, dst, True)
        return
    for child in fs.ls(src):
        target = f"{dst}/{child.name.rstrip('/')}"
        if child.isDir:
            move_tree(child.path.rstrip("/"), target)
        elif not fs.exists(target):
            fs.mv(child.path, target, True)
    fs.rm(src, True)

def apply_relocations(relocations, events, copy_failed):
    """Move earlier copies of renamed or moved items to where they now live.

    Returns (keep_old, move_errors, moved). keep_old holds item ids whose inventory
    row must keep its old path: their move failed, or the new copy of a moved file
    failed. Keeping the old path is what lets the next run notice and retry."""
    taken = {row["relative_path"] for row in events.values() if row is not None}
    keep_old, move_errors, moved = set(), 0, 0
    # Deepest first, so a renamed child moves before its renamed parent.
    for item_id, kind, old, new in sorted(relocations, key=lambda r: -(r[2] or "").count("/")):
        if not old or not new or old in taken:
            continue   # another item now lives at the old path; leave it alone
        if kind == "file" and item_id in copy_failed:
            keep_old.add(item_id)
            continue
        src, dst = onelake_path(old), onelake_path(new)
        try:
            if kind == "folder":
                move_tree(src, dst)
                rewrite_descendant_paths(old, new)
            elif notebookutils.fs.exists(src) and notebookutils.fs.exists(dst):
                notebookutils.fs.rm(src, False)
            moved += 1
        except Exception as e:   # noqa: BLE001 - keep the old path so the next run retries
            move_errors += 1
            keep_old.add(item_id)
            print(f"could not relocate '{old}' -> '{new}': {e}")
    return keep_old, move_errors, moved

def migrate():
    require_run_parameters()
    site_id, drive_id = resolve_drive()
    state = {}
    events = {}   # item_id -> inventory row, or None when Graph reports it deleted
    copy_failed = set()
    audit, copied, skipped, errors = [], 0, 0, 0
    for it in enumerate_items(site_id, drive_id, state):
        if it.get("deleted"):
            events[it["id"]] = None
            skipped += 1
            continue
        if "root" in it:      # the library itself, not a document
            skipped += 1
            continue
        is_file = "file" in it
        dest, status, tmp_path = None, None, None
        try:
            folder = relative_folder(it, drive_id)
            events[it["id"]] = inventory_row(it, folder)
            if not is_file:
                skipped += 1
                continue
            dest = files_uri(*dest_parts(folder, it["name"]))
            # The /delta response does not carry @microsoft.graph.downloadUrl, so
            # download via /content. Graph 302-redirects to a pre-authenticated
            # storage URL; requests drops the Authorization header on the
            # cross-host redirect (correct -- that URL is already authorized).
            item_drive = (it.get("parentReference") or {}).get("driveId", drive_id)
            content_url = f"{GRAPH}/drives/{item_drive}/items/{it['id']}/content"
            fd, tmp_path = tempfile.mkstemp()
            with os.fdopen(fd, "wb") as tmp, graph_get(content_url, stream=True) as resp:
                for chunk in resp.iter_content(chunk_size=4 * 1024 * 1024):
                    tmp.write(chunk)
            notebookutils.fs.cp("file://" + tmp_path, dest, True)
            copied += 1
            status = "copied"
        except Exception as e:   # noqa: BLE001 - record and continue
            errors += 1
            status = f"error: {e}"
            if is_file:
                copy_failed.add(it["id"])
        finally:
            # Always clean up: a failed download or copy used to leave its temp file
            # on the driver's local disk, which fills up over a large library.
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        if status is not None:
            audit.append(dict(site=site_url, library=library_name, name=it.get("name"),
                              item_id=it["id"], size=int(it.get("size") or 0),
                              status=status, dest=dest, ts_utc=_now()))
        if len(audit) >= 200:
            write_audit(audit); audit = []
    write_audit(audit)
    # Relocations are applied before the inventory is written, because they are
    # detected by comparing this run's paths with the ones recorded last time.
    keep_old, move_errors, moved = apply_relocations(relocated_items(events), events, copy_failed)
    for item_id in keep_old:
        events.pop(item_id, None)
    errors += move_errors
    write_inventory(events, replace_scope=state.get("full_enumeration", False) and errors == 0)
    # Advance the watermark only on a clean run (no errors), so failed files are
    # re-enumerated and retried next time. A clean 'full' run also sets the
    # baseline so subsequent 'incremental' runs resume correctly.
    if errors == 0 and state.get("delta_link"):
        write_watermark(site_key(), state["delta_link"])
    return dict(copied=copied, skipped=skipped, errors=errors, relocated=moved,
                inventoried=sum(1 for row in events.values() if row is not None),
                resynced=state.get("resynced", False))

# CELL ========================================================================
# Entry point
if site_url:
    outcome = migrate()
    result = {"site": site_url, "library": library_name, "mode": mode, **outcome}
    print(json.dumps(result))
    notebookutils.notebook.exit(json.dumps(result))
else:
    # No site configured -> smoke mode: prove the OneLake write path works.
    require_onelake_target()
    notebookutils.fs.put(files_uri("_smoketest", "hello.txt"),
                         "onelake write ok @ " + _now(), True)
    (spark.createDataFrame([Row(check="onelake_write", status="ok", ts_utc=_now())])
        .write.mode("overwrite").option("overwriteSchema", "true")
        .format("delta").save(table_uri("migration_smoke")))
    print("SMOKE_OK")
    notebookutils.notebook.exit("SMOKE_OK")
