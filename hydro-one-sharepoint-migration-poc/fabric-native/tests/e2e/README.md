# End-to-end test: the real migration notebook in Fabric, SharePoint simulated

`run_e2e.py` builds a notebook from three parts and runs it as a Fabric notebook job:

1. `fake_graph.py`: an in-memory SharePoint answering the notebook's calls to
   login.microsoftonline.com and graph.microsoft.com, shaped like Graph's real responses.
2. The cells of `Migrate_SharePoint_Content/notebook.py`, unchanged, minus the entry-point cell.
3. `driver.py`: runs `migrate()` through the scenarios below and checks OneLake and the Delta
   tables after each one, then writes `Files/_e2e/results.json`.

Everything except Graph is real: Spark, Delta MERGE/UPDATE/DELETE, OneLake writes, moves and
deletes through `notebookutils.fs`, and the Fabric notebook runtime.

```
az login
python run_e2e.py <workspace-id>
```

It runs `notebooks/Migrate_SharePoint_Content/notebook.py` from this repo; pass a second argument to test
another copy of the notebook.

The workspace needs a capacity. The script creates a Lakehouse `HydroOneE2E` and a notebook
`E2E_Migrate_Harness`, and clears the test folders and tables first, so every run starts empty.

| Scenario | What changes in SharePoint | Checked |
|---|---|---|
| S0 | A library with `#`, `%`, `&`, `=`, `;`, `+`, quotes, brackets, accents, CJK and spaces in names | Every file lands with identical bytes |
| S1 full | Nested folders, same-named files in two folders, empty and 5 MB files; children listed before parents, one item listed twice; a 401 mid-feed and a 429 on a download | Bytes, paths, token refresh, 13 inventory rows, watermark, audit |
| S2 incremental | Modify, add, delete, and rename a folder (Graph returns only the folder) | Only changed files copied; folder contents moved; old path gone; deleted file kept in OneLake but removed from inventory; child paths rewritten |
| S3 | Move a file to another folder | New path present, old copy removed, inventory updated |
| S4 | One download fails every attempt (500) | Error counted and audited; other files copied; watermark held; next run copies it and advances the watermark |
| S5 | Saved delta link expired (410 Gone) | Resyncs, no failure, new file copied |
| S6 | Full run | Inventory equals SharePoint exactly |
| Final | | OneLake equals SharePoint byte for byte, plus the deleted file kept by design |

Not covered: Graph's real responses and limits (a real-tenant run covers those: 30 files in June
2026), very large libraries, and Key Vault (the run passes `client_secret` directly).

Results on 2026-11-17 (Microsoft test tenant, F8 capacity): 34/34 checks passed on three consecutive runs.
