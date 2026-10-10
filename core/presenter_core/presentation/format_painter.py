"""Copy one object's formatting onto other objects on the same slide, like PowerPoint's
format painter: fill, outline, effects, 3-D, the theme style reference and run formatting.

Shape to shape copies everything. When a picture is involved, only the outline and
effects are copied: a picture's fill is its image. Text formatting is copied as the
source's first run properties; each target run keeps its language and its own links.
Placeholders inherit text formatting from their layout, so text formatting is only
copied between non-placeholder shapes; their shape formatting is still copied."""

from __future__ import annotations

import copy
import dataclasses
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    _NS,
    DRAWING_NS,
    PRESENTATION_NS,
    REL_NS,
    _parse_xml_part,
    inspect_pptx_snapshot,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

A = f"{{{DRAWING_NS}}}"
P = f"{{{PRESENTATION_NS}}}"
FILLS = {
    f"{A}{name}" for name in ("noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill")
}
HEAD = {f"{A}xfrm", f"{A}custGeom", f"{A}prstGeom"}
# spPr children after geometry, in schema order.
CATEGORIES: tuple[tuple[str, set[str]], ...] = (
    ("fill", FILLS),
    ("line", {f"{A}ln"}),
    ("effects", {f"{A}effectLst", f"{A}effectDag"}),
    ("scene3d", {f"{A}scene3d"}),
    ("shape3d", {f"{A}sp3d"}),
)
# Run attributes that describe the text itself rather than how it looks.
TEXT_KEEP = {"lang", "altLang", "dirty", "err", "noProof", "smtClean", "smtId", "bmk"}
LINKS = {f"{A}hlinkClick", f"{A}hlinkMouseOver"}
# What a format edit may change about a target; everything else must read back unchanged.
FORMAT_FIELDS = {
    "text_style": None,
    "shape_style": None,
    "text_edit_candidate": False,
    "single_run_text_edit_candidate": False,
    "uniform_run_text_edit_candidate": False,
    "text_format_edit_candidate": False,
    # Derived from Office extensions, which a replaced fill or outline may carry.
    "group_editable": False,
    "group_reason": None,
}


def _sppr(node: Any) -> Any:
    found = node.find(f"{P}spPr")
    if found is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED", "This object has no shape properties to format."
        )
    return found


def _has_relationships(element: Any) -> bool:
    return any(key.startswith(f"{{{REL_NS}}}") for item in element.iter() for key in item.attrib)


def _placeholder(node: Any) -> bool:
    return bool(node.xpath("./*/p:nvPr/p:ph", namespaces=_NS))


def _source_run(node: Any) -> Any | None:
    body = node.find(f"{P}txBody")
    if body is None:
        return None
    for path in ("a:p/a:r/a:rPr", "a:p/a:fld/a:rPr", "a:p/a:endParaRPr"):
        found = body.find(path, _NS)
        if found is not None:
            return found
    return etree.Element(f"{A}rPr")


def _paint_sppr(source: Any, target: Any, categories: set[str]) -> None:
    source_sppr, target_sppr = _sppr(source), _sppr(target)
    children = list(target_sppr)
    head = [item for item in children if item.tag in HEAD]
    tail = [item for item in children if item.tag == f"{A}extLst"]
    ordered = list(head)
    for name, tags in CATEGORIES:
        side = source_sppr if name in categories else target_sppr
        ordered.extend(
            copy.deepcopy(item) if side is source_sppr else item
            for item in side
            if item.tag in tags
        )
    known = HEAD | {f"{A}extLst"} | set().union(*(tags for _, tags in CATEGORIES))
    if any(item.tag not in known for item in children):
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED",
            "This object uses shape properties that stay read-only.",
        )
    for item in children:
        target_sppr.remove(item)
    target_sppr.extend(ordered + tail)


def _paint_style(source: Any, target: Any) -> None:
    previous = target.find(f"{P}style")
    if previous is not None:
        target.remove(previous)
    style = source.find(f"{P}style")
    if style is not None:
        target.insert(list(target).index(target.find(f"{P}spPr")) + 1, copy.deepcopy(style))


def _painted_run(template: Any, existing: Any | None, tag: str) -> Any:
    run = etree.Element(tag)
    for key, value in template.attrib.items():
        if key not in TEXT_KEEP:
            run.set(key, value)
    if existing is not None:
        for key, value in existing.attrib.items():
            if key in TEXT_KEEP:
                run.set(key, value)
    children = [copy.deepcopy(item) for item in template if item.tag not in LINKS]
    links = [item for item in (existing if existing is not None else []) if item.tag in LINKS]
    # Links come after sym and before rtl/extLst in CT_TextCharacterProperties.
    split = next(
        (i for i, item in enumerate(children) if item.tag in {f"{A}rtl", f"{A}extLst"}),
        len(children),
    )
    run.extend(children[:split] + links + children[split:])
    return run


def _paint_text(template: Any, target: Any) -> None:
    body = target.find(f"{P}txBody")
    if body is None:
        return
    for parent in body.xpath("a:p/a:r | a:p/a:fld | a:p/a:br", namespaces=_NS):
        existing = parent.find(f"{A}rPr")
        painted = _painted_run(template, existing, f"{A}rPr")
        if existing is not None:
            parent.replace(existing, painted)
        else:
            parent.insert(0, painted)
    for existing in body.findall("a:p/a:endParaRPr", _NS):
        existing.getparent().replace(existing, _painted_run(template, existing, f"{A}endParaRPr"))


def _canonical(element: Any) -> bytes:
    return bytes(etree.tostring(element, method="c14n", exclusive=True))


def _look(run: Any) -> tuple[Any, ...]:
    """A run's formatting without its language or links."""
    return (
        sorted((k, v) for k, v in run.attrib.items() if k not in TEXT_KEEP),
        [_canonical(item) for item in run if item.tag not in LINKS],
    )


def _verify_painted(
    root: Any, source: Any, node: Any, categories: set[str], both_shapes: bool, template: Any
) -> bool:
    """Re-read the written slide: the target now carries the source's formatting."""
    source_sppr, target_sppr = _sppr(source), _sppr(node)
    for name, tags in CATEGORIES:
        if name in categories and [
            _canonical(item) for item in source_sppr if item.tag in tags
        ] != [_canonical(item) for item in target_sppr if item.tag in tags]:
            return False
    if both_shapes:
        style, painted = source.find(f"{P}style"), node.find(f"{P}style")
        if (style is None) != (painted is None) or (
            style is not None and _canonical(style) != _canonical(painted)
        ):
            return False
    if template is not None:
        runs = node.xpath("p:txBody/a:p/*/a:rPr | p:txBody/a:p/a:endParaRPr", namespaces=_NS)
        if any(_look(run) != _look(template) for run in runs):
            return False
    return True


def copy_object_format(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "slide_id",
            "source_object_id",
            "target_object_ids",
        },
    )
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
    source_id = editor._uuid_field(params.get("source_object_id"), "source_object_id")
    ids = params.get("target_object_ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= 20:
        raise invalid_request("Paint formatting onto 1-20 objects.")
    ids = [editor._uuid_field(value, "target_object_ids") for value in ids]
    if len(set(ids)) != len(ids) or source_id in ids:
        raise invalid_request("Targets must be distinct and different from the source.")
    source = editor._current_revision_source(project, document)
    if source["revision_id"] != revision:
        raise editor._revision_conflict()
    path = editor._storage.paths.snapshot_path(
        project, source["local_snapshot_path"], require_exists=True
    )
    with path.open("rb") as handle:
        fidelity = inspect_pptx_snapshot(
            handle,
            document_id=document,
            expected_sha256=source["sha256"],
            byte_size=source["byte_size"],
        )
    slide = next((item for item in fidelity.slides if item.slide_id == slide_id), None)
    objects = {o.object_id: o for o in slide.objects} if slide is not None else {}
    painter = objects.get(source_id)
    targets = [objects.get(object_id) for object_id in ids]
    if painter is None or any(o is None for o in targets):
        raise CoreDomainError(
            "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected objects are unavailable."
        )
    if any(o is None or o.kind not in {"sp", "pic"} for o in [painter, *targets]):
        raise CoreDomainError(
            "PRESENTATION_EDIT_UNSUPPORTED",
            "Formatting can be copied between shapes, text boxes and pictures only.",
        )
    assert slide is not None
    copied: dict[str, list[str]] = {}
    plans: list[tuple[Any, set[str], bool, Any]] = []

    def write(original: Path, target: Path) -> bool:
        copied.clear()
        plans.clear()
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
            unchanged = etree.tostring(
                root, encoding="UTF-8", xml_declaration=True, standalone=True
            )

            def find(obj: Any) -> Any:
                try:
                    return editor._find_object_node(
                        root, ooxml_id=obj.ooxml_id, kind=obj.kind, include_group_children=True
                    )
                except CoreDomainError as error:
                    if error.code != "PRESENTATION_EDIT_TARGET_NOT_FOUND":
                        raise
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        f"{obj.name} is stored as alternate content and its format stays "
                        "read-only.",
                    ) from error

            source_node = find(painter)
            template = _source_run(source_node) if painter.kind == "sp" else None
            if template is not None:
                template = copy.deepcopy(template)
                for link in [item for item in template if item.tag in LINKS]:
                    template.remove(link)
            source_sppr = _sppr(source_node)
            source_style = source_node.find(f"{P}style")
            for obj in targets:
                assert obj is not None
                node = find(obj)
                both_shapes = painter.kind == obj.kind == "sp"
                categories = (
                    {name for name, _ in CATEGORIES}
                    if both_shapes
                    else {"line", "effects", "scene3d", "shape3d"}
                )
                parts = [
                    item
                    for name, tags in CATEGORIES
                    if name in categories
                    for item in source_sppr
                    if item.tag in tags
                ]
                if both_shapes and source_style is not None:
                    parts.append(source_style)
                text = (
                    both_shapes
                    and template is not None
                    and node.find(f"{P}txBody") is not None
                    and not _placeholder(source_node)
                    and not _placeholder(node)
                )
                if text:
                    parts.append(template)
                if any(_has_relationships(item) for item in parts):
                    raise CoreDomainError(
                        "PRESENTATION_EDIT_UNSUPPORTED",
                        "The source formatting refers to package parts, such as a picture "
                        "fill, and cannot be copied.",
                    )
                _paint_sppr(source_node, node, categories)
                if both_shapes:
                    _paint_style(source_node, node)
                if text:
                    _paint_text(template, node)
                plans.append((obj, categories, both_shapes, template if text else None))
                copied[obj.object_id] = [
                    *(["fill", "theme style"] if both_shapes else []),
                    "outline",
                    "effects",
                    *(["text"] if text else []),
                ]
            payload = etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)
            if payload == unchanged:
                return False
            with zipfile.ZipFile(target, "w", allowZip64=True) as output:
                output.comment = archive.comment
                for info in archive.infolist():
                    if info.filename == slide.part_name:
                        output.writestr(copy.copy(info), payload)
                    else:
                        with (
                            archive.open(info) as reader,
                            output.open(copy.copy(info), "w") as writer,
                        ):
                            shutil.copyfileobj(reader, writer, length=1024 * 1024)
        with zipfile.ZipFile(target) as written:
            written_root = _parse_xml_part(written, written.getinfo(slide.part_name))
        written_source = editor._find_object_node(
            written_root, ooxml_id=painter.ooxml_id, kind=painter.kind, include_group_children=True
        )
        structural = all(
            _verify_painted(
                written_root,
                written_source,
                editor._find_object_node(
                    written_root, ooxml_id=obj.ooxml_id, kind=obj.kind, include_group_children=True
                ),
                categories,
                both_shapes,
                text_template,
            )
            for obj, categories, both_shapes, text_template in plans
        )
        with target.open("rb") as handle:
            updated = inspect_pptx_snapshot(
                handle,
                document_id=document,
                expected_sha256=editor._sha256_path(target),
                byte_size=target.stat().st_size,
            )
        before = {o.object_id: o for page in fidelity.slides for o in page.objects}
        after = {o.object_id: o for page in updated.slides for o in page.objects}
        painted_after = after.get(source_id)

        def neutral(item: Any) -> Any:
            return dataclasses.replace(item, **FORMAT_FIELDS)

        valid = (
            structural
            and painted_after == painter
            and set(after) == set(before)
            and all(after[k] == v for k, v in before.items() if k not in ids)
            and all(
                obj is not None
                and obj.object_id in after
                and neutral(after[obj.object_id]) == neutral(obj)
                for obj in targets
            )
        )
        if not valid:
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The copied formatting did not pass validation.",
            )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {
        **result,
        "slide_id": slide_id,
        "source_object_id": source_id,
        "copied": [{"object_id": k, "aspects": v} for k, v in copied.items()],
    }
