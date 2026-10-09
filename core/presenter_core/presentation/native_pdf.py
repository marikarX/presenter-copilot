"""One-shot native PDF conversion, separate from the Core request loop.

PowerPoint can reuse the user's application instance. Never change its settings
or call Quit; only the read-only presentation opened here belongs to this worker.
The privileged desktop supplies private copied input/output paths, never a
renderer-selected source or final destination.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlsplit

from lxml import etree  # type: ignore[import-untyped]
from pypdf import PdfReader

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.ingestion.security import preflight_source

MAX_PDF_BYTES = 100 * 1024 * 1024
# Installed PowerPoint rounds valid custom page sizes (observed 0.025pt).
NATIVE_PAGE_TOLERANCE_PT = 1 / 16
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_HYPERLINK = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"


def _failure(code: str, message: str) -> CoreDomainError:
    return CoreDomainError(code, message)


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_native_source(path: Path, expected_sha256: str) -> tuple[int, float, float]:
    """Bound the archive and reject automatic active/external dependencies."""
    preflight_source(path, "pptx")
    if _digest(path) != expected_sha256:
        raise _failure("SOURCE_SNAPSHOT_CHANGED", "The PDF export snapshot changed.")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    with zipfile.ZipFile(path) as archive:
        presentation = etree.fromstring(archive.read("ppt/presentation.xml"), parser)
        namespace = "http://schemas.openxmlformats.org/presentationml/2006/main"
        sizes = presentation.findall(f"{{{namespace}}}sldSz")
        lists = presentation.findall(f"{{{namespace}}}sldIdLst")
        if len(sizes) != 1 or len(lists) != 1:
            raise _failure("PRESENTATION_PDF_SOURCE_INVALID", "The slide inventory is invalid.")
        count = len(lists[0].findall(f"{{{namespace}}}sldId"))
        width, height = (
            float(sizes[0].get("cx", "0")) / 12700,
            float(sizes[0].get("cy", "0")) / 12700,
        )
        if not 0 < count <= 5000 or not all(math.isfinite(n) and n > 0 for n in (width, height)):
            raise _failure("PRESENTATION_PDF_SOURCE_INVALID", "The slide geometry is invalid.")
        for info in archive.infolist():
            name = info.filename.casefold()
            if "vbaproject" in name or name.startswith("ppt/activex/"):
                raise _failure(
                    "PRESENTATION_PDF_ACTIVE_CONTENT",
                    "This presentation contains active content. Export it manually in PowerPoint.",
                )
            if name == "[content_types].xml":
                root = etree.fromstring(archive.read(info), parser)
                if any(
                    any(
                        marker in node.get("ContentType", "").casefold()
                        for marker in ("macroenabled", "vbaproject", "activex", "oleobject")
                    )
                    for node in root
                ):
                    raise _failure(
                        "PRESENTATION_PDF_ACTIVE_CONTENT",
                        "Active or embedded OLE content requires manual PDF export in PowerPoint.",
                    )
            elif name.endswith(".rels"):
                root = etree.fromstring(archive.read(info), parser)
                if root.tag != f"{{{_REL_NS}}}Relationships":
                    raise _failure(
                        "PRESENTATION_PDF_SOURCE_INVALID", "The presentation links are invalid."
                    )
                for node in root:
                    target = urlsplit(node.get("Target", "").replace("\\", "/"))
                    if node.get("TargetMode", "").casefold() != "external" and (
                        target.scheme or target.netloc
                    ):
                        raise _failure(
                            "PRESENTATION_PDF_EXTERNAL_CONTENT",
                            "External content requires manual PDF export in PowerPoint.",
                        )
                    if (
                        node.get("TargetMode", "").casefold() == "external"
                        and node.get("Type") != _HYPERLINK
                    ):
                        raise _failure(
                            "PRESENTATION_PDF_EXTERNAL_CONTENT",
                            "External content requires manual PDF export in PowerPoint.",
                        )
            elif name.endswith(".xml") and name.startswith("ppt/slides/"):
                root = etree.fromstring(archive.read(info), parser)
                if any(
                    "ppaction://macro" in node.get("action", "").casefold() for node in root.iter()
                ):
                    raise _failure(
                        "PRESENTATION_PDF_ACTIVE_CONTENT",
                        "Macro actions require manual PDF export in PowerPoint.",
                    )

    return count, width, height


def validate_pdf(path: Path, pages: int, width: float, height: float) -> dict[str, Any]:
    size = path.stat().st_size
    if not 0 < size <= MAX_PDF_BYTES:
        raise _failure(
            "PRESENTATION_PDF_INVALID", "The exported PDF exceeds the size limit or is empty."
        )
    with path.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise _failure("PRESENTATION_PDF_INVALID", "PowerPoint did not produce a readable PDF.")
        stream.seek(0)
        reader = PdfReader(stream, strict=True)
        # Retain Office labels/encryption; never remove protection to pass validation.
        if reader.is_encrypted:
            raise _failure(
                "PRESENTATION_PDF_PROTECTED",
                "This protected PDF needs manual export and review in PowerPoint.",
            )
        if pages < 1 or len(reader.pages) != pages:
            raise _failure(
                "PRESENTATION_PDF_INVALID", "The exported PDF has an unexpected page count."
            )
        for page in reader.pages:
            box = page.mediabox
            if not math.isclose(float(box.width), width, abs_tol=1.0) or not math.isclose(
                float(box.height), height, abs_tol=1.0
            ):
                raise _failure(
                    "PRESENTATION_PDF_INVALID", "The exported PDF page size differs from the deck."
                )
    return {"byte_size": size, "sha256": _digest(path), "page_count": pages}


def export_native_pdf(job: dict[str, Any], *, application: Any = None) -> dict[str, Any]:
    reject_unknown_fields(job, {"snapshot_path", "output_path", "source_sha256", "include_hidden"})
    digest = job.get("source_sha256")
    hidden = job.get("include_hidden")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest) or not isinstance(hidden, bool):
        raise invalid_request("The native PDF job metadata is invalid.")
    for field in ("snapshot_path", "output_path"):
        value = job.get(field)
        if not isinstance(value, str) or not value or len(value) > 32768 or "\x00" in value:
            raise invalid_request("The native PDF job path is invalid.")
    source = Path(job["snapshot_path"])
    output = Path(job["output_path"])
    if (
        not source.is_absolute()
        or not output.is_absolute()
        or source.is_symlink()
        or output.exists()
        or output.is_symlink()
        or source.suffix.casefold() != ".pptx"
        or output.suffix.casefold() != ".pdf"
        or source.parent.resolve() != output.parent.resolve()
    ):
        raise invalid_request(
            "PDF conversion requires new output beside its private PPTX snapshot."
        )
    expected_count, expected_width, expected_height = validate_native_source(source, digest)
    initialized = False
    pythoncom: Any = None
    presentation: Any = None
    try:
        if application is None:
            if sys.platform != "win32":
                raise _failure(
                    "PRESENTATION_PDF_UNAVAILABLE",
                    "PDF export requires Microsoft PowerPoint installed on Windows.",
                )
            pythoncom = importlib.import_module("pythoncom")
            pythoncom.CoInitialize()
            initialized = True
            client = importlib.import_module("win32com.client")
            try:
                application = client.DispatchEx("PowerPoint.Application")
            except Exception as error:
                raise _failure(
                    "PRESENTATION_PDF_UNAVAILABLE",
                    "Microsoft PowerPoint could not be started for PDF export.",
                ) from error
        presentation = application.Presentations.Open(
            str(source), ReadOnly=True, Untitled=False, WithWindow=False
        )
        slide_count = int(presentation.Slides.Count)
        if slide_count != expected_count:
            raise _failure("PRESENTATION_PDF_INVALID", "The deck has an invalid slide count.")
        page_count = sum(
            1
            for index in range(1, slide_count + 1)
            if hidden or int(presentation.Slides.Item(index).SlideShowTransition.Hidden) == 0
        )
        if page_count < 1:
            raise _failure(
                "PRESENTATION_PDF_EMPTY",
                "No visible slides remain. Include hidden slides to export.",
            )
        width = float(presentation.PageSetup.SlideWidth)
        height = float(presentation.PageSetup.SlideHeight)
        if not all(math.isfinite(value) and value > 0 for value in (width, height)):
            raise _failure("PRESENTATION_PDF_INVALID", "The deck has an invalid page size.")
        if not math.isclose(
            width, expected_width, rel_tol=0, abs_tol=NATIVE_PAGE_TOLERANCE_PT
        ) or not math.isclose(height, expected_height, rel_tol=0, abs_tol=NATIVE_PAGE_TOLERANCE_PT):
            raise _failure("PRESENTATION_PDF_INVALID", "PowerPoint changed the slide geometry.")
        # PDF(2), print intent(2), slides(1), all(1). Preserve labels, tags,
        # and bitmap restricted fonts. No notes pages, animations or handouts.
        presentation.ExportAsFixedFormat(
            str(output),
            2,
            2,
            0,
            1,
            1,
            # This Office build requires msoCTrue (1): msoTrue (-1) silently
            # omits hidden slides. Validate the actual page count below.
            1 if hidden else 0,
            None,
            1,
            "",
            False,
            True,
            True,
            True,
            False,
        )
        result = validate_pdf(output, page_count, width, height)
        if _digest(source) != digest:
            raise _failure("SOURCE_SNAPSHOT_CHANGED", "PowerPoint changed the PDF export snapshot.")
        return {
            **result,
            "source_sha256": digest,
            "slide_count": slide_count,
            "include_hidden": hidden,
            "renderer": "microsoft_powerpoint",
        }
    finally:
        try:
            if presentation is not None:
                presentation.Close()
        finally:
            presentation = None
            application = None
            if initialized:
                pythoncom.CoUninitialize()


def run_pdf_worker(stdin: TextIO, stdout: TextIO) -> int:
    """Bounded one-job IPC. Never echo raw Office exceptions, paths or source data."""
    try:
        raw = stdin.read(8193)
        if len(raw) > 8192:
            raise invalid_request("The native PDF job is too large.")
        job = json.loads(raw)
        if not isinstance(job, dict):
            raise invalid_request("The native PDF job must be an object.")
        result = export_native_pdf(job)
        response: dict[str, Any] = {"ok": True, "result": result}
        code = 0
    except CoreDomainError as error:
        response = {
            "ok": False,
            "error": {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
                "details": {},
            },
        }
        code = 1
    except Exception:
        response = {
            "ok": False,
            "error": {
                "code": "PRESENTATION_PDF_FAILED",
                "message": "PowerPoint could not export this PDF. Try manual export in PowerPoint.",
                "retryable": True,
                "details": {},
            },
        }
        code = 1
    stdout.write(json.dumps(response) + "\n")
    stdout.flush()
    return code
