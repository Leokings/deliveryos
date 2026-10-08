# DeliveryOS v1/v2/v3 architecture

DeliveryOS is an agent-callable delivery lifecycle, not an AI agent or a generic
LLM chat service. Existing buyer and provider agents (or humans) use signed
GenLayer calls to agree on work, submit a versioned deliverable, and obtain a
neutral acceptance decision.

## Boundary

| Layer | Responsibility |
| --- | --- |
| HTTP/MCP adapter | Validate requests, prepare transactions, show status, notify callers; never decide the on-chain verdict. |
| Evidence host | Serve publicly accessible, UTF-8 deliverable bytes. V1 accepts one bounded file; v2/v3 accept a canonical manifest with 1–6 bounded source files. |
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

## V2 package boundary

V2 is deployed as a **separate** `DeliveryOSPackages.py` contract. It retains
the bilateral lifecycle but changes the submitted object from one document to
a canonical manifest. The manifest is committed after its source files so it
can refer to their full source-commit SHA without a self-referential hash.
It lists exact URLs, hashes, lengths, media types, and zero-based criterion
mappings. Validators fetch the manifest and every mapped file from the frozen
repository prefix, verify all declared bytes, and compare the same structured
status vector **plus** the content fingerprint, file count, and byte total.
Manual buyer acceptance still requires validator-side byte verification, but
is explicitly recorded as a `BUYER` decision rather than AI consensus.

The manifest and each file are capped at 4,800 bytes; the source files total
at most 12,000 bytes. Supported interpretation is UTF-8 text, Markdown, JSON,
and CSV—not executable code, images, or private content. A revision must change
the file-hash set. The package preflight API and MCP tool are conveniences;
their result never replaces on-chain validator retrieval. Finalized successful
execution and the resulting chain state, not a proposed transaction hash, are
the evidence of a completed decision.

## V3 pending-evidence recovery

V3 is a separate contract that retains the v2 package format. A provider may
submit a different manifest while a version is `SUBMITTED`; the old record is
marked `SUPERSEDED` but keeps its URL and hash. The correction does not use a
revision allowance. The first submission in each review cycle freezes
`review_deadline_epoch`, so repeated corrections cannot indefinitely delay
`close_unreviewed`. The date ends the correction window and makes unreviewed
closure available; it does not close the job automatically. Until someone
successfully calls `close_unreviewed`, the buyer can still accept or either
party can request validator review. A successful close records `INCONCLUSIVE`.
`last_reviewed_fingerprint` tracks the last
assessed file set, so a requested revision cannot be disguised by a sequence
of metadata-only corrections. Both `accept_delivery` and `evaluate_delivery`
require an expected version: if a correction finalized before the decision,
the stale transaction fails instead of acting on unseen evidence.

## Required evidence for a production claim

Direct tests cover authorization, state transitions, and validator comparison
against a dissenting criterion vector or changed bytes. Studionet receipts and
state cover acceptance, revision, rejection, and no-delivery expiry; a
browser-signed job creation has also been exercised. The read API exposes
exact chain, contract, transaction, and evidence digest where relevant. A
controlled full multi-validator disagreement run remains to be done. This is
a public Studionet pilot, not production escrow.
