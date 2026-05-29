"""Generate fully-synthetic Rogers-shaped RAN telemetry CSVs for the
Network Anomaly Detection demo.

Tables produced (all written to ./csv/):
  dim_site               80 sites across CA provinces (weighted by population)
  dim_cell              240 cells (3 sectors per site), 4G/5G mix
  dim_date               28 days, 2026-05-04 .. 2026-05-31
  dim_hour               24 hours w/ daypart
  dim_alarm_type         15 alarm types (RAN / transport / core / power)
  dim_customer_segment    4 segments (Consumer-Prepaid/Postpaid, SMB, Enterprise)
  fact_cell_kpi         hourly per-cell KPIs (availability, throughput,
                         latency, PRB util, attached users, drop rate)
  fact_alarms           discrete alarm events w/ severity + MTTR
  fact_traffic          daily per-cell voice/data/SMS rollups
  fact_customer_impact  daily per-cell per-segment tickets + sentiment

Seeded anomalies driving the demo narrative:
  A. Site outage     — S-TOR-007 (3 cells) hard down 2026-05-25 16:00-19:00
  B. Vendor latency  — Nokia BC cells RTT creeps 22ms -> 55ms from 2026-05-22
  C. Stadium surge   — TOR-DT cells hit 96% PRB on 2026-05-24 18:00-22:00
  D. Chronic degrade — C-VAN-N-002 availability 99% -> 89% slow decline
  E. CX correlation  — tickets/sentiment track availability + throughput dips,
                       Postpaid + Enterprise segments most reactive

Run once:
  py build_csvs.py
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20260529
random.seed(SEED)
np.random.seed(SEED)

OUT = Path(__file__).parent / "csv"
OUT.mkdir(exist_ok=True)

# ---------------------------------------------------------------- constants --

PROVINCES = [
    # (code, name, weight, top_cities)
    ("ON", "Ontario", 0.36, [("Toronto", 43.6532, -79.3832, "TOR"),
                              ("Ottawa", 45.4215, -75.6972, "OTT"),
                              ("Mississauga", 43.5890, -79.6441, "MIS"),
                              ("Hamilton", 43.2557, -79.8711, "HAM"),
                              ("London", 42.9849, -81.2453, "LDN")]),
    ("QC", "Quebec",  0.22, [("Montreal", 45.5019, -73.5674, "MTL"),
                              ("Quebec City", 46.8139, -71.2080, "QBC"),
                              ("Laval", 45.6066, -73.7124, "LAV")]),
    ("BC", "British Columbia", 0.14, [("Vancouver", 49.2827, -123.1207, "VAN"),
                                       ("Victoria", 48.4284, -123.3656, "VIC"),
                                       ("Surrey", 49.1913, -122.8490, "SUR")]),
    ("AB", "Alberta", 0.12, [("Calgary", 51.0447, -114.0719, "CAL"),
                              ("Edmonton", 53.5461, -113.4938, "EDM")]),
    ("MB", "Manitoba", 0.04, [("Winnipeg", 49.8951, -97.1384, "WPG")]),
    ("SK", "Saskatchewan", 0.03, [("Saskatoon", 52.1332, -106.6700, "SAS"),
                                   ("Regina", 50.4452, -104.6189, "REG")]),
    ("NS", "Nova Scotia", 0.03, [("Halifax", 44.6488, -63.5752, "HAL")]),
    ("NB", "New Brunswick", 0.02, [("Moncton", 46.0878, -64.7782, "MNC")]),
    ("NL", "Newfoundland", 0.02, [("St. John's", 47.5615, -52.7126, "STJ")]),
    ("PE", "Prince Edward Island", 0.02, [("Charlottetown", 46.2382, -63.1311, "CHA")]),
]

TECHS = [("4G", 0.55), ("5G", 0.45)]
BANDS_4G = ["B7-2600", "B12-700", "B66-AWS3"]
BANDS_5G = ["n78-3500", "n41-2500", "n71-600"]
VENDORS = [("Ericsson", 0.42), ("Nokia", 0.36), ("Samsung", 0.22)]

# Site count + cells per site (3 sectors typical)
N_SITES = 80
CELLS_PER_SITE = 3

START_DATE = pd.Timestamp("2026-05-04")
END_DATE   = pd.Timestamp("2026-05-31")
DATES = pd.date_range(START_DATE, END_DATE, freq="D")
HOURS = list(range(24))

# Anomaly windows (kept as constants so report measures can reference them)
INCIDENT_SITE = None  # filled in after dim_site built
INCIDENT_TS = pd.Timestamp("2026-05-25 16:00")
STADIUM_TS  = pd.Timestamp("2026-05-24 18:00")
NOKIA_BC_RAMP_START = pd.Timestamp("2026-05-22 00:00")
CHRONIC_CELL = "C-VAN-N-002"

# ------------------------------------------------------------- helpers ------

def weighted_choice(pairs):
    items, weights = zip(*pairs)
    return random.choices(items, weights=weights, k=1)[0]

def jitter(lat, lon):
    return lat + np.random.normal(0, 0.04), lon + np.random.normal(0, 0.04)

# --------------------------------------------------------------- dim_site ---

site_rows = []
city_pool = []
for code, name, w, cities in PROVINCES:
    for c in cities:
        city_pool.append((code, name, w, c))

# distribute N_SITES across provinces by population weight
prov_weights = [p[2] for p in PROVINCES]
assigned = np.random.choice(len(PROVINCES), size=N_SITES, p=np.array(prov_weights)/sum(prov_weights))
site_counter = {}
for i, prov_idx in enumerate(assigned):
    code, name, w, cities = PROVINCES[prov_idx]
    city, lat0, lon0, city_code = random.choice(cities)
    site_counter[code] = site_counter.get(code, 0) + 1
    n = site_counter[code]
    site_id = f"S-{city_code}-{n:03d}"
    lat, lon = jitter(lat0, lon0)
    tech = weighted_choice(TECHS)
    vendor = weighted_choice(VENDORS)
    commissioned = pd.Timestamp("2020-01-01") + pd.Timedelta(days=random.randint(0, 2000))
    site_rows.append({
        "site_id": site_id,
        "site_name": f"{city} {city_code}{n:03d}",
        "region": code,
        "region_name": name,
        "city": city,
        "latitude": round(lat, 5),
        "longitude": round(lon, 5),
        "primary_technology": tech,
        "primary_vendor": vendor,
        "commissioned_date": commissioned.strftime("%Y-%m-%d"),
        "site_type": random.choice(["Macro", "Macro", "Macro", "SmallCell", "Rooftop"]),
    })
dim_site = pd.DataFrame(site_rows)
dim_site.to_csv(OUT / "dim_site.csv", index=False)
print(f"dim_site: {len(dim_site)} rows")

# Pick incident site: the 7th Toronto site, if it exists; else the first TOR site
tor_sites = dim_site[dim_site["site_id"].str.startswith("S-TOR-")]["site_id"].tolist()
INCIDENT_SITE = tor_sites[6] if len(tor_sites) >= 7 else tor_sites[0] if tor_sites else dim_site["site_id"].iloc[0]
print(f"  incident site -> {INCIDENT_SITE}")

# downtown Toronto cells for stadium surge
DT_TOR_SITES = tor_sites[:4]  # first 4 TOR sites act as "downtown"

# --------------------------------------------------------------- dim_cell ---

cell_rows = []
for _, s in dim_site.iterrows():
    for sec in range(1, CELLS_PER_SITE + 1):
        tech = s["primary_technology"]
        # 80% same tech as site, 20% mixed
        if random.random() < 0.20:
            tech = "5G" if tech == "4G" else "4G"
        bands = BANDS_5G if tech == "5G" else BANDS_4G
        cell_id = f"C-{s['site_id'].split('-',1)[1]}-{sec:01d}"
        # rename to match chronic cell convention
        prefix = s["site_id"].split("-", 1)[1]
        cell_id = f"C-{prefix}-{sec:03d}"
        cell_rows.append({
            "cell_id": cell_id,
            "site_id": s["site_id"],
            "sector": sec,
            "technology": tech,
            "band": random.choice(bands),
            "vendor": s["primary_vendor"] if random.random() < 0.85 else weighted_choice(VENDORS),
            "azimuth_deg": (sec - 1) * 120,
            "max_throughput_dl_mbps": 250 if tech == "4G" else 1200,
        })
dim_cell = pd.DataFrame(cell_rows)
dim_cell.to_csv(OUT / "dim_cell.csv", index=False)
print(f"dim_cell: {len(dim_cell)} rows  ({(dim_cell.technology=='5G').sum()} 5G)")

INCIDENT_CELLS = dim_cell[dim_cell["site_id"] == INCIDENT_SITE]["cell_id"].tolist()
print(f"  incident cells -> {INCIDENT_CELLS}")
DT_TOR_CELLS = dim_cell[dim_cell["site_id"].isin(DT_TOR_SITES)]["cell_id"].tolist()
print(f"  downtown TOR cells -> {len(DT_TOR_CELLS)}")

# rename a Vancouver cell to be the chronic-degrade target
van_n_cells = dim_cell[dim_cell["cell_id"].str.startswith("C-VAN-")]["cell_id"].tolist()
if van_n_cells:
    target = van_n_cells[0]
    if target != CHRONIC_CELL:
        dim_cell.loc[dim_cell["cell_id"] == target, "cell_id"] = CHRONIC_CELL
        dim_cell.to_csv(OUT / "dim_cell.csv", index=False)
        print(f"  chronic cell -> {CHRONIC_CELL} (renamed from {target})")

# Nokia BC cells — for vendor latency creep
NOKIA_BC_CELLS = dim_cell.merge(dim_site[["site_id", "region"]], on="site_id")
NOKIA_BC_CELLS = NOKIA_BC_CELLS[(NOKIA_BC_CELLS.vendor == "Nokia") & (NOKIA_BC_CELLS.region == "BC")]["cell_id"].tolist()
print(f"  Nokia BC cells (latency creep) -> {len(NOKIA_BC_CELLS)}")

# --------------------------------------------------------------- dim_date ---

dim_date = pd.DataFrame({
    "date_key":   DATES.strftime("%Y-%m-%d"),
    "year":       DATES.year,
    "month":      DATES.month,
    "year_month": DATES.strftime("%Y-%m"),
    "week_number": DATES.isocalendar().week.values,
    "day_name":   DATES.day_name(),
    "is_weekend": DATES.weekday >= 5,
})
dim_date.to_csv(OUT / "dim_date.csv", index=False)
print(f"dim_date: {len(dim_date)} rows")

# --------------------------------------------------------------- dim_hour ---

dim_hour = pd.DataFrame({
    "hour": HOURS,
    "hour_label": [f"{h:02d}:00" for h in HOURS],
    "daypart": ["Late Night" if h < 6 else
                 "Morning"    if h < 9 else
                 "Business"   if h < 17 else
                 "Peak"       if h < 22 else
                 "Evening"    for h in HOURS],
    "is_peak": [9 <= h <= 21 for h in HOURS],
})
dim_hour.to_csv(OUT / "dim_hour.csv", index=False)
print(f"dim_hour: {len(dim_hour)} rows")

# ----------------------------------------------------------- dim_alarm_type -

alarm_types = [
    ("AT01", "Cell Down",                "Critical", "RAN"),
    ("AT02", "Sector Outage",            "Critical", "RAN"),
    ("AT03", "High PRB Utilization",     "Major",    "RAN"),
    ("AT04", "Throughput Degradation",   "Major",    "RAN"),
    ("AT05", "Latency Threshold Exceeded","Major",   "RAN"),
    ("AT06", "Backhaul Link Down",       "Critical", "Transport"),
    ("AT07", "Backhaul Congestion",      "Major",    "Transport"),
    ("AT08", "Fiber Cut",                "Critical", "Transport"),
    ("AT09", "Core Element CPU High",    "Major",    "Core"),
    ("AT10", "PCRF Session Drop",        "Major",    "Core"),
    ("AT11", "Power Module Fault",       "Critical", "Power"),
    ("AT12", "Generator Switchover",     "Minor",    "Power"),
    ("AT13", "VSWR Antenna Mismatch",    "Minor",    "RAN"),
    ("AT14", "Software Watchdog Reset",  "Minor",    "RAN"),
    ("AT15", "Temperature Threshold",    "Minor",    "Power"),
]
dim_alarm = pd.DataFrame(alarm_types, columns=["alarm_type_id", "alarm_name", "severity", "category"])
dim_alarm.to_csv(OUT / "dim_alarm_type.csv", index=False)
print(f"dim_alarm_type: {len(dim_alarm)} rows")

# ----------------------------------------------------- dim_customer_segment -

segments = [
    ("CS01", "Consumer-Prepaid",  "Consumer",   3_500_000),
    ("CS02", "Consumer-Postpaid", "Consumer",   6_200_000),
    ("CS03", "SMB",               "Business",     650_000),
    ("CS04", "Enterprise",        "Business",     180_000),
]
dim_segment = pd.DataFrame(segments, columns=["segment_id", "segment_name", "segment_class", "subscriber_count"])
dim_segment.to_csv(OUT / "dim_customer_segment.csv", index=False)
print(f"dim_customer_segment: {len(dim_segment)} rows")

# -------------------------------------------------------- fact_cell_kpi -----
# Hourly per-cell KPIs. Volume = 240 cells * 24 * 28 = 161,280 rows.
# To keep CSV size manageable we sample every other day for non-incident cells.

cell_meta = dim_cell.merge(dim_site[["site_id", "region"]], on="site_id")
cell_meta_idx = cell_meta.set_index("cell_id")

# baselines per cell (so different cells have different "normal")
rng = np.random.default_rng(SEED)
baselines = {}
for _, c in cell_meta.iterrows():
    base_avail = rng.uniform(98.5, 99.9)
    if c.technology == "5G":
        base_dl, base_ul, base_lat = rng.uniform(400, 800), rng.uniform(80, 160), rng.uniform(15, 25)
    else:
        base_dl, base_ul, base_lat = rng.uniform(60, 140), rng.uniform(15, 35), rng.uniform(28, 42)
    base_prb = rng.uniform(45, 65)
    base_users = rng.uniform(180, 420)
    baselines[c.cell_id] = (base_avail, base_dl, base_ul, base_lat, base_prb, base_users)

kpi_rows = []
for _, c in cell_meta.iterrows():
    cell_id = c.cell_id
    avail0, dl0, ul0, lat0, prb0, usr0 = baselines[cell_id]
    region = c.region
    vendor = c.vendor
    for d in DATES:
        for h in HOURS:
            ts = d + pd.Timedelta(hours=h)
            # diurnal pattern: PRB/users peak 18:00-22:00
            diurnal = math.sin(((h - 6) / 24) * 2 * math.pi) * 0.4 + 0.5  # 0.1..0.9
            prb = max(5, prb0 * (0.6 + 1.0 * diurnal) + rng.normal(0, 4))
            users = max(20, usr0 * (0.5 + 1.1 * diurnal) + rng.normal(0, 25))
            # throughput inversely scales when PRB saturates
            sat = max(0, (prb - 80) / 20)
            dl = max(5, dl0 * (1 - 0.55 * sat) + rng.normal(0, dl0 * 0.05))
            ul = max(1, ul0 * (1 - 0.45 * sat) + rng.normal(0, ul0 * 0.05))
            lat = max(8, lat0 * (1 + 0.45 * sat) + rng.normal(0, 1.8))
            avail = min(100.0, avail0 + rng.normal(0, 0.15))
            drop = max(0, rng.normal(0.4, 0.15) + sat * 0.6)

            # ---- ANOMALY INJECTIONS -----------------------------
            # A. Site outage 2026-05-25 16:00-19:00 on INCIDENT_CELLS
            if cell_id in INCIDENT_CELLS and INCIDENT_TS <= ts <= INCIDENT_TS + pd.Timedelta(hours=3):
                avail = rng.uniform(8, 22)
                dl = rng.uniform(2, 12)
                ul = rng.uniform(0.5, 3)
                lat = rng.uniform(180, 260)
                drop = rng.uniform(6, 12)
                users = rng.uniform(0, 30)
                prb = rng.uniform(5, 15)
            # B. Nokia BC latency creep from 2026-05-22 onward
            if cell_id in NOKIA_BC_CELLS and ts >= NOKIA_BC_RAMP_START:
                days_in = (ts - NOKIA_BC_RAMP_START).days
                lat += min(35, days_in * 4) + rng.normal(0, 2)
            # C. Stadium surge 2026-05-24 18-22 on downtown TOR cells
            if cell_id in DT_TOR_CELLS and STADIUM_TS <= ts <= STADIUM_TS + pd.Timedelta(hours=4):
                prb = rng.uniform(92, 99)
                dl = max(5, dl0 * 0.35 + rng.normal(0, 4))
                ul = max(1, ul0 * 0.4 + rng.normal(0, 1))
                lat = lat0 * 2.3 + rng.normal(0, 4)
                users = usr0 * 2.8 + rng.normal(0, 30)
                drop = rng.uniform(1.8, 3.5)
            # D. Chronic degrade C-VAN-N-002: linear avail decline 99 -> 89 over period
            if cell_id == CHRONIC_CELL:
                day_idx = (ts.normalize() - START_DATE).days
                avail = max(85, 99 - (day_idx / 27) * 10) + rng.normal(0, 0.5)
                if day_idx > 18:
                    drop += rng.uniform(0.8, 2.0)

            kpi_rows.append((
                ts.strftime("%Y-%m-%d"),
                h,
                cell_id,
                round(avail, 2),
                round(dl, 2),
                round(ul, 2),
                round(lat, 2),
                round(prb, 2),
                int(users),
                round(drop, 3),
            ))

fact_kpi = pd.DataFrame(kpi_rows, columns=[
    "date_key", "hour", "cell_id",
    "availability_pct", "throughput_dl_mbps", "throughput_ul_mbps",
    "latency_ms", "prb_utilization_pct", "attached_users", "drop_rate_pct",
])
fact_kpi.to_csv(OUT / "fact_cell_kpi.csv", index=False)
print(f"fact_cell_kpi: {len(fact_kpi):,} rows  ({(OUT/'fact_cell_kpi.csv').stat().st_size/1e6:.1f} MB)")

# ----------------------------------------------------------- fact_alarms ----

alarm_rows = []
alarm_seq = 0
# Background alarms: low rate per cell
for _, c in cell_meta.iterrows():
    n = rng.poisson(1.2)  # ~1-2 alarms per cell over the period
    for _ in range(int(n)):
        d = random.choice(list(DATES))
        h = random.randint(0, 23)
        at = random.choices(["AT03", "AT04", "AT05", "AT07", "AT10", "AT13", "AT14", "AT15"],
                             weights=[4, 3, 3, 2, 1, 2, 3, 2])[0]
        sev = dim_alarm.set_index("alarm_type_id").loc[at, "severity"]
        dur = max(5, int(rng.exponential(45)))
        alarm_seq += 1
        alarm_rows.append((f"A{alarm_seq:06d}", c.cell_id, d.strftime("%Y-%m-%d"), h, at, sev, dur, 1, dur))

# Incident-driven alarms
# A. Site outage: 3 critical alarms (AT01 + AT06 + AT11)
for cid in INCIDENT_CELLS:
    for at in ["AT01", "AT06", "AT11"]:
        sev = dim_alarm.set_index("alarm_type_id").loc[at, "severity"]
        dur = random.randint(180, 240)
        alarm_seq += 1
        alarm_rows.append((f"A{alarm_seq:06d}", cid, INCIDENT_TS.strftime("%Y-%m-%d"),
                            INCIDENT_TS.hour, at, sev, dur, 1, dur))

# B. Nokia BC: AT05 latency alarms ramp up
for cid in NOKIA_BC_CELLS:
    for offset in [1, 3, 5, 7]:
        ts = NOKIA_BC_RAMP_START + pd.Timedelta(days=offset)
        if ts > END_DATE: break
        alarm_seq += 1
        alarm_rows.append((f"A{alarm_seq:06d}", cid, ts.strftime("%Y-%m-%d"), 14,
                            "AT05", "Major", int(rng.uniform(60, 180)), 1, int(rng.uniform(60, 180))))

# C. Stadium surge: AT03 PRB on downtown cells
for cid in DT_TOR_CELLS:
    alarm_seq += 1
    alarm_rows.append((f"A{alarm_seq:06d}", cid, STADIUM_TS.strftime("%Y-%m-%d"),
                        STADIUM_TS.hour, "AT03", "Major", random.randint(120, 240), 1, random.randint(120, 240)))

# D. Chronic cell: AT04 throughput degradation alarms toward end
for offset in [20, 22, 24, 26]:
    ts = START_DATE + pd.Timedelta(days=offset)
    if ts > END_DATE: break
    alarm_seq += 1
    resolved = 1 if offset < 24 else 0
    alarm_rows.append((f"A{alarm_seq:06d}", CHRONIC_CELL, ts.strftime("%Y-%m-%d"), 10,
                        "AT04", "Major", int(rng.uniform(80, 220)), resolved,
                        int(rng.uniform(80, 220)) if resolved else 0))

fact_alarms = pd.DataFrame(alarm_rows, columns=[
    "alarm_id", "cell_id", "date_key", "hour", "alarm_type_id",
    "severity", "duration_minutes", "resolved_flag", "mttr_minutes",
])
fact_alarms.to_csv(OUT / "fact_alarms.csv", index=False)
print(f"fact_alarms: {len(fact_alarms):,} rows")

# ----------------------------------------------------------- fact_traffic ---
# Daily rollups (voice/data/SMS) per cell.

traffic_rows = []
for _, c in cell_meta.iterrows():
    cell_id = c.cell_id
    base_voice = rng.uniform(800, 2200)
    base_data  = rng.uniform(120, 480) * (2.5 if c.technology == "5G" else 1.0)
    base_sms   = rng.uniform(500, 1400)
    for d in DATES:
        weekend = d.weekday() >= 5
        v = base_voice * (0.7 if weekend else 1.0) * rng.uniform(0.85, 1.15)
        g = base_data  * (1.15 if weekend else 1.0) * rng.uniform(0.85, 1.20)
        sms = base_sms * rng.uniform(0.80, 1.20)
        # Stadium event boosts downtown TOR traffic that night
        if cell_id in DT_TOR_CELLS and d.normalize() == STADIUM_TS.normalize():
            v *= 1.8
            g *= 3.2
            sms *= 1.4
        # Incident day reduces incident-cell traffic
        if cell_id in INCIDENT_CELLS and d.normalize() == INCIDENT_TS.normalize():
            v *= 0.45
            g *= 0.40
            sms *= 0.55
        traffic_rows.append((d.strftime("%Y-%m-%d"), cell_id,
                              round(v, 1), round(g, 2), int(sms)))

fact_traffic = pd.DataFrame(traffic_rows, columns=[
    "date_key", "cell_id", "voice_minutes", "data_gb", "sms_count",
])
fact_traffic.to_csv(OUT / "fact_traffic.csv", index=False)
print(f"fact_traffic: {len(fact_traffic):,} rows")

# --------------------------------------------------- fact_customer_impact --
# Daily per-cell per-segment tickets + sentiment. Only generate rows for
# cells with meaningful impact (avoid 30k rows of zeros).

impact_rows = []
# baseline ticket rate per segment per 1000 users
ticket_rate = {"CS01": 0.5, "CS02": 1.2, "CS03": 2.0, "CS04": 3.5}
sentiment_base = {"CS01": 0.62, "CS02": 0.68, "CS03": 0.55, "CS04": 0.51}

# pre-compute avg availability per cell per day for impact correlation
daily_kpi = fact_kpi.groupby(["date_key", "cell_id"]).agg(
    avg_avail=("availability_pct", "mean"),
    avg_dl=("throughput_dl_mbps", "mean"),
    avg_lat=("latency_ms", "mean"),
    avg_users=("attached_users", "mean"),
).reset_index()

for _, r in daily_kpi.iterrows():
    cell_id = r.cell_id
    avail = r.avg_avail
    dl = r.avg_dl
    lat = r.avg_lat
    users = r.avg_users
    # impact severity 0..1
    impact = 0.0
    if avail < 95:   impact += (95 - avail) / 50
    if lat  > 60:    impact += min(0.5, (lat - 60) / 200)
    impact = min(1.0, impact)
    # baseline noise
    bg = rng.uniform(0, 0.05)
    impact = max(bg, impact)
    if impact < 0.04:
        continue
    for seg_id, seg in [("CS01", "Consumer-Prepaid"), ("CS02", "Consumer-Postpaid"),
                         ("CS03", "SMB"), ("CS04", "Enterprise")]:
        # postpaid + enterprise react harder
        reactivity = {"CS01": 0.7, "CS02": 1.1, "CS03": 1.3, "CS04": 1.6}[seg_id]
        affected = int(users * rng.uniform(0.5, 0.9) * impact * reactivity * 0.3)
        tickets = max(0, int(ticket_rate[seg_id] * (users / 1000) * (1 + impact * 8 * reactivity)))
        repeat = int(tickets * rng.uniform(0.15, 0.35))
        sent = max(0.05, sentiment_base[seg_id] - impact * 0.45 * reactivity + rng.normal(0, 0.03))
        if tickets == 0 and affected == 0:
            continue
        impact_rows.append((r.date_key, cell_id, seg_id,
                             tickets, repeat, round(sent, 3), affected))

fact_impact = pd.DataFrame(impact_rows, columns=[
    "date_key", "cell_id", "segment_id",
    "tickets_opened", "repeat_caller_count", "sentiment_score", "affected_customers",
])
fact_impact.to_csv(OUT / "fact_customer_impact.csv", index=False)
print(f"fact_customer_impact: {len(fact_impact):,} rows")

# ------------------------------------------------------------- summary ------

print("\nAnomaly cheat-sheet (for the demo narrative):")
print(f"  A. Site outage     -> {INCIDENT_SITE}, cells={INCIDENT_CELLS}, ts={INCIDENT_TS}")
print(f"  B. Vendor latency  -> Nokia BC cells ({len(NOKIA_BC_CELLS)} cells), ramp from {NOKIA_BC_RAMP_START.date()}")
print(f"  C. Stadium surge   -> downtown TOR cells ({len(DT_TOR_CELLS)} cells), ts={STADIUM_TS}")
print(f"  D. Chronic degrade -> {CHRONIC_CELL}, slow decline over period")
print(f"\nAll CSVs in: {OUT}")
