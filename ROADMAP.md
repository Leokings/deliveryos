# DeliveryOS roadmap

## Current: public Studionet pilot

Decisions-first protocol, public text evidence, bilateral wallet permissions,
revision/deadline handling, a browser workspace, read-only HTTP/OpenAPI, and a
local per-party MCP connector. V2 adds canonical, public multi-file evidence
packages; v3 adds bounded pending-evidence correction and version-bound
decisions; v4 enforces a hard on-chain decision cutoff. All versions remain decision-only. No escrow,
payments, private evidence, or production-grade guarantee. Read the
[v1 test record](deployments/studionet.json) and
[v2 test record](deployments/studionet_packages.json) before making a stronger claim.
V3 evidence is in [its separate test record](deployments/studionet_packages_v3.json).
V4 evidence is in [its separate test record](deployments/studionet_packages_v4.json).

## Built in v2: evidence packages for agent work

V1 assesses one UTF-8 file of at most 4,800 bytes. V2 supports a canonical
public manifest listing up to six commit-pinned text/Markdown/JSON/CSV files,
their SHA-256 hashes, media types, byte lengths, and criterion mappings. It is
a new contract version, not a silent change to v1. It does **not** yet inspect
images, execute source trees, or verify off-chain claims.

Acceptance gates:

1. Threat-model URL fetches, manifest traversal, file-count/size limits,
   ambiguous encodings, and validator disagreement.
2. Test both honest and adversarial manifests in direct mode and Studionet.
   A controlled live multi-validator disagreement test remains open.
3. Keep every verdict linked to exact public bytes, chain, contract, and
   finalized transaction; expose the links to browser and agent users.
4. Pilot it with two independent third-party agent hosts and real human
   approval of writes; bundled MCP tool tests alone do not satisfy this gate.

## After that: private evidence, then escrow

Private evidence needs a new trust/privacy design; current validators cannot
independently inspect secret bytes without one. Payments require a separate
escrow contract, explicit release/appeal rules, fee and liveness modeling,
security review, and live network tests. Do not connect automatic payouts to
v1's `ACCEPTED` field.
