"""Reviewed external click links across a text shape's runs."""

import zipfile
from pathlib import Path

import pytest
from lxml import etree
from test_bullet_marker import NS, A, _Deck
from test_presentation_workspace_source import _call

from presenter_core.presentation.fidelity import HYPERLINK_REL_TYPE, REL_NS

REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _keep(_properties: etree._Element) -> None:
    pass


class _Links(_Deck):
    def link(self, url: str | None, expected: str | None = None, *, use_current: bool = True):
        target, slide_id = self.target()
        objects = self.objects()
        current = objects[target["object_id"]]["hyperlink"]
        reply = _call(
            self.core,
            "link",
            "presentation.workspace.set_text_hyperlink",
            {
                "project_id": self.project,
                "document_id": self.document,
                "expected_revision_id": self.revision,
                "slide_id": slide_id,
                "object_id": target["object_id"],
                "expected_text": target["current_text"],
                "expected_url": current["url"] if use_current else expected,
                "replacement_url": url,
            },
        )
        if reply["ok"]:
            self.revision = reply["result"]["revision_id"]
        return reply

    def objects(self) -> dict[str, dict]:
        inventory = _call(
            self.core,
            "objects",
            "presentation.workspace.list_text_targets",
            {
                "project_id": self.project,
                "document_id": self.document,
                "revision_id": self.revision,
                "slide_number": self.slide_number,
            },
        )
        return {item["object_id"]: item for item in inventory["result"]["objects"]}

    def hyperlink(self) -> dict | None:
        return self.objects()[self.target()[0]["object_id"]]["hyperlink"]

    def parts(self) -> tuple[list[etree._Element], list[etree._Element]]:
        with self.core._storage.project_database(self.project) as connection:
            row = connection.execute(
                "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
                (self.revision,),
            ).fetchone()
        path = self.core._storage.paths.snapshot_path(
            self.project, row["local_snapshot_path"], require_exists=True
        )
        name = f"slide{self.slide_number}.xml"
        with zipfile.ZipFile(path) as archive:
            rels = etree.fromstring(archive.read(f"ppt/slides/_rels/{name}.rels"))
        links = [item for item in rels if item.get("Type") == HYPERLINK_REL_TYPE]
        runs = [
            run
            for properties in self.properties()
            for run in properties.getparent().findall("a:r", NS)
        ]
        return links, runs


def test_link_sets_changes_and_removes_without_orphans(tmp_path: Path) -> None:
    deck = _Links(tmp_path, _keep)
    try:
        assert deck.hyperlink() == {"url": None, "slide_id": None}
        assert deck.link("https://example.com/report")["ok"]
        links, runs = deck.parts()
        assert [(item.get("Target"), item.get("TargetMode")) for item in links] == [
            ("https://example.com/report", "External")
        ]
        assert {run.find(f"{A}rPr/{A}hlinkClick").get(f"{{{REL_NS}}}id") for run in runs} == {
            links[0].get("Id")
        }
        assert deck.hyperlink() == {"url": "https://example.com/report", "slide_id": None}

        assert deck.link("mailto:team@example.com")["ok"]
        links, _ = deck.parts()
        assert [item.get("Target") for item in links] == ["mailto:team@example.com"]

        assert deck.link(None)["ok"]
        links, runs = deck.parts()
        assert links == []
        assert all(run.find(f"{A}rPr/{A}hlinkClick") is None for run in runs)
        assert deck.hyperlink() == {"url": None, "slide_id": None}
        same = deck.link(None)
        assert same["ok"] and same["result"]["changed"] is False
    finally:
        deck.core.close()


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///C:/secret.txt",
        "http://",
        "slides/next",
        "https://example.com/a b",
        "mailto:nobody",
        "h" * 2049,
    ],
)
def test_unsafe_or_invalid_links_are_rejected(tmp_path: Path, url: str) -> None:
    deck = _Links(tmp_path, _keep)
    try:
        reply = deck.link(url)
        assert not reply["ok"] and reply["error"]["code"] == "INVALID_REQUEST"
    finally:
        deck.core.close()


def test_stale_expected_link_is_rejected(tmp_path: Path) -> None:
    deck = _Links(tmp_path, _keep)
    try:
        reply = deck.link("https://example.com", "https://old.example.com", use_current=False)
        assert not reply["ok"] and reply["error"]["code"] == "PRESENTATION_EDIT_STALE_TARGET"
    finally:
        deck.core.close()


def test_internal_slide_jump_links_stay_read_only(tmp_path: Path) -> None:
    def jump(properties: etree._Element) -> None:
        run = properties.getparent().find("a:r", NS)
        node = run.find(f"{A}rPr")
        if node is None:
            node = etree.Element(f"{A}rPr")
            run.insert(0, node)
        link = etree.SubElement(
            node, f"{A}hlinkClick", action="ppaction://hlinkshowjump?jump=nextslide"
        )
        link.set(f"{{{REL_NS}}}id", "")

    deck = _Links(tmp_path, jump)
    try:
        assert deck.hyperlink() is None
    finally:
        deck.core.close()


def test_link_can_jump_to_another_slide_and_be_removed(tmp_path: Path) -> None:
    deck = _Links(tmp_path, _keep)
    try:
        other = next(number for number in (1, 2, 3) if number != deck.slide_number)
        target_slide = _call(
            deck.core,
            "other",
            "presentation.workspace.list_text_targets",
            {
                "project_id": deck.project,
                "document_id": deck.document,
                "revision_id": deck.revision,
                "slide_number": other,
            },
        )["result"]["slide_id"]
        target, slide_id = deck.target()
        reply = _call(
            deck.core,
            "jump",
            "presentation.workspace.set_text_hyperlink",
            {
                "project_id": deck.project,
                "document_id": deck.document,
                "expected_revision_id": deck.revision,
                "slide_id": slide_id,
                "object_id": target["object_id"],
                "expected_text": target["current_text"],
                "expected_url": None,
                "replacement_slide_id": target_slide,
            },
        )
        assert reply["ok"], reply
        deck.revision = reply["result"]["revision_id"]
        assert deck.hyperlink() == {"url": None, "slide_id": target_slide}
        with deck.core._storage.project_database(deck.project) as connection:
            row = connection.execute(
                "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
                (deck.revision,),
            ).fetchone()
        path = deck.core._storage.paths.snapshot_path(
            deck.project, row["local_snapshot_path"], require_exists=True
        )
        with zipfile.ZipFile(path) as archive:
            rels = etree.fromstring(
                archive.read(f"ppt/slides/_rels/slide{deck.slide_number}.xml.rels")
            )
        jumps = [item for item in rels if item.get("Type", "").endswith("/slide")]
        assert [item.get("Target") for item in jumps] == [f"slide{other}.xml"]
        _links, runs = deck.parts()
        assert {run.find(f"{A}rPr/{A}hlinkClick").get("action") for run in runs} == {
            "ppaction://hlinksldjump"
        }
        target, slide_id = deck.target()
        cleared = _call(
            deck.core,
            "clear",
            "presentation.workspace.set_text_hyperlink",
            {
                "project_id": deck.project,
                "document_id": deck.document,
                "expected_revision_id": deck.revision,
                "slide_id": slide_id,
                "object_id": target["object_id"],
                "expected_text": target["current_text"],
                "expected_slide_id": target_slide,
                "replacement_url": None,
            },
        )
        assert cleared["ok"], cleared
        deck.revision = cleared["result"]["revision_id"]
        assert deck.hyperlink() == {"url": None, "slide_id": None}
    finally:
        deck.core.close()
