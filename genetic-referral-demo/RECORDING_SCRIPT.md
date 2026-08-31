# Screen recording script — genetic referral case-finding

Generated from the teleprompter by `scripts/make_recording_script.py`,
so the two cannot drift. Re-run it after any edit to `docs-teleprompter.html`.

Live: https://claude.ai/code/artifact/6b5e7ad0-e8cd-4567-bae7-fd178dae5846

*Screen recording script · outcome first · notes · about 16 minutes of narration*

The recording leads with the outcome, demonstrates the Fabric IQ experience,
and only then explains the machinery underneath. Sections marked **ref** are
not spoken; they exist so you can answer "how does that actually work?"
precisely rather than approximately.

> Quoted text is what you say. *Italic* is what you do.

## Before you hit record

- Capacity `fabdemo85829` **Active 20+ minutes** — item editors lag a resume.
- **Tab order is outcome-first now:** **cohort agent** (0:00) · **bronze_clinical_notes** (2:00) · **silver_extracted_findings** (2:40) · ontology (5:05) · **referral_queries** (6:15 — the queryset, where GQL runs) · latency (7:35) · **gold_validation_evidence_uplift** (8:20 — the finding) · gold lakehouse Files/contracts (10:35) · workspace (12:25) · bronze · silver · gold criteria · Foundry (16:35). Run `tabs_ont.py` and it lands in this order.
- Foundry tab on `referral-foundry-mcap` → project `genetic-referral`.
- Terminal in the repo, `az login` done.
- **Click every tab once** before recording — Fabric lazy-renders background tabs.
- **Bind the queryset first, once.** Open `referral_queries` → *Use an existing model* → `referral_graph`. Do this before you record; the first time it asks, and after that it remembers. You run GQL in the **queryset**, not in the graph model — the model is only the schema.
- **Visible but not walked:** `gold_graph_dimensions` (builds the graph's dimension tables), `agent_handoff_publisher` (writes the evidence contracts), `gold_cohort_summary` (the cohort agent's serving table). Know what they are in case someone asks.
- Gold holds 16 tables, three of which are copies of silver — that is the graph's single-lakehouse requirement, and there is a line for it in the workspace section.
- **You open on the cohort agent, not the workspace.** Say the three numbers first, then ask the agent for the state breakdown and let it corroborate. The narration never depends on its answer — if it stalls, carry on.
- **The finding is that the gap got WIDER.** Reading the notes found 44 more patients and moved the interpreter sensitivity gap from 12.6 points to 14.3. Do not present the uplift as the headline and the widening as a footnote — it is the other way round.
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

- **Cohort** — 2,400 patients · **264 flagged** · 1,722 no indicators · 414 not screened
- **Notes uplift** — coded only **220** → with notes **264** · **44 flagged only via notes**
- **Notes** — 5,079 notes · 573 findings only in prose · **472 recovered (82%)**
- **Extraction** — precision **100%** · recall **91.7%** · present 1,854 / negated 1,736 / family 1,075
- **Sensitivity** — coded only **87.8** vs **75.2** (gap 12.6)
- **… with notes** — **96.9** vs **82.6** — gap **14.3, WIDER**
- **Latency** — median **12.0 months** · 50% over a year · longest 33.2
- **Observations** — gold 3,559 = 1,705 coded + **1,854 from notes**
- **Ontology / graph** — 6 entity types · 5 relationship types · 19 bound properties
- **Knowledge base** — 31 documents

## 0:00 · What it produces

*Open on the **cohort agent** tab, chat pane empty. Nothing else on screen for the first minute.*

> This is a case-finding pipeline in Microsoft Fabric, built for **SickKids**.

> The ask: **use agentic intelligence to identify patients early for genetic consultation or testing** — by reading historical clinical notes and patient history.

> Children with undiagnosed rare conditions get referred late because their findings are scattered. Across clinics, across visits, and across different *kinds* of record. Some of it is coded. A lot is only ever written in a note.

`— beat · the numbers, before any screen —`

> Two thousand four hundred patients in. **Two hundred and sixty-four** flagged for genetics review.

> **Forty-four of those were flagged only because the pipeline read the notes.** Nothing in any coded field would have surfaced them.

> For everyone flagged, the qualifying evidence had been in the record a median of **twelve months**. Half of them, over a year.

*Now type it and send. Keep talking while it runs — about fifteen seconds.*


```
How many patients are in each referral state?
```

`— TYPE NOW: “How many patients are in each referral state?” · send · keep talking —`

> That is the cohort agent answering off the gold tables, not me reading a slide. And it returns the caveat with each figure — the middle state does not mean the patient is clear, it means nothing was found in the record.

`— the finding —`

> And reading the notes did something I did not build it to do. It found forty-four more children, *and it widened the gap between who gets found and who does not*. That is the most important thing in here.

> Two clarifications. **This is not genomics** — no genome, no variant, no test result. And the data is synthetic: two thousand four hundred generated patients, notes included. **No SickKids data**, no connection to any SickKids system.

> Output first, then the code.


## 2:00 · The notes — what the coded feed could not see

*Open `bronze_clinical_notes`. Show one row, then widen `note_text`.*

> This is the part a coded pipeline walks straight past.

> A note says *low tone*. It never says *H P colon zero zero zero one two five two*. So a pipeline reading coded observations does not see that patient has hypotonia — because in this record, nobody ever coded it.

> There are 5,079 notes across the cohort. 573 findings are described in one of them and coded nowhere at all.

*Switch to `silver_extracted_findings`.*

> So silver reads the notes and produces findings from them. Each one carries the note it came from, the character span it matched, and an assertion.

`— the assertion column is the whole thing —`

> Matching is the easy half. These three sentences all contain the word scoliosis, and only one is a finding about this patient.


```
Scoliosis noted, unchanged since the last review.   -> present
No evidence of scoliosis.                           -> negated
An older sibling was investigated for scoliosis.    -> family_history
```

> Only *present* reaches gold. Count the other two and you flag patients for findings their notes say they do not have — and you inflate the body-system count that the strongest criterion reads.

*Show the assertion breakdown: present 1,854 · negated 1,736 · family history 1,075.*

> Of 4,665 mentions found, only 1,854 are findings about the patient in front of you. Nearly three in five are a negation or somebody else's history.

`— how well does it work —`

> Extraction recovered **472 of the 573** findings that existed only in prose — about eighty-two per cent — with no false positives.

> What it missed is all shorthand the dictionary does not carry. *G D D.* *C H D.* *Failure to thrive.* *Floppy.* That is where a clinical NLP model goes in production, and the contract would not change: every finding still names the note and the span.

**Note.** **Why a dictionary and not a model.** The argument of this pipeline is that the criteria decide who surfaces and the criteria are inspectable. Put a model in the extraction path and a model decides which findings a patient has — the same problem one step earlier, no longer reproducible or measurable for bias. Production should use clinical NLP. The only reason extraction can be *measured* here at all is that the cohort is synthetic and carries an answer key; a real deployment cannot compute this number.

**Note.** **If asked why precision is 100%.** Because the extractor only claims phrases it knows and the assertion logic handles negation and family history. Recall is the honest number — eighty-two per cent of note-only findings — and it is below 100 because eighteen per cent of mentions were deliberately written in shorthand the lexicon was never given.


## 3:55 · Where the notes live — not here

*No screen needed. Say this straight after the notes section; it is the first question reading notes raises.*

> One thing to be clear about, because a demo that reads clinical notes raises it immediately.

> In this build the notes are synthetic and generated in the workspace. In your environment they would not move at all.

`— the mechanism —`

> OneLake shortcuts read data where it already is. Cloudera ships **Apache Ozone**, which exposes an S3-compatible API, so Fabric points an S3-compatible shortcut at it and reads in place. No copy, no ingest, no second home for a clinical note.

> And for an endpoint that is not on the public internet — which yours would not be — the same shortcut runs through an **on-premises data gateway** you host. Microsoft supports that for S3, S3-compatible and Google Cloud Storage shortcuts.

`— the honest half —`

> What Fabric does write is the derived output. The extracted findings, the criteria results, the evidence contracts. Coded findings and pointers back to the note — not the note text.

> So **Expedition stays the source of truth.** One copy of the notes, where they already are, under your governance. Fabric reads them and writes back something much smaller.

**Note.** **Specifics, if pushed.** Ozone is on CDP runtimes and speaks S3, so it is an `S3 compatible` shortcut — not a bespoke Cloudera connector. The gateway is a standard OPDG on a Windows host with network line of sight to the Ozone endpoint; a self-signed certificate must be trusted on that host. OPDG shortcuts support caching, which cuts repeated egress. Use the service endpoint, not a bucket URL. If they cannot expose Ozone's S3 gateway at all, Data Factory has Impala and Hive connectors over the same gateway — but that is a **pipeline copy**, the thing we are trying not to do, so do not lead with it.


## 5:05 · The ontology

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


## 6:15 · The graph — checking a flag

*Switch to `referral_queries` — the **graph queryset**, which is the thing you run queries in. The graph model itself is just the schema. Paste the query and press **Run**.*


```
MATCH (p:Patient)-[r:hasFeature]->(f:Feature)-[:inBodySystem]->(b:BodySystem)
WHERE p.patientId = 'SYN-00096'
RETURN f.hpoLabel AS feature, b.bodySystem AS system, r.recordedBy AS source
ORDER BY system, feature
```

> You cannot ask a table why. This is the graph — the same entities, made traversable. You write GQL against it instead of joining six tables by hand.

`— if someone asks why both —`

> This is one of the forty-four — a patient the coded feed alone would never have surfaced. They were flagged for findings spanning multiple body systems. The query walks patient, to findings, to body systems — so you can check the flag rather than trust it.

*Results — five rows. **Small for gestational age** / growth / *note extraction*. Seizure / neurology, twice: once *Clinician*, once *note extraction*. Scoliosis / skeletal, the same pair.*

> Look at `recordedBy`. Seizure and scoliosis were both coded *and* described in a note. But **small for gestational age** only ever appears in prose.

> And that is the one that matters. On coded evidence this patient has findings in two body systems — neurology and skeletal. The criterion needs three. The note adds growth, and that is what takes them over the line.

> So this is not a patient the coded pipeline scored slightly lower. It is a patient it could not see at all — and you can walk exactly why, back to the sentence it came from.

*Second query.*


```
MATCH (p:Patient)-[:attendedEncounter]->(:Encounter)
      -[:encounterWithSpecialty]->(s:Specialty)
WHERE p.referralState = 'no_indicators_recorded'
RETURN s.specialty AS specialty, COUNT(DISTINCT p) AS children
GROUP BY specialty ORDER BY children DESC
```

> Second query, different question. Not who got flagged — who did not, and which clinics they are sitting in.

*Results: General Paediatrics 778 · Cardiology 771 · ENT 759 · Developmental Paediatrics 755 · Neurology 743 · Orthopaedics 736.*

> Nearly eight hundred patients with no indicators recorded are in General Paediatrics. Around seven hundred and fifty each across Cardiology, ENT and Developmental Paediatrics. Most are fine. But the screen does miss patients, and this is where the missed ones sit.

`— beat —`

*If asked how the graph was built — and someone will:*

`— beat —`

**Note.** **Get this exactly right.** Ontology and graph are both **Fabric IQ** components — Microsoft defines Fabric IQ as ontologies, semantic models, graphs and data agents. Both are real here and both are on screen. What you must **not** say is that the ontology found the children — the named criteria in gold do that, deterministically, and that separation is the point of the whole demo.


## 7:35 · Latency — how long the evidence sat there

*Open the **notebook** `gold_signal_latency`, or just show the figures.*

> Next question: for each patient, when did their criteria first become true?

> Across all 264 flagged, the median is **twelve months**. Half are over a year. The longest is 33.2 months.

> This is not anyone making a mistake. The findings were recorded by different clinicians, in different clinics, months apart — some coded, some only written down. Nothing joined them up.

> That is what the pipeline does. It joins them up, and it computes the date the pattern completed.

> So **early** is a measured number here, not a claim.

**Note.** **Be precise about the claim.** The synthetic record contains no referral events, so this says the evidence has been **sufficient** since that date. It does **not** say a referral was missed or late. On real data, comparing the qualifying date against the actual referral date is the number you would want, and the obvious next thing to build.

**Note.** **If you show latency by interpreter need,** it reads 10.9 months against 12.9 — apparently *better* for interpreter-needing patients. That is **survivorship**, not good news: the screen only surfaces patients whose evidence crossed the threshold, and fewer of their findings reach any field, so the ones that do surface are the more florid cases. The subtler ones are not in this table because the screen never found them. They are in the sensitivity gap instead.


## 8:20 · The finding — reading the notes made the gap worse

*Show `gold_validation_evidence_uplift` in the gold lakehouse. Four rows. Slow right down here.*

> This is the number I opened with, and it is the one I would most want you to take away.

> The cohort plants the same rate of clustered presentation in both groups. Same simulated biology. What differs is how much of it gets written down — and now, which field it gets written in.

`— coded only —`

> On coded observations alone, the screen finds **87.8 per cent** of affected patients where no interpreter is needed, and **75.2** where one is. A gap of **12.6 points**.

`— now add the notes —`

> Both go up. **96.9** and **82.6**. Forty-four more children found, which is the headline anyone would want.

> And the gap goes from 12.6 points to **14.3**. Reading the notes found more patients *and made the disparity worse*.

`— beat · let that sit —`

> Which is not a paradox. A new reading channel helps most where there is most to read. Shorter consultations produce shorter notes, so the group that was already under-documented gained the least from reading them.

> I want to be precise about the status of that number. This is a synthetic cohort and I planted the documentation behaviour, so the direction follows from how it was built. Whether it goes the same way in your data is an empirical question, and I do not know the answer.

> The point is not the number. The point is that the pipeline *measures* it — so you find out before you deploy the capability, not after.

> A team that shipped notes extraction on *we found forty-four more children* would have shipped a widened disparity and never known it was there.

> And nothing in the criteria reads language or interpreter status. There is an assert in the notebook that fails the build if that ever stops being true. Excluding the column is not what makes this visible — measuring the outcome by group is.

**Note.** **Do not soften this into a win.** The instinct is to present the uplift and mention the gap. It has to be the other way round: the uplift is expected, the widening is the finding. If someone pushes back that the demo is "negative", the answer is that a screen you cannot audit for this is a screen you cannot deploy in a paediatric hospital.

**Note.** **If asked how you know sensitivity at all:** the cohort is synthetic and carries an answer key. A real deployment cannot compute this, which is precisely the argument for the synthetic cohort — it measures what production never shows you: not how many flagged patients turn out to be affected, but how many affected patients were never flagged. The **absolute** level is close to circular against a planted pattern. The **gap**, and the change in the gap, are not.


## 10:35 · The brief, and the four checks

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


## 12:10 · How it works

*Back to the workspace list.*

> That is the output. Now the code that produces it.

> Three parts worth looking at: how the record gets conformed, how the criteria are written, and what each agent can reach.


## 12:25 · The workspace

*Click into the workspace list.*

> One workspace. Three lakehouses — bronze, silver, gold. A pipeline with five notebook activities, about nine minutes end to end. Plus the ontology, the graph and three agents.

> Bronze pulls the vocabulary and generates the record. Silver conforms it. Gold applies the criteria, computes latency, and runs the sensitivity check.

*Scroll the workspace list slowly while you say this.*

> All Delta tables in OneLake. No copies out, nothing leaves the workspace.

*If anyone notices gold holds copies of some silver tables — `gold_encounters`, `gold_observations`, `gold_hpo_terms` — have this ready:*


## 12:55 · Bronze — the raw record

*Open the **notebook** `bronze_clinical_record` from the workspace list. Header, then the cohort cell.*

> Bronze pulls the Human Phenotype Ontology from its public API — a coded vocabulary of observable findings. Genetics services use it; it is not genetic data.

> Then it generates the record with realistic mess in it. Two date formats, five spellings across three service names, family history present for about sixty per cent of patients — and notes that describe things the coded fields never captured.

*Point at the comments in the cohort cell.*


## 13:25 · Silver — null is not false

*Open the **notebook** `silver_conformed_record`. The family history cell.*

> This is the cell that matters most.

> Family history is missing for forty per cent of patients. The easy fix is `fillna(False)`, which turns *nobody asked* into *asked, answer was no* for forty per cent of the cohort. Every downstream count is then wrong.

*Point at `history_taken`.*

> So `history_taken` is its own boolean and the flags stay null where nobody asked. The criteria skip nulls rather than counting them as negative.

> Same logic gives the third state: too sparse to evaluate comes out `not_screened`, not clear.


## 14:10 · Gold — the criteria

*Open the **notebook** `gold_referral_signals`. The `CRITERIA` cell.*

*First of the three words: **identify**.*

> Six criteria. Each named, each with its own threshold, all in one dict at the top of the notebook.

> No risk score, on purpose. *Flagged because findings span four body systems* is something a clinician can check and push back on. *Risk zero point eight one* is not.

*Point at the tiers.*

> Two tiers. **Sufficient** criteria flag on their own; **contributory** ones only count in combination. Weight them the same and you flag a fifth of the cohort.

*Scroll to the three-states table.*

> And the criteria did not change when we added notes. They read findings — it does not matter to them whether a finding came from a coded field or a sentence. That is the whole reason the comparison is clean.

`— beat —`

> Every threshold is a placeholder pending sign-off from the SickKids genetics service.


## 15:15 · Three agents, and what each can reach

*Third word: **agentic**. This is the one that does not mean what you might assume.*

> Patients are flagged by the criteria in gold, not by a model. You can read them, version them, re-run them and measure them for bias. You cannot do any of that with a model that decides who surfaces.

> So the agents are not doing the finding. What matters about each one is what it can reach.

*Open the envelope that brief was written from: `gold_lakehouse` → Files → `contracts/` → `patient-evidence.SYN-00195.json`.*

> The first wrote that brief. No tools, no query access — it gets a JSON file and nothing else, so its scope is whatever is in the file.

`— second agent —`

> The second answers vocabulary questions from a Foundry IQ knowledge base: thirty-one documents, no patient data indexed. Ask it which patients were flagged and it returns design docs, because there is nothing else in there.

> The third is a Fabric data agent over gold — the one to scrutinise hardest, because it can reach every patient row. Its limits are prompt instructions, and instructions are weaker than not having access.

`— third agent —`

> So it is pointed at a summary table of precomputed figures with the caveats stored as columns. Where you can enforce scope structurally, do. Where you cannot, say so.


## 16:35 · Fabric and Foundry — which does what

*No screen needed. Say this over the workspace, or over the brief you just produced.*

> Quickly, on which platform does what.

`— what Fabric did —`

> Fabric does the data and the selection: one copy in OneLake or shortcut to where it already lives, the criteria, the ontology and graph, plus lineage and permissions.

`— where it stops —`

> What it does not do is scope a model to a single payload, validate an output against a schema, or hold reference documents apart from patient data. That is a different job — constraining and checking what gets generated about a patient.

> So Fabric selects the patients. Foundry constrains and checks what gets written about them.

`— what Foundry did —`

> On naming: **Fabric IQ** is the ontology, the graph and the data agent. **Foundry IQ** is the knowledge base. Separate products — Foundry IQ does not take Fabric IQ as a source.

`— name both layers, accurately —`

**Note.** **Two things to keep straight.** The ontology, the graph and the data agent are all **Fabric IQ** components, and all three are live and populated here — six entity types, five relationship types, nineteen bound properties. And Foundry IQ does **not** take Fabric IQ as a knowledge source; its sources are Blob, SharePoint, OneLake and the web. The two are used together, not plugged into one another.


## 17:30 · Close

> Recap. Criteria you can read. Three states kept separate. Findings extracted from notes, each one traceable to a sentence. Latency measured per patient. And sensitivity measured by group.

> The thresholds are not clinically validated — placeholders for the SickKids genetics service to review. The data is synthetic; no SickKids data was used.

`— beat · close on the sentence you opened with —`

> And the part nobody asked for, which is the reason to build it this way: reading the notes found forty-four more children and widened the gap. You only know that if you measure it.


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

***Results:** median 12.0 months · 50% over a year · longest 32.9. 83 of 220 — 38% — over a year. Qualified by a sufficient criterion: 144 children, median 8.1 months. By combination: 76 children, median 9.9.*

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
graph                 USED   referral_graph, 18,731 nodes / 37,216 edges
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

***Loading:** creating the model fires a Refresh job automatically — 3½ minutes for 18,731 nodes and 37,216 edges. In the portal that is the **Save** button; save and ingest are one operation, so every save reloads the data.*

**Note.** **Why gold holds copies of silver.** An edge whose two endpoints and its own source table are not all in the same lakehouse is **silently dropped at load** — the refresh reports Completed with a null failure reason and the definition still lists the edge type. Four of five edge types vanished this way before every source was moved into gold. Always count edges by label after a load; never trust Completed.


## — · Have an answer ready


---

2362 spoken words — about 17 minutes of narration at a measured pace, nearer 18 recorded once page loads and query runs are in.
