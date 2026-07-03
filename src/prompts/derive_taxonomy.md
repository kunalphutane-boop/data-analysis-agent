You are deriving a fixed, reusable Intent taxonomy for a call-center analytics job.
You are given a SAMPLE of customer-call transcripts (agent/customer turns). Your job is
to produce a small, stable list of intent categories that every call in the full dataset
will later be classified into.

This defaults to a lending / retail-banking call center. Unless a BUSINESS CONTEXT
section is provided below, start from this expected base set and keep every one of these
categories (they are the canonical fallback):
- Loan enquiry
- EMI/Payment
- Account balance/Statement
- Verification/Registration
- Branch/Timing
- Complaint/Escalation
- Other/Unclear

## If a BUSINESS CONTEXT section is provided
The user has authored a free-text description of their business (appended at the very end
of this prompt). When it is present, TAILOR the taxonomy to THAT domain — derive intent
labels that reflect the user's own operation and terminology, not the generic defaults.
For example, a lending NBFC servicing call center would yield intents such as
`Loan enquiry`, `EMI/Payment`, `KYC/Verification`, `Disbursement delay`,
`Foreclosure/Prepayment`, `Collections/Overdue`, `Complaint/Escalation`. Do NOT force the
generic base categories above when a business context is present; use domain-fit labels.

Rules:
- Return a FIXED list of short intent labels. Keep it stable and small (7-12 labels).
- With NO business context, include ALL seven base categories above, spelled EXACTLY as written.
- With a business context, derive labels that fit that domain (a few extra domain labels are
  encouraged); keep them short, reusable buckets — not per-call or overly-specific labels.
- Do NOT invent per-call or overly-specific labels. These are buckets for thousands of calls.
- `Other/Unclear` is the catch-all; keep it last.

Respond with ONLY a JSON array of strings, no prose and no markdown fences. Example:
["Loan enquiry", "EMI/Payment", "Account balance/Statement", "Verification/Registration", "Branch/Timing", "Complaint/Escalation", "Other/Unclear"]
