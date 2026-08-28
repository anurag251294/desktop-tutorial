# Screen recording script — genetic referral case-finding

Generated from the teleprompter, so the two cannot drift.
Live version: https://claude.ai/code/artifact/6b5e7ad0-e8cd-4567-bae7-fd178dae5846

> Quoted text is what you say. *Italic* is what you do.

## Before you hit record

- Capacity `fabdemo85829` **Active 20+ minutes** — item editors lag a resume.
- Fabric tabs in order: workspace · bronze · silver · gold criteria · **graph** · **latency** · validation · gold lakehouse.
- Foundry tab on `referral-foundry-mcap` → project `genetic-referral`.
- Terminal in the repo, `az login` done.
- **Click every tab once** before recording — Fabric lazy-renders background tabs.
- **Visible but not walked:** `gold_graph_dimensions` (builds the graph's dimension tables), `agent_handoff_publisher` (writes the evidence contracts), `gold_cohort_summary` (the cohort agent's serving table). Know what they are in case someone asks.
- Gold holds 16 tables, three of which are copies of silver — that is the graph's single-lakehouse requirement, and there is a line for it in the workspace section.

## What is what — nothing here lives inside a lakehouse

- Everything you open in this script is in the **workspace list**, not inside a lakehouse. `bronze_clinical_record` is a **notebook** that sits beside `bronze_lakehouse`, not in it.
- **NOTEBOOK** — `bronze_clinical_record` · `silver_conformed_record` · `gold_referral_signals` · `gold_signal_latency` · `validation_sensitivity`
- **GRAPH** — `referral_graph`
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
- **Graph** — 18,731 nodes · 35,216 edges
- **Knowledge base** — 31 documents

---

## 0:00 · Open cold

> This is a demonstration of case-finding in Microsoft Fabric, for a children's hospital.

> Before anything else, one clarification, because it has already been misunderstood once. **This is not a genomics project.** There is no genome here, no variant, no test result. Nothing in this system reads genetic data of any kind.

> The question is the one that comes *before* genetics gets involved: which children, already in this hospital, should somebody be looking at — sooner than they currently are.

*— — beat — —*

> Children with undiagnosed rare conditions often spend years in what clinicians call a diagnostic odyssey. Many specialists. Many investigations. No unifying answer. And often no genetics referral, because no single clinician ever sees the whole pattern.

> The signals are usually already in the chart. They are just scattered across it.

---

## 1:00 · The workspace

*Click into the workspace list.*

> One Fabric workspace. Three lakehouses in a medallion — bronze, silver, gold. A pipeline. A graph. And three agents, which I will come back to, because the differences between them are the point.

> Every child in here is fabricated. Two thousand four hundred of them. No real record was touched, and nothing was connected to a hospital system.

*If anyone notices gold holds copies of some silver tables — `gold_encounters`, `gold_observations`, `gold_hpo_terms` — have this ready:*

> Gold carries copies of a few silver tables, and that is deliberate. The graph needs every table it reads to sit in one lakehouse — an edge whose two ends and its own source are spread across two lakehouses is silently dropped at load, which cost us four of five relationship types before we found it. Gold is the serving layer, so gold is where the graph reads.

---

## 1:30 · Bronze — the record as it actually arrives

*Open the **notebook** `bronze_clinical_record` from the workspace list. Header, then the cohort cell.*

> Bronze does two things. It pulls the Human Phenotype Ontology from its public API — a vocabulary of *observable clinical features*: developmental delay, hypotonia, short stature. It is used by genetics services, which is not the same thing as being genetic information.

> And it generates the clinical record deliberately untidy.

*Point at the comments in the cohort cell.*

> Two date formats, because the encounter feed and the observation feed were built by different teams a decade apart. Five spellings of three services. Family history recorded for only about six children in ten.

> A demo built on tidy data teaches you nothing, because the hard part of this problem is that the record is not tidy.

---

## 3:00 · Silver — the distinction everything rests on

*Open the **notebook** `silver_conformed_record`. The family history cell.*

> This is the cell I would ask you to remember.

> Family history is missing for four children in ten. The obvious engineering move is to fill the gap with `false` and get a clean boolean column.

> That would be wrong, and it would be dangerous. **Asked, and the answer was no** is not the same as **nobody asked.** Filling that gap invents a negative finding for forty per cent of the cohort, and every count downstream becomes a lie.

*Point at `history_taken`.*

> So `history_taken` is its own column, and the three flags stay null — unknown — where nobody asked. Gold refuses to score on an absence.

> The same reasoning gives us a third state later: a child whose record is too short to read is *not screened*, which is not the same as screened and clear.

---

## 4:30 · Gold — named criteria, two tiers, no score

*Open the **notebook** `gold_referral_signals`. The `CRITERIA` cell.*

> Six criteria. Each one named, each carrying its own threshold, all in one place a clinician can read.

> There is deliberately **no risk score.** A clinician reading “surfaced because features span four body systems” can disagree with the threshold and tell you why. A clinician reading “risk zero point eight one” can only defer to it or ignore it. One of those is a conversation. The other is not.

*Point at the tiers.*

> Two tiers. A *sufficient* criterion surfaces a child on its own — developmental regression does that. A *contributory* one counts only in combination. Weight them equally and you surface a fifth of the clinic, which is a list nobody reads.

*Scroll to the three-states table.*

> Three states, and they must never collapse into each other. Indicators present. No indicators recorded. Not screened.

> The middle one is the one that gets misread. It does **not** mean the child has no indication. It means nothing was found *in the record*. A child whose features were never coded looks exactly like a child who does not have them. The pipeline cannot tell those apart, so it does not pretend to.

*— — beat — —*

> And every threshold in that cell is a **placeholder**, pending sign-off by the genetics service. They are written out as a table so that conversation is about something a clinician can mark up, not a number buried in code.

---

## 7:00 · The graph — the criterion, walked

*Switch to the **graph** `referral_graph`. Run it.*

> The whole model is a graph — patients, the features observed on them, the body systems those features belong to, the encounters, the specialties, and the criteria that surfaced each child. Eighteen thousand nodes, thirty-five thousand relationships.

> So when the pipeline says this child surfaced because their features span multiple body systems, you do not have to take that on trust. You can walk it.

*Results: cardiac · neurodevelopment ×2 · neurology · skeletal.*

> There it is. Abnormal heart morphology — cardiac. Developmental regression and global developmental delay — neurodevelopment. Hypotonia — neurology. Scoliosis — skeletal. That is the criterion, made of its evidence.

*Run the co-occurrence query.*

> And because it is a graph, a question that is awkward in SQL becomes one pattern: which body systems actually co-occur in the children we surfaced. In SQL that is a self-join over a bridge table. Here it is one line.

> **NOTE** — **Do not overstate this.** It is a Fabric graph — a labelled property graph over OneLake, queried in standard GQL, documented under Fabric IQ. It is **not** a Fabric IQ ontology; that is a different feature and it is not enabled in this tenant.

```
MATCH (p:Patient)-[:hasFeature]->(f:Feature)-[:inBodySystem]->(b:BodySystem)
WHERE p.patientId = 'SYN-00017'
RETURN f.hpoLabel AS feature, b.bodySystem AS system
ORDER BY system, feature
```

```
MATCH (p:Patient)-[:hasFeature]->(:Feature)-[:inBodySystem]->(b:BodySystem)
WHERE p.referralState = 'indicators_present'
RETURN b.bodySystem AS system, COUNT(DISTINCT p) AS children
GROUP BY system ORDER BY children DESC
```

---

## 9:00 · How long it was already there

*Open the **notebook** `gold_signal_latency`, or just show the figures.*

> That child surfaced because their features span multiple body systems. Here is the question that actually matters: **when did that become true?**

> The sixth of March, twenty twenty-four. **Twenty-nine months ago.** Every feature the criterion needed was already coded, and had been for nearly two and a half years.

*— — beat · let it sit — —*

> Across all two hundred and twenty children the screen surfaced, the median is nearly nine months. **Thirty-eight per cent** have had complete, sufficient evidence sitting in the record for over a year. The longest is thirty-three months.

> Nobody did anything wrong here. Those features were recorded by different clinicians, in different clinics, months apart. No single person ever saw them together — which is exactly what a diagnostic odyssey is.

> This is what the pipeline actually does. Not new information. The same information, joined up, on the day the pattern completed rather than years later.

> **NOTE** — **Be precise about the claim.** The synthetic record contains no referral events, so this says the evidence has been **sufficient** since that date. It does **not** say a referral was missed or late. On real data, comparing the qualifying date against the actual referral date is the number you would want — and the obvious next thing to build.

---

## 11:00 · The finding that matters

*Show the **table** `gold_validation_sensitivity` (inside `gold_lakehouse`), or run the interpreter query on the graph.*

> Now the part I would not want you to miss.

> This cohort was generated so that children whose families need an interpreter have **exactly the same underlying rate** of clustered presentation as everybody else. Same biology. The only thing that differs is how much of it reached the record.

*Point at the feature counts: 939 across 486 children, versus 766 across 467.*

> Just under two features recorded per child where no interpreter is needed. About one point six where one is. Consultations run shorter through an interpreter, history-taking is harder, and description is less likely to land in a coded field.

> Here is what that costs.

*Switch to the sensitivity figures.*

> The screen finds **eighty-eight per cent** of affected children in one group, and **seventy-five per cent** in the other. A twelve-point gap, from identical planted prevalence.

> And nothing in the criteria reads language, or interpreter need. The notebook asserts that and fails the build if it ever stops being true.

> **A flag can be blind to a protected attribute and still reproduce the inequity attached to it.** Excluding the column proves nothing. Measuring the outcome is the only thing that shows it.

*— — beat · the most important sentence in the recording — —*

> Measuring it does not fix it. What it does is point at the actual remedy — which is interpreter-supported history-taking, not a better model.

> **NOTE** — **If you also show latency by interpreter need, read it carefully.** It appears to say interpreter-needing children are found *sooner* — eight months against ten. That is **survivorship, not good news**: the screen only surfaces children whose evidence crossed the threshold, and fewer of their features reach the record, so the ones that do surface are the more florid cases. The subtler ones are not in that table because the screen never found them. They are in this sensitivity gap instead.

> **NOTE** — **If asked how you know the sensitivity:** the cohort is synthetic and carries an answer key. A real deployment cannot compute this — which is precisely the argument for the synthetic cohort. It measures what production never shows you: not how many flagged children turn out to be affected, but how many affected children were never flagged. Be equally plain that the **absolute** figure is close to circular; the **gap between groups** is not, because both were planted identically.

---

## 13:30 · Three agents, three different reaches

> There are three agents here, and the interesting thing is not what they do. It is how much each one can reach, and where the safety comes from in each case.

*Open a contract: `gold_lakehouse` → Files → `contracts/` → `patient-evidence.SYN-00195.json`.*

> The first writes the brief about one child. It never queries anything. It is handed a fixed envelope — the patient's state, the criteria that fired, and a list of evidence items, each with an identifier.

> That is the whole safety argument. It cannot reach a patient it was not handed, because scope is a property of the input, not of the model behaving. And every value it can state already carries a citation, so a claim with no citation is a claim about something that was never supplied.

*— — second agent — —*

> The second answers questions about **vocabulary**. What developmental regression means. What makes a criterion sufficient rather than contributory. It is backed by a Foundry IQ knowledge base — thirty-one documents: phenotype definitions pulled from the ontology, the six criteria, the three states.

> It can retrieve freely, because there is nothing in that corpus that identifies anybody. Ask it which patients have been surfaced and it returns design documentation — because **there are no patients in it.** Not because we told it to refuse. Because the data is not there.

> A knowledge layer answers what a word means. It must not become a way to ask who a child is. That line is enforced by what we indexed, not by a prompt.

*— — third agent — —*

> The third answers cohort questions straight from Fabric — how many surfaced, which criteria fire most, how long the evidence has been sitting there.

> And this is the one to scrutinise hardest, so I want to be honest about it. It *can* reach every child in the gold tables. Its restraint does not come from the shape of its input the way the first agent's does. It comes from instructions — and instructions are weaker than structure.

> That is why it is pointed at a summary table of precomputed figures rather than the raw records, and why every figure carries its caveat as data travelling alongside it. Where you can make safety structural, do. Where you cannot, say so out loud.

---

## 15:30 · The brief, and the four gates

*Terminal.*

*While it drafts — about thirty seconds:*

> Four gates run on whatever comes back. Schema — is it the right shape. Citations — does every claim point at evidence actually supplied. Clinical safety — no diagnosis, no named condition, no recommendation to refer or not refer, and no language that turns “nothing was recorded” into “nothing is wrong”.

> And separately, a fourth: does the brief state its own limitations. That is its own gate because gate three catches a bad sentence being *present*, and gate four catches a necessary sentence being *absent*. Absence is much harder to notice by reading.

*Gates print. Open the brief; read the family history line aloud.*

> This is the child where nobody ever took a family history. The agent writes: *“Family history was not recorded, so nothing is known about it.”*

> Not “no significant family history”. That would be a different claim about a real child, and it would be false.

> **NOTE** — **If it fails** with `invalid_prompt: Unsupported parameter 'top_p'` — that is a service-side intermittent, not your fault and not a configuration error. Re-run the same command; it works on the retry.

```
python scripts/foundry/create_referral_agent.py \
    --evidence cicd/patient-evidence.SYN-00195.json \
    --output cicd/referral-brief.SYN-00195.json
```

---

## 17:00 · Close

> So: named criteria a clinician can argue with. Three states that never collapse. Evidence that can be walked rather than trusted. A measurement of how long that evidence had been sitting there. Agents whose reach is deliberately different, with four gates on the one that writes about a child. And equity measured as an output, not as a review somebody promises to do later.

> None of these thresholds are clinically validated — they are placeholders, and they need the genetics service to mark them up. No real data has been anywhere near this.

> What it does show is the shape: case-finding that is inspectable, reproducible, and honest about who it misses.

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

**“Is any of this genomic?”**
No. Nothing reads a genome, a variant, or a test result.

**If something breaks**
Graph query fails → may be mid-refresh; skip it. Agent errors → re-run, it is intermittent. Anything Spark → do not wait on it; nothing here needs a session. Blank tab → Fabric lazy-loads; click it and keep talking.
