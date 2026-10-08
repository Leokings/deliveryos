"""Opt-in live clock-gate test for an ACTIVE, undelivered Studionet job."""

import json
import time
import uuid

from deliveryos_agent.client import DeliveryOSClient
from genlayer_py import create_account


CONTRACT = "0xef13Bfe9A9B0b4cE7EB4AfC2d8EDd8A6c6D43e40"
# Public test-only keys. Never fund or reuse these accounts beyond gasless Studionet.
BUYER_KEY = "0x" + "33" * 32
PROVIDER_KEY = "0x" + "44" * 32
PREFIX = "https://raw.githubusercontent.com/Leokings/digital-deliverable-verifier/"


def finalized(client, tx_hash: str, expect_success: bool):
    for _ in range(100):
        try:
            status = client.transaction_status(tx_hash)
        except Exception:
            time.sleep(3)
            continue
        if status["status"] == "FINALIZED":
            assert status["finalized_success"] is expect_success, status
            return status
        time.sleep(3)
    raise AssertionError(f"Transaction did not finalize: {tx_hash}")


def test_active_job_cannot_expire_early_and_expires_after_deadline():
    buyer = DeliveryOSClient(CONTRACT, BUYER_KEY)
    provider = DeliveryOSClient(CONTRACT, PROVIDER_KEY)
    job_id = "expiry_" + uuid.uuid4().hex[:18]
    due = int(time.time()) + 180
    provider_address = create_account(PROVIDER_KEY).address
    transactions = {}
    print("DELIVERYOS_EXPIRY_JOB=" + job_id, flush=True)

    transactions["propose"] = buyer.create_job(
        job_id, provider_address,
        "Deliver a public UTF-8 installation note that identifies an exact installation command.",
        ["The submitted note includes the command python -m pip install -r requirements.txt."],
        PREFIX, due, 0,
    )["transaction_hash"]
    finalized(buyer, transactions["propose"], True)

    transactions["accept_job"] = provider.accept_job(job_id)["transaction_hash"]
    finalized(provider, transactions["accept_job"], True)
    assert buyer.get_job(job_id)["status"] == "ACTIVE"

    transactions["premature_expiry"] = buyer.expire_undelivered(job_id)["transaction_hash"]
    finalized(buyer, transactions["premature_expiry"], False)
    assert buyer.get_job(job_id)["status"] == "ACTIVE"

    while time.time() <= due + 4:
        time.sleep(2)
    transactions["expiry"] = buyer.expire_undelivered(job_id)["transaction_hash"]
    finalized(buyer, transactions["expiry"], True)
    job = buyer.get_job(job_id)
    assert job["status"] == "EXPIRED", job
    assert job["decision_source"] == "DEADLINE", job
    assert job["current_version"] == 0, job
    print("DELIVERYOS_EXPIRY_RECORD=" + json.dumps({
        "contract_address": CONTRACT, "job_id": job_id,
        "due_epoch": due, "transactions": transactions,
        "status": job["status"], "decision_source": job["decision_source"],
    }, sort_keys=True), flush=True)
