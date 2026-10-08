"""Recovery, deadline and role checks for the v3 package protocol."""

import hashlib
import json

import pytest


PREFIX = "https://raw.githubusercontent.com/example/deliveryos/"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
MANIFEST_COMMIT = "89abcdef0123456789abcdef0123456789abcdef"
MANIFEST_URL = PREFIX + MANIFEST_COMMIT + "/package.json"
GUIDE_URL = PREFIX + COMMIT + "/guide.md"
FACTS_URL = PREFIX + COMMIT + "/facts.json"
GUIDE = b"# Install\nRun: npm install example-service\n"
FACTS = b'{"verify":"example-service --version"}'
CRITERIA = ["The guide states the installation command.",
            "The JSON record names the verification command."]


def sha(body):
    return hashlib.sha256(body).hexdigest()


def manifest(guide=GUIDE, guide_size=None):
    files = [
        {"url": GUIDE_URL, "sha256": sha(guide), "size_bytes": len(guide) if guide_size is None else guide_size,
         "media_type": "text/markdown", "criteria": [0]},
        {"url": FACTS_URL, "sha256": sha(FACTS), "size_bytes": len(FACTS),
         "media_type": "application/json", "criteria": [1]},
    ]
    return (json.dumps({"protocol": "DELIVERYOS_PACKAGE_V1", "source_commit": COMMIT,
                        "files": files}, sort_keys=True, separators=(",", ":")) + "\n").encode()


def mock_package(vm, data, guide=GUIDE):
    vm.mock_web(r".*package\.json$", {"status": 200, "body": data})
    vm.mock_web(r".*guide\.md$", {"status": 200, "body": guide})
    vm.mock_web(r".*facts\.json$", {"status": 200, "body": FACTS})


@pytest.fixture
def setup_v3(direct_vm, direct_deploy, direct_alice, direct_bob):
    direct_vm.warp("2026-10-08T12:00:00Z")
    contract = direct_deploy("contracts/DeliveryOSPackagesV3.py")
    direct_vm.sender = direct_alice
    contract.create_job("package_example_03", "0x" + direct_bob.hex(),
                        "Deliver an installation guide and a machine-readable verification record.",
                        json.dumps(CRITERIA), PREFIX, 1791550800, 1)
    direct_vm.sender = direct_bob
    contract.accept_job("package_example_03")
    return contract, direct_vm, direct_alice, direct_bob


def submit(contract, vm, provider, data):
    vm.sender = provider
    return contract.submit_delivery("package_example_03", MANIFEST_URL, sha(data), len(data))


def test_invalid_pending_package_can_be_corrected_and_reviewed(setup_v3):
    contract, vm, buyer, provider = setup_v3
    invalid = manifest(guide_size=len(GUIDE) + 1)
    assert submit(contract, vm, provider, invalid) == 1
    first_deadline = contract.get_job("package_example_03")["review_deadline_epoch"]
    mock_package(vm, invalid)
    vm.sender = buyer
    with vm.expect_revert("Evidence length changed"):
        contract.evaluate_delivery("package_example_03", 1)
    assert contract.get_job("package_example_03")["status"] == "SUBMITTED"

    valid = manifest()
    with vm.expect_revert("Only the provider"):
        contract.submit_delivery("package_example_03", MANIFEST_URL, sha(valid), len(valid))
    vm.sender = provider
    with vm.expect_revert("change the manifest bytes"):
        contract.submit_delivery("package_example_03", MANIFEST_URL, sha(invalid), len(invalid))
    assert submit(contract, vm, provider, valid) == 2
    job = contract.get_job("package_example_03")
    assert job["protocol"] == "DELIVERYOS_PACKAGES_V3"
    assert job["review_deadline_epoch"] == first_deadline
    assert job["revision_count"] == 0
    assert contract.get_submission("package_example_03", 1)["verdict"] == "SUPERSEDED"
    assert contract.get_submission("package_example_03", 2)["verdict"] == ""

    vm.clear_mocks()
    mock_package(vm, valid)
    vm.mock_llm(r".*untrusted_documents.*", json.dumps({"statuses": ["MET", "MET"]}))
    vm.sender = buyer
    with vm.expect_revert("Pending version changed"):
        contract.accept_delivery("package_example_03", 1)
    with vm.expect_revert("Pending version changed"):
        contract.evaluate_delivery("package_example_03", 1)
    contract.evaluate_delivery("package_example_03", 2)
    assert contract.get_job("package_example_03")["status"] == "ACCEPTED"
    assert contract.get_submission("package_example_03", 2)["content_fingerprint"]
    assert vm.run_validator() is True


def test_correction_cannot_extend_review_window(setup_v3):
    contract, vm, buyer, provider = setup_v3
    first = manifest(guide_size=len(GUIDE) + 1)
    submit(contract, vm, provider, first)
    deadline = contract.get_job("package_example_03")["review_deadline_epoch"]
    vm.warp("2026-10-16T12:00:00Z")
    second = manifest()
    submit(contract, vm, provider, second)
    assert contract.get_job("package_example_03")["review_deadline_epoch"] == deadline
    vm.warp("2026-10-17T13:00:01Z")
    with vm.expect_revert("Correction window passed"):
        contract.submit_delivery("package_example_03", MANIFEST_URL, sha(first), len(first))
    vm.sender = buyer
    contract.close_unreviewed("package_example_03")
    assert contract.get_job("package_example_03")["status"] == "INCONCLUSIVE"
    assert contract.get_submission("package_example_03", 2)["verdict"] == "INCONCLUSIVE"


def test_revision_checks_last_reviewed_content_after_a_correction(setup_v3):
    contract, vm, buyer, provider = setup_v3
    first = manifest()
    submit(contract, vm, provider, first)
    mock_package(vm, first)
    vm.mock_llm(r".*untrusted_documents.*", json.dumps({"statuses": ["NOT_MET", "MET"]}))
    vm.sender = buyer
    contract.evaluate_delivery("package_example_03", 1)
    assert contract.get_job("package_example_03")["status"] == "REVISION"
    reviewed_fingerprint = contract.get_job("package_example_03")["last_reviewed_fingerprint"]

    vm.sender = provider
    metadata_change = json.loads(first)
    metadata_change["files"][0]["criteria"] = [0, 1]
    second = (json.dumps(metadata_change, sort_keys=True, separators=(",", ":")) + "\n").encode()
    submit(contract, vm, provider, second)
    third_change = json.loads(second)
    third_change["files"][1]["criteria"] = [0, 1]
    third = (json.dumps(third_change, sort_keys=True, separators=(",", ":")) + "\n").encode()
    submit(contract, vm, provider, third)
    job = contract.get_job("package_example_03")
    assert job["revision_count"] == 1
    assert job["last_reviewed_fingerprint"] == reviewed_fingerprint
    vm.clear_mocks()
    mock_package(vm, third)
    vm.mock_llm(r".*untrusted_documents.*", json.dumps({"statuses": ["MET", "MET"]}))
    vm.sender = buyer
    with vm.expect_revert("Revision must change at least one file"):
        contract.evaluate_delivery("package_example_03", 3)
    assert contract.get_job("package_example_03")["status"] == "SUBMITTED"


def test_version_bound_buyer_acceptance_still_verifies_exact_bytes(setup_v3):
    contract, vm, buyer, provider = setup_v3
    data = manifest()
    submit(contract, vm, provider, data)
    vm.sender = buyer
    mock_package(vm, data, guide=b"changed bytes")
    with vm.expect_revert("Evidence length changed"):
        contract.accept_delivery("package_example_03", 1)
    assert contract.get_job("package_example_03")["status"] == "SUBMITTED"
    vm.clear_mocks()
    mock_package(vm, data)
    contract.accept_delivery("package_example_03", 1)
    assert contract.get_job("package_example_03")["decision_source"] == "BUYER"
    assert contract.get_submission("package_example_03", 1)["content_fingerprint"]
    assert vm.run_validator() is True
    vm.sender = provider
    with vm.expect_revert("Job is not awaiting a delivery"):
        contract.submit_delivery("package_example_03", MANIFEST_URL, sha(data), len(data))
