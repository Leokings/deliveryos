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


@pytest.mark.parametrize(("status", "role", "expected"), [
    ("PROPOSED", "provider", ["deliveryos_accept_job", "deliveryos_decline_job"]),
    ("PROPOSED", "buyer", ["deliveryos_cancel_proposal"]),
    ("ACTIVE", "provider", ["deliveryos_submit_delivery"]),
    ("SUBMITTED", "buyer", ["deliveryos_accept_delivery", "deliveryos_evaluate_delivery"]),
    ("SUBMITTED", "provider", ["deliveryos_evaluate_delivery"]),
    ("ACCEPTED", "provider", []),
])
def test_next_actions_are_role_and_state_specific(status, role, expected):
    service = DeliveryOSClient(ADDRESS, client=FakeSDK())
    service.account = SimpleNamespace(address="0x" + ("b" if role == "buyer" else "c") * 40)
    service.get_job = lambda _: {
        "status": status, "buyer": "0x" + "b" * 40,
        "provider": "0x" + "c" * 40, "protocol": "DELIVERYOS_PACKAGES_V2",
    }
    result = service.next_actions("job_12345")
    assert result["role"] == role
    assert result["possible_tools"] == expected
    assert result["job_url_path"] == "/?version=v2&job=job_12345"


def test_readonly_agent_cannot_receive_signed_action_suggestions():
    service = DeliveryOSClient(ADDRESS, client=FakeSDK())
    service.get_job = lambda _: {
        "status": "PROPOSED", "buyer": "0x" + "b" * 40,
        "provider": "0x" + "c" * 40,
    }
    result = service.next_actions("job_12345")
    assert result["role"] == "observer"
    assert result["possible_tools"] == []


def test_v3_agent_suggests_bounded_correction():
    service = DeliveryOSClient(ADDRESS, client=FakeSDK())
    service.account = SimpleNamespace(address="0x" + "c" * 40)
    service.get_job = lambda _: {
        "status": "SUBMITTED", "buyer": "0x" + "b" * 40,
        "provider": "0x" + "c" * 40, "protocol": "DELIVERYOS_PACKAGES_V3",
        "review_deadline_epoch": 9999999999,
    }
    result = service.next_actions("job_12345")
    assert result["possible_tools"] == ["deliveryos_submit_delivery", "deliveryos_evaluate_delivery"]
    assert result["job_url_path"] == "/?version=v3&job=job_12345"
    service.get_job = lambda _: {
        "status": "SUBMITTED", "buyer": "0x" + "b" * 40,
        "provider": "0x" + "c" * 40, "protocol": "DELIVERYOS_PACKAGES_V3",
        "review_deadline_epoch": 1,
    }
    # The contract, not this advisory list, remains the final clock authority.
    late_tools = service.next_actions("job_12345")["possible_tools"]
    assert "deliveryos_submit_delivery" not in late_tools
    assert "deliveryos_evaluate_delivery" in late_tools  # v3 has a soft cutoff.
    assert "deliveryos_close_unreviewed" in late_tools


def test_v3_decision_requires_exact_inspected_version():
    sdk = FakeSDK()
    service = DeliveryOSClient(ADDRESS, client=sdk)
    service.account = SimpleNamespace(address="0x" + "b" * 40)
    service.get_job = lambda _: {"protocol": "DELIVERYOS_PACKAGES_V3", "current_version": 2}
    with pytest.raises(ValueError, match="expected_version"):
        service.accept_delivery("job_12345")
    with pytest.raises(ValueError, match="Pending version changed"):
        service.evaluate_delivery("job_12345", 1)
    result = service.accept_delivery("job_12345", 2)
    assert result["method"] == "accept_delivery"
    assert sdk.writes[0][3] == ["job_12345", 2]


def test_v4_agent_stops_decisions_after_cutoff(monkeypatch):
    monkeypatch.setattr("deliveryos_agent.client.time.time", lambda: 100)
    sdk = FakeSDK()
    service = DeliveryOSClient(ADDRESS, client=sdk)
    service.account = SimpleNamespace(address="0x" + "b" * 40)
    service.get_job = lambda _: {
        "status": "SUBMITTED", "buyer": "0x" + "b" * 40,
        "provider": "0x" + "c" * 40, "protocol": "DELIVERYOS_PACKAGES_V4",
        "current_version": 2, "review_deadline_epoch": 99,
    }
    result = service.next_actions("job_12345")
    assert result["job_url_path"] == "/?version=v4&job=job_12345"
    assert result["possible_tools"] == ["deliveryos_close_unreviewed"]
    with pytest.raises(ValueError, match="Review cutoff passed"):
        service.accept_delivery("job_12345", 2)
    with pytest.raises(ValueError, match="Review cutoff passed"):
        service.evaluate_delivery("job_12345", 2)
    assert sdk.writes == []


def test_v4_agent_can_review_current_version_before_cutoff(monkeypatch):
    monkeypatch.setattr("deliveryos_agent.client.time.time", lambda: 100)
    sdk = FakeSDK()
    service = DeliveryOSClient(ADDRESS, client=sdk)
    service.account = SimpleNamespace(address="0x" + "c" * 40)
    service.get_job = lambda _: {
        "status": "SUBMITTED", "buyer": "0x" + "b" * 40,
        "provider": "0x" + "c" * 40, "protocol": "DELIVERYOS_PACKAGES_V4",
        "current_version": 2, "review_deadline_epoch": 100,
    }
    assert service.next_actions("job_12345")["possible_tools"] == [
        "deliveryos_submit_delivery", "deliveryos_evaluate_delivery",
    ]
    with pytest.raises(ValueError, match="expected_version"):
        service.evaluate_delivery("job_12345")
    service.evaluate_delivery("job_12345", 2)
    assert sdk.writes[0][3] == ["job_12345", 2]


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
