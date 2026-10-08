"""Opt-in full-consensus Studionet test of DeliveryOS package v2."""

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

from deliveryos_agent.packages import verify_public_package


RPC = "https://studio.genlayer.com/api"
PREFIX = "https://raw.githubusercontent.com/Leokings/deliveryos/"
MANIFEST_URL = (
    PREFIX + "d8a674033c477f0d2bcae59ab8049cb2bdd86e37/"
    "examples/package_v2/package.json"
)
MANIFEST_SHA256 = "4b33e4b5f89d0c3772298c50431fed8f1bc78e641125f4eafec518c44192c083"
# Public, test-only keys. Never fund or reuse them on other networks.
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
                "User-Agent": "DeliveryOS-Packages-Studionet/2.0",
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


@pytest.mark.integration
def test_studionet_package_consensus_and_manual_acceptance():
    source = Path(__file__).resolve().parents[2] / "contracts" / "DeliveryOSPackages.py"
    preflight = verify_public_package(MANIFEST_URL, PREFIX, 2)
    assert preflight["sha256"] == MANIFEST_SHA256
    assert preflight["file_count"] == 2
    assert preflight["total_bytes"] == 320

    buyer, provider = Account.from_key(BUYER_TEST_KEY), Account.from_key(PROVIDER_TEST_KEY)
    factory = get_contract_factory(contract_file_path=source)
    deployed = _ok(factory.deploy_contract_tx(
        args=[], account=buyer, wait_transaction_status=TransactionStatus.FINALIZED
    ))
    address = extract_contract_address(deployed)
    print("DELIVERYOS_PACKAGES_DEPLOY=" + json.dumps({"address": address, "tx": deployed["hash"]}), flush=True)
    buyer_contract = factory.build_contract(address, account=buyer)
    provider_contract = factory.build_contract(address, account=provider)
    due = int((datetime.now(timezone.utc) + timedelta(days=3)).timestamp())
    criteria = [
        "The Markdown guide explicitly states the command python -m pip install -r requirements.txt.",
        "The JSON facts file explicitly contains verify_command equal to python -m deliveryos_agent.mcp_server.",
    ]
    transactions = {"deploy": deployed["hash"]}

    def write(contract, method, args, label):
        receipt = _ok(getattr(contract, method)(args=args).transact(
            wait_transaction_status=TransactionStatus.FINALIZED
        ))
        transactions[label] = receipt["hash"]
        print("DELIVERYOS_PACKAGES_TX=" + json.dumps({"step": label, "hash": receipt["hash"]}), flush=True)

    def create_and_submit(job_id):
        write(buyer_contract, "create_job", [
            job_id, provider.address,
            "Deliver an installation guide and a JSON verification record for the public example service.",
            json.dumps(criteria), PREFIX, due, 0,
        ], "propose_" + job_id)
        write(provider_contract, "accept_job", [job_id], "accept_job_" + job_id)
        write(provider_contract, "submit_delivery", [
            job_id, MANIFEST_URL, MANIFEST_SHA256, preflight["size_bytes"],
        ], "submit_" + job_id)

    reviewed_job = "package_" + uuid.uuid4().hex[:16]
    create_and_submit(reviewed_job)
    write(buyer_contract, "evaluate_delivery", [reviewed_job], "review")
    job = buyer_contract.get_job(args=[reviewed_job]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL
    )
    submission = buyer_contract.get_submission(args=[reviewed_job, 1]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL
    )
    assert job["status"] == "ACCEPTED", job
    assert job["decision_source"] == "CONSENSUS", job
    assert job["latest_statuses"] == ["MET", "MET"], job
    assert submission["content_fingerprint"] == preflight["content_fingerprint"], submission
    assert submission["file_count"] == 2 and submission["total_bytes"] == 320, submission

    manual_job = "package_" + uuid.uuid4().hex[:16]
    create_and_submit(manual_job)
    write(buyer_contract, "accept_delivery", [manual_job], "manual_accept")
    manual = buyer_contract.get_job(args=[manual_job]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL
    )
    assert manual["status"] == "ACCEPTED" and manual["decision_source"] == "BUYER", manual
    manual_submission = buyer_contract.get_submission(args=[manual_job, 1]).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL
    )
    assert manual_submission["content_fingerprint"] == preflight["content_fingerprint"]

    deployed_code = base64.b64decode(_rpc("gen_getContractCode", [address]), validate=True)
    local_code = source.read_bytes().replace(b"\r\n", b"\n")
    assert deployed_code == local_code, "Deployed v2 source differs from local file"
    print("DELIVERYOS_PACKAGES_RECORD=" + json.dumps({
        "address": address, "reviewed_job": reviewed_job, "manual_job": manual_job,
        "transactions": transactions, "status": job["status"],
        "statuses": job["latest_statuses"], "decision_source": job["decision_source"],
        "manifest_url": MANIFEST_URL, "manifest_sha256": MANIFEST_SHA256,
        "content_fingerprint": preflight["content_fingerprint"],
        "source_sha256_lf": hashlib.sha256(local_code).hexdigest(),
    }, sort_keys=True), flush=True)
