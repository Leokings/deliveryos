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


_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_COMMIT = re.compile(r"^[0-9a-fA-F]{40}$")
_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
MAX_EVIDENCE_BYTES = 4800
_write_lock = threading.RLock()


class DeliveryOSClient:
    def __init__(self, contract_address: str, private_key: str | None = None, client=None):
        if not _ADDRESS.fullmatch(contract_address):
            raise ValueError("Contract address must be a 0x-prefixed 20-byte address")
        self.contract_address = contract_address
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
        return cls(address, key)

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
        if status == "PROPOSED":
            if role == "provider":
                actions = ["deliveryos_accept_job", "deliveryos_decline_job"]
            elif role == "buyer":
                actions = ["deliveryos_cancel_proposal"]
        elif status in ("ACTIVE", "REVISION") and role == "provider":
            actions = ["deliveryos_submit_delivery"]
        elif status == "SUBMITTED":
            if role == "buyer":
                actions = ["deliveryos_accept_delivery", "deliveryos_evaluate_delivery"]
            elif role == "provider":
                actions = ["deliveryos_evaluate_delivery"]
                if (job.get("protocol") == "DELIVERYOS_PACKAGES_V3" and
                        time.time() <= int(job.get("review_deadline_epoch", 0))):
                    actions.insert(0, "deliveryos_submit_delivery")
        protocol = ("v3" if job.get("protocol") == "DELIVERYOS_PACKAGES_V3" else
                    "v2" if job.get("protocol") == "DELIVERYOS_PACKAGES_V2" else "v1")
        return {
            "job_id": job_id,
            "status": status,
            "role": role,
            "wallet_address": self.wallet_address,
            "possible_tools": actions,
            "job_url_path": f"/?version={protocol}&job={job_id}",
            "next_step": ("Choose a possible tool. For v3 acceptance/review, pass the inspected "
                          "current_version as expected_version. Then check the transaction hash "
                          "until finalized_success is true and read the job again."
                          if protocol == "v3" and actions else
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
            "finalized_success": (status == "FINALIZED" and execution == "SUCCESS"
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
        is_v3 = job.get("protocol") == "DELIVERYOS_PACKAGES_V3"
        if job["status"] not in (("ACTIVE", "REVISION", "SUBMITTED") if is_v3 else ("ACTIVE", "REVISION")):
            raise ValueError("Job is not awaiting a delivery")
        if is_v3 and job["status"] == "SUBMITTED" and time.time() > int(job.get("review_deadline_epoch", 0)):
            raise ValueError("Correction window passed")
        if not evidence_url.startswith(job["evidence_prefix"]):
            raise ValueError("Evidence URL is outside the agreed source prefix")
        if job.get("protocol") in ("DELIVERYOS_PACKAGES_V2", "DELIVERYOS_PACKAGES_V3"):
            from .packages import verify_public_package
            previous_fingerprint = job.get("last_reviewed_fingerprint") if is_v3 else None
            if not is_v3 and job["status"] == "REVISION":
                previous = self.get_submission(job_id, int(job["current_version"]))
                previous_fingerprint = previous.get("content_fingerprint")
            evidence = verify_public_package(
                evidence_url, job["evidence_prefix"], len(job["criteria"]),
                previous_fingerprint=previous_fingerprint,
            )
            if is_v3 and job["status"] == "SUBMITTED":
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
        if job.get("protocol") == "DELIVERYOS_PACKAGES_V3":
            if type(expected_version) is not int or expected_version < 1:
                raise ValueError("V3 decisions require the inspected expected_version")
            if expected_version != int(job["current_version"]):
                raise ValueError("Pending version changed; inspect the latest evidence")
            return [job_id, expected_version]
        if expected_version is not None:
            raise ValueError("Expected version is supported only by the v3 contract")
        return [job_id]

    def accept_delivery(self, job_id: str, expected_version: int | None = None) -> dict:
        return self._write("accept_delivery", self._decision_args(job_id, expected_version))

    def evaluate_delivery(self, job_id: str, expected_version: int | None = None) -> dict:
        return self._write("evaluate_delivery", self._decision_args(job_id, expected_version))

    def expire_undelivered(self, job_id: str) -> dict:
        return self._write("expire_undelivered", [job_id])

    def close_unreviewed(self, job_id: str) -> dict:
        return self._write("close_unreviewed", [job_id])
