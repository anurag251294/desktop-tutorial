# Genetic referral case-finding — Fabric demo

Finding children who should be **referred for genetic consultation**, from signals
already sitting in the clinical record — and being honest about who the screen misses.

> **No genomic data. No patient data.**
> Nothing here reads a genome, a variant, or a test result. The reference data is the
> Human Phenotype Ontology, which is a vocabulary of *observable clinical features* —
> developmental delay, hypotonia, short stature. Every patient is fabricated. This is a
> demonstration and is not a clinical tool.

## What problem this addresses

Children with undiagnosed rare conditions often spend years in a diagnostic odyssey:
many specialists, many investigations, no unifying answer, and no one referring to
genetics because no single clinician sees the whole pattern. The signals are usually
present in the chart long before anyone joins them up.

This pipeline joins them up. It reads the record, applies named criteria, and produces
a short list of children a clinician may want to look at — each with the specific
observations and encounters that put them on the list.

**It does not decide anything.** It surfaces records. A clinician decides.

### Where the intelligence actually sits

Worth being exact, because it is easy to overclaim. The children are identified by
**named, deterministic criteria** — not by a language model. That is a deliberate
choice: criteria can be inspected, argued with, reproduced next month, and measured for
bias. A model that decided who surfaced could do none of those things.

The agentic parts of the system are the ones where judgement is not being exercised over
a child:

| Component | What it does | Decides who surfaces? |
| --- | --- | --- |
| Criteria in Gold | Identifies the cohort | **Yes** — deterministic, inspectable |
| Referral brief agent | Renders one child's evidence into prose, with citations | No |
| Cohort agent | Answers a clinician's questions across the surfaced cohort | No |
| Vocabulary knowledge base | Explains what a term or criterion means | No |

So this is an agentic system in which the identification step is deliberately *not*
agentic. If someone asks "is the AI finding the patients", the honest answer is: the AI
makes the finding readable, queryable and safe; the finding itself is arithmetic you can
audit.

Of a 2,400-child cohort the live run surfaces **220 (9.2%)**, reports 1,766 (73.6%) with
no indicators recorded, and 414 (17.2%) as not screened at all.

```text
HPO public API   →  bronze  →  silver  →  gold  →  evidence contract  →  agent  →  brief
synthetic chart     verbatim   conformed  criteria   bounded JSON,        cites,   4 gates
                               + gated    + states   every claim has ID   computes
                                          + equity                        nothing
```

## The three states that must never collapse

| State | Meaning | What it is **not** |
| --- | --- | --- |
| `indicators_present` | Criteria fired on this record | **Not a diagnosis**, and not a referral |
| `no_indicators_recorded` | The record was read, nothing fired | **Not "no indication"** — the record may be silent, not the child |
| `not_screened` | Too little record to read | **Not a clear screen** |

The middle state is the one that gets misread, and the misreading is dangerous. A child
with a genetic condition whose features were never coded looks identical to a child
without one. The pipeline cannot tell them apart, so it does not claim to, and the agent
is forbidden from writing anything a tired reader could take as reassurance.

## Two tiers, not a score

Six criteria, each named, each carrying its own threshold:

| Criterion | Tier | Fires when |
| --- | --- | --- |
| `MULTI_SYSTEM` | sufficient | Features recorded across 3+ body systems |
| `REGRESSION` | sufficient | Developmental regression recorded (HP:0002376) |
| `NEURODEV_PLUS` | contributory | A neurodevelopmental feature plus one in another system |
| `DIAGNOSTIC_ODYSSEY` | contributory | 4+ specialties over 12+ months, diagnosis recorded at under half of encounters |
| `REPEAT_UNDIAGNOSED_ADMISSION` | contributory | 2+ admissions with no diagnosis recorded |
| `FAMILY_HISTORY` | contributory | Affected first-degree relative, consanguinity, or recurrent pregnancy loss |

A *sufficient* criterion surfaces the child alone. *Contributory* criteria surface a
child only in combination — two or more. Weighting them equally surfaces a fifth of the
clinic, and a list that long is a list nobody reads.

There is deliberately **no risk score**. A clinician reading *"surfaced because features
span four body systems"* can disagree with the threshold and say why. A clinician reading
*"risk 0.81"* can only defer or ignore.

**Every threshold is a placeholder pending sign-off by the genetics service.** They are
tuned to produce a demonstrable cohort, not to be clinically correct. They are gathered
in one cell and written out as `gold_criteria_definitions` so the clinical conversation
is about a table someone can mark up.

## The finding this demo is built around

The cohort is generated so that children whose families need an interpreter have **the
same underlying rate** of clustered presentation as everyone else. What differs is how
much of it reaches the record: consultations run shorter through an interpreter,
history-taking is harder, and description is less likely to land in a coded field.

Run `validation_sensitivity.ipynb` and the screen reports:

| Group | Affected | Surfaced | Sensitivity |
| --- | --- | --- | --- |
| No interpreter needed | 98 | 86 | **87.8%** |
| Interpreter needed | 109 | 82 | **75.2%** |

Same planted prevalence, a **12.6 point** gap in who gets found. Flag rate follows it:
12.1% against 10.2%.

These are figures from the live run of `2026-08-27`, not estimates. Re-running with a
different `COHORT_SEED` moves them by a point or two; the direction does not move.

Nothing in the criteria reads language or interpreter need; the gold notebook asserts
that and fails the build if it ever becomes untrue. Excluding the attribute does not
prevent the disparity, because the disparity arrives through the features themselves.
That is the point. **A flag can be blind to a protected attribute and still reproduce
the inequity attached to it**, and the only way to know is to measure the outcome.

Measuring it does not fix it. It makes it arguable — and it points at the actual
remedy, which is interpreter-supported history-taking, not a better model.

### The measurement that production cannot make

`validation_sensitivity.ipynb` reads `_latent_cluster` — ground truth for which
synthetic children were generated as affected. Real records carry no such column; if you
knew which children had an undiagnosed condition you would not need a screen.

That is what makes the synthetic cohort worth building. It measures the thing a live
deployment never can: **not how many flagged children turn out to be affected, but how
many affected children were never flagged.** No production dashboard will show you that
number, and it is the one that matters.

The answer key stays in Bronze. Silver drops it and asserts it is gone, so nothing in the
scoring path can read it.

> The absolute sensitivity figure is **not** evidence the criteria work — it is measured
> against a cohort this repository generated using a definition of "affected" this
> repository invented, which is close to circular. The **gap between groups** is not
> circular: both were planted identically.

## Four gates on the agent's output

Run by `scripts/foundry/create_referral_agent.py`, which exits non-zero if any fails.

1. **Schema** — the brief validates against `referral-brief.schema.json`, or it is not a
   brief. Checked with `jsonschema`, not by eye.
2. **Citation** — every entry in `reasons` cites at least one `evidence_id`, and every
   cited ID appears in the evidence actually supplied. Invented identifiers are the
   failure mode this exists to catch; it has caught them before.
3. **Clinical** — no diagnosis, no named condition or gene, no recommendation to refer
   or not refer, and no phrasing that reads as reassurance (`no concerns`,
   `screen negative`, `unremarkable`). `recommended_action` may only be
   `clinician_review`.
4. **Limitation** — every brief states that it reflects only what was recorded, and that
   undocumented features are invisible to the pipeline. A brief without that line is
   rejected even if everything in it is true.

When the evidence contract is empty the agent has a lawful escape:
`{"error": "no-evidence", "patient_id": "..."}`. Without it, a contract requiring at
least one citation leaves no valid document, and a model with no valid output available
will invent one — which is exactly how fabricated evidence IDs appeared during the
geohazard build.

## Layout

```
fabric/notebooks/
  bronze_clinical_record.ipynb    HPO fetch + synthetic cohort, generated untidy
  silver_conformed_record.ipynb   typing, specialty conformance, populated-rate gate
  gold_referral_signals.ipynb     criteria, three states, equity check, evidence
  validation_sensitivity.ipynb    sensitivity by group against the answer key
agent-architecture/
  prompts/referral-agent-system.md      the fenced block is the system message
  contracts/referral-brief.schema.json  what the agent may emit
scripts/
  fabric/     provisioning and pipeline runs
  foundry/    agent creation and the four gates
```

## What is deliberately untidy in the generated data

A demo built on tidy data teaches the wrong lesson.

* **Family history recorded for ~60%.** A blank is *nobody asked*, not *no history*.
  Silver keeps `history_taken` as its own column; Gold refuses to score on the absence.
* **Two date formats** — the encounter feed writes `dd/MM/yyyy`, the observation feed
  `MM/dd/yyyy`. Parsed per feed; anything that will not parse is quarantined rather than
  coerced into a plausible wrong date.
* **Free-text specialty names** with several spellings of the same service
  (`Pediatrics` / `Paediatrics`, `ENT` / `Otolaryngology`).
* **Children with too little record to screen**, who must report as `not_screened`.

## Relationship to `genetic-consultation-demo/`

That folder is a **different problem** and is superseded for this use case. It
interprets ClinVar variant classifications — genomic reference data, answering *"what
does this variant mean?"* This folder answers *"which children should someone look at?"*
and touches no genomic data at all. See `genetic-consultation-demo/SUPERSEDED.md`.
