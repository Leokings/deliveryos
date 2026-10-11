"""Direct-mode evidence for the V5-to-Passport finalized-message contract."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest


SOURCE_PATH = Path("contracts/DeliveryOSPackagesV5.py").resolve()
PASSPORT_PATH = Path("contracts/DeliveryOSProviderPassport.py").resolve()
SOURCE = "0x" + hashlib.sha256(str(SOURCE_PATH).encode()).digest()[:20].hex()
PASSPORT_ADDRESS = "0x" + hashlib.sha256(str(PASSPORT_PATH).encode()).digest()[:20].hex()
PREFIX = "https://raw.githubusercontent.com/example/deliveryos/"
SOURCE_COMMIT = "0123456789abcdef0123456789abcdef01234567"
MANIFEST_COMMIT = "89abcdef0123456789abcdef0123456789abcdef"
MANIFEST_URL = PREFIX + MANIFEST_COMMIT + "/package.json"
GUIDE_URL = PREFIX + SOURCE_COMMIT + "/guide.md"
GUIDE = b"# Install\nRun: npm install example-service\n"
CRITERIA = ["The guide states the installation command."]


def digest(body):
    return hashlib.sha256(body).hexdigest()


def package_manifest():
    return (json.dumps({
        "protocol": "DELIVERYOS_PACKAGE_V1", "source_commit": SOURCE_COMMIT,
        "files": [{"url": GUIDE_URL, "sha256": digest(GUIDE),
                   "size_bytes": len(GUIDE), "media_type": "text/markdown",
                   "criteria": [0]}],
    }, sort_keys=True, separators=(",", ":")) + "\n").encode()


@pytest.fixture
def flow(direct_vm, direct_deploy, direct_alice, direct_bob):
    direct_vm.warp("2026-10-08T12:00:00Z")
    direct_vm.sender = direct_alice
    source = direct_deploy("contracts/DeliveryOSPackagesV5.py", PASSPORT_ADDRESS)
    direct_vm.passport_source_for_test = SOURCE

    messages = []
    views = []

    def capture_message(vm, request):
        if "CallContract" in request:
            views.append(request["CallContract"])
            from genlayer.py import calldata
            return bytes([0]) + calldata.encode(vm.passport_source_for_test)
        if "PostMessage" in request:
            messages.append(request["PostMessage"])
            return {"ok": None}
        return None

    direct_vm._gl_call_hook = capture_message
    return source, direct_vm, direct_alice, direct_bob, messages, views


def prepare_job(source, vm, buyer, provider, job_id, max_revisions=1):
    due_epoch = int(datetime(2026, 10, 30, 12, tzinfo=timezone.utc).timestamp())
    vm.sender = buyer
    source.create_job(job_id, "0x" + provider.hex(),
                      "Deliver an installation guide with a command.",
                      json.dumps(CRITERIA), PREFIX, due_epoch, max_revisions)
    vm.sender = provider
    source.accept_job(job_id)
    manifest = package_manifest()
    source.submit_delivery(job_id, MANIFEST_URL, digest(manifest), len(manifest))
    vm.mock_web(r".*package\.json$", {"status": 200, "body": manifest})
    vm.mock_web(r".*guide\.md$", {"status": 200, "body": GUIDE})


def test_terminal_consensus_result_emits_finalized_provider_receipt_message(flow):
    source, vm, buyer, provider, messages, views = flow
    prepare_job(source, vm, buyer, provider, "passport_accept_01")
    vm.mock_llm(r".*untrusted_documents.*", json.dumps({"statuses": ["MET"]}))
    source.evaluate_delivery("passport_accept_01", 1)
    assert source.get_job("passport_accept_01")["status"] == "ACCEPTED"
    assert source.get_job("passport_accept_01")["decision_source"] == "CONSENSUS"
    assert len(messages) == 1

    message = messages[0]
    assert message["address"].as_hex.lower() == PASSPORT_ADDRESS
    assert message["on"] == "finalized"
    call = message["calldata"]
    assert call["method"] == "record_consensus_outcome"
    assert call["args"][0] == "passport_accept_01"
    assert call["args"][3] == 1
    assert call["args"][4] == "ACCEPTED"
    assert call["args"][6] == '["MET"]'
    assert views


def test_revision_and_manual_buyer_acceptance_do_not_emit_passport_receipts(flow):
    source, vm, buyer, provider, messages, _views = flow

    prepare_job(source, vm, buyer, provider, "passport_revision_01", max_revisions=1)
    vm.mock_llm(r".*untrusted_documents.*", json.dumps({"statuses": ["NOT_MET"]}))
    source.evaluate_delivery("passport_revision_01", 1)
    assert source.get_job("passport_revision_01")["status"] == "REVISION"
    assert messages == []

    prepare_job(source, vm, buyer, provider, "passport_buyer_01", max_revisions=0)
    vm.sender = buyer
    source.accept_delivery("passport_buyer_01", 1)
    assert source.get_job("passport_buyer_01")["status"] == "ACCEPTED"
    assert source.get_job("passport_buyer_01")["decision_source"] == "BUYER"
    assert messages == []


def test_v5_refuses_to_open_jobs_until_passport_is_bound_to_this_address(flow):
    source, vm, buyer, _provider, _messages, views = flow
    vm.passport_source_for_test = "0x" + "e" * 40
    vm.sender = buyer
    due_epoch = int(datetime(2026, 10, 30, 12, tzinfo=timezone.utc).timestamp())
    with vm.expect_revert("Provider Passport is not bound to this V5 contract"):
        source.create_job("passport_unbound_01", "0x" + ("2" * 40),
                          "Deliver a public report with evidence.",
                          json.dumps(CRITERIA), PREFIX, due_epoch, 1)
    assert source.get_job_count() == 0
    assert len(views) == 1
