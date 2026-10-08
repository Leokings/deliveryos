import pytest
from mcp import Client

from deliveryos_agent import mcp_server


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_mcp_exposes_read_and_signed_write_tools(monkeypatch):
    class FakeService:
        contract_address = "0x" + "a" * 40
        wallet_address = "0x" + "b" * 40

        def get_job(self, job_id):
            return {"job_id": job_id, "status": "SUBMITTED"}

        def evaluate_delivery(self, job_id):
            return {"transaction_hash": "0x" + "c" * 64,
                    "status": "SUBMITTED_TO_NETWORK", "method": "evaluate_delivery"}

    monkeypatch.setattr(mcp_server.DeliveryOSClient, "from_env", lambda: FakeService())
    async with Client(mcp_server.mcp, raise_exceptions=True) as client:
        listing = await client.list_tools()
        names = {tool.name for tool in listing.tools}
        assert {"deliveryos_identity", "deliveryos_get_job",
                "deliveryos_submit_delivery", "deliveryos_evaluate_delivery",
                "deliveryos_transaction_status", "deliveryos_get_job_count",
                "deliveryos_get_job_id"} <= names

        job = await client.call_tool("deliveryos_get_job", {"job_id": "job_12345"})
        assert job.is_error is False
        assert job.content and "SUBMITTED" in job.content[0].text

        write = await client.call_tool("deliveryos_evaluate_delivery", {"job_id": "job_12345"})
        assert write.is_error is False
        assert write.content and "SUBMITTED_TO_NETWORK" in write.content[0].text
