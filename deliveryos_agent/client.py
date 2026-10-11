"""Studionet client. Writes are signed by the caller's own wallet."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from urllib import error, request
from urllib.parse import urlsplit

from genlayer_py import create_account
from genlayer_py.chains import studionet
from genlayer_py.client import create_client
from genlayer_py.types import TransactionHashVariant


_ADDRESS = re.compile(r"^0x(?!0{40}$)[0-9a-fA-F]{40}$")
_COMMIT = re.compile(r"^[0-9a-fA-F]{40}$")
_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_EVIDENCE_BYTES = 4800
_write_lock = threading.RLock()


class DeliveryOSClient:
    def __init__(self, contract_address: str, private_key: str | None = None, client=None,
                 passport_contract_address: str | None = None):
        if not _ADDRESS.fullmatch(contract_address):
            raise ValueError("Contract address must be a 0x-prefixed 20-byte address")
        if passport_contract_address is not None and not _ADDRESS.fullmatch(passport_contract_address):
            raise ValueError("Passport contract address must be a 0x-prefixed 20-byte address")
        self.contract_address = contract_address
        self.passport_contract_address = passport_contract_address
        self.account = None
        if private_key:
            if not re.fullmatch(r"(?:0x)?[0-9a-fA-F]{64}", private_key):
                raise ValueError("Wallet key must be 32 bytes of hexadecimal")
            self.account = create_account(private_key)
        # This SDK requires an account even for reads. Keep an ephemeral read
        # identity separate from the configured signing wallet.
        self.client = client if client is not None else create_client(
            chain=studionet, account=self.account or create_account()
        )

    @classmethod
    def from_env(cls):
        address = os.environ.get("DELIVERYOS_CONTRACT_ADDRESS", "")
        key = os.environ.get("DELIVERYOS_PRIVATE_KEY")
        passport = os.environ.get("DELIVERYOS_PASSPORT_ADDRESS")
        return cls(address, key, passport_contract_address=passport)

    @property
    def wallet_address(self) -> str | None:
        return self.account.address if self.account is not None else None

    def _read(self, name: str, args: list):
        return self.client.read_contract(
            self.contract_address, name, args=args,
            transaction_hash_variant=TransactionHashVariant.LATEST_FINAL,
        )

    def _write(self, name: str, args: list) -> dict:
        if self.account is None:
            raise RuntimeError("Writes need DELIVERYOS_PRIVATE_KEY in the agent's own environment")
        with _write_lock:
            tx_hash = self.client.write_contract(
                self.contract_address, name, account=self.account, args=args
            )
        # Never re-submit automatically after a timeout. Poll this hash or read job state.
        return {"transaction_hash": str(tx_hash), "status": "SUBMITTED_TO_NETWORK",
                "contract_address": self.contract_address, "method": name}

    def _passport_read(self, name: str, args: list):
        if not self.passport_contract_address:
            raise RuntimeError("Set DELIVERYOS_PASSPORT_ADDRESS to use Provider Passport tools")
        return self.client.read_contract(
            self.passport_contract_address, name, args=args,
            transaction_hash_variant=TransactionHashVariant.LATEST_FINAL,
        )

    def _passport_write(self, name: str, args: list) -> dict:
        if not self.passport_contract_address:
            raise RuntimeError("Set DELIVERYOS_PASSPORT_ADDRESS to use Provider Passport tools")
        if self.account is None:
            raise RuntimeError("Profile writes need DELIVERYOS_PRIVATE_KEY in the agent's own environment")
        with _write_lock:
            tx_hash = self.client.write_contract(
                self.passport_contract_address, name, account=self.account, args=args
            )
        return {"transaction_hash": str(tx_hash), "status": "SUBMITTED_TO_NETWORK",
                "contract_address": self.passport_contract_address, "method": name}

    def passport_identity(self) -> dict:
        if not self.passport_contract_address:
            raise RuntimeError("Set DELIVERYOS_PASSPORT_ADDRESS to use Provider Passport tools")
        return {
            "network": "studionet", "chain_id": 61999,
            "passport_contract_address": self.passport_contract_address,
            "source_contract_address": self._passport_read("get_source_contract", []),
            "owner_address": self._passport_read("get_owner", []),
        }

    def get_provider_profile(self, wallet_address: str) -> dict:
        if not _ADDRESS.fullmatch(wallet_address):
            raise ValueError("Wallet address must be a 0x-prefixed 20-byte address")
        return self._passport_read("get_provider_profile", [wallet_address])

    def get_provider_receipt_count(self, wallet_address: str) -> int:
        if not _ADDRESS.fullmatch(wallet_address):
            raise ValueError("Wallet address must be a 0x-prefixed 20-byte address")
        return int(self._passport_read("get_provider_receipt_count", [wallet_address]))

    def get_provider_receipt(self, wallet_address: str, index: int) -> dict:
        if not _ADDRESS.fullmatch(wallet_address):
            raise ValueError("Wallet address must be a 0x-prefixed 20-byte address")
        if type(index) is not int or index < 0:
            raise ValueError("Receipt index must be a non-negative integer")
        return self._passport_read("get_provider_receipt", [wallet_address, index])

    def get_receipt_by_id(self, receipt_id: str) -> dict:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", receipt_id):
            raise ValueError("Receipt ID must be a 32-byte hexadecimal hash")
        return self._passport_read("get_receipt_by_id", [receipt_id])

    def passport_receipt_status(self, job_id: str) -> dict:
        """Read source and companion at LATEST_FINAL; dispatch is not receipt success."""
        job = self.get_job(job_id)
        if job.get("protocol") != "DELIVERYOS_PACKAGES_V6":
            raise ValueError("Receipt recovery requires the V6 contract")
        dispatch = self._read("get_passport_dispatch", [job_id])
        if (not self.passport_contract_address or
                dispatch["passport_contract_address"].lower() != self.passport_contract_address.lower()):
            raise ValueError("Configured Passport does not match the source contract")
        bound_source = self._passport_read("get_source_contract", [])
        if str(bound_source).lower() != self.contract_address.lower():
            raise ValueError("Passport is not bound to this source contract")
        receipt = (self._passport_read("get_outcome_for_job", [job_id, int(job["current_version"])])
                   if dispatch["receipt_eligible"] else {})
        return {"job_id": job_id, **dispatch, "receipt_recorded": bool(receipt),
                "receipt": receipt, "read_finality": "LATEST_FINAL",
                "warning": "A queued callback is not proof of a successfully recorded receipt."}

    def sync_passport_receipt(self, job_id: str, expected_version: int) -> dict:
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("Expected version must be a positive integer")
        status = self.passport_receipt_status(job_id)
        if expected_version != int(status["version"]):
            raise ValueError("Outcome version changed; inspect the latest job")
        if not status["receipt_eligible"]:
            raise ValueError("Only a terminal consensus outcome has a Passport receipt")
        if self.wallet_address is None:
            raise RuntimeError("Writes need DELIVERYOS_PRIVATE_KEY in the agent's own environment")
        job = self.get_job(job_id)
        if self.wallet_address.lower() not in (job["buyer"].lower(), job["provider"].lower()):
            raise ValueError("Only a party may sync a receipt")
        if not status["receipt_recorded"] and time.time() < int(status["next_retry_epoch"]):
            raise ValueError("Passport retry cooldown has not passed")
        return self._write("sync_passport_receipt", [job_id, expected_version])

    def set_my_provider_profile(self, display_name: str, bio: str,
                                 capabilities: list[str]) -> dict:
        if self.account is None:
            raise RuntimeError("Profile writes need DELIVERYOS_PRIVATE_KEY in the agent's own environment")
        if not isinstance(capabilities, list) or any(not isinstance(tag, str) for tag in capabilities):
            raise ValueError("Capabilities must be a list of text tags")
        return self._passport_write("set_my_profile", [
            display_name, bio, json.dumps(capabilities, separators=(",", ":")),
        ])

    def get_job(self, job_id: str) -> dict:
        return self._read("get_job", [job_id])

    def next_actions(self, job_id: str) -> dict:
        """Explain the caller's role and likely next tools without signing anything.

        This is guidance only. The contract checks authorization, state, and its
        clock again when a transaction actually executes.
        """
        if not _JOB_ID.fullmatch(job_id):
            raise ValueError("Job ID must be 8-64 letters, digits, underscores or hyphens")
        job = self.get_job(job_id)
        wallet = (self.wallet_address or "").lower()
        role = ("buyer" if wallet and wallet == str(job.get("buyer", "")).lower()
                else "provider" if wallet and wallet == str(job.get("provider", "")).lower()
                else "observer")
        status = str(job.get("status", "UNKNOWN"))
        actions: list[str] = []
        deadline = job.get("submission_deadline_epoch", job.get("due_epoch"))
        overdue = (status in ("PROPOSED", "ACTIVE", "REVISION")
                   and isinstance(deadline, (int, float)) and time.time() > deadline)
        if overdue:
            if wallet:
                actions = ["deliveryos_expire_undelivered"]
        elif status == "PROPOSED":
            if role == "provider":
                actions = ["deliveryos_accept_job", "deliveryos_decline_job"]
            elif role == "buyer":
                actions = ["deliveryos_cancel_proposal"]
        elif status in ("ACTIVE", "REVISION") and role == "provider":
            actions = ["deliveryos_submit_delivery"]
        elif status == "SUBMITTED":
            package_protocol = job.get("protocol")
            can_correct = package_protocol in (
                "DELIVERYOS_PACKAGES_V3", "DELIVERYOS_PACKAGES_V4", "DELIVERYOS_PACKAGES_V5", "DELIVERYOS_PACKAGES_V6",
            )
            before_cutoff = time.time() <= int(job.get("review_deadline_epoch", 0))
            if package_protocol in ("DELIVERYOS_PACKAGES_V4", "DELIVERYOS_PACKAGES_V5", "DELIVERYOS_PACKAGES_V6") and not before_cutoff:
                if wallet:
                    actions = ["deliveryos_close_unreviewed"]
            elif role == "buyer":
                actions = ["deliveryos_accept_delivery", "deliveryos_evaluate_delivery"]
            elif role == "provider":
                actions = ["deliveryos_evaluate_delivery"]
                if can_correct and before_cutoff:
                    actions.insert(0, "deliveryos_submit_delivery")
            if package_protocol == "DELIVERYOS_PACKAGES_V3" and not before_cutoff and wallet:
                actions.append("deliveryos_close_unreviewed")
        if (job.get("protocol") == "DELIVERYOS_PACKAGES_V6" and
                status in ("ACCEPTED", "REJECTED", "INCONCLUSIVE") and
                job.get("decision_source") == "CONSENSUS" and role != "observer"):
            actions = ["deliveryos_passport_receipt_status", "deliveryos_sync_passport_receipt"]
        protocol = ("v6" if job.get("protocol") == "DELIVERYOS_PACKAGES_V6" else
                    "v5" if job.get("protocol") == "DELIVERYOS_PACKAGES_V5" else
                    "v4" if job.get("protocol") == "DELIVERYOS_PACKAGES_V4" else
                    "v3" if job.get("protocol") == "DELIVERYOS_PACKAGES_V3" else
                    "v2" if job.get("protocol") == "DELIVERYOS_PACKAGES_V2" else "v1")
        return {
            "job_id": job_id,
            "status": status,
            "role": role,
            "wallet_address": self.wallet_address,
            "possible_tools": actions,
            "job_url_path": None if protocol in ("v5", "v6") else f"/?version={protocol}&job={job_id}",
            "browser_ui_note": ("V5/V6 jobs are available through MCP. The hosted browser workspace remains V4."
                                if protocol in ("v5", "v6") else None),
            "next_step": ("The v4/v5/v6 decision cutoff has passed. Anyone with a wallet may close this "
                          "unreviewed submission as inconclusive; approval and review can no longer succeed."
                          if protocol in ("v4", "v5", "v6") and actions == ["deliveryos_close_unreviewed"] else
                          "Check the finalized Passport receipt. If missing, wait until next_retry_epoch "
                          "and sync the stored outcome; this cannot reassess or change the verdict."
                          if protocol == "v6" and actions == ["deliveryos_passport_receipt_status",
                                                               "deliveryos_sync_passport_receipt"] else
                          "Use the DeliveryOS MCP tools. For acceptance/review, pass the inspected "
                          "current_version; verified Passport receipts appear only after terminal validator "
                          "decisions finalize."
                          if protocol in ("v5", "v6") and actions else
                          "Choose a possible tool. For v3/v4/v5/v6 acceptance/review, pass the inspected "
                          "current_version as expected_version. Then check the transaction hash "
                          "until finalized_success is true and read the job again."
                          if protocol in ("v3", "v4", "v5", "v6") and actions else
                          "Choose a possible tool, then check its transaction hash until "
                          "finalized_success is true and read the job again."
                          if actions else "No role-specific write is currently suggested. "
                          "Check the assigned wallet and job state."),
            "warning": "Suggestions are not authorization; the contract enforces roles, deadlines, and state.",
        }

    def get_submission(self, job_id: str, version: int) -> dict:
        return self._read("get_submission", [job_id, version])

    def get_job_count(self) -> int:
        return self._read("get_job_count", [])

    def get_job_id(self, index: int) -> str:
        return self._read("get_job_id", [index])

    def transaction_status(self, transaction_hash: str) -> dict:
        if not re.fullmatch(r"0x[0-9a-fA-F]{64}", transaction_hash):
            raise ValueError("Transaction hash must be 32 bytes")
        receipt = self.client.get_transaction(transaction_hash)
        leader = ((receipt.get("consensus_data") or {}).get("leader_receipt") or [{}])[0]
        status = receipt.get("status_name", "UNKNOWN")
        consensus = receipt.get("result_name", "UNKNOWN")
        execution = leader.get("execution_result", "UNKNOWN")
        result = leader.get("result")
        return {
            "transaction_hash": transaction_hash,
            "status": status,
            "consensus_result": consensus,
            "execution_result": execution,
            "finalized_success": (status == "FINALIZED" and execution in ("SUCCESS", "FINISHED_WITH_RETURN")
                                  and consensus in ("AGREE", "MAJORITY_AGREE")),
            "error": result.get("payload") if execution == "ERROR" and isinstance(result, dict) else None,
        }

    def create_job(self, job_id: str, provider: str, brief: str, criteria: list[str],
                   evidence_prefix: str, due_epoch: int, max_revisions: int = 1) -> dict:
        if not _JOB_ID.fullmatch(job_id):
            raise ValueError("Job ID must be 8-64 letters, digits, underscores or hyphens")
        if not _ADDRESS.fullmatch(provider):
            raise ValueError("Provider must be a wallet address")
        if not isinstance(criteria, list) or not 1 <= len(criteria) <= 4:
            raise ValueError("Provide 1-4 acceptance criteria")
        self._validate_evidence_url(evidence_prefix, prefix=True)
        return self._write("create_job", [job_id, provider, brief,
                           json.dumps(criteria, separators=(",", ":")),
                           evidence_prefix, due_epoch, max_revisions])

    def accept_job(self, job_id: str) -> dict:
        return self._write("accept_job", [job_id])

    def decline_job(self, job_id: str) -> dict:
        return self._write("decline_job", [job_id])

    def cancel_proposal(self, job_id: str) -> dict:
        return self._write("cancel_proposal", [job_id])

    @staticmethod
    def _validate_evidence_url(url: str, prefix: bool = False) -> None:
        if not isinstance(url, str) or len(url) > 1024:
            raise ValueError("Evidence URL is invalid")
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.netloc != "raw.githubusercontent.com"
                or parsed.query or parsed.fragment or parsed.username or parsed.password
                or parsed.port):
            raise ValueError("Use a plain raw.githubusercontent.com HTTPS URL")
        parts = parsed.path.split("/")
        if len(parts) < 4 or not parts[1] or not parts[2]:
            raise ValueError("Evidence URL needs an owner and repository")
        if not (prefix and len(parts) == 4 and parts[3] == ""):
            if len(parts) < 5 or not _COMMIT.fullmatch(parts[3]):
                raise ValueError("Evidence URL needs a full commit SHA and file")
        if ("//" in parsed.path or not re.fullmatch(r"/[A-Za-z0-9._~/-]+", parsed.path)
                or any(part in (".", "..") for part in parts)):
            raise ValueError("Evidence URL path is unsafe")
        if prefix and not url.endswith("/"):
            raise ValueError("Evidence prefix must end in /")
        if not prefix and not parts[-1]:
            raise ValueError("Evidence URL must name a file")

    @classmethod
    def fetch_public_evidence_bytes(cls, url: str) -> bytes:
        cls._validate_evidence_url(url)

        class NoRedirect(request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = request.build_opener(NoRedirect)
        call = request.Request(url, headers={"Accept-Encoding": "identity"})
        try:
            with opener.open(call, timeout=20) as response:
                if response.status != 200:
                    raise ValueError("Evidence must return HTTP 200")
                body = response.read(MAX_EVIDENCE_BYTES + 1)
        except error.HTTPError as exc:
            raise ValueError(f"Evidence fetch failed with HTTP {exc.code}") from exc
        if not 1 <= len(body) <= MAX_EVIDENCE_BYTES:
            raise ValueError("Evidence must be 1-4800 bytes")
        return body

    @classmethod
    def pin_public_evidence(cls, url: str) -> dict:
        body = cls.fetch_public_evidence_bytes(url)
        try:
            if not body.decode("utf-8").strip():
                raise ValueError("Evidence must contain nonempty UTF-8 text")
        except UnicodeDecodeError as exc:
            raise ValueError("Evidence must be UTF-8 text") from exc
        return {"url": url, "sha256": hashlib.sha256(body).hexdigest(),
                "size_bytes": len(body)}

    def submit_delivery(self, job_id: str, evidence_url: str) -> dict:
        job = self.get_job(job_id)
        supports_correction = job.get("protocol") in (
            "DELIVERYOS_PACKAGES_V3", "DELIVERYOS_PACKAGES_V4", "DELIVERYOS_PACKAGES_V5", "DELIVERYOS_PACKAGES_V6",
        )
        if job["status"] not in (("ACTIVE", "REVISION", "SUBMITTED") if supports_correction else ("ACTIVE", "REVISION")):
            raise ValueError("Job is not awaiting a delivery")
        if supports_correction and job["status"] == "SUBMITTED" and time.time() > int(job.get("review_deadline_epoch", 0)):
            raise ValueError("Correction window passed")
        if not evidence_url.startswith(job["evidence_prefix"]):
            raise ValueError("Evidence URL is outside the agreed source prefix")
        if job.get("protocol") in (
            "DELIVERYOS_PACKAGES_V2", "DELIVERYOS_PACKAGES_V3",
            "DELIVERYOS_PACKAGES_V4", "DELIVERYOS_PACKAGES_V5", "DELIVERYOS_PACKAGES_V6",
        ):
            from .packages import verify_public_package
            previous_fingerprint = job.get("last_reviewed_fingerprint") if supports_correction else None
            if not supports_correction and job["status"] == "REVISION":
                previous = self.get_submission(job_id, int(job["current_version"]))
                previous_fingerprint = previous.get("content_fingerprint")
            evidence = verify_public_package(
                evidence_url, job["evidence_prefix"], len(job["criteria"]),
                previous_fingerprint=previous_fingerprint,
            )
            if supports_correction and job["status"] == "SUBMITTED":
                previous = self.get_submission(job_id, int(job["current_version"]))
                if evidence["sha256"] == previous["sha256"]:
                    raise ValueError("A correction must change the manifest bytes")
        else:
            evidence = self.pin_public_evidence(evidence_url)
        result = self._write("submit_delivery", [job_id, evidence_url,
                             evidence["sha256"], evidence["size_bytes"]])
        return {**result, "evidence": evidence}

    def _decision_args(self, job_id: str, expected_version: int | None) -> list:
        job = self.get_job(job_id)
        protocol = job.get("protocol")
        if protocol in (
            "DELIVERYOS_PACKAGES_V3", "DELIVERYOS_PACKAGES_V4", "DELIVERYOS_PACKAGES_V5", "DELIVERYOS_PACKAGES_V6",
        ):
            if type(expected_version) is not int or expected_version < 1:
                raise ValueError("V3/V4/V5/V6 decisions require the inspected expected_version")
            if expected_version != int(job["current_version"]):
                raise ValueError("Pending version changed; inspect the latest evidence")
            if (protocol in ("DELIVERYOS_PACKAGES_V4", "DELIVERYOS_PACKAGES_V5", "DELIVERYOS_PACKAGES_V6") and
                    time.time() > int(job.get("review_deadline_epoch", 0))):
                raise ValueError("Review cutoff passed; close the unreviewed submission")
            return [job_id, expected_version]
        if expected_version is not None:
            raise ValueError("Expected version is supported only by the v3/v4/v5/v6 contracts")
        return [job_id]

    def accept_delivery(self, job_id: str, expected_version: int | None = None) -> dict:
        return self._write("accept_delivery", self._decision_args(job_id, expected_version))

    def evaluate_delivery(self, job_id: str, expected_version: int | None = None) -> dict:
        return self._write("evaluate_delivery", self._decision_args(job_id, expected_version))

    def expire_undelivered(self, job_id: str) -> dict:
        return self._write("expire_undelivered", [job_id])

    def close_unreviewed(self, job_id: str) -> dict:
        return self._write("close_unreviewed", [job_id])
