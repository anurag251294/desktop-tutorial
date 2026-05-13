"""Live event simulator for the MLJ RT demo.

Run this in a terminal during the demo. It pushes 1-3 events/sec into the
Eventhouse for ~5 minutes (or until Ctrl-C). The dashboard auto-refreshes
and you can watch the timechart tick up live.

  python mlj_rti_stream.py [seconds]   # default 300s

The simulator deliberately injects a couple of 'REVIEW'-level events every
30 seconds so the AML tile shows new entries during the demo.
"""
import subprocess, json, urllib.request, time, sys, io, random
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def sh(c): return subprocess.check_output(c, shell=True).decode().strip()

with open(r"C:\Users\anuragdhuria\AppData\Local\Temp\mlj_ctx.json") as f:
    C = json.load(f)
DB = C["kql_db_name"]; QURI = C["kql_query_uri"]
KTOKEN = sh(f"az account get-access-token --resource {QURI} --query accessToken -o tsv")

def kusto(query):
    url = QURI + "/v1/rest/mgmt"
    body = json.dumps({"db": DB, "csl": query}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                  headers={"Authorization": f"Bearer {KTOKEN}",
                                           "Content-Type":"application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return r.status, r.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()

EVENT_TYPES = ["PortalLogin","PolicyView","PremiumPayment","InvestmentTrade","ClaimSubmission",
               "AdvisorContact","AddressChange","BeneficiaryChange","LargeWithdrawal","CashPayment","FailedLogin"]
PREFECTURES = ["TOKYO","OSAKA","KANAGAWA","AICHI","HOKKAIDO","FUKUOKA","HYOGO","KYOTO","HIROSHIMA","MIYAGI","SAITAMA","CHIBA"]
BRANCHES = ["Tokyo Marunouchi","Tokyo Shibuya","Yokohama Minato Mirai","Osaka Umeda","Kobe Sannomiya",
            "Nagoya Sakae","Sapporo Odori","Fukuoka Tenjin","Sendai Aoba","Kyoto Karasuma"]

def make_event(force_review=False):
    if force_review:
        et = random.choice(["LargeWithdrawal","CashPayment"])
        amount = random.uniform(10_000_000, 60_000_000) if et=="LargeWithdrawal" else random.uniform(2_000_000, 15_000_000)
        alert = "REVIEW"
        notes = random.choice(["Routed to AML team","Beneficiary mismatch","CDD review needed","High-velocity flag"])
    else:
        et = random.choice(EVENT_TYPES)
        amount = random.uniform(20_000, 1_000_000) if et in ("PremiumPayment","InvestmentTrade","ClaimSubmission") else 0
        alert = random.choices(["INFO","WATCH","REVIEW"], weights=[80,15,5])[0]
        notes = "" if alert == "INFO" else random.choice(["Soft watch","Pattern monitor","Velocity check"])
    return {
        "EventId": f"L-{int(time.time()*1000)}-{random.randint(1000,9999)}",
        "EventTime": datetime.now(timezone.utc).isoformat(),
        "EventType": et,
        "CustomerId": f"CUS-{random.randint(1,200):04d}",
        "Prefecture": random.choice(PREFECTURES),
        "BranchOffice": random.choice(BRANCHES),
        "Channel": random.choice(["Portal","Mobile","Branch","Direct Debit","Wire","Konbini"]),
        "Amount": round(amount, 0),
        "PaymentMethod": random.choice(["Direct Debit","Wire","Konbini","Bank Transfer","n/a"]),
        "Status": "Completed" if et!="FailedLogin" else "Failed",
        "AlertLevel": alert,
        "AdvisorId": f"ADV-{random.randint(1,30):04d}",
        "PolicyId": "" if et in ("PortalLogin","FailedLogin") else f"POL-{random.randint(1,400):05d}",
        "Notes": notes,
    }

def csv_esc(v):
    s = str(v) if v is not None else ""
    if any(c in s for c in [',','"','\n']): return '"' + s.replace('"','""') + '"'
    return s

duration = int(sys.argv[1]) if len(sys.argv) > 1 else 300
print(f"== Streaming events for {duration}s ==", flush=True)
print(f"  Database: {DB}", flush=True)
print(f"  Watch the RT dashboard auto-refresh", flush=True)
print(f"  Ctrl-C to stop early\n", flush=True)

start = time.time()
n = 0
cols = ["EventId","EventTime","EventType","CustomerId","Prefecture","BranchOffice","Channel","Amount","PaymentMethod","Status","AlertLevel","AdvisorId","PolicyId","Notes"]
try:
    while time.time() - start < duration:
        # Build a small batch of 2-5 events
        batch_size = random.randint(2, 5)
        # Inject one REVIEW event every ~30s
        force_review_idx = 0 if int(time.time()) % 30 == 0 and random.random() < 0.5 else -1
        events = [make_event(force_review=(i==force_review_idx)) for i in range(batch_size)]
        csv = "\n".join(",".join(csv_esc(e[c]) for c in cols) for e in events)
        cmd = ".ingest inline into table transaction_events_rt with(format='csv') <|\n" + csv
        s, b = kusto(cmd)
        if s >= 400:
            print(f"  ingest err: HTTP {s}: {b[:200]}", flush=True)
            time.sleep(2); continue
        n += batch_size
        if n % 20 == 0:
            elapsed = int(time.time() - start)
            print(f"  [{elapsed:>3}s] {n:>4} events ingested  (rate ~{n/elapsed:.1f}/sec)", flush=True)
        # Refresh token periodically (1hr token lifetime)
        if time.time() - start > 3000:
            KTOKEN = sh(f"az account get-access-token --resource {QURI} --query accessToken -o tsv")
            start = time.time() - 100  # reset window
        time.sleep(random.uniform(0.5, 1.5))
except KeyboardInterrupt:
    print(f"\n  stopped at {n} events", flush=True)
print(f"\n== Done. Total streamed: {n} events ==", flush=True)
