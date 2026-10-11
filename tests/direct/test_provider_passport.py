"""Security and indexing tests for the wallet-bound Provider Passport."""

import json
from datetime import datetime, timezone

import pytest


SOURCE = "0x" + "f" * 40
FINGERPRINT = "a" * 64
JOB = "passport_job_001"
TEST_NOW = int(datetime(2026, 10, 12, 12, tzinfo=timezone.utc).timestamp())


@pytest.fixture(params=["DeliveryOSProviderPassport", "DeliveryOSProviderPassportV2"])
def passport(direct_vm, direct_deploy, direct_alice, request):
    direct_vm.warp("2026-10-12T12:00:00Z")
    direct_vm.sender = direct_alice
    contract = direct_deploy("contracts/" + request.param + ".py")
    contract.set_source_contract(SOURCE)
    return contract, direct_vm, direct_alice


def record(contract, job_id=JOB, buyer="0x" + "1" * 40,
           provider="0x" + "2" * 40, version=1, verdict="ACCEPTED",
           fingerprint=FINGERPRINT, statuses='["MET","MET"]', epoch=None):
    return contract.record_consensus_outcome(
        job_id, buyer, provider, version, verdict, fingerprint,
        statuses, TEST_NOW - 1 if epoch is None else epoch,
    )


def test_source_is_owner_configured_once_and_not_replaceable(passport, direct_charlie):
    contract, vm, owner = passport
    assert contract.get_source_contract().lower() == SOURCE
    vm.sender = direct_charlie
    with vm.expect_revert("Only the registry owner"):
        contract.set_source_contract("0x" + "e" * 40)
    vm.sender = owner
    with vm.expect_revert("already configured"):
        contract.set_source_contract("0x" + "e" * 40)


def test_only_source_can_create_valid_immutable_receipts(passport, direct_charlie):
    contract, vm, _owner = passport
    vm.sender = direct_charlie
    with vm.expect_revert("Only the configured DeliveryOS"):
        record(contract)

    vm.sender = SOURCE
    receipt_id = record(contract)
    receipt = contract.get_receipt_by_id(receipt_id)
    assert receipt["schema"] == "DELIVERYOS_PROVIDER_RECEIPT_V1"
    assert receipt["source_contract"] == SOURCE
    assert receipt["provider"] == "0x" + "2" * 40
    assert receipt["verdict"] == "ACCEPTED"
    assert receipt["decision_source"] == "CONSENSUS"
    assert receipt["finality"] == "SOURCE_TRANSACTION_FINALIZED"
    assert contract.get_provider_receipt_count("0x" + "2" * 40) == 1
    assert contract.get_provider_receipt("0x" + "2" * 40, 0)["receipt_id"] == receipt_id
    assert contract.get_receipt_count() == 1


def test_duplicate_source_callback_is_idempotent_but_conflicts_revert(passport):
    contract, vm, _owner = passport
    vm.sender = SOURCE
    first = record(contract)
    assert record(contract) == first
    assert contract.get_receipt_count() == 1
    with vm.expect_revert("conflicting receipt"):
        record(contract, fingerprint="b" * 64)
    assert contract.get_provider_receipt_count("0x" + "2" * 40) == 1


@pytest.mark.parametrize(("verdict", "statuses"), [
    ("BUYER_APPROVED", '["MET"]'),
    ("ACCEPTED", '["MET","UNCLEAR"]'),
    ("REJECTED", '["UNCLEAR"]'),
    ("INCONCLUSIVE", '["MET"]'),
    ("INCONCLUSIVE", '["NOT_MET","UNCLEAR"]'),
    ("ACCEPTED", '["MET","UNKNOWN"]'),
])
def test_receipt_verdict_and_criterion_vector_must_be_consistent(passport, verdict, statuses):
    contract, vm, _owner = passport
    vm.sender = SOURCE
    with vm.expect_revert():
        record(contract, job_id=JOB + verdict, verdict=verdict, statuses=statuses)
    assert contract.get_receipt_count() == 0


def test_receipt_rejects_self_dealing_bad_hash_epoch_and_index(passport, direct_charlie):
    contract, vm, _owner = passport
    vm.sender = SOURCE
    with vm.expect_revert("different wallets"):
        record(contract, buyer="0x" + "2" * 40, provider="0x" + "2" * 40)
    with vm.expect_revert("hexadecimal"):
        record(contract, job_id="passport_bad_hash", fingerprint="z" * 64)
    with vm.expect_revert("Decision time is invalid"):
        record(contract, job_id="passport_future", epoch=TEST_NOW + 1000)
    with vm.expect_revert("out of range"):
        contract.get_provider_receipt("0x" + "2" * 40, 0)
    assert contract.get_receipt_count() == 0


def test_profiles_are_wallet_owned_bounded_and_explicitly_unverified(passport, direct_charlie):
    contract, vm, owner = passport
    vm.sender = owner
    contract.set_my_profile("  Builder  ", "  I make public tools.  ", '["research","writing"]')
    owner_hex = "0x" + owner.hex() if isinstance(owner, bytes) else owner.as_hex
    profile = contract.get_provider_profile(owner_hex)
    assert profile["display_name"] == "Builder"
    assert profile["bio"] == "I make public tools."
    assert profile["capabilities"] == ["research", "writing"]
    assert profile["profile_claims"] == "SELF_REPORTED_NOT_VALIDATED"
    assert profile["registered"] is True
    assert profile["receipt_count"] == 0
    assert contract.get_profile_count() == 1
    with vm.expect_revert("unique"):
        contract.set_my_profile("Builder", "", '["research","research"]')
    with vm.expect_revert():
        contract.set_my_profile("Builder", "", json.dumps(["x" * 33]))

    vm.sender = direct_charlie
    contract.set_my_profile("Other wallet", "", '[]')
    assert contract.get_profile_count() == 2
    assert contract.get_profile_wallet(0).lower() == owner_hex
