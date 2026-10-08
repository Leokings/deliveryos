from types import SimpleNamespace

import pytest

from deliveryos_agent.client import DeliveryOSClient


ADDRESS = "0x" + "a" * 40
PREFIX = (
    "https://raw.githubusercontent.com/Leokings/digital-deliverable-verifier/"
    "c58779c534ddae9f127bffc2e06584b6f56a9f9a/tests/fixtures/"
)
URL = PREFIX + "installation-guide.txt"


class FakeSDK:
    def __init__(self):
        self.writes = []

    def read_contract(self, address, name, args, transaction_hash_variant):
        assert address == ADDRESS
        if name == "get_job":
            return {"status": "ACTIVE", "evidence_prefix": PREFIX}
        if name == "get_submission":
            return {"version": args[1], "verdict": "ACCEPTED"}
        raise AssertionError(name)

    def write_contract(self, address, name, account, args):
        self.writes.append((address, name, account.address, args))
        return "0x" + "b" * 64

    def get_transaction(self, tx_hash):
        return {"status_name": "FINALIZED", "result_name": "AGREE",
                "consensus_data": {"leader_receipt": [{"execution_result": "SUCCESS"}]}}


def test_connector_requires_signer_for_write():
    service = DeliveryOSClient(ADDRESS, client=FakeSDK())
    assert service.wallet_address is None
    assert service.get_job("job_12345")["status"] == "ACTIVE"
    with pytest.raises(RuntimeError, match="DELIVERYOS_PRIVATE_KEY"):
        service.accept_job("job_12345")


def test_evidence_source_and_digest_bound_to_write(monkeypatch):
    sdk = FakeSDK()
    service = DeliveryOSClient(ADDRESS, client=sdk)
    service.account = SimpleNamespace(address="0x" + "c" * 40)
    monkeypatch.setattr(service, "pin_public_evidence", lambda url: {
        "url": url, "sha256": "d" * 64, "size_bytes": 655,
    })
    result = service.submit_delivery("job_12345", URL)
    assert result["transaction_hash"] == "0x" + "b" * 64
    assert result["evidence"]["sha256"] == "d" * 64
    assert sdk.writes == [(ADDRESS, "submit_delivery", service.wallet_address,
                           ["job_12345", URL, "d" * 64, 655])]


def test_rejects_mutable_or_untrusted_evidence_url():
    DeliveryOSClient._validate_evidence_url(
        "https://raw.githubusercontent.com/Leokings/digital-deliverable-verifier/",
        prefix=True,
    )
    for url in (
        "https://raw.githubusercontent.com/Leokings/repo/main/file.txt",
        "https://localhost/private.txt",
        "https://raw.githubusercontent.com/Leokings/repo/" + "a" * 40 + "/../file.txt",
    ):
        with pytest.raises(ValueError):
            DeliveryOSClient.pin_public_evidence(url)


def test_finalization_checks_execution_not_just_consensus():
    sdk = FakeSDK()
    service = DeliveryOSClient(ADDRESS, client=sdk)
    assert service.transaction_status("0x" + "b" * 64)["finalized_success"] is True
    sdk.get_transaction = lambda _: {
        "status_name": "FINALIZED", "result_name": "MAJORITY_AGREE",
        "consensus_data": {"leader_receipt": [{"execution_result": "ERROR",
                                                "result": {"payload": "invalid_contract"}}]},
    }
    status = service.transaction_status("0x" + "b" * 64)
    assert status["finalized_success"] is False
    assert status["error"] == "invalid_contract"
    sdk.get_transaction = lambda _: {
        "status_name": "FINALIZED", "result_name": "DISAGREE",
        "consensus_data": {"leader_receipt": [{"execution_result": "SUCCESS"}]},
    }
    assert service.transaction_status("0x" + "b" * 64)["finalized_success"] is False
