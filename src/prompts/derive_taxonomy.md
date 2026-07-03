You are deriving a fixed, reusable Intent taxonomy for a call-center analytics job.
You are given a SAMPLE of customer-call transcripts (agent/customer turns). Your job is
to produce a small, stable list of intent categories that every call in the full dataset
will later be classified into.

This is a lending / retail-banking call center. Start from this expected base set and
keep every one of these categories (they are the canonical fallback):
- Loan enquiry
- EMI/Payment
- Account balance/Statement
- Verification/Registration
- Branch/Timing
- Complaint/Escalation
- Other/Unclear

Rules:
- Return a FIXED list of short intent labels. Keep it stable and small (7-12 labels).
- Always include ALL seven base categories above, spelled EXACTLY as written.
- You MAY add at most a few extra categories ONLY if the sample clearly shows a
  recurring intent that none of the base categories cover. Prefer reusing the base set.
- Do NOT invent per-call or overly-specific labels. These are buckets for thousands of calls.
- `Other/Unclear` is the catch-all; keep it last.

Respond with ONLY a JSON array of strings, no prose and no markdown fences. Example:
["Loan enquiry", "EMI/Payment", "Account balance/Statement", "Verification/Registration", "Branch/Timing", "Complaint/Escalation", "Other/Unclear"]
