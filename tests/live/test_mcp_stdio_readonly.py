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
