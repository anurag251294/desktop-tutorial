"""Generate synthetic HR data for the Interac Power BI demo.

Target persona: Canadian payments network (~1,000 active employees, Toronto HQ,
tech-heavy, OSFI/FINTRAC regulated). Story arcs the data must support:

  1. Workforce composition shows ~58% tech roles; gender split overall 47/53
     but tech roles only 32% female (DEI gap).
  2. Tech attrition (last 12 months) ~18% vs ~11% non-tech.
  3. Regrettable attrition concentrated in Senior Engineers (IC4-IC5) at ~22%,
     with a visible Q4-2025 spike in the Payments Platform team.
  4. Comp pressure: Senior IC engineers running at ~0.92x of synthetic market
     median; Risk/Compliance underpaid vs banking peers.
  5. Compliance: FINTRAC AML training 96% completion, OSFI code-of-conduct
     attestations 100% on-time, but 7 employees overdue on COI for 90+ days.
  6. Key-Influencers fodder: manager identity + role family + Toronto location
     are the top predictors of regrettable attrition.

Outputs 7 CSVs to ./data/. Deterministic via seed.
"""
from __future__ import annotations

import csv
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path

SEED = 20260524
random.seed(SEED)

OUT = Path(__file__).parent / "data"
OUT.mkdir(parents=True, exist_ok=True)

TODAY = date(2026, 5, 24)
START = date(2022, 1, 1)
SNAPSHOT_DATES = []
cur = date(2022, 1, 31)
while cur <= TODAY:
    SNAPSHOT_DATES.append(cur)
    # Move to last day of next month
    nm = cur.replace(day=1) + timedelta(days=32)
    cur = (nm.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    if cur > TODAY:
        break


# ---------- Reference data ----------
DEPARTMENTS = [
    # (name, function, target_active_hc, cost_center)
    ("Payments Platform",        "Engineering",      85, "CC-1001"),
    ("Money Movement",           "Engineering",      62, "CC-1002"),
    ("Core Network",             "Engineering",      55, "CC-1003"),
    ("Cyber Security",           "Engineering",      48, "CC-1004"),
    ("Data & ML Platform",       "Engineering",      45, "CC-1005"),
    ("Cloud Platform",           "Engineering",      52, "CC-1006"),
    ("Mobile & Web",             "Engineering",      38, "CC-1007"),
    ("Site Reliability",         "Engineering",      25, "CC-1008"),
    ("Product Management",       "Product",          48, "CC-2001"),
    ("Design",                   "Product",          22, "CC-2002"),
    ("Credit Risk",              "Risk & Compliance",24, "CC-3001"),
    ("Fraud & Financial Crime",  "Risk & Compliance",32, "CC-3002"),
    ("AML / FINTRAC",            "Risk & Compliance",20, "CC-3003"),
    ("OSFI Liaison & Policy",    "Risk & Compliance",10, "CC-3004"),
    ("Privacy & Data Protection","Risk & Compliance",12, "CC-3005"),
    ("Network Operations",       "Operations",       38, "CC-4001"),
    ("Settlement Operations",    "Operations",       30, "CC-4002"),
    ("Dispute Resolution",       "Operations",       28, "CC-4003"),
    ("Vendor Operations",        "Operations",       16, "CC-4004"),
    ("Customer Experience",      "Customer Experience",58, "CC-5001"),
    ("Finance",                  "Corporate",        42, "CC-6001"),
    ("Legal",                    "Corporate",        18, "CC-6002"),
    ("Human Resources",          "Corporate",        32, "CC-6003"),
    ("Marketing & Comms",        "Corporate",        28, "CC-6004"),
    ("Corporate Strategy",       "Corporate",        14, "CC-6005"),
    ("IT & Workplace",           "Corporate",        18, "CC-6006"),
]

TECH_FUNCTIONS = {"Engineering"}

# Role catalogue: (family, level, title, is_tech, base_salary_min, base_salary_max, market_median)
ROLES = [
    # IC tech
    ("Engineering", "IC1", "Associate Engineer",          True,  78_000,  95_000,   88_000),
    ("Engineering", "IC2", "Software Engineer",           True,  95_000, 118_000,  108_000),
    ("Engineering", "IC3", "Senior Software Engineer",    True, 118_000, 148_000,  140_000),
    ("Engineering", "IC4", "Staff Engineer",              True, 148_000, 185_000,  178_000),
    ("Engineering", "IC5", "Principal Engineer",          True, 180_000, 230_000,  220_000),
    ("Engineering", "IC6", "Distinguished Engineer",      True, 225_000, 285_000,  280_000),
    # IC non-tech
    ("Product",     "IC2", "Associate Product Manager",   False, 88_000, 105_000,  100_000),
    ("Product",     "IC3", "Senior Product Manager",      False,115_000, 145_000,  138_000),
    ("Product",     "IC4", "Group Product Manager",       False,145_000, 178_000,  170_000),
    ("Risk",        "IC2", "Risk Analyst",                False, 78_000,  95_000,   92_000),
    ("Risk",        "IC3", "Senior Risk Analyst",         False, 95_000, 122_000,  120_000),
    ("Risk",        "IC4", "Risk Manager",                False,122_000, 155_000,  155_000),
    ("Compliance",  "IC3", "Compliance Officer",          False, 95_000, 120_000,  118_000),
    ("Compliance",  "IC4", "Senior Compliance Officer",   False,120_000, 152_000,  150_000),
    ("Operations",  "IC1", "Operations Analyst",          False, 62_000,  78_000,   72_000),
    ("Operations",  "IC2", "Senior Operations Analyst",   False, 78_000,  98_000,   92_000),
    ("Operations",  "IC3", "Operations Lead",             False, 98_000, 125_000,  118_000),
    ("CX",          "IC1", "Customer Support Specialist", False, 55_000,  68_000,   62_000),
    ("CX",          "IC2", "Senior Support Specialist",   False, 68_000,  85_000,   80_000),
    ("Design",      "IC2", "Product Designer",            False, 88_000, 112_000,  108_000),
    ("Design",      "IC3", "Senior Product Designer",     False,112_000, 140_000,  135_000),
    ("Corporate",   "IC2", "Analyst",                     False, 70_000,  88_000,   82_000),
    ("Corporate",   "IC3", "Senior Analyst",              False, 88_000, 115_000,  108_000),
    ("Corporate",   "IC4", "Manager",                     False,115_000, 145_000,  140_000),
    # Management
    ("Management",  "M1",  "Engineering Manager",         True, 155_000, 195_000,  185_000),
    ("Management",  "M2",  "Senior Engineering Manager",  True, 185_000, 230_000,  220_000),
    ("Management",  "M3",  "Director, Engineering",       True, 220_000, 280_000,  270_000),
    ("Management",  "M2",  "Director, Product",           False,195_000, 245_000,  235_000),
    ("Management",  "M2",  "Director, Risk",              False,180_000, 225_000,  215_000),
    ("Management",  "M2",  "Director, Compliance",        False,175_000, 220_000,  210_000),
    ("Management",  "M2",  "Director, Operations",        False,160_000, 200_000,  190_000),
    ("Management",  "M3",  "VP, Engineering",             True, 280_000, 360_000,  340_000),
    ("Management",  "M3",  "VP, Product",                 False,260_000, 330_000,  315_000),
    ("Management",  "M3",  "VP, Risk & Compliance",       False,250_000, 320_000,  305_000),
    # Executive
    ("Executive",   "E1",  "Chief Technology Officer",    True, 425_000, 525_000,  500_000),
    ("Executive",   "E1",  "Chief Product Officer",       False,400_000, 500_000,  475_000),
    ("Executive",   "E1",  "Chief Risk Officer",          False,400_000, 500_000,  475_000),
    ("Executive",   "E1",  "Chief Financial Officer",     False,420_000, 525_000,  500_000),
    ("Executive",   "E1",  "Chief People Officer",        False,360_000, 450_000,  425_000),
    ("Executive",   "E2",  "Chief Executive Officer",     False,650_000, 825_000,  775_000),
]

LOCATIONS = [
    # (name, city, province, country, is_remote, weight)
    ("Toronto HQ",   "Toronto",  "ON", "Canada", False, 0.45),
    ("Calgary",      "Calgary",  "AB", "Canada", False, 0.10),
    ("Ottawa",       "Ottawa",   "ON", "Canada", False, 0.08),
    ("Remote - ON",  "Various",  "ON", "Canada", True,  0.18),
    ("Remote - AB",  "Various",  "AB", "Canada", True,  0.06),
    ("Remote - QC",  "Various",  "QC", "Canada", True,  0.07),
    ("Remote - BC",  "Various",  "BC", "Canada", True,  0.06),
]

TRAINING_COURSES = [
    # (course_id, name, mandatory, regulator, frequency_months)
    ("TRN-001", "FINTRAC AML & ATF Training",       True,  "FINTRAC", 12),
    ("TRN-002", "OSFI E-21 Operational Resilience", True,  "OSFI",    12),
    ("TRN-003", "Code of Conduct & Ethics",         True,  "Internal",12),
    ("TRN-004", "PIPEDA Privacy Foundations",       True,  "PIPEDA",  24),
    ("TRN-005", "Insider Trading Policy",           True,  "Internal",12),
    ("TRN-006", "Cyber Security Awareness",         True,  "Internal", 6),
    ("TRN-007", "Anti-Bribery & Anti-Corruption",   True,  "Internal",24),
    ("TRN-008", "Workplace Respect & Harassment",   True,  "Internal",24),
    ("TRN-009", "Payment Card Industry (PCI) DSS",  False, "PCI",     12),
    ("TRN-010", "Quantum Cryptography Primer",      False, "Internal",None),
]

ATTESTATION_TYPES = [
    ("ATT-COI", "Conflict of Interest", True, 12),
    ("ATT-COC", "Code of Conduct Attestation", True, 12),
    ("ATT-PRV", "Privacy & Data Handling", True, 12),
    ("ATT-INS", "Insider Trading Window", True, 6),
]

# Diverse Canadian first/last name pool (representative, not exhaustive)
FIRST_NAMES_F = [
    "Aanya","Aisha","Amelia","Anika","Ava","Beatrice","Camille","Catherine","Chen","Chloe",
    "Daniela","Divya","Emma","Fatima","Genevieve","Grace","Hannah","Isabella","Jessica","Julia",
    "Kavya","Layla","Lily","Mei","Mia","Nadia","Noor","Olivia","Priya","Rachel",
    "Sara","Sienna","Sofia","Sophie","Tara","Valeria","Wen","Yara","Yuki","Zara",
]
FIRST_NAMES_M = [
    "Aaron","Adrian","Ahmed","Alexander","Amir","Anthony","Arjun","Benjamin","Carlos","Chen",
    "Daniel","David","Diego","Elijah","Ethan","Felix","Gabriel","Hassan","Henry","Hugo",
    "Ibrahim","Isaac","Jacob","James","Jin","Kai","Khalid","Liam","Lucas","Mateo",
    "Mohammed","Nathan","Noah","Omar","Oscar","Pablo","Rahul","Ryan","Samir","Tarek",
    "Theo","Viktor","William","Xavier","Yusuf","Zain",
]
LAST_NAMES = [
    "Adebayo","Ahmed","Anand","Bouchard","Brown","Chen","Choudhury","Cohen","Da Silva","Davis",
    "Desjardins","Dhillon","Dubois","Fernandez","Gagnon","Garcia","Goldberg","Gupta","Hernandez","Hussain",
    "Ibrahim","Iyer","Johnson","Joshi","Kaur","Kim","Kumar","Lavoie","Leblanc","Lee",
    "Levesque","Li","Liu","Lopez","MacDonald","Martin","Martinez","Mehta","Morin","Murphy",
    "Nakamura","Nguyen","O'Brien","Okafor","Park","Patel","Pereira","Pham","Roy","Sanchez",
    "Shah","Singh","Smith","Tanaka","Taylor","Tran","Tremblay","Wang","Williams","Wong","Yamamoto","Zhang",
]
ETHNICITIES = [
    ("South Asian",     0.18),
    ("East Asian",      0.14),
    ("White",           0.42),
    ("Black",           0.06),
    ("Hispanic/Latinx", 0.05),
    ("Middle Eastern",  0.06),
    ("Indigenous",      0.02),
    ("Mixed / Other",   0.07),
]

TERMINATION_REASONS_VOL = [
    ("Better opportunity - higher comp",      0.22, True),
    ("Better opportunity - growth/scope",     0.20, True),
    ("Relocation / personal",                 0.08, False),
    ("Career change",                         0.08, False),
    ("Manager / culture",                     0.14, True),
    ("Work-life balance / burnout",           0.10, True),
    ("Return to study",                       0.04, False),
    ("Retirement",                            0.06, False),
    ("Other voluntary",                       0.08, False),
]
TERMINATION_REASONS_INV = [
    ("Performance",                            0.40, False),
    ("Role eliminated",                        0.35, False),
    ("Conduct / policy violation",             0.10, False),
    ("End of contract",                        0.15, False),
]

RECRUITMENT_CHANNELS = [
    ("LinkedIn",            0.32),
    ("Employee referral",   0.22),
    ("Agency",              0.14),
    ("University recruit",  0.08),
    ("Direct apply",        0.12),
    ("Indeed",              0.07),
    ("Conference / event",  0.05),
]


# ---------- Helpers ----------
def weighted_choice(items):
    """items is list of (value, weight)"""
    vals = [i[0] for i in items]
    wts = [i[1] for i in items]
    return random.choices(vals, weights=wts, k=1)[0]


def pick_name(gender):
    pool = FIRST_NAMES_F if gender == "F" else FIRST_NAMES_M
    return f"{random.choice(pool)} {random.choice(LAST_NAMES)}"


def write_csv(name, headers, rows):
    p = OUT / name
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)
    print(f"  wrote {p.name}  ({len(rows):,} rows)")


# ---------- Build dim_department ----------
print("Building dim_department...")
dept_rows = []
for i, (name, fn, hc, cc) in enumerate(DEPARTMENTS, start=1):
    dept_rows.append([f"DPT-{i:03d}", name, fn, cc, hc])
write_csv("dim_department.csv",
          ["department_id", "department_name", "function", "cost_center", "target_active_hc"],
          dept_rows)
dept_by_id = {r[0]: r for r in dept_rows}
dept_by_name = {r[1]: r for r in dept_rows}


# ---------- Build dim_role ----------
print("Building dim_role...")
role_rows = []
for i, (family, level, title, is_tech, smin, smax, smed) in enumerate(ROLES, start=1):
    role_rows.append([f"ROL-{i:03d}", title, family, level,
                      "Yes" if is_tech else "No", smin, smax, smed])
write_csv("dim_role.csv",
          ["role_id", "role_title", "role_family", "role_level",
           "is_tech_role", "base_salary_min", "base_salary_max", "market_median_salary"],
          role_rows)
role_by_id = {r[0]: r for r in role_rows}


# ---------- Build dim_location ----------
print("Building dim_location...")
loc_rows = []
for i, (name, city, prov, country, remote, _) in enumerate(LOCATIONS, start=1):
    loc_rows.append([f"LOC-{i:03d}", name, city, prov, country, "Yes" if remote else "No"])
write_csv("dim_location.csv",
          ["location_id", "location_name", "city", "province", "country", "is_remote"],
          loc_rows)
loc_weights = [(loc_rows[i][0], LOCATIONS[i][5]) for i in range(len(LOCATIONS))]


# ---------- Build dim_date ----------
print("Building dim_date...")
date_rows = []
d = START
while d <= TODAY + timedelta(days=365):
    iso_year, iso_week, _ = d.isocalendar()
    q = (d.month - 1) // 3 + 1
    date_rows.append([
        d.isoformat(),
        d.year, q, d.month, d.day,
        d.strftime("%Y-%m"),
        f"{d.year}-Q{q}",
        d.strftime("%A"),
        d.strftime("%B"),
        iso_week,
        "Yes" if d.weekday() >= 5 else "No",
    ])
    d += timedelta(days=1)
write_csv("dim_date.csv",
          ["date", "year", "quarter", "month_num", "day",
           "year_month", "year_quarter", "day_name", "month_name", "iso_week", "is_weekend"],
          date_rows)


# ---------- Generate employees ----------
print("Generating employees...")

# We need an active population that hits each department's target HC, plus a
# realistic backlog of terminated employees so the attrition story works.
# Strategy: oversample hires across 2022-2026, then mark terminations to leave
# the target HC active at TODAY.

ACTIVE_TARGET = sum(hc for _, _, hc, _ in DEPARTMENTS)
# We'll create ~22% extra historical employees who left (so attrition stays realistic)
TOTAL_EVER = int(ACTIVE_TARGET * 1.22)

# Roles eligible per function
def eligible_roles(function_name):
    if function_name == "Engineering":
        families = {"Engineering", "Management"}
    elif function_name == "Product":
        families = {"Product", "Management", "Design"}
    elif function_name == "Risk & Compliance":
        families = {"Risk", "Compliance", "Management"}
    elif function_name == "Operations":
        families = {"Operations", "Management"}
    elif function_name == "Customer Experience":
        families = {"CX", "Operations", "Management"}
    elif function_name == "Corporate":
        families = {"Corporate", "Management"}
    else:
        families = {"Corporate"}
    return [r for r in role_rows if r[2] in families]


def pick_role_for_department(dept):
    """Skew IC-heavy with a few managers; one exec total per company."""
    eligibles = eligible_roles(dept[2])
    levels = []
    for r in eligibles:
        lv = r[3]
        # Pyramid weights
        if lv == "IC1": w = 12
        elif lv == "IC2": w = 18
        elif lv == "IC3": w = 22
        elif lv == "IC4": w = 14
        elif lv == "IC5": w = 6
        elif lv == "IC6": w = 1
        elif lv == "M1":  w = 5
        elif lv == "M2":  w = 2
        elif lv == "M3":  w = 1
        else: w = 0  # exec - handled separately
        levels.append((r, w))
    if not levels:
        return random.choice(eligibles)
    return weighted_choice(levels)


def pick_gender_for_role(role):
    is_tech = role[4] == "Yes"
    # Tech ~32% female, non-tech ~58% female (overall ~47/53 male/female)
    p_female = 0.32 if is_tech else 0.58
    return "F" if random.random() < p_female else "M"


employees = []  # list of dicts
emp_seq = 0


def new_employee(dept, role, hire_date, gender=None, ethnicity=None, location=None):
    global emp_seq
    emp_seq += 1
    g = gender or pick_gender_for_role(role)
    eth = ethnicity or weighted_choice(ETHNICITIES)
    loc = location or weighted_choice(loc_weights)
    name = pick_name(g)
    birth_year = TODAY.year - random.randint(24, 58)
    smin, smax, smed = role[5], role[6], role[7]
    # Compensation pressure: tech IC3-IC5 paid ~0.90-0.96x of market;
    # risk/compliance paid 0.85-0.92x; everyone else 0.95-1.05x
    is_tech = role[4] == "Yes"
    level = role[3]
    fam = role[2]
    if is_tech and level in ("IC3", "IC4", "IC5"):
        comp_ratio = random.uniform(0.88, 0.98)
    elif fam in ("Risk", "Compliance"):
        comp_ratio = random.uniform(0.83, 0.94)
    else:
        comp_ratio = random.uniform(0.94, 1.06)
    salary = round(smed * comp_ratio / 1000) * 1000
    salary = max(smin, min(salary, int(smax * 1.10)))
    bonus_pct = 0.10 if level.startswith("IC") else 0.20 if level.startswith("M") else 0.45
    return {
        "employee_id": f"EMP-{emp_seq:05d}",
        "full_name": name,
        "gender": g,
        "ethnicity": eth,
        "birth_year": birth_year,
        "hire_date": hire_date,
        "department_id": dept[0],
        "role_id": role[0],
        "location_id": loc,
        "base_salary_cad": salary,
        "bonus_target_pct": bonus_pct,
        "equity_grant_cad": int(salary * (1.5 if level.startswith("E") else 1.0 if level.startswith("M") else 0.5 if is_tech and level in ("IC4","IC5","IC6") else 0.2)),
        "manager_id": None,  # filled later
        "status": "Active",
        "termination_date": None,
        "termination_reason": None,
        "termination_type": None,
        "regrettable": None,
    }


# Create executives first (one per E1/E2)
print("  seeding executive layer...")
exec_roles = [r for r in role_rows if r[3] in ("E1", "E2")]
corporate_dept = dept_by_name["Corporate Strategy"]
exec_employees = []
for r in exec_roles:
    # Pick a department that fits the exec
    title = r[1]
    if "Technology" in title:
        d = dept_by_name["Cloud Platform"]
    elif "Product" in title:
        d = dept_by_name["Product Management"]
    elif "Risk" in title:
        d = dept_by_name["Credit Risk"]
    elif "Financial" in title:
        d = dept_by_name["Finance"]
    elif "People" in title:
        d = dept_by_name["Human Resources"]
    else:
        d = corporate_dept
    e = new_employee(d, r, date(2022, 1, 15) - timedelta(days=random.randint(0, 1200)),
                     location="LOC-001")
    e["bonus_target_pct"] = 0.55 if r[3] == "E1" else 0.85
    exec_employees.append(e)
    employees.append(e)

ceo = next(e for e in exec_employees if "CEO" in e.get("_marker", "") or True and role_by_id[e["role_id"]][1] == "Chief Executive Officer")

# Generate the rest
print(f"  generating {TOTAL_EVER:,} historical employees...")
# Distribute hires across the 4.5-year window
hire_window_days = (TODAY - START).days

for _ in range(TOTAL_EVER):
    # Weighted pick of department by target HC
    dept = random.choices(
        [d for d in dept_rows],
        weights=[d[4] for d in dept_rows], k=1)[0]
    role = pick_role_for_department(dept)
    # Hire date - skew toward earlier (more tenure) for IC4+/managers
    level = role[3]
    if level in ("IC4", "IC5", "IC6", "M1", "M2", "M3"):
        # Older hires
        offset = random.randint(0, hire_window_days + 600)
        hd = START - timedelta(days=600) + timedelta(days=offset)
    else:
        offset = int(random.triangular(0, hire_window_days, hire_window_days * 0.6))
        hd = START + timedelta(days=offset)
    if hd > TODAY:
        hd = TODAY - timedelta(days=random.randint(7, 90))
    if hd < date(2015, 1, 1):
        hd = date(2015, 1, 1) + timedelta(days=random.randint(0, 1500))
    employees.append(new_employee(dept, role, hd))

# Mark terminations - we need active HC to land near target per department,
# AND we want the attrition story:
#   - tech attrition ~18% LTM, non-tech ~11%
#   - Senior Engineers (IC4-IC5) regrettable ~22%
#   - Q4 2025 spike on Payments Platform
print("  marking terminations...")

# First pass: random terminations across the population to drain to ~target
# Then a targeted spike for Payments Platform in Q4 2025.

# Group employees by department
by_dept = {}
for e in employees:
    by_dept.setdefault(e["department_id"], []).append(e)

for dept in dept_rows:
    dept_id, _, fn, _, target = dept
    pool = by_dept.get(dept_id, [])
    # Sort by hire date asc so older employees more likely to be the ones who left
    pool.sort(key=lambda e: e["hire_date"])
    n_active_target = target
    n_to_terminate = max(0, len(pool) - n_active_target)
    # Bias toward those hired >18 months ago
    candidates = [e for e in pool if (TODAY - e["hire_date"]).days > 540]
    if len(candidates) < n_to_terminate:
        candidates = pool[:]
    # Choose terminations
    chosen = random.sample(candidates, min(n_to_terminate, len(candidates)))
    for e in chosen:
        # Termination date between hire+9mo and today
        earliest = e["hire_date"] + timedelta(days=270)
        latest = TODAY - timedelta(days=7)
        if earliest >= latest:
            continue
        # Skew tech LTM higher
        role = role_by_id[e["role_id"]]
        is_tech = role[4] == "Yes"
        level = role[3]
        is_payments_platform = e["department_id"] == dept_by_name["Payments Platform"][0]
        # Probability that termination falls in last 12 months (drives LTM
        # attrition rate). Tuned so tech LTM ~18%, non-tech ~10-12%.
        if is_tech:
            p_recent = 0.32
        else:
            p_recent = 0.20
        if is_payments_platform and level in ("IC3", "IC4", "IC5"):
            p_recent = 0.55
        if random.random() < p_recent:
            term_date = TODAY - timedelta(days=random.randint(7, 365))
        else:
            span = (latest - earliest).days
            term_date = earliest + timedelta(days=random.randint(0, span))
        # Payments Platform Q4 2025 spike (10-12 visible leavers)
        if is_payments_platform and level in ("IC3", "IC4", "IC5") and random.random() < 0.30:
            term_date = date(2025, 10, 1) + timedelta(days=random.randint(0, 90))
        # Type and reason
        if random.random() < 0.82:
            term_type = "Voluntary"
            reasons = [(r, w) for r, w, _ in TERMINATION_REASONS_VOL]
            reason = weighted_choice(reasons)
            # Regrettable if senior tech or driver was comp/manager/burnout
            # Overall LTM regrettable rate should land ~22-26%.
            base_regret = 0.12
            if is_tech and level in ("IC3", "IC4", "IC5"):
                base_regret = 0.42
            if is_tech and level in ("IC4", "IC5"):
                base_regret = 0.55  # the headline number for Senior Engineers
            if level in ("M1", "M2", "M3"):
                base_regret = 0.50
            if "comp" in reason.lower() or "growth" in reason.lower() or "manager" in reason.lower() or "burnout" in reason.lower():
                base_regret = min(0.85, base_regret + 0.10)
            regrettable = "Yes" if random.random() < base_regret else "No"
        else:
            term_type = "Involuntary"
            reasons = [(r, w) for r, w, _ in TERMINATION_REASONS_INV]
            reason = weighted_choice(reasons)
            regrettable = "No"
        e["status"] = "Terminated"
        e["termination_date"] = term_date
        e["termination_reason"] = reason
        e["termination_type"] = term_type
        e["regrettable"] = regrettable

# Assign managers within each department
print("  assigning manager hierarchy...")
for dept in dept_rows:
    dept_id = dept[0]
    pool = [e for e in by_dept.get(dept_id, []) if e["status"] == "Active"]
    # Managers in this dept
    mgrs = [e for e in pool if role_by_id[e["role_id"]][2] == "Management"]
    ics = [e for e in pool if role_by_id[e["role_id"]][2] != "Management"]
    if not mgrs:
        # No manager in dept - all report to CEO equivalent
        if exec_employees:
            top = exec_employees[0]["employee_id"]
            for e in ics:
                e["manager_id"] = top
        continue
    # Each IC reports to a random manager in the dept
    for e in ics:
        e["manager_id"] = random.choice(mgrs)["employee_id"]
    # Managers report to highest-level manager in the dept (or to an exec)
    mgrs_sorted = sorted(mgrs, key=lambda m: role_by_id[m["role_id"]][3], reverse=True)
    top_mgr = mgrs_sorted[0]
    for m in mgrs:
        if m["employee_id"] == top_mgr["employee_id"]:
            # Top manager of dept reports to relevant exec
            fn = dept[2]
            exec_match = None
            for ex in exec_employees:
                ex_title = role_by_id[ex["role_id"]][1]
                if fn == "Engineering" and "Technology" in ex_title:
                    exec_match = ex
                elif fn == "Product" and "Product" in ex_title:
                    exec_match = ex
                elif fn == "Risk & Compliance" and "Risk" in ex_title:
                    exec_match = ex
                elif fn == "Corporate" and ("Financial" in ex_title or "People" in ex_title):
                    exec_match = ex
            if exec_match is None:
                exec_match = exec_employees[0]
            m["manager_id"] = exec_match["employee_id"]
        else:
            m["manager_id"] = top_mgr["employee_id"]

# Executives report to CEO
ceo = next((e for e in exec_employees if role_by_id[e["role_id"]][1] == "Chief Executive Officer"), None)
if ceo:
    for ex in exec_employees:
        if ex["employee_id"] != ceo["employee_id"]:
            ex["manager_id"] = ceo["employee_id"]

# ---------- Write dim_employee ----------
print("Writing dim_employee.csv...")
emp_rows = []
for e in employees:
    emp_rows.append([
        e["employee_id"],
        e["full_name"],
        e["gender"],
        e["ethnicity"],
        e["birth_year"],
        e["hire_date"].isoformat(),
        e["department_id"],
        e["role_id"],
        e["location_id"],
        e["manager_id"] or "",
        e["status"],
        e["termination_date"].isoformat() if e["termination_date"] else "",
        e["termination_type"] or "",
        e["termination_reason"] or "",
        e["regrettable"] or "",
        e["base_salary_cad"],
        round(e["bonus_target_pct"], 3),
        e["equity_grant_cad"],
    ])
write_csv("dim_employee.csv",
          ["employee_id", "full_name", "gender", "ethnicity", "birth_year",
           "hire_date", "department_id", "role_id", "location_id", "manager_id",
           "status", "termination_date", "termination_type", "termination_reason",
           "regrettable", "current_base_salary_cad", "current_bonus_target_pct",
           "current_equity_grant_cad"],
          emp_rows)


# ---------- fact_headcount_snapshot ----------
print("Building fact_headcount_snapshot...")
hc_rows = []
for snap in SNAPSHOT_DATES:
    for e in employees:
        if e["hire_date"] > snap:
            continue
        if e["termination_date"] and e["termination_date"] <= snap:
            continue
        hc_rows.append([
            snap.isoformat(),
            e["employee_id"],
            e["department_id"],
            e["role_id"],
            e["location_id"],
            e["manager_id"] or "",
            1.0,  # FTE
            e["base_salary_cad"],
        ])
write_csv("fact_headcount_snapshot.csv",
          ["snapshot_date", "employee_id", "department_id", "role_id",
           "location_id", "manager_id", "fte", "base_salary_cad"],
          hc_rows)


# ---------- fact_attrition (one row per terminated employee) ----------
print("Building fact_attrition...")
att_rows = []
for e in employees:
    if e["status"] != "Terminated":
        continue
    tenure_days = (e["termination_date"] - e["hire_date"]).days
    exit_score = round(random.uniform(2.5, 4.8), 1)
    if e["termination_type"] == "Voluntary" and e["regrettable"] == "Yes":
        exit_score = round(random.uniform(2.0, 3.8), 1)
    att_rows.append([
        f"TRM-{att_rows.__len__()+1:05d}",
        e["employee_id"],
        e["termination_date"].isoformat(),
        e["termination_type"],
        e["termination_reason"],
        e["regrettable"],
        tenure_days,
        round(tenure_days / 30.44, 1),
        exit_score,
        e["department_id"],
        e["role_id"],
        e["location_id"],
        e["manager_id"] or "",
    ])
write_csv("fact_attrition.csv",
          ["attrition_id", "employee_id", "termination_date", "termination_type",
           "termination_reason", "regrettable", "tenure_days", "tenure_months",
           "exit_interview_score", "department_id", "role_id", "location_id", "manager_id"],
          att_rows)


# ---------- fact_compensation (history of comp actions) ----------
print("Building fact_compensation...")
comp_rows = []
for e in employees:
    # Hire action
    comp_rows.append([
        f"CMP-{len(comp_rows)+1:06d}",
        e["employee_id"],
        e["hire_date"].isoformat(),
        "Hire",
        # Start at ~85-92% of current salary, ramp up to current
        round(e["base_salary_cad"] * random.uniform(0.85, 0.92) / 1000) * 1000,
        e["base_salary_cad"],
        round(e["bonus_target_pct"], 3),
        e["equity_grant_cad"],
        e["department_id"],
        e["role_id"],
    ])
    # 0-3 mid-cycle actions (promo/adjustment/refresh)
    n_actions = random.choices([0, 1, 2, 3], weights=[20, 35, 30, 15])[0]
    last_date = e["hire_date"]
    for _ in range(n_actions):
        next_date = last_date + timedelta(days=random.randint(180, 420))
        if e["termination_date"] and next_date >= e["termination_date"]:
            break
        if next_date > TODAY:
            break
        action = random.choices(["Annual Adjustment", "Promotion", "Equity Refresh"],
                                weights=[60, 20, 20])[0]
        if action == "Promotion":
            new_sal = int(e["base_salary_cad"] * random.uniform(1.10, 1.22))
        elif action == "Annual Adjustment":
            new_sal = int(e["base_salary_cad"] * random.uniform(1.02, 1.06))
        else:
            new_sal = e["base_salary_cad"]
        comp_rows.append([
            f"CMP-{len(comp_rows)+1:06d}",
            e["employee_id"],
            next_date.isoformat(),
            action,
            e["base_salary_cad"],
            new_sal,
            round(e["bonus_target_pct"], 3),
            int(e["equity_grant_cad"] * random.uniform(0.5, 1.5)) if action == "Equity Refresh" else 0,
            e["department_id"],
            e["role_id"],
        ])
        last_date = next_date
    # Termination action
    if e["status"] == "Terminated":
        comp_rows.append([
            f"CMP-{len(comp_rows)+1:06d}",
            e["employee_id"],
            e["termination_date"].isoformat(),
            "Termination",
            e["base_salary_cad"],
            0,
            0,
            0,
            e["department_id"],
            e["role_id"],
        ])
write_csv("fact_compensation.csv",
          ["comp_action_id", "employee_id", "effective_date", "action_type",
           "previous_base_salary", "new_base_salary", "bonus_target_pct",
           "equity_grant_cad", "department_id", "role_id"],
          comp_rows)


# ---------- fact_recruitment ----------
print("Building fact_recruitment...")
rec_rows = []
# Generate one req per hire from 2022 onward + ~30% open/closed-no-hire
hires_2022_plus = [e for e in employees if e["hire_date"] >= date(2022, 1, 1)]
for i, e in enumerate(hires_2022_plus):
    role = role_by_id[e["role_id"]]
    # time to fill 25-180 days (skew by level)
    level = role[3]
    if level in ("IC1", "IC2"):
        ttf = random.randint(25, 70)
    elif level in ("IC3",):
        ttf = random.randint(45, 110)
    elif level in ("IC4", "IC5", "M1", "M2"):
        ttf = random.randint(70, 180)
    else:
        ttf = random.randint(90, 220)
    posting = e["hire_date"] - timedelta(days=ttf)
    applicants = random.randint(50, 700)
    interviewed = max(4, int(applicants * random.uniform(0.04, 0.10)))
    offers = max(1, int(interviewed * random.uniform(0.08, 0.22)))
    accepted = 1  # the hire
    channel = weighted_choice(RECRUITMENT_CHANNELS)
    rec_rows.append([
        f"REQ-{i+1:05d}",
        posting.isoformat(),
        e["hire_date"].isoformat(),
        "Filled",
        e["department_id"],
        e["role_id"],
        e["location_id"],
        applicants,
        interviewed,
        offers,
        accepted,
        ttf,
        channel,
        e["employee_id"],
    ])
# Add ~80 open reqs (still active)
for j in range(80):
    dept = random.choices([d for d in dept_rows],
                          weights=[d[4] for d in dept_rows], k=1)[0]
    role = pick_role_for_department(dept)
    loc = weighted_choice(loc_weights)
    posting = TODAY - timedelta(days=random.randint(7, 110))
    applicants = random.randint(20, 400)
    interviewed = max(2, int(applicants * random.uniform(0.04, 0.10)))
    offers = random.randint(0, 2)
    channel = weighted_choice(RECRUITMENT_CHANNELS)
    rec_rows.append([
        f"REQ-{len(rec_rows)+1:05d}",
        posting.isoformat(),
        "",
        "Open",
        dept[0],
        role[0],
        loc,
        applicants,
        interviewed,
        offers,
        0,
        "",
        channel,
        "",
    ])
write_csv("fact_recruitment.csv",
          ["req_id", "posting_date", "hire_date", "status",
           "department_id", "role_id", "location_id",
           "applicants", "interviewed", "offers_made", "offers_accepted",
           "time_to_fill_days", "source_channel", "hired_employee_id"],
          rec_rows)


# ---------- fact_training_completion ----------
print("Building fact_training_completion...")
train_rows = []
# Each active employee gets every mandatory course; assign due date and completion
for e in employees:
    if e["status"] != "Active":
        continue
    for course in TRAINING_COURSES:
        cid, cname, mand, regulator, freq = course
        # Most recent due date
        if freq:
            cycle_offset = random.randint(0, freq * 30)
            due = TODAY + timedelta(days=cycle_offset) - timedelta(days=freq * 30)
        else:
            # Optional course
            due = TODAY + timedelta(days=180)
            if random.random() < 0.4:
                continue  # not everyone takes optional
        # Completion probability depends on mandatory + regulator
        if mand and regulator in ("FINTRAC", "OSFI"):
            p_complete = 0.96
        elif mand:
            p_complete = 0.93
        else:
            p_complete = 0.65
        if random.random() < p_complete:
            completion = due - timedelta(days=random.randint(1, 45))
            if completion < e["hire_date"]:
                completion = e["hire_date"] + timedelta(days=random.randint(7, 45))
            status = "Completed"
            days_overdue = 0
        else:
            completion = None
            if due < TODAY:
                status = "Overdue"
                days_overdue = (TODAY - due).days
            else:
                status = "Upcoming"
                days_overdue = 0
        train_rows.append([
            f"TRC-{len(train_rows)+1:06d}",
            e["employee_id"],
            cid,
            cname,
            regulator,
            "Yes" if mand else "No",
            due.isoformat(),
            completion.isoformat() if completion else "",
            status,
            days_overdue,
            e["department_id"],
            e["location_id"],
        ])
write_csv("fact_training_completion.csv",
          ["training_record_id", "employee_id", "course_id", "course_name",
           "regulator", "is_mandatory", "due_date", "completion_date",
           "status", "days_overdue", "department_id", "location_id"],
          train_rows)


# ---------- fact_attestations ----------
print("Building fact_attestations...")
att_records = []
for e in employees:
    if e["status"] != "Active":
        continue
    for atype, aname, mand, freq in ATTESTATION_TYPES:
        cycle_offset = random.randint(0, freq * 30)
        due = TODAY + timedelta(days=cycle_offset) - timedelta(days=freq * 30)
        if atype == "ATT-COI":
            # Most complete; we top up to exactly 7 overdue 90+ days afterwards
            p_complete = 0.998
        else:
            p_complete = 0.995
        if random.random() < p_complete:
            done = due - timedelta(days=random.randint(1, 20))
            if done < e["hire_date"]:
                done = e["hire_date"] + timedelta(days=random.randint(7, 20))
            status = "Completed"
            days_overdue = 0
        else:
            done = None
            if due < TODAY:
                status = "Overdue"
                days_overdue = (TODAY - due).days
            else:
                status = "Upcoming"
                days_overdue = 0
        att_records.append([
            f"ATR-{len(att_records)+1:06d}",
            e["employee_id"],
            atype,
            aname,
            "Yes" if mand else "No",
            due.isoformat(),
            done.isoformat() if done else "",
            status,
            days_overdue,
            e["department_id"],
        ])
# Force exactly 7 overdue 90+ COI records (controlled compliance story point)
coi_records = [r for r in att_records if r[2] == "ATT-COI"]
NEEDED_OVERDUE_90 = 7
# Reset any natural ATT-COI overdues so we get a clean count
for r in coi_records:
    if r[7] == "Overdue":
        # Restore as completed
        r[6] = (date.fromisoformat(r[5]) - timedelta(days=random.randint(1, 15))).isoformat()
        r[7] = "Completed"
        r[8] = 0
# Now stamp exactly 7 fresh 90+ day overdues
candidates = [r for r in coi_records if r[7] == "Completed"]
for r in random.sample(candidates, min(NEEDED_OVERDUE_90, len(candidates))):
    r[5] = (TODAY - timedelta(days=random.randint(95, 220))).isoformat()
    r[6] = ""
    r[7] = "Overdue"
    r[8] = (TODAY - date.fromisoformat(r[5])).days
write_csv("fact_attestation.csv",
          ["attestation_record_id", "employee_id", "attestation_type",
           "attestation_name", "is_mandatory", "due_date", "completed_date",
           "status", "days_overdue", "department_id"],
          att_records)


# ---------- Summary KPIs ----------
print("\n=== Summary ===")
active = [e for e in employees if e["status"] == "Active"]
tech_active = [e for e in active if role_by_id[e["role_id"]][4] == "Yes"]
print(f"Active headcount:        {len(active):,}")
print(f"  Tech roles:            {len(tech_active):,}  ({len(tech_active)/len(active)*100:.1f}%)")
print(f"  Female overall:        {sum(1 for e in active if e['gender']=='F')/len(active)*100:.1f}%")
print(f"  Female in tech:        {sum(1 for e in tech_active if e['gender']=='F')/max(len(tech_active),1)*100:.1f}%")
ltm_terms = [e for e in employees if e["status"] == "Terminated" and (TODAY - e["termination_date"]).days <= 365]
ltm_tech_terms = [e for e in ltm_terms if role_by_id[e["role_id"]][4] == "Yes"]
ltm_nontech_terms = [e for e in ltm_terms if role_by_id[e["role_id"]][4] == "No"]
# Approximate average HC = active + half of LTM terms
avg_tech_hc = len(tech_active) + len(ltm_tech_terms) / 2
avg_nontech_hc = len(active) - len(tech_active) + len(ltm_nontech_terms) / 2
print(f"Attrition LTM (tech):    {len(ltm_tech_terms)/max(avg_tech_hc,1)*100:.1f}%  ({len(ltm_tech_terms)} leavers)")
print(f"Attrition LTM (non-tech):{len(ltm_nontech_terms)/max(avg_nontech_hc,1)*100:.1f}%  ({len(ltm_nontech_terms)} leavers)")
regret_count = sum(1 for e in ltm_terms if e["regrettable"] == "Yes")
print(f"Regrettable rate (LTM):  {regret_count/max(len(ltm_terms),1)*100:.1f}%")
pp_id = dept_by_name["Payments Platform"][0]
pp_q4 = [e for e in employees if e["status"] == "Terminated" and e["department_id"] == pp_id
         and e["termination_date"] >= date(2025, 10, 1) and e["termination_date"] < date(2026, 1, 1)]
print(f"Payments Platform Q4-25 leavers: {len(pp_q4)}")
overdue_90 = sum(1 for r in coi_records if r[7] == "Overdue" and r[8] >= 90)
print(f"COI overdue 90+ days:    {overdue_90}")
print(f"\nFiles written to: {OUT}")
