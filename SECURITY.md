# DeliveryOS v1/v2 security boundary

This is a non-custodial, decision-only Studionet release. Do not connect
payments to its status field without a separate escrow design and review.

- Buyer, provider, brief, criteria, deadlines, versions, and evidence links are
  public. Do not put secrets or personal client material in them.
- Provider writes require the provider wallet; buyer writes require the buyer
  wallet. `accept_delivery` is explicitly marked `decision_source=BUYER` and
  must not be represented as a validator judgment.
- A provider cannot change an earlier version's URL, length, or SHA-256.
  Validators independently retrieve the bytes at a fixed GitHub raw host and
  reject missing or changed bytes. This proves byte identity only, not truth,
  authorship, licensing, safety, or completion of an external action.
- External deliverable text is serialized as an untrusted JSON field in the
  model prompt. This reduces delimiter/role spoofing; it is not a proof against
  prompt injection or model error. Validators compare structured per-criterion
  statuses, but human review remains appropriate for consequential work.
- A pending review never becomes accepted by timeout. After the grace window,
  anyone can close it `INCONCLUSIVE`. Revisions cannot reuse identical bytes
  and get at least three days when requested after the original due date.
- The agent connector never puts a wallet key in an on-chain call or tool
  response. It expects a per-party key in a trusted local environment. MCP
  host approval for state-changing tools is recommended. A public API key is
  not a substitute for transaction signing.
- The hosted Vercel API is read-only and uses no signing key. Browser writes
  use a selected EIP-1193 wallet; they must verify Studionet chain 61999 and
  retain the returned transaction hash. The UI must not treat `FINALIZED` alone
  as success: it also checks consensus and leader execution.
- The evidence preflight endpoint accepts only `raw.githubusercontent.com`
  full-commit URLs, rejects redirects, caps fetched bytes at 4,800, and never
  executes evidence content. It is a convenience check, not proof of factual
  truth or a substitute for validator retrieval.
- V2's package preflight and contract additionally require canonical manifest
  JSON, one full source-commit SHA shared by every file, exact byte lengths and
  SHA-256 values, bounded file count and total size, unique file URLs/bytes,
  and coverage of every criterion. The manifest itself uses a later commit.
  The server fetches only allowlisted GitHub raw URLs without redirects or
  running file content. Revisions cannot recycle an unchanged file-hash set.
- V2's manual buyer acceptance verifies the package bytes through validators
  before recording the buyer's decision. This confirms byte identity, **not**
  the buyer's factual claims or a neutral AI verdict. Consumers must inspect
  `decision_source` and should not treat buyer acceptance as consensus.
- Only `raw.githubusercontent.com` and full commit-SHA evidence URLs are
  accepted. The buyer approves the repository prefix. The agent connector
  refuses redirects; GenLayer validators check the final fetched byte hash.

Known limits: there is no escrow, automated evidence authenticity check,
private evidence, image/video interpretation, app-level appeal flow, audited
wallet custody, or security guarantee against all adversarial deliverables.
V2 package checks do not prove authorship or external completion. Browser and
agent preflight may reject some unusual CSV accepted by Python's parser; use
plain, conventional CSV or text/JSON. A controlled adversarial multi-validator
disagreement run remains unverified; the available test evidence must not be
presented as a guarantee of model correctness.
The current test suite includes local state-machine/connector tests and live
Studionet acceptance, revision/rejection, two-agent MCP manual acceptance,
browser-signed job creation, and early/late no-delivery expiry paths. A direct
validator test rejects disagreement and changed bytes; deliberately forcing a
multi-validator disagreement on a live network remains unverified. The project
does not claim production-grade escrow or universal model correctness.
