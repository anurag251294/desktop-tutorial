# Interac Demo — Fabric Build Guide

End-to-end build in the Fabric portal for the **Interac HR Power BI demo**. Assumes the lakehouse has been provisioned and CSVs loaded to Delta tables (see `load_csvs_to_delta.py`).

## Environment

| Component | Value |
|---|---|
| Tenant | `MngEnvMCAP510531.onmicrosoft.com` |
| Capacity | `fabdemo85829` (F2, Canada Central) |
| Workspace | `InteracHRDemo` (`2690ef29-1370-476c-b28c-58a505fea2bd`) |
| Lakehouse | `InteracHR_Lakehouse` (`454b4c50-e93e-4ce6-9c17-1d03a6ed9d6a`) |
| Portal URL | `https://app.powerbi.com/groups/2690ef29-1370-476c-b28c-58a505fea2bd` |

## Tables in the lakehouse

```
dim_date            (1,970 rows)
dim_department      (   26 rows)
dim_role            (   40 rows)
dim_location        (    7 rows)
dim_employee        (  898 active / 1,221 total)
fact_headcount_snapshot  (28k+ rows, monthly)
fact_attrition           (206 rows)
fact_compensation        (2,484 rows)
fact_recruitment         (1,060 rows)
fact_training_completion (8,651 rows)
fact_attestation         (3,592 rows)
```

---

## Step 1 — Semantic model on Direct Lake

1. Open the lakehouse → top-right toggle to **SQL endpoint** view.
2. Click **Reporting → Manage default semantic model**.
3. Add all 11 tables. Save.
4. Go back to workspace → open the auto-created semantic model (`InteracHR_Lakehouse`).

### Relationships (star schema)

Build these in the Model view:

```
dim_employee[employee_id]            --*  fact_headcount_snapshot[employee_id]
dim_employee[employee_id]            --*  fact_attrition[employee_id]
dim_employee[employee_id]            --*  fact_compensation[employee_id]
dim_employee[employee_id]            --*  fact_training_completion[employee_id]
dim_employee[employee_id]            --*  fact_attestation[employee_id]
dim_employee[employee_id]            --*  fact_recruitment[hired_employee_id]  (inactive)

dim_department[department_id]        --*  dim_employee[department_id]
dim_department[department_id]        --*  fact_headcount_snapshot[department_id]
dim_department[department_id]        --*  fact_attrition[department_id]
dim_department[department_id]        --*  fact_recruitment[department_id]
dim_department[department_id]        --*  fact_training_completion[department_id]
dim_department[department_id]        --*  fact_attestation[department_id]
dim_department[department_id]        --*  fact_compensation[department_id]

dim_role[role_id]                    --*  dim_employee[role_id]
dim_role[role_id]                    --*  fact_headcount_snapshot[role_id]
dim_role[role_id]                    --*  fact_attrition[role_id]
dim_role[role_id]                    --*  fact_compensation[role_id]
dim_role[role_id]                    --*  fact_recruitment[role_id]

dim_location[location_id]            --*  dim_employee[location_id]
dim_location[location_id]            --*  fact_headcount_snapshot[location_id]
dim_location[location_id]            --*  fact_attrition[location_id]
dim_location[location_id]            --*  fact_training_completion[location_id]
dim_location[location_id]            --*  fact_recruitment[location_id]

dim_date[date]                       --*  fact_headcount_snapshot[snapshot_date]
dim_date[date]                       --*  fact_attrition[termination_date]
dim_date[date]                       --*  fact_compensation[effective_date]
dim_date[date]                       --*  fact_recruitment[posting_date]    (inactive)
dim_date[date]                       --*  fact_recruitment[hire_date]
dim_date[date]                       --*  fact_training_completion[due_date]
dim_date[date]                       --*  fact_attestation[due_date]
```

Mark `dim_date` as a date table (column `date`).

---

## Step 2 — DAX measures

Create a **Measures** table (Home → New table → `Measures = ROW("placeholder", BLANK())`), hide the placeholder column, then add these.

### Headcount

```dax
Active Employees =
CALCULATE(
    DISTINCTCOUNT(fact_headcount_snapshot[employee_id]),
    LASTDATE(fact_headcount_snapshot[snapshot_date])
)

Active Employees (As of Date) =
VAR _maxDate = MAX(fact_headcount_snapshot[snapshot_date])
RETURN
    CALCULATE(
        DISTINCTCOUNT(fact_headcount_snapshot[employee_id]),
        fact_headcount_snapshot[snapshot_date] = _maxDate
    )

Tech Employees =
CALCULATE(
    [Active Employees],
    dim_role[is_tech_role] = "Yes"
)

% Tech =
DIVIDE([Tech Employees], [Active Employees])

% Female =
VAR _female =
    CALCULATE(
        [Active Employees],
        dim_employee[gender] = "F"
    )
RETURN DIVIDE(_female, [Active Employees])

% Female (Tech) =
VAR _f =
    CALCULATE(
        [Active Employees],
        dim_employee[gender] = "F",
        dim_role[is_tech_role] = "Yes"
    )
RETURN DIVIDE(_f, [Tech Employees])
```

### Attrition

```dax
Terminations (Period) =
COUNTROWS(fact_attrition)

Terminations LTM =
CALCULATE(
    [Terminations (Period)],
    DATESINPERIOD(dim_date[date], TODAY(), -12, MONTH)
)

Avg Headcount LTM =
VAR _months =
    CALENDAR(EDATE(TODAY(), -12), TODAY())
VAR _agg =
    AVERAGEX(
        VALUES(fact_headcount_snapshot[snapshot_date]),
        CALCULATE(DISTINCTCOUNT(fact_headcount_snapshot[employee_id]))
    )
RETURN _agg

Attrition Rate LTM =
DIVIDE([Terminations LTM], [Avg Headcount LTM])

Regrettable Attrition LTM =
CALCULATE(
    [Terminations LTM],
    fact_attrition[regrettable] = "Yes"
)

% Regrettable LTM =
DIVIDE([Regrettable Attrition LTM], [Terminations LTM])

Voluntary Attrition LTM =
CALCULATE(
    [Terminations LTM],
    fact_attrition[termination_type] = "Voluntary"
)
```

### Recruitment

```dax
Open Reqs =
CALCULATE(
    DISTINCTCOUNT(fact_recruitment[req_id]),
    fact_recruitment[status] = "Open"
)

Hires LTM =
CALCULATE(
    DISTINCTCOUNT(fact_recruitment[req_id]),
    fact_recruitment[status] = "Filled",
    DATESINPERIOD(dim_date[date], TODAY(), -12, MONTH)
)

Avg Time to Fill (days) =
CALCULATE(
    AVERAGE(fact_recruitment[time_to_fill_days]),
    fact_recruitment[status] = "Filled"
)

Pipeline Conversion =
DIVIDE(
    SUM(fact_recruitment[offers_accepted]),
    SUM(fact_recruitment[applicants])
)
```

### Compensation

```dax
Total Base Salary (Active) =
CALCULATE(
    SUMX(VALUES(dim_employee[employee_id]), MAX(dim_employee[current_base_salary_cad])),
    dim_employee[status] = "Active"
)

Avg Base Salary =
CALCULATE(
    AVERAGE(dim_employee[current_base_salary_cad]),
    dim_employee[status] = "Active"
)

Comp Ratio vs Market =
VAR _empAvg =
    AVERAGEX(
        FILTER(dim_employee, dim_employee[status] = "Active"),
        dim_employee[current_base_salary_cad]
    )
VAR _mktAvg =
    AVERAGEX(
        FILTER(dim_employee, dim_employee[status] = "Active"),
        RELATED(dim_role[market_median_salary])
    )
RETURN DIVIDE(_empAvg, _mktAvg)

Below Market Comp Count =
SUMX(
    FILTER(dim_employee, dim_employee[status] = "Active"),
    IF(
        DIVIDE(dim_employee[current_base_salary_cad],
               RELATED(dim_role[market_median_salary])) < 0.95,
        1, 0
    )
)
```

### Compliance

```dax
Mandatory Training Completion % =
VAR _total =
    CALCULATE(
        COUNTROWS(fact_training_completion),
        fact_training_completion[is_mandatory] = "Yes"
    )
VAR _done =
    CALCULATE(
        COUNTROWS(fact_training_completion),
        fact_training_completion[is_mandatory] = "Yes",
        fact_training_completion[status] = "Completed"
    )
RETURN DIVIDE(_done, _total)

Overdue Mandatory Training =
CALCULATE(
    COUNTROWS(fact_training_completion),
    fact_training_completion[is_mandatory] = "Yes",
    fact_training_completion[status] = "Overdue"
)

COI Overdue 90+ Days =
CALCULATE(
    COUNTROWS(fact_attestation),
    fact_attestation[attestation_type] = "ATT-COI",
    fact_attestation[status] = "Overdue",
    fact_attestation[days_overdue] >= 90
)

FINTRAC Training Completion % =
VAR _t =
    CALCULATE(
        COUNTROWS(fact_training_completion),
        fact_training_completion[regulator] = "FINTRAC"
    )
VAR _c =
    CALCULATE(
        COUNTROWS(fact_training_completion),
        fact_training_completion[regulator] = "FINTRAC",
        fact_training_completion[status] = "Completed"
    )
RETURN DIVIDE(_c, _t)
```

---

## Step 3 — Report pages

Create a new report on the semantic model. 6 pages.

### Page 1 — Executive Overview

Layout: 4 KPI cards across top, 2 large visuals below.

| Visual | Field/Measure | Notes |
|---|---|---|
| Card | `[Active Employees]` | "Headcount" |
| Card | `[Attrition Rate LTM]` | % format |
| Card | `[% Regrettable LTM]` | % format, red if > 25% |
| Card | `[Open Reqs]` | "Active reqs" |
| Line chart | `dim_date[year_month]` × `[Active Employees]` | 24-month trend |
| Stacked bar | `dim_department[function]` × `[Active Employees]` | grouped by gender |

### Page 2 — Workforce Composition

| Visual | Detail |
|---|---|
| Donut | `dim_role[role_family]` × `[Active Employees]` |
| Stacked column | `dim_department[function]` × `[Active Employees]` by `dim_employee[gender]` |
| Map | `dim_location[city]` × `[Active Employees]` (filled map of Canada) |
| Matrix | Rows: `dim_role[role_level]`. Columns: `dim_employee[gender]`. Values: `[Active Employees]`, `[% Female]` |
| Bar | `dim_employee[ethnicity]` × `[Active Employees]` |

### Page 3 — Attrition Deep Dive

| Visual | Detail |
|---|---|
| Card | `[Terminations LTM]`, `[Attrition Rate LTM]`, `[% Regrettable LTM]` |
| Line | `dim_date[year_month]` × `[Terminations (Period)]` (LTM filter) — **highlight the Q4-25 Payments Platform spike** |
| Treemap | `dim_department[department_name]` × `[Regrettable Attrition LTM]` |
| Decomposition Tree | Analyze `[Regrettable Attrition LTM]` → split by department, role_family, role_level, location, gender |
| Key Influencers | Analyze `fact_attrition[regrettable]` ("Yes") → explained by department, role_level, location, manager_id |
| Bar | `fact_attrition[termination_reason]` × count |

### Page 4 — Talent Acquisition

| Visual | Detail |
|---|---|
| Card | `[Open Reqs]`, `[Hires LTM]`, `[Avg Time to Fill (days)]`, `[Pipeline Conversion]` |
| Funnel | applicants → interviewed → offers_made → offers_accepted |
| Bar | `fact_recruitment[source_channel]` × `[Hires LTM]` |
| Line | `dim_date[year_month]` × `[Avg Time to Fill (days)]` |

### Page 5 — Compensation

| Visual | Detail |
|---|---|
| Card | `[Avg Base Salary]`, `[Comp Ratio vs Market]`, `[Below Market Comp Count]` |
| Bar | `dim_department[function]` × `[Comp Ratio vs Market]` |
| Scatter | X = `dim_role[market_median_salary]`, Y = `[Avg Base Salary]`, bubbles by role |
| Histogram | `dim_employee[current_base_salary_cad]` distribution |

### Page 6 — Compliance & Risk

| Visual | Detail |
|---|---|
| Card | `[FINTRAC Training Completion %]`, `[Mandatory Training Completion %]`, `[COI Overdue 90+ Days]` |
| Bar | `fact_training_completion[regulator]` × `[Mandatory Training Completion %]` |
| Table | Employees with `[COI Overdue 90+ Days]` — `full_name`, `department_name`, `manager`, `days_overdue` |
| Stacked bar | `dim_department[function]` × overdue trainings |

---

## Step 4 — RLS (Row-Level Security)

In semantic model → Security → Manage roles:

```dax
[Role: HR Business Partner]
-- no filter (sees everyone)

[Role: People Manager]
-- only sees own org chain
[dim_employee][manager_id] = USERNAME() ||
[dim_employee][employee_id] = USERNAME()

[Role: Compliance Officer]
-- can only see compliance pages (enforce via page-level filters too)
[dim_department][function] = "Risk & Compliance" || TRUE()
```

For the demo, use **View as Role → People Manager** with a test username from `dim_employee[manager_id]`.

---

## Step 5 — Sensitivity labels

In the semantic model → Sensitivity → apply **Confidential \\ HR**. Show that the label propagates to:

- The report
- Any export (PPT, PDF, Excel)
- Downstream pinned dashboard tiles

This is the **Microsoft Purview Information Protection** story — label once, enforced everywhere.

---

## Step 6 — Copilot in Power BI prompts

In the published report → top-right Copilot button. Try these prompts live:

1. *"Summarize the attrition story for the last 12 months."*
2. *"Which department has the highest regrettable attrition?"*
3. *"Build me a page for our compliance officer."*
4. *"What is the gender split in our engineering function?"*
5. *"Create a measure for Year-over-Year change in active headcount."*

Note: Copilot in Power BI requires F64 capacity for Service-side authoring. **F2 capacity (current setup) supports Copilot in semantic model + Q&A only**, NOT report authoring. For full demo, mention "in production we'd run on F64+ for in-report Copilot — same experience, just upgrade the SKU".

---

## Verification before demo

```powershell
# Confirm capacity Active
az resource show -g rg-fabric-demo -n fabdemo85829 `
  --resource-type Microsoft.Fabric/capacities `
  --query "properties.state" -o tsv
# Expected: Active

# List tables in lakehouse
$tok = az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv
$h = @{ Authorization = "Bearer $tok" }
(Invoke-RestMethod -Headers $h -Uri "https://api.fabric.microsoft.com/v1/workspaces/2690ef29-1370-476c-b28c-58a505fea2bd/lakehouses/454b4c50-e93e-4ce6-9c17-1d03a6ed9d6a/tables").data | Format-Table name, type
# Expected: 11 tables, all type=Managed
```

## Cost control

**Always pause the capacity after the demo:**

```powershell
az resource invoke-action --action suspend `
  --resource-group rg-fabric-demo `
  --name fabdemo85829 `
  --resource-type Microsoft.Fabric/capacities
```
