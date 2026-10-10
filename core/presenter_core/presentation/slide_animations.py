"""A slide's entrance and exit animations: which objects appear or leave, with what
effect, in what order.

Only the main click sequence of entrance and exit effects is editable; each object
can have one of each. Emphasis and motion effects, triggers, by-paragraph or chart
builds and alternate-content timing keep the slide read-only. Unchanged effects are
carried over verbatim, so custom durations and delays survive reordering.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import shutil
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.fidelity import (
    PRESENTATION_NS,
    _parse_xml_part,
    inspect_pptx_snapshot,
)

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

P = f"{{{PRESENTATION_NS}}}"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_NS = {"p": PRESENTATION_NS, "mc": MC}
MAX_EFFECTS = 50
# (presetID, presetSubtype, presetClass) for the effects that can be chosen.
EFFECTS = {
    "appear": ("1", "0", "entr"),
    "fade": ("10", "0", "entr"),
    "fly_in": ("2", "4", "entr"),
    "wipe": ("22", "4", "entr"),
    "zoom": ("23", "16", "entr"),
    "disappear": ("1", "0", "exit"),
    "fade_out": ("10", "0", "exit"),
    "fly_out": ("2", "4", "exit"),
    "wipe_out": ("22", "4", "exit"),
    "zoom_out": ("23", "16", "exit"),
}
# An effect this editor does not write is kept as "custom" (entrance) or "custom_exit".
CUSTOM = {"entr": "custom", "exit": "custom_exit"}
CLASSES = {name: value[2] for name, value in EFFECTS.items()} | {
    name: kind for kind, name in CUSTOM.items()
}
STARTS = {"on_click": "clickEffect", "with_previous": "withEffect", "after_previous": "afterEffect"}
_TARGET_KINDS = {"sp": "nvSpPr", "pic": "nvPicPr", "grpSp": "nvGrpSpPr", "cxnSp": "nvCxnSpPr"}


class _ReadOnly(Exception):
    pass


def _targets(root: etree._Element) -> dict[str, bool]:
    """Top-level shape ids that can enter, mapped to whether they hold text."""
    result: dict[str, bool] = {}
    tree = root.find(f"{P}cSld/{P}spTree")
    if tree is None:
        return result
    for child in tree:
        tag = etree.QName(child).localname
        if tag not in _TARGET_KINDS:
            continue
        nonvisual = child.find(f"{P}{_TARGET_KINDS[tag]}/{P}cNvPr")
        if nonvisual is not None and nonvisual.get("id"):
            result[nonvisual.get("id")] = child.find(f"{P}txBody") is not None
    return result


def _child(element: etree._Element, tag: str) -> etree._Element:
    """A child element, or an empty placeholder (lxml elements without children are falsy)."""
    found = element.find(tag)
    return etree.Element("missing") if found is None else found


def _children(element: etree._Element, tag: str) -> list[etree._Element]:
    found = [child for child in element if isinstance(child.tag, str)]
    if any(child.tag != f"{P}{tag}" for child in found):
        raise _ReadOnly("This slide uses an animation structure that stays read-only.")
    return found


def _time_node(par: etree._Element) -> etree._Element:
    node = par.find(f"{P}cTn")
    if node is None:
        raise _ReadOnly("This slide uses an animation structure that stays read-only.")
    return node


def _delays(node: etree._Element) -> list[etree._Element]:
    return list(node.findall(f"{P}stCondLst/{P}cond"))


def _parse(root: etree._Element) -> list[dict[str, Any]]:
    """The editable main sequence, or _ReadOnly with a reason."""
    if root.xpath("./mc:AlternateContent[.//p:timing]", namespaces=_NS):
        raise _ReadOnly("This slide uses newer animation effects that stay read-only.")
    timing = root.find(f"{P}timing")
    if timing is None:
        return []
    if timing.xpath(".//p:cTn[@presetClass='mediacall']", namespaces=_NS):
        raise _ReadOnly("This slide plays audio or video; its timing stays read-only.")
    targets = _targets(root)
    for child in timing:
        if isinstance(child.tag, str) and child.tag not in {f"{P}tnLst", f"{P}bldLst"}:
            raise _ReadOnly("This slide uses an animation structure that stays read-only.")
    builds = timing.find(f"{P}bldLst")
    if builds is not None:
        for build in builds:
            if not isinstance(build.tag, str):
                continue
            if build.tag != f"{P}bldP" or build.get("build", "whole") != "whole" or len(build):
                raise _ReadOnly(
                    "This slide builds text, charts or diagrams in parts; that stays read-only."
                )
    roots = _children(_child(timing, f"{P}tnLst"), "par")
    if not roots:
        return []
    root_node = _time_node(roots[0])
    if len(roots) != 1 or root_node.get("nodeType") != "tmRoot":
        raise _ReadOnly("This slide uses an animation structure that stays read-only.")
    sequences = _children(_child(root_node, f"{P}childTnLst"), "seq")
    if not sequences:
        return []
    main = sequences[0].find(f"{P}cTn")
    if len(sequences) != 1 or main is None or main.get("nodeType") != "mainSeq":
        raise _ReadOnly("This slide has trigger animations that stay read-only.")
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    clicks = _children(_child(main, f"{P}childTnLst"), "par")
    for click_index, click in enumerate(clicks):
        click_node = _time_node(click)
        conditions = _delays(click_node)
        on_begin = any(cond.get("evt") == "onBegin" for cond in conditions)
        if (
            not conditions
            or conditions[0].get("delay") != "indefinite"
            or (on_begin and click_index)
            or len(conditions) > (2 if on_begin else 1)
        ):
            raise _ReadOnly("This slide uses custom animation timing that stays read-only.")
        groups = _children(_child(click_node, f"{P}childTnLst"), "par")
        for group_index, group in enumerate(groups):
            effects = _children(_child(_time_node(group), f"{P}childTnLst"), "par")
            for effect_index, effect in enumerate(effects):
                node = _time_node(effect)
                kind = node.get("presetClass")
                if kind not in CUSTOM:
                    raise _ReadOnly(
                        "This slide has emphasis or motion animations that stay read-only."
                    )
                if effect_index:
                    wanted = "withEffect"
                elif group_index:
                    wanted = "afterEffect"
                elif on_begin:
                    wanted = node.get("nodeType", "")
                else:
                    wanted = "clickEffect"
                if node.get("nodeType") != wanted or wanted not in STARTS.values():
                    raise _ReadOnly("This slide uses custom animation timing that stays read-only.")
                spids = {target.get("spid") for target in effect.iter(f"{P}spTgt")}
                if (
                    len(spids) != 1
                    or any(len(target) for target in effect.iter(f"{P}spTgt"))
                    or effect.xpath(".//p:cond[@evt] | .//p:cond/p:tn", namespaces=_NS)
                ):
                    raise _ReadOnly(
                        "This slide animates text by paragraph or uses triggers; read-only."
                    )
                spid = next(iter(spids))
                if spid not in targets or (spid, kind) in seen:
                    raise _ReadOnly(
                        "This slide animates nested or repeated targets; that stays read-only."
                    )
                seen.add((spid, kind))
                preset = (node.get("presetID"), node.get("presetSubtype", "0"), kind)
                items.append(
                    {
                        "ooxml_id": spid,
                        "class": kind,
                        "effect": next(
                            (name for name, value in EFFECTS.items() if value == preset),
                            CUSTOM[kind],
                        ),
                        "start": next(k for k, v in STARTS.items() if v == node.get("nodeType")),
                        "element": effect,
                    }
                )
    return items


def _fingerprint(root: etree._Element) -> str:
    timing = root.find(f"{P}timing")
    data = b"" if timing is None else etree.tostring(timing, method="c14n")
    return hashlib.sha256(data).hexdigest()


def _state(root: etree._Element, objects: dict[str, Any]) -> dict[str, Any]:
    targets = _targets(root)
    candidates = [
        {"object_id": obj.object_id, "name": obj.name}
        for ooxml_id, obj in objects.items()
        if ooxml_id in targets
    ]
    try:
        items = _parse(root)
    except _ReadOnly as error:
        return {
            "editable": False,
            "reason": str(error),
            "effects": [],
            "candidates": candidates,
            "fingerprint": _fingerprint(root),
        }
    return {
        "editable": True,
        "reason": None,
        "effects": [
            {
                "object_id": objects[item["ooxml_id"]].object_id,
                "name": objects[item["ooxml_id"]].name,
                "effect": item["effect"],
                "start": item["start"],
            }
            for item in items
        ],
        "candidates": candidates,
        "fingerprint": _fingerprint(root),
    }


def slide_animation_state(root: etree._Element, slide: Any) -> dict[str, Any]:
    """The animation state of one parsed slide part, as get_slide_animations reports it."""
    return _state(root, {obj.ooxml_id: obj for obj in slide.objects})


def _element(tag: str, parent: etree._Element | None = None, **attributes: str) -> etree._Element:
    if parent is None:
        return etree.Element(f"{P}{tag}", **attributes)
    return etree.SubElement(parent, f"{P}{tag}", **attributes)


def _behavior(
    parent: etree._Element,
    spid: str,
    duration: str,
    attribute: str | None = None,
    *,
    hold: bool = True,
    additive: bool = False,
) -> etree._Element:
    behavior = _element("cBhvr", parent)
    if additive:
        behavior.set("additive", "base")
    node = _element("cTn", behavior, id="0", dur=duration)
    if hold:
        node.set("fill", "hold")
    if attribute == "style.visibility":
        _element("cond", _element("stCondLst", node), delay="0")
    _element("spTgt", _element("tgtEl", behavior), spid=spid)
    if attribute:
        _element("attrName", _element("attrNameLst", behavior)).text = attribute
    return behavior


def _canonical(spid: str, effect: str) -> etree._Element:
    """The effect exactly as PowerPoint writes it (captured from PowerPoint's own output)."""
    preset, subtype, kind = EFFECTS[effect]
    if kind == "exit":
        return _canonical_exit(spid, effect)
    par = _element("par")
    node = _element(
        "cTn",
        par,
        id="0",
        presetID=preset,
        presetClass="entr",
        presetSubtype=subtype,
        fill="hold",
        grpId="0",
        nodeType="clickEffect",
    )
    _element("cond", _element("stCondLst", node), delay="0")
    children = _element("childTnLst", node)
    visible = _element("set", children)
    _behavior(visible, spid, "1", "style.visibility")
    _element("strVal", _element("to", visible), val="visible")

    def animate(attribute: str, start: str, end: str, *, additive: bool) -> None:
        anim = _element("anim", children, calcmode="lin", valueType="num")
        _behavior(anim, spid, "500", attribute, additive=additive)
        frames = _element("tavLst", anim)
        for time, value in (("0", start), ("100000", end)):
            kind = "fltVal" if value == "0" else "strVal"
            _element(kind, _element("val", _element("tav", frames, tm=time)), val=value)

    def filtered(name: str) -> None:
        animation = _element("animEffect", children, transition="in", filter=name)
        _behavior(animation, spid, "500", hold=False)

    if effect == "fade":
        filtered("fade")
    elif effect == "wipe":
        filtered("wipe(down)")
    elif effect == "fly_in":
        animate("ppt_x", "#ppt_x", "#ppt_x", additive=True)
        animate("ppt_y", "1+#ppt_h/2", "#ppt_y", additive=True)
    elif effect == "zoom":
        animate("ppt_w", "0", "#ppt_w", additive=False)
        animate("ppt_h", "0", "#ppt_h", additive=False)
    return par


def _canonical_exit(spid: str, effect: str) -> etree._Element:
    """An exit effect as PowerPoint writes it: the animation, then hide the object."""
    preset, subtype, _kind = EFFECTS[effect]
    par = _element("par")
    node = _element(
        "cTn",
        par,
        id="0",
        presetID=preset,
        presetClass="exit",
        presetSubtype=subtype,
        fill="hold",
        grpId="0",
        nodeType="clickEffect",
    )
    _element("cond", _element("stCondLst", node), delay="0")
    children = _element("childTnLst", node)

    def animate(attribute: str, start: str, end: str, *, additive: bool) -> None:
        anim = _element("anim", children, calcmode="lin", valueType="num")
        _behavior(anim, spid, "500", attribute, hold=False, additive=additive)
        frames = _element("tavLst", anim)
        for time, value in (("0", start), ("100000", end)):
            _element("strVal", _element("val", _element("tav", frames, tm=time)), val=value)

    if effect in {"fade_out", "wipe_out"}:
        animation = _element(
            "animEffect",
            children,
            transition="out",
            filter="fade" if effect == "fade_out" else "wipe(down)",
        )
        _behavior(animation, spid, "500", hold=False)
    elif effect == "fly_out":
        animate("ppt_x", "ppt_x", "ppt_x", additive=True)
        animate("ppt_y", "ppt_y", "1+ppt_h/2", additive=True)
    elif effect == "zoom_out":
        animate("ppt_w", "ppt_w", "4*ppt_w", additive=False)
        animate("ppt_h", "ppt_h", "4*ppt_h", additive=False)
    hidden = _element("set", children)
    behavior = _element("cBhvr", hidden)
    timing = _element("cTn", behavior, id="0", dur="1", fill="hold")
    # Disappear hides at once; the others hide as their 500 ms animation ends.
    _element(
        "cond",
        _element("stCondLst", timing),
        delay="0" if effect == "disappear" else "499",
    )
    _element("spTgt", _element("tgtEl", behavior), spid=spid)
    _element("attrName", _element("attrNameLst", behavior)).text = "style.visibility"
    _element("strVal", _element("to", hidden), val="hidden")
    return par


def _int(value: str | None) -> int:
    return int(value) if value is not None and value.isdigit() else 0


def _length(effect: etree._Element) -> int:
    """When an effect finishes, relative to its group's start (ms)."""
    node = _time_node(effect)
    own = _int(next((c.get("delay") for c in _delays(node)), None))
    end = 0
    for inner in node.iter(f"{P}cTn"):
        if inner is not node:
            delay = _int(next((c.get("delay") for c in _delays(inner)), None))
            end = max(end, delay + _int(inner.get("dur")))
    return own + end


def _timing(
    plan: list[tuple[str, str, etree._Element]], targets: dict[str, bool], old: Any
) -> etree._Element:
    timing = _element("timing")
    root_node = _element(
        "cTn",
        _element("par", _element("tnLst", timing)),
        id="0",
        dur="indefinite",
        restart="never",
        nodeType="tmRoot",
    )
    sequence = _element("seq", _element("childTnLst", root_node), concurrent="1", nextAc="seek")
    main = _element("cTn", sequence, id="0", dur="indefinite", nodeType="mainSeq")
    clicks = _element("childTnLst", main)
    for kind, event in (("prevCondLst", "onPrev"), ("nextCondLst", "onNext")):
        condition = _element("cond", _element(kind, sequence), evt=event, delay="0")
        _element("sldTgt", _element("tgtEl", condition))
    group_effects: etree._Element | None = None
    click_effects: etree._Element | None = None
    groups: dict[str, dict[int, int]] = {}
    offset = end = 0
    for index, (_spid, start, effect) in enumerate(plan):
        if click_effects is None or start == "on_click":
            click = _element("cTn", _element("par", clicks), id="0", fill="hold")
            conditions = _element("stCondLst", click)
            _element("cond", conditions, delay="indefinite")
            if index == 0 and start != "on_click":
                begin = _element("cond", conditions, evt="onBegin", delay="0")
                _element("tn", begin, val="2")
            click_effects = _element("childTnLst", click)
            group_effects = None
            offset = end = 0
        if group_effects is None or start != "with_previous":
            offset = end if group_effects is not None else 0
            group = _element("cTn", _element("par", click_effects), id="0", fill="hold")
            _element("cond", _element("stCondLst", group), delay=str(offset))
            group_effects = _element("childTnLst", group)
        node = _time_node(effect)
        node.set("nodeType", STARTS[start])
        # PowerPoint numbers each object's build groups in sequence order.
        node.set("grpId", str(groups.setdefault(_spid, {}).setdefault(index, len(groups[_spid]))))
        group_effects.append(effect)
        end = max(end, offset + _length(effect))
    builds = _element("bldLst", timing)
    old_builds = (
        {}
        if old is None
        else {(b.get("spid"), b.get("grpId", "0")): b for b in old.iter(f"{P}bldP")}
    )
    for spid, numbers in groups.items():
        if not targets.get(spid):
            continue
        for number in sorted(numbers.values()):
            kept = old_builds.get((spid, str(number)))
            if kept is None:
                kept = old_builds.get((spid, "0"))
            build = (
                copy.deepcopy(kept)
                if kept is not None
                else _element("bldP", spid=spid, grpId="0", animBg="1")
            )
            build.set("grpId", str(number))
            builds.append(build)
    if not len(builds):
        timing.remove(builds)
    for number, node in enumerate(timing.iter(f"{P}cTn"), start=1):
        node.set("id", str(number))
    return timing


def _load(editor: PresentationEditService, params: dict[str, Any]) -> tuple[Any, ...]:
    project = editor._project_id(params.get("project_id"))
    document = editor._document_id(params.get("document_id"))
    revision = editor._uuid_field(params.get("expected_revision_id"), "expected_revision_id")
    slide_id = editor._uuid_field(params.get("slide_id"), "slide_id")
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
    if slide is None:
        raise CoreDomainError(
            "PRESENTATION_EDIT_TARGET_NOT_FOUND", "The selected slide is unavailable."
        )
    return project, document, revision, source, path, fidelity, slide


def _slide_root(editor: Any, path: Path, source: dict[str, Any], part: str) -> etree._Element:
    from presenter_core.presentation.editing import _verified_source_archive

    with _verified_source_archive(
        path, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
    ) as archive:
        return _parse_xml_part(archive, archive.getinfo(part))


def get_slide_animations(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    reject_unknown_fields(params, {"project_id", "document_id", "expected_revision_id", "slide_id"})
    _project, _document, revision, source, path, _fidelity, slide = _load(editor, params)
    root = _slide_root(editor, path, source, slide.part_name)
    objects = {obj.ooxml_id: obj for obj in slide.objects}
    return {"revision_id": revision, "slide_id": slide.slide_id, **_state(root, objects)}


def _requested(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > MAX_EFFECTS:
        raise invalid_request(
            f"effects must be a list of at most {MAX_EFFECTS} entries.", field="effects"
        )
    result = []
    for entry in value:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"object_id", "effect", "start"}
            or not isinstance(entry["object_id"], str)
            or entry["effect"] not in CLASSES
            or entry["start"] not in STARTS
        ):
            raise invalid_request(
                "Each effect needs object_id, effect ("
                + ", ".join(CLASSES)
                + ") and start (on_click, with_previous, after_previous).",
                field="effects",
            )
        result.append(dict(entry))
    if len({(entry["object_id"], CLASSES[entry["effect"]]) for entry in result}) != len(result):
        raise invalid_request(
            "Each object can have one entrance and one exit effect.", field="effects"
        )
    return result


def _comparable(obj: Any) -> Any:
    # Animation targets are not deletable or groupable; everything else must stay equal.
    return dataclasses.replace(obj, delete_editable=False, group_editable=False, group_reason=None)


def set_slide_animations(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    from presenter_core.presentation.editing import _verified_source_archive

    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "slide_id",
            "expected_fingerprint",
            "effects",
        },
    )
    requested = _requested(params.get("effects"))
    project, document, revision, source, path, fidelity, slide = _load(editor, params)
    root = _slide_root(editor, path, source, slide.part_name)
    objects = {obj.ooxml_id: obj for obj in slide.objects}
    before = _state(root, objects)
    if before["fingerprint"] != params.get("expected_fingerprint"):
        raise CoreDomainError(
            "PRESENTATION_EDIT_STALE_TARGET",
            "The slide animations changed. Refresh and try again.",
            retryable=True,
        )
    if not before["editable"]:
        raise CoreDomainError("PRESENTATION_EDIT_UNSUPPORTED", before["reason"])
    by_object = {obj.object_id: obj.ooxml_id for obj in slide.objects}
    targets = _targets(root)
    current = {(item["ooxml_id"], item["class"]): item for item in _parse(root)}
    for entry in requested:
        spid = by_object.get(entry["object_id"])
        if spid not in targets:
            raise CoreDomainError(
                "PRESENTATION_EDIT_TARGET_NOT_FOUND",
                "An animated object is unavailable or nested inside a group.",
            )
        kind = CLASSES[entry["effect"]]
        if entry["effect"] == CUSTOM[kind] and (
            current.get((spid, kind), {}).get("effect") != CUSTOM[kind]
        ):
            raise invalid_request(
                "Only an object that already has a custom effect can keep it.",
                field="effects",
            )
    wanted = [
        {"object_id": entry["object_id"], "effect": entry["effect"], "start": entry["start"]}
        for entry in requested
    ]
    if wanted == [
        {key: item[key] for key in ("object_id", "effect", "start")} for item in before["effects"]
    ]:
        return {
            "changed": False,
            "revision_id": source["revision_id"],
            "revision_number": int(source["revision_number"]),
            "sha256": source["sha256"],
            "byte_size": int(source["byte_size"]),
        }

    def write(original: Path, target: Path) -> bool:
        with _verified_source_archive(
            original, expected_sha256=source["sha256"], expected_byte_size=source["byte_size"]
        ) as archive:
            slide_root = _parse_xml_part(archive, archive.getinfo(slide.part_name))
            if _fingerprint(slide_root) != before["fingerprint"]:
                raise CoreDomainError(
                    "PRESENTATION_EDIT_STALE_TARGET",
                    "The slide animations changed. Refresh and try again.",
                    retryable=True,
                )
            existing = {(item["ooxml_id"], item["class"]): item for item in _parse(slide_root)}
            plan = []
            for entry in requested:
                spid = by_object[entry["object_id"]]
                kept = existing.get((spid, CLASSES[entry["effect"]]))
                effect = (
                    copy.deepcopy(kept["element"])
                    if kept is not None and kept["effect"] == entry["effect"]
                    else _canonical(spid, entry["effect"])
                )
                plan.append((spid, entry["start"], effect))
            old = slide_root.find(f"{P}timing")
            if plan:
                timing = _timing(plan, _targets(slide_root), old)
                if old is not None:
                    old.addprevious(timing)
                else:
                    anchor = slide_root.find(f"{P}extLst")
                    if anchor is None:
                        slide_root.append(timing)
                    else:
                        anchor.addprevious(timing)
            if old is not None:
                slide_root.remove(old)
            rewritten = etree.tostring(
                slide_root, encoding="UTF-8", xml_declaration=True, standalone=True
            )
            with zipfile.ZipFile(target, "w", allowZip64=True) as output:
                output.comment = archive.comment
                for info in archive.infolist():
                    if info.filename == slide.part_name:
                        output.writestr(copy.copy(info), rewritten)
                    else:
                        with (
                            archive.open(info) as reader,
                            output.open(copy.copy(info), "w") as writer,
                        ):
                            shutil.copyfileobj(reader, writer, length=1024 * 1024)
        with target.open("rb") as handle:
            updated = inspect_pptx_snapshot(
                handle,
                document_id=document,
                expected_sha256=editor._sha256_path(target),
                byte_size=target.stat().st_size,
            )
        revised = next((item for item in updated.slides if item.slide_id == slide.slide_id), None)
        with zipfile.ZipFile(target) as archive:
            after = (
                _state(
                    _parse_xml_part(archive, archive.getinfo(revised.part_name)),
                    {obj.ooxml_id: obj for obj in revised.objects},
                )
                if revised is not None
                else None
            )
        if (
            after is None
            or not after["editable"]
            or [{k: e[k] for k in ("object_id", "effect", "start")} for e in after["effects"]]
            != wanted
            or {o.object_id: _comparable(o) for page in updated.slides for o in page.objects}
            != {o.object_id: _comparable(o) for page in fidelity.slides for o in page.objects}
        ):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "The slide animation edit did not pass validation.",
            )
        return True

    result = editor._commit_revision(project, document, revision, source, write)
    return {**result, "slide_id": slide.slide_id, "effects": wanted}
