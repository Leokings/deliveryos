"""Adversarial direct-mode coverage for the immutable multi-file protocol."""

import hashlib
import json

import pytest


NOW = "2026-10-08T12:00:00Z"
DUE = 1791550800
PREFIX = "https://raw.githubusercontent.com/example/deliveryos/"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
MANIFEST_COMMIT = "89abcdef0123456789abcdef0123456789abcdef"
BASE = PREFIX + COMMIT + "/"
MANIFEST_URL = PREFIX + MANIFEST_COMMIT + "/package.json"
GUIDE_URL = BASE + "guide.md"
FACTS_URL = BASE + "facts.json"
BRIEF = "Deliver a short installation guide and a machine-readable verification record."
CRITERIA = ["The guide states the installation command.",
            "The JSON record names the verification command."]
GUIDE = b"# Install\nRun: npm install example-service\n"
FACTS = b'{"verify":"example-service --version"}'


def sha(body):
    return hashlib.sha256(body).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def package(files=None):
    if files is None:
        files = [
            {"url": GUIDE_URL, "sha256": sha(GUIDE), "size_bytes": len(GUIDE),
             "media_type": "text/markdown", "criteria": [0]},
            {"url": FACTS_URL, "sha256": sha(FACTS), "size_bytes": len(FACTS),
             "media_type": "application/json", "criteria": [1]},
        ]
    return canonical({"protocol": "DELIVERYOS_PACKAGE_V1",
                      "source_commit": COMMIT, "files": files}) + b"\n"


def mock_package(vm, manifest, guide=GUIDE, facts=FACTS):
    vm.mock_web(r".*package\.json$", {"status": 200, "body": manifest})
    vm.mock_web(r".*guide\.md$", {"status": 200, "body": guide})
    vm.mock_web(r".*facts\.json$", {"status": 200, "body": facts})


@pytest.fixture
def setup_package(direct_vm, direct_deploy, direct_alice, direct_bob):
    direct_vm.warp(NOW)
    contract = direct_deploy("contracts/DeliveryOSPackages.py")
    direct_vm.sender = direct_alice
    contract.create_job("package_example_01", "0x" + direct_bob.hex(), BRIEF,
                        json.dumps(CRITERIA), PREFIX, DUE, 1)
    direct_vm.sender = direct_bob
    contract.accept_job("package_example_01")
    return contract, direct_vm, direct_alice, direct_bob


def submit(contract, vm, provider, manifest, url=MANIFEST_URL):
    vm.sender = provider
    contract.submit_delivery("package_example_01", url, sha(manifest), len(manifest))


def test_validator_review_fetches_all_files_and_accepts(setup_package):
    contract, vm, buyer, provider = setup_package
    manifest = package()
    submit(contract, vm, provider, manifest)
    mock_package(vm, manifest)
    vm.mock_llm(r".*untrusted_documents.*", json.dumps({"statuses": ["MET", "MET"]}))
    vm.sender = buyer
    contract.evaluate_delivery("package_example_01")
    job = contract.get_job("package_example_01")
    record = contract.get_submission("package_example_01", 1)
    assert job["status"] == "ACCEPTED"
    assert job["protocol"] == "DELIVERYOS_PACKAGES_V2"
    assert job["decision_source"] == "CONSENSUS"
    assert record["file_count"] == 2
    assert record["total_bytes"] == len(GUIDE) + len(FACTS)
    assert record["content_fingerprint"]
    assert vm.run_validator() is True

    vm.clear_mocks()
    mock_package(vm, manifest)
    vm.mock_llm(r".*untrusted_documents.*", json.dumps({"statuses": ["MET", "NOT_MET"]}))
    assert vm.run_validator() is False

    vm.clear_mocks()
    mock_package(vm, manifest, guide=b"maliciously changed")
    vm.mock_llm(r".*untrusted_documents.*", json.dumps({"statuses": ["MET", "MET"]}))
    assert vm.run_validator() is False


def test_buyer_acceptance_requires_valid_bytes(setup_package):
    contract, vm, buyer, provider = setup_package
    manifest = package()
    submit(contract, vm, provider, manifest)
    mock_package(vm, manifest, guide=b"forged bytes")
    vm.sender = buyer
    with vm.expect_revert("[EVIDENCE_ERROR]"):
        contract.accept_delivery("package_example_01")
    assert contract.get_job("package_example_01")["status"] == "SUBMITTED"
    vm.clear_mocks()
    mock_package(vm, manifest)
    contract.accept_delivery("package_example_01")
    assert contract.get_job("package_example_01")["decision_source"] == "BUYER"
    assert contract.get_submission("package_example_01", 1)["file_count"] == 2
    assert vm.run_validator() is True


@pytest.mark.parametrize("mutation,error", [
    (lambda files: files[0].update(url=PREFIX + "f" * 40 + "/guide.md"), "source commit"),
    (lambda files: files[1].update(url=files[0]["url"]), "Duplicate file URL"),
    (lambda files: files[1].update(sha256=files[0]["sha256"]), "Duplicate file bytes"),
    (lambda files: files[1].update(criteria=[0]), "Every criterion"),
    (lambda files: files[0].update(media_type="image/png"), "Unsupported media type"),
    (lambda files: files[0].update(size_bytes=True), "File size"),
    (lambda files: files[0].update(criteria=[True]), "criterion mapping"),
    (lambda files: files[0].update(size_bytes=12001), "File size"),
])
def test_invalid_manifest_never_reaches_ai(setup_package, mutation, error):
    contract, vm, buyer, provider = setup_package
    data = json.loads(package())
    mutation(data["files"])
    manifest = canonical(data) + b"\n"
    submit(contract, vm, provider, manifest)
    mock_package(vm, manifest)
    vm.sender = buyer
    with vm.expect_revert(error):
        contract.evaluate_delivery("package_example_01")
    assert contract.get_job("package_example_01")["status"] == "SUBMITTED"


def test_noncanonical_manifest_and_bad_json_file_are_rejected(setup_package):
    contract, vm, buyer, provider = setup_package
    manifest = json.dumps(json.loads(package()), indent=2).encode()
    submit(contract, vm, provider, manifest)
    mock_package(vm, manifest)
    vm.sender = buyer
    with vm.expect_revert("canonical JSON"):
        contract.evaluate_delivery("package_example_01")

    vm.clear_mocks()
    good_manifest = package()
    # The provider cannot silently alter the submitted hash. A new job/version
    # would be needed for the corrected manifest.
    mock_package(vm, good_manifest)
    with vm.expect_revert("Evidence length changed"):
        contract.evaluate_delivery("package_example_01")


def test_csv_artifact_is_parsed_before_ai_review(setup_package):
    contract, vm, buyer, provider = setup_package
    csv_body = b'name,value\n"foo, bar",1\n'
    data = json.loads(package())
    data["files"][1].update(sha256=sha(csv_body), size_bytes=len(csv_body),
                            media_type="text/csv")
    manifest = canonical(data) + b"\n"
    submit(contract, vm, provider, manifest)
    mock_package(vm, manifest, facts=csv_body)
    vm.mock_llm(r".*untrusted_documents.*", json.dumps({"statuses": ["MET", "MET"]}))
    vm.sender = buyer
    contract.evaluate_delivery("package_example_01")
    assert contract.get_job("package_example_01")["status"] == "ACCEPTED"
    assert vm.run_validator() is True


def test_duplicate_or_changed_metadata_is_not_a_revision(setup_package):
    contract, vm, buyer, provider = setup_package
    first = package()
    submit(contract, vm, provider, first)
    mock_package(vm, first)
    vm.mock_llm(r".*untrusted_documents.*", json.dumps({"statuses": ["NOT_MET", "MET"]}))
    vm.sender = buyer
    contract.evaluate_delivery("package_example_01")
    assert contract.get_job("package_example_01")["status"] == "REVISION"

    vm.sender = provider
    with vm.expect_revert("manifest bytes"):
        contract.submit_delivery("package_example_01", MANIFEST_URL, sha(first), len(first))

    data = json.loads(first)
    data["files"][0]["criteria"] = [0, 1]
    second = canonical(data) + b"\n"
    submit(contract, vm, provider, second)
    vm.clear_mocks()
    mock_package(vm, second)
    vm.mock_llm(r".*untrusted_documents.*", json.dumps({"statuses": ["MET", "MET"]}))
    vm.sender = buyer
    with vm.expect_revert("Revision must change at least one file"):
        contract.evaluate_delivery("package_example_01")
    assert contract.get_job("package_example_01")["status"] == "SUBMITTED"
