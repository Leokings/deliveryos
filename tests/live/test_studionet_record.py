"""Independent, read-only verification of the saved final-source run."""

import base64
import hashlib
import json
from pathlib import Path
import time
from urllib import request

import pytest

from deliveryos_agent import DeliveryOSClient


ROOT = Path(__file__).resolve().parents[2]
RECORD = json.loads((ROOT / "deployments" / "studionet.json").read_text(encoding="utf-8"))


def _retry_read(function):
    for attempt in range(5):
        try:
            return function()
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2)


@pytest.mark.integration
def test_saved_studionet_receipts_state_and_source():
    service = DeliveryOSClient(RECORD["contract_address"])
    case = RECORD["acceptance_test"]
    manual = RECORD["manual_agent_test"]
    revision = RECORD["revision_test"]
    expiry = RECORD["expiry_test"]
    browser = RECORD["browser_wallet_test"]
    for hash_ in [*case["transactions"].values(), *manual["transactions"].values(),
                  *revision["transactions"].values(),
                  expiry["transactions"]["propose"], expiry["transactions"]["accept_job"],
                  expiry["transactions"]["expiry"], browser["transaction"]]:
        receipt = _retry_read(lambda: service.transaction_status(hash_))
        assert receipt["finalized_success"] is True, receipt

    early = _retry_read(lambda: service.transaction_status(expiry["transactions"]["premature_expiry"]))
    assert early["status"] == "FINALIZED" and early["finalized_success"] is False, early
    expiry_job = _retry_read(lambda: service.get_job(expiry["job_id"]))
    assert expiry_job["status"] == expiry["expected_status"]
    assert expiry_job["decision_source"] == expiry["expected_decision_source"]
    assert expiry_job["current_version"] == 0
    browser_job = _retry_read(lambda: service.get_job(browser["job_id"]))
    assert browser_job["status"] == browser["expected_status"]
    assert browser_job["buyer"].lower() == browser["buyer"].lower()

    job = _retry_read(lambda: service.get_job(case["job_id"]))
    submission = _retry_read(lambda: service.get_submission(case["job_id"], 1))
    assert job["status"] == case["expected_status"]
    assert job["decision_source"] == case["expected_decision_source"]
    assert job["latest_statuses"] == case["expected_criterion_statuses"]
    assert job["evidence_prefix"] == "https://raw.githubusercontent.com/Leokings/digital-deliverable-verifier/"
    assert submission["verdict"] == case["expected_status"]
    assert submission["sha256"] == case["evidence_sha256"]
    assert submission["size_bytes"] == case["evidence_size_bytes"]
    assert service.pin_public_evidence(case["evidence_url"])["sha256"] == case["evidence_sha256"]

    manual_job = _retry_read(lambda: service.get_job(manual["job_id"]))
    manual_submission = _retry_read(lambda: service.get_submission(manual["job_id"], 1))
    assert manual_job["status"] == manual["expected_status"]
    assert manual_job["decision_source"] == manual["expected_decision_source"]
    assert manual_submission["verdict"] == manual["expected_status"]
    assert manual_submission["sha256"] == manual["evidence_sha256"]

    revision_job = _retry_read(lambda: service.get_job(revision["job_id"]))
    assert revision_job["status"] == revision["expected_status"]
    assert revision_job["decision_source"] == revision["expected_decision_source"]
    assert revision_job["revision_count"] == 1
    for number in (1, 2):
        expected = revision[f"version_{number}"]
        version = _retry_read(lambda n=number: service.get_submission(revision["job_id"], n))
        assert version["sha256"] == expected["evidence_sha256"]
        assert version["statuses"] == expected["criterion_statuses"]
        assert version["verdict"] == expected["verdict"]

    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "gen_getContractCode",
                          "params": [RECORD["contract_address"]]}).encode()
    call = request.Request(RECORD["rpc_url"], data=payload,
                           headers={"Content-Type": "application/json",
                                    "Accept": "application/json",
                                    "User-Agent": "DeliveryOS-Studionet-Audit/1.0"})
    def get_code():
        with request.urlopen(call, timeout=30) as response:
            reply = json.load(response)
        assert "error" not in reply, reply
        return base64.b64decode(reply["result"], validate=True)

    deployed = _retry_read(get_code)
    source = (ROOT / "contracts" / "DeliveryOS.py").read_bytes().replace(b"\r\n", b"\n")
    assert deployed == source
    assert hashlib.sha256(source).hexdigest() == RECORD["source_sha256_lf"]
