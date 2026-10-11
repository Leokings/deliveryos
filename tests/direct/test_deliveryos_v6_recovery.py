"""V6 recovery guards. Direct mode mocks callbacks, not network consensus."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from test_deliveryos_v5_passport_flow import prepare_job


SOURCE = "0x" + hashlib.sha256(str(Path("contracts/DeliveryOSPackagesV6.py").resolve()).encode()).digest()[:20].hex()
PASSPORT = "0x" + "e" * 40


@pytest.fixture
def flow(direct_vm, direct_deploy, direct_alice, direct_bob):
    vm = direct_vm
    vm.warp("2026-10-08T12:00:00Z")
    vm.sender = direct_alice
    contract = direct_deploy("contracts/DeliveryOSPackagesV6.py", PASSPORT)
    messages = []
    vm.recorded_outcome = {}
    vm.passport_source = SOURCE

    def hook(_vm, request):
        if "CallContract" in request:
            from genlayer.py import calldata
            call = request["CallContract"]["calldata"]
            result = vm.passport_source if call["method"] == "get_source_contract" else vm.recorded_outcome
            return bytes([0]) + calldata.encode(result)
        if "PostMessage" in request:
            messages.append(request["PostMessage"])
            return {"ok": None}
        return None

    vm._gl_call_hook = hook
    return contract, vm, direct_alice, direct_bob, messages


@pytest.mark.parametrize(("statuses", "verdict"), [
    (["MET"], "ACCEPTED"), (["NOT_MET"], "REJECTED"), (["UNCLEAR"], "INCONCLUSIVE"),
])
def test_missing_receipt_retries_exact_stored_consensus_after_cutoff(flow, statuses, verdict):
    source, vm, buyer, provider, messages = flow
    job_id = "recovery_terminal_" + verdict
    prepare_job(source, vm, buyer, provider, job_id, max_revisions=0)
    vm.mock_llm(r".*untrusted_documents.*", json.dumps({"statuses": statuses}))
    source.evaluate_delivery(job_id, 1)
    job = source.get_job(job_id)
    submission = source.get_submission(job_id, 1)
    assert job["status"] == verdict and len(messages) == 1
    first = messages[0]
    with vm.expect_revert("cooldown"):
        source.sync_passport_receipt(job_id, 1)
    # Even after the review cutoff, a stored terminal result can be delivered.
    vm.warp("2026-11-10T12:00:00Z")
    vm.sender = buyer
    source.sync_passport_receipt(job_id, 1)
    assert len(messages) == 2
    assert messages[1]["calldata"] == first["calldata"]
    assert messages[1]["on"] == "finalized"
    assert source.get_job(job_id) == job
    assert source.get_submission(job_id, 1) == submission
    dispatch = source.get_passport_dispatch(job_id)
    assert dispatch["receipt_eligible"] is True
    assert dispatch["next_retry_epoch"] == dispatch["last_dispatch_epoch"] + 120
    with vm.expect_revert("cooldown"):
        source.sync_passport_receipt(job_id, 1)


def test_sync_guards_roles_versions_binding_and_existing_receipt(flow, direct_charlie):
    source, vm, buyer, provider, messages = flow
    job_id = "recovery_guard_001"
    prepare_job(source, vm, buyer, provider, job_id, max_revisions=0)
    vm.mock_llm(r".*untrusted_documents.*", '{"statuses":["MET"]}')
    source.evaluate_delivery(job_id, 1)
    vm.sender = direct_charlie
    with vm.expect_revert("Only a party"):
        source.sync_passport_receipt(job_id, 1)
    vm.sender = buyer
    with vm.expect_revert("version changed"):
        source.sync_passport_receipt(job_id, 2)
    vm.passport_source = "0x" + "d" * 40
    with vm.expect_revert("not bound"):
        source.sync_passport_receipt(job_id, 1)
    vm.passport_source = SOURCE
    vm.recorded_outcome = {"receipt_id": "a" * 64}
    before = source.get_passport_dispatch(job_id)
    source.sync_passport_receipt(job_id, 1)
    source.sync_passport_receipt(job_id, 1)
    assert len(messages) == 1
    assert source.get_passport_dispatch(job_id) == before


@pytest.mark.parametrize("outcome", ["pending", "revision", "manual", "timeout"])
def test_non_consensus_or_non_terminal_outcomes_cannot_mint_receipts(flow, outcome):
    source, vm, buyer, provider, messages = flow
    job_id = "recovery_excluded_" + outcome
    prepare_job(source, vm, buyer, provider, job_id, max_revisions=1)
    if outcome == "revision":
        vm.mock_llm(r".*untrusted_documents.*", '{"statuses":["NOT_MET"]}')
        source.evaluate_delivery(job_id, 1)
    elif outcome == "manual":
        vm.sender = buyer
        source.accept_delivery(job_id, 1)
    elif outcome == "timeout":
        vm.warp("2026-11-10T12:00:00Z")
        source.close_unreviewed(job_id)
    with vm.expect_revert("Only a terminal consensus"):
        source.sync_passport_receipt(job_id, 1)
    assert messages == []
    assert source.get_passport_dispatch(job_id)["receipt_eligible"] is False


def test_v2_lookup_matches_immutable_receipt_and_rejects_invalid_keys(direct_vm, direct_deploy, direct_alice):
    vm = direct_vm
    vm.warp("2026-10-08T12:00:00Z")
    vm.sender = direct_alice
    contract = direct_deploy("contracts/DeliveryOSProviderPassportV2.py")
    contract.set_source_contract(SOURCE)
    assert contract.get_outcome_for_job("lookup_job_001", 1) == {}
    vm.sender = SOURCE
    epoch = int(datetime(2026, 10, 8, 11, tzinfo=timezone.utc).timestamp())
    receipt_id = contract.record_consensus_outcome(
        "lookup_job_001", "0x" + "1" * 40, "0x" + "2" * 40, 1,
        "ACCEPTED", "a" * 64, '["MET"]', epoch)
    assert contract.get_outcome_for_job("lookup_job_001", 1) == contract.get_receipt_by_id(receipt_id)
    assert contract.get_outcome_for_job("lookup_job_001", 2) == {}
    with vm.expect_revert("positive"):
        contract.get_outcome_for_job("lookup_job_001", 0)
    with vm.expect_revert():
        contract.get_outcome_for_job("x", 1)
