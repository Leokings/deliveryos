from types import SimpleNamespace

import pytest

from deliveryos_agent.client import DeliveryOSClient


SOURCE = "0x" + "a" * 40
PASSPORT = "0x" + "b" * 40
BUYER = "0x" + "c" * 40
PROVIDER = "0x" + "d" * 40


@pytest.fixture
def service(monkeypatch):
    client = DeliveryOSClient(SOURCE, client=object(), passport_contract_address=PASSPORT)
    client.account = SimpleNamespace(address=BUYER)
    client.get_job = lambda _: {"protocol": "DELIVERYOS_PACKAGES_V6", "current_version": 1,
        "status": "ACCEPTED", "decision_source": "CONSENSUS", "buyer": BUYER, "provider": PROVIDER,
        "review_deadline_epoch": 1}
    client._read = lambda *_: {"passport_contract_address": PASSPORT, "version": 1,
        "next_retry_epoch": 100, "receipt_eligible": True}
    client._passport_read = lambda name, _: SOURCE if name == "get_source_contract" else {}
    client._write = lambda name, args: {"method": name, "args": args}
    monkeypatch.setattr("deliveryos_agent.client.time.time", lambda: 101)
    return client


def test_v6_sync_uses_frozen_version_and_ignores_old_review_cutoff(service):
    assert service.passport_receipt_status("job_12345")["receipt_recorded"] is False
    assert service.sync_passport_receipt("job_12345", 1) == {
        "method": "sync_passport_receipt", "args": ["job_12345", 1]}
    guidance = service.next_actions("job_12345")
    assert guidance["job_url_path"] is None
    assert "deliveryos_sync_passport_receipt" in guidance["possible_tools"]


@pytest.mark.parametrize("version", [0, True, 2])
def test_v6_sync_rejects_invalid_or_stale_version(service, version):
    with pytest.raises(ValueError):
        service.sync_passport_receipt("job_12345", version)


def test_v6_sync_rejects_observers_and_cooldown(service, monkeypatch):
    service.account = SimpleNamespace(address="0x" + "e" * 40)
    with pytest.raises(ValueError, match="Only a party"):
        service.sync_passport_receipt("job_12345", 1)
    service.account = SimpleNamespace(address=BUYER)
    monkeypatch.setattr("deliveryos_agent.client.time.time", lambda: 99)
    with pytest.raises(ValueError, match="cooldown"):
        service.sync_passport_receipt("job_12345", 1)


def test_status_rejects_wrong_companion_or_source(service):
    service.passport_contract_address = "0x" + "e" * 40
    with pytest.raises(ValueError, match="does not match"):
        service.passport_receipt_status("job_12345")
    service.passport_contract_address = PASSPORT
    service._passport_read = lambda *_: "0x" + "e" * 40
    with pytest.raises(ValueError, match="not bound"):
        service.passport_receipt_status("job_12345")
