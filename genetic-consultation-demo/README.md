# Genetic Consultation Agent — Fabric demo

A working demonstration of a grounded consultation-drafting agent on Microsoft Fabric.
Public ClinVar reference data, synthetic cases, and an agent that can only say what the
pipeline gave it.

> **No patient data.** Every case in this repository is fabricated. The variants they
> reference are real public ClinVar records, which is reference data, not patient data.
> Nothing here is a clinical tool or suitable for use in patient care.

## The design commitment

The language model never determines anything. Classification comes from ClinVar's
submitted assertions, read at a stated release. The model's only job is to render that
into prose for a clinical genetics team, carrying a citation for every claim.

The trade is deliberate: it gives up the fluency of a model reasoning over raw genomic
data, and buys back reproducibility, inspectable reasoning, and the property that a wrong
answer is a bug in code you can fix rather than a behaviour you can only re-prompt.

```text
public ClinVar API  →  bronze  →  silver  →  gold  →  evidence contract  →  agent  →  draft
                       verbatim   typed +    cases +   bounded JSON,        cites,     3 gates
                                  gated      coverage  every value has ID   computes
                                                                            nothing
```

## The three states that must never collapse

This is the whole point of the demo, and the reason a generic RAG pipeline is not
adequate here.

| State | Meaning | What it is **not** |
| --- | --- | --- |
| `classified` | A submitted assertion exists in the release read | — |
| `no_reference_entry` | The variant is real, but nobody has submitted an assertion | **Not benign** |
| `gene_not_covered` | The gene was not on the panel, or could not be read | **Not a negative result** |

Only a variant classified benign is a negative finding. The other two are absences of
information. They are kept structurally distinct from Gold onward, and a validator fails
the build if the agent's prose blurs them.

`SYNTH-004` exists to exercise the third state: the referral indication implicates *TSC1*,
*TSC1* is not on the epilepsy panel, and the pipeline found nothing. A naive summariser
would write "no pathogenic variants were identified" — which is true, useless, and
dangerously reassuring. The agent is forced to write that *TSC1* was never examined.

## Three gates on the agent's output

Run by `scripts/foundry/create_consultation_agent.py`, which exits non-zero if any fails.

| Gate | Catches |
| --- | --- |
| **1. Citation resolution** | Evidence IDs the agent invented |
| **2. Schema validation** | A document that is not the shape the contract demands |
| **3. Clinical safety** | A valid, well-cited document that is still unsafe |

Gate 3 is the domain-specific one, and it exists because gates 1 and 2 both pass a
document that should never reach a clinician. It checks that:

* No definitive or advisory language appears anywhere — *ruled out*, *excluded*,
  *confirms*, *recommend*, *normal*.
* A **VUS or unclassified variant is never described in reassuring terms** — not *low
  risk*, not *unlikely to be relevant*, not *probably benign*.
* A **coverage gap is named explicitly** in the coverage statement, not buried.
* The agent **reported** each classification rather than rewording it — the value must
  match the evidence exactly.
* `reviewRequired` is true. An unreviewed draft must never present as reviewed.

### Why three, from experience

An earlier build of this architecture, in a non-clinical domain, produced a fully
schema-valid document citing evidence ID `E1` — which did not exist. It had no lawful
alternative: the contract required a citation per claim, and with no evidence supplied,
no valid document was expressible. **Schema validation passed it.** Only the citation
check caught it.

That is why the prompt here gives the agent an explicit way to return nothing, and why
there are three gates rather than one.

## Repository

```text
fabric/
  notebooks/
    bronze_clinvar_reference.ipynb   # public NCBI ClinVar API → Delta, verbatim
    silver_variant_reference.ipynb   # typed rows + populated-rate gate
    gold_case_assessment.ipynb       # synthetic cases, three-state assessment
    agent_handoff_publisher.ipynb    # validated evidence contract per case
  pipelines/
    pl_genetic_consultation.json     # four-activity orchestration
agent-architecture/
  prompts/consultation-agent-system.md      # the clinical guardrails
  contracts/consultation-output.schema.json # the output contract
scripts/
  fabric/provision_fabric_demo.py    # idempotent workspace provisioning
  fabric/run_pipeline.py             # start and poll
  foundry/create_consultation_agent.py  # draft + three gates
```

## Reference sources

All public, anonymous, and versioned. The release read is captured as data — ClinVar
revises assertions continuously, and a classification without a release is not verifiable.

| Source | Provides | Cited as |
| --- | --- | --- |
| ClinVar (NCBI E-utilities) | Variant–condition assertions, clinical significance, review status | VCV accession |
| HPO | Phenotype terms for the referral indication | `HP:` term |

Review status is carried through deliberately. An assertion from a single submitter with
no stated criteria is not equivalent to an expert-panel classification, and the agent is
instructed not to imply otherwise.

## The populated-rate gate

Silver asserts a minimum populated rate on every field the report may cite, and **fails
the run** if one is unexpectedly empty. This exists because a silently-null attribute is
indistinguishable from a real negative by the time it reaches prose — and in an earlier
build, one field read as authoritative for weeks while being null in every record of
every run.

## Running it

```bash
python scripts/fabric/provision_fabric_demo.py \
  --config cicd/fabric-setup.config.json --output cicd/fabric-setup.output.json

python scripts/fabric/run_pipeline.py --output cicd/fabric-setup.output.json

python scripts/foundry/create_consultation_agent.py \
  --foundry cicd/foundry-setup.output.json \
  --evidence cicd/case-evidence.SYNTH-004.json
```

The pipeline needs an active Fabric capacity. The agent step does not.

## Scope

This is an architecture demonstration. It is not a validated variant classifier, it does
not implement ACMG/AMP criteria evaluation, and it defers entirely to ClinVar's submitted
classifications. A production system would need a validated classification layer, clinical
governance, and a regulatory assessment appropriate to its intended use.
