"""DeliveryOS MCP tools for existing buyer/provider agents.

Run with: mcp run deliveryos_agent/mcp_server.py
Set DELIVERYOS_CONTRACT_ADDRESS to the v1, v2, v3 or v4 deployment and, for
writes, DELIVERYOS_PRIVATE_KEY. V2/v3/v4 jobs use public package manifests.
"""

import hashlib

from mcp.server import MCPServer

from deliveryos_agent.client import DeliveryOSClient
from deliveryos_agent.packages import build_manifest, verify_public_package


mcp = MCPServer("DeliveryOS")


def _service() -> DeliveryOSClient:
    return DeliveryOSClient.from_env()


@mcp.tool()
def deliveryos_identity() -> dict:
    """Show the Studionet contract and this connector's signing wallet, if configured."""
    service = _service()
    return {"network": "studionet", "chain_id": 61999,
            "contract_address": service.contract_address,
            "wallet_address": service.wallet_address,
            "can_write": service.wallet_address is not None}


@mcp.tool()
def deliveryos_get_job(job_id: str) -> dict:
    """Read a finalized job, including parties, frozen criteria, deadline, and verdict."""
    return _service().get_job(job_id)


@mcp.tool()
def deliveryos_next_actions(job_id: str) -> dict:
    """Read a job and suggest tools for this configured wallet; never signs automatically."""
    return _service().next_actions(job_id)


@mcp.tool()
def deliveryos_get_submission(job_id: str, version: int) -> dict:
    """Read versioned delivery evidence and its current verdict or superseded status."""
    return _service().get_submission(job_id, version)


@mcp.tool()
def deliveryos_get_job_count() -> int:
    """Read the total number of jobs on this contract."""
    return _service().get_job_count()


@mcp.tool()
def deliveryos_get_job_id(index: int) -> str:
    """Read a public job ID by zero-based index; use get_job_count for the bound."""
    return _service().get_job_id(index)


@mcp.tool()
def deliveryos_transaction_status(transaction_hash: str) -> dict:
    """Check if a signed transaction finalized and actually executed successfully."""
    return _service().transaction_status(transaction_hash)


@mcp.tool()
def deliveryos_create_job(job_id: str, provider: str, brief: str, criteria: list[str],
                          evidence_prefix: str, due_epoch: int, max_revisions: int = 1) -> dict:
    """Buyer: propose frozen work terms on Studionet. This sends a signed transaction."""
    return _service().create_job(job_id, provider, brief, criteria,
                                 evidence_prefix, due_epoch, max_revisions)


@mcp.tool()
def deliveryos_accept_job(job_id: str) -> dict:
    """Provider: accept an open job proposal with this agent's wallet."""
    return _service().accept_job(job_id)


@mcp.tool()
def deliveryos_decline_job(job_id: str) -> dict:
    """Provider: decline an open proposal; irreversible for that job ID."""
    return _service().decline_job(job_id)


@mcp.tool()
def deliveryos_cancel_proposal(job_id: str) -> dict:
    """Buyer: cancel a proposal before provider acceptance."""
    return _service().cancel_proposal(job_id)


@mcp.tool()
def deliveryos_submit_delivery(job_id: str, evidence_url: str) -> dict:
    """Provider: preflight and submit evidence; v3/v4 can correct a pending package."""
    return _service().submit_delivery(job_id, evidence_url)


@mcp.tool()
def deliveryos_build_package_manifest(evidence_prefix: str, source_commit: str,
                                      files: list[dict], criterion_count: int) -> dict:
    """Prepare exact v2/v3/v4 manifest bytes after committing 1-6 public source files.

    Each file requires path, UTF-8 content, media_type, and zero-based criteria.
    Save manifest_text exactly (with its final newline), commit it separately,
    and submit its commit-pinned raw GitHub URL. This does not publish files.
    """
    specs = []
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "content", "media_type", "criteria"}:
            raise ValueError("Each file needs path, content, media_type, and criteria")
        specs.append({"path": item["path"], "body": item["content"],
                      "media_type": item["media_type"], "criteria": item["criteria"]})
    manifest = build_manifest(evidence_prefix, source_commit, specs, criterion_count)
    return {"manifest_text": manifest.decode("utf-8"),
            "sha256": hashlib.sha256(manifest).hexdigest(),
            "size_bytes": len(manifest),
            "next_step": "Save the exact manifest text, commit it, then submit that commit-pinned raw URL."}


@mcp.tool()
def deliveryos_verify_package(manifest_url: str, evidence_prefix: str,
                              criterion_count: int) -> dict:
    """Preflight a public v2/v3/v4 manifest and every referenced file, without signing."""
    return verify_public_package(manifest_url, evidence_prefix, criterion_count)


@mcp.tool()
def deliveryos_accept_delivery(job_id: str, expected_version: int | None = None) -> dict:
    """Buyer: accept inspected evidence. V3/V4 require current_version; v4 also enforces a hard review cutoff."""
    return _service().accept_delivery(job_id, expected_version) if expected_version is not None else _service().accept_delivery(job_id)


@mcp.tool()
def deliveryos_evaluate_delivery(job_id: str, expected_version: int | None = None) -> dict:
    """Either party: request validator review. V3/V4 require the inspected current_version; v4 has a hard cutoff."""
    return _service().evaluate_delivery(job_id, expected_version) if expected_version is not None else _service().evaluate_delivery(job_id)


@mcp.tool()
def deliveryos_expire_undelivered(job_id: str) -> dict:
    """Anyone: close a job that has no delivery after its deadline."""
    return _service().expire_undelivered(job_id)


@mcp.tool()
def deliveryos_close_unreviewed(job_id: str) -> dict:
    """Anyone: close a still-unreviewed delivery after its seven-day grace period; v4 also blocks late decisions."""
    return _service().close_unreviewed(job_id)


if __name__ == "__main__":
    mcp.run()
