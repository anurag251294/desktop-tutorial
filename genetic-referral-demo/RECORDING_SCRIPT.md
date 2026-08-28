# Screen recording script — genetic referral case-finding

Generated from the teleprompter, so the two cannot drift.
Live: https://claude.ai/code/artifact/6b5e7ad0-e8cd-4567-bae7-fd178dae5846

The use case, in one sentence: **use agentic intelligence to identify patients
early for genetic consultation or testing.** The script is built around the three
words that do the work — *identify*, *early*, *agentic* — and is honest about the
one that does not mean what people assume.

Sections marked **ref** are not spoken. They exist so you can answer
"how does that actually work?" precisely rather than approximately.

> Quoted text is what you say. *Italic* is what you do.

## Before you hit record

- Capacity `fabdemo85829` **Active 20+ minutes** — item editors lag a resume.
- Fabric tabs in order: workspace · bronze · silver · gold criteria · **referral_queries** (the queryset — this is where GQL runs) · **latency** · validation · gold lakehouse.
- Foundry tab on `referral-foundry-mcap` → project `genetic-referral`.
- Terminal in the repo, `az login` done.
- **Click every tab once** before recording — Fabric lazy-renders background tabs.
- **Bind the queryset first, once.** Open `referral_queries` → *Use an existing model* → `referral_graph`. Do this before you record; the first time it asks, and after that it remembers. You run GQL in the **queryset**, not in the graph model — the model is only the schema.
- **Visible but not walked:** `gold_graph_dimensions` (builds the graph's dimension tables), `agent_handoff_publisher` (writes the evidence contracts), `gold_cohort_summary` (the cohort agent's serving table). Know what they are in case someone asks.
- Gold holds 16 tables, three of which are copies of silver — that is the graph's single-lakehouse requirement, and there is a line for it in the workspace section.

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


```bash
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

---

## 0:00 · Open cold

> This is case-finding in Microsoft Fabric, built for **SickKids** — the Hospital for Sick Children.

> One clarification first. **This is not a genomics project.** No genome, no variant, no test result. Nothing here reads genetic data of any kind.

> The question comes *before* genetics gets involved: which children, already at SickKids, should somebody be looking at sooner than they currently are.

*— — beat · state the use case — —*

> The use case is one sentence: **use agentic intelligence to identify patients early for genetic consultation or testing.**

> Three words do the real work — **identify**, **early** and **agentic** — and I will show you what each one means here.

*— — beat — —*

> Children with undiagnosed rare conditions spend years in a diagnostic odyssey. Many specialists, many investigations, no unifying answer — because no single clinician ever sees the whole pattern.

> The signals are already in the chart. They are just scattered across it.

---

## 1:00 · The workspace

*Click into the workspace list.*

> One workspace. Three lakehouses — bronze, silver, gold. A pipeline running five notebooks end to end in about nine minutes. An ontology, a graph beneath it, and three agents.

> And every child in here is fabricated — two thousand four hundred of them. **No SickKids data was used.** No record touched, no system connected, and nobody had to give us access to anything to build this.

*Scroll the workspace list slowly while you say this.*

> Bronze fetches the phenotype vocabulary and generates the record. Silver conforms it. Gold applies the criteria, measures how long the evidence sat there, and checks whether the flag lands evenly.

> All of it in one workspace. No copies, no exports, nothing leaving OneLake.

*If anyone notices gold holds copies of some silver tables — `gold_encounters`, `gold_observations`, `gold_hpo_terms` — have this ready:*

---

## 1:30 · Bronze — the record as it actually arrives

*Open the **notebook** `bronze_clinical_record` from the workspace list. Header, then the cohort cell.*

> Bronze pulls the Human Phenotype Ontology from its public API — a vocabulary of *observable clinical features*: developmental delay, hypotonia, short stature. Used by genetics services, which is not the same as being genetic information.

> Then it generates the clinical record deliberately untidy. Two date formats, because the encounter feed and the observation feed were built a decade apart. Five spellings of three services. Family history recorded for about six children in ten.

*Point at the comments in the cohort cell.*

> A demo on tidy data teaches you nothing. The hard part of this problem is that the record is not tidy.

---

## 3:00 · Silver — the distinction everything rests on

*Open the **notebook** `silver_conformed_record`. The family history cell.*

> This is the cell I would ask you to remember.

> Family history is missing for four children in ten. The obvious move is to fill the gap with false and get a clean boolean column.

> That would be dangerous. *Asked, and the answer was no* is not *nobody asked*. Filling that gap invents a negative finding for forty per cent of the cohort, and every count downstream becomes a lie.

*Point at `history_taken`.*

> So `history_taken` is its own column, and the flags stay null — unknown — where nobody asked. Gold refuses to score on an absence.

> The same reasoning gives a third state later: a child whose record is too short to read is *not screened*, which is not screened and clear.

---

## 4:30 · Gold — named criteria, two tiers, no score

*Open the **notebook** `gold_referral_signals`. The `CRITERIA` cell.*

*First of the three words: **identify**.*

> Six criteria, each named, each carrying its own threshold, in one place a clinician can read. This is the identifying — and it is arithmetic, not judgement.

> There is deliberately no risk score. A clinician reading *surfaced because features span four body systems* can disagree and tell you why. A clinician reading *risk zero point eight one* can only defer or ignore. One of those is a conversation.

*Point at the tiers.*

> Two tiers. A **sufficient** criterion surfaces a child on its own. A **contributory** one counts only in combination. Weight them equally and you surface a fifth of the clinic — a list nobody reads.

*Scroll to the three-states table.*

> Three states that must never collapse: indicators present, no indicators recorded, not screened.

> The middle one gets misread. It does not mean the child has no indication — it means nothing was found in the record. A child whose features were never coded looks exactly like a child who does not have them, and the pipeline does not pretend to tell them apart.

*— — beat — —*

> Every threshold is a **placeholder**, pending sign-off by the SickKids genetics service. Written as a table, so that conversation is about something a clinician can mark up.

---

## 6:30 · The ontology — where the domain is declared

*Open `referral_ontology`. Let the canvas render — six entity types and the relationships between them.*

> Everything so far has been tables. Useful — but a table does not know what it *is*.

> This does. This is the ontology, and it is where the domain gets declared. Not in a report, not in somebody's SQL — here.

*— — walk the canvas — —*

> Six entity types: a **Patient**, a **Feature** — an observable clinical finding — the **BodySystem** it belongs to, a **Criterion**, an **Encounter**, and the **Specialty** it happened in.

> And five relationships: a patient *has* a feature, a feature is *in* a body system, a patient is *surfaced by* a criterion, *attends* an encounter, an encounter is *with* a specialty. The model of this problem, written down once.

*— — the part that matters — —*

> And none of it is a copy. Every entity type is bound to a table in gold — nineteen properties, each mapped to a real column. So this is not a diagram somebody drew in a workshop. It is attached to the data.

> That is the difference between a data model and a semantic layer. A data model tells you how the bytes are arranged. This tells you what they *mean* — and tells the same thing to the query, the agent and the clinician, because there is only one of it.

*— — name it — —*

> And this is **Fabric IQ**: ontologies, semantic models, graphs and data agents. This is the ontology component.

> **NOTE** — **Be accurate about what is new here.** The ontology and the graph declare the *same* six entities and five relationships against the *same* gold tables. That is deliberate — one model, expressed once. Do not claim the ontology found anything the criteria did not; it does not compute the criteria. What it changes is that the meaning now lives in one declared place instead of being implied by a notebook.

> **NOTE** — **Preview.** Ontology is in preview and we enabled it in this tenant for this build. If someone asks how long it took: flip the tenant setting, then about ten minutes before the service honoured it. Worth saying plainly rather than pretending it was instant.

---

## 8:00 · The graph — the criterion, walked

*Switch to `referral_queries` — the **graph queryset**, which is the thing you run queries in. The graph model itself is just the schema. Paste the query and press **Run**.*

```
MATCH (p:Patient)-[:hasFeature]->(f:Feature)-[:inBodySystem]->(b:BodySystem)
WHERE p.patientId = 'SYN-00017'
RETURN f.hpoLabel AS feature, b.bodySystem AS system
ORDER BY system, feature
```

> You cannot ask a diagram a question. This is the graph — the same six entities and five relationships, made walkable. Eighteen thousand nodes, thirty-five thousand relationships, over the same gold tables.

*— — if someone asks why both — —*

> The ontology carries *meaning*. The graph carries *reach* — traversal, path finding, questions shaped like relationships rather than joins.

> So when the pipeline says this child surfaced because their features span multiple body systems, you do not have to take it on trust. You can walk it.

*Results: cardiac · neurodevelopment ×2 · neurology · skeletal.*

> There it is. Abnormal heart morphology — cardiac. Developmental regression and global developmental delay — neurodevelopment. Hypotonia — neurology. Scoliosis — skeletal. The criterion, made of its evidence.

*Now the third query — the one worth the time.*

```
MATCH (p:Patient)-[:attendedEncounter]->(:Encounter)
      -[:encounterWithSpecialty]->(s:Specialty)
WHERE p.referralState = 'no_indicators_recorded'
RETURN s.specialty AS specialty, COUNT(DISTINCT p) AS children
GROUP BY specialty ORDER BY children DESC
```

> Now a different question. Not who we found — who we did *not*, and where those children turn up.

*Results: General Paediatrics 801 · Cardiology 794 · ENT 785 · Developmental Paediatrics 776 · Neurology 769 · Orthopaedics 754.*

> Eight hundred children the screen missed are sitting in General Paediatrics. Nearly eight hundred more in Cardiology, ENT and Developmental Paediatrics. Most are fine — but if this screen is missing children, and the next section shows that it is, that is the list of clinics they are sitting in.

*— — beat — —*

> That is why a graph rather than a table. Not because the answers are impossible in SQL — because the questions arrive in the shape of relationships.

*If asked how the graph was built — and someone will:*

*— — beat — —*

> **NOTE** — **Get this exactly right.** Ontology and graph are both **Fabric IQ** components — Microsoft defines Fabric IQ as ontologies, semantic models, graphs and data agents. Both are real here and both are on screen. What you must **not** say is that the ontology found the children — the named criteria in gold do that, deterministically, and that separation is the point of the whole demo.

---

## 10:00 · How long it was already there

*Open the **notebook** `gold_signal_latency`, or just show the figures.*

*Second word: **early**. This is the section that earns it.*

> That child surfaced because their features span multiple body systems. Here is the question that actually matters: *when did that become true?*

> The sixth of March, twenty twenty-four. Twenty-nine months ago. Every feature the criterion needed was already coded, and had been for nearly two and a half years.

*— — beat · let it sit — —*

> Across all two hundred and twenty children surfaced, the median is nearly nine months. Thirty-eight per cent had complete, sufficient evidence sitting in the record for over a year. The longest is thirty-three months.

> Nobody did anything wrong. Those features were recorded by different clinicians, in different clinics, months apart. No single person ever saw them together — which is exactly what a diagnostic odyssey is.

> That is what the pipeline does. Not new information — the same information, joined up, on the day the pattern completed rather than years later.

> That is what **early** means here, and it is measured rather than asserted.

> **NOTE** — **Be precise about the claim.** The synthetic record contains no referral events, so this says the evidence has been **sufficient** since that date. It does **not** say a referral was missed or late. On real data, comparing the qualifying date against the actual referral date is the number you would want — and the obvious next thing to build.

---

## 12:00 · The finding that matters

*Show the **table** `gold_validation_sensitivity` (inside `gold_lakehouse`), or run the interpreter query on the graph.*

> Now the part I would not want you to miss.

> This cohort was generated so that children whose families need an interpreter have exactly the same underlying rate of clustered presentation as everybody else. Same biology. The only thing that differs is how much of it reached the record.

*Point at the feature counts: 939 across 486 children, versus 766 across 467.*

> Just under two features recorded per child where no interpreter is needed. About one point six where one is. Consultations run shorter, history-taking is harder, and description is less likely to land in a coded field.

*Switch to the sensitivity figures.*

> Here is what that costs. The screen finds **eighty-eight per cent** of affected children in one group and **seventy-five per cent** in the other. A twelve-point gap, from identical planted prevalence.

> And nothing in the criteria reads language or interpreter need. The notebook asserts that and fails the build if it ever stops being true.

> A flag can be blind to a protected attribute and still reproduce the inequity attached to it. Excluding the column proves nothing; measuring the outcome is the only thing that shows it.

*— — beat · the most important sentence in the recording — —*

> And it points at the actual remedy — interpreter-supported history-taking, not a better model.

> **NOTE** — **If you also show latency by interpreter need, read it carefully.** It appears to say interpreter-needing children are found *sooner* — eight months against ten. That is **survivorship, not good news**: the screen only surfaces children whose evidence crossed the threshold, and fewer of their features reach the record, so the ones that do surface are the more florid cases. The subtler ones are not in that table because the screen never found them. They are in this sensitivity gap instead.

> **NOTE** — **If asked how you know the sensitivity:** the cohort is synthetic and carries an answer key. A real deployment cannot compute this — which is precisely the argument for the synthetic cohort. It measures what production never shows you: not how many flagged children turn out to be affected, but how many affected children were never flagged. Be equally plain that the **absolute** figure is close to circular; the **gap between groups** is not, because both were planted identically.

---

## 14:30 · Three agents, three different reaches

*Third word: **agentic**. This is the one that does not mean what you might assume.*

> The children are identified by deterministic criteria — not by a model. Criteria can be inspected, argued with, reproduced next month and measured for bias. A model deciding who surfaces could do none of those things.

> So the agentic part is not the finding. It is everything around it — and what matters about the three agents is how much each one can reach.

*Open a contract: `gold_lakehouse` → Files → `contracts/` → `patient-evidence.SYN-00195.json`.*

> The first writes the brief about one child, and never queries anything. It is handed a fixed envelope — the patient's state, the criteria that fired, and evidence items, each with an identifier.

> That is the whole safety argument. It cannot reach a patient it was not handed, because scope is a property of the input, not of the model behaving.

*— — second agent — —*

> The second answers questions about **vocabulary**. It is backed by a Foundry IQ knowledge base: thirty-one documents, and no patients at all.

> Ask it which patients have been surfaced and it returns design documentation. Not because we told it to refuse — because the data is not there.

*— — third agent — —*

> The third answers cohort questions straight from Fabric — how many surfaced, which criteria fire most.

> This is the one to scrutinise hardest: it can reach every child in the gold tables. Its restraint comes from instructions, and instructions are weaker than structure.

> So it is pointed at a summary table of precomputed figures, each carrying its caveat as data. Where you can make safety structural, do. Where you cannot, say so out loud.

---

## 16:30 · The brief, and the four gates

*Terminal.*

```
python scripts/foundry/create_referral_agent.py \
    --evidence cicd/patient-evidence.SYN-00195.json \
    --output cicd/referral-brief.SYN-00195.json
```

*While it drafts — about thirty seconds:*

> Four gates run on whatever comes back. **Schema** — is it the right shape. **Citations** — does every claim point at evidence actually supplied. **Clinical safety** — no diagnosis, no named condition, no recommendation to refer, and no language that turns *nothing was recorded* into *nothing is wrong*.

> And a fourth: does the brief state its own limitations. That is separate because gate three catches a bad sentence being present, and gate four catches a necessary sentence being absent. Absence is much harder to notice by reading.

*Gates print. Open the brief; read the family history line aloud.*

> This is the child where nobody ever took a family history. The agent writes: *Family history was not recorded, so nothing is known about it.*

> Not *no significant family history*. That would be a different claim about a real child, and it would be false.

> **NOTE** — **If it fails** with `invalid_prompt: Unsupported parameter 'top_p'` — that is a service-side intermittent, not your fault and not a configuration error. Re-run the same command; it works on the retry.

---

## 17:30 · Where Fabric stops and Foundry starts

*No screen needed. Say this over the workspace, or over the brief you just produced.*

> It is worth being explicit about which platform did what, because the seam is not arbitrary — it falls where the nature of the problem changes.

*— — what fabric did — —*

> Fabric holds the data and decides *who*: one copy in OneLake, six criteria you can read, and a semantic layer over the same tables so the reasoning can be walked. Then it governs all of it — lineage, permissions, refresh.

*— — where it stops — —*

> But three things this needs before SickKids would run it, Fabric does not do.

> It cannot say *this model may see this envelope and nothing else*. It has no output contract — no schema the answer must validate against, no gate that refuses a document because a required sentence is missing. And it has no place to keep reference knowledge separately from patient data.

> Those are not gaps in Fabric. They are a different problem: not *what is true of this cohort* but *what may this system say about a child, and how do we prove it stayed inside that*.

*— — what foundry did — —*

> That is the Foundry half — the bounded contract, the four gates as code we own, and the knowledge base with provably no patients in it.

> So: Fabric decides *who*. Foundry decides *what may be said* about them, and proves it.

*— — name both layers, accurately — —*

> Both halves have names. **Fabric IQ** is the semantic layer over Fabric data — the ontology, the graph and the cohort agent are all Fabric IQ. **Foundry IQ** is the managed knowledge layer — the vocabulary knowledge base is that.

> Separate products, designed to be used together. Fabric IQ for the semantics, Foundry IQ for the knowledge, and gates of our own around whatever gets said about a child.

> **NOTE** — **Two things to keep straight.** Graphs and data agents **are** Fabric IQ, so saying this uses Fabric IQ is accurate. The Fabric IQ **ontology** is a separate component of it. It is **enabled in this tenant as of today**, and an ontology item exists but is empty — the graph is what carries the model in this demo. And Foundry IQ does **not** take Fabric IQ as a knowledge source; its sources are Blob, SharePoint, OneLake and the web. The two layers are used together, not plugged into one another.

---

## 19:00 · Close

> So: named criteria a clinician can argue with. Three states that never collapse. Evidence that can be walked rather than trusted. A measurement of how long it had been sitting there. And equity measured as an output, not promised as a review later.

> None of these thresholds are clinically validated — they are placeholders, and they need the SickKids genetics service to mark them up. No SickKids data has been anywhere near this.

> What it does show is the shape: case-finding that is inspectable, reproducible, and honest about who it misses.

*— — beat · close on the sentence you opened with — —*

> Back to that one sentence. **Identify** — six criteria you can read and disagree with. **Early** — a median of nearly nine months the evidence was already there. **Agentic** — three agents around the finding, the one that writes about a child held to four gates and given no reach at all.

> And the part the sentence does not ask for, which matters most: a measurement of who this misses, and whether it misses the same people the system already misses.

---

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

---

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

---

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

> **NOTE** — **The claim it makes, precisely.** The evidence has been **sufficient** since that date. It does **not** say a referral was missed — the synthetic record contains no referral events at all. On real data, qualifying date against actual referral date is the number worth having.

---

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

---

## ref · The Foundry IQ knowledge base

*Not spoken. Azure AI Search `referral-kb-search` on the Free tier → index `referral-vocabulary` → knowledge source → knowledge base `referral-vocabulary-kb`, reached from the agent over MCP.*

```
31 documents:  16 phenotype terms, definitions fetched from the ontology
                6 criteria, with tier and placeholder status
                3 referral states, and what each one does NOT mean
                6 design concepts: tiers, no-score, equity, scope
```

*A knowledge base will not retrieve at all without a model attached to it, and that model is called with the **Search** service's managed identity — so that identity needs Cognitive Services User on the Foundry account.*

> **NOTE** — **The scope line is structural, not prompted.** Ask it which patients were surfaced and it returns design documentation, because the corpus contains no patients. The build script refuses to publish if `SYN-`, `OBS:`, `ENC:` or `patient_id` appears anywhere in it.

---

## ref · The cohort agent

*Not spoken. `referral_cohort_agent`, a Fabric data agent over `gold_cohort_summary` — one tall table, one row per figure, with each figure's caveat travelling beside it as data rather than living in a prompt.*

*It reads a summary rather than the raw tables for two reasons. An agent answering from raw tables has to do arithmetic, and arithmetic is where it invents. And `gold_referral_state` carries an `array` column, which the SQL analytics endpoint cannot surface at all — the agent could only ever discover three of the nine gold tables.*

> **NOTE** — **This is the agent to scrutinise hardest, and say so.** It can reach every child in gold. Its restraint comes from instructions, not from the shape of its input, and instructions are weaker than structure. Where you can make safety structural, do. Where you cannot, say it out loud.

---

## ref · The capability split, for the follow-up

*Not spoken. For the conversation after the recording.*

***Fabric carries:** OneLake as the single copy · medallion transformation and conformance · the criteria, as inspectable deterministic logic · the graph, a labelled property graph over the same tables with GQL and no ETL · the equity and latency measurements · scheduled refresh · lineage, workspace RBAC, capacity governance · a data agent for natural-language cohort questions.*

***Fabric does not carry:** a way to bound what a model can see to one supplied envelope · output contracts, meaning a schema an answer must validate against · refusal behaviour you can test in CI · reference knowledge held separately from patient data · model choice, versioning or evaluation.*

***Foundry carries those:** the evidence contract, making scope structural rather than instructed · four gates as code, exiting non-zero, provable by 13 offline test cases · a Foundry IQ knowledge base whose corpus is vocabulary only, enforced at build time · model deployment and versioning.*

> **NOTE** — **The honest seam.** Fabric answers "who, and on what evidence". Foundry answers "what may be said about them, and can you prove it stayed inside that". The cohort agent sits awkwardly across the line — it is a Fabric agent with the widest reach and only instructions restraining it, which is precisely why it reads a summary table rather than the raw records.

***What Fabric IQ is, per Microsoft:** a semantic intelligence layer for Fabric, made of *ontologies, semantic models, graphs and data agents*, so agents can reason over analytics in OneLake and Power BI.*

```
Fabric IQ component   status here
graph                 USED   referral_graph, 18,731 nodes / 35,216 edges
data agent            USED   referral_cohort_agent over gold_cohort_summary
semantic model        not used -- the graph carries the semantics instead
ontology              USED   referral_ontology, 6 entity types / 5 relationship types
```

***What Foundry IQ is:** a managed knowledge layer — knowledge bases over Azure Blob, SharePoint, OneLake and the web, with agentic retrieval, permission enforcement and citations. Used here for the vocabulary knowledge base, 31 documents.*

> **NOTE** — **Do not claim they plug into each other.** Foundry IQ does not list Fabric IQ among its knowledge sources. Microsoft says each IQ workload is standalone and they can be used together — which is what this is. Ontology is enabled here (tenant setting `OntologyPreview`; Canada Central supports it — the only region that does not is South Central US) and is built out: six entity types bound to gold, five relationship types. It sits above the graph rather than replacing it.

---

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

> **NOTE** — **Why gold holds copies of silver.** An edge whose two endpoints and its own source table are not all in the same lakehouse is **silently dropped at load** — the refresh reports Completed with a null failure reason and the definition still lists the edge type. Four of five edge types vanished this way before every source was moved into gold. Always count edges by label after a load; never trust Completed.

---

## — · Have an answer ready

**“So is the AI actually identifying the patients?”**
Be exact; this is the question that catches people out. The children are identified by **deterministic criteria, not by a model** — deliberately, because criteria can be inspected, argued with and measured for bias, and a model deciding who surfaces could not be. The agentic parts are the ones that exercise no judgement over a child.

**“Would this work on our data?”**
Unknown, and say so. What transfers is the shape — inspectable criteria, three states, evidence contracts, gates, equity measured as an output.

**“What is the false positive rate?”**
On synthetic data that is an artefact of the generator. The useful question is the one the validation notebook answers: who gets missed, and is it the same people who already get missed.

**“Why not just let a model read the chart?”**
Then the model decides who surfaces, and you cannot inspect the criteria, reproduce the run next month, or measure the flag for bias — because there is no flag, only an opinion.

**“Is the graph your ontology?”**
No — they are two items and you saw both. `referral_ontology` is the Fabric IQ ontology: six entity types and five relationship types, each bound to a gold table, declaring what the things *are*. `referral_graph` is the property graph over the same gold tables, which is what makes the model traversable in GQL. Microsoft’s own framing is that ontology works together with graph, and that is how it is used here — declare it once, walk it when you need to.

**“Why declare the same model twice?”**
Fair challenge, and the honest answer is that today they are separate declarations of one model, because the graph was built first. The direction of travel is that the ontology is the place the domain is defined and everything else reads from it. What you should not hear me claim is that the ontology is computing anything — the named criteria in gold do the identifying, deterministically, and that separation is deliberate.

**“Is this Fabric IQ, or is it Foundry?”**
Both, and they are different layers. Fabric IQ is the semantic layer over Fabric data — ontologies, semantic models, graphs, data agents. We use the graph and a data agent. Foundry IQ is the managed knowledge layer for agents; we use a knowledge base for clinical vocabulary. We use the ontology, the graph and a data agent — three of the four Fabric IQ components. The two IQs are standalone products designed to be used together, not plugged into one another.

**“Is any of this genomic?”**
No. Nothing reads a genome, a variant, or a test result.

**If something breaks**
Graph query fails → may be mid-refresh; skip it. Agent errors → re-run, it is intermittent. Anything Spark → do not wait on it; nothing here needs a session. Blank tab → Fabric lazy-loads; click it and keep talking.
