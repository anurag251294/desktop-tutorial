"""Generate JP-context demo data for the Manulife Japan POC.

Same column shapes as the CA POC so we can reuse the silver/gold notebooks with
minimal change. Domain alignment happens at the silver layer (Customer /
Distributor / Product / Finance / System). All currency values are JPY (yen).
"""
import csv, random, os
from datetime import date, datetime, timedelta

random.seed(20260513)
OUT = r"C:\Users\anuragdhuria\OneDrive - Microsoft\Documents\GitHub\desktop-tutorial\manulife-fabric-poc\data\raw\structured_jp"
os.makedirs(OUT, exist_ok=True)

# ---- JP name pools (romanized) ----
JP_SURNAMES = ["Tanaka","Sato","Suzuki","Watanabe","Ito","Yamamoto","Nakamura","Kobayashi","Kato","Yoshida",
               "Yamada","Sasaki","Yamaguchi","Matsumoto","Inoue","Kimura","Hayashi","Shimizu","Mori","Ikeda",
               "Hashimoto","Yamazaki","Ishikawa","Nakajima","Maeda","Fujita","Ogawa","Goto","Okada","Hasegawa"]
JP_GIVEN_MALE = ["Hiroshi","Kenji","Takeshi","Yusuke","Daiki","Ryo","Haruki","Shota","Takumi","Naoki",
                 "Tatsuya","Kazuki","Ryota","Tsuyoshi","Yuto","Kaito","Sora","Akira","Masashi","Jun"]
JP_GIVEN_FEMALE = ["Akiko","Yuki","Sakura","Mei","Hanako","Aoi","Hina","Yui","Rin","Mio",
                   "Saki","Ayaka","Yuna","Misaki","Nana","Kana","Riko","Kaori","Megumi","Mayumi"]

# Prefectures + sample cities
PREFECTURES = [
    ("Tokyo",       ["Shibuya","Shinjuku","Minato","Chiyoda","Setagaya","Bunkyo","Meguro","Shinagawa","Toshima","Sumida"]),
    ("Osaka",       ["Osaka","Sakai","Toyonaka","Suita","Higashiosaka"]),
    ("Kanagawa",    ["Yokohama","Kawasaki","Sagamihara","Yokosuka","Fujisawa"]),
    ("Aichi",       ["Nagoya","Toyota","Okazaki","Ichinomiya"]),
    ("Hokkaido",    ["Sapporo","Asahikawa","Hakodate"]),
    ("Fukuoka",     ["Fukuoka","Kitakyushu","Kurume"]),
    ("Hyogo",       ["Kobe","Himeji","Nishinomiya","Amagasaki"]),
    ("Kyoto",       ["Kyoto","Uji"]),
    ("Hiroshima",   ["Hiroshima","Fukuyama"]),
    ("Miyagi",      ["Sendai","Ishinomaki"]),
    ("Saitama",     ["Saitama","Kawaguchi","Kawagoe"]),
    ("Chiba",       ["Chiba","Funabashi","Matsudo","Ichikawa"]),
]
STREET_SUFFIXES = ["chome","ku-dori","sakura-cho","midori-ku","hon-machi","kita-cho","minami-cho","higashi-machi","nishi-machi"]

PRODUCTS = [
    # (name, category, line, min_cov, max_cov, rate, risk)
    ("Variable Annuity Plus",            "Investment",  "Wealth",         500000,  50000000, 0.0220, "Medium"),
    ("Variable Annuity Conservative",    "Investment",  "Wealth",         500000,  30000000, 0.0150, "Low"),
    ("Whole Life with Disability Rider", "Insurance",   "Life",           1000000, 200000000, 0.0085, "Low"),
    ("Term Life 20 (JP)",                "Insurance",   "Life",           500000,  100000000, 0.0018, "Low"),
    ("Endowment 15 (Kakushin)",          "Insurance",   "Life",           1000000, 50000000,  0.0055, "Low"),
    ("Cancer Insurance Plus",            "Insurance",   "Health",         500000,  20000000,  0.0095, "Medium"),
    ("Income Protection Standard",       "Insurance",   "Health",         100000,  10000000,  0.0072, "Medium"),
    ("Critical Illness Cover",           "Insurance",   "Health",         500000,  30000000,  0.0088, "Medium"),
    ("Group Pension Plan",               "Investment",  "Group",          1000000, 500000000, 0.0035, "Low"),
    ("Single Premium Whole Life",        "Insurance",   "Life",           5000000, 300000000, 0.0210, "Low"),
    ("Medical Insurance Comprehensive",  "Insurance",   "Health",         100000,  20000000,  0.0048, "Medium"),
    ("Education Endowment",              "Insurance",   "Life",           1000000, 30000000,  0.0042, "Low"),
]

FUNDS = [
    ("Manulife Japan TOPIX Index",       "Equity",     4, "Japan"),
    ("Manulife Japan Growth",            "Equity",     5, "Japan"),
    ("Manulife Asia ex-Japan Equity",    "Equity",     5, "Asia Pacific"),
    ("Manulife Global Equity",           "Equity",     4, "Global"),
    ("Manulife US Tech Innovation",      "Equity",     5, "North America"),
    ("Manulife Japan Government Bond",   "Fixed Income",1, "Japan"),
    ("Manulife Global Bond",             "Fixed Income",2, "Global"),
    ("Manulife Balanced Yen",            "Mixed",      3, "Japan"),
    ("Manulife Yen Money Market",        "Money Market",1, "Japan"),
    ("Manulife Sustainable Asia",        "Equity",     4, "Asia Pacific"),
]

BRANCHES = [
    ("Tokyo Marunouchi",   "Kanto"),
    ("Tokyo Shibuya",      "Kanto"),
    ("Yokohama Minato Mirai","Kanto"),
    ("Osaka Umeda",        "Kansai"),
    ("Kobe Sannomiya",     "Kansai"),
    ("Nagoya Sakae",       "Chubu"),
    ("Sapporo Odori",      "Hokkaido"),
    ("Fukuoka Tenjin",     "Kyushu"),
    ("Sendai Aoba",        "Tohoku"),
    ("Kyoto Karasuma",     "Kansai"),
]
CERT = ["Junior","Senior","Principal","Master"]
SPEC = ["Life Insurance","Health Insurance","Wealth Management","Variable Annuity","Group Pension","Estate Planning"]
SEGMENTS = ["Retail","Mass Affluent","High Net Worth","Ultra HNW","Group"]

# ---------- helpers ----------
def jp_phone():
    return f"0{random.randint(70,90)}-{random.randint(1000,9999)}-{random.randint(1000,9999)}"

def jp_postal():
    return f"{random.randint(100,999)}-{random.randint(1000,9999)}"

def jp_address(pref, city):
    return f"{random.randint(1,5)}-{random.randint(1,30)}-{random.randint(1,20)} {random.choice(STREET_SUFFIXES)}"

def jp_email(first, last, i):
    domains = ["outlook.jp","yahoo.co.jp","gmail.com","manulife.co.jp"]
    return f"{first.lower()}.{last.lower()}{i}@{random.choice(domains)}"

def rand_date(start, end):
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))

def yen(x):
    return int(round(x))

# ---------- 1. Customers (Customer domain) ----------
N_CUST = 200
customers = []
for i in range(1, N_CUST+1):
    gender = random.choice(["Male","Female"])
    last = random.choice(JP_SURNAMES)
    first = random.choice(JP_GIVEN_MALE if gender=="Male" else JP_GIVEN_FEMALE)
    pref, cities = random.choice(PREFECTURES)
    city = random.choice(cities)
    dob = rand_date(date(1945,1,1), date(2005,12,31))
    reg = rand_date(date(2018,1,1), date(2026,5,1))
    customers.append({
        "customer_id": f"CUS-{i:04d}",
        "first_name": first,
        "last_name": last,
        "email": jp_email(first, last, i),
        "phone": jp_phone(),
        "date_of_birth": dob.isoformat(),
        "gender": gender,
        "address_line1": jp_address(pref, city),
        "city": city,
        "province": pref,                # we reuse 'province' column name for prefecture
        "postal_code": jp_postal(),
        "country": "Japan",
        "customer_segment": random.choices(SEGMENTS, weights=[5,3,2,1,1])[0],
        "registration_date": reg.isoformat(),
        "is_active": random.choices(["TRUE","FALSE"], weights=[9,1])[0],
    })
with open(os.path.join(OUT,"customers.csv"),"w",newline="",encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(customers[0].keys()))
    w.writeheader(); w.writerows(customers)
print(f"customers: {len(customers)}")

# ---------- 2. Advisors (Distributor domain) ----------
N_ADV = 30
advisors = []
for i in range(1, N_ADV+1):
    gender = random.choice(["Male","Female"])
    last = random.choice(JP_SURNAMES)
    first = random.choice(JP_GIVEN_MALE if gender=="Male" else JP_GIVEN_FEMALE)
    branch, region = random.choice(BRANCHES)
    hire = rand_date(date(2008,1,1), date(2024,12,31))
    advisors.append({
        "advisor_id": f"ADV-{i:04d}",
        "first_name": first,
        "last_name": last,
        "email": f"{first.lower()}.{last.lower()}@manulife.co.jp",
        "branch_office": branch,
        "region": region,
        "certification_level": random.choice(CERT),
        "specialization": random.choice(SPEC),
        "hire_date": hire.isoformat(),
        "is_active": random.choices(["TRUE","FALSE"], weights=[19,1])[0],
        "aum_total": yen(random.uniform(500_000_000, 30_000_000_000)),   # JPY 500M to 30B
    })
with open(os.path.join(OUT,"advisors.csv"),"w",newline="",encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(advisors[0].keys()))
    w.writeheader(); w.writerows(advisors)
print(f"advisors: {len(advisors)}")

# ---------- 3. Products (Product domain) ----------
products = []
for i, (name, cat, line, mn, mx, rate, risk) in enumerate(PRODUCTS, start=1):
    products.append({
        "product_id": f"PRD-{i:04d}",
        "product_name": name,
        "product_category": cat,
        "product_line": line,
        "description": f"{name} - JPY-denominated insurance / investment product for the Japanese market",
        "min_coverage": mn,
        "max_coverage": mx,
        "base_premium_rate": rate,
        "launch_date": rand_date(date(2010,1,1), date(2023,12,31)).isoformat(),
        "is_active": "TRUE",
        "risk_tier": risk,
    })
with open(os.path.join(OUT,"products.csv"),"w",newline="",encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(products[0].keys()))
    w.writeheader(); w.writerows(products)
print(f"products: {len(products)}")

# ---------- 4. Policies (Finance domain) ----------
N_POL = 400
policies = []
status_choices = ["Active","Active","Active","Lapsed","Cancelled","Active"]
pay_freq = ["Monthly","Quarterly","Semi-Annual","Annual"]
for i in range(1, N_POL+1):
    cust = random.choice(customers)
    prod = random.choice(products)
    adv = random.choice(advisors)
    eff = rand_date(date(2018,1,1), date(2025,12,31))
    expiry_years = random.choice([10,15,20,30,99])
    exp = date(eff.year + expiry_years, eff.month, min(eff.day, 28))
    coverage = random.randint(prod["min_coverage"], prod["max_coverage"])
    premium = yen(coverage * prod["base_premium_rate"] * random.uniform(0.8, 1.2) / 12)   # monthly equiv ¥
    policies.append({
        "policy_id": f"POL-{i:05d}",
        "customer_id": cust["customer_id"],
        "product_id": prod["product_id"],
        "advisor_id": adv["advisor_id"],
        "policy_number": f"MLJ-{random.randint(100000,999999)}",
        "policy_type": prod["product_line"],
        "status": random.choice(status_choices),
        "effective_date": eff.isoformat(),
        "expiry_date": exp.isoformat(),
        "premium_amount": premium,
        "coverage_amount": coverage,
        "payment_frequency": random.choice(pay_freq),
        "last_payment_date": rand_date(date(2025,1,1), date(2026,5,1)).isoformat(),
        "risk_category": random.choice(["Low","Medium","High"]),
    })
with open(os.path.join(OUT,"policies.csv"),"w",newline="",encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(policies[0].keys()))
    w.writeheader(); w.writerows(policies)
print(f"policies: {len(policies)}")

# ---------- 5. Claims (Finance domain) ----------
N_CLM = 150
claims = []
claim_types = ["Hospitalisation","Surgery","Cancer Treatment","Critical Illness","Disability","Death Benefit","Outpatient","Annuity Withdrawal"]
status_c = [("Approved",0.55),("Denied",0.18),("Pending",0.20),("Under Review",0.07)]
denial_reasons = ["Pre-existing condition","Policy lapsed","Outside coverage","Documentation incomplete","Fraud suspected"]
ADJUSTERS = [f"{random.choice(JP_GIVEN_MALE+JP_GIVEN_FEMALE)} {random.choice(JP_SURNAMES)}" for _ in range(15)]
for i in range(1, N_CLM+1):
    pol = random.choice(policies)
    claim_dt = rand_date(date(2023,1,1), date(2026,5,1))
    status = random.choices([s[0] for s in status_c], weights=[s[1] for s in status_c])[0]
    claim_amt = yen(random.uniform(50_000, 5_000_000))   # JPY 50k - 5M
    if status == "Approved":
        approved = yen(claim_amt * random.uniform(0.65, 1.0))
        res = claim_dt + timedelta(days=random.randint(7,45))
        denial = ""
    elif status == "Denied":
        approved = 0
        res = claim_dt + timedelta(days=random.randint(7,30))
        denial = random.choice(denial_reasons)
    else:
        approved = 0
        res = ""
        denial = ""
    claims.append({
        "claim_id": f"CLM-{i:05d}",
        "policy_id": pol["policy_id"],
        "customer_id": pol["customer_id"],
        "claim_number": f"JPN-{random.randint(100000,999999)}",
        "claim_date": claim_dt.isoformat(),
        "claim_type": random.choice(claim_types),
        "claim_amount": claim_amt,
        "approved_amount": approved,
        "status": status,
        "adjuster_name": random.choice(ADJUSTERS),
        "resolution_date": res.isoformat() if res else "",
        "denial_reason": denial,
        "notes": random.choice(["","Senior reviewer assigned","Customer escalation","Routine review","Complex case"]),
    })
with open(os.path.join(OUT,"claims.csv"),"w",newline="",encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(claims[0].keys()))
    w.writeheader(); w.writerows(claims)
print(f"claims: {len(claims)}")

# ---------- 6. Investments (Finance domain) ----------
N_INV = 200
investments = []
for i in range(1, N_INV+1):
    cust = random.choice(customers)
    adv = random.choice(advisors)
    fund, ftype, rrate, fregion = random.choice(FUNDS)
    inv_amt = yen(random.uniform(500_000, 30_000_000))
    perf = random.uniform(-0.20, 0.25)
    inception = rand_date(date(2018,1,1), date(2025,12,31))
    investments.append({
        "investment_id": f"INV-{i:05d}",
        "customer_id": cust["customer_id"],
        "advisor_id": adv["advisor_id"],
        "fund_name": fund,
        "fund_type": ftype,
        "investment_amount": inv_amt,
        "current_value": yen(inv_amt * (1 + perf)),
        "inception_date": inception.isoformat(),
        "last_valuation_date": rand_date(date(2026,4,1), date(2026,5,1)).isoformat(),
        "return_ytd_pct": round(perf * 100 * random.uniform(0.3, 1.0), 2),
        "return_1yr_pct": round(perf * 100, 2),
        "risk_rating": rrate,
        "region": fregion,
    })
with open(os.path.join(OUT,"investments.csv"),"w",newline="",encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(investments[0].keys()))
    w.writeheader(); w.writerows(investments)
print(f"investments: {len(investments)}")

# ---------- 7. Transactions (Finance domain) ----------
N_TXN = 800
transactions = []
txn_types = ["Premium Payment","Investment Purchase","Investment Redemption","Annuity Payout","Claim Settlement","Policy Loan","Loan Repayment"]
methods = ["Bank Transfer","Direct Debit","Credit Card","Convenience Store (Konbini)","Furikomi"]
for i in range(1, N_TXN+1):
    txn_type = random.choice(txn_types)
    cust = random.choice(customers)
    pol_id = ""; inv_id = ""; amount = 0
    if txn_type == "Premium Payment":
        pol = random.choice([p for p in policies if p["customer_id"] == cust["customer_id"]] or [random.choice(policies)])
        pol_id = pol["policy_id"]; cust_id = pol["customer_id"]
        amount = pol["premium_amount"]
    elif txn_type in ("Investment Purchase","Investment Redemption"):
        inv = random.choice(investments)
        inv_id = inv["investment_id"]; cust_id = inv["customer_id"]
        amount = yen(random.uniform(100_000, 5_000_000))
    elif txn_type == "Claim Settlement":
        clm = random.choice([c for c in claims if c["status"]=="Approved"] or [random.choice(claims)])
        pol_id = clm["policy_id"]; cust_id = clm["customer_id"]
        amount = clm["approved_amount"]
    else:
        cust_id = cust["customer_id"]
        amount = yen(random.uniform(50_000, 2_000_000))
    transactions.append({
        "transaction_id": f"TXN-{i:06d}",
        "customer_id": cust_id,
        "policy_id": pol_id,
        "investment_id": inv_id,
        "transaction_type": txn_type,
        "amount": amount,
        "transaction_date": rand_date(date(2024,1,1), date(2026,5,1)).isoformat(),
        "payment_method": random.choice(methods),
        "status": random.choices(["Completed","Pending","Failed"], weights=[18,1,1])[0],
        "reference_number": f"REF-{random.randint(10_000_000, 99_999_999)}",
    })
with open(os.path.join(OUT,"transactions.csv"),"w",newline="",encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(transactions[0].keys()))
    w.writeheader(); w.writerows(transactions)
print(f"transactions: {len(transactions)}")

print(f"\nAll JP data written to: {OUT}")
