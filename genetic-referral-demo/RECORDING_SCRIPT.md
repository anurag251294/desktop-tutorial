# Recording script — genetic referral case-finding

Word-for-word narration with the click path beside it. Roughly **14 minutes**.

## Before you hit record

| | |
| --- | --- |
| Capacity | `fabdemo85829` **Active** for at least 20 minutes — item editors lag a resume |
| Tabs open, in this order | workspace list · `gold_referral_signals` · `referral_graph` queryset · `Files/contracts/` · a terminal in the repo |
| Terminal | `cd genetic-referral-demo` and `az login` already done |
| Verified live | `python scripts/fabric/query_graph.py` → 7/7 · `python scripts/foundry/test_gates.py` → 13/13 |

**Notebook cells will be empty.** Fabric stores notebooks as source without outputs, so a
pipeline run leaves nothing on screen. That is fine and this script is built for it —
notebooks are shown for their **code**, and every number comes from the graph or the
agent, both of which answer in seconds. Do not run a notebook live; a cold Spark session
is three minutes of silence.

---

## 0:00 — Open cold, on a black slide or the workspace list

> This is a demonstration of agentic case-finding in Microsoft Fabric, for a children's
> hospital.
>
> Before anything else, one clarification, because it has already been misunderstood
> once. **This is not a genomics project.** There is no genome here, no variant, no test
> result. Nothing in this system reads genetic data of any kind.
>
> The question is the one that comes *before* genetics gets involved. Which children,
> already in the hospital, should somebody be looking at — sooner than they currently
> are.

*Beat. Then:*

> Children with undiagnosed rare conditions often spend years in what clinicians call a
> diagnostic odyssey. Many specialists. Many investigations. No unifying answer. And
> often no genetics referral, because no single clinician ever sees the whole pattern.
>
> The signals are usually already in the chart. They are just scattered across it.

---

## 1:00 — What is on screen: the workspace

*Click into the workspace list.*

> Everything here is one Fabric workspace. Three lakehouses in a medallion — bronze,
> silver, gold. A pipeline. A graph. And an agent.
>
> All the data is synthetic. Two thousand four hundred fabricated children. No real
> record was touched.

---

## 1:30 — Bronze: the record as it actually arrives

*Open `bronze_clinical_record`. Scroll to the markdown header, then the cohort cell.*

> Bronze does two things. It pulls the Human Phenotype Ontology from its public API —
> that is a vocabulary of *observable clinical features*, developmental delay, hypotonia,
> short stature. It is used by genetics services, which is not the same thing as being
> genetic information.
>
> And it generates the clinical record deliberately untidy.

*Point at the comments in the cohort cell.*

> Two date formats, because the encounter feed and the observation feed were built by
> different teams a decade apart. Five spellings of three services. And family history
> recorded for only about six children in ten.
>
> A demo built on tidy data teaches you nothing, because the hard part of this problem is
> that the record is not tidy.

---

## 3:00 — Silver: the distinction the whole thing rests on

*Open `silver_conformed_record`. Go to the family history cell.*

> This is the cell I would ask you to remember.
>
> Family history is missing for four children in ten. The obvious engineering move is to
> fill the gap with `false` and get a clean boolean column.
>
> That would be wrong, and it would be dangerous. **Asked, and the answer was no** is not
> the same as **nobody asked.** Filling the gap invents a negative finding for forty per
> cent of the cohort, and every downstream count becomes a lie.

*Point at `history_taken`.*

> So `history_taken` is kept as its own column, and the three flags stay null — unknown —
> where nobody asked. Gold refuses to score on the absence.
>
> The same reasoning gives us a third state later: a child whose record is too short to
> read is *not screened*, which is not the same as screened and clear.

---

## 4:30 — Gold: named criteria, two tiers, no score

*Open `gold_referral_signals`. Scroll to the `CRITERIA` cell.*

> Six criteria. Each one named, each carrying its own threshold, all in one place where a
> clinician can read them.
>
> There is deliberately **no risk score.** A clinician reading "surfaced because features
> span four body systems" can disagree with the threshold and tell you why. A clinician
> reading "risk zero point eight one" can only defer to it, or ignore it. One of those is
> a conversation. The other is not.

*Point at the tiers.*

> Two tiers. A *sufficient* criterion surfaces a child on its own — developmental
> regression does that. A *contributory* one only counts in combination. Weight them
> equally and you surface a fifth of the clinic, and a list that long is a list nobody
> reads.

*Scroll to the three-states table in the markdown.*

> Three states, and they must never collapse into each other.
>
> Indicators present. No indicators recorded. Not screened.
>
> The middle one is the one that gets misread. It does **not** mean the child has no
> indication. It means nothing was found *in the record*. A child whose features were
> never coded looks exactly like a child who does not have them. The pipeline cannot tell
> those apart — so it does not pretend to, and the agent is forbidden from writing
> anything a tired reader could take as reassurance.

*Beat.*

> And every threshold in that cell is a placeholder, pending sign-off by the genetics
> service. They are written out as a table precisely so that conversation is about
> something a clinician can mark up, not a number buried in code.

---

## 7:00 — The graph: the criterion, walked

*Switch to the `referral_graph` queryset. Run the `SYN-00017` traversal.*

```gql
MATCH (p:Patient)-[:hasFeature]->(f:Feature)-[:inBodySystem]->(b:BodySystem)
WHERE p.patientId = 'SYN-00017'
RETURN f.hpoLabel AS feature, b.bodySystem AS system
ORDER BY system, feature
```

> The criteria are not just numbers in a table. The whole model is a graph — patients,
> the features observed on them, the body systems those features belong to, the
> encounters, the specialties, and the criteria that surfaced each child.
>
> So when the pipeline says this child surfaced because features span multiple body
> systems, you do not have to take that on trust. You can walk it.

*Results appear: cardiac, neurodevelopment ×2, neurology, skeletal.*

> There it is. Abnormal heart morphology — cardiac. Developmental regression and global
> developmental delay — neurodevelopment. Hypotonia — neurology. Scoliosis — skeletal.
>
> That is the criterion, made of its evidence.

*Run the co-occurrence query.*

```gql
MATCH (p:Patient)-[:hasFeature]->(:Feature)-[:inBodySystem]->(b:BodySystem)
WHERE p.referralState = 'indicators_present'
RETURN b.bodySystem AS system, COUNT(DISTINCT p) AS children
GROUP BY system ORDER BY children DESC
```

> And because it is a graph, questions that are awkward in SQL become one pattern. Which
> body systems actually co-occur in the children we surfaced. In SQL that is a self-join
> over a bridge table. Here it is one line.

**Say this, and do not overstate it:** this is a Fabric graph — a labelled property graph
over OneLake, queried in standard GQL, and documented under Fabric IQ. It is **not** a
Fabric IQ ontology; that is a different feature and it is not enabled in this tenant.

---

## 9:30 — The finding that matters

*Run the interpreter query, or show `gold_validation_sensitivity`.*

```gql
MATCH (p:Patient)-[:hasFeature]->(f:Feature)
RETURN p.interpreterRequired AS interpreterRequired,
       COUNT(DISTINCT p) AS children, COUNT(f) AS featuresRecorded
GROUP BY interpreterRequired ORDER BY interpreterRequired
```

> Now the part I would not want you to miss.
>
> This cohort was generated so that children whose families need an interpreter have
> **exactly the same underlying rate** of clustered presentation as everybody else. Same
> biology. The only thing that differs is how much of it reached the record.

*Point at the numbers: 939 features across 486 children, versus 766 across 467.*

> Just under two features recorded per child where no interpreter is needed. About one
> point six where one is. Consultations run shorter through an interpreter, history-taking
> is harder, and description is less likely to land in a coded field.
>
> Here is what that costs.

*Switch to the sensitivity figures — 87.8% versus 75.2%.*

> The screen finds eighty-eight per cent of affected children in one group, and
> seventy-five per cent in the other. A twelve-point gap, from identical planted
> prevalence.
>
> And nothing in the criteria reads language, or interpreter need. The notebook asserts
> that, and fails the build if it ever stops being true.
>
> **A flag can be blind to a protected attribute and still reproduce the inequity attached
> to it.** Excluding the column proves nothing. Measuring the outcome is the only thing
> that shows it.

*Beat. This is the most important sentence in the recording.*

> Measuring it does not fix it. What it does is point at the actual remedy — which is
> interpreter-supported history-taking, not a better model.

**If asked how you know the sensitivity:** because the cohort is synthetic and carries an
answer key. Say plainly that a real deployment cannot compute this — which is precisely
the argument for building the synthetic cohort. It measures the thing production never
shows you: not how many flagged children turn out to be affected, but how many affected
children were never flagged. Be equally plain that the *absolute* number is close to
circular; the *gap between groups* is not, because both were planted identically.

---

## 12:00 — The agent: it renders, it does not reason

*Open a contract from `Files/contracts/` — use `patient-evidence.SYN-00195.json`.*

> The agent never queries anything. It is handed a fixed envelope: the patient's state,
> the criteria that fired, and a list of evidence items, each with an identifier.
>
> That is the whole safety argument. It cannot reach a patient it was not handed — scope
> is a property of the input, not of the model behaving. And every value it can state
> already carries a citation, so a claim with no citation is a claim about something that
> was never supplied.

*Switch to the terminal. Run the agent.*

```bash
python scripts/foundry/create_referral_agent.py \
    --evidence cicd/patient-evidence.SYN-00195.json \
    --output cicd/referral-brief.SYN-00195.json
```

*While it drafts, about thirty seconds:*

> Four gates run on whatever comes back. Schema — is it the right shape. Citations — does
> every claim point at evidence that was actually supplied. Clinical safety — no
> diagnosis, no named condition, no recommendation to refer or not refer, and no language
> that turns "nothing was recorded" into "nothing is wrong".
>
> And separately, a fourth gate: does the brief state its own limitations. That is its own
> check because gate three catches a bad sentence being *present*, and gate four catches a
> necessary sentence being *absent*. Absence is much harder to notice by reading.

*Gates print. Open the brief and read the family history line aloud.*

> This is the patient where nobody ever took a family history. And the agent writes:
> *"Family history was not recorded, so nothing is known about it."*
>
> Not "no significant family history". That would be a different claim about a real
> child, and it would be false.

---

## 13:30 — Close

> So: named criteria a clinician can argue with. Three states that never collapse. An
> agent that can only say what the pipeline gave it, with four gates on the way out. And
> an equity measurement as an output, not as a review somebody promises to do later.
>
> None of the thresholds here are clinically validated — they are placeholders, and they
> need the genetics service to mark them up. No real data has been anywhere near this.
>
> What it does show is the shape: that you can build case-finding which is inspectable,
> reproducible, and honest about who it misses.

---

## Things to have an answer ready for

**"Would this work on our data?"**
Unknown, and say so. What transfers is the shape — inspectable criteria, three states,
evidence contracts, gates, equity measured as an output.

**"What is the false positive rate?"**
On synthetic data that number is an artefact of the generator. The useful question is the
one the validation notebook answers: who gets missed, and is it the same people who
already get missed.

**"Why not just let a model read the chart?"**
Then the model decides who surfaces, and you cannot inspect the criteria, reproduce the
run next month, or measure the flag for bias — because there is no flag, only an opinion.

**"Is any of this genomic?"**
No. Nothing reads a genome, a variant, or a test result.

## If something breaks

- **Graph query fails** → it may be mid-refresh; the demo survives without it, go straight
  to the agent.
- **Agent 500s on create** → transient, seen once; re-run the command.
- **Anything Spark** → do not wait on it. Nothing in this script needs a Spark session.
