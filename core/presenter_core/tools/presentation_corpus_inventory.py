"""Read-only structural inventory for the locally cached PPTX research corpus."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from presenter_core.errors import CoreDomainError
from presenter_core.presentation.fidelity import inspect_pptx_snapshot

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPOSITORY_ROOT / "docs" / "PRESENTATION_WORKSPACE" / "corpus-manifest.json"
LOCAL_ROOT = REPOSITORY_ROOT / ".local"
CORPUS_ROOT = LOCAL_ROOT / "presentation-workspace-corpus"


def _sha256(handle: Any) -> str:
    digest = hashlib.sha256()
    handle.seek(0)
    while chunk := handle.read(1024 * 1024):
        digest.update(chunk)
    handle.seek(0)
    return digest.hexdigest()


def _md5(handle: Any) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    handle.seek(0)
    while chunk := handle.read(1024 * 1024):
        digest.update(chunk)
    handle.seek(0)
    return digest.hexdigest()


def _entry(item: dict[str, Any]) -> dict[str, Any]:
    name = item.get("local_name")
    base = {
        "record_id": item.get("record_id"),
        "source_type": item.get("source_type", "zenodo"),
        "source_identifier": item.get("archive_identifier") or item.get("doi"),
        "doi": item.get("doi"),
        "title": item.get("title"),
        "creators": item.get("creators"),
        "source_filename": item.get("source_filename"),
        "local_name": name,
    }
    if not isinstance(name, str) or Path(name).name != name:
        return {**base, "status": "failed", "code": "CORPUS_MANIFEST_INVALID"}

    source = CORPUS_ROOT / name
    try:
        if LOCAL_ROOT.is_symlink() or CORPUS_ROOT.is_symlink() or source.is_symlink():
            return {**base, "status": "failed", "code": "CORPUS_PATH_SYMLINK"}
        resolved_root = CORPUS_ROOT.resolve(strict=True)
        resolved_source = source.resolve(strict=True)
        if resolved_source.parent != resolved_root or not resolved_source.is_file():
            return {**base, "status": "failed", "code": "CORPUS_PATH_INVALID"}
        byte_size = resolved_source.stat().st_size
        if byte_size != item.get("file_size_bytes"):
            return {**base, "status": "failed", "code": "CORPUS_SIZE_MISMATCH"}

        with resolved_source.open("rb") as handle:
            if _md5(handle) != item.get("file_md5"):
                return {**base, "status": "failed", "code": "CORPUS_MD5_MISMATCH"}
            sha256 = _sha256(handle)
            if item.get("file_sha1"):
                handle.seek(0)
                sha1 = hashlib.sha1(usedforsecurity=False)
                while chunk := handle.read(1024 * 1024):
                    sha1.update(chunk)
                if sha1.hexdigest() != item.get("file_sha1"):
                    return {**base, "status": "failed", "code": "CORPUS_SHA1_MISMATCH"}
                handle.seek(0)
            if item.get("file_sha256") and sha256 != item.get("file_sha256"):
                return {**base, "status": "failed", "code": "CORPUS_SHA256_MISMATCH"}
            try:
                fidelity = inspect_pptx_snapshot(
                    handle,
                    document_id=f"corpus-{item['record_id']}",
                    expected_sha256=sha256,
                    byte_size=byte_size,
                )
            except CoreDomainError as error:
                return {
                    **base,
                    "status": "unsupported",
                    "code": error.code,
                    "byte_size": byte_size,
                    "sha256": sha256,
                }

        object_kinds = Counter(obj.kind for slide in fidelity.slides for obj in slide.objects)
        summary = fidelity.summary()
        return {
            **base,
            "status": "inventory_only",
            "byte_size": byte_size,
            "sha256": sha256,
            "slide_count": summary["slide_count"],
            "object_count": summary["object_count"],
            "text_edit_candidates": summary["text_edit_candidates"],
            "nontext_or_unmodeled_objects": summary["nontext_or_unmodeled_objects"],
            "object_kinds": dict(sorted(object_kinds.items())),
            "editable_notes_slides": sum(slide.speaker_notes_editable for slide in fidelity.slides),
        }
    except FileNotFoundError:
        return {**base, "status": "failed", "code": "CORPUS_FILE_MISSING"}
    except OSError:
        return {**base, "status": "failed", "code": "CORPUS_FILE_UNREADABLE"}
    except Exception:
        return {**base, "status": "failed", "code": "PPTX_INVENTORY_FAILED"}


def main() -> int:
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(json.dumps({"status": "failed", "code": "CORPUS_MANIFEST_UNAVAILABLE"}))
        return 1
    records = manifest.get("records")
    supplemental_records = manifest.get("supplemental_records", [])
    if not isinstance(records, list) or not records or not isinstance(supplemental_records, list):
        print(json.dumps({"status": "failed", "code": "CORPUS_MANIFEST_INVALID"}))
        return 1
    records = [*records, *supplemental_records]

    entries = [
        _entry(item)
        if isinstance(item, dict)
        else {
            "status": "failed",
            "code": "CORPUS_MANIFEST_INVALID",
        }
        for item in records
    ]
    unsupported = sum(entry.get("status") == "unsupported" for entry in entries)
    failed = sum(entry.get("status") == "failed" for entry in entries)
    result = {
        "status": "completed" if failed == 0 else "failed",
        "operation": "read_only_pptx_structural_inventory",
        "record_count": len(entries),
        "parser_supported_count": len(entries) - unsupported - failed,
        "unsupported_count": unsupported,
        "failure_count": failed,
        "deck_text_emitted": False,
        "entries": entries,
    }
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
