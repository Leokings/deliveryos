import hashlib
import json

import pytest


NOW = "2026-10-08T12:00:00Z"
DUE = 1791550800  # 2026-10-09 12:00:00 UTC
PREFIX = "https://raw.githubusercontent.com/example/deliveryos/"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
EVIDENCE = PREFIX + COMMIT + "/delivery.txt"
EVIDENCE2 = PREFIX + COMMIT + "/delivery-v2.txt"
BRIEF = "Deliver a concise installation guide for the example service."
CRITERIA = [
    "The guide states the installation command.",
    "The guide states how to verify a successful installation.",
]
BODY = b"Install: npm install example-service\nVerify: example-service --version\n"
SHA = hashlib.sha256(BODY).hexdigest()
BODY2 = BODY + b"Revision: updated formatting.\n"
SHA2 = hashlib.sha256(BODY2).hexdigest()


@pytest.fixture
def setup_job(direct_vm, direct_deploy, direct_alice, direct_bob):
    direct_vm.warp(NOW)
    contract = direct_deploy("contracts/DeliveryOS.py")
    direct_vm.sender = direct_alice
    contract.create_job("job_example_001", "0x" + direct_bob.hex(), BRIEF, json.dumps(CRITERIA), PREFIX, DUE, 1)
    return contract, direct_vm, direct_alice, direct_bob


def test_full_manual_lifecycle(setup_job):
    contract, vm, buyer, provider = setup_job
    job = contract.get_job("job_example_001")
    assert job["status"] == "PROPOSED"
    assert job["buyer"] != job["provider"]
    assert job["scope_digest"] != ""
    assert contract.get_job_count() == 1
    assert contract.get_job_id(0) == "job_example_001"

    vm.sender = provider
    contract.accept_job("job_example_001")
    contract.submit_delivery("job_example_001", EVIDENCE, SHA, len(BODY))
    assert contract.get_job("job_example_001")["status"] == "SUBMITTED"
    assert contract.get_submission("job_example_001", 1)["sha256"] == SHA

    vm.sender = buyer
    contract.accept_delivery("job_example_001")
    assert contract.get_job("job_example_001")["status"] == "ACCEPTED"
    assert contract.get_submission("job_example_001", 1)["verdict"] == "ACCEPTED"
    with vm.expect_revert("Job is not awaiting a delivery"):
        vm.sender = provider
        contract.submit_delivery("job_example_001", EVIDENCE, SHA, len(BODY))


def test_consensus_acceptance_with_pinned_bytes(setup_job):
    contract, vm, buyer, provider = setup_job
    vm.sender = provider
    contract.accept_job("job_example_001")
    contract.submit_delivery("job_example_001", EVIDENCE, SHA, len(BODY))
    vm.mock_web(r".*raw\.githubusercontent\.com.*delivery\.txt", {"status": 200, "body": BODY})
    vm.mock_llm(r".*installation guide.*", json.dumps({"statuses": ["MET", "MET"]}))
    vm.sender = buyer
    contract.evaluate_delivery("job_example_001")
    job = contract.get_job("job_example_001")
    assert job["status"] == "ACCEPTED"
    assert job["decision_source"] == "CONSENSUS"
    assert job["latest_statuses"] == ["MET", "MET"]
    assert contract.get_submission("job_example_001", 1)["verdict"] == "ACCEPTED"


def test_validator_rejects_disagreeing_or_changed_evidence(setup_job):
    contract, vm, buyer, provider = setup_job
    vm.sender = provider
    contract.accept_job("job_example_001")
    contract.submit_delivery("job_example_001", EVIDENCE, SHA, len(BODY))
    vm.mock_web(r".*delivery\.txt", {"status": 200, "body": BODY})
    vm.mock_llm(r".*installation guide.*", json.dumps({"statuses": ["MET", "MET"]}))
    vm.sender = buyer
    contract.evaluate_delivery("job_example_001")
    assert vm.run_validator() is True

    vm.clear_mocks()
    vm.mock_web(r".*delivery\.txt", {"status": 200, "body": BODY})
    vm.mock_llm(r".*installation guide.*", json.dumps({"statuses": ["MET", "NOT_MET"]}))
    assert vm.run_validator() is False

    vm.clear_mocks()
    vm.mock_web(r".*delivery\.txt", {"status": 200, "body": b"changed evidence"})
    vm.mock_llm(r".*installation guide.*", json.dumps({"statuses": ["MET", "MET"]}))
    assert vm.run_validator() is False


def test_revision_then_rejection_when_allowance_exhausted(setup_job):
    contract, vm, buyer, provider = setup_job
    vm.sender = provider
    contract.accept_job("job_example_001")
    contract.submit_delivery("job_example_001", EVIDENCE, SHA, len(BODY))
    vm.mock_web(r".*raw\.githubusercontent\.com.*delivery\.txt", {"status": 200, "body": BODY})
    vm.mock_llm(r".*installation guide.*", json.dumps({"statuses": ["MET", "NOT_MET"]}))
    vm.sender = buyer
    contract.evaluate_delivery("job_example_001")
    assert contract.get_job("job_example_001")["status"] == "REVISION"

    vm.sender = provider
    with vm.expect_revert("must change the evidence bytes"):
        contract.submit_delivery("job_example_001", EVIDENCE, SHA, len(BODY))
    contract.submit_delivery("job_example_001", EVIDENCE2, SHA2, len(BODY2))
    assert contract.get_job("job_example_001")["revision_count"] == 1
    vm.mock_web(r".*delivery-v2\.txt", {"status": 200, "body": BODY2})
    vm.sender = buyer
    contract.evaluate_delivery("job_example_001")
    assert contract.get_job("job_example_001")["status"] == "REJECTED"
    assert contract.get_submission("job_example_001", 1)["verdict"] == "REVISION"
    assert contract.get_submission("job_example_001", 2)["verdict"] == "REJECTED"


def test_missing_or_changed_evidence_never_accepts(setup_job):
    contract, vm, buyer, provider = setup_job
    vm.sender = provider
    contract.accept_job("job_example_001")
    contract.submit_delivery("job_example_001", EVIDENCE, SHA, len(BODY))
    vm.mock_web(r".*raw\.githubusercontent\.com.*delivery\.txt", {"status": 200, "body": b"fake bytes"})
    vm.mock_llm(r".*installation guide.*", json.dumps({"statuses": ["MET", "MET"]}))
    vm.sender = buyer
    with vm.expect_revert("[EVIDENCE_ERROR]"):
        contract.evaluate_delivery("job_example_001")
    assert contract.get_job("job_example_001")["status"] == "SUBMITTED"


def test_authorization_duplicate_and_deadline(setup_job, direct_charlie):
    contract, vm, buyer, provider = setup_job
    vm.sender = buyer
    with vm.expect_revert("Job ID already exists"):
        contract.create_job("job_example_001", "0x" + provider.hex(), BRIEF, json.dumps(CRITERIA), PREFIX, DUE, 1)
    with vm.expect_revert("Only the provider may accept"):
        contract.accept_job("job_example_001")
    vm.sender = direct_charlie
    with vm.expect_revert("Only the provider may accept"):
        contract.accept_job("job_example_001")
    vm.sender = provider
    contract.accept_job("job_example_001")
    vm.warp("2026-10-10T12:00:00Z")
    with vm.expect_revert("Submission deadline passed"):
        contract.submit_delivery("job_example_001", EVIDENCE, SHA, len(BODY))
    vm.sender = direct_charlie
    contract.expire_undelivered("job_example_001")
    assert contract.get_job("job_example_001")["status"] == "EXPIRED"
    assert contract.get_job("job_example_001")["decision_source"] == "DEADLINE"


def test_evidence_source_policy_and_zero_delivery_guard(setup_job):
    contract, vm, buyer, provider = setup_job
    vm.sender = buyer
    with vm.expect_revert("Only the buyer may accept a submitted delivery"):
        contract.accept_delivery("job_example_001")
    vm.sender = provider
    contract.accept_job("job_example_001")
    with vm.expect_revert("outside the agreed source prefix"):
        contract.submit_delivery("job_example_001", "https://raw.githubusercontent.com/other/repo/0123456789abcdef0123456789abcdef01234567/file.txt", SHA, len(BODY))
    with vm.expect_revert("Evidence must use raw.githubusercontent.com"):
        contract.submit_delivery("job_example_001", "https://localhost/private.txt", SHA, len(BODY))
    with vm.expect_revert("full commit SHA"):
        contract.submit_delivery("job_example_001", "https://raw.githubusercontent.com/example/deliveryos/main/delivery.txt", SHA, len(BODY))


def test_pending_review_can_end_only_after_grace(setup_job, direct_charlie):
    contract, vm, buyer, provider = setup_job
    vm.sender = provider
    contract.accept_job("job_example_001")
    contract.submit_delivery("job_example_001", EVIDENCE, SHA, len(BODY))
    vm.sender = direct_charlie
    with vm.expect_revert("Review grace period has not passed"):
        contract.close_unreviewed("job_example_001")
    vm.warp("2026-10-17T12:00:00Z")
    contract.close_unreviewed("job_example_001")
    assert contract.get_job("job_example_001")["status"] == "INCONCLUSIVE"
    assert contract.get_job("job_example_001")["decision_source"] == "REVIEW_TIMEOUT"
    assert contract.get_submission("job_example_001", 1)["verdict"] == "INCONCLUSIVE"


def test_review_after_original_due_preserves_revision_window(setup_job):
    contract, vm, buyer, provider = setup_job
    vm.sender = provider
    contract.accept_job("job_example_001")
    contract.submit_delivery("job_example_001", EVIDENCE, SHA, len(BODY))
    vm.mock_web(r".*delivery\.txt", {"status": 200, "body": BODY})
    vm.mock_llm(r".*installation guide.*", json.dumps({"statuses": ["NOT_MET", "NOT_MET"]}))
    vm.warp("2026-10-10T12:00:00Z")
    vm.sender = buyer
    contract.evaluate_delivery("job_example_001")
    job = contract.get_job("job_example_001")
    assert job["status"] == "REVISION"
    assert job["submission_deadline_epoch"] > DUE
    vm.sender = provider
    contract.submit_delivery("job_example_001", EVIDENCE2, SHA2, len(BODY2))
    assert contract.get_job("job_example_001")["status"] == "SUBMITTED"
