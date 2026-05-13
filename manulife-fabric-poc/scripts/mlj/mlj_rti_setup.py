"""Build a Real-Time Intelligence stack for the MLJ POC:
1. Eventhouse + KQL database
2. transaction_events_rt table (live AML / portal / claim events)
3. Seed with ~2000 synthetic events spanning the last 24h
4. Save context for dashboard creation
"""
import subprocess, json, urllib.request, time, sys, io, random
from datetime import datetime, timedelta, timezone
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def sh(c): return subprocess.check_output(c, shell=True).decode().strip()

with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json") as f:
    C = json.load(f)
WS = C["workspace_id"]
TOKEN = sh("az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv")

def fab(method, url, body=None, timeout=180):
    data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower():v for k,v in r.headers.items()}, r.read().decode() if r.status != 202 else ""
    except urllib.error.HTTPError as e:
        return e.code, {k.lower():v for k,v in (e.headers.items() if e.headers else [])}, e.read().decode()

def wait_op(op):
    for _ in range(80):
        time.sleep(3)
        _, _, b = fab("GET", f"https://api.fabric.microsoft.com/v1/operations/{op}")
        s = json.loads(b)
        if s.get("status") in ("Succeeded","Failed"): return s
    return {"status":"Timeout"}

# --- 1. Create Eventhouse ---
print("== Creating Eventhouse ==")
s, h, b = fab("GET", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/eventhouses")
existing = [x for x in json.loads(b).get("value",[]) if x["displayName"] == "MLJ_RealTimeHub"]
if existing:
    eh = existing[0]
    print(f"  Found existing: {eh['id']}")
else:
    s, h, b = fab("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/eventhouses",
                  {"displayName":"MLJ_RealTimeHub",
                   "description":"Real-Time Intelligence hub for MLJ - live AML, portal click-stream, claim events"})
    print(f"  HTTP {s}")
    if s == 202:
        op = h.get("x-ms-operation-id")
        res = wait_op(op)
        print(f"  status: {res.get('status')}")
        if res.get("status") != "Succeeded":
            print(f"  err: {res}"); sys.exit(1)
        _, _, rb = fab("GET", f"https://api.fabric.microsoft.com/v1/operations/{op}/result")
        eh = json.loads(rb)
    elif s == 201:
        eh = json.loads(b)
    else:
        print(f"  failed: {b[:500]}"); sys.exit(1)
print(f"  Eventhouse id: {eh['id']}")

# --- 2. Get Eventhouse properties (cluster URL, default KQL DB) ---
print("\n== Fetching Eventhouse cluster URLs ==")
for _ in range(20):
    s, h, b = fab("GET", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/eventhouses/{eh['id']}")
    info = json.loads(b)
    props = info.get("properties", {})
    query_uri = props.get("queryServiceUri")
    ingest_uri = props.get("ingestionServiceUri")
    db_ids = props.get("databasesItemIds", [])
    if query_uri and db_ids:
        print(f"  Query URI: {query_uri}")
        print(f"  Ingest URI: {ingest_uri}")
        print(f"  Default DB IDs: {db_ids}")
        break
    time.sleep(5)
else:
    print("  cluster info not ready"); sys.exit(2)

# Get default KQL DB display name
default_db_id = db_ids[0]
s, h, b = fab("GET", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/kqlDatabases/{default_db_id}")
db_info = json.loads(b)
DB_NAME = db_info["displayName"]
print(f"  Default DB name: {DB_NAME}")

# Save to context
C["eventhouse_id"] = eh["id"]
C["kql_db_id"] = default_db_id
C["kql_db_name"] = DB_NAME
C["kql_query_uri"] = query_uri
C["kql_ingest_uri"] = ingest_uri
with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json","w") as f:
    json.dump(C, f, indent=2)

# --- 3. Kusto: create table + ingest data ---
print("\n== Authenticating to Kusto cluster ==")
KUSTO_TOKEN = sh(f"az account get-access-token --resource {query_uri} --query accessToken -o tsv")

def kusto(cluster_uri, db, query, is_mgmt=False):
    path = "/v1/rest/mgmt" if is_mgmt else "/v2/rest/query"
    url = cluster_uri + path
    body = json.dumps({"db": db, "csl": query, "properties":{"Options":{"queryconsistency":"strongconsistency"}}}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                  headers={"Authorization": f"Bearer {KUSTO_TOKEN}",
                                           "Content-Type": "application/json; charset=utf-8",
                                           "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

# Create / replace table
print("\n== Creating transaction_events_rt table ==")
create_table = """.create-merge table transaction_events_rt (
    EventId: string,
    EventTime: datetime,
    EventType: string,
    CustomerId: string,
    Prefecture: string,
    BranchOffice: string,
    Channel: string,
    Amount: real,
    PaymentMethod: string,
    Status: string,
    AlertLevel: string,
    AdvisorId: string,
    PolicyId: string,
    Notes: string
)"""
s, b = kusto(query_uri, DB_NAME, create_table, is_mgmt=True)
print(f"  HTTP {s}")
if s >= 400: print(f"  body: {b[:500]}")

# Generate ~2000 events spanning last 24 hours
print("\n== Generating synthetic events ==")
random.seed(20260513)
EVENT_TYPES = [
    ("PortalLogin",      0.30, "Portal",   "Completed",   "INFO"),
    ("PolicyView",       0.18, "Portal",   "Completed",   "INFO"),
    ("PremiumPayment",   0.12, "Direct Debit", "Completed","INFO"),
    ("InvestmentTrade",  0.08, "Portal",   "Completed",   "INFO"),
    ("ClaimSubmission",  0.05, "Mobile",   "Pending",     "INFO"),
    ("AdvisorContact",   0.07, "Branch",   "Completed",   "INFO"),
    ("AddressChange",    0.04, "Portal",   "Completed",   "WATCH"),
    ("BeneficiaryChange",0.03, "Branch",   "Completed",   "WATCH"),
    ("LargeWithdrawal",  0.05, "Wire",     "Completed",   "REVIEW"),
    ("CashPayment",      0.03, "Konbini",  "Completed",   "REVIEW"),
    ("FailedLogin",      0.05, "Portal",   "Failed",      "WATCH"),
]
PREFECTURES = ["TOKYO","OSAKA","KANAGAWA","AICHI","HOKKAIDO","FUKUOKA","HYOGO","KYOTO","HIROSHIMA","MIYAGI","SAITAMA","CHIBA"]
BRANCHES = ["Tokyo Marunouchi","Tokyo Shibuya","Yokohama Minato Mirai","Osaka Umeda","Kobe Sannomiya","Nagoya Sakae","Sapporo Odori","Fukuoka Tenjin","Sendai Aoba","Kyoto Karasuma"]

now = datetime.now(timezone.utc)
events = []
for i in range(2000):
    et = random.choices([e[0] for e in EVENT_TYPES], weights=[e[1] for e in EVENT_TYPES])[0]
    spec = next(e for e in EVENT_TYPES if e[0]==et)
    # Pump some recent activity (last hour) heavier than older - half within last 1h
    if random.random() < 0.45:
        delta_min = random.uniform(0, 60)
    else:
        delta_min = random.uniform(60, 24*60)
    ts = now - timedelta(minutes=delta_min)
    cust_id = f"CUS-{random.randint(1,200):04d}"
    adv_id = f"ADV-{random.randint(1,30):04d}"
    pol_id = f"POL-{random.randint(1,400):05d}" if et in ("PolicyView","PremiumPayment","ClaimSubmission","BeneficiaryChange") else ""
    # Amount logic
    if et == "PremiumPayment": amount = round(random.uniform(20000, 500000),0)
    elif et == "InvestmentTrade": amount = round(random.uniform(100000, 5_000_000),0)
    elif et == "ClaimSubmission": amount = round(random.uniform(50_000, 3_000_000),0)
    elif et == "LargeWithdrawal": amount = round(random.uniform(5_000_000, 50_000_000),0)
    elif et == "CashPayment": amount = round(random.uniform(1_000_000, 10_000_000),0)
    else: amount = 0
    # AML uplift
    alert = spec[4]
    if et == "LargeWithdrawal" and amount > 10_000_000: alert = "REVIEW"
    if et == "CashPayment" and amount > 1_000_000: alert = "REVIEW"
    notes = ""
    if alert == "REVIEW":
        notes = random.choice(["Routed to AML team","Awaiting CDD review","Flagged: amount threshold","Beneficiary mismatch"])
    elif alert == "WATCH":
        notes = random.choice(["Soft watch","Pattern monitor","Velocity check"])
    events.append({
        "EventId": f"E-{i:06d}",
        "EventTime": ts.isoformat(),
        "EventType": et,
        "CustomerId": cust_id,
        "Prefecture": random.choice(PREFECTURES),
        "BranchOffice": random.choice(BRANCHES),
        "Channel": spec[2],
        "Amount": amount,
        "PaymentMethod": spec[2] if spec[2] in ("Direct Debit","Wire","Konbini","Bank Transfer") else "n/a",
        "Status": spec[3],
        "AlertLevel": alert,
        "AdvisorId": adv_id,
        "PolicyId": pol_id,
        "Notes": notes,
    })

# Ingest inline (single .ingest command)
def kql_csv_escape(v):
    if v is None: return ""
    s = str(v)
    if any(c in s for c in [',','"','\n']):
        return '"' + s.replace('"','""') + '"'
    return s

print(f"  Ingesting {len(events)} events via .ingest inline ...")
# Build CSV body
cols = ["EventId","EventTime","EventType","CustomerId","Prefecture","BranchOffice","Channel","Amount","PaymentMethod","Status","AlertLevel","AdvisorId","PolicyId","Notes"]
csv_lines = [",".join(kql_csv_escape(e[c]) for c in cols) for e in events]

# Use .ingest inline with into and with batch (KQL inline ingest)
# Build the multi-line command
ingest_cmd = ".ingest inline into table transaction_events_rt with(format='csv') <|\n" + "\n".join(csv_lines)
# Single .ingest inline can take a lot but let's split into batches of 500
batch_size = 500
total = 0
for i in range(0, len(events), batch_size):
    batch = csv_lines[i:i+batch_size]
    cmd = ".ingest inline into table transaction_events_rt with(format='csv') <|\n" + "\n".join(batch)
    s, b = kusto(query_uri, DB_NAME, cmd, is_mgmt=True)
    if s >= 400:
        print(f"  batch {i}: HTTP {s} - {b[:400]}")
        break
    total += len(batch)
    print(f"  ingested {total}/{len(events)}")

# Verify
print("\n== Verifying ingest ==")
s, b = kusto(query_uri, DB_NAME, "transaction_events_rt | count")
print(f"  count HTTP {s}: {b[:300]}")

# Print useful KQL queries for dashboard
print("\n== Sample dashboard queries (ready for tiles) ==")
queries = {
"Last hour - events per minute":
"transaction_events_rt | where EventTime > ago(1h) | summarize Events = count() by bin(EventTime, 1m) | render timechart",

"Alert level distribution (last 24h)":
"transaction_events_rt | where EventTime > ago(24h) | summarize Count = count() by AlertLevel | render piechart",

"Top 10 review-level events (most recent)":
"transaction_events_rt | where AlertLevel == 'REVIEW' | top 10 by EventTime desc | project EventTime, EventType, CustomerId, BranchOffice, Amount, Notes",

"Transaction value by branch (last 24h)":
"transaction_events_rt | where EventTime > ago(24h) and Amount > 0 | summarize TotalAmount = sum(Amount) by BranchOffice | top 10 by TotalAmount desc | render barchart",

"Prefecture heatmap (last 24h)":
"transaction_events_rt | where EventTime > ago(24h) | summarize Events = count() by Prefecture | render columnchart",

"Failed logins last hour":
"transaction_events_rt | where EventTime > ago(1h) and EventType == 'FailedLogin' | summarize FailedLogins = count() by CustomerId | top 20 by FailedLogins desc",
}
for name, q in queries.items():
    print(f"\n--- {name} ---\n{q}")

print("\n== DONE ==")
