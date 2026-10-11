# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

# SPDX-License-Identifier: MIT

"""TEST ONLY: deliberately rejects callbacks until its owner enables receipts.

Profiles and capability tags are self-reported. Receipts can only be written
by the one-time configured DeliveryOS V6 source, which calls this contract
after a terminal validator decision has finalized. There is deliberately no
aggregate trust score, free-form review, payment, or caller-supplied verdict.
"""

from genlayer import *
from datetime import datetime, timezone
import hashlib
import json


_UserError = gl.vm.UserError


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
FINAL_VERDICTS = ("ACCEPTED", "REJECTED", "INCONCLUSIVE")
CRITERION_STATUSES = ("MET", "NOT_MET", "UNCLEAR")
MAX_CAPABILITIES = 8
MAX_CAPABILITIES_JSON_BYTES = 512
MAX_CRITERION_JSON_BYTES = 160


def _caller() -> str:
    sender = gl.message.sender_address
    if isinstance(sender, str):
        sender = Address(sender)
    return sender.as_hex.lower()


def _address(value: str, label: str) -> str:
    if isinstance(value, Address):
        value = value.as_hex
    if not isinstance(value, str) or len(value) != 42 or value[:2].lower() != "0x":
        raise _UserError(f"{label} must be a wallet address")
    try:
        normalized = Address(value).as_hex.lower()
    except Exception:
        raise _UserError(f"{label} must be a 20-byte address")
    if normalized == ZERO_ADDRESS:
        raise _UserError(f"{label} cannot be the zero address")
    return normalized


def _bounded_text(value: str, label: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise _UserError(f"{label} must be text")
    cleaned = value.strip()
    if len(cleaned) < minimum or len(cleaned) > maximum or "\x00" in cleaned:
        raise _UserError(f"{label} must contain {minimum}-{maximum} characters")
    return cleaned


def _job_id(value: str) -> str:
    cleaned = _bounded_text(value, "Job ID", 8, 64)
    for character in cleaned:
        if character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-":
            raise _UserError("Job ID may contain only letters, numbers, _ and -")
    return cleaned


def _fingerprint(value: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise _UserError("Evidence fingerprint must be a 64-character SHA-256")
    lowered = value.lower()
    for character in lowered:
        if character not in "0123456789abcdef":
            raise _UserError("Evidence fingerprint must be hexadecimal")
    return lowered


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class FaultInjectingPassport(gl.Contract):
    callback_enabled: bool
    owner: Address
    source_contract: Address
    profiles: TreeMap[str, str]
    profile_wallets: DynArray[str]
    provider_receipt_counts: TreeMap[str, u256]
    provider_receipt_keys: TreeMap[str, str]
    receipts: TreeMap[str, str]
    receipt_by_id: TreeMap[str, str]
    receipt_count: u256

    def __init__(self):
        self.callback_enabled = False
        self.owner = gl.message.sender_address
        self.source_contract = Address(ZERO_ADDRESS)
        self.receipt_count = u256(0)

    @gl.public.write
    def enable_receipts(self) -> None:
        if gl.message.sender_address != self.owner:
            raise _UserError("Only the test fixture owner may enable receipts")
        self.callback_enabled = True

    @gl.public.write
    def set_source_contract(self, contract_address: str) -> str:
        """Owner-only one-time binding to the deployed DeliveryOS V6 contract."""
        if gl.message.sender_address != self.owner:
            raise _UserError("Only the registry owner may configure the source")
        if self.source_contract.as_hex.lower() != ZERO_ADDRESS:
            raise _UserError("Source contract is already configured")
        normalized = _address(contract_address, "Source contract")
        self.source_contract = Address(normalized)
        return normalized

    @gl.public.write
    def set_my_profile(self, display_name: str, bio: str, capabilities_json: str) -> None:
        """Create or update only the connected wallet's public profile."""
        wallet = _caller()
        name = _bounded_text(display_name, "Display name", 1, 48)
        if not isinstance(bio, str) or len(bio) > 280 or "\x00" in bio:
            raise _UserError("Bio must be at most 280 characters")
        if (not isinstance(capabilities_json, str) or
                len(capabilities_json.encode("utf-8")) > MAX_CAPABILITIES_JSON_BYTES):
            raise _UserError("Capabilities JSON is too long")
        try:
            capabilities = json.loads(capabilities_json)
        except Exception:
            raise _UserError("Capabilities must be a JSON array")
        if not isinstance(capabilities, list) or len(capabilities) > MAX_CAPABILITIES:
            raise _UserError("Provide at most eight capability tags")
        normalized = []
        for item in capabilities:
            tag = _bounded_text(item, "Capability", 2, 32).lower()
            if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in tag):
                raise _UserError("Capabilities may use lowercase letters, numbers, and hyphens")
            if tag in normalized:
                raise _UserError("Capability tags must be unique")
            normalized.append(tag)

        if not self.profiles.get(wallet, ""):
            self.profile_wallets.append(wallet)
        self.profiles[wallet] = _canonical({
            "wallet": wallet,
            "display_name": name,
            "bio": bio.strip(),
            "capabilities": normalized,
            "profile_claims": "SELF_REPORTED_NOT_VALIDATED",
        })

    @gl.public.write
    def record_consensus_outcome(
        self,
        job_id: str,
        buyer: str,
        provider: str,
        version: u256,
        verdict: str,
        evidence_fingerprint: str,
        criterion_statuses_json: str,
        decided_epoch: u256,
    ) -> str:
        """Accept a receipt only from the pinned V6 finality callback."""
        if not self.callback_enabled:
            raise _UserError("[TEST_ONLY] Simulated callback unavailability")
        source = self.source_contract.as_hex.lower()
        if source == ZERO_ADDRESS:
            raise _UserError("Provider Passport source is not configured")
        if _caller() != source:
            raise _UserError("Only the configured DeliveryOS V6 contract may record outcomes")

        clean_job_id = _job_id(job_id)
        clean_buyer = _address(buyer, "Buyer")
        clean_provider = _address(provider, "Provider")
        if clean_buyer == clean_provider:
            raise _UserError("Buyer and provider must be different wallets")
        version_number = int(version)
        if version_number < 1:
            raise _UserError("Receipt version must be positive")
        if verdict not in FINAL_VERDICTS:
            raise _UserError("Only terminal consensus outcomes can be recorded")
        fingerprint = _fingerprint(evidence_fingerprint)
        if (not isinstance(criterion_statuses_json, str) or
                len(criterion_statuses_json.encode("utf-8")) > MAX_CRITERION_JSON_BYTES):
            raise _UserError("Criterion status JSON is too long")
        try:
            statuses = json.loads(criterion_statuses_json)
        except Exception:
            raise _UserError("Criterion statuses must be a JSON array")
        if (not isinstance(statuses, list) or not 1 <= len(statuses) <= 4 or
                any(status not in CRITERION_STATUSES for status in statuses)):
            raise _UserError("Criterion statuses must contain 1-4 valid results")
        if verdict == "ACCEPTED" and not all(status == "MET" for status in statuses):
            raise _UserError("Accepted receipts require every criterion to be MET")
        if verdict == "REJECTED" and "NOT_MET" not in statuses:
            raise _UserError("Rejected receipts require a NOT_MET criterion")
        if verdict == "INCONCLUSIVE" and ("UNCLEAR" not in statuses or "NOT_MET" in statuses):
            raise _UserError("Inconclusive receipts require UNCLEAR and no NOT_MET result")

        decision_epoch = int(decided_epoch)
        if decision_epoch <= 0 or decision_epoch > int(datetime.now(timezone.utc).timestamp()):
            raise _UserError("Decision time is invalid")

        key = source + "#" + clean_job_id + "#" + str(version_number)
        existing = self.receipts.get(key, "")
        fields = {
            "schema": "DELIVERYOS_PROVIDER_RECEIPT_V1",
            "chain_id": int(gl.message.chain_id),
            "source_contract": source,
            "job_id": clean_job_id,
            "buyer": clean_buyer,
            "provider": clean_provider,
            "version": version_number,
            "verdict": verdict,
            "decision_source": "CONSENSUS",
            "evidence_fingerprint": fingerprint,
            "criterion_statuses": statuses,
            "decided_epoch": decision_epoch,
            "finality": "SOURCE_TRANSACTION_FINALIZED",
        }
        receipt_id = hashlib.sha256(_canonical(fields).encode("utf-8")).hexdigest()
        if existing:
            prior = json.loads(existing)
            if prior.get("receipt_id") != receipt_id:
                raise _UserError("A conflicting receipt already exists for this job version")
            return receipt_id

        receipt = {"receipt_id": receipt_id, **fields}
        self.receipts[key] = _canonical(receipt)
        self.receipt_by_id[receipt_id] = key
        count = int(self.provider_receipt_counts.get(clean_provider, u256(0)))
        self.provider_receipt_keys[clean_provider + "#" + str(count)] = key
        self.provider_receipt_counts[clean_provider] = u256(count + 1)
        self.receipt_count = self.receipt_count + u256(1)
        return receipt_id

    @gl.public.view
    def get_owner(self) -> str:
        return self.owner.as_hex

    @gl.public.view
    def get_source_contract(self) -> str:
        return self.source_contract.as_hex

    @gl.public.view
    def get_provider_profile(self, wallet_address: str) -> dict:
        wallet = _address(wallet_address, "Wallet")
        encoded = self.profiles.get(wallet, "")
        if encoded:
            profile = json.loads(encoded)
            registered = True
        else:
            profile = {"wallet": wallet, "display_name": "", "bio": "", "capabilities": [],
                       "profile_claims": "SELF_REPORTED_NOT_VALIDATED"}
            registered = False
        profile["registered"] = registered
        profile["receipt_count"] = int(self.provider_receipt_counts.get(wallet, u256(0)))
        return profile

    @gl.public.view
    def get_provider_receipt_count(self, wallet_address: str) -> u256:
        wallet = _address(wallet_address, "Wallet")
        return self.provider_receipt_counts.get(wallet, u256(0))

    @gl.public.view
    def get_provider_receipt(self, wallet_address: str, index: u256) -> dict:
        wallet = _address(wallet_address, "Wallet")
        index_number = int(index)
        count = int(self.provider_receipt_counts.get(wallet, u256(0)))
        if index_number >= count:
            raise _UserError("Provider receipt index is out of range")
        key = self.provider_receipt_keys[wallet + "#" + str(index_number)]
        return json.loads(self.receipts[key])

    @gl.public.view
    def get_outcome_for_job(self, job_id: str, version: u256) -> dict:
        """Read an immutable source/job/version receipt, or {} when absent."""
        clean_job_id = _job_id(job_id)
        version_number = int(version)
        if version_number < 1:
            raise _UserError("Receipt version must be positive")
        key = self.source_contract.as_hex.lower() + "#" + clean_job_id + "#" + str(version_number)
        encoded = self.receipts.get(key, "")
        return json.loads(encoded) if encoded else {}

    @gl.public.view
    def get_receipt_by_id(self, receipt_id: str) -> dict:
        clean_id = _fingerprint(receipt_id)
        key = self.receipt_by_id.get(clean_id, "")
        if not key:
            raise _UserError("Unknown receipt")
        return json.loads(self.receipts[key])

    @gl.public.view
    def get_profile_count(self) -> u256:
        return u256(len(self.profile_wallets))

    @gl.public.view
    def get_profile_wallet(self, index: u256) -> str:
        index_number = int(index)
        if index_number >= len(self.profile_wallets):
            raise _UserError("Profile index is out of range")
        return self.profile_wallets[index_number]

    @gl.public.view
    def get_receipt_count(self) -> u256:
        return self.receipt_count
