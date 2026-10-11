"""Opt-in V6 full-consensus smoke and controlled callback-failure recovery.

The fault registry is a TEST-ONLY copy with an owner-operated rejection gate.
It is never used by the production website. Keys here are public test keys;
never fund them or use them on another network.
"""

import hashlib
import json
import os
from pathlib import Path
import time
import uuid

import pytest
from eth_account import Account
from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded
from gltest.types import TransactionHashVariant, TransactionStatus
from gltest.utils import extract_contract_address
from genlayer_py import create_account
from genlayer_py.chains import studionet
from genlayer_py.client import create_client
from genlayer_py.exceptions import GenLayerError

from deliveryos_agent.packages import verify_public_package
from test_studionet_packages_v4 import _code, _ok, MANIFEST_URL, PREFIX


ROOT = Path(__file__).resolve().parents[2]
BUYER = Account.from_key("0x" + "11" * 32)
PROVIDER = Account.from_key("0x" + "22" * 32)
RPC_CLIENT = create_client(chain=studionet, account=create_account())


def _retry_read(call):
    for attempt in range(4):
        try:
            return call()
        except GenLayerError as error:
            if attempt == 3 or not any(text in str(error).lower() for text in (
                "returned invalid json", "502", "503", "bad gateway", "request to",
            )):
                raise
            print("PASSPORT_V6_READ_RETRY=" + str(attempt + 1), flush=True)
            time.sleep(2 ** attempt)


def _read(contract, method, args):
    return _retry_read(lambda: getattr(contract, method)(args=args).call(
        transaction_hash_variant=TransactionHashVariant.LATEST_FINAL))


def _write(contract, method, args, records, label):
    # Submit once, record the hash before polling. Only reads may be retried.
    if label not in records:
        records[label] = RPC_CLIENT.write_contract(
            contract.address, method, account=contract.account, args=args)
        print("PASSPORT_V6_TX=" + json.dumps({"step": label, "hash": records[label]}), flush=True)
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        receipt = _retry_read(lambda: RPC_CLIENT.get_transaction(records[label]))
        if receipt and receipt.get("status_name") == "FINALIZED":
            return _ok(receipt)
        time.sleep(3)
    raise AssertionError("Transaction did not finalize; resume using the printed hash, not a new write")


def _wait_children(parent_hash, success):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        parent = _retry_read(lambda: RPC_CLIENT.get_transaction(parent_hash))
        _ok(parent)
        children = parent.get("triggered_transactions") or []
        if children:
            assert len(children) == 1, children
            child = _retry_read(lambda: RPC_CLIENT.get_transaction(children[0]))
            if child and child.get("status_name") == "FINALIZED":
                assert tx_execution_succeeded(child) is success, child
                return {"hash": child["hash"], "status": child["status_name"],
                        "consensus": child.get("result_name"),
                        "execution": child["consensus_data"]["leader_receipt"][0]["execution_result"],
                        "result": child["consensus_data"]["leader_receipt"][0].get("result")}
        time.sleep(3)
    raise AssertionError("Callback did not finalize; inspect source transaction before retrying")


def _exercise(source_address, passport_address, fault=False, resume_job=None, resume_transactions=None):
    sf = get_contract_factory(contract_file_path=ROOT / "contracts/DeliveryOSPackagesV6.py")
    pf = get_contract_factory(contract_file_path=ROOT / (
        "tests/fixtures/FaultInjectingPassport.py" if fault else "contracts/DeliveryOSProviderPassportV2.py"))
    buyer_source = sf.build_contract(source_address, account=BUYER)
    provider_source = sf.build_contract(source_address, account=PROVIDER)
    passport = pf.build_contract(passport_address, account=BUYER)
    provider_passport = pf.build_contract(passport_address, account=PROVIDER)
    assert _read(passport, "get_source_contract", []).lower() == source_address.lower()
    preflight = verify_public_package(MANIFEST_URL, PREFIX, 2)
    job_id = resume_job or (("callback_fault_" if fault else "passport_v6_") + uuid.uuid4().hex[:12])
    transactions = dict(resume_transactions or {})
    if not resume_job:
        if not fault:
            _write(provider_passport, "set_my_profile", [
                "DeliveryOS test provider", "Public test wallet; fixture work only.", '["writing","research"]',
            ], transactions, "profile")
        _write(buyer_source, "create_job", [
            job_id, PROVIDER.address,
            "Deliver an installation guide and a JSON verification record for the public example service.",
            json.dumps([
                "The Markdown guide explicitly states the command python -m pip install -r requirements.txt.",
                "The JSON facts file explicitly contains verify_command equal to python -m deliveryos_agent.mcp_server.",
            ]), PREFIX, int(time.time()) + 3 * 86400, 0,
        ], transactions, "create")
        _write(provider_source, "accept_job", [job_id], transactions, "accept")
        _write(provider_source, "submit_delivery", [
            job_id, MANIFEST_URL, preflight["sha256"], preflight["size_bytes"],
        ], transactions, "submit")
        _write(buyer_source, "evaluate_delivery", [job_id, 1], transactions, "evaluate")
    job = _read(buyer_source, "get_job", [job_id])
    submission = _read(buyer_source, "get_submission", [job_id, 1])
    assert job["status"] == "ACCEPTED" and job["decision_source"] == "CONSENSUS", job
    assert job["latest_statuses"] == ["MET", "MET"]
    assert submission["content_fingerprint"] == preflight["content_fingerprint"]
    initial_child = _wait_children(transactions["evaluate"], success=not fault)
    count_before_sync = int(_read(passport, "get_provider_receipt_count", [PROVIDER.address]))
    already_recorded = bool(_read(passport, "get_outcome_for_job", [job_id, 1]))
    if fault:
        if not already_recorded:
            _write(passport, "enable_receipts", [], transactions, "enable_test_callback")
            dispatch = _read(buyer_source, "get_passport_dispatch", [job_id])
            remaining = int(dispatch["next_retry_epoch"]) - int(time.time()) + 2
            print("PASSPORT_V6_COOLDOWN_SECONDS=" + str(max(0, remaining)), flush=True)
            while remaining > 0:
                time.sleep(min(10, remaining))
                remaining = int(dispatch["next_retry_epoch"]) - int(time.time()) + 2
            _write(provider_source, "sync_passport_receipt", [job_id, 1], transactions, "recover")
        assert "recover" in transactions, "An existing recovered receipt needs its original recovery hash"
        recovered_child = _wait_children(transactions["recover"], success=True)
    else:
        recovered_child = None
    receipt = _read(passport, "get_outcome_for_job", [job_id, 1])
    receipt_fields = {key: value for key, value in receipt.items() if key != "receipt_id"}
    expected_id = hashlib.sha256(json.dumps(
        receipt_fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert receipt["receipt_id"] == expected_id
    assert receipt["evidence_fingerprint"] == preflight["content_fingerprint"]
    assert receipt["source_contract"].lower() == source_address.lower()
    assert receipt["verdict"] == job["status"] and receipt["decided_epoch"] == job["decided_epoch"]
    final_count = int(_read(passport, "get_provider_receipt_count", [PROVIDER.address]))
    assert final_count == count_before_sync + (1 if fault and not already_recorded else 0)
    _write(buyer_source, "sync_passport_receipt", [job_id, 1], transactions, "duplicate_noop")
    assert int(_read(passport, "get_provider_receipt_count", [PROVIDER.address])) == final_count
    assert _read(buyer_source, "get_job", [job_id]) == job
    assert _read(buyer_source, "get_submission", [job_id, 1]) == submission
    assert _read(passport, "get_outcome_for_job", [job_id, 1]) == receipt
    local_source = (ROOT / "contracts/DeliveryOSPackagesV6.py").read_bytes().replace(b"\r\n", b"\n")
    local_passport = (ROOT / (
        "tests/fixtures/FaultInjectingPassport.py" if fault else
        "contracts/DeliveryOSProviderPassportV2.py")).read_bytes().replace(b"\r\n", b"\n")
    assert _code(source_address) == local_source
    assert _code(passport_address) == local_passport
    record = {
        "test_only_fault_fixture": fault,
        "source_address": source_address, "passport_address": passport_address,
        "job_id": job_id, "transactions": transactions, "job": job, "receipt": receipt,
        "initial_callback": initial_child, "recovered_callback": recovered_child,
        "source_sha256_lf": hashlib.sha256(local_source).hexdigest(),
        "passport_sha256_lf": hashlib.sha256(local_passport).hexdigest(),
        "verified_at": int(time.time()), "provider_receipt_count": final_count,
    }
    print("PASSPORT_V6_EVIDENCE=" + json.dumps(record, sort_keys=True), flush=True)
    return record


@pytest.mark.integration
def test_production_v6_finalized_receipt_and_duplicate_noop():
    source = os.environ.get("DELIVERYOS_V6_TEST_ADDRESS")
    passport = os.environ.get("DELIVERYOS_V6_TEST_PASSPORT")
    if not source or not passport:
        pytest.skip("Provide the deployed V6 addresses for the live smoke test")
    resume_job = os.environ.get("DELIVERYOS_V6_RESUME_JOB")
    resume_transactions = json.loads(os.environ.get("DELIVERYOS_V6_RESUME_TRANSACTIONS", "{}"))
    _exercise(source, passport, resume_job=resume_job, resume_transactions=resume_transactions)


@pytest.mark.integration
def test_controlled_failed_callback_then_recovery():
    resume_source = os.environ.get("DELIVERYOS_V6_FAULT_RESUME_ADDRESS")
    if resume_source:
        _exercise(resume_source, os.environ["DELIVERYOS_V6_FAULT_RESUME_PASSPORT"], fault=True,
            resume_job=os.environ["DELIVERYOS_V6_FAULT_RESUME_JOB"],
            resume_transactions=json.loads(os.environ["DELIVERYOS_V6_FAULT_RESUME_TRANSACTIONS"]))
        return
    transactions = {}
    pf = get_contract_factory(contract_file_path=ROOT / "tests/fixtures/FaultInjectingPassport.py")
    deployed_passport = _ok(pf.deploy_contract_tx(
        args=[], account=BUYER, wait_transaction_status=TransactionStatus.FINALIZED))
    passport_address = extract_contract_address(deployed_passport)
    sf = get_contract_factory(contract_file_path=ROOT / "contracts/DeliveryOSPackagesV6.py")
    deployed_source = _ok(sf.deploy_contract_tx(
        args=[passport_address], account=BUYER, wait_transaction_status=TransactionStatus.FINALIZED))
    source_address = extract_contract_address(deployed_source)
    passport = pf.build_contract(passport_address, account=BUYER)
    _write(passport, "set_source_contract", [source_address], transactions, "bind_fault_fixture")
    print("PASSPORT_V6_FAULT_DEPLOY=" + json.dumps({
        "source_address": source_address, "passport_address": passport_address,
        "source_deploy": deployed_source["hash"], "passport_deploy": deployed_passport["hash"],
        **transactions,
    }), flush=True)
    _exercise(source_address, passport_address, fault=True)
