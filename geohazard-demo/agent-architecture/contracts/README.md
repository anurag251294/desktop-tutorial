# Contract notes

## Why `citations` keeps `minItems: 1`

Every `citedText` and `finding` must carry at least one evidence ID. That is the whole
point: a quantitative claim with no citation is exactly what this design exists to
prevent.

The cost is that a **no-evidence** request has no representable answer. Asked a question
with no `geohazard-report-input` supplied, the agent produced a structurally valid
document citing `E1`, which did not exist — the schema left it no lawful alternative.

Relaxing `minItems` to 0 would fix the symptom and destroy the guarantee: it would make
an uncited claim legal in every report, not just empty ones.

So the contract is unchanged, and the system prompt instead defines an explicit escape:
with no input document, return `{"error": "no-evidence", ...}` and no report at all. That
object deliberately fails schema validation, which is correct — it is not a report.

Note that schema validation alone would have passed the fabricated document. Only the
citation-resolution check in `scripts/foundry/create_report_agent.py` rejected it. Both
checks are load-bearing; neither is sufficient alone.
