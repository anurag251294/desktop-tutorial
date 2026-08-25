# Demo runbook — TCHC Fabric deep dive

Maps to the agenda for **Thursday 27 August 2026**. Sixty minutes of demo across agenda
items 4, 5 and 6, plus what to say for 7 and 8.

The through-line: **one copy of the data, three layers of treatment, one model, and the
arrears number is a calculation you can inspect rather than a column somebody exported.**

> **Everything is synthetic.** 120 buildings, roughly 9,000 units, 24 months. No TCHC
> system was contacted and no real tenant data exists anywhere in this demo. Say this in
> the first minute — the vocabulary is deliberately realistic (RGI and market rent, unit
> turnaround, arrears aging) and people will otherwise wonder.

## Environment

| | |
| --- | --- |
| Workspace | `TCHC_Fabric_Demo` on `fabdemo85829` (F64, Canada Central) |
| Lakehouses | `bronze_lakehouse`, `silver_lakehouse`, `gold_lakehouse` |
| Pipeline | `pl_tchc_medallion` |
| Semantic model | `TCHC_Arrears_Vacancy` — Direct Lake |
| Report | `TCHC_Arrears_and_Vacancy` — three pages |

> **Resume the capacity 30 minutes before, not 5.** It reports Active within a minute,
> but Fabric item editors stay unavailable for roughly 20–25 minutes after a resume while
> every backend check passes. There is nothing to fix and no way to hurry it.

---

## Item 4 — Landing TCHC data in OneLake (20 min)

**Open the workspace and show the three lakehouses.**

* One OneLake per tenant. Bronze, Silver and Gold are three lakehouses over **the same
  storage**, not three copies. The medallion is a treatment convention, not a storage one.
* Open `bronze_lakehouse` → **Files** and **Tables** side by side. Delta tables are the
  same Parquet files any engine can read; nothing is locked into a proprietary format.

**Then open `bronze_source_extracts` and show the parameters cell.**

The demo generates its extracts, but the shape is the point: two systems, landed
verbatim, nothing cleaned on the way in.

**What to say about the ingestion options, since only some can be shown live:**

| Option | Where it fits at TCHC | Demoable today |
| --- | --- | --- |
| **Shortcut** | Data already in ADLS or another lakehouse. No copy, no pipeline, no latency. | Yes — create one live |
| **Mirroring** | A supported source database, continuously replicated with no pipeline to maintain | No — needs a real source |
| **Data Factory pipeline** | Scheduled extracts from a system with an API or database | Yes — `pl_tchc_medallion` |
| **Dataflow Gen2** | Low-code transformation, closer to a Power Query audience | Discuss |
| **On-prem / VNet gateway** | Whichever TCHC source systems are not internet-reachable | No — needs a host |

> Be straight that mirroring and the gateway are architecture conversation, not live
> demo. Both need something on TCHC's side that does not exist yet, and pretending
> otherwise sets up a disappointment in the first sprint.

**This is the moment to ask the prepared questions** — system of record for arrears
balances, system of record for vacancy, on-prem or cloud, and what integration surface
exists. The answers change which row of that table the engagement actually uses.

---

## Item 5 — Medallion in practice (20 min)

**Open `bronze_lakehouse` and preview `bronze_fin_receipts`.**

Point at the columns: `posting_date` is text, `amount_cad` is text with a currency
symbol, and the account key is `tenant_account` while the charges table calls the same
thing `household_ref`.

> "This is what an extract actually looks like. Bronze's job is to be a faithful record
> of what arrived, including its problems. If we clean on the way in, we lose the ability
> to prove what the source sent."

**Then open `silver_conformed` and scroll to the data quality output.**

The layer has to fix six specific things, and each is worth naming:

| Problem | Handling |
| --- | --- |
| Two date formats — `dd/mm/yyyy` and `mm/dd/yyyy` | Parsed per source system, never guessed |
| Money as `"$1,234.56"` | Stripped and cast |
| Five spellings of two tenure concepts | One controlled vocabulary |
| A re-sent receipts batch | Deduplicated on the natural key |
| Receipts for unknown accounts | **Quarantined** |
| Work orders with unresolvable units | **Quarantined** |

**Open `silver_quarantine` and let it sit on screen for a moment.**

> "These rows did not make it into the numbers, and here they are with the reason. If we
> had dropped the orphan receipts silently, arrears would read higher than it is and
> nobody downstream could tell. Quarantine is the difference between a number you can
> defend and one you can only report."

**On the date formats specifically** — parsing the finance file with the property system's
pattern would silently transpose day and month for the first twelve days of every month.
It would not error. It would just be wrong, quietly, forever.

**Lakehouse versus Warehouse**, since the agenda asks:

* **Lakehouse** — Spark and notebooks, files and tables together, best where the work is
  transformation and data engineering. That is Bronze and Silver here.
* **Warehouse** — T-SQL, multi-table transactions, a familiar surface for a SQL team.
  Reasonable for Gold if TCHC's analysts live in SQL.
* Both sit on the same OneLake storage and both are queryable from either engine, so
  this is a team-skills decision far more than a technical one.

---

## Item 6 — From curated data to a decision (20 min)

**Open `gold_star_schema` and show how arrears is calculated.**

This is the most important five minutes of the session.

> "Arrears is not a column in any source system. It is what is left when receipts have
> not covered charges. We allocate receipts **to the oldest outstanding charge first**,
> because that is how a rent account actually settles, and the aging bucket follows the
> oldest charge still carrying a balance."

Then say what the easy version gets wrong:

> "If you just compare this month's charge to this month's payment, a household that pays
> two weeks late every month looks permanently in arrears, and a household that missed a
> month last year and never made it up looks fine. Both answers are wrong in ways that
> reach a caseworker."

**Open the semantic model and show Direct Lake.**

* Direct Lake reads the Delta files directly. **No import, no scheduled refresh, no
  second copy.** When the pipeline writes, the model sees it.
* Import is a copy in memory — fastest queries, but a refresh schedule and a data latency.
* DirectQuery sends every query to the source — always current, slowest, and it puts your
  reporting load on the source system.
* Direct Lake is the reason the medallion and the semantic layer are not two projects.

**Then open the report — `TCHC_Arrears_and_Vacancy`.**

| Page | Shows |
| --- | --- |
| **Arrears overview** | Portfolio position, trend, aging profile, concentration by ward and tenure |
| **Arrears deep dive** | Slice by region, tenure and unit size; the table underneath is the caseload view |
| **Vacancy and turnaround** | Vacancy rate, revenue forgone, turnaround days by category |

**On the vacancy page, point at "Turnarounds open".**

> "Average turnaround counts only completed work orders. An unfinished turnaround has an
> unknown duration, not a zero one, so it is reported separately rather than averaged in.
> Averaging it in would make performance look better the longer a unit sits empty."

That single design decision is the closest thing in the demo to what the MVP argument is
actually about.

---

## Item 7 — Security, privacy and data protection (15 min)

Discussion, not demo. The honest framing:

* **Workspace roles** — Admin, Member, Contributor, Viewer. Coarse, and the first control
  to get right.
* **OneLake data access roles** — folder-level control within a lakehouse, so a team can
  reach Gold without reaching Bronze.
* **Row-level security** in the semantic model — a caseworker sees their own portfolio,
  a director sees everything. Defined in the model, enforced for every report over it.
* **Object-level security** — hide a column or a table entirely from a role, which
  matters for anything identifying at the household grain.
* **Sensitivity labels** via Purview Information Protection, which travel with exports.
* **Private endpoints** — Fabric supports them; the network path is a design decision to
  make with TCHC's network team early, not in sprint three.

**The question to put back to the room:** whether the development environment uses live,
masked, or synthetic tenant data. This demo is entirely synthetic, deliberately. That is
the safest default for a build environment and it is worth deciding on purpose rather
than by omission, because it constrains how the first sprint is staffed and where it runs.

---

## Item 8 — Governance, capacity and operations (10 min)

* **Domains and workspaces** — one workspace per environment per domain is the usual
  starting shape. Decide the naming convention before the first workspace, not after the
  fifth.
* **Purview** — lineage across OneLake, so "where did this number come from" has an
  answer that is not a person.
* **Capacity** — F-SKUs are capacity units, shared across everything in the tenant.
  Interactive queries and background jobs draw on the same pool, and Fabric smooths
  bursts over time. The Capacity Metrics app is where you see what is actually consuming.
* **Git integration** — this entire demo is in a repository: notebooks, pipeline, model
  and report definitions. Deployment pipelines promote between workspaces.

> On sizing: resist quoting an F-SKU today. It depends on volume, refresh pattern and
> concurrency, and none of those are known yet. It is on the pre-kickoff checklist for
> a reason.

---

## If something goes wrong

| Symptom | Cause | Do |
| --- | --- | --- |
| Fabric item editors will not open | Capacity resumed under ~25 minutes ago | Wait. Show the repo and the architecture meanwhile |
| Report shows blank visuals | Semantic model has not reframed since the last write | `POST datasets/{id}/refreshes` with `{"type":"full"}` |
| Model cannot see a new table | SQL endpoint has not synced | `POST /sqlEndpoints/{id}/refreshMetadata?preview=true` |
| A slicer renders empty | Known PBIR quirk below ~48px height | Already sized correctly here |

## Reset

```bash
python scripts/fabric/provision_fabric_demo.py \
  --config cicd/fabric-setup.config.json --output cicd/fabric-setup.output.json
python scripts/fabric/run_pipeline.py --output cicd/fabric-setup.output.json
python scripts/fabric/create_semantic_model.py --output cicd/fabric-setup.output.json
python scripts/fabric/build_report.py --output cicd/fabric-setup.output.json
```

Idempotent — existing items are updated rather than duplicated.
