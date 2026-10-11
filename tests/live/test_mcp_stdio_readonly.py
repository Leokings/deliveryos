"""Read-only smoke against the earlier verified Studionet deployment."""

import json
from pathlib import Path
import sys

import pytest
from mcp import Client, StdioServerParameters


MANIFEST = json.loads((Path(__file__).resolve().parents[2] / "deployments" / "studionet.json").read_text())
ADDRESS = MANIFEST["contract_address"]
JOB_ID = MANIFEST["acceptance_test"]["job_id"]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_agent_host_can_read_finalized_job_over_stdio():
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "deliveryos_agent.mcp_server"],
        env={"DELIVERYOS_CONTRACT_ADDRESS": ADDRESS},
    )
    async with Client(server, raise_exceptions=True) as agent:
        identity = await agent.call_tool("deliveryos_identity", {})
        assert identity.is_error is False
        assert ADDRESS in identity.content[0].text
        assert "False" in identity.content[0].text or "false" in identity.content[0].text
        job = await agent.call_tool("deliveryos_get_job", {"job_id": JOB_ID})
        assert job.is_error is False
        assert "ACCEPTED" in job.content[0].text
        assert "CONSENSUS" in job.content[0].text


@pytest.mark.anyio
async def test_v6_agent_reads_finalized_passport_receipt_over_stdio():
    record = json.loads((Path(__file__).resolve().parents[2] /
        "deployments/studionet_packages_v6.json").read_text(encoding="utf-8"))
    server = StdioServerParameters(
        command=sys.executable, args=["-m", "deliveryos_agent.mcp_server"],
        env={"DELIVERYOS_CONTRACT_ADDRESS": record["contract_address"],
             "DELIVERYOS_PASSPORT_ADDRESS": record["provider_passport"]["address"]},
    )
    async with Client(server, raise_exceptions=True) as agent:
        identity = await agent.call_tool("deliveryos_identity", {})
        assert not identity.is_error
        assert record["contract_address"] in identity.content[0].text
        status = await agent.call_tool("deliveryos_passport_receipt_status", {
            "job_id": record["end_to_end_test"]["job_id"],
        })
        assert not status.is_error
        assert record["end_to_end_test"]["receipt"]["receipt_id"] in status.content[0].text
        assert "LATEST_FINAL" in status.content[0].text
        assert '"receipt_recorded":true' in status.content[0].text.replace(" ", "")
