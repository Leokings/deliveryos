# Try Provider Passport for the first time

DeliveryOS helps two wallets agree to public digital work and obtain an
auditable acceptance decision. This milestone adds wallet-owned profiles,
finalized consensus outcome receipts, and recovery when a receipt callback
fails. It is a decision-only Studionet pilot, not a marketplace or payment app.

## Start without a wallet or API key

1. Open [Provider Passport](https://deliveryos-tau-wheat.vercel.app/passport)
   in a fresh browser. There is no account or connection requirement.
2. Paste this public test provider wallet:
   `0x1563915e194d8cfba1943570603f7606a3115508`, then select **Look up**.
3. Read its profile and accepted work outcome. Profile tags and bio are
   self-reported. The outcome is different: it comes from the configured
   DeliveryOS V6 contract after a terminal validator decision finalized.
4. Check the job ID, version, MET/MET criterion vector, fingerprint, receipt
   ID, and source contract. The
   [public API response](https://deliveryos-tau-wheat.vercel.app/api/passport?wallet=0x1563915e194d8cfba1943570603f7606a3115508)
   exposes the complete fields and both registry addresses.
5. To check preservation of earlier work, look up
   `0xa7D72Fbbe2B148187512A0534Aef62A11f92faFE`. Its existing V5 receipt is
   still visible. V5 receipts were not rewritten or falsely migrated to V6.

For the original browser job workflow, open the
[homepage](https://deliveryos-tau-wheat.vercel.app/) and select **Explore a
completed example**. That workflow remains V4. V6 job actions and receipt
recovery are currently MCP tools, not buttons in the browser job workspace.

## Let your existing agent use V6

Clone the public repository and follow the environment/setup commands in
[README](../README.md#let-an-ai-agent-use-it). Configure:

```text
DELIVERYOS_CONTRACT_ADDRESS=0x1eA0dfc62647353aFf10657B5eD0319cC0Eb5D7E
DELIVERYOS_PASSPORT_ADDRESS=0x821070E1254bB22e23DC80D06a5b6E6C198b0176
```

Launch `python -m deliveryos_agent.mcp_server` from an existing trusted MCP
host. Do not send a private key to the website or to a chat. Leave
`DELIVERYOS_PRIVATE_KEY` unset for public reads. For writes, use a dedicated
Studionet test wallet in the agent host's secure local environment, one
separate wallet per party. Never use the repository's public test keys for
real funds.

1. Call `deliveryos_identity` to confirm the configured source and companion.
2. Call `deliveryos_passport_receipt_status` with job ID
   `passport_v6_845cb6367fe3`. Expect `receipt_recorded=true` and
   `read_finality=LATEST_FINAL`, with the same receipt shown by the website.
3. For a new job, the buyer calls `deliveryos_create_job` with one provider
   wallet, a brief, 1–4 observable criteria, a public GitHub repository prefix,
   due epoch, and revision limit. Check each returned transaction until
   `finalized_success=true`; do not assume a submitted hash is success.
4. The named provider reads and accepts the terms with its own wallet, then
   publishes commit-pinned evidence. Use `deliveryos_build_package_manifest`
   and `deliveryos_verify_package` to prepare and verify 1–6 bounded public
   text/Markdown/JSON/CSV files. The manifest must be committed after the
   source files. Never publish private client material.
5. The provider calls `deliveryos_submit_delivery`. Either party can call
   `deliveryos_evaluate_delivery`, passing the inspected current version.
   After finalization, read the job and then the Passport receipt. A manual
   buyer approval or timeout does not create a consensus receipt.
6. If a terminal consensus job has no finalized receipt, wait until the
   reported `next_retry_epoch`, then either job party may call
   `deliveryos_sync_passport_receipt(job_id, expected_version)`. Check its
   transaction and the companion again. Recovery resends the stored outcome;
   it does not rerun AI or let the caller alter the verdict.

## Inspect the evidence

The [V6 deployment/test record](../deployments/studionet_packages_v6.json)
includes deployment hashes, binding, normal source and child transactions,
receipt IDs, source-code hashes, and the controlled failure/recovery run.
The [audit report](audit-2026-10-11.md) separates local tests, live consensus,
browser/API verification, infrastructure interruptions, and remaining limits.

The failure fixture is separate from the website's real Passport. Its first
callback deliberately failed; recovery then recorded the unchanged result.
It demonstrates that recovery path, not that every possible network outage or
adversarial AI judgment has been solved. There are no payments or guarantees
of factual truth, quality, identity, or model correctness.
