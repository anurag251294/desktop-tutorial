# Superseded for the SickKids use case

**This demo answers a different question than the one SickKids asked.**

It is a *variant interpretation* demo: it reads ClinVar classifications — genomic
reference data — and drafts a consultation summary from them. The question it answers is
*"what does this variant mean?"*

The SickKids use case involves **no genomic data**. It is *case-finding*: using agentic
intelligence to identify patients early for genetic consultation or testing, from
signals already in the clinical record. The question is *"which children should someone
look at?"*

Different input, different output, different clinical risk:

| | This folder | The SickKids use case |
| --- | --- | --- |
| Input | Variants, ClinVar accessions | Clinical record signals — phenotype, encounters, family history |
| Question | What does this variant mean? | Should this child see genetics, sooner? |
| Output | Consultation summary | A surfaced patient with the reasons attached |
| Main risk | Misreporting a classification | **Missing a child**, and reproducing historical under-referral |

**For the SickKids demo, use [`../genetic-referral-demo/`](../genetic-referral-demo/).**

## Why this folder is kept

The architecture is sound and was carried over wholesale: the pipeline computes and the
agent only renders, every claim carries a citation, three states that must not collapse,
and a lawful `no-evidence` escape so the model is never cornered into inventing one.
Only the domain layer was wrong.

It also remains a working reference for variant interpretation, should that come up as a
genuinely separate conversation. It should not be shown as, or alongside, the
case-finding demo — showing both is how the two got conflated in the first place.
