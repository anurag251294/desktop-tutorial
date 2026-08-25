# Demo runbook — Genetic Consultation Agent

A 20-minute walkthrough. The story is one claim: **the pipeline decides, the model only
explains, and three independent gates reject the draft if it drifts.**

Audience is mixed — clinical genetics, informatics, and account team. Lead with the
clinical safety argument, not the architecture. The architecture is how the safety is
achieved, not the point.

## Environment

| | |
| --- | --- |
| Tenant | MngEnvMCAP510531 |
| Fabric workspace | `Genomics_Demo` on `fabdemo85829` (F64, Canada Central) |
| Foundry | `geohazard-foundry-mcap` / `geohazard-project`, model `gpt-5.4-mini` |
| Verified run | `ff857590-904f-42d8-9618-7a45bdea33fc` |

> **Cost.** The F64 bills at roughly **$11.52/hour** while Active. Resume before, suspend
> immediately after.
>
> ```bash
> CAP="/subscriptions/<sub>/resourceGroups/rg-fabric-demo/providers/Microsoft.Fabric/capacities/fabdemo85829"
> az resource invoke-action --action resume  --ids "$CAP"
> az resource invoke-action --action suspend --ids "$CAP"
> ```

## Before you start

1. **Resume 30 minutes ahead, not 5.** The capacity reports Active within a minute, but
   Fabric item editors stay unavailable for roughly 20–25 minutes after a resume while
   every backend check passes. There is nothing to fix and no way to hurry it.
2. **The agent half needs no capacity.** `cicd/case-evidence.SYNTH-004.json` and the
   `consultation-output.*.json` files are committed. If Fabric misbehaves, Acts 3 and 4
   still run.
3. **Say "synthetic" in the first minute.** Every case is fabricated. The variants they
   reference are real public ClinVar records, which is reference data, not patient data.
   Get that stated before anyone wonders.

---

## Act 1 — It all comes from public reference data (3 min)

**Open `bronze_clinvar_reference` and show the parameters cell.**

* No credentials, no uploads, no file transfer. The panel is eight childhood epilepsy
  genes and the source is the **public NCBI ClinVar API**.
* Bronze stores what the API returned, verbatim — 960 variant records for this run.
* **The release stamp is data, not metadata.** ClinVar revises assertions continuously. A
  classification without a release is not verifiable, so the run records exactly what it
  read and when.

> "If a variant is reclassified next month, we can tell you precisely which release this
> report was written against. That is not provenance trivia in genetics."

---

## Act 2 — The medallion makes it answerable, and the gate keeps it honest (5 min)

**Open `silver_variant_reference` and scroll to the populated-rate gate output.**

* Bronze is nested JSON that neither SQL nor an agent can interrogate. Silver flattens it
  to one typed row per variant: significance, review status, conditions, consequence.
* **Review status is carried, not flattened.** A single submitter with no stated criteria
  is not equivalent to an expert panel, and the agent is instructed never to imply it is.
* Then the part worth pausing on: **every field the report may cite is asserted here, and
  the notebook fails the run if one is unexpectedly empty.**

> "In a previous build of this architecture, one field read as authoritative for weeks
> while being null in every record of every run. Nothing failed — it just quietly
> degraded. A silently-null attribute is indistinguishable from a real negative by the
> time it reaches prose, so now it stops the pipeline instead."

---

## Act 3 — Three states that must never collapse (6 min)

**This is the act. Everything else supports it.**

Open `gold_case_assessment` and show the state table, then the four cases.

| State | Meaning | What it is **not** |
| --- | --- | --- |
| `classified` | A submitted assertion exists in the release read | — |
| `no_reference_entry` | The variant is real, nobody has submitted an assertion | **Not benign** |
| `gene_not_covered` | The gene was never examined | **Not a negative result** |

Only a variant classified benign is a negative finding. The other two are absences of
information, and they are kept structurally apart from Gold onward.

**Walk the four synthetic cases:**

| Case | Exercises | Result |
| --- | --- | --- |
| `SYNTH-001` | Normal path | Pathogenic `SCN2A` + a benign variant recorded, not reported |
| `SYNTH-002` | VUS | `PCDH19` uncertain — reportable, explicitly not actionable |
| `SYNTH-003` | No submission | Unclassified, `clinicalSignificance` **null** |
| `SYNTH-004` | Coverage gap | *TSC1* implicated by the referral, not on the panel |

> "SYNTH-004 is the one I would ask you to push on. The referral says tuberous sclerosis
> features. TSC1 is not on the epilepsy panel. The pipeline found nothing. A naive
> summariser writes *no pathogenic variants were identified* — which is true, useless, and
> the most dangerous sentence in the report."

---

## Act 4 — The agent, and the three gates (5 min)

**Show `agent-architecture/prompts/consultation-agent-system.md`.**

Point out that the prohibitions are longer than the instructions, deliberately. A drafting
agent in a clinical setting fails by *adding* — the dangerous output is the fluent,
confident sentence no evidence supports.

**Then show the drafts.** Read SYNTH-004's coverage statement aloud, verbatim:

> "The childhood_epilepsy_v1 panel was used for this case. **TSC1 was not examined because
> it is not on the panel, and no conclusion about TSC1 can be drawn from this result.**"

And SYNTH-003:

> "This variant is unclassified because assessmentState is no_reference_entry; no submitted
> assertion was found in the release that was read."

`clinicalSignificance` is **null** there — not coerced to benign, not softened.

**Then the gates.** Run it live if the room is technical:

```bash
python scripts/foundry/create_consultation_agent.py \
  --foundry cicd/foundry-setup.output.json \
  --evidence cicd/case-evidence.SYNTH-004.json
```

| Gate | Catches |
| --- | --- |
| 1. Citation resolution | Evidence IDs the agent invented |
| 2. Schema validation | A document that is not the contract's shape |
| 3. **Clinical safety** | A valid, well-cited document that is still unsafe |

Gate 3 rejects definitive or advisory language, a VUS or unclassified variant described in
reassuring terms, a coverage gap not named in the coverage statement, a classification the
agent *reworded* rather than reported, and `reviewRequired` set to anything but true.

> "Gate 3 exists because gates 1 and 2 both pass a document that should never reach a
> clinician. A draft can cite perfectly and validate perfectly while describing an
> uncertain result as reassuring."

**The credibility moment — tell them this happened:**

> On the first run, this agent produced a draft that passed the clinical gate and failed
> the schema gate: it had substituted its own, shorter disclaimer. Cause was mine — the
> required text sat in a section the system message did not include, so the model never
> saw the words it was told to copy.
>
> In an earlier non-clinical build, an agent given no evidence at all returned a fully
> schema-valid document citing evidence ID `E1`, which did not exist. **Schema validation
> passed it.** Only the citation check caught it. That is why there are three gates and
> why the prompt has an explicit way to return nothing.

---

## Questions to invite

These are the ones worth being asked, and the answers are all "yes, and here is where":

* *What happens if ClinVar reclassifies after we issue a report?* — the release is
  recorded per run; reclassification handling is an open design question, deliberately.
* *Who reviews this?* — `reviewRequired` is `true` by contract and cannot be set false.
* *Can it tell us a patient is affected?* — no; the prompt forbids diagnosis and the gate
  rejects the language.
* *What if the model hallucinates a citation?* — gate 1, demonstrated.

## Known gaps — say these before they are found

* **Not a variant classifier.** It defers entirely to ClinVar's submitted assertions and
  implements no ACMG/AMP criteria evaluation. A production system needs a validated
  classification layer.
* **No gnomAD frequency, no phenotype matching.** The HPO terms are carried but not scored
  against the finding.
* **Bronze takes about 10 minutes** because NCBI rate-limits anonymous callers. An NCBI API
  key raises the limit substantially.
* **Regulatory position is unresolved.** If this drafts ahead of a clinician it may be
  software-as-a-medical-device under Health Canada, and PHIPA governs the residency
  question. Both belong on the table before build, not after.

## Reset

```bash
python scripts/fabric/provision_fabric_demo.py \
  --config cicd/fabric-setup.config.json --output cicd/fabric-setup.output.json
python scripts/fabric/run_pipeline.py --output cicd/fabric-setup.output.json
```

Idempotent. Each run gets its own `run_id` and writes to its own partition, so previous
runs stay intact and comparable.
