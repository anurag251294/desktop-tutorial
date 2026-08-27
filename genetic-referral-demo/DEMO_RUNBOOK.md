# Runbook — genetic referral case-finding

For the recording. Roughly 15 minutes of material. If you run short, the equity
section is the part worth protecting and the graph section is the part to cut —
it is the most impressive and the least load-bearing.

## Say this first, before anything is on screen

> This is **not** a genomics project. No genome, no variant, no test result appears
> anywhere in this system. The question is the one that comes *before* genetics gets
> involved: which children in the hospital should someone be looking at, sooner than
> they currently are.

Say it in the first thirty seconds. This has already been misunderstood once, by
someone reading the same words from the outside, so treat it as the opening line rather
than a caveat you get to later.

The reference data is the Human Phenotype Ontology — a coded vocabulary for *observable*
clinical features. It is used by genetics services, which is not the same as being
genetic information.

## What you are showing

Children with undiagnosed rare conditions often spend years in a diagnostic odyssey:
many specialists, no unifying answer, no genetics referral, because no single clinician
sees the whole pattern. The signals are usually in the chart already.

The pipeline joins them up and produces a short list, each entry carrying the specific
observations and encounters that put it there. **It decides nothing.** A clinician
decides.

## Walkthrough

### 1. Bronze — the record as it really is (2 min)

Open `bronze_clinical_record`. Two things to point at:

* The **HPO fetch** is a live call to a public ontology API, and the release it read is
  stamped as data. A phenotype term's meaning is fixed by its ontology version.
* The cohort is generated **deliberately untidy** — two date formats, five spellings of
  three services, and family history recorded for only some children.

> "A demo built on tidy data teaches you nothing, because the hard part of this
> problem is that the record is not tidy."

### 2. Silver — the distinction that carries the whole thing (2 min)

Open `silver_conformed_record`, the family history cell.

> "Family history is recorded for about six in ten children. The obvious move is to
> fill the gap with `false` and get a clean boolean column. That would invent a
> negative finding for four in ten children."

`history_taken` is kept as its own column. **Asked and the answer was no** is not the
same as **nobody asked**.

Same reasoning gives the third state: a child whose record is too short to read is
`not_screened`, which is not a clear screen.

### 3. Gold — named criteria, two tiers, no score (3 min)

Open `gold_referral_signals`.

Show the `CRITERIA` cell. Six criteria, each named, each carrying its own threshold, all
in one place.

> "There is no risk score, and that's deliberate. A clinician reading 'surfaced because
> features span four body systems' can disagree with the threshold and tell you why. A
> clinician reading 'risk 0.81' can only defer to it or ignore it."

Two tiers: **sufficient** surfaces a child alone, **contributory** only in combination.
Weighting them equally surfaces a fifth of the clinic, and a list that long is a list
nobody reads.

Then the three states table. Land the middle one hard:

> "`no_indicators_recorded` does not mean the child has no indication. It means nothing
> was found *in the record*. A child whose features were never coded looks exactly like
> a child who doesn't have them. The pipeline can't tell them apart, so it doesn't
> pretend to."

**Every threshold is a placeholder pending sign-off by the genetics service.** Say that
out loud. They are written out as `gold_criteria_definitions` so the clinical
conversation is about a table someone can mark up, not a number buried in code.

### 4. The equity finding — the part that matters (3 min)

Run or show `validation_sensitivity`.

| Group | Affected | Surfaced | Sensitivity |
| --- | --- | --- | --- |
| No interpreter needed | 98 | 86 | **87.8%** |
| Interpreter needed | 109 | 82 | **75.2%** |

> "Both groups were generated with the same underlying rate. The only difference is how
> much of it reached the record — consultations run shorter through an interpreter,
> history-taking is harder, description is less likely to land in a coded field.
>
> The screen finds seven and a half in ten affected children in one group and nearly
> nine in ten in the other. Nothing in the criteria reads language or interpreter need —
> the notebook asserts that and fails the build if it stops being true.
>
> **A flag can be blind to a protected attribute and still reproduce the inequity
> attached to it.** Excluding the column proves nothing. Measuring the outcome is the
> only thing that shows it."

Then the honest close on this section:

> "Measuring it doesn't fix it. What it does is point at the actual remedy, which is
> interpreter-supported history-taking — not a better model."

**If someone asks how you know the sensitivity:** because the cohort is synthetic and
carries an answer key. Say plainly that a real deployment cannot compute this, which is
precisely the argument for building the synthetic cohort — it measures the thing
production never shows you: not how many flagged children turn out to be affected, but
how many affected children were never flagged.

Be equally plain that the **absolute** figure is close to circular — it is measured
against a pattern this repository planted. The **gap between groups** is not, because
both groups were planted identically.

### 5. The graph — the criterion, walked instead of asserted (3 min)

Open `referral_graph`. Six node types, five edge types, over the gold tables.

Run the traversal for `SYN-00017`:

```gql
MATCH (p:Patient)-[:hasFeature]->(f:Feature)-[:inBodySystem]->(b:BodySystem)
WHERE p.patientId = 'SYN-00017'
RETURN f.hpoLabel AS feature, b.bodySystem AS system
ORDER BY system, feature
```

> "The criterion says features span three or more body systems. Here are the systems,
> and here are the features underneath each one. Nobody has to take the number on
> trust — you can walk it."

Then the question that is genuinely awkward in SQL and one pattern here:

```gql
MATCH (p:Patient)-[:attendedEncounter]->(:Encounter)
      -[:encounterWithSpecialty]->(s:Specialty)
WHERE p.referralState = 'no_indicators_recorded'
RETURN s.specialty AS specialty, COUNT(DISTINCT p) AS children
GROUP BY s.specialty ORDER BY children DESC LIMIT 10
```

> "These are the children the screen did *not* surface, and where they actually turn
> up. If the screen is missing people, this is the clinic they are sitting in."

**Say what this is, and what it is not.** It is a Fabric graph — a labeled property
graph over OneLake, queried with standard GQL, documented under Fabric IQ. It is **not**
a Fabric IQ ontology: that feature returns `FeatureNotAvailable` in this tenant and
region, so nothing here should be described as one.

If asked about the agent and the graph together: Fabric Data Agent supports graph as a
data source with natural-language-to-GQL, in preview. Not wired up here.

### 5. The agent — it renders, it does not reason (2 min)

Open a contract from `Files/contracts/`, or the two committed samples:
`SYN-00017` (family history taken, four criteria) and `SYN-00195` (family
history **never taken** — the case that matters). Point out that it is a fixed envelope, not a
query: the agent cannot reach a patient it was not handed, and every value it can state
already carries an `evidence_id`.

Show a brief, then the four gates.

> "Schema, citations, clinical safety, and — separately — whether the brief states its
> own limitations. That last one is its own gate because gate three catches a bad
> sentence being *present*, and gate four catches a necessary sentence being *absent*.
> Absence is much harder to notice by reading."

If you have time, run `scripts/foundry/test_gates.py` live. Thirteen cases, each built
to break exactly one rule. It needs no Azure, no capacity, and takes about a second.

For `SYN-00195` the agent writes *"Family history was not recorded, so nothing is
known about it."* Read that line out. A summariser with no clinical gate writes
"no significant family history", which is a different claim about a real child.

## Questions you should expect

**"Would this actually work on our data?"**
Unknown, and say so. The criteria are placeholders. What transfers is the shape: named
inspectable criteria, three states kept distinct, evidence contracts, gates, and an
equity measurement as an output rather than a review afterwards.

**"What's the false positive rate?"**
On synthetic data that number is an artefact of the generator. The more useful question
is the one the validation notebook answers: who gets missed, and is it the same people
who already get missed.

**"Why not just let the model read the chart?"**
Then the model decides who surfaces, and you cannot inspect the criteria, reproduce the
run next month, or measure the flag for bias — because there is no flag, only an
opinion. Here the pipeline computes and the agent only renders.

**"Is any of this genomic?"**
No. Nothing reads a genome, a variant, or a test result. HPO is a vocabulary of
observable clinical features.

## What is not built

Say these before someone finds them.

* **Clinical criteria are unvalidated placeholders.** Nothing has been reviewed by a
  clinician.
* **No real data has ever touched this**, and no integration to a real EHR exists.
* **The agent has been tested against the gates, not against clinical judgement.**
* **`not_screened` is 17% of the cohort** — a real deployment would need to decide what
  happens to those children, and that is a service design question, not a data one.
