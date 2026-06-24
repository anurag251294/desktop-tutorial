"""Rogers Finance synthetic data generator.

Companion to the 'Enterprise Semantic Layer' demo (slide 6: 'one measure,
queried everywhere'). Builds a small Finance star schema so a single ARPU
measure defined once in the certified semantic model can be queried from
Excel, Power BI, and a Copilot data agent.

Grain choices:
  - Revenue / Costs:        monthly, by business_unit x product x region
  - Subscribers / Churn:    monthly, by business_unit x product x segment x region

24 months of history ending 2026-06. CSVs land in ./csv.
"""
from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path

random.seed(42)

OUT = Path(__file__).parent / "csv"
OUT.mkdir(parents=True, exist_ok=True)

# ---- Dimensions -----------------------------------------------------------

BUSINESS_UNITS = [
    # bu_id, bu_name, bu_type
    ("BU01", "Wireless",                 "Connectivity"),
    ("BU02", "Cable, Internet & Home",   "Connectivity"),
    ("BU03", "Media",                    "Media & Sports"),
    ("BU04", "Enterprise & Business",    "B2B"),
]

PRODUCTS = [
    # product_id, product_name, bu_id, revenue_type, list_price
    ("P001", "Wireless Postpaid - Premium",  "BU01", "Subscription",  92.0),
    ("P002", "Wireless Postpaid - Mid",      "BU01", "Subscription",  68.0),
    ("P003", "Wireless Postpaid - Value",    "BU01", "Subscription",  52.0),
    ("P004", "Wireless Prepaid",             "BU01", "Subscription",  31.0),
    ("P005", "Wireless 5G Home Internet",    "BU01", "Subscription",  74.0),

    ("P101", "Ignite Internet 1Gbps",        "BU02", "Subscription",  98.0),
    ("P102", "Ignite Internet 500",          "BU02", "Subscription",  82.0),
    ("P103", "Ignite TV",                    "BU02", "Subscription",  56.0),
    ("P104", "Home Phone",                   "BU02", "Subscription",  28.0),
    ("P105", "Smart Home Monitoring",        "BU02", "Subscription",  35.0),

    ("P201", "Sportsnet Subscriptions",      "BU03", "Subscription",  24.0),
    ("P202", "Sportsnet+ Streaming",         "BU03", "Subscription",  19.0),
    ("P203", "Linear TV Advertising",        "BU03", "Advertising",    0.0),
    ("P204", "Digital Advertising",          "BU03", "Advertising",    0.0),
    ("P205", "Toronto Blue Jays Tickets",    "BU03", "Tickets",        0.0),

    ("P301", "Enterprise Wireless Fleet",    "BU04", "Subscription",  64.0),
    ("P302", "Dedicated Internet Access",    "BU04", "Subscription", 1800.0),
    ("P303", "SD-WAN Managed",               "BU04", "Subscription",  950.0),
    ("P304", "Unified Communications",       "BU04", "Subscription",  340.0),
    ("P305", "Private 5G Networks",          "BU04", "Project",     12000.0),
]

REGIONS = [
    # region_id, region_name, province_code, population_weight
    ("R01", "Greater Toronto Area",  "ON", 0.20),
    ("R02", "Ottawa & Eastern ON",   "ON", 0.08),
    ("R03", "Southwestern Ontario",  "ON", 0.10),
    ("R04", "Greater Montreal",      "QC", 0.13),
    ("R05", "Quebec Regions",        "QC", 0.10),
    ("R06", "Greater Vancouver",     "BC", 0.09),
    ("R07", "BC Regions",            "BC", 0.05),
    ("R08", "Calgary & Southern AB", "AB", 0.06),
    ("R09", "Edmonton & Northern AB","AB", 0.05),
    ("R10", "Prairies (SK & MB)",    "SK", 0.05),
    ("R11", "Atlantic Canada",       "NS", 0.07),
    ("R12", "North & Territories",   "YT", 0.02),
]

SEGMENTS = [
    # seg_id, seg_name, seg_type
    ("S01", "Consumer - Postpaid",   "Consumer"),
    ("S02", "Consumer - Prepaid",    "Consumer"),
    ("S03", "Consumer - Premium",    "Consumer"),
    ("S04", "Small Business",        "SMB"),
    ("S05", "Mid-Market",            "Enterprise"),
    ("S06", "Large Enterprise",      "Enterprise"),
    ("S07", "Public Sector",         "Enterprise"),
]

CHANNELS = [
    ("C01", "Direct - Retail Stores"),
    ("C02", "Direct - Online"),
    ("C03", "Direct - Call Centre"),
    ("C04", "Dealer / Partner"),
    ("C05", "Enterprise Account Team"),
]


# ---- Date dim (last 24 full months ending 2026-06) -----------------------

def month_iter(start_year, start_month, n):
    y, m = start_year, start_month
    for _ in range(n):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


MONTHS = list(month_iter(2024, 7, 24))   # 2024-07 .. 2026-06
LATEST_YEAR, LATEST_MONTH = MONTHS[-1]

QUARTER = {1: "Q1", 2: "Q1", 3: "Q1", 4: "Q2", 5: "Q2", 6: "Q2",
           7: "Q3", 8: "Q3", 9: "Q3", 10: "Q4", 11: "Q4", 12: "Q4"}
MONTH_NAME = {1: "January", 2: "February", 3: "March", 4: "April",
              5: "May", 6: "June", 7: "July", 8: "August",
              9: "September", 10: "October", 11: "November", 12: "December"}


# ---- Synthetic generators -------------------------------------------------

@dataclass
class BUParams:
    base_subs: int          # nation-wide subs in earliest month
    arpu_target: float      # rough $ ARPU we aim for in latest month
    subs_growth_pm: float   # avg monthly subs growth (%)
    arpu_drift_pm: float    # avg monthly ARPU change (%)
    churn_rate_pm: float    # voluntary churn % of base per month
    gross_margin: float     # blended gross margin


BU_PARAMS = {
    "BU01": BUParams(base_subs=10_900_000, arpu_target=58.6, subs_growth_pm=0.0030,
                     arpu_drift_pm=0.0008,  churn_rate_pm=0.0098, gross_margin=0.58),
    "BU02": BUParams(base_subs= 2_500_000, arpu_target=132.0, subs_growth_pm=-0.0008,
                     arpu_drift_pm=0.0012,  churn_rate_pm=0.0124, gross_margin=0.52),
    "BU03": BUParams(base_subs=   480_000, arpu_target= 23.0, subs_growth_pm=0.0090,
                     arpu_drift_pm=0.0020,  churn_rate_pm=0.0220, gross_margin=0.34),
    "BU04": BUParams(base_subs=    61_000, arpu_target=420.0, subs_growth_pm=0.0080,
                     arpu_drift_pm=0.0030,  churn_rate_pm=0.0070, gross_margin=0.46),
}

SEG_WEIGHT_BY_BU = {
    "BU01": [("S01", 0.46), ("S02", 0.18), ("S03", 0.20), ("S04", 0.10),
             ("S05", 0.04), ("S06", 0.015), ("S07", 0.005)],
    "BU02": [("S01", 0.55), ("S03", 0.25), ("S04", 0.14), ("S05", 0.04),
             ("S06", 0.015), ("S07", 0.005), ("S02", 0.0)],
    "BU03": [("S01", 0.62), ("S03", 0.30), ("S05", 0.04), ("S06", 0.03),
             ("S07", 0.01), ("S02", 0.0), ("S04", 0.0)],
    "BU04": [("S04", 0.35), ("S05", 0.32), ("S06", 0.22), ("S07", 0.11),
             ("S01", 0.0), ("S02", 0.0), ("S03", 0.0)],
}


def write_csv(name, header, rows):
    path = OUT / f"{name}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  wrote {name:<28s} {len(rows):>9,} rows  -> {path.name}")


# ---- Dimension files ------------------------------------------------------

def gen_dim_date():
    rows = []
    for y, m in MONTHS:
        first = date(y, m, 1)
        key = first.strftime("%Y-%m")
        rows.append([
            key,                       # date_key 'YYYY-MM'
            first.isoformat(),         # month_start
            y,                         # fiscal_year (calendar = fiscal here)
            QUARTER[m],
            f"{y}-{QUARTER[m]}",       # year_quarter
            m,                         # month_number
            MONTH_NAME[m],
            f"{MONTH_NAME[m][:3]} {y}",
        ])
    write_csv("dim_date",
              ["date_key", "month_start", "fiscal_year", "fiscal_quarter",
               "year_quarter", "month_number", "month_name", "month_label"],
              rows)


def gen_dim_business_unit():
    rows = [[bu_id, name, bu_type] for bu_id, name, bu_type in BUSINESS_UNITS]
    write_csv("dim_business_unit",
              ["bu_id", "bu_name", "bu_type"], rows)


def gen_dim_product():
    rows = [[pid, pname, bu, rtype, price] for pid, pname, bu, rtype, price in PRODUCTS]
    write_csv("dim_product",
              ["product_id", "product_name", "bu_id", "revenue_type", "list_price"], rows)


def gen_dim_region():
    rows = [[r, name, prov, w] for r, name, prov, w in REGIONS]
    write_csv("dim_region",
              ["region_id", "region_name", "province_code", "population_weight"], rows)


def gen_dim_customer_segment():
    rows = [[s, name, stype] for s, name, stype in SEGMENTS]
    write_csv("dim_customer_segment",
              ["segment_id", "segment_name", "segment_type"], rows)


def gen_dim_channel():
    rows = [[c, name] for c, name in CHANNELS]
    write_csv("dim_channel",
              ["channel_id", "channel_name"], rows)


# ---- Fact: subscribers (monthly) -----------------------------------------

def split_segments(total, bu_id):
    """Allocate a monthly per-(BU,region,product) subscriber total across segments."""
    weights = SEG_WEIGHT_BY_BU[bu_id]
    out = []
    running = 0
    for i, (seg_id, w) in enumerate(weights):
        if i == len(weights) - 1:
            out.append((seg_id, max(0, total - running)))
        else:
            v = int(round(total * w))
            out.append((seg_id, v))
            running += v
    return out


def gen_facts():
    """Generate revenue, subscribers, churn, costs in one pass to keep
    relationships consistent (revenue / avg-subs reconciles to ARPU)."""
    revenue_rows = []
    subs_rows = []
    churn_rows = []
    cost_rows = []

    # National monthly trajectories per BU
    bu_trajectory = {}
    for bu_id, p in BU_PARAMS.items():
        subs_path = []
        arpu_path = []
        s = p.base_subs
        # back out starting ARPU from target and drift over 24 months
        a = p.arpu_target / ((1 + p.arpu_drift_pm) ** 24)
        for i in range(len(MONTHS)):
            # add seasonality + noise
            season = 1 + 0.012 * (1 if MONTHS[i][1] in (11, 12, 6) else 0)
            noise_s = random.uniform(-0.004, 0.004)
            noise_a = random.uniform(-0.004, 0.004)
            s = max(1, s * (1 + p.subs_growth_pm + noise_s) * season)
            a = a * (1 + p.arpu_drift_pm + noise_a)
            subs_path.append(s)
            arpu_path.append(a)
        bu_trajectory[bu_id] = (subs_path, arpu_path)

    # ---- Inject a Finance-relevant anomaly for the demo:
    # Wireless prepaid (P004) ARPU dips in Apr 2026 due to a promo glitch
    # that recovers by Jun 2026. Lets a presenter say: "Ask Copilot what
    # happened to Wireless Prepaid ARPU in April."
    promo_glitch_month = MONTHS.index((2026, 4))
    promo_glitch_recovery = MONTHS.index((2026, 6))

    # ---- Generate monthly facts at BU x Product x Region grain
    for bu_id, _, _ in BUSINESS_UNITS:
        p = BU_PARAMS[bu_id]
        products_in_bu = [pid for pid, _, b, _, _ in PRODUCTS if b == bu_id]
        # equal weight across products, with slight variation
        product_weights = {pid: random.uniform(0.7, 1.3) for pid in products_in_bu}
        total_pw = sum(product_weights.values())
        product_weights = {k: v / total_pw for k, v in product_weights.items()}

        subs_path, arpu_path = bu_trajectory[bu_id]

        for idx, (y, m) in enumerate(MONTHS):
            date_key = f"{y:04d}-{m:02d}"
            month_total_subs = subs_path[idx]
            month_arpu = arpu_path[idx]

            for pid in products_in_bu:
                product_subs = month_total_subs * product_weights[pid]
                # ARPU drift for this product
                base_price = next(pr for p_, _, b_, _, pr in PRODUCTS if p_ == pid)
                product_arpu = month_arpu * (base_price / 60.0 if base_price > 0 else 0.5)
                product_arpu = max(2.0, product_arpu)

                # promo glitch on prepaid
                if pid == "P004" and promo_glitch_month <= idx <= promo_glitch_recovery:
                    severity = 1.0 - 0.18 * (1 - (idx - promo_glitch_month) /
                                             max(1, promo_glitch_recovery - promo_glitch_month))
                    product_arpu *= severity

                for region_id, _, _, pop_w in REGIONS:
                    reg_subs = product_subs * pop_w * random.uniform(0.92, 1.08)
                    reg_arpu = product_arpu * random.uniform(0.96, 1.04)
                    revenue = reg_subs * reg_arpu

                    revenue_rows.append([
                        date_key, bu_id, pid, region_id,
                        round(revenue, 2),
                        round(reg_arpu, 4),
                    ])

                    # Subscribers split by segment
                    avg_subs = int(round(reg_subs))
                    end_subs = int(round(reg_subs * random.uniform(0.997, 1.003)))
                    for seg_id, seg_subs in split_segments(avg_subs, bu_id):
                        if seg_subs <= 0:
                            continue
                        seg_end_subs = int(round(seg_subs * (end_subs / max(1, avg_subs))))
                        subs_rows.append([
                            date_key, bu_id, pid, region_id, seg_id,
                            seg_subs, seg_end_subs,
                        ])

                    # Churn (gross adds + voluntary + involuntary)
                    gross_adds = int(round(reg_subs * (p.subs_growth_pm + p.churn_rate_pm)
                                           * random.uniform(0.9, 1.1)))
                    vol_churn = int(round(reg_subs * p.churn_rate_pm
                                          * random.uniform(0.9, 1.1)))
                    inv_churn = int(round(vol_churn * random.uniform(0.10, 0.25)))
                    churn_rows.append([
                        date_key, bu_id, pid, region_id,
                        gross_adds, vol_churn, inv_churn,
                    ])

                    # Costs: COGS + network opex + CAC
                    cogs = revenue * (1 - p.gross_margin) * random.uniform(0.95, 1.05)
                    network_opex = revenue * random.uniform(0.08, 0.14)
                    cac = gross_adds * random.uniform(35, 90) if base_price > 0 else 0
                    cost_rows.append([
                        date_key, bu_id, pid, region_id,
                        round(cogs, 2), round(network_opex, 2), round(cac, 2),
                    ])

    write_csv("fact_revenue_monthly",
              ["date_key", "bu_id", "product_id", "region_id",
               "revenue", "list_arpu"],
              revenue_rows)
    write_csv("fact_subscribers_monthly",
              ["date_key", "bu_id", "product_id", "region_id", "segment_id",
               "avg_subscribers", "end_subscribers"],
              subs_rows)
    write_csv("fact_churn_monthly",
              ["date_key", "bu_id", "product_id", "region_id",
               "gross_adds", "voluntary_churn", "involuntary_churn"],
              churn_rows)
    write_csv("fact_costs_monthly",
              ["date_key", "bu_id", "product_id", "region_id",
               "cogs", "network_opex", "customer_acquisition_cost"],
              cost_rows)


def main():
    print(f"Writing CSVs to {OUT}")
    gen_dim_date()
    gen_dim_business_unit()
    gen_dim_product()
    gen_dim_region()
    gen_dim_customer_segment()
    gen_dim_channel()
    gen_facts()
    print("\nDone. Demo narrative hooks:")
    print("  - Hero metric: ARPU (Revenue / Average Subscribers)")
    print("  - Promo-glitch anomaly: Wireless Prepaid (P004) ARPU dips Apr-Jun 2026")
    print("  - LOBs: Wireless / Cable & Home / Media / Enterprise")
    print(f"  - 24 months, {len(MONTHS[0])}-{MONTHS[0]} to {MONTHS[-1]}")


if __name__ == "__main__":
    main()
