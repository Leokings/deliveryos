import hashlib
import json
from types import SimpleNamespace

import pytest

from deliveryos_agent.client import DeliveryOSClient
from deliveryos_agent.packages import build_manifest, verify_public_package


PREFIX = "https://raw.githubusercontent.com/example/deliveryos/"
SOURCE_COMMIT = "a" * 40
MANIFEST_COMMIT = "b" * 40
MANIFEST_URL = PREFIX + MANIFEST_COMMIT + "/package.json"
GUIDE = b"Install: npm install example-service\n"
FACTS = b'{"verify":"example-service --version"}'


def files():
    return [
        {"path": "guide.md", "body": GUIDE, "media_type": "text/markdown", "criteria": [0]},
        {"path": "facts.json", "body": FACTS, "media_type": "application/json", "criteria": [1]},
    ]


def install_fetch(monkeypatch, manifest, guide=GUIDE, facts=FACTS):
    payloads = {
        MANIFEST_URL: manifest,
        PREFIX + SOURCE_COMMIT + "/guide.md": guide,
        PREFIX + SOURCE_COMMIT + "/facts.json": facts,
    }
    monkeypatch.setattr(DeliveryOSClient, "fetch_public_evidence_bytes",
                        classmethod(lambda cls, url: payloads[url]))


def test_builder_and_preflight_match_contract_format(monkeypatch):
    manifest = build_manifest(PREFIX, SOURCE_COMMIT, files(), 2)
    parsed = json.loads(manifest)
    assert parsed["source_commit"] == SOURCE_COMMIT
    assert parsed["files"][0]["url"].startswith(PREFIX + SOURCE_COMMIT)
    assert hashlib.sha256(manifest).hexdigest() != ""
    install_fetch(monkeypatch, manifest)
    evidence = verify_public_package(MANIFEST_URL, PREFIX, 2)
    assert evidence["sha256"] == hashlib.sha256(manifest).hexdigest()
    assert evidence["size_bytes"] == len(manifest)
    assert evidence["file_count"] == 2
    assert evidence["total_bytes"] == len(GUIDE) + len(FACTS)
    with pytest.raises(ValueError, match="Revision must change"):
        verify_public_package(MANIFEST_URL, PREFIX, 2,
                              previous_fingerprint=evidence["content_fingerprint"])


def test_builder_rejects_unsafe_paths_and_uncovered_criteria():
    for path in ("../secret", "/absolute", "nested/../secret", "folder//file"):
        specs = files()
        specs[0]["path"] = path
        with pytest.raises(ValueError, match="path is unsafe"):
            build_manifest(PREFIX, SOURCE_COMMIT, specs, 2)
    specs = files()
    specs[1]["criteria"] = [0]
    with pytest.raises(ValueError, match="Every criterion"):
        build_manifest(PREFIX, SOURCE_COMMIT, specs, 2)


def test_preflight_rejects_changed_file_and_manifest(monkeypatch):
    manifest = build_manifest(PREFIX, SOURCE_COMMIT, files(), 2)
    install_fetch(monkeypatch, manifest, guide=b"Changed bytes")
    with pytest.raises(ValueError, match="do not match"):
        verify_public_package(MANIFEST_URL, PREFIX, 2)
    install_fetch(monkeypatch, json.dumps(json.loads(manifest), indent=2).encode())
    with pytest.raises(ValueError, match="canonical JSON"):
        verify_public_package(MANIFEST_URL, PREFIX, 2)


def test_package_client_preflights_before_signed_write(monkeypatch):
    manifest = build_manifest(PREFIX, SOURCE_COMMIT, files(), 2)
    install_fetch(monkeypatch, manifest)

    class FakeSDK:
        def __init__(self):
            self.writes = []

        def read_contract(self, address, name, args, transaction_hash_variant):
            assert name == "get_job"
            return {"status": "ACTIVE", "protocol": "DELIVERYOS_PACKAGES_V2",
                    "evidence_prefix": PREFIX, "criteria": ["criterion 0", "criterion 1"]}

        def write_contract(self, address, name, account, args):
            self.writes.append((name, args))
            return "0x" + "c" * 64

    sdk = FakeSDK()
    client = DeliveryOSClient("0x" + "d" * 40, client=sdk)
    client.account = SimpleNamespace(address="0x" + "e" * 40)
    result = client.submit_delivery("package_example_01", MANIFEST_URL)
    assert result["evidence"]["file_count"] == 2
    assert sdk.writes == [("submit_delivery", ["package_example_01", MANIFEST_URL,
                                              hashlib.sha256(manifest).hexdigest(), len(manifest)])]
