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
        passport_contract_address = "0x" + "e" * 40
        wallet_address = "0x" + "b" * 40

        def passport_identity(self):
            return {"passport_contract_address": self.passport_contract_address}

        def get_provider_profile(self, wallet_address):
            return {"wallet": wallet_address, "profile_claims": "SELF_REPORTED_NOT_VALIDATED"}

        def get_provider_receipt_count(self, wallet_address):
            return 1

        def get_provider_receipt(self, wallet_address, index):
            return {"receipt_id": "f" * 64, "index": index}

        def get_receipt_by_id(self, receipt_id):
            return {"receipt_id": receipt_id}

        def set_my_provider_profile(self, display_name, bio, capabilities):
            return {"transaction_hash": "0x" + "c" * 64, "method": "set_my_profile"}

        def get_job(self, job_id):
            return {"job_id": job_id, "status": "SUBMITTED"}

        def next_actions(self, job_id):
            return {"job_id": job_id, "role": "buyer",
                    "possible_tools": ["deliveryos_accept_delivery"]}

        def evaluate_delivery(self, job_id):
            return {"transaction_hash": "0x" + "c" * 64,
                    "status": "SUBMITTED_TO_NETWORK", "method": "evaluate_delivery"}

        def accept_delivery(self, job_id, expected_version=None):
            return {"transaction_hash": "0x" + "d" * 64,
                    "status": "SUBMITTED_TO_NETWORK", "method": "accept_delivery",
                    "expected_version": expected_version}

    monkeypatch.setattr(mcp_server.DeliveryOSClient, "from_env", lambda: FakeService())
    async with Client(mcp_server.mcp, raise_exceptions=True) as client:
        listing = await client.list_tools()
        names = {tool.name for tool in listing.tools}
        descriptions = {tool.name: tool.description or "" for tool in listing.tools}
        assert {"deliveryos_identity", "deliveryos_get_job", "deliveryos_next_actions",
                "deliveryos_submit_delivery", "deliveryos_evaluate_delivery",
                "deliveryos_transaction_status", "deliveryos_get_job_count",
                "deliveryos_get_job_id", "deliveryos_build_package_manifest",
                "deliveryos_verify_package", "deliveryos_passport_identity",
                "deliveryos_get_provider_profile", "deliveryos_get_provider_receipt_count",
                "deliveryos_get_provider_receipt", "deliveryos_get_receipt_by_id",
                "deliveryos_set_my_provider_profile"} <= names
        assert "V3-V5 require current_version" in descriptions["deliveryos_accept_delivery"]
        assert "V4/V5 enforce a hard review cutoff" in descriptions["deliveryos_evaluate_delivery"]
        assert "V4/V5 block late decisions" in descriptions["deliveryos_close_unreviewed"]

        passport = await client.call_tool("deliveryos_get_provider_profile", {
            "wallet_address": "0x" + "b" * 40,
        })
        assert passport.is_error is False
        assert "SELF_REPORTED_NOT_VALIDATED" in passport.content[0].text

        passport_identity = await client.call_tool("deliveryos_passport_identity", {})
        assert passport_identity.is_error is False
        assert "passport_contract_address" in passport_identity.content[0].text
        receipt_count = await client.call_tool("deliveryos_get_provider_receipt_count", {
            "wallet_address": "0x" + "b" * 40,
        })
        assert receipt_count.is_error is False and "1" in receipt_count.content[0].text
        receipt = await client.call_tool("deliveryos_get_provider_receipt", {
            "wallet_address": "0x" + "b" * 40, "index": 0,
        })
        assert receipt.is_error is False and "receipt_id" in receipt.content[0].text
        receipt_by_id = await client.call_tool("deliveryos_get_receipt_by_id", {
            "receipt_id": "f" * 64,
        })
        assert receipt_by_id.is_error is False and "receipt_id" in receipt_by_id.content[0].text

        profile_write = await client.call_tool("deliveryos_set_my_provider_profile", {
            "display_name": "Builder", "bio": "", "capabilities": ["research"],
        })
        assert profile_write.is_error is False
        assert "set_my_profile" in profile_write.content[0].text

        job = await client.call_tool("deliveryos_get_job", {"job_id": "job_12345"})
        assert job.is_error is False
        assert job.content and "SUBMITTED" in job.content[0].text

        guidance = await client.call_tool("deliveryos_next_actions", {"job_id": "job_12345"})
        assert guidance.is_error is False
        assert "deliveryos_accept_delivery" in guidance.content[0].text

        write = await client.call_tool("deliveryos_evaluate_delivery", {"job_id": "job_12345"})
        assert write.is_error is False
        assert write.content and "SUBMITTED_TO_NETWORK" in write.content[0].text

        bound = await client.call_tool("deliveryos_accept_delivery", {
            "job_id": "job_12345", "expected_version": 2,
        })
        assert bound.is_error is False
        assert '"expected_version":2' in bound.content[0].text.replace(" ", "")

        prepared = await client.call_tool("deliveryos_build_package_manifest", {
            "evidence_prefix": "https://raw.githubusercontent.com/Leokings/deliveryos/",
            "source_commit": "a" * 40,
            "files": [{"path": "proof.txt", "content": "Proof text\n",
                       "media_type": "text/plain", "criteria": [0]}],
            "criterion_count": 1,
        })
        assert prepared.is_error is False
        assert "manifest_text" in prepared.content[0].text
        assert "Proof text" not in prepared.content[0].text
