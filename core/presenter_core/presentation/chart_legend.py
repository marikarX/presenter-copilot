"""Explicit legend edits isolate the selected chart and preserve workbook bytes."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from lxml import etree  # type: ignore[import-untyped]

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.presentation.charts import CNS, NS

if TYPE_CHECKING:
    from presenter_core.presentation.editing import PresentationEditService

POSITIONS = {"left": "l", "right": "r", "top": "t", "bottom": "b", "top_right": "tr"}


def inspect_legend(chart: Any) -> dict[str, Any]:
    legends = chart.findall("c:chart/c:legend", NS)
    if not legends:
        return {"editable": True, "reason": None, "position": "hidden", "overlay": False}
    unsupported = {
        "editable": False,
        "reason": "Legends with manual layouts, extensions or unsupported settings stay read-only.",
        "position": None,
        "overlay": None,
    }
    if len(legends) != 1:
        return unsupported
    legend = legends[0]
    allowed = {"legendPos", "legendEntry", "layout", "overlay", "spPr", "txPr"}
    if legend.attrib or any(
        child.tag not in {f"{{{CNS}}}{tag}" for tag in allowed} for child in legend
    ):
        return unsupported
    if any(len(legend.findall("c:" + tag, NS)) > 1 for tag in allowed - {"legendEntry"}):
        return unsupported
    layout = legend.find("c:layout", NS)
    if layout is not None and (layout.attrib or len(layout)):
        return unsupported
    position = legend.find("c:legendPos", NS)
    overlay = legend.find("c:overlay", NS)
    code = position.get("val") if position is not None else "r"
    value = overlay.get("val") if overlay is not None else "0"
    if (
        code not in POSITIONS.values()
        or value not in {"0", "1", "false", "true"}
        or any(
            node is not None and (set(node.attrib) != {"val"} or len(node))
            for node in [position, overlay]
        )
    ):
        return unsupported
    return {
        "editable": True,
        "reason": None,
        "position": next(key for key, val in POSITIONS.items() if val == code),
        "overlay": value in {"1", "true"},
    }


def apply_legend(chart: Any, position: str, overlay: bool) -> bool:
    state = inspect_legend(chart)
    if not state["editable"]:
        raise CoreDomainError("PRESENTATION_EDIT_UNSUPPORTED", state["reason"])
    desired = {"position": position, "overlay": False if position == "hidden" else overlay}
    if all(state[key] == value for key, value in desired.items()):
        return False
    parent = chart.find("c:chart", NS)
    legend = parent.find("c:legend", NS)
    if position == "hidden":
        if legend is not None:
            parent.remove(legend)
        return True
    if legend is None:
        legend = etree.Element(f"{{{CNS}}}legend")
        # The legend follows plotArea and precedes plotVisOnly/blank-display settings.
        plot = parent.find("c:plotArea", NS)
        parent.insert(parent.index(plot) + 1, legend)
    pos = legend.find("c:legendPos", NS)
    if pos is None:
        pos = etree.Element(f"{{{CNS}}}legendPos")
        legend.insert(0, pos)
    pos.set("val", POSITIONS[position])
    node = legend.find("c:overlay", NS)
    if node is None:
        node = etree.Element(f"{{{CNS}}}overlay")
        index = next(
            (i for i, v in enumerate(legend) if v.tag in {f"{{{CNS}}}spPr", f"{{{CNS}}}txPr"}),
            len(legend),
        )
        legend.insert(index, node)
    node.set("val", "1" if overlay else "0")
    return True


def set_chart_legend(editor: PresentationEditService, params: dict[str, Any]) -> dict[str, Any]:
    reject_unknown_fields(
        params,
        {
            "project_id",
            "document_id",
            "expected_revision_id",
            "slide_id",
            "object_id",
            "expected_fingerprint",
            "legend_position",
            "legend_overlay",
        },
    )
    position = params.get("legend_position")
    overlay = params.get("legend_overlay")
    if (
        not isinstance(position, str)
        or position not in {*POSITIONS, "hidden"}
        or type(overlay) is not bool
        or (position == "hidden" and overlay)
    ):
        raise invalid_request("Choose a legend placement and overlay setting.")

    def mutate(chart: Any) -> bool:
        unchanged = copy.deepcopy(chart)
        if not apply_legend(chart, position, overlay):
            return False
        compared = copy.deepcopy(chart)
        for tree in [compared, unchanged]:
            for node in tree.findall("c:chart/c:legend", NS):
                node.getparent().remove(node)
        if etree.tostring(compared, method="c14n") != etree.tostring(unchanged, method="c14n"):
            raise CoreDomainError(
                "PRESENTATION_EDIT_VALIDATION_FAILED",
                "Legend editing changed other chart settings.",
            )
        return True

    from presenter_core.presentation.chart_appearance import edit_chart_appearance

    return edit_chart_appearance(editor, params, mutate)
