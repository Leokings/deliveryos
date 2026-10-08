"""Build and preflight DeliveryOS v2 public, commit-pinned evidence packages.

Publish source files at commit A, then publish the canonical manifest at a
later commit B. The manifest cannot reference its own commit hash.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re

from .client import DeliveryOSClient


PROTOCOL = "DELIVERYOS_PACKAGE_V1"
MEDIA_TYPES = frozenset(("text/plain", "text/markdown", "application/json", "text/csv"))
MAX_FILES = 6
MAX_FILE_BYTES = 4800
MAX_TOTAL_BYTES = 12000
_COMMIT = re.compile(r"[0-9a-fA-F]{40}\Z")
_PATH = re.compile(r"[A-Za-z0-9._~/-]+\Z")


def canonical_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _path(value: str) -> str:
    if (not isinstance(value, str) or not value or not _PATH.fullmatch(value)
            or value.startswith("/") or value.endswith("/") or "//" in value
            or any(part in (".", "..") for part in value.split("/"))):
        raise ValueError("Repository file path is unsafe")
    return value


def _document(body: bytes, media_type: str) -> None:
    if not isinstance(body, bytes) or not 1 <= len(body) <= MAX_FILE_BYTES:
        raise ValueError("Each file must be 1-4800 bytes")
    if not isinstance(media_type, str) or media_type not in MEDIA_TYPES:
        raise ValueError("Unsupported media type")
    try:
        content = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("File must be UTF-8") from exc
    if not content.strip():
        raise ValueError("File must contain text")
    if media_type == "application/json":
        try:
            json.loads(content)
        except ValueError as exc:
            raise ValueError("JSON file is invalid") from exc
    elif media_type == "text/csv":
        rows = list(csv.reader(io.StringIO(content)))
        if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
            raise ValueError("CSV rows must have consistent columns")


def _mapping(indexes, criterion_count: int) -> list[int]:
    if (not isinstance(indexes, list) or not indexes
            or any(type(index) is not int or index < 0 or index >= criterion_count
                   for index in indexes)
            or len(set(indexes)) != len(indexes)):
        raise ValueError("File criterion mapping is invalid")
    return indexes


def _fingerprint(hashes: list[str]) -> str:
    return hashlib.sha256(canonical_bytes(sorted(hashes))).hexdigest()


def build_manifest(evidence_prefix: str, source_commit: str, files: list[dict],
                   criterion_count: int) -> bytes:
    """Return exact bytes to save as a manifest after files are committed.

    Each file dict has path, body (bytes or str), media_type, and zero-based
    criteria indexes. The caller must publish these same bytes at source_commit.
    """
    DeliveryOSClient._validate_evidence_url(evidence_prefix, prefix=True)
    if not isinstance(source_commit, str) or not _COMMIT.fullmatch(source_commit):
        raise ValueError("Source commit must be a full Git SHA")
    if not 1 <= criterion_count <= 4 or not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError("Expected 1-4 criteria and 1-6 files")
    result = []
    seen_paths = set()
    seen_hashes = set()
    covered = set()
    total = 0
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "body", "media_type", "criteria"}:
            raise ValueError("File spec needs path, body, media_type, and criteria")
        path = _path(item["path"])
        body = item["body"].encode("utf-8") if isinstance(item["body"], str) else item["body"]
        media_type = item["media_type"]
        _document(body, media_type)
        indexes = _mapping(item["criteria"], criterion_count)
        if path in seen_paths:
            raise ValueError("Duplicate file path")
        digest = hashlib.sha256(body).hexdigest()
        if digest in seen_hashes:
            raise ValueError("Duplicate file bytes")
        total += len(body)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("Package exceeds 12000 bytes")
        seen_paths.add(path)
        seen_hashes.add(digest)
        covered.update(indexes)
        result.append({"url": evidence_prefix + source_commit + "/" + path,
                       "sha256": digest, "size_bytes": len(body),
                       "media_type": media_type, "criteria": indexes})
    if covered != set(range(criterion_count)):
        raise ValueError("Every criterion needs a mapped file")
    manifest = canonical_bytes({"protocol": PROTOCOL, "source_commit": source_commit,
                                "files": result}) + b"\n"
    if len(manifest) > MAX_FILE_BYTES:
        raise ValueError("Manifest exceeds 4800 bytes")
    return manifest


def verify_public_package(manifest_url: str, evidence_prefix: str, criterion_count: int,
                          previous_fingerprint: str | None = None) -> dict:
    """Fetch every public file without redirects; return on-chain submit metadata."""
    DeliveryOSClient._validate_evidence_url(evidence_prefix, prefix=True)
    DeliveryOSClient._validate_evidence_url(manifest_url)
    if not manifest_url.startswith(evidence_prefix):
        raise ValueError("Manifest is outside the agreed repository")
    body = DeliveryOSClient.fetch_public_evidence_bytes(manifest_url)
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Manifest must be UTF-8 JSON") from exc
    if (not isinstance(data, dict) or set(data) != {"protocol", "source_commit", "files"}
            or body != canonical_bytes(data) + b"\n"):
        raise ValueError("Manifest must be canonical JSON with exact fields")
    if data["protocol"] != PROTOCOL or not isinstance(data["source_commit"], str) or not _COMMIT.fullmatch(data["source_commit"]):
        raise ValueError("Manifest protocol or source commit is invalid")
    files = data["files"]
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES or not 1 <= criterion_count <= 4:
        raise ValueError("Expected 1-4 criteria and 1-6 files")
    owner_repo = "/".join(manifest_url[len("https://raw.githubusercontent.com/"):].split("/")[:2])
    source_prefix = "https://raw.githubusercontent.com/" + owner_repo + "/" + data["source_commit"] + "/"
    seen_urls = set()
    seen_hashes = set()
    covered = set()
    hashes = []
    total = 0
    for item in files:
        if not isinstance(item, dict) or set(item) != {"url", "sha256", "size_bytes", "media_type", "criteria"}:
            raise ValueError("File fields are invalid")
        url = item["url"]
        DeliveryOSClient._validate_evidence_url(url)
        if url == manifest_url or not url.startswith(evidence_prefix) or not url.startswith(source_prefix):
            raise ValueError("File must use the agreed repository and source commit")
        if url in seen_urls:
            raise ValueError("Duplicate file URL")
        digest = item["sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError("File SHA-256 is invalid")
        digest = digest.lower()
        if digest in seen_hashes:
            raise ValueError("Duplicate file bytes")
        size = item["size_bytes"]
        if type(size) is not int or not 1 <= size <= MAX_FILE_BYTES:
            raise ValueError("File size must be 1-4800 bytes")
        indexes = _mapping(item["criteria"], criterion_count)
        data_bytes = DeliveryOSClient.fetch_public_evidence_bytes(url)
        if len(data_bytes) != size or hashlib.sha256(data_bytes).hexdigest() != digest:
            raise ValueError("File bytes do not match the manifest")
        _document(data_bytes, item["media_type"])
        total += size
        if total > MAX_TOTAL_BYTES:
            raise ValueError("Package exceeds 12000 bytes")
        covered.update(indexes)
        seen_urls.add(url)
        seen_hashes.add(digest)
        hashes.append(digest)
    if covered != set(range(criterion_count)):
        raise ValueError("Every criterion needs a mapped file")
    fingerprint = _fingerprint(hashes)
    if previous_fingerprint and fingerprint == previous_fingerprint:
        raise ValueError("Revision must change at least one file")
    return {"url": manifest_url, "sha256": hashlib.sha256(body).hexdigest(),
            "size_bytes": len(body), "file_count": len(files), "total_bytes": total,
            "content_fingerprint": fingerprint}
