"""A hard decision cutoff for v4 package jobs."""

import hashlib
import json

import pytest


PREFIX = "https://raw.githubusercontent.com/example/deliveryos/"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
MANIFEST_COMMIT = "89abcdef0123456789abcdef0123456789abcdef"
MANIFEST_URL = PREFIX + MANIFEST_COMMIT + "/package.json"
GUIDE_URL = PREFIX + COMMIT + "/guide.md"
GUIDE = b"# Install\nRun: npm install example-service\n"
CRITERIA = ["The guide states the installation command."]


def sha(body):
    return hashlib.sha256(body).hexdigest()


def manifest():
    return (json.dumps({
        "protocol": "DELIVERYOS_PACKAGE_V1", "source_commit": COMMIT,
        "files": [{"url": GUIDE_URL, "sha256": sha(GUIDE),
                   "size_bytes": len(GUIDE), "media_type": "text/markdown",
                   "criteria": [0]}],
    }, sort_keys=True, separators=(",", ":")) + "\n").encode()


@pytest.fixture
def submitted(direct_vm, direct_deploy, direct_alice, direct_bob):
    direct_vm.warp("2026-10-08T12:00:00Z")
    contract = direct_deploy("contracts/DeliveryOSPackagesV4.py")
    direct_vm.sender = direct_alice
    contract.create_job("hard_cutoff_01", "0x" + direct_bob.hex(),
                        "Deliver an installation guide with a command.",
                        json.dumps(CRITERIA), PREFIX, 1791550800, 1)
    direct_vm.sender = direct_bob
    contract.accept_job("hard_cutoff_01")
    data = manifest()
    contract.submit_delivery("hard_cutoff_01", MANIFEST_URL, sha(data), len(data))
    direct_vm.mock_web(r".*package\.json$", {"status": 200, "body": data})
    direct_vm.mock_web(r".*guide\.md$", {"status": 200, "body": GUIDE})
    direct_vm.mock_llm(r".*untrusted_documents.*", json.dumps({"statuses": ["MET"]}))
    job = contract.get_job("hard_cutoff_01")
    assert job["protocol"] == "DELIVERYOS_PACKAGES_V4"
    assert job["status"] == "SUBMITTED"
    return contract, direct_vm, direct_alice, direct_bob, job["review_deadline_epoch"]


@pytest.mark.parametrize("decision", ["accept_delivery", "evaluate_delivery"])
def test_decisions_revert_after_cutoff_and_anyone_can_close(submitted, direct_charlie, decision):
    contract, vm, buyer, provider, deadline = submitted
    vm.warp("2026-10-17T13:00:01Z")
    assert contract.get_job("hard_cutoff_01")["review_deadline_epoch"] == deadline
    vm.sender = buyer if decision == "accept_delivery" else provider
    with vm.expect_revert("Review cutoff passed"):
        getattr(contract, decision)("hard_cutoff_01", 1)
    assert contract.get_job("hard_cutoff_01")["status"] == "SUBMITTED"
    assert contract.get_submission("hard_cutoff_01", 1)["verdict"] == ""
    vm.sender = provider
    with vm.expect_revert("Correction window passed"):
        contract.submit_delivery("hard_cutoff_01", MANIFEST_URL, sha(manifest()), len(manifest()))
    vm.sender = direct_charlie
    contract.close_unreviewed("hard_cutoff_01")
    job = contract.get_job("hard_cutoff_01")
    assert job["status"] == "INCONCLUSIVE"
    assert job["decision_source"] == "REVIEW_TIMEOUT"
    assert contract.get_submission("hard_cutoff_01", 1)["verdict"] == "INCONCLUSIVE"


@pytest.mark.parametrize("decision", ["accept_delivery", "evaluate_delivery"])
def test_decision_succeeds_at_cutoff(submitted, decision):
    contract, vm, buyer, provider, deadline = submitted
    from datetime import datetime, timezone
    vm.warp(datetime.fromtimestamp(deadline, timezone.utc).isoformat().replace("+00:00", "Z"))
    vm.sender = buyer if decision == "accept_delivery" else provider
    with vm.expect_revert("Review grace period has not passed"):
        contract.close_unreviewed("hard_cutoff_01")
    getattr(contract, decision)("hard_cutoff_01", 1)
    assert contract.get_job("hard_cutoff_01")["status"] == "ACCEPTED"
    assert vm.run_validator() is True


def test_wrong_version_rejected_before_cutoff(submitted):
    contract, vm, buyer, _provider, _deadline = submitted
    vm.sender = buyer
    with vm.expect_revert("Pending version changed"):
        contract.accept_delivery("hard_cutoff_01", 2)
    with vm.expect_revert("Pending version changed"):
        contract.evaluate_delivery("hard_cutoff_01", 2)
