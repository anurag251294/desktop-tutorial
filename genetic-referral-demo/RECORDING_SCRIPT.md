# Screen recording script — genetic referral case-finding

Generated from the teleprompter by `scripts/make_recording_script.py`,
so the two cannot drift. Re-run it after any edit to `docs-teleprompter.html`.

Live: https://claude.ai/code/artifact/6b5e7ad0-e8cd-4567-bae7-fd178dae5846

*Screen recording script · outcome first · about 16 minutes of narration*

The recording leads with the outcome, demonstrates the Fabric IQ experience,
and only then explains the machinery underneath. Sections marked **ref** are
not spoken; they exist so you can answer "how does that actually work?"
precisely rather than approximately.

> Quoted text is what you say. *Italic* is what you do.

## Before you hit record

- Capacity `fabdemo85829` **Active 20+ minutes** — item editors lag a resume.
- **Tab order is outcome-first now:** **cohort agent** (0:00) · ontology (1:50) · **referral_queries** (3:10 — the queryset, this is where GQL runs) · graph model · latency (5:20) · gold lakehouse (6:20 validation, then 7:45 Files/contracts) · workspace (9:45) · bronze · silver · gold criteria · cohort agent (13:15) · Foundry (15:00). Run `tabs_ont.py` and it lands in this order.
- Foundry tab on `referral-foundry-mcap` → project `genetic-referral`.
- Terminal in the repo, `az login` done.
- **Click every tab once** before recording — Fabric lazy-renders background tabs.
- **Bind the queryset first, once.** Open `referral_queries` → *Use an existing model* → `referral_graph`. Do this before you record; the first time it asks, and after that it remembers. You run GQL in the **queryset**, not in the graph model — the model is only the schema.
- **Visible but not walked:** `gold_graph_dimensions` (builds the graph's dimension tables), `agent_handoff_publisher` (writes the evidence contracts), `gold_cohort_summary` (the cohort agent's serving table). Know what they are in case someone asks.
- Gold holds 16 tables, three of which are copies of silver — that is the graph's single-lakehouse requirement, and there is a line for it in the workspace section.
- **You open on the cohort agent, not the workspace.** Say the three numbers first, then ask the agent for the state breakdown and let it corroborate. The narration never depends on its answer — if it stalls, carry on.
- **Warm the agent before you record.** Ask it `How many patients are in each referral state?` once and discard the answer. First call after a capacity resume is slow, and the model intermittently returns `invalid_prompt` — you want that to happen in rehearsal, not in the take.

## What is what — nothing here lives inside a lakehouse

- Everything you open in this script is in the **workspace list**, not inside a lakehouse. `bronze_clinical_record` is a **notebook** that sits beside `bronze_lakehouse`, not in it.
- **NOTEBOOK** — `bronze_clinical_record` · `silver_conformed_record` · `gold_referral_signals` · `gold_signal_latency` · `validation_sensitivity`
- **ONTOLOGY** — `referral_ontology` — the semantic layer. Six entity types, five relationship types, bound to gold. **Open this before the graph.**
- **GRAPH MODEL** — `referral_graph` — the schema. You do *not* run queries here.
- **GRAPH QUERYSET** — `referral_queries` — where GQL is written and run. Bind it to the model once.
- **DATA AGENT** — `referral_cohort_agent`
- **LAKEHOUSE** — `bronze_lakehouse` · `silver_lakehouse` · `gold_lakehouse`
- **TABLES** — live *inside* the lakehouses — `bronze_patients`, `gold_referral_state`, and so on
- **CONTRACTS** — `gold_lakehouse` → Files → `contracts/`

## Verify — seconds each


```
python scripts/fabric/query_graph.py     # 7/7
python scripts/foundry/test_gates.py     # 13/13
```

## Numbers you will say

- **Cohort** — 2,400 children · **220 surfaced (9.2%)** · 1,766 no indicators · 414 not screened
- **Latency** — median **8.7 months** · **38%** over a year · longest 32.9
- **The one patient** — `SYN-00017` qualified **2024-03-06** — **29.7 months** ago
- **Sensitivity** — **87.8%** no interpreter vs **75.2%** interpreter needed
- **Ontology** — 6 entity types · 5 relationship types · 19 bound properties
- **Graph** — 18,731 nodes · 35,216 edges
- **Knowledge base** — 31 documents

## 0:00 · What it produces

*Open on the **cohort agent** tab, chat pane empty. Nothing else on screen for the first minute.*

> This is a case-finding pipeline in Microsoft Fabric, built for **SickKids**.

> The ask was one line: **use agentic intelligence to identify patients early for genetic consultation or testing.**

> Children with undiagnosed rare conditions get referred late because their findings are spread across different clinics and different visits. No single clinician sees all of them. The data is in the chart already; it is just not in one place.

`— beat · say the numbers, then ask for them —`

> Two thousand four hundred patients in. **Two hundred and twenty** flagged for genetics review — nine point two per cent. One thousand seven hundred and sixty-six where the record was read and nothing fired. Four hundred and fourteen with too little record to read at all.

*Now type it and send. Keep talking while it runs — about fifteen seconds.*


```
How many patients are in each referral state?
```

`— TYPE NOW: “How many patients are in each referral state?” · send · keep talking —`

> That is the cohort agent answering off the gold tables, not me reading a slide. And notice it returns the caveat with each figure — the middle state does not mean the patient is clear, it means nothing was found in the record.

> Two more numbers I will come back to. The findings that triggered each flag had been sitting in the record for a median of **eight point seven months**, thirty-eight per cent of them over a year. And the screen catches **eighty-seven point eight per cent** of affected patients where no interpreter is needed, **seventy-five point two** where one is.

`— beat —`

> Two things to be clear about up front. **This is not genomics.** No genome, no variant, no test result — nothing here reads genetic data. It runs on phenotype codes and encounter records.

> And the data is synthetic. Two thousand four hundred generated patients. **No SickKids data**, and no connection to any SickKids system.

> That agent is one of three, and it is the least constrained of them — I will come back to why that matters. First, where the definitions it just used are declared.

**Note.** **If the agent stalls or returns `invalid_prompt`.** Keep going — you have already said the numbers, so nothing in the narration depends on it. Say "that one is intermittent, I will come back to it" and pick up at the ontology. Do not re-send mid-take; the retry lands in the middle of the next section.


## 2:05 · The ontology

*Open `referral_ontology`. Let the canvas render — six entity types and the relationships between them.*

> This is the ontology. It is where the entity types and the relationships between them are defined.

> **Fabric IQ** is Microsoft's name for this layer — ontologies, semantic models, graphs and data agents. This is the ontology part of it.

`— walk the canvas —`

> Six entity types. **Patient**. **Feature**, which is an observed clinical finding. **BodySystem**. **Criterion**. **Encounter**. **Specialty**.

> Five relationship types. Patient `hasFeature`. Feature `inBodySystem`. Patient `surfacedBy` Criterion. Patient `attendedEncounter`. Encounter `encounterWithSpecialty` Specialty.

`— the part that matters —`

> Every entity type is bound to a table in the gold lakehouse. Nineteen properties, each mapped to a column. Nothing is copied — it reads the Delta tables directly.

> The point of doing it here is that the definitions live in one place. The graph query, the data agent and the notebook all resolve Patient and Feature to the same tables and the same columns.

`— name it —`

> And because the bindings are live, you can query it for a specific patient.

**Note.** **Be accurate about what is new here.** The ontology and the graph declare the *same* six entities and five relationships against the *same* gold tables. That is deliberate — one model, expressed once. Do not claim the ontology found anything the criteria did not; it does not compute the criteria. What it changes is that the meaning now lives in one declared place instead of being implied by a notebook.

**Note.** **Preview.** Ontology is in preview and we enabled it in this tenant for this build. If someone asks how long it took: flip the tenant setting, then about ten minutes before the service honoured it. Worth saying plainly rather than pretending it was instant.


## 3:25 · The graph — checking a flag

*Switch to `referral_queries` — the **graph queryset**, which is the thing you run queries in. The graph model itself is just the schema. Paste the query and press **Run**.*


```
MATCH (p:Patient)-[:hasFeature]->(f:Feature)-[:inBodySystem]->(b:BodySystem)
WHERE p.patientId = 'SYN-00017'
RETURN f.hpoLabel AS feature, b.bodySystem AS system
ORDER BY system, feature
```

> This is the graph model over those same six entity types. Eighteen thousand seven hundred nodes, thirty-five thousand relationships, built from the same gold tables.

`— if someone asks why both —`

> The ontology defines the model. The graph makes it traversable — you write GQL against it instead of joining six tables by hand.

> Patient `SYN-00017` was flagged for findings spanning multiple body systems. This query walks patient, to features, to body systems. So you can check the flag rather than trust it.

*Results: cardiac · neurodevelopment ×2 · neurology · skeletal.*

> Five features across four systems. Abnormal heart morphology, cardiac. Developmental regression and global developmental delay, neurodevelopment. Hypotonia, neurology. Scoliosis, skeletal. That is the criterion, expanded into the rows it was computed from.

*Second query.*


```
MATCH (p:Patient)-[:attendedEncounter]->(:Encounter)
      -[:encounterWithSpecialty]->(s:Specialty)
WHERE p.referralState = 'no_indicators_recorded'
RETURN s.specialty AS specialty, COUNT(DISTINCT p) AS children
GROUP BY specialty ORDER BY children DESC
```

> Second query, different question. Not who got flagged — who did not, and which clinics they are sitting in.

*Results: General Paediatrics 801 · Cardiology 794 · ENT 785 · Developmental Paediatrics 776 · Neurology 769 · Orthopaedics 754.*

> Eight hundred and one patients with `no_indicators_recorded` are in General Paediatrics. Seven hundred and ninety-four in Cardiology, seven hundred and eighty-five in ENT. Most of those are fine. But the screen does miss patients, and this is where the missed ones are.

`— beat —`

> You could write both of these in SQL. The graph is easier because the questions are about relationships — patient to feature to body system is three joins in SQL and one MATCH here.

*If asked how the graph was built — and someone will:*

`— beat —`

**Note.** **Get this exactly right.** Ontology and graph are both **Fabric IQ** components — Microsoft defines Fabric IQ as ontologies, semantic models, graphs and data agents. Both are real here and both are on screen. What you must **not** say is that the ontology found the children — the named criteria in gold do that, deterministically, and that separation is the point of the whole demo.


## 5:35 · Latency — how long the data sat there

*Open the **notebook** `gold_signal_latency`, or just show the figures.*

*Second word: **early**.*

> Same patient. Next question: when did that criterion first become true?

> Sixth of March, twenty twenty-four. Twenty-nine point seven months ago. Every feature the criterion needed was already coded by that date.

`— beat · let it sit —`

> Across all two hundred and twenty, the median is eight point seven months. Thirty-eight per cent are over a year. The longest is thirty-two point nine months.

> This is not anyone making a mistake. The features were recorded by different clinicians, in different clinics, months apart. Nothing joined them up.

> That is all the pipeline does here. It joins them up, and it computes the date the pattern completed.

> So **early** is a measured number in this build, not a claim.

**Note.** **Be precise about the claim.** The synthetic record contains no referral events, so this says the evidence has been **sufficient** since that date. It does **not** say a referral was missed or late. On real data, comparing the qualifying date against the actual referral date is the number you would want — and the obvious next thing to build.


## 6:35 · Sensitivity, split by interpreter need

*Show the **table** `gold_validation_sensitivity` (inside `gold_lakehouse`), or run the interpreter query on the graph.*

> This is the number I opened with, and where it comes from.

> The generator plants the same underlying rate of clustered presentation in both groups. Patients whose families need an interpreter get the same simulated biology as everyone else. What differs is how much of it gets recorded.

*Point at the feature counts: 939 across 486 children, versus 766 across 467.*

> One point nine three features recorded per patient where no interpreter is needed. One point six four where one is. Shorter consultations, harder history-taking, less of it lands in a coded field.

*Switch to the sensitivity figures.*

> So the screen catches **eighty-seven point eight per cent** in one group and **seventy-five point two** in the other. Twelve point six points of difference, off identical planted prevalence.

> The criteria never read language or interpreter status. There is an assert in the notebook that fails the build if that stops being true.

> Which is the point: excluding the column does not make the output even. The only way to see this is to measure the outcome by group, which is what this table does.

`— beat —`

> And it tells you what to fix — interpreter-supported history-taking, not the model.

**Note.** **If you also show latency by interpreter need, read it carefully.** It appears to say interpreter-needing children are found *sooner* — eight months against ten. That is **survivorship, not good news**: the screen only surfaces children whose evidence crossed the threshold, and fewer of their features reach the record, so the ones that do surface are the more florid cases. The subtler ones are not in that table because the screen never found them. They are in this sensitivity gap instead.

**Note.** **If asked how you know the sensitivity:** the cohort is synthetic and carries an answer key. A real deployment cannot compute this — which is precisely the argument for the synthetic cohort. It measures what production never shows you: not how many flagged children turn out to be affected, but how many affected children were never flagged. Be equally plain that the **absolute** figure is close to circular; the **gap between groups** is not, because both were planted identically.


## 8:00 · The brief, and the four checks

*Terminal. Run it, then open the brief on screen — this section is about the *document*, not the pipeline.*


```
python scripts/foundry/create_referral_agent.py \
    --evidence cicd/patient-evidence.SYN-00195.json \
    --output cicd/referral-brief.SYN-00195.json
```

*While it drafts — about thirty seconds:*

> This is the output a clinician gets. One patient, one page. It is written by an agent that receives a JSON file of evidence and has no query access at all.

> Four checks run on what comes back. **Schema** — does it match the expected JSON shape. **Citations** — does every claim reference an evidence ID that was actually supplied. **Clinical safety** — no diagnosis, no named condition, no recommendation to refer, and no wording that turns *not recorded* into *not present*.

> Fourth check: does the brief state its own limitations. That is separate from the third because the third looks for a bad sentence being there, and the fourth looks for a required sentence being missing. Missing is harder to catch.

*Gates print. Open the brief; read the family history line aloud.*

> This is a patient where family history was never taken. The agent writes: *family history was not recorded, so nothing is known about it.*

> Not *no significant family history*. That would be a claim about the patient, and it would be false.

**Note.** **If it fails** with `invalid_prompt: Unsupported parameter 'top_p'` — that is a service-side intermittent, not your fault and not a configuration error. Re-run the same command; it works on the retry.


## 9:40 · How it works

*Back to the workspace list.*

> That is the output. Now the code that produces it.

> Three parts worth looking at: how the record gets conformed, how the criteria are written, and what each agent can reach.


## 10:00 · The workspace

*Click into the workspace list.*

> One workspace. Three lakehouses — bronze, silver, gold. A pipeline with five notebook activities, about nine minutes end to end. Plus the ontology, the graph and three agents.

> Bronze pulls the vocabulary and generates the record. Silver conforms it. Gold applies the criteria, computes latency, and runs the sensitivity check.

*Scroll the workspace list slowly while you say this.*

> All Delta tables in OneLake. No copies out, nothing leaves the workspace.

*If anyone notices gold holds copies of some silver tables — `gold_encounters`, `gold_observations`, `gold_hpo_terms` — have this ready:*


## 10:30 · Bronze — the raw record

*Open the **notebook** `bronze_clinical_record` from the workspace list. Header, then the cohort cell.*

> Bronze pulls the Human Phenotype Ontology from its public API. It is a coded vocabulary of observable clinical findings — developmental delay, hypotonia, short stature. Genetics services use it; it is not genetic data.

> Then it generates the record with realistic mess in it. Two date formats, because the encounter feed and the observation feed are simulated as different-era systems. Five spellings across three service names. Family history present for about sixty per cent of patients.

*Point at the comments in the cohort cell.*

> That is deliberate. If the input is clean, the pipeline never exercises the parts that matter.


## 11:15 · Silver — null is not false

*Open the **notebook** `silver_conformed_record`. The family history cell.*

> This is the cell that matters most.

> Family history is missing for forty per cent of patients. The easy fix is `fillna(False)` and you get a clean boolean column.

> That is wrong. *Asked, answer was no* and *nobody asked* are different facts. `fillna(False)` turns the second into the first for forty per cent of the cohort, and every downstream count is off.

*Point at `history_taken`.*

> So `history_taken` is its own boolean, and the finding flags stay null where nobody asked. The criteria in gold skip nulls rather than counting them as negative.

> Same logic gives the third state. If a patient's record is too sparse to evaluate, they come out `not_screened`, not clear.

> This is also where that twelve-point gap comes from. The criteria read recorded findings. Fewer findings recorded means fewer patients flagged.


## 12:15 · Gold — the criteria

*Open the **notebook** `gold_referral_signals`. The `CRITERIA` cell.*

*First of the three words: **identify**.*

> Six criteria. Each named, each with its own threshold, all in one `CRITERIA` dict at the top of the notebook.

> No risk score, on purpose. *Flagged because findings span four body systems* is something a clinician can check and push back on. *Risk zero point eight one* is not.

*Point at the tiers.*

> Two tiers. **Sufficient** criteria flag a patient on their own. **Contributory** ones only count in combination. Weight them the same and you flag about a fifth of the cohort, which is not usable.

*Scroll to the three-states table.*

> Three output states in `gold_referral_state`: `indicators_present`, `no_indicators_recorded`, `not_screened`.

> The middle one is the one people misread. It means nothing was found in the record, not that the patient has no indication. An uncoded patient and an unaffected patient look identical here, and the pipeline does not guess between them.

`— beat —`

> Every threshold in that dict is a placeholder. They need sign-off from the SickKids genetics service. They are in a table so that is a concrete review rather than a conversation about the code.


## 13:30 · Three agents, and what each can reach

*Third word: **agentic**. This is the one that does not mean what you might assume.*

> Patients are flagged by the criteria in gold, not by a model. That is deliberate: you can read the criteria, version them, re-run them next month and measure them for bias. You cannot do any of that with a model that decides who surfaces.

> So the agents are not doing the finding. They do everything around it, and what matters about each one is what it can reach.

*Open the envelope that brief was written from: `gold_lakehouse` → Files → `contracts/` → `patient-evidence.SYN-00195.json`.*

> First agent wrote that brief. No tools, no query access. It gets this JSON file and nothing else: the patient's state, which criteria fired, and the evidence items.

> So its scope is whatever is in the file. It cannot reach a patient it was not given, whatever you prompt it with.

`— second agent —`

> Second agent answers vocabulary questions from a Foundry IQ knowledge base — thirty-one documents, no patient data indexed. Ask it which patients were flagged and it returns design docs, because there is nothing else in there to return.

> Third is the agent I opened with — a Fabric data agent over the gold lakehouse. This is the one to look at hardest, because it can reach every patient row. Its limits are prompt instructions, and instructions are weaker than not having access.

`— third agent —`

> So it is pointed at `gold_cohort_summary` — precomputed aggregates with the caveats stored as columns. Where you can enforce scope structurally, do that. Where you cannot, be explicit that you have not.


## 15:15 · Fabric and Foundry — which does what

*No screen needed. Say this over the workspace, or over the brief you just produced.*

> Quick note on which platform does what, because it comes up.

`— what Fabric did —`

> Fabric does the data and the selection. One copy in OneLake, the criteria, the ontology and graph over the same tables, plus lineage and permissions.

`— where it stops —`

> Three things it does not do. There is no way to scope a model to a single payload. There is no output contract — no schema validation, no check that refuses a document because a required sentence is missing. And there is nowhere to hold reference documents separately from patient data.

> Those are not gaps in Fabric. They are a different job: constraining and validating what gets generated about a patient.

> So Fabric selects the patients. Foundry constrains and checks what gets written about them.

`— what Foundry did —`

> On naming: **Fabric IQ** is the ontology, the graph and the data agent. **Foundry IQ** is the knowledge base. Separate products — Foundry IQ does not take Fabric IQ as a source.

`— name both layers, accurately —`

**Note.** **Two things to keep straight.** The ontology, the graph and the data agent are all **Fabric IQ** components, and all three are live and populated here — six entity types, five relationship types, nineteen bound properties. And Foundry IQ does **not** take Fabric IQ as a knowledge source; its sources are Blob, SharePoint, OneLake and the web. The two are used together, not plugged into one another.


## 16:20 · Close

> Recap. Criteria you can read in a table. Three states kept separate. Evidence you can walk in the graph. Latency computed per patient. And a sensitivity check split by interpreter need.

> The thresholds are not clinically validated. They are placeholders for the SickKids genetics service to review. And the data is synthetic — no SickKids data was used.

> Back to the original ask. **Identify**: six named criteria. **Early**: a median of eight point seven months, measured. **Agentic**: three agents around the pipeline, and the one that writes about a patient has no query access and four output checks.

`— beat · close on the sentence you opened with —`

> And the part that was not asked for: a measurement of who the screen misses, and whether it misses the same people the system already misses.


## ref · The pipeline, if anyone digs

*Not spoken. `pl_genetic_referral`, five notebook activities, about nine minutes end to end.*


```
bronze_clinical_record   HPO fetch + synthetic cohort      -> 6 bronze tables
silver_conformed_record  typing, conformance, gates        -> 6 silver tables
gold_referral_signals    criteria, 3 states, equity check  -> gold
gold_signal_latency      temporal replay                   -> gold_signal_latency
agent_handoff_publisher  bounded evidence contracts        -> Files/contracts/
```

***Bronze** calls the public HPO API for 16 phenotype terms and stamps the release date as data — a term's meaning is fixed by its ontology version. It generates 2,400 children, 16,288 encounters and 1,705 observations, deliberately untidy: two date formats, five spellings of three services, family history for about 60%.*

***Silver** parses each feed with the format it actually writes — `dd/MM/yyyy` for encounters, `MM/dd/yyyy` for observations — and quarantines anything that will not parse rather than coercing it into a plausible wrong date. It conforms the specialty spellings, attaches HPO labels and body systems, and keeps `history_taken` as its own column. A populated-rate gate at 97% runs on every column the evidence contract will later cite, and fails the build below that.*

***Gold** applies the criteria, assigns the three states, asserts that language and interpreter need never reached the scoring inputs, and builds the contracts. The generator's answer key is dropped in silver with an assert, so nothing in the scoring path can read it.*


## ref · How the criteria are computed

*Not spoken. Plain Spark predicates in one cell of `gold_referral_signals`. No model anywhere near the identification.*


```
MULTI_SYSTEM        sufficient    systems_involved >= 3
REGRESSION          sufficient    HP:0002376 observed
NEURODEV_PLUS       contributory  neurodev feature AND systems >= 2
DIAGNOSTIC_ODYSSEY  contributory  4+ specialties AND 12+ months
                                  AND diagnosis recorded at < 50% of encounters
REPEAT_UNDIAGNOSED  contributory  2+ admissions with no diagnosis recorded
FAMILY_HISTORY      contributory  affected relative / consanguinity /
                                  recurrent loss, only where history was taken

surfaced = any sufficient  OR  two or more contributory
```

*Thresholds live in one parameter cell and are written out as `gold_criteria_definitions`, so the clinical conversation is about a table someone can mark up rather than a number buried in code. All are **placeholders**; none has been reviewed by a clinician.*

***Fire counts:** FAMILY_HISTORY 230 · NEURODEV_PLUS 204 · MULTI_SYSTEM 134 · REPEAT_UNDIAGNOSED 131 · REGRESSION 114 · DIAGNOSTIC_ODYSSEY 106. Weighting them flat surfaced 21% of the cohort; tiering brings it to 9.2%.*


## ref · How latency is computed

*Not spoken. `gold_signal_latency` replays each record forward in date order with running windows, and finds the first moment the tier rule was already satisfied.*


```
running distinct body systems   -> when did it reach 3?      MULTI_SYSTEM
first HP:0002376 observation    -> that date                 REGRESSION
running specialties, months,
  and diagnosed share           -> when did all three hold?  DIAGNOSTIC_ODYSSEY
cumulative undiagnosed admits   -> the second one            REPEAT_UNDIAGNOSED

qualifying_date = earliest( first sufficient , second contributory )
latency         = cutoff - qualifying_date
```

***Results:** median 8.7 months · mean 10.7 · p90 21.0 · longest 32.9. 83 of 220 — 38% — over a year. Qualified by a sufficient criterion: 144 children, median 8.1 months. By combination: 76 children, median 9.9.*

**Note.** **The claim it makes, precisely.** The evidence has been **sufficient** since that date. It does **not** say a referral was missed — the synthetic record contains no referral events at all. On real data, qualifying date against actual referral date is the number worth having.


## ref · The evidence contract and the four gates

*Not spoken. `agent_handoff_publisher` writes one JSON envelope per surfaced child — 34 of them.*


```
patient    { patient_id, referral_state, age_years, family_history_status }
criteria   [ { criterion, tier, description } ]
evidence   [ { evidence_id, evidence_type, evidence_date, evidence_text } ]
provenance { run_id, reference_source, reference_read_on, note }
```

*Only children in state `indicators_present` get one. A child the pipeline did not surface is one the agent must not write about, and the cleanest way to enforce that is never to hand it over.*

***The four gates** run in `create_referral_agent.py` and exit non-zero if any fails:*


```
1 schema      validates against referral-brief.schema.json. Hard-fails if the
              jsonschema library is missing -- a gate that skips is not a gate
2 citation    every reason cites at least one evidence_id, and every id cited
              was actually supplied
3 clinical    no diagnosis, no named condition, no refer / do-not-refer, no
              reassuring language; state and criteria copied, not invented
4 limitation  the brief says out loud that it reflects only what was recorded
```

*Gate 4 is separate because gate 3 catches a bad sentence being *present* and gate 4 catches a necessary sentence being *absent*. `test_gates.py` proves all four across 13 cases, needs no Azure and runs in about a second.*

*There is a lawful escape: an empty envelope returns `{"error": "no-evidence"}`. Without it, a contract demanding a citation leaves no valid document, and a model with no valid output available will invent one — which is exactly how fabricated evidence IDs appeared on an earlier build.*


## ref · The Foundry IQ knowledge base

*Not spoken. Azure AI Search `referral-kb-search` on the Free tier → index `referral-vocabulary` → knowledge source → knowledge base `referral-vocabulary-kb`, reached from the agent over MCP.*


```
31 documents:  16 phenotype terms, definitions fetched from the ontology
                6 criteria, with tier and placeholder status
                3 referral states, and what each one does NOT mean
                6 design concepts: tiers, no-score, equity, scope
```

*A knowledge base will not retrieve at all without a model attached to it, and that model is called with the **Search** service's managed identity — so that identity needs Cognitive Services User on the Foundry account.*

**Note.** **The scope line is structural, not prompted.** Ask it which patients were surfaced and it returns design documentation, because the corpus contains no patients. The build script refuses to publish if `SYN-`, `OBS:`, `ENC:` or `patient_id` appears anywhere in it.


## ref · The cohort agent

*Not spoken. `referral_cohort_agent`, a Fabric data agent over `gold_cohort_summary` — one tall table, one row per figure, with each figure's caveat travelling beside it as data rather than living in a prompt.*

*It reads a summary rather than the raw tables for two reasons. An agent answering from raw tables has to do arithmetic, and arithmetic is where it invents. And `gold_referral_state` carries an `array` column, which the SQL analytics endpoint cannot surface at all — the agent could only ever discover three of the nine gold tables.*

**Note.** **This is the agent to scrutinise hardest, and say so.** It can reach every child in gold. Its restraint comes from instructions, not from the shape of its input, and instructions are weaker than structure. Where you can make safety structural, do. Where you cannot, say it out loud.


## ref · The capability split, for the follow-up

*Not spoken. For the conversation after the recording.*

***Fabric carries:** OneLake as the single copy · medallion transformation and conformance · the criteria, as inspectable deterministic logic · the graph, a labelled property graph over the same tables with GQL and no ETL · the equity and latency measurements · scheduled refresh · lineage, workspace RBAC, capacity governance · a data agent for natural-language cohort questions.*

***Fabric does not carry:** a way to bound what a model can see to one supplied envelope · output contracts, meaning a schema an answer must validate against · refusal behaviour you can test in CI · reference knowledge held separately from patient data · model choice, versioning or evaluation.*

***Foundry carries those:** the evidence contract, making scope structural rather than instructed · four gates as code, exiting non-zero, provable by 13 offline test cases · a Foundry IQ knowledge base whose corpus is vocabulary only, enforced at build time · model deployment and versioning.*

**Note.** **The honest seam.** Fabric answers "who, and on what evidence". Foundry answers "what may be said about them, and can you prove it stayed inside that". The cohort agent sits awkwardly across the line — it is a Fabric agent with the widest reach and only instructions restraining it, which is precisely why it reads a summary table rather than the raw records.

***What Fabric IQ is, per Microsoft:** a semantic intelligence layer for Fabric, made of *ontologies, semantic models, graphs and data agents*, so agents can reason over analytics in OneLake and Power BI.*


```
Fabric IQ component   status here
graph                 USED   referral_graph, 18,731 nodes / 35,216 edges
data agent            USED   referral_cohort_agent over gold_cohort_summary
semantic model        not used -- the graph carries the semantics instead
ontology              USED   referral_ontology, 6 entity types / 5 relationship types
```

***What Foundry IQ is:** a managed knowledge layer — knowledge bases over Azure Blob, SharePoint, OneLake and the web, with agentic retrieval, permission enforcement and citations. Used here for the vocabulary knowledge base, 31 documents.*

**Note.** **Do not claim they plug into each other.** Foundry IQ does not list Fabric IQ among its knowledge sources. Microsoft says each IQ workload is standalone and they can be used together — which is what this is. Ontology is enabled here (tenant setting `OntologyPreview`; Canada Central supports it — the only region that does not is South Central US) and is built out: six entity types bound to gold, five relationship types. It sits above the graph rather than replacing it.


## ref · The graph model, if anyone digs

*Not spoken. Here so you can answer precisely rather than approximately.*

***Five definition parts**, POSTed by `scripts/fabric/build_graph_model.py`: `dataSources` (which lakehouse, which tables, bound by item reference) · `graphType` (the schema) · `graphDefinition` (table-to-node/edge mapping and key columns) · `stylingConfiguration` (canvas layout) · `graphSettings`.*

***The schema — entities and relationships — lives in `graphType.json`.** That is the file where the domain is declared: six node types, five edge types, their keys and properties. Everything else in the definition maps that schema onto tables.*

***Graph versus ontology, concretely.** The graph can say *Feature belongs to BodySystem*. An ontology could also say that a phenotype term *is a kind of* clinical finding, that a child cannot be both not-screened and surfaced, or that "developmental regression" means the same thing in this model as in the semantic model and the data agent — definitions decoupled from any table. Structure versus meaning, and inference on top.*

***Node type = table + unique key column.** One row, one node.*


```
Patient      <- gold_referral_state        key patientId
Feature      <- gold_hpo_terms             key hpoId
BodySystem   <- gold_body_systems          key bodySystem
Criterion    <- gold_criteria_definitions  key criterion
Encounter    <- gold_encounters            key encounterId
Specialty    <- gold_specialties           key specialty
```

***Edge type = a table holding both endpoint keys.** The foreign key becomes the relationship.*


```
hasFeature              Patient   -> Feature      via gold_observations   patient_id  -> hpo_id
inBodySystem            Feature   -> BodySystem   via gold_hpo_terms      hpo_id      -> body_system
surfacedBy              Patient   -> Criterion    via gold_criteria_hits  patient_id  -> criterion
attendedEncounter       Patient   -> Encounter    via gold_encounters     patient_id  -> encounter_id
encounterWithSpecialty  Encounter -> Specialty    via gold_encounters     encounter_id-> specialty
```

*`gold_hpo_terms` and `gold_encounters` each appear twice — once as a node table, once as an edge table. A table holding both an entity and its relationship serves both roles.*

***Why body systems and specialties got their own tables:** a node key must be unique. Pointing `BodySystem` at `gold_hpo_terms` would offer sixteen rows for seven systems.*

***Running queries:** a graph model holds the schema and the data; a **graph queryset** is the surface you query from. Bind the queryset to the model once via *Use an existing model*. The portal path is `/graph-queryset/{id}` — hyphenated, which guessed deep links get wrong.*

***Loading:** creating the model fires a Refresh job automatically — 3½ minutes for 18,731 nodes and 35,216 edges. In the portal that is the **Save** button; save and ingest are one operation, so every save reloads the data.*

**Note.** **Why gold holds copies of silver.** An edge whose two endpoints and its own source table are not all in the same lakehouse is **silently dropped at load** — the refresh reports Completed with a null failure reason and the definition still lists the edge type. Four of five edge types vanished this way before every source was moved into gold. Always count edges by label after a load; never trust Completed.


## — · Have an answer ready


---

2101 spoken words — about 15 minutes of narration at a measured pace, nearer 18 recorded once page loads and query runs are in.
