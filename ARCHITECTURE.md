# DeliveryOS v1 architecture

DeliveryOS is an agent-callable delivery lifecycle, not an AI agent or a generic
LLM chat service. Existing buyer and provider agents (or humans) use signed
GenLayer calls to agree on work, submit a versioned deliverable, and obtain a
neutral acceptance decision.

## Boundary

| Layer | Responsibility |
| --- | --- |
| HTTP/MCP adapter | Validate requests, prepare transactions, show status, notify callers; never decide the on-chain verdict. |
| Evidence host | Serve publicly accessible, UTF-8 deliverable bytes. v1 accepts bounded HTTPS text with a declared SHA-256 and length. |
| Intelligent Contract | Freeze the brief and criteria, authorize buyer/provider actions, enforce deadlines and revision limits, retrieve pinned evidence, determine a structured verdict by validator consensus, and persist the result. |
| GenLayer validators | Independently fetch the same bytes and compare ordered per-criterion statuses, not free-form prose. |

User action -> signed job proposal -> seller acceptance -> signed evidence
submission -> independently fetched/hash-checked bytes -> non-deterministic
criterion assessment -> status-vector consensus -> deterministic state change ->
finalized transaction and agent-visible result.

## v1 decision policy

- One job has one buyer, one provider, 1-4 immutable criteria, a due date, and a
  buyer-selected revision allowance (0-2).
- The buyer approves a public GitHub repository prefix before work begins;
  providers can create a future commit after accepting the job.
- Each provider submission creates a new version with immutable URL, exact
  length, and SHA-256. Prior versions remain readable.
- The evidence URL must be a public `raw.githubusercontent.com` file at a full
  40-character commit SHA within the buyer-approved repository/prefix.
- For each criterion the model must return `MET`, `NOT_MET`, or `UNCLEAR`.
  Validators independently compare the ordered status vector. Reasons are
  explanatory and non-authoritative.
- All `MET` -> `ACCEPTED`. Any `NOT_MET` or `UNCLEAR` -> `REVISION` if revisions
  remain, otherwise `REJECTED` or `INCONCLUSIVE` respectively. Evidence or
  model failure leaves the submission pending; it never silently passes.
- A requested revision gets at least three days from the review, even if the
  original due date has passed. Submitting identical bytes is not a revision.
- Either party may initiate review. The buyer may accept a submitted version
  manually. Nobody may approve an unsubmitted job.
- A job with no submission after its due date can be expired. A submitted job
  still pending seven days after the due date can be closed as `INCONCLUSIVE`.
  There is no
  automatic payout or financial reputation in v1.

## Deliberate v1 limits

- Public evidence only. Never submit secrets, private client data, or personal
  information. The content hash proves byte identity, not truth or ownership.
- Text deliverables only (for example JSON, CSV, documentation, copy, or an SVG
  source file). Visual and executable verification need separate adapters and
  evidence policies; a seller's summary of a file is not the file itself.
- No payments or escrow. GEN settlement is a later release after the decision,
  timeout, liveness, and fee paths have been tested on a live GenLayer network.
- This is distinct from the existing `DigitalDeliverableVerifier` contract:
  that project is a reusable single-policy verifier. DeliveryOS adds bilateral
  agreement, delivery versioning, deadlines, revisions, and agent-facing flows.

## Required evidence for a production claim

Direct tests cover authorization, state transitions, and validator comparison
against a dissenting criterion vector or changed bytes. Studionet receipts and
state cover acceptance, revision, rejection, and no-delivery expiry; a
browser-signed job creation has also been exercised. The read API exposes
exact chain, contract, transaction, and evidence digest where relevant. A
controlled full multi-validator disagreement run remains to be done. This is
a public Studionet pilot, not production escrow.
