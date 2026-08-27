"""Approximate the generator and criteria in plain Python to predict the cohort split.

Cheaper than a Spark run and catches the two failure modes that would kill the demo:
a flag that fires on almost nobody, and one that fires on almost everybody.

APPROXIMATE, not identical. It mirrors the notebook's RNG draw for draw, which is
enough to land within a point of the real split -- the live 2026-08-27 run surfaced
9.2% against 9.0% here -- but small differences remain, and months_in_service is
calendar-accurate in Spark and a 30.44-day approximation here. Use it to decide whether
the thresholds are sane before spending capacity. Do not quote its numbers as results;
quote the run.
"""
import random
from collections import Counter
from datetime import date, timedelta

COHORT_SIZE = 2400
MONTHS_OF_HISTORY = 36
COHORT_SEED = 20260827
MIN_RECORD_DAYS = 180

MIN_SYSTEMS_MULTI = 3
MIN_SPECIALTIES_ODYSSEY = 4
MIN_MONTHS_ODYSSEY = 12
MAX_DIAGNOSED_SHARE_ODYSSEY = 0.5
MIN_UNDIAGNOSED_ADMISSIONS = 2
MIN_CONTRIBUTORY = 2

# Planted documentation bias -- see the comment in the loop below.
UNDER_DOC_INTERPRETER = 0.35
FHX_ASKED_BASE = 0.68
FHX_ASKED_INTERPRETER = 0.44

BODY_SYSTEM = {
    "HP:0001263": "neurodevelopment", "HP:0001249": "neurodevelopment",
    "HP:0000750": "neurodevelopment", "HP:0002376": "neurodevelopment",
    "HP:0001252": "neurology", "HP:0001250": "neurology",
    "HP:0004322": "growth", "HP:0001518": "growth", "HP:0011968": "growth",
    "HP:0000252": "craniofacial", "HP:0000175": "craniofacial",
    "HP:0001999": "craniofacial",
    "HP:0001627": "cardiac",
    "HP:0000365": "sensory", "HP:0000505": "sensory",
    "HP:0002650": "skeletal",
}
INDICATOR_TERMS = list(BODY_SYSTEM)

SPECIALTIES = [
    "General Paediatrics", "General Pediatrics", "Neurology", "Neurology  ",
    "Cardiology", "Cardiology (Outpatient)", "Ophthalmology", "ENT",
    "Otolaryngology", "Developmental Paediatrics", "Developmental Pediatrics",
    "Respirology", "Gastroenterology", "Endocrinology", "Nephrology",
    "Orthopaedics", "Orthopedics", "Metabolics", "Immunology", "Dermatology",
]
LANGUAGES = ["English", "English", "English", "English", "Mandarin", "Cantonese",
             "Tamil", "Urdu", "Spanish", "Arabic", "Tagalog", "Portuguese",
             "Somali", "Farsi", "Gujarati"]


def conform(name):
    """Mirror the silver conformance so specialty counts match."""
    out = name.strip().title().replace("Pediatric", "Paediatric")
    out = out.split(" (")[0]
    if out == "Otolaryngology":
        out = "Ent"
    return out.replace("Orthopedic", "Orthopaedic")


RNG = random.Random(COHORT_SEED)
TODAY = date(2026, 8, 27)
WINDOW_START = TODAY - timedelta(days=30 * MONTHS_OF_HISTORY)

states = Counter()
fires = Counter()
by_group = {}
by_sensitivity = {}
latent_flagged = latent_total = 0
criteria_per_patient = Counter()

for index in range(COHORT_SIZE):
    birth = TODAY - timedelta(days=RNG.randint(200, 17 * 365))
    language = RNG.choice(LANGUAGES)
    interpreter = language != "English" and RNG.random() < 0.72
    latent = RNG.random() < 0.11
    enrolled = WINDOW_START + timedelta(days=RNG.randint(0, 30 * MONTHS_OF_HISTORY))

    span = max(1, (TODAY - enrolled).days)
    visit_count = RNG.randint(6, 22) if latent else RNG.randint(1, 11)
    specialties, dates, admitted_undiag, diagnosed = set(), [], 0, 0
    for _ in range(visit_count):
        when = enrolled + timedelta(days=RNG.randint(0, span))
        raw = RNG.choice(SPECIALTIES)
        specialties.add(conform(raw))
        dates.append(when)
        adm = RNG.random() < (0.22 if latent else 0.07)
        diag = RNG.random() > (0.55 if latent else 0.2)
        diagnosed += 1 if diag else 0
        if adm and not diag:
            admitted_undiag += 1

    feature_count = (RNG.randint(2, 6) if latent
                     else RNG.choices([0, 1, 2], weights=[62, 26, 12])[0])
    terms = RNG.sample(INDICATOR_TERMS, min(feature_count, len(INDICATOR_TERMS)))

    # Under-documentation, not under-prevalence. Children whose families need an
    # interpreter have the same underlying rate of clustered presentation -- `latent`
    # is drawn before language is consulted -- but their features reach the record
    # less often. Consultations run shorter, history-taking is harder, and free-text
    # description is less likely to be coded. This is the bias the equity check exists
    # to catch, and it is planted here deliberately so that the check has something
    # real to find.
    terms = [t for t in terms
             if not (interpreter and RNG.random() < UNDER_DOC_INTERPRETER)]
    for _ in terms:
        RNG.randint(0, span)          # keep the RNG stream aligned with the notebook
    systems = {BODY_SYSTEM[t] for t in terms}

    asked = RNG.random() < (FHX_ASKED_INTERPRETER if interpreter else FHX_ASKED_BASE)
    if asked:
        affected = (RNG.random() < 0.35) if latent else (RNG.random() < 0.06)
        consang = (RNG.random() < 0.16) if latent else (RNG.random() < 0.03)
        loss = (RNG.random() < 0.18) if latent else (RNG.random() < 0.05)
        # The notebook also stamps asked_on. It costs a draw, and omitting it here
        # slides the two RNG streams apart for every patient with a history taken --
        # which is most of them, so the whole cohort diverges from that point on.
        RNG.randint(0, 200)
    else:
        affected = consang = loss = None

    record_days = (TODAY - enrolled).days
    screenable = record_days >= MIN_RECORD_DAYS

    months = ((max(dates) - min(dates)).days / 30.44) if dates else 0.0
    diagnosed_share = diagnosed / visit_count if visit_count else 0.0

    # Two tiers. A sufficient criterion surfaces the child on its own; a contributory
    # one only counts alongside another. Treating "developmental regression" and "one
    # affected relative" as equally decisive is what pushes the flag rate to a fifth of
    # the clinic and makes the list ignorable.
    sufficient, contributory = [], []
    if len(systems) >= MIN_SYSTEMS_MULTI:
        sufficient.append("MULTI_SYSTEM")
    if "HP:0002376" in terms:
        sufficient.append("REGRESSION")
    if "neurodevelopment" in systems and len(systems) >= 2:
        contributory.append("NEURODEV_PLUS")
    if (len(specialties) >= MIN_SPECIALTIES_ODYSSEY
            and months >= MIN_MONTHS_ODYSSEY
            and diagnosed_share < MAX_DIAGNOSED_SHARE_ODYSSEY):
        contributory.append("DIAGNOSTIC_ODYSSEY")
    if admitted_undiag >= MIN_UNDIAGNOSED_ADMISSIONS:
        contributory.append("REPEAT_UNDIAGNOSED_ADMISSION")
    if asked and (affected or consang or loss):
        contributory.append("FAMILY_HISTORY")

    surfaced = bool(sufficient) or len(contributory) >= MIN_CONTRIBUTORY
    hits = sufficient + contributory if surfaced else []

    if not screenable:
        state = "not_screened"
    elif surfaced:
        state = "indicators_present"
    else:
        state = "no_indicators_recorded"
    states[state] += 1

    if screenable:
        for hit in hits:
            fires[hit] += 1
        criteria_per_patient[len(hits)] += 1
        key = "interpreter" if interpreter else "no interpreter"
        seen, flagged = by_group.get(key, (0, 0))
        by_group[key] = (seen + 1, flagged + (1 if hits else 0))
        if latent:
            latent_total += 1
            latent_flagged += 1 if hits else 0
            seen, found = by_sensitivity.get(key, (0, 0))
            by_sensitivity[key] = (seen + 1, found + (1 if hits else 0))

total = sum(states.values())
print(f"cohort {total:,}\n")
for state, count in states.most_common():
    print(f"  {state:24} {count:>6,}  ({count / total:5.1%})")

print("\ncriterion fire counts (screened patients only)")
for name, count in fires.most_common():
    print(f"  {name:30} {count:>5,}")

print("\ncriteria fired per screened patient")
for n in sorted(criteria_per_patient):
    print(f"  {n} criteria   {criteria_per_patient[n]:>5,}")

print("\nflag rate by interpreter need")
for key, (seen, flagged) in sorted(by_group.items()):
    print(f"  {key:16} screened={seen:>5,}  flagged={flagged:>4,}  "
          f"rate={flagged / seen:.1%}")

if latent_total:
    print(f"\nsensitivity against the generator's own answer key: "
          f"{latent_flagged}/{latent_total} = {latent_flagged / latent_total:.1%}")

print("\nsensitivity by interpreter need -- the number that matters")
for key, (seen, found) in sorted(by_sensitivity.items()):
    print(f"  {key:16} affected={seen:>4,}  surfaced={found:>4,}  "
          f"sensitivity={found / seen:.1%}")
