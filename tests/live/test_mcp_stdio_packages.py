"""Opt-in v2 MCP stdio read and public-package preflight against Studionet."""

import json
from pathlib import Path
import sys

import pytest
from mcp import Client, StdioServerParameters


MANIFEST = json.loads((Path(__file__).resolve().parents[2] / "deployments"
                       / "studionet_packages.json").read_text())
ADDRESS = MANIFEST["contract_address"]
JOB_ID = MANIFEST["consensus_review"]["job_id"]
PREFIX = "https://raw.githubusercontent.com/Leokings/deliveryos/"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_agent_host_reads_v2_and_preflights_public_package():
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "deliveryos_agent.mcp_server"],
        env={"DELIVERYOS_CONTRACT_ADDRESS": ADDRESS},
    )
    async with Client(server, raise_exceptions=True) as agent:
        job = await agent.call_tool("deliveryos_get_job", {"job_id": JOB_ID})
        assert job.is_error is False
        assert "DELIVERYOS_PACKAGES_V2" in job.content[0].text
        assert "ACCEPTED" in job.content[0].text
        next_actions = await agent.call_tool("deliveryos_next_actions", {"job_id": JOB_ID})
        assert next_actions.is_error is False
        assert "/?version=v2&job=" + JOB_ID in next_actions.content[0].text
        assert "observer" in next_actions.content[0].text
        package = await agent.call_tool("deliveryos_verify_package", {
            "manifest_url": MANIFEST["manifest_url"],
            "evidence_prefix": PREFIX,
            "criterion_count": 2,
        })
        assert package.is_error is False
        assert MANIFEST["manifest_sha256"] in package.content[0].text
        assert MANIFEST["content_fingerprint"] in package.content[0].text
