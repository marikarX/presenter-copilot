from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from lxml import etree

from presenter_core.errors import CoreDomainError
from presenter_core.ipc.core import CoreService
from presenter_core.presentation.editing import _next_ooxml_shape_id
from presenter_core.presentation.fidelity import (
    DRAWING_NS,
    MARKUP_COMPATIBILITY_NS,
    PRESENTATION_NS,
    REL_NS,
    _objects_for_slide,
)

_NS = {"p": PRESENTATION_NS, "a": DRAWING_NS}


def _slide_root() -> tuple[etree._Element, etree._Element]:
    root = etree.Element(
        f"{{{PRESENTATION_NS}}}sld",
        nsmap={
            "p": PRESENTATION_NS,
            "a": DRAWING_NS,
            "r": REL_NS,
            "mc": MARKUP_COMPATIBILITY_NS,
            "p14": "http://schemas.microsoft.com/office/powerpoint/2010/main",
        },
    )
    shape_tree = etree.SubElement(
        etree.SubElement(root, f"{{{PRESENTATION_NS}}}cSld"),
        f"{{{PRESENTATION_NS}}}spTree",
    )
    nonvisual = etree.SubElement(shape_tree, f"{{{PRESENTATION_NS}}}nvGrpSpPr")
    etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}cNvPr", id="1", name="Slide root")
    etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}cNvGrpSpPr")
    etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}nvPr")
    etree.SubElement(shape_tree, f"{{{PRESENTATION_NS}}}grpSpPr")
    return root, shape_tree


def _shape(shape_id: str, name: str = "Shape") -> etree._Element:
    shape = etree.Element(f"{{{PRESENTATION_NS}}}sp")
    nonvisual = etree.SubElement(shape, f"{{{PRESENTATION_NS}}}nvSpPr")
    etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}cNvPr", id=shape_id, name=name)
    etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}cNvSpPr")
    etree.SubElement(nonvisual, f"{{{PRESENTATION_NS}}}nvPr")
    etree.SubElement(shape, f"{{{PRESENTATION_NS}}}spPr")
    return shape


def _inventory(root: etree._Element):
    return _objects_for_slide(
        root,
        document_id="00000000-0000-4000-8000-000000000001",
        ooxml_slide_id="256",
        slide_width_emu=12_192_000,
        slide_height_emu=6_858_000,
    )


@pytest.mark.parametrize(
    ("requires", "selected_name"),
    [("p14", "Fallback representation"), ("p", "Choice representation")],
)
def test_alternate_content_selects_one_supported_object_and_marks_it_read_only(
    requires: str,
    selected_name: str,
) -> None:
    root, shape_tree = _slide_root()
    alternate = etree.SubElement(shape_tree, f"{{{MARKUP_COMPATIBILITY_NS}}}AlternateContent")
    choice = etree.SubElement(
        alternate,
        f"{{{MARKUP_COMPATIBILITY_NS}}}Choice",
        Requires=requires,
    )
    choice.append(_shape("42", "Choice representation"))
    fallback = etree.SubElement(alternate, f"{{{MARKUP_COMPATIBILITY_NS}}}Fallback")
    fallback.append(_shape("42", "Fallback representation"))

    objects = _inventory(root)

    assert len(objects) == 1
    selected = objects[0]
    assert selected.ooxml_id == "42"
    assert selected.name == selected_name
    assert not selected.text_edit_candidate
    assert not selected.geometry_editable
    assert not selected.delete_editable
    assert selected.text_style is not None and not selected.text_style.editable


def test_group_children_are_inventoried_but_graphic_frame_payloads_are_opaque() -> None:
    root, shape_tree = _slide_root()
    group = etree.SubElement(shape_tree, f"{{{PRESENTATION_NS}}}grpSp")
    group_nonvisual = etree.SubElement(group, f"{{{PRESENTATION_NS}}}nvGrpSpPr")
    etree.SubElement(group_nonvisual, f"{{{PRESENTATION_NS}}}cNvPr", id="2", name="Group")
    etree.SubElement(group_nonvisual, f"{{{PRESENTATION_NS}}}cNvGrpSpPr")
    etree.SubElement(group_nonvisual, f"{{{PRESENTATION_NS}}}nvPr")
    etree.SubElement(group, f"{{{PRESENTATION_NS}}}grpSpPr")
    group.append(_shape("3", "Nested shape"))

    frame = etree.SubElement(shape_tree, f"{{{PRESENTATION_NS}}}graphicFrame")
    frame_nonvisual = etree.SubElement(frame, f"{{{PRESENTATION_NS}}}nvGraphicFramePr")
    etree.SubElement(frame_nonvisual, f"{{{PRESENTATION_NS}}}cNvPr", id="4", name="OLE frame")
    etree.SubElement(frame_nonvisual, f"{{{PRESENTATION_NS}}}cNvGraphicFramePr")
    etree.SubElement(frame_nonvisual, f"{{{PRESENTATION_NS}}}nvPr")
    graphic = etree.SubElement(frame, f"{{{DRAWING_NS}}}graphic")
    graphic_data = etree.SubElement(
        graphic, f"{{{DRAWING_NS}}}graphicData", uri="urn:fixture:ole-fallback"
    )
    for index in range(2):
        nested_picture = etree.SubElement(graphic_data, f"{{{PRESENTATION_NS}}}pic")
        nested_nonvisual = etree.SubElement(nested_picture, f"{{{PRESENTATION_NS}}}nvPicPr")
        etree.SubElement(
            nested_nonvisual,
            f"{{{PRESENTATION_NS}}}cNvPr",
            id="0",
            name=f"Opaque fallback {index}",
        )

    objects = _inventory(root)

    assert [(item.kind, item.ooxml_id, item.name) for item in objects] == [
        ("grpSp", "2", "Group"),
        ("sp", "3", "Nested shape"),
        ("graphicFrame", "4", "OLE frame"),
    ]
    assert _next_ooxml_shape_id(shape_tree) == "5"


def test_id_allocation_tolerates_raw_branch_duplicates_but_stays_above_them() -> None:
    _, shape_tree = _slide_root()
    alternate = etree.SubElement(shape_tree, f"{{{MARKUP_COMPATIBILITY_NS}}}AlternateContent")
    choice = etree.SubElement(
        alternate,
        f"{{{MARKUP_COMPATIBILITY_NS}}}Choice",
        Requires="p14",
    )
    choice.append(_shape("90", "Choice representation"))
    fallback = etree.SubElement(alternate, f"{{{MARKUP_COMPATIBILITY_NS}}}Fallback")
    fallback.append(_shape("90", "Fallback representation"))

    assert _next_ooxml_shape_id(shape_tree) == "91"


def test_effective_duplicate_shape_ids_still_fail_closed() -> None:
    root, shape_tree = _slide_root()
    shape_tree.append(_shape("7", "First"))
    shape_tree.append(_shape("7", "Duplicate"))

    with pytest.raises(CoreDomainError) as error:
        _inventory(root)

    assert error.value.code == "PRESENTATION_FIDELITY_STRUCTURE_INVALID"


@pytest.mark.parametrize("requires", ["", "missing-prefix"])
def test_malformed_alternate_content_requirements_fail_closed(requires: str) -> None:
    root, shape_tree = _slide_root()
    alternate = etree.SubElement(shape_tree, f"{{{MARKUP_COMPATIBILITY_NS}}}AlternateContent")
    choice = etree.SubElement(
        alternate,
        f"{{{MARKUP_COMPATIBILITY_NS}}}Choice",
        Requires=requires,
    )
    choice.append(_shape("8", "Choice"))
    fallback = etree.SubElement(alternate, f"{{{MARKUP_COMPATIBILITY_NS}}}Fallback")
    fallback.append(_shape("8", "Fallback"))

    with pytest.raises(CoreDomainError) as error:
        _inventory(root)

    assert error.value.code == "PRESENTATION_FIDELITY_STRUCTURE_INVALID"


def _write_alternate_content_fixture(destination: Path) -> int:
    source_path = (
        Path(__file__).parents[2] / "samples" / "synthetic-deck" / "deck" / "presentation.pptx"
    )
    slide_part = "ppt/slides/slide1.xml"
    with (
        zipfile.ZipFile(source_path, "r") as source,
        zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as output,
    ):
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == slide_part:
                root = etree.fromstring(payload)
                shape_trees = root.xpath("./p:cSld/p:spTree", namespaces=_NS)
                assert len(shape_trees) == 1
                shape_tree = shape_trees[0]
                raw_ids = [
                    int(value) for value in shape_tree.xpath(".//p:cNvPr/@id", namespaces=_NS)
                ]
                new_id = max(raw_ids) + 100
                source_shape = next(
                    child
                    for child in shape_tree
                    if child.tag == f"{{{PRESENTATION_NS}}}sp"
                    and child.xpath("./p:nvSpPr/p:cNvPr", namespaces=_NS)
                    and not child.xpath("./p:nvSpPr/p:nvPr/p:ph", namespaces=_NS)
                )
                alternate = etree.Element(
                    f"{{{MARKUP_COMPATIBILITY_NS}}}AlternateContent",
                    nsmap={
                        "mc": MARKUP_COMPATIBILITY_NS,
                        "p14": "http://schemas.microsoft.com/office/powerpoint/2010/main",
                    },
                )
                choice = etree.SubElement(
                    alternate,
                    f"{{{MARKUP_COMPATIBILITY_NS}}}Choice",
                    Requires="p14",
                )
                fallback = etree.SubElement(alternate, f"{{{MARKUP_COMPATIBILITY_NS}}}Fallback")
                for branch, name in (
                    (choice, "Compatibility choice"),
                    (fallback, "Compatibility fallback"),
                ):
                    shape = etree.fromstring(etree.tostring(source_shape))
                    nonvisual = shape.xpath("./p:nvSpPr/p:cNvPr", namespaces=_NS)
                    assert len(nonvisual) == 1
                    nonvisual[0].set("id", str(new_id))
                    nonvisual[0].set("name", name)
                    branch.append(shape)
                extension_lists = shape_tree.xpath("./p:extLst", namespaces=_NS)
                insert_at = (
                    shape_tree.index(extension_lists[0]) if extension_lists else len(shape_tree)
                )
                shape_tree.insert(insert_at, alternate)
                payload = etree.tostring(
                    root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=True,
                )
                new_id = max(new_id, *raw_ids)
            output.writestr(info, payload)
    return new_id


def test_text_box_creation_preserves_alternate_content_and_allocates_above_it(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "alternate-content.pptx"
    max_raw_id = _write_alternate_content_fixture(source_path)
    core = CoreService(data_root=tmp_path / "data")
    try:

        def call(request_id: str, method: str, params: dict[str, object]) -> dict[str, object]:
            return core.handle_message(
                {
                    "protocol_version": 1,
                    "type": "request",
                    "request_id": request_id,
                    "method": method,
                    "params": params,
                }
            )

        project_response = call("create-project", "project.create", {"name": "Compatibility"})
        assert project_response["ok"] is True
        project_id = project_response["result"]["project"]["id"]
        imported = call(
            "import-alternate-deck",
            "source.import",
            {
                "project_id": project_id,
                "path": str(source_path),
                "kind": "presentation",
            },
        )
        assert imported["ok"] is True
        document_id = imported["result"]["document"]["id"]
        opened = call(
            "open-alternate-deck",
            "presentation.workspace.open_source",
            {"project_id": project_id, "document_id": document_id},
        )
        assert opened["ok"] is True
        revision_id = opened["result"]["revision_id"]
        inventory = call(
            "list-alternate-deck-targets",
            "presentation.workspace.list_text_targets",
            {
                "project_id": project_id,
                "document_id": document_id,
                "revision_id": revision_id,
                "slide_number": 1,
            },
        )
        assert inventory["ok"] is True
        objects = inventory["result"]["objects"]
        compatibility_object = next(
            item for item in objects if item["name"] == "Compatibility fallback"
        )
        assert compatibility_object["ooxml_shape_id"] == str(max_raw_id)
        assert compatibility_object["geometry_editable"] is False
        assert compatibility_object["delete_editable"] is False

        created = call(
            "create-text-box-with-alternates",
            "presentation.workspace.create_text_box",
            {
                "project_id": project_id,
                "document_id": document_id,
                "expected_revision_id": revision_id,
                "slide_id": inventory["result"]["slide_id"],
                "text": "Created after alternate content",
            },
        )
        assert created["ok"] is True, created
        latest = call(
            "list-created-text-box",
            "presentation.workspace.list_text_targets",
            {
                "project_id": project_id,
                "document_id": document_id,
                "revision_id": created["result"]["revision_id"],
                "slide_number": 1,
            },
        )
        assert latest["ok"] is True
        new_object = next(
            item
            for item in latest["result"]["objects"]
            if item["object_id"] == created["result"]["created_object_id"]
        )
        assert new_object["ooxml_shape_id"] == str(max_raw_id + 1)
        with zipfile.ZipFile(source_path) as before:
            with core._storage.project_database(project_id) as connection:
                row = connection.execute(
                    "SELECT local_snapshot_path FROM presentation_revisions WHERE id = ?",
                    (created["result"]["revision_id"],),
                ).fetchone()
            assert row is not None
            revised_path = core._storage.paths.snapshot_path(
                project_id, row["local_snapshot_path"], require_exists=True
            )
            with zipfile.ZipFile(revised_path) as after:
                original_names = {info.filename for info in before.infolist()}
                assert original_names == {info.filename for info in after.infolist()}
                for name in original_names - {"ppt/slides/slide1.xml"}:
                    assert before.read(name) == after.read(name)
    finally:
        core.close()
