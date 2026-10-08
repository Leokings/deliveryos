"""Opt-in full-consensus Studionet recovery test for the v4 package protocol."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import uuid
from urllib import request

import pytest
from eth_account import Account
from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded
from gltest.types import TransactionHashVariant, TransactionStatus
from gltest.utils import extract_contract_address

from deliveryos_agent.packages import verify_public_package


RPC = "https://studio.genlayer.com/api"
PREFIX = "https://raw.githubusercontent.com/Leokings/deliveryos/"
MANIFEST_URL = (PREFIX + "d8a674033c477f0d2bcae59ab8049cb2bdd86e37/"
                "examples/package_v2/package.json")
# Public, test-only keys. Never fund or reuse them on another network.
BUYER_TEST_KEY = "0x" + "11" * 32
PROVIDER_TEST_KEY = "0x" + "22" * 32


def _ok(receipt):
    assert tx_execution_succeeded(receipt), receipt
    assert receipt.get("status_name") == TransactionStatus.FINALIZED.value, receipt
    assert receipt.get("result_name") in (None, "AGREE", "MAJORITY_AGREE"), receipt
    return receipt


def _code(address):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "gen_getContractCode",
                       "params": [address]}).encode()
    call = request.Request(RPC, data=body, headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "DeliveryOS-V4-Studionet/4.0",
    })
    with request.urlopen(call, timeout=30) as response:
        payload = json.load(response)
    assert "error" not in payload, payload
    return base64.b64decode(payload["result"], validate=True)


@pytest.mark.integration
def test_studionet_v4_correction_and_consensus():
    source = Path(__file__).resolve().parents[2] / "contracts" / "DeliveryOSPackagesV4.py"
    preflight = verify_public_package(MANIFEST_URL, PREFIX, 2)
    buyer, provider = Account.from_key(BUYER_TEST_KEY), Account.from_key(PROVIDER_TEST_KEY)
    factory = get_contract_factory(contract_file_path=source)
    address = os.environ.get("DELIVERYOS_V4_RESUME_ADDRESS")
    transactions = {}
    if not address:
        deployed = _ok(factory.deploy_contract_tx(
            args=[], account=buyer, wait_transaction_status=TransactionStatus.FINALIZED
        ))
        address = extract_contract_address(deployed)
        transactions["deploy"] = deployed["hash"]
        print("DELIVERYOS_V4_DEPLOY=" + json.dumps({"address": address, "tx": deployed["hash"]}), flush=True)
    for attempt in range(5):
        try:
            buyer_contract = factory.build_contract(address, account=buyer)
            break
        except ValueError:
            if attempt == 4:
                raise
            time.sleep(2)
    provider_contract = factory.build_contract(address, account=provider)
    due = int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp())
    job_id = "package_v4_" + uuid.uuid4().hex[:16]
    print("DELIVERYOS_V4_JOB=" + job_id, flush=True)
    criteria = [
        "The Markdown guide explicitly states the command python -m pip install -r requirements.txt.",
        "The JSON facts file explicitly contains verify_command equal to python -m deliveryos_agent.mcp_server.",
    ]

    def write(contract, method, args, label):
        receipt = _ok(getattr(contract, method)(args=args).transact(
            wait_transaction_status=TransactionStatus.FINALIZED
        ))
        transactions[label] = receipt["hash"]
        print("DELIVERYOS_V4_TX=" + json.dumps({"step": label, "hash": receipt["hash"]}), flush=True)

    write(buyer_contract, "create_job", [job_id, provider.address,
        "Deliver an installation guide and a JSON verification record for the public example service.",
        json.dumps(criteria), PREFIX, due, 1], "propose")
    write(provider_contract, "accept_job", [job_id], "accept_job")
    write(provider_contract, "submit_delivery", [job_id, MANIFEST_URL, "0" * 64,
        preflight["size_bytes"]], "bad_submit")
    pending = buyer_contract.get_job(args=[job_id]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL)
    review_deadline = pending["review_deadline_epoch"]
    assert pending["status"] == "SUBMITTED" and pending["current_version"] == 1
    write(provider_contract, "submit_delivery", [job_id, MANIFEST_URL,
        preflight["sha256"], preflight["size_bytes"]], "correction")
    corrected = buyer_contract.get_job(args=[job_id]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL)
    first = buyer_contract.get_submission(args=[job_id, 1]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL)
    assert corrected["status"] == "SUBMITTED" and corrected["current_version"] == 2
    assert corrected["review_deadline_epoch"] == review_deadline
    assert corrected["revision_count"] == 0 and first["verdict"] == "SUPERSEDED"
    write(buyer_contract, "evaluate_delivery", [job_id, 2], "review")
    final = buyer_contract.get_job(args=[job_id]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL)
    second = buyer_contract.get_submission(args=[job_id, 2]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL)
    assert final["status"] == "ACCEPTED" and final["decision_source"] == "CONSENSUS", final
    assert final["latest_statuses"] == ["MET", "MET"], final
    assert second["content_fingerprint"] == preflight["content_fingerprint"], second
    local_code = source.read_bytes().replace(b"\r\n", b"\n")
    assert _code(address) == local_code, "Deployed v4 source differs from local file"
    print("DELIVERYOS_V4_RECORD=" + json.dumps({
        "address": address, "job_id": job_id, "transactions": transactions,
        "status": final["status"], "statuses": final["latest_statuses"],
        "review_deadline_epoch": review_deadline,
        "manifest_url": MANIFEST_URL,
        "manifest_sha256": preflight["sha256"],
        "source_sha256_lf": hashlib.sha256(local_code).hexdigest(),
    }, sort_keys=True), flush=True)

@pytest.mark.integration
def test_studionet_v4_resume_after_rpc_limit():
    """Finish the one live run if Studionet's hourly quota interrupted its reads."""
    address = os.environ.get("DELIVERYOS_V4_RESUME_ADDRESS")
    if not address:
        pytest.skip("Set DELIVERYOS_V4_RESUME_ADDRESS for this recovery-only test")
    source = Path(__file__).resolve().parents[2] / "contracts" / "DeliveryOSPackagesV4.py"
    preflight = verify_public_package(MANIFEST_URL, PREFIX, 2)
    buyer = Account.from_key(BUYER_TEST_KEY)
    factory = get_contract_factory(contract_file_path=source)
    contract = factory.build_contract(address, account=buyer)
    job_id = contract.get_job_id(args=[0]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL)
    job = contract.get_job(args=[job_id]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL)
    first = contract.get_submission(args=[job_id, 1]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL)
    second = contract.get_submission(args=[job_id, 2]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL)
    assert job["protocol"] == "DELIVERYOS_PACKAGES_V4" and job["current_version"] == 2, job
    assert job["revision_count"] == 0 and job["review_deadline_epoch"] > 0, job
    assert first["sha256"] == "0" * 64 and first["verdict"] == "SUPERSEDED", first
    assert second["sha256"] == preflight["sha256"] and second["verdict"] in ("", "ACCEPTED"), second
    review_hash = ""
    if job["status"] == "SUBMITTED":
        receipt = _ok(contract.evaluate_delivery(args=[job_id, 2]).transact(
            wait_transaction_status=TransactionStatus.FINALIZED))
        review_hash = receipt["hash"]
        print("DELIVERYOS_V4_TX=" + json.dumps({"step": "review", "hash": review_hash}), flush=True)
    final = contract.get_job(args=[job_id]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL)
    final_submission = contract.get_submission(args=[job_id, 2]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL)
    assert final["status"] == "ACCEPTED" and final["decision_source"] == "CONSENSUS", final
    assert final["latest_statuses"] == ["MET", "MET"], final
    assert final_submission["content_fingerprint"] == preflight["content_fingerprint"]
    local_code = source.read_bytes().replace(b"\r\n", b"\n")
    assert _code(address) == local_code, "Deployed v4 source differs from local file"
    print("DELIVERYOS_V4_RECORD=" + json.dumps({
        "address": address, "job_id": job_id, "review_transaction": review_hash,
        "status": final["status"], "statuses": final["latest_statuses"],
        "review_deadline_epoch": final["review_deadline_epoch"],
        "manifest_url": MANIFEST_URL, "manifest_sha256": preflight["sha256"],
        "content_fingerprint": preflight["content_fingerprint"],
        "source_sha256_lf": hashlib.sha256(local_code).hexdigest(),
    }, sort_keys=True), flush=True)

