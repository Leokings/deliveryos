"""Two separate MCP agent processes exercise the signed manual path."""

import ast
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import uuid

import anyio
from mcp import Client, StdioServerParameters
import pytest


ROOT = Path(__file__).resolve().parents[2]
RECORD = json.loads((ROOT / "deployments" / "studionet.json").read_text(encoding="utf-8"))
ADDRESS = RECORD["contract_address"]
FIXTURE = RECORD["acceptance_test"]
PREFIX = "https://raw.githubusercontent.com/Leokings/digital-deliverable-verifier/"
BUYER_KEY = "0x" + "11" * 32  # public test-only keys, never fund
PROVIDER_KEY = "0x" + "22" * 32
PROVIDER_ADDRESS = "0x1563915e194D8CfBA1943570603F7606A3115508"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _result(result):
    assert result.is_error is False, result
    if result.structured_content is not None:
        return result.structured_content
    raw = result.content[0].text
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return ast.literal_eval(raw)


async def _tool(client, name, args):
    return _result(await client.call_tool(name, args))


async def _finalized(client, tx_hash):
    for _ in range(90):
        try:
            receipt = await _tool(client, "deliveryos_transaction_status", {
                "transaction_hash": tx_hash,
            })
        except Exception:
            await anyio.sleep(3)
            continue
        if receipt["status"] == "FINALIZED":
            assert receipt["finalized_success"] is True, receipt
            return
        await anyio.sleep(3)
    raise AssertionError(f"Transaction did not finalize: {tx_hash}")


@pytest.mark.anyio
@pytest.mark.integration
async def test_two_mcp_agents_complete_manual_delivery():
    buyer_server = StdioServerParameters(
        command=sys.executable, args=["-m", "deliveryos_agent.mcp_server"],
        env={"DELIVERYOS_CONTRACT_ADDRESS": ADDRESS, "DELIVERYOS_PRIVATE_KEY": BUYER_KEY},
    )
    provider_server = StdioServerParameters(
        command=sys.executable, args=["-m", "deliveryos_agent.mcp_server"],
        env={"DELIVERYOS_CONTRACT_ADDRESS": ADDRESS, "DELIVERYOS_PRIVATE_KEY": PROVIDER_KEY},
    )
    job_id = "agent_" + uuid.uuid4().hex[:18]
    print("DELIVERYOS_AGENT_JOB=" + job_id, flush=True)
    receipts = {}
    async with Client(buyer_server, raise_exceptions=True) as buyer:
        async with Client(provider_server, raise_exceptions=True) as provider:
            due = int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp())
            proposal = await _tool(buyer, "deliveryos_create_job", {
                "job_id": job_id,
                "provider": PROVIDER_ADDRESS,
                "brief": "Deliver the public Digital Deliverable Verifier installation guide with its actual install command.",
                "criteria": ["The guide explicitly includes the command python -m pip install -r requirements.txt."],
                "evidence_prefix": PREFIX,
                "due_epoch": due,
                "max_revisions": 1,
            })
            receipts["propose"] = proposal["transaction_hash"]
            print("DELIVERYOS_AGENT_TX=" + json.dumps({"step": "propose", "hash": receipts["propose"]}), flush=True)
            await _finalized(buyer, receipts["propose"])

            accepted = await _tool(provider, "deliveryos_accept_job", {"job_id": job_id})
            receipts["accept_job"] = accepted["transaction_hash"]
            print("DELIVERYOS_AGENT_TX=" + json.dumps({"step": "accept_job", "hash": receipts["accept_job"]}), flush=True)
            await _finalized(provider, receipts["accept_job"])

            submitted = await _tool(provider, "deliveryos_submit_delivery", {
                "job_id": job_id, "evidence_url": FIXTURE["evidence_url"],
            })
            assert submitted["evidence"]["sha256"] == FIXTURE["evidence_sha256"]
            receipts["submit"] = submitted["transaction_hash"]
            print("DELIVERYOS_AGENT_TX=" + json.dumps({"step": "submit", "hash": receipts["submit"]}), flush=True)
            await _finalized(provider, receipts["submit"])

            manual = await _tool(buyer, "deliveryos_accept_delivery", {"job_id": job_id})
            receipts["accept_delivery"] = manual["transaction_hash"]
            print("DELIVERYOS_AGENT_TX=" + json.dumps({"step": "accept_delivery", "hash": receipts["accept_delivery"]}), flush=True)
            await _finalized(buyer, receipts["accept_delivery"])

            job = await _tool(buyer, "deliveryos_get_job", {"job_id": job_id})
            version = await _tool(provider, "deliveryos_get_submission", {"job_id": job_id, "version": 1})
            assert job["status"] == "ACCEPTED", job
            assert job["decision_source"] == "BUYER", job
            assert version["verdict"] == "ACCEPTED", version
            assert version["sha256"] == FIXTURE["evidence_sha256"], version
            print("DELIVERYOS_AGENT_RECORD=" + json.dumps({
                "contract_address": ADDRESS, "job_id": job_id,
                "transactions": receipts, "status": job["status"],
                "decision_source": job["decision_source"],
                "submission_verdict": version["verdict"],
                "evidence_sha256": version["sha256"],
            }, sort_keys=True), flush=True)
