"""A slide's entrance and exit animations."""

import io
import zipfile
from pathlib import Path

from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches
from test_presentation_workspace_source import _call, _import_presentation, _open, _project_id

from presenter_core.ipc.core import CoreService
from presenter_core.presentation.fidelity import PRESENTATION_NS

P = f"{{{PRESENTATION_NS}}}"

# A custom entrance (Split, preset 16) with a 2 s duration on the box, and an
# emphasis variant used for the read-only case.
_TIMING = """<p:timing xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
<p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>
<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>
<p:par><p:cTn id="3" fill="hold"><p:stCondLst><p:cond delay="indefinite"/></p:stCondLst>
<p:childTnLst>
<p:par><p:cTn id="4" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>
<p:par><p:cTn id="5" presetID="16" presetClass="{cls}" presetSubtype="21" fill="hold" grpId="0"
 nodeType="clickEffect"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>
<p:set><p:cBhvr><p:cTn id="6" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst>
</p:cTn><p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl><p:attrNameLst>
<p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr>
<p:to><p:strVal val="visible"/></p:to></p:set>
<p:animEffect transition="in" filter="barn(inVertical)"><p:cBhvr><p:cTn id="7" dur="2000"/>
<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>
</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>
</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn>
<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond>
</p:prevCondLst>
<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond>
</p:nextCondLst>
</p:seq></p:childTnLst></p:cTn></p:par></p:tnLst>
<p:bldLst><p:bldP spid="{spid}" grpId="0" animBg="1"/></p:bldLst></p:timing>"""


class _Deck:
    def __init__(self, tmp_path: Path, timing_class: str | None = None) -> None:
        source = tmp_path / "animations.pptx"
        deck = Presentation()
        slide = deck.slides.add_slide(deck.slide_layouts[5])
        slide.shapes.title.text = "Title"
        box = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(1), Inches(2), Inches(3), Inches(2)
        )
        box.name = "Box"
        box.text = "Point"
        for extra in ("Second", "", "Third"):
            box.text_frame.add_paragraph().text = extra
        image = io.BytesIO()
        Image.new("RGB", (32, 24), (40, 120, 200)).save(image, "PNG")
        image.seek(0)
        slide.shapes.add_picture(image, Inches(5), Inches(2), Inches(3), Inches(2)).name = "Pic"
        if timing_class:
            slide._element.append(
                etree.fromstring(_TIMING.format(cls=timing_class, spid=box.shape_id))
            )
        deck.save(source)
        self.core = CoreService(data_root=tmp_path / "data")
        self.project = _project_id(self.core)
        self.document = _import_presentation(self.core, self.project, source)["id"]
        self.revision = _open(self.core, self.project, self.document)["revision_id"]
        targets = _call(
            self.core,
            "targets",
            "presentation.workspace.list_text_targets",
            {
                "project_id": self.project,
                "document_id": self.document,
                "revision_id": self.revision,
                "slide_number": 1,
            },
        )["result"]
        self.slide_id = targets["slide_id"]
        self.ids = {obj["name"]: obj["object_id"] for obj in targets["objects"]}
        self.objects = targets["objects"]

    def scope(self) -> dict:
        return {
            "project_id": self.project,
            "document_id": self.document,
            "expected_revision_id": self.revision,
            "slide_id": self.slide_id,
        }

    def state(self) -> dict:
        reply = _call(self.core, "get", "presentation.workspace.get_slide_animations", self.scope())
        assert reply["ok"], reply
        return reply["result"]

    def apply(self, effects: list[tuple[str, str, str]], fingerprint: str | None = None) -> dict:
        reply = _call(
            self.core,
            "set",
            "presentation.workspace.set_slide_animations",
            {
                **self.scope(),
                "expected_fingerprint": fingerprint or self.state()["fingerprint"],
                "effects": [
                    {"object_id": self.ids[name], "effect": effect, "start": start}
                    for name, effect, start in effects
                ],
            },
        )
        if reply["ok"]:
            self.revision = reply["result"]["revision_id"]
        return reply

    def timing(self) -> etree._Element | None:
        with self.core._storage.project_database(self.project) as connection:
            row = connection.execute(
                "SELECT local_snapshot_path FROM presentation_revisions WHERE id=?",
                (self.revision,),
            ).fetchone()
        path = self.core._storage.paths.snapshot_path(
            self.project, row["local_snapshot_path"], require_exists=True
        )
        with zipfile.ZipFile(path) as archive:
            return etree.fromstring(archive.read("ppt/slides/slide1.xml")).find(f"{P}timing")


def _summary(state: dict) -> list[tuple[str, str, str]]:
    return [(e["name"], e["effect"], e["start"]) for e in state["effects"]]


def test_animations_add_reorder_and_remove(tmp_path: Path) -> None:
    deck = _Deck(tmp_path)
    try:
        initial = deck.state()
        assert initial["editable"] and initial["effects"] == []
        assert {c["name"] for c in initial["candidates"]} >= {"Title 1", "Box", "Pic"}
        plan = [
            ("Title 1", "fade", "on_click"),
            ("Box", "fly_in", "after_previous"),
            ("Pic", "zoom", "with_previous"),
        ]
        assert deck.apply(plan)["ok"]
        assert _summary(deck.state()) == plan
        timing = deck.timing()
        assert timing is not None
        ids = [int(node.get("id")) for node in timing.iter(f"{P}cTn")]
        assert ids == list(range(1, len(ids) + 1))
        # Text shapes get a whole-object build entry; the picture does not.
        assert len(timing.findall(f"{P}bldLst/{P}bldP")) == 2
        # After-previous starts a second time group 500 ms into the click.
        groups = timing.xpath(
            ".//p:cTn[@nodeType='mainSeq']/p:childTnLst/p:par/p:cTn/p:childTnLst/p:par/p:cTn",
            namespaces={"p": PRESENTATION_NS},
        )
        assert [g.find(f"{P}stCondLst/{P}cond").get("delay") for g in groups] == ["0", "500"]
        box = next(o for o in deck.objects if o["name"] == "Box")
        assert box["delete_editable"]
        refreshed = _call(
            deck.core,
            "t",
            "presentation.workspace.list_text_targets",
            {
                "project_id": deck.project,
                "document_id": deck.document,
                "revision_id": deck.revision,
                "slide_number": 1,
            },
        )["result"]["objects"]
        assert not next(o for o in refreshed if o["name"] == "Box")["delete_editable"]

        reordered = [("Pic", "appear", "with_previous"), ("Title 1", "fade", "on_click")]
        assert deck.apply(reordered)["ok"]
        assert _summary(deck.state()) == reordered
        assert deck.apply([])["ok"]
        assert deck.state()["effects"] == [] and deck.timing() is None
    finally:
        deck.core.close()


def test_custom_entrance_kept_and_guards(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, timing_class="entr")
    try:
        state = deck.state()
        assert _summary(state) == [("Box", "custom", "on_click")]
        assert deck.apply([("Title 1", "wipe", "on_click"), ("Box", "custom", "on_click")])["ok"]
        kept = deck.timing().xpath(".//p:cTn[@presetID='16']", namespaces={"p": PRESENTATION_NS})
        assert len(kept) == 1 and kept[0].xpath(
            ".//p:cTn[@dur='2000']", namespaces={"p": PRESENTATION_NS}
        )
        stale = deck.apply([], fingerprint=state["fingerprint"])
        assert not stale["ok"] and stale["error"]["code"] == "PRESENTATION_EDIT_STALE_TARGET"
        bad = deck.apply([("Pic", "custom", "on_click")])
        assert not bad["ok"] and bad["error"]["code"] == "INVALID_REQUEST"
        duplicate = deck.apply([("Pic", "fade", "on_click"), ("Pic", "wipe", "on_click")])
        assert not duplicate["ok"] and duplicate["error"]["code"] == "INVALID_REQUEST"
    finally:
        deck.core.close()


def test_custom_emphasis_is_kept_and_motion_paths_stay_read_only(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, timing_class="emph")
    try:
        assert _summary(deck.state()) == [("Box", "custom_emphasis", "on_click")]
        reply = deck.apply(
            [("Box", "custom_emphasis", "on_click"), ("Pic", "pulse", "after_previous")]
        )
        assert reply["ok"], reply.get("error")
        assert _summary(deck.state()) == [
            ("Box", "custom_emphasis", "on_click"),
            ("Pic", "pulse", "after_previous"),
        ]
    finally:
        deck.core.close()
    (tmp_path / "motion").mkdir()
    motion = _Deck(tmp_path / "motion", timing_class="path")
    try:
        state = motion.state()
        assert not state["editable"] and "motion" in state["reason"]
        reply = motion.apply([])
        assert not reply["ok"] and reply["error"]["code"] == "PRESENTATION_EDIT_UNSUPPORTED"
    finally:
        motion.core.close()


def test_media_timing_reason(tmp_path: Path) -> None:
    deck = _Deck(tmp_path, timing_class="mediacall")
    try:
        state = deck.state()
        assert not state["editable"] and "audio or video" in state["reason"]
    finally:
        deck.core.close()


def test_exit_effects_follow_entrances(tmp_path: Path) -> None:
    deck = _Deck(tmp_path)
    try:
        plan = [
            ("Box", "fade", "on_click"),
            ("Pic", "zoom_out", "with_previous"),
            ("Box", "fly_out", "on_click"),
            ("Title 1", "disappear", "after_previous"),
        ]
        reply = deck.apply(plan)
        assert reply["ok"], reply.get("error")
        assert _summary(deck.state()) == plan
        timing = deck.timing()
        ns = {"p": PRESENTATION_NS}
        exits = timing.xpath(".//p:cTn[@presetClass='exit']", namespaces=ns)
        assert [(n.get("presetID"), n.get("presetSubtype")) for n in exits] == [
            ("23", "16"),
            ("2", "4"),
            ("1", "0"),
        ]
        # Every exit ends by hiding its object: at once for Disappear, else at 499 ms.
        for node, delay in zip(exits, ("499", "499", "0"), strict=True):
            hide = node.xpath(".//p:set[p:to/p:strVal/@val='hidden']", namespaces=ns)
            assert hide and hide[0].find(".//p:cond", ns).get("delay") == delay
        # The box enters (group 0) and leaves (group 1), as PowerPoint numbers them.
        box_groups = [
            n.get("grpId")
            for n in timing.xpath(".//p:cTn[@presetClass]", namespaces=ns)
            if n.find(".//p:spTgt", ns).get("spid") == timing.find(".//p:spTgt", ns).get("spid")
        ]
        assert box_groups == ["0", "1"]
        builds = [(b.get("spid"), b.get("grpId")) for b in timing.iter(f"{P}bldP")]
        assert len(builds) == len(set(builds)) == 3  # Box twice, the title once

        twice = deck.apply([("Box", "fade_out", "on_click"), ("Box", "disappear", "on_click")])
        assert not twice["ok"] and twice["error"]["code"] == "INVALID_REQUEST"
        kept = deck.apply([("Box", "fly_out", "on_click")])
        assert kept["ok"]
        assert _summary(deck.state()) == [("Box", "fly_out", "on_click")]
    finally:
        deck.core.close()


def test_paragraph_builds_step_through_text(tmp_path: Path) -> None:
    deck = _Deck(tmp_path)
    try:
        box = next(c for c in deck.state()["candidates"] if c["name"] == "Box")
        # Empty paragraphs cannot be animated, so index 2 is skipped.
        assert [(p["index"], p["text"]) for p in box["paragraphs"]] == [
            (0, "Point"),
            (1, "Second"),
            (3, "Third"),
        ]

        def entry(effect: str, start: str, paragraph: int | None) -> dict:
            return {
                "object_id": deck.ids["Box"],
                "effect": effect,
                "start": start,
                "paragraph": paragraph,
            }

        def apply(entries: list[dict]) -> dict:
            reply = _call(
                deck.core,
                "set",
                "presentation.workspace.set_slide_animations",
                {
                    **deck.scope(),
                    "expected_fingerprint": deck.state()["fingerprint"],
                    "effects": entries,
                },
            )
            if reply["ok"]:
                deck.revision = reply["result"]["revision_id"]
            return reply

        build = [
            entry("fade", "after_previous", 0),
            entry("fade", "on_click", 1),
            entry("fade", "on_click", 3),
        ]
        reply = apply(build)
        assert reply["ok"], reply.get("error")
        assert [(e["effect"], e["start"], e["paragraph"]) for e in deck.state()["effects"]] == [
            ("fade", "after_previous", 0),
            ("fade", "on_click", 1),
            ("fade", "on_click", 3),
        ]
        timing = deck.timing()
        ns = {"p": PRESENTATION_NS}
        ranges = [(r.get("st"), r.get("end")) for r in timing.iterfind(".//p:pRg", ns)]
        assert set(ranges) == {("0", "0"), ("1", "1"), ("3", "3")}
        # One paragraph build: a single group and a build-by-paragraph entry.
        assert {n.get("grpId") for n in timing.iterfind(".//p:cTn[@presetClass]", ns)} == {"0"}
        assert [(b.get("build"), b.get("grpId")) for b in timing.iterfind(".//p:bldP", ns)] == [
            ("p", "0")
        ]

        # The whole box can still leave afterwards; a missing paragraph is refused.
        assert apply([*build, entry("fade_out", "on_click", None)])["ok"]
        missing = apply([entry("fade", "on_click", 2)])
        assert not missing["ok"] and missing["error"]["code"] == "INVALID_REQUEST"
        twice = apply([entry("fade", "on_click", 1), entry("wipe", "on_click", 1)])
        assert not twice["ok"] and twice["error"]["code"] == "INVALID_REQUEST"
    finally:
        deck.core.close()


def test_emphasis_effects_written_as_powerpoint_does(tmp_path: Path) -> None:
    deck = _Deck(tmp_path)
    try:
        plan = [
            ("Box", "fade", "on_click"),
            ("Box", "grow_shrink", "on_click"),
            ("Pic", "spin", "with_previous"),
            ("Title 1", "teeter", "after_previous"),
        ]
        reply = deck.apply(plan)
        assert reply["ok"], reply.get("error")
        assert _summary(deck.state()) == plan
        ns = {"p": PRESENTATION_NS}
        emphasis = deck.timing().xpath(".//p:cTn[@presetClass='emph']", namespaces=ns)
        assert [n.get("presetID") for n in emphasis] == ["6", "8", "32"]
        assert emphasis[0].find(".//p:animScale/p:by", ns).get("x") == "150000"
        assert len(emphasis[2].findall(".//p:animRot", ns)) == 5
        twice = deck.apply([("Box", "spin", "on_click"), ("Box", "pulse", "on_click")])
        assert not twice["ok"] and twice["error"]["code"] == "INVALID_REQUEST"
    finally:
        deck.core.close()
