# DeliveryOS roadmap

## Current: public Studionet pilot

Decisions-first protocol, public text evidence, bilateral wallet permissions,
revision/deadline handling, a browser workspace, read-only HTTP/OpenAPI, and a
local per-party MCP connector. No escrow, payments, private evidence, or
production-grade guarantee. Read the [test record](deployments/studionet.json)
before making any stronger claim.

## Next build: evidence packages for agent work

The present contract assesses one UTF-8 file of at most 4,800 bytes. Real
agent deliveries often contain several artifacts. The next release should
support a canonical public manifest that lists commit-pinned files, their
SHA-256 hashes, media types, byte lengths, and criterion-to-file mappings.
Adapters can then inspect deterministic facts in documents, CSV/JSON, source
trees, and image metadata before GenLayer judges the narrow semantic question.
This is a new contract version, not a silent change to the deployed v1 address.

Acceptance gates:

1. Threat-model URL fetches, manifest traversal, file-count/size limits,
   ambiguous encodings, and validator disagreement.
2. Test both honest and adversarial manifests in direct mode, a controlled
   multi-validator environment, and Studionet.
3. Keep every verdict linked to exact public bytes, chain, contract, and
   finalized transaction; expose the links to browser and agent users.
4. Pilot it with two independent agent hosts and real human approval of writes.

## After that: private evidence, then escrow

Private evidence needs a new trust/privacy design; current validators cannot
independently inspect secret bytes without one. Payments require a separate
escrow contract, explicit release/appeal rules, fee and liveness modeling,
security review, and live network tests. Do not connect automatic payouts to
v1's `ACCEPTED` field.
