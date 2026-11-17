# E2E harness, last cell: run the real migrate() through a series of SharePoint changes and
# check OneLake and the Delta tables after each one. Results go to Files/_e2e/results.json.
import hashlib, json, random, tempfile, traceback

RESULTS = []
SITE = f"https://{HOST}/sites/E2E"


def check(scenario, name, ok, detail=""):
    RESULTS.append({"scenario": scenario, "check": name, "ok": bool(ok), "detail": str(detail)[:600]})
    print(("PASS " if ok else "FAIL ") + f"[{scenario}] {name}" + (f" -- {detail}" if detail and not ok else ""))


def run(lib, run_mode):
    """One migration run, as a fresh notebook run would start it."""
    global site_url, library_name, mode
    site_url, library_name, mode = SITE, lib, run_mode
    _folder_paths.clear()
    _token_cache.update(value=None, expires_at=0.0)
    out = migrate()
    print(lib, run_mode, json.dumps(out))
    return out


def onelake_files(lib):
    """Relative path -> bytes for every file under Files/<site>/<library> in OneLake."""
    global library_name
    library_name = lib
    root = onelake_path("")
    found = {}

    def walk(p, rel):
        for f in notebookutils.fs.ls(p):
            r = f"{rel}/{f.name}".strip("/")
            if f.isDir:
                walk(f.path.rstrip("/"), r)
            else:
                fd, local = tempfile.mkstemp()
                os.close(fd)
                notebookutils.fs.cp(f.path, "file://" + local, True)
                with open(local, "rb") as fh:
                    found[r] = fh.read()
                os.remove(local)

    if notebookutils.fs.exists(root):
        walk(root, "")
    return found


def inventory(lib):
    df = (spark.read.format("delta").load(table_uri(inventory_table))
          .where((F.col("site") == SITE) & (F.col("library") == lib)))
    return {r["item_id"]: r.asDict() for r in df.collect()}


def watermark(lib):
    global library_name
    library_name = lib
    return read_watermark(site_key())


def same_bytes(expected, actual):
    bad = [p for p, b in expected.items() if actual.get(p) is None or
           hashlib.md5(actual[p]).hexdigest() != hashlib.md5(b).hexdigest()]
    return bad


try:
    workspace_id, lakehouse_id = "__WORKSPACE_ID__", "__LAKEHOUSE_ID__"
    tenant_id, client_id, client_secret = "tenant-1", "client-1", "fake-secret"

    # ---------------------------------------------------------------- S0: unusual names
    odd = FAKE.add_drive(Drive("drive-2", "Odd Names"))
    f1 = odd.mkdir("folder with spaces")
    f2 = odd.mkdir("100% done")
    f3 = odd.mkdir("über")
    odd.put("Report #1 (50%).txt", "root", b"hash and percent")
    odd.put("Café – ñ résumé.docx", "root", b"accents and en dash")
    odd.put("a&b=c;d+e.txt", f1, b"query characters")
    odd.put("#tag.txt", f2, b"leading hash")
    odd.put("naïve 文件.txt", f3, b"unicode")
    odd.put("it's ~ok~ [v2] {x}.txt", "root", b"quote tilde brackets")
    out = run("Odd Names", "full")
    check("S0 odd names", "no errors", out["errors"] == 0, out)
    got = onelake_files("Odd Names")
    bad = same_bytes(odd.files(), got)
    check("S0 odd names", "every file in OneLake with identical bytes", not bad, f"missing/different: {bad}; found: {sorted(got)}")

    # ---------------------------------------------------------------- S1: full run
    d = FAKE.add_drive(Drive("drive-1", "Documents"))
    A = d.mkdir("A"); B = d.mkdir("B", A)
    spec = d.put("spec.txt", B, b"spec v1")
    ra = d.put("readme.txt", A, b"A readme v1")
    C = d.mkdir("C")
    rc = d.put("readme.txt", C, b"C readme")           # same name, different folder
    data = d.put("data.csv", C, b"id,value\n1,2\n")
    X = d.mkdir("X"); Y = d.mkdir("Y", X)
    deep = d.put("deep.txt", Y, b"deep")
    empty = d.put("empty.bin", "root", b"")
    big = d.put("big.bin", "root", random.Random(7).randbytes(5 * 1024 * 1024))
    notes = d.put("notes.txt", "root", b"deleted later")
    # Children before their parents, and one item twice, as Graph allows.
    d.fresh_order = [spec, A, B, ra, rc, C, rc, data, deep, X, Y, empty, big, notes]
    FAKE.fault("skip=3", 401)                                          # token rejected mid-feed
    FAKE.fault(f"/items/{big}/content", 429, headers={"Retry-After": "1"})   # throttled download
    posts_before = FAKE.token_posts
    out = run("Documents", "full")
    FAKE.clear_faults()
    check("S1 full", "no errors", out["errors"] == 0, out)
    check("S1 full", "all 8 files copied (the repeated item may count twice)", out["copied"] in (8, 9), out)
    check("S1 full", "token refreshed after the 401", FAKE.token_posts - posts_before == 2, FAKE.token_posts - posts_before)
    got = onelake_files("Documents")
    bad = same_bytes(d.files(), got)
    check("S1 full", "every file in OneLake with identical bytes", not bad, f"{bad}; found {sorted(got)}")
    check("S1 full", "same-named files kept apart", got.get("A/readme.txt") == b"A readme v1" and got.get("C/readme.txt") == b"C readme")
    inv = inventory("Documents")
    check("S1 full", "inventory has 13 items (5 folders, 8 files)", len(inv) == 13, len(inv))
    check("S1 full", "inventory paths correct", inv.get(spec, {}).get("relative_path") == "A/B/spec.txt", inv.get(spec))
    wm1 = watermark("Documents")
    check("S1 full", "watermark saved", bool(wm1), wm1)
    audit = (spark.read.format("delta").load(table_uri(audit_table))
             .where((F.col("library") == "Documents") & (F.col("status") == "copied")).count())
    check("S1 full", "audit has a copied row per file", audit in (8, 9), audit)

    # ---------------------------------------------------------------- S2: modify, add, delete, rename folder
    d.modify(ra, b"A readme v2")
    new = d.put("new.txt", C, b"new file")
    d.delete(notes)
    d.rename(A, "A-renamed")
    out = run("Documents", "incremental")
    check("S2 incremental", "no errors", out["errors"] == 0, out)
    check("S2 incremental", "only the 2 changed files copied", out["copied"] == 2, out)
    got = onelake_files("Documents")
    check("S2 incremental", "folder contents moved to the new name",
          got.get("A-renamed/B/spec.txt") == b"spec v1" and got.get("A-renamed/readme.txt") == b"A readme v2",
          sorted(got))
    check("S2 incremental", "nothing left at the old folder path", not any(p.startswith("A/") for p in got), sorted(got))
    check("S2 incremental", "deleted file kept in OneLake (by design)", got.get("notes.txt") == b"deleted later")
    inv = inventory("Documents")
    check("S2 incremental", "deleted file removed from inventory", notes not in inv)
    check("S2 incremental", "child path rewritten in inventory", inv.get(spec, {}).get("relative_path") == "A-renamed/B/spec.txt", inv.get(spec))
    wm2 = watermark("Documents")
    check("S2 incremental", "watermark advanced", wm2 and wm2 != wm1, (wm1, wm2))

    # ---------------------------------------------------------------- S3: move a file
    d.move(deep, C)
    out = run("Documents", "incremental")
    got = onelake_files("Documents")
    check("S3 move file", "no errors", out["errors"] == 0, out)
    check("S3 move file", "file at new path, old copy removed",
          got.get("C/deep.txt") == b"deep" and "X/Y/deep.txt" not in got, sorted(got))
    check("S3 move file", "inventory path updated", inventory("Documents").get(deep, {}).get("relative_path") == "C/deep.txt")

    # ---------------------------------------------------------------- S4: a download keeps failing
    wm3 = watermark("Documents")
    flaky = d.put("flaky.txt", C, b"flaky")
    ok = d.put("ok.txt", C, b"ok")
    FAKE.fault(f"/items/{flaky}/content", 500, times=99, headers={"Retry-After": "0"})
    out = run("Documents", "incremental")
    FAKE.clear_faults()
    got = onelake_files("Documents")
    check("S4 failing download", "error reported", out["errors"] == 1, out)
    check("S4 failing download", "other new file still copied", got.get("C/ok.txt") == b"ok")
    check("S4 failing download", "watermark held back", watermark("Documents") == wm3)
    failed_rows = (spark.read.format("delta").load(table_uri(audit_table))
                   .where((F.col("item_id") == flaky) & F.col("status").startswith("error")).count())
    check("S4 failing download", "failure recorded in migration_audit", failed_rows == 1, failed_rows)
    out = run("Documents", "incremental")
    got = onelake_files("Documents")
    check("S4 retry", "next run copies the failed file", out["errors"] == 0 and got.get("C/flaky.txt") == b"flaky", out)
    check("S4 retry", "watermark advances once clean", watermark("Documents") != wm3)

    # ---------------------------------------------------------------- S5: expired delta link
    d.expired.add(d.seq)
    later = d.put("after-410.txt", "root", b"after resync")
    out = run("Documents", "incremental")
    check("S5 expired delta link", "resynced without failing", out["errors"] == 0 and out["resynced"], out)
    check("S5 expired delta link", "new file copied", onelake_files("Documents").get("after-410.txt") == b"after resync")

    # ---------------------------------------------------------------- S6: full run rebuilds the inventory
    out = run("Documents", "full")
    inv = inventory("Documents")
    check("S6 full rebuild", "no errors", out["errors"] == 0, out)
    expect_paths = d.all_paths()
    got_paths = {r["relative_path"] for r in inv.values()}
    check("S6 full rebuild", "inventory matches SharePoint exactly", got_paths == expect_paths,
          f"extra {sorted(got_paths - expect_paths)} missing {sorted(expect_paths - got_paths)}")

    # ---------------------------------------------------------------- final parity
    got = onelake_files("Documents")
    expected = dict(d.files()); expected["notes.txt"] = b"deleted later"
    bad = same_bytes(expected, got)
    check("Final", "OneLake matches SharePoint byte for byte", not bad, bad)
    check("Final", "no unexpected files in OneLake", set(got) == set(expected), sorted(set(got) - set(expected)))
except Exception:
    check("Harness", "ran to the end", False, traceback.format_exc())

summary = {"passed": sum(r["ok"] for r in RESULTS), "failed": sum(not r["ok"] for r in RESULTS), "results": RESULTS}
notebookutils.fs.put(files_uri("_e2e", "results.json"), json.dumps(summary, indent=1, ensure_ascii=False), True)
print(json.dumps({k: summary[k] for k in ("passed", "failed")}))
notebookutils.notebook.exit(json.dumps({k: summary[k] for k in ("passed", "failed")}))
