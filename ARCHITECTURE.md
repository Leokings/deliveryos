# DeliveryOS v1–v6 architecture

DeliveryOS is an agent-callable delivery lifecycle, not an AI agent or a generic
LLM chat service. Existing buyer and provider agents (or humans) use signed
GenLayer calls to agree on work, submit a versioned deliverable, and obtain a
neutral acceptance decision.

## Boundary

| Layer | Responsibility |
| --- | --- |
| HTTP/MCP adapter | Validate requests, prepare transactions, show status, notify callers; never decide the on-chain verdict. |
| Evidence host | Serve publicly accessible, UTF-8 deliverable bytes. V1 accepts one bounded file; v2–v6 accept a canonical manifest with 1–6 bounded source files. |
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

## V4 hard decision cutoff

V4 is another immutable contract with the same package and correction rules.
Before executing either `accept_delivery` or `evaluate_delivery`, it checks
the fixed `review_deadline_epoch` against the chain clock. The decision is
allowed through the exact deadline and reverts afterward. Pending corrections
already obey the same cutoff. Once the cutoff passes, any wallet may record
`INCONCLUSIVE` with `close_unreviewed`; there is no automatic cron or timeout
transaction. The v3 contract and its existing jobs retain the prior policy.
Direct tests exercise both decision methods on and after the boundary; the
live Studionet evidence covers deployment and the normal consensus path, not
a seven-day-late transaction.

## V5 Provider Passport (deployed on Studionet)

V5 is a separately deployed copy of the V4 lifecycle. It first checks the
Passport's pinned source by a synchronous cross-contract view before opening
each new job. Its new outcome callback is emitted with `on="finalized"` after
`evaluate_delivery` reaches a terminal consensus verdict. `REVISION` remains
intermediate and emits nothing; buyer approvals, expiry, and unreviewed
timeouts also emit nothing.
This is important because a source result that is merely accepted could still
be appealed and must not become a permanent reputation receipt.

The companion `DeliveryOSProviderPassport` contract permits the V5 address to
be configured exactly once by its deployer/owner. Thereafter, only that address
can append receipts. Each record carries chain ID, source address, job/version,
buyer/provider, terminal verdict, criterion vector, evidence fingerprint,
decision time, and a deterministic receipt ID. A duplicate identical callback
is idempotent; a conflicting record for the same job/version is rejected.
Wallet owners can update only their own profile. Profile text and capability
tags are explicitly self-reported; the contract does not produce a composite
trust score or make a truth/quality guarantee.

The V5 source constructor pins its Passport address; the Passport is deployed
first, then V5, then the Passport's one-time source binding is set to that V5
address. The final binding is a deployment trust root and must be verified
before V5 jobs are opened. V1-v4 deployments cannot generate the callback, so
their existing records cannot be backfilled as finalized Passport receipts.
V5 MCP tools, a read-only `/passport` page, and `/api/passport` lookup are live.
The existing request workflow and lifecycle API remain on V4; V5 job operations
are available through MCP, not a hosted V5 lifecycle REST API. The canonical
StudioNet addresses and deployment/test receipts are recorded in
`deployments/studionet_packages_v5.json`. A full live test finalized a V5
consensus decision and the resulting Passport receipt was read through both
the Vercel API and Python agent client. This verifies the happy-path callback;
it does not establish production-grade reliability or a controlled live
validator-disagreement result.

## V6 recoverable outcome dispatch

V6 preserves the frozen source result and adds `sync_passport_receipt` for
the two parties only. It checks the expected version, terminal CONSENSUS
decision, one-time companion binding, existing job/version receipt, and a
120-second dispatch cooldown. Missing receipts are re-emitted only with the
stored payload, on source finalization. No model, evidence fetch, or new
decision runs. Companion idempotence handles two callbacks in flight; a
recorded receipt makes subsequent sync calls no-ops.

Dispatch success and child execution success are separate. The new companion
adds a job/version lookup that returns an empty object when absent. MCP reads
both contracts at LATEST_FINAL and refuses mismatched configuration. The
public HTTP lookup preserves V5 alongside V6, with registry metadata kept
outside immutable receipt objects so content-derived receipt IDs remain
verifiable. It reads a bounded recent window, not an unbounded full-history
scan. Old immutable V5 jobs cannot gain the new source retry method.

## Required evidence for a production claim

Direct tests cover authorization, state transitions, and validator comparison
against a dissenting criterion vector or changed bytes. Studionet receipts and
state cover acceptance, revision, rejection, and no-delivery expiry; a
browser-signed job creation has also been exercised. The read API exposes
exact chain, contract, transaction, and evidence digest where relevant. A
controlled full multi-validator disagreement run remains to be done. This is
a public Studionet pilot, not production escrow.
