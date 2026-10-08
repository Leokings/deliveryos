"""DeliveryOS MCP tools for existing buyer/provider agents.

Run with: mcp run deliveryos_agent/mcp_server.py
Set DELIVERYOS_CONTRACT_ADDRESS and, for writes, DELIVERYOS_PRIVATE_KEY.
"""

from mcp.server import MCPServer

from deliveryos_agent.client import DeliveryOSClient


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
def deliveryos_get_submission(job_id: str, version: int) -> dict:
    """Read a finalized immutable delivery version and its content digest."""
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
    """Provider: fetch and hash a public commit-pinned UTF-8 file, then submit it."""
    return _service().submit_delivery(job_id, evidence_url)


@mcp.tool()
def deliveryos_accept_delivery(job_id: str) -> dict:
    """Buyer: manually accept the pending version without an AI review."""
    return _service().accept_delivery(job_id)


@mcp.tool()
def deliveryos_evaluate_delivery(job_id: str) -> dict:
    """Either party: ask GenLayer validators to compare pinned evidence to criteria."""
    return _service().evaluate_delivery(job_id)


@mcp.tool()
def deliveryos_expire_undelivered(job_id: str) -> dict:
    """Anyone: close a job that has no delivery after its deadline."""
    return _service().expire_undelivered(job_id)


@mcp.tool()
def deliveryos_close_unreviewed(job_id: str) -> dict:
    """Anyone: close a still-unreviewed delivery after its seven-day grace period."""
    return _service().close_unreviewed(job_id)


if __name__ == "__main__":
    mcp.run()
