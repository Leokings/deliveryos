# DeliveryOS

DeliveryOS is a tool that a buyer agent and a provider agent can call to agree
on a digital deliverable, submit a version, and get a GenLayer-backed
acceptance or revision decision. It is **not** an agent, marketplace, payment
system, or escrow. The decision-only contracts are live on Studionet: v1
assesses one text file; v2–v4 assess a package of 1–6 text files. V3 adds
bounded correction and version-bound decisions; v4 makes the review cutoff a
hard on-chain limit for approval and AI review. A browser
workspace and read-only public API live in [`web/`](web/). This is a public
Studionet pilot, not a payments product.

Live site: [deliveryos-tau-wheat.vercel.app](https://deliveryos-tau-wheat.vercel.app/).
Public source: [github.com/Leokings/deliveryos](https://github.com/Leokings/deliveryos).

## First-time flow

First, click **Explore a completed example** on the website. No wallet is
needed to read the accepted job, its public evidence, and its finalized review
transaction. To make your own request, select **Create request**. Enter the
invitee's wallet address, a plain-language task, 1–4 observable completion
points, and a normal public GitHub repository link. The form supplies a job
reference and a due date, both editable. Your wallet signs the request. Send
the resulting job link to the invitee, who opens it, reads the terms, and
accepts using the named wallet. This is a direct invitation, not a job board.

The invitee publishes the finished files and submits their pinned evidence
URL. V4 supports a package of 1–6 files and is the default; the older
versions are under **Change format**. See the package instructions
below before preparing package evidence. The buyer can approve a submission, or
either party can ask GenLayer validators to review it. Wait for
**finalized + successful execution**, then refresh the job. No API key is
needed for public reads; no funds move in any version.

## Evidence packages (v4 current, v3 and v2 legacy)

V4 is a separate contract at
`0x4254924698AA7d4195BC2D734D3b767F6296Ff65` on Studionet chain 61999.
It does not change earlier jobs. V3 remains readable at
`0x89fFB4Ced8C0befa594B470629b3b15827749DbF` on Studionet chain 61999. It does not alter existing
v1 or v2 jobs. V2 remains readable at
`0x6AdA7535b224343D48175930bd4874201B3f8860`. A first-time provider should:

1. Agree to a v4 job with 1–4 objective criteria and a public GitHub repository
   prefix approved by the buyer. Do not publish private client material.
2. Create 1–6 UTF-8 text, Markdown, JSON, or CSV files, each at most 4,800 bytes
   and at most 12,000 bytes together. Commit these files and copy the full
   40-character **source commit** SHA.
3. Use the MCP `deliveryos_build_package_manifest` tool or
   [`build_manifest`](deliveryos_agent/packages.py) with each file's path,
   exact content, media type, and zero-based criterion indexes. Every criterion
   must map to at least one file. Save the returned `manifest_text` exactly,
   including its single final newline. Commit the manifest in a **second**
   commit. It cannot point to its own commit SHA.
4. Submit the raw GitHub URL of that second commit's manifest. The website or
   `deliveryos_verify_package` fetches every pinned source file, checks URL,
   length, UTF-8, SHA-256, format, and mapping, then submits the manifest hash.
5. If a pending v4 manifest was wrong or became unavailable, submit a different
   manifest before the fixed correction cutoff. The earlier version remains
   visible as `SUPERSEDED`, and correcting it does not spend a requested
   revision or postpone the hard review cutoff. The browser
   and MCP connector preflight the new public bytes; the contract re-verifies
   them at decision time.
6. The buyer may accept manually after GenLayer validators independently
   verify the package bytes, or either party can request validator assessment
   of the frozen criteria. The `decision_source` shows `BUYER` versus
   `CONSENSUS`. V4 acceptance and review include the inspected version number;
   a later correction causes a stale signed decision to fail. A revision must
   change at least one source file, not merely edit the manifest metadata.
   At the exact cutoff, a decision is still allowed; after it, neither buyer
   approval nor validator review can execute. Anyone may then call
   `close_unreviewed` to record `INCONCLUSIVE`.

A [real two-file package](examples/package_v2/package.json) and its
[source files](examples/package_v2/source/) show the exact format. Its live
[consensus-reviewed job](https://deliveryos-tau-wheat.vercel.app/?version=v2&job=package_f2131d0cd28244b2)
and receipts are in [deployments/studionet_packages.json](deployments/studionet_packages.json).
The v3 [corrected and consensus-reviewed job](https://deliveryos-tau-wheat.vercel.app/?version=v3&job=package_v3_b3a8798ee6a74d11)
and its deploy, correction and review transactions are recorded in
[deployments/studionet_packages_v3.json](deployments/studionet_packages_v3.json).
The v4 [corrected and consensus-reviewed job](https://deliveryos-tau-wheat.vercel.app/?version=v4&job=package_v4_2d746c70318d4b36)
and its deploy, correction, and review receipts are in
[deployments/studionet_packages_v4.json](deployments/studionet_packages_v4.json).
The content hash proves which bytes were assessed, not that their factual
claims are true or that external work happened.

The v1 lifecycle is available to agents through MCP; v2/v3/v4 use the same signed
methods plus the package tools described above:

1. The buyer and provider each use their own GenLayer wallet. The buyer writes
   a job with a provider address, brief, 1-4 acceptance criteria, public
   GitHub repository prefix, due date, and 0-2 allowed revisions. The buyer
   does **not** need to know the provider's future commit SHA yet.
2. The provider reads the frozen terms and signs `accept_job` (or declines).
3. The provider publishes a UTF-8 text deliverable, at most 4,800 bytes, in a
   public GitHub repository. It must be addressed by a full 40-character
   **commit SHA**, not a moving branch name.
4. The provider's connector fetches the exact file, computes SHA-256 and byte
   length, and signs `submit_delivery`. The contract records a new version.
5. The buyer can explicitly accept that version. Alternatively, either party
   can call `evaluate_delivery`; GenLayer validators independently fetch the
   same hash-pinned bytes and judge each criterion as `MET`, `NOT_MET`, or
   `UNCLEAR`. The contract turns that agreed vector into `ACCEPTED`, `REVISION`,
   `REJECTED`, or `INCONCLUSIVE`. A requested revision gets at least three
   days from the review and must change the evidence bytes.
6. Each write returns a transaction hash. The caller must check
   `deliveryos_transaction_status` until it is **finalized and execution
   successful**, then read the finalized job. Consensus agreement alone is
   not proof the contract executed.

If no deliverable arrives by the due date, anyone can call
`expire_undelivered`. If a submitted version remains unresolved past its
review window, anyone can call `close_unreviewed`; a successful close ends
`INCONCLUSIVE`, never as a silent acceptance. Closure is not automatic. For
v4, approval and validator review are blocked immediately after the cutoff,
even before a close transaction. Older v3 jobs retain their softer rule: a
late decision is possible until somebody closes them.

## Let an AI agent use it

The hosted v1 API exposes finalized reads at `/api/health`, `/api/jobs`,
`/api/jobs/{id}`, `/api/jobs/{id}/submissions/{version}`,
`/api/transactions/{hash}`, and `/api/openapi`. V2 uses `/api/v2/health`,
`/api/v2/jobs`, `/api/v2/jobs/{id}`,
`/api/v2/jobs/{id}/submissions/{version}`,
`/api/v2/packages/preflight`, and `/api/v2/openapi`; transaction status is
shared. V3 and v4 use matching `/api/v3/` and `/api/v4/` endpoints. V4 is the default at
`/openapi.json`. These endpoints are public and
read-only. A write still needs the buyer or provider's own wallet. There is no
hosted custodial signer or API-key-only write pathway in any version.

The bundled [MCP server](deliveryos_agent/mcp_server.py) exposes the lifecycle
as tools to existing agents. It uses the agent owner's wallet **locally** for
signed writes. There is no hosted API key that can magically sign for every
user. An API key could authorize a hosted service, but a write still needs
some wallet to sign it, and a hosted custodial signer would add security and
operating costs that these versions intentionally avoid.

The website now opens on the v4 workflow. A buyer (human or agent) proposes a
job addressed to **one specific provider wallet**. The buyer shares the
version-specific job URL; the provider (human or agent) connects that wallet
and accepts or declines. This is a direct invitation, not a marketplace of
open listings. The new `deliveryos_next_actions` MCP tool reads a job and
suggests the tools available to the configured wallet without signing or
submitting anything. The agent must still check the transaction hash for
finality and execution success, then read the job again. Public API discovery
is also available at `/openapi.json` and `/llms.txt`.

From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
$env:DELIVERYOS_CONTRACT_ADDRESS = "0x4254924698AA7d4195BC2D734D3b767F6296Ff65"
# For legacy v3 packages, use 0x89fFB4Ced8C0befa594B470629b3b15827749DbF.
# For legacy v2 packages, use 0x6AdA7535b224343D48175930bd4874201B3f8860.
# For legacy v1, use 0xef13Bfe9A9B0b4cE7EB4AfC2d8EDd8A6c6D43e40.
# For read-only tools, leave DELIVERYOS_PRIVATE_KEY unset.
# For signed writes, set it only in a trusted local process environment.
$env:DELIVERYOS_PRIVATE_KEY = "<your wallet's private key>"
.\.venv\Scripts\python.exe -m deliveryos_agent.mcp_server
```

Configure your MCP host to launch the absolute path to that Python executable
with `-m deliveryos_agent.mcp_server`; supply the contract address and (only
if writes are needed) wallet key in the host's secure environment settings.
Use one wallet per party. Never commit a key, put it in a public Vercel client
bundle, or hand one shared signing key to unrelated agents. Agent hosts should
require human approval for on-chain write tools.

The Python [client](deliveryos_agent/client.py) is also usable directly. Its
`transaction_status` checks actual execution, and its evidence helper rejects
mutable branch URLs. The MCP transport was tested in memory and through real
stdio subprocesses, including two separate wallets completing an on-chain job;
it has not yet been installed in a third-party agent host.

## Test and audit

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
genvm-lint check contracts/DeliveryOS.py --json
genvm-lint check contracts/DeliveryOSPackages.py --json
genvm-lint check contracts/DeliveryOSPackagesV3.py --json
genvm-lint check contracts/DeliveryOSPackagesV4.py --json
.\.venv\Scripts\python.exe -m pytest tests/direct tests/unit -v
gltest tests/integration -v -s --network studionet
.\.venv\Scripts\python.exe -m pytest tests/live/test_mcp_stdio_readonly.py tests/live/test_studionet_record.py -v
cd web
npm ci
npm test
npm run typecheck
npm run build
npm run test:e2e
```

Direct tests exercise authorization, duplicate IDs, deadlines, evidence
integrity, revisions, rejection, and timeout. Unit tests exercise the client
and MCP tool transport. The integration test deploys to Studionet, uses
independent buyer/provider accounts, submits a public commit-pinned document,
invokes validator review, verifies finalized state, and compares the deployed
source bytes to the repository file. A second live case exercises
`REVISION → REJECTED`; two MCP subprocesses exercised the signed manual path.
The verified v1 address and transaction IDs are in
[deployments/studionet.json](deployments/studionet.json). V2's separate source
hash, deployed address, validator-reviewed acceptance, and buyer acceptance
are in [deployments/studionet_packages.json](deployments/studionet_packages.json).
V3's separate source hash, live correction, unchanged unreviewed-close threshold and
consensus-reviewed acceptance are in
[deployments/studionet_packages_v3.json](deployments/studionet_packages_v3.json).
V4's source hash, live correction and consensus-reviewed acceptance are in
[deployments/studionet_packages_v4.json](deployments/studionet_packages_v4.json).
Five clock-controlled direct tests cover late decision rejection, the exact
cutoff boundary, and overdue closure; a live seven-day-late Studionet
transaction has not yet been observed.
A second live run is not a
substitute for checking the receipt: a network 502 may leave submission
ambiguous, so do not blindly repeat a write.

`tests/live/test_mcp_stdio_write.py` sends a new signed Studionet job each time
it is run; it is intentionally excluded from the default test command.
`tests/live/test_studionet_expiry.py` exercises the live deadline gate and also
sends transactions, so it is opt-in. `web/tests/browser-write.mjs` uses an
ephemeral generated test wallet to create a real on-chain job through the site;
run it explicitly with `npm run test:e2e:live`. Browser tests generate local
screenshots under ignored `web/artifacts/`.

For deployed-site verification, set `BASE_URL` to the live site before running
the browser suites. Set `DELIVERYOS_TEST_VERSION=v1` or `v2` for legacy signed
browser tests (`test:e2e:live`); the default signed test uses v4. The public-site
v2 run on 2026-10-08 passed desktop/mobile,
wallet switching, package preflight, public API, and an actual signed
Studionet job creation (`v2_browser_9f3efa3e8e864342`). Its finalized
transaction and chain-state evidence are in the v2 test record. This does not
prove compatibility with every browser wallet or guarantee AI decisions on
unseen evidence.

The simplified UI revision also passed the public-site browser suite. Its
normal GitHub-link form produced a finalized Studionet proposal through a
local production-style build; the exact transaction and job are in the same
test record. A follow-up public-site write hit Studionet's hourly RPC limit
before returning a transaction hash, so it is **not** counted as a successful
production write for this revision. The interface now gives a plain-language
retry warning; check wallet activity and job state before trying again.

The v3 release passed the public-site browser suite and a fresh wallet-signed
`create_job` through the production site. The v3 job and finalized successful
transaction are in [the v3 test record](deployments/studionet_packages_v3.json).
This verifies the browser's write path for v3, not every wallet extension or
every future Studionet response.

See [ARCHITECTURE.md](ARCHITECTURE.md) for protocol boundaries and explicit
limitations. In particular, SHA-256 proves the bytes examined, not that a
seller's factual claims are true. GenLayer AI judgments can still be
inconsistent or fooled by adversarial content; users should write objective
criteria and review consequential outcomes. There is no production payment
claim in this release.

See [ROADMAP.md](ROADMAP.md) for the next milestones.
