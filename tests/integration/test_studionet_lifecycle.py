"""Real Studionet lifecycle. Run explicitly with --network studionet."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import time
import uuid
from urllib import error, request

import pytest
from eth_account import Account
from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded
from gltest.types import TransactionHashVariant, TransactionStatus
from gltest.utils import extract_contract_address
from genlayer_py.exceptions import GenLayerError
from genlayer_py.provider.provider import GenLayerProvider


FIXTURE_URL = (
    "https://raw.githubusercontent.com/Leokings/digital-deliverable-verifier/"
    "c58779c534ddae9f127bffc2e06584b6f56a9f9a/tests/fixtures/installation-guide.txt"
)
FIXTURE_PREFIX = "https://raw.githubusercontent.com/Leokings/digital-deliverable-verifier/"
FIXTURE_SHA256 = "ab218cdca2b0765c780b3983c9837c4ebf1eb24ddc7c0f5c00b6b87ddb9d5d49"
FIXTURE_SIZE = 655
RPC = "https://studio.genlayer.com/api"
# Public, test-only keys. Never fund or reuse these accounts outside Studionet.
BUYER_TEST_KEY = "0x" + "11" * 32
PROVIDER_TEST_KEY = "0x" + "22" * 32


def _ok(receipt):
    assert tx_execution_succeeded(receipt), receipt
    assert receipt.get("status_name") == TransactionStatus.FINALIZED.value, receipt
    assert receipt.get("result_name") in (None, "AGREE", "MAJORITY_AGREE"), receipt
    return receipt


def _rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last_error = None
    for attempt in range(6):
        try:
            call = request.Request(RPC, data=body, headers={
                "Content-Type": "application/json", "Accept": "application/json",
                "User-Agent": "DeliveryOS-Studionet-Audit/1.0",
            })
            with request.urlopen(call, timeout=30) as response:
                payload = json.load(response)
            assert "error" not in payload, payload
            return payload["result"]
        except (error.HTTPError, error.URLError, TimeoutError, AssertionError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < 5:
                time.sleep(3)
    raise AssertionError(f"Studionet RPC verification failed: {last_error}")


@pytest.fixture(autouse=True)
def retry_transient_read_rpc(monkeypatch):
    original = GenLayerProvider.make_request

    def resilient(self, method, params):
        for attempt in range(6):
            try:
                return original(self, method, params)
            except GenLayerError as exc:
                is_read = str(method).startswith(("eth_get", "gen_get")) or str(method) == "gen_call"
                if not is_read or "invalid JSON" not in str(exc) or attempt == 5:
                    raise
                time.sleep(3)

    monkeypatch.setattr(GenLayerProvider, "make_request", resilient)


@pytest.mark.integration
def test_studionet_consensus_acceptance():
    source = Path(__file__).resolve().parents[2] / "contracts" / "DeliveryOS.py"
    buyer, provider = Account.from_key(BUYER_TEST_KEY), Account.from_key(PROVIDER_TEST_KEY)
    factory = get_contract_factory(contract_file_path=source)
    deployed = _ok(factory.deploy_contract_tx(
        args=[], account=buyer, wait_transaction_status=TransactionStatus.FINALIZED
    ))
    address = extract_contract_address(deployed)
    print("DELIVERYOS_STUDIONET_DEPLOY=" + json.dumps({"address": address, "tx": deployed["hash"]}), flush=True)
    buyer_contract = factory.build_contract(address, account=buyer)
    provider_contract = factory.build_contract(address, account=provider)

    job_id = "deliveryos_" + uuid.uuid4().hex[:16]
    print("DELIVERYOS_STUDIONET_PARTIES=" + json.dumps({
        "job_id": job_id, "buyer": buyer.address, "provider": provider.address,
    }), flush=True)
    due = int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp())
    receipts = {"deploy": deployed["hash"]}

    proposal = _ok(buyer_contract.create_job(args=[
        job_id,
        provider.address,
        "Deliver the public Digital Deliverable Verifier installation guide, including its actual install and verification commands.",
        json.dumps(["The guide explicitly includes the command python -m pip install -r requirements.txt."]),
        FIXTURE_PREFIX,
        due,
        0,
    ]).transact(wait_transaction_status=TransactionStatus.FINALIZED))
    receipts["propose"] = proposal["hash"]
    print("DELIVERYOS_STUDIONET_TX=" + json.dumps({"step": "propose", "hash": proposal["hash"]}), flush=True)
    accepted = _ok(provider_contract.accept_job(args=[job_id]).transact(
        wait_transaction_status=TransactionStatus.FINALIZED
    ))
    receipts["accept_job"] = accepted["hash"]
    print("DELIVERYOS_STUDIONET_TX=" + json.dumps({"step": "accept_job", "hash": accepted["hash"]}), flush=True)
    submitted = _ok(provider_contract.submit_delivery(args=[
        job_id, FIXTURE_URL, FIXTURE_SHA256, FIXTURE_SIZE
    ]).transact(wait_transaction_status=TransactionStatus.FINALIZED))
    receipts["submit"] = submitted["hash"]
    print("DELIVERYOS_STUDIONET_TX=" + json.dumps({"step": "submit", "hash": submitted["hash"]}), flush=True)
    reviewed = _ok(provider_contract.evaluate_delivery(args=[job_id]).transact(
        wait_transaction_status=TransactionStatus.FINALIZED
    ))
    receipts["review"] = reviewed["hash"]
    print("DELIVERYOS_STUDIONET_TX=" + json.dumps({"step": "review", "hash": reviewed["hash"]}), flush=True)

    job = buyer_contract.get_job(args=[job_id]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL
    )
    submission = buyer_contract.get_submission(args=[job_id, 1]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL
    )
    assert job["status"] == "ACCEPTED", job
    assert job["decision_source"] == "CONSENSUS", job
    assert job["latest_statuses"] == ["MET"], job
    assert submission["sha256"] == FIXTURE_SHA256, submission
    assert submission["verdict"] == "ACCEPTED", submission

    print("DELIVERYOS_STUDIONET_FLOW=" + json.dumps({
        "address": address, "job_id": job_id, "transactions": receipts,
        "state": job["status"], "decision_source": job["decision_source"],
        "statuses": job["latest_statuses"],
    }, sort_keys=True), flush=True)

    deployed_code = base64.b64decode(_rpc("gen_getContractCode", [address]), validate=True)
    local_code = source.read_bytes().replace(b"\r\n", b"\n")
    assert deployed_code == local_code, "Studionet deployed code differs from local source"
    print("DELIVERYOS_STUDIONET_RECORD=" + json.dumps({
        "address": address,
        "job_id": job_id,
        "transactions": receipts,
        "state": job["status"],
        "decision_source": job["decision_source"],
        "statuses": job["latest_statuses"],
        "evidence_url": FIXTURE_URL,
        "evidence_sha256": FIXTURE_SHA256,
        "source_sha256": hashlib.sha256(local_code).hexdigest(),
    }, sort_keys=True), flush=True)


@pytest.mark.integration
def test_studionet_revision_then_rejection():
    record = json.loads((Path(__file__).resolve().parents[2] / "deployments" / "studionet.json").read_text())
    address = record["contract_address"]
    source = Path(__file__).resolve().parents[2] / "contracts" / "DeliveryOS.py"
    factory = get_contract_factory(contract_file_path=source)
    buyer = Account.from_key(BUYER_TEST_KEY)
    provider = Account.from_key(PROVIDER_TEST_KEY)
    buyer_contract = factory.build_contract(address, account=buyer)
    provider_contract = factory.build_contract(address, account=provider)
    job_id = "revision_" + uuid.uuid4().hex[:16]
    due = int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp())
    print("DELIVERYOS_REVISION_JOB=" + job_id, flush=True)
    transactions = {}

    def write(contract, method, args, label):
        receipt = _ok(getattr(contract, method)(args=args).transact(
            wait_transaction_status=TransactionStatus.FINALIZED
        ))
        transactions[label] = receipt["hash"]
        print("DELIVERYOS_REVISION_TX=" + json.dumps({"step": label, "hash": receipt["hash"]}), flush=True)

    write(buyer_contract, "create_job", [
        job_id, provider.address,
        "Deliver a public text document that includes the exact sentence green turtles dance on Saturn.",
        json.dumps(["The submitted document explicitly contains the exact sentence green turtles dance on Saturn."]),
        FIXTURE_PREFIX, due, 1,
    ], "propose")
    write(provider_contract, "accept_job", [job_id], "accept_job")
    write(provider_contract, "submit_delivery", [
        job_id, FIXTURE_URL, FIXTURE_SHA256, FIXTURE_SIZE,
    ], "submit_v1")
    write(provider_contract, "evaluate_delivery", [job_id], "review_v1")
    after_first = buyer_contract.get_job(args=[job_id]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL
    )
    assert after_first["status"] == "REVISION", after_first
    assert after_first["latest_statuses"] == ["NOT_MET"], after_first
    assert after_first["submission_deadline_epoch"] >= due, after_first

    second_url = FIXTURE_PREFIX + "c58779c534ddae9f127bffc2e06584b6f56a9f9a/LICENSE"
    second_sha = "cec17f27a3b8b9f0607b85ea4e1674e3212051cf6365ddbecfa90b7d095b3300"
    write(provider_contract, "submit_delivery", [job_id, second_url, second_sha, 1098], "submit_v2")
    write(buyer_contract, "evaluate_delivery", [job_id], "review_v2")
    final = buyer_contract.get_job(args=[job_id]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL
    )
    version1 = buyer_contract.get_submission(args=[job_id, 1]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL
    )
    version2 = buyer_contract.get_submission(args=[job_id, 2]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL
    )
    assert final["status"] == "REJECTED", final
    assert final["decision_source"] == "CONSENSUS", final
    assert final["revision_count"] == 1, final
    assert version1["verdict"] == "REVISION", version1
    assert version2["verdict"] == "REJECTED", version2
    assert version1["sha256"] != version2["sha256"]
    print("DELIVERYOS_REVISION_RECORD=" + json.dumps({
        "address": address, "job_id": job_id, "transactions": transactions,
        "version_1": {"sha256": version1["sha256"], "statuses": version1["statuses"], "verdict": version1["verdict"]},
        "version_2": {"sha256": version2["sha256"], "statuses": version2["statuses"], "verdict": version2["verdict"]},
        "final_status": final["status"], "decision_source": final["decision_source"],
    }, sort_keys=True), flush=True)
