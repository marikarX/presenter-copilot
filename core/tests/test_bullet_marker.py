"""Reviewed bullet color/size edits and plain text-font bullet tolerance."""

import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from lxml import etree
from test_presentation_workspace_source import (
    FIXTURE_ROOT,
    _call,
    _import_presentation,
    _open,
    _project_id,
    _write_multirun_text_fixture,
)

from presenter_core.ipc.core import CoreService
from presenter_core.presentation.fidelity import DRAWING_NS, PRESENTATION_NS
from presenter_core.providers.edit_plan_schema import _STYLE_PROPERTIES

NS = {"p": PRESENTATION_NS, "a": DRAWING_NS}
A = f"{{{DRAWING_NS}}}"


def _fixture(tmp_path: Path, mutate: Callable[[etree._Element], None]) -> tuple[Path, int, str]:
    base = tmp_path / "base.pptx"
    slide_number, shape_id = _write_multirun_text_fixture(
        FIXTURE_ROOT / "deck" / "presentation.pptx", base
    )
    target = tmp_path / "bullets.pptx"
    with zipfile.ZipFile(base) as source, zipfile.ZipFile(target, "w") as output:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == f"ppt/slides/slide{slide_number}.xml":
                root = etree.fromstring(content)
                for properties in root.xpath(
                    ".//p:sp[p:nvSpPr/p:cNvPr[@id=$id]]/p:txBody/a:p/a:pPr",
                    namespaces=NS,
                    id=shape_id,
                ):
                    mutate(properties)
                content = etree.tostring(root, encoding="UTF-8", xml_declaration=True)
            output.writestr(info, content)
    return target, slide_number, shape_id


def _with_font(typeface: str) -> Callable[[etree._Element], None]:
    def mutate(properties: etree._Element) -> None:
        bullet = properties.find(f"{A}buChar")
        assert bullet is not None
        bullet.addprevious(etree.Element(f"{A}buFont", typeface=typeface))

    return mutate


class _Deck:
    def __init__(self, tmp_path: Path, mutate: Callable[[etree._Element], None]) -> None:
        path, self.slide_number, self.shape_id = _fixture(tmp_path, mutate)
        self.core = CoreService(data_root=tmp_path / "data")
        self.project = _project_id(self.core)
        self.document = _import_presentation(self.core, self.project, path)["id"]
        self.revision = _open(self.core, self.project, self.document)["revision_id"]

    def target(self) -> tuple[dict, str]:
        inventory = _call(
            self.core,
            "targets",
            "presentation.workspace.list_text_targets",
            {
                "project_id": self.project,
                "document_id": self.document,
                "revision_id": self.revision,
                "slide_number": self.slide_number,
            },
        )
        assert inventory["ok"], inventory
        target = next(
            item
            for item in inventory["result"]["targets"]
            if item["ooxml_shape_id"] == self.shape_id
        )
        return target, inventory["result"]["slide_id"]

    def format(self, style: dict) -> dict:
        target, slide_id = self.target()
        reply = _call(
            self.core,
            "format",
            "presentation.workspace.format_text_shape",
            {
                "project_id": self.project,
                "document_id": self.document,
                "expected_revision_id": self.revision,
                "slide_id": slide_id,
                "object_id": target["object_id"],
                "expected_text": target["current_text"],
                "expected_style_fingerprint": target["text_style"]["fingerprint"],
                "replacement_style": style,
            },
        )
        if reply["ok"]:
            self.revision = reply["result"]["revision_id"]
        return reply

    def properties(self) -> list[etree._Element]:
        with self.core._storage.project_database(self.project) as connection:
            row = connection.execute(
                "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
                (self.revision,),
            ).fetchone()
        path = self.core._storage.paths.snapshot_path(
            self.project, row["local_snapshot_path"], require_exists=True
        )
        with zipfile.ZipFile(path) as archive:
            root = etree.fromstring(archive.read(f"ppt/slides/slide{self.slide_number}.xml"))
        return root.xpath(
            ".//p:sp[p:nvSpPr/p:cNvPr[@id=$id]]/p:txBody/a:p/a:pPr",
            namespaces=NS,
            id=self.shape_id,
        )


def _names(properties: etree._Element) -> list[str]:
    return [child.tag.removeprefix(A) for child in properties]


def test_plain_text_font_bullets_are_editable_and_font_is_preserved(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, _with_font("Arial"))
    try:
        style = deck.target()[0]["text_style"]
        assert style["bullet_state"] == "bullet" and style["bullet_editable"]
        assert style["bullet_color_editable"] and style["bullet_size_editable"]
        assert style["bullet_color"] is None and style["bullet_size_percent"] is None
        reply = deck.format({"bullet_mode": "numbered_alpha_lower"})
        assert reply["ok"], reply
        for properties in deck.properties():
            assert properties.find(f"{A}buFont").get("typeface") == "Arial"
            assert properties.find(f"{A}buAutoNum").get("type") == "alphaLcPeriod"
            assert properties.find(f"{A}buChar") is None
    finally:
        deck.core.close()


def test_bullet_color_and_size_apply_in_schema_order_and_read_back(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, _with_font("Calibri"))
    try:
        reply = deck.format({"bullet_color": "#c00000", "bullet_size_percent": 150})
        assert reply["ok"], reply
        assert reply["result"]["changed"] is True
        for properties in deck.properties():
            names = [n for n in _names(properties) if n.startswith("bu")]
            assert names == ["buClr", "buSzPct", "buFont", "buChar"]
            assert properties.find(f"{A}buClr/{A}srgbClr").get("val") == "C00000"
            assert properties.find(f"{A}buSzPct").get("val") == "150000"
        style = deck.target()[0]["text_style"]
        assert style["bullet_color"] == "#C00000"
        assert style["bullet_size_percent"] == 150
        assert style["bullet_state"] == "bullet"
        # Changing the marker type keeps the reviewed color and size.
        assert deck.format({"bullet_mode": "bullet_square"})["ok"]
        style = deck.target()[0]["text_style"]
        assert (style["bullet_state"], style["bullet_color"], style["bullet_size_percent"]) == (
            "bullet_square",
            "#C00000",
            150,
        )
        # Re-applying the same values is a no-op without a new revision.
        same = deck.format({"bullet_color": "#C00000", "bullet_size_percent": 150})
        assert same["ok"] and same["result"]["changed"] is False
    finally:
        deck.core.close()


def _theme_color(properties: etree._Element) -> None:
    color = etree.Element(f"{A}buClr")
    etree.SubElement(color, f"{A}schemeClr", val="accent1")
    properties.find(f"{A}buChar").addprevious(color)


@pytest.mark.parametrize(
    "mutate",
    [_with_font("Wingdings"), _theme_color],
    ids=["symbol-font", "theme-color"],
)
def test_unsupported_bullet_decoration_stays_read_only(tmp_path: Path, mutate) -> None:
    deck = _Deck(tmp_path, mutate)
    try:
        style = deck.target()[0]["text_style"]
        assert not style["bullet_editable"]
        assert not style["bullet_color_editable"] and not style["bullet_size_editable"]
        for change in ({"bullet_color": "#000000"}, {"bullet_mode": "numbered"}):
            reply = deck.format(change)
            assert not reply["ok"]
            assert reply["error"]["code"] == "PRESENTATION_EDIT_UNSUPPORTED"
    finally:
        deck.core.close()


@pytest.mark.parametrize(
    "style",
    [
        {"bullet_color": "red"},
        {"bullet_color": "#12345"},
        {"bullet_size_percent": 24},
        {"bullet_size_percent": 401},
        {"bullet_size_percent": 100.5},
    ],
)
def test_invalid_bullet_decoration_values_are_rejected(tmp_path: Path, style) -> None:
    deck = _Deck(tmp_path, _with_font("Arial"))
    try:
        reply = deck.format(style)
        assert not reply["ok"] and reply["error"]["code"] == "INVALID_REQUEST"
    finally:
        deck.core.close()


def test_copilot_schema_exposes_bullet_decoration() -> None:
    assert _STYLE_PROPERTIES["bullet_color"]["minLength"] == 7
    assert _STYLE_PROPERTIES["bullet_size_percent"]["minimum"] == 25
    assert _STYLE_PROPERTIES["bullet_size_percent"]["maximum"] == 400
