# DeliveryOS

DeliveryOS is a tool that a buyer agent and a provider agent can call to agree
on a digital deliverable, submit a version, and get a GenLayer-backed
acceptance or revision decision. It is **not** an agent, marketplace, payment
system, or escrow. Version 1 makes decisions first; funds are out of scope.
The contract is live on Studionet. A browser workspace and read-only public API
live in [`web/`](web/). This is a public Studionet pilot, not a payments product.

## First-time flow

On the website, choose **Start a job** and connect the buyer wallet. Set a
provider wallet, brief, 1–4 objective criteria, public repository prefix, due
date, and revision allowance. The provider then opens the job ID, connects
their own wallet, and accepts. After publishing a UTF-8 file at a full GitHub
commit SHA, the provider enters its raw URL and clicks **Submit this version**.
The site independently checks the file's SHA-256 and byte length before the
wallet signs. Finally, the buyer accepts or either party requests validator
review. Wait for **finalized + successful execution**, then refresh the job.
No API key is needed for public reads; no funds move in this version.

The same lifecycle is available to agents through MCP:

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
`expire_undelivered`. If a submitted version remains unresolved seven days
past its due date, anyone can call `close_unreviewed`; this ends
`INCONCLUSIVE`, never as a silent acceptance.

## Let an AI agent use it

The hosted API exposes finalized reads at `/api/health`, `/api/jobs`,
`/api/jobs/{id}`, `/api/jobs/{id}/submissions/{version}`,
`/api/transactions/{hash}`, and `/api/openapi`. These endpoints are public and
read-only. A write still needs the buyer or provider's own wallet. There is no
hosted custodial signer or API-key-only write pathway in v1.

The bundled [MCP server](deliveryos_agent/mcp_server.py) exposes the lifecycle
as tools to existing agents. It uses the agent owner's wallet **locally** for
signed writes. There is no hosted API key that can magically sign for every
user. An API key could authorize a hosted service, but a write still needs
some wallet to sign it, and a hosted custodial signer would add security and
operating costs that v1 intentionally avoids.

From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
$env:DELIVERYOS_CONTRACT_ADDRESS = "0xef13Bfe9A9B0b4cE7EB4AfC2d8EDd8A6c6D43e40"
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
The verified address and transaction IDs are in
[deployments/studionet.json](deployments/studionet.json). A second live run is not a
substitute for checking the receipt: a network 502 may leave submission
ambiguous, so do not blindly repeat a write.

`tests/live/test_mcp_stdio_write.py` sends a new signed Studionet job each time
it is run; it is intentionally excluded from the default test command.
`tests/live/test_studionet_expiry.py` exercises the live deadline gate and also
sends transactions, so it is opt-in. `web/tests/browser-write.mjs` uses an
ephemeral generated test wallet to create a real on-chain job through the site;
run it explicitly with `npm run test:e2e:live`. Browser tests generate local
screenshots under ignored `web/artifacts/`.

See [ARCHITECTURE.md](ARCHITECTURE.md) for protocol boundaries and explicit
limitations. In particular, SHA-256 proves the bytes examined, not that a
seller's factual claims are true. GenLayer AI judgments can still be
inconsistent or fooled by adversarial content; users should write objective
criteria and review consequential outcomes. There is no production payment
claim in this release.

See [ROADMAP.md](ROADMAP.md) for the next milestones.
