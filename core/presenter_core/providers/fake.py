"""Deterministic test-only provider with bounded payload capture."""

from __future__ import annotations

import json
from time import monotonic
from typing import Any, cast

from .models import (
    CHALLENGE_INTENSITIES,
    ProviderCapabilities,
    ProviderError,
    ProviderHealth,
    ProviderInvocation,
    ReasoningProvider,
    ReasoningRequest,
    ReasoningResult,
    validate_provider_output,
)


class DeterministicFakeReasoningProvider(ReasoningProvider):
    """Offline provider used by CI and explicit developer acceptance flows."""

    id = "fake-test"

    def __init__(
        self,
        *,
        locality: str = "remote",
        failure_code: str | None = None,
        model_id: str = "fake-teach-v1",
    ) -> None:
        self.locality = locality
        self.model_id = model_id
        self.failure_code = failure_code
        self.requests: list[dict[str, Any]] = []
        self.request_objects: list[ReasoningRequest] = []
        self.call_count = 0

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            structured_outputs=True,
            streaming=False,
            cancellation=False,
            task_types=(
                "teach_question",
                "teach_candidate",
                "challenge_question",
                "challenge_follow_up",
                "challenge_evaluation",
                "live_cue",
                "presentation_text_rewrite",
                "presentation_outline",
                "presentation_narrative_review",
                "presentation_claim_extraction",
                "presentation_rehearsal_coverage",
                "presentation_rehearsal_objections",
                "presentation_rehearsal_objection_equivalence",
                "presentation_edit_plan",
            ),
        )

    def health(self) -> ProviderHealth:
        if self.failure_code == "PROVIDER_UNCONFIGURED":
            return ProviderHealth(
                provider_id=self.id,
                locality=self.locality,
                model_id=self.model_id,
                status="unconfigured",
                configured=False,
                error_code=self.failure_code,
            )
        return ProviderHealth(
            provider_id=self.id,
            locality=self.locality,
            model_id=self.model_id,
            status="ready",
            configured=True,
        )

    def generate(self, invocation: ProviderInvocation) -> ReasoningResult:
        request = invocation.request
        self.call_count += 1
        self.requests.append(invocation.to_payload())
        self.request_objects.append(request)
        if self.failure_code is not None:
            raise ProviderError(
                self.failure_code,
                "The deterministic reasoning provider was configured to fail.",
                retryable=self.failure_code
                in {"PROVIDER_TIMEOUT", "PROVIDER_RATE_LIMITED", "PROVIDER_UNAVAILABLE"},
            )
        started = monotonic()
        if request.task_type == "teach_question":
            evidence = request.evidence[0] if request.evidence else None
            if isinstance(evidence, dict) and isinstance(evidence.get("label"), str):
                question = (
                    f"What made the option described in {evidence['label']} a poor fit "
                    "for this project?"
                )
            else:
                question = "What decision or tradeoff behind this project should I remember?"
            output = validate_provider_output(
                request.task_type,
                {"question": question, "focus": "decision_rationale"},
            )
        elif request.task_type == "live_cue":
            grounding = (
                request.grounding_evidence
                or request.evidence
                or request.preferred_user_explanations
            )
            evidence = grounding[0] if grounding else None
            if isinstance(evidence, dict):
                label = str(evidence.get("label") or "Project source")
                excerpt = " ".join(str(evidence.get("text") or "").split())
                line = f"{label}: {excerpt}"[:180].rstrip()
                evidence_ids = [
                    str(item["evidence_id"])
                    for item in grounding[:2]
                    if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
                ]
            else:
                line = "Use the prepared project context to answer directly."
                evidence_ids = []
            output = validate_provider_output(
                request.task_type,
                {"cue_type": "fact", "lines": [line], "evidence_ids": evidence_ids},
            )
        elif request.task_type == "teach_candidate":
            answer = (request.user_input or "").strip()
            if not answer:
                raise ProviderError(
                    "PROVIDER_MALFORMED_OUTPUT",
                    "The deterministic provider needs a user explanation.",
                )
            lowered = answer.casefold()
            if "reject" in lowered or "rollback" in lowered or "cutover" in lowered:
                candidate_text = (
                    "We rejected it because it doubled the cutover surface and made rollback "
                    "harder."
                    if "doubled the cutover surface" in lowered
                    else answer
                )
            else:
                candidate_text = answer
            output = validate_provider_output(
                request.task_type,
                {
                    "kind": "rationale",
                    "text": candidate_text,
                    "follow_up_question": None,
                },
            )
        elif request.task_type in {"challenge_question", "challenge_follow_up"}:
            output = self._challenge_question(request)
        elif request.task_type == "challenge_evaluation":
            output = self._challenge_evaluation(request)
        elif request.task_type == "presentation_text_rewrite":
            try:
                selected = json.loads(request.current_slide_summary or "{}")
                selected_text = selected["selected_text"]
            except (json.JSONDecodeError, KeyError, TypeError) as error:
                raise ProviderError(
                    "PROVIDER_MALFORMED_OUTPUT",
                    "The deterministic provider needs selected presentation text.",
                ) from error
            if not isinstance(selected_text, str) or not selected_text:
                raise ProviderError(
                    "PROVIDER_MALFORMED_OUTPUT",
                    "The deterministic provider needs selected presentation text.",
                )
            output = validate_provider_output(
                request.task_type,
                {
                    "replacement_text": selected_text,
                    "edit_summary": "Review the selected text before applying this proposal.",
                },
            )
        elif request.task_type == "presentation_edit_plan":
            snapshot = json.loads(request.current_slide_summary or "{}")[
                "presentation_edit_snapshot"
            ]
            slide = snapshot["slides"][0]
            obj = next(
                item
                for item in slide["objects"]
                if item["single_run_text_edit_candidate"] or item["uniform_run_text_edit_candidate"]
            )
            output = validate_provider_output(
                request.task_type,
                {
                    "summary": "Review a coordinated title and speaker-notes proposal.",
                    "operations": [
                        {
                            "type": "replace_text_shape",
                            "params": {
                                "slide_id": slide["slide_id"],
                                "object_id": obj["object_id"],
                                "replacement_text": obj["text"][:1988] + " — reviewed",
                            },
                            "rationale": "Make the reviewed wording explicit.",
                            "evidence_ids": [],
                        },
                        {
                            "type": "replace_speaker_notes",
                            "params": {
                                "slide_id": slide["slide_id"],
                                "replacement_text": (slide["speaker_notes"] or "")[:11940]
                                + "\nReview the decision with the audience.",
                            },
                            "rationale": "Keep the speaking reminder with the slide.",
                            "evidence_ids": [],
                        },
                    ],
                },
            )
            for additional in snapshot["slides"][1:19]:
                if additional["speaker_notes_editable"] and additional["speaker_notes"] is not None:
                    output["operations"].append(
                        {
                            "type": "replace_speaker_notes",
                            "params": {
                                "slide_id": additional["slide_id"],
                                "replacement_text": additional["speaker_notes"][:11940]
                                + "\nReview the decision with the audience.",
                            },
                            "rationale": "Keep the speaking reminder with the selected slide.",
                            "evidence_ids": [],
                        }
                    )
            output = validate_provider_output(request.task_type, output)
            if (
                request.question == "Insert the attached picture at the lower right."
                and snapshot.get("assets")
            ):
                asset = snapshot["assets"][0]
                width = min(1371600, snapshot["slide_width_emu"] // 3)
                height = min(
                    snapshot["slide_height_emu"] // 3,
                    max(1, round(width * asset["height"] / asset["width"])),
                )
                output = validate_provider_output(
                    request.task_type,
                    {
                        "summary": "Insert the explicitly attached deck image.",
                        "operations": [
                            {
                                "type": "create_picture",
                                "params": {
                                    "slide_id": slide["slide_id"],
                                    "asset_id": asset["asset_id"],
                                    "geometry": {
                                        "x_emu": snapshot["slide_width_emu"] - width - 100000,
                                        "y_emu": snapshot["slide_height_emu"] - height - 100000,
                                        "width_emu": width,
                                        "height_emu": height,
                                    },
                                    "alt_text": "Attached visual",
                                },
                                "rationale": "Reuse the requested image at the lower right.",
                                "evidence_ids": [],
                            }
                        ],
                    },
                )
            if request.question == "Add a styled callout using a coordinated creation plan.":
                from .edit_plan_schema import PARAMETER_SCHEMAS

                style = dict.fromkeys(
                    PARAMETER_SCHEMAS["format_text_shape"]["properties"]["replacement_style"][
                        "properties"
                    ]
                )
                style.update(bold=True, font_size_pt=28, font_color="#7064AA")
                output = validate_provider_output(
                    request.task_type,
                    {
                        "summary": "Create, style and position a callout in one reviewed revision.",
                        "operations": [
                            {
                                "type": kind,
                                "params": values,
                                "rationale": rationale,
                                "evidence_ids": [],
                            }
                            for kind, values, rationale in [
                                (
                                    "create_text_box",
                                    {
                                        "slide_id": slide["slide_id"],
                                        "text": "Approve the measured pilot",
                                    },
                                    "Add the requested callout.",
                                ),
                                (
                                    "format_text_shape",
                                    {
                                        "slide_id": slide["slide_id"],
                                        "object_id": {"created_by": 1},
                                        "replacement_style": style,
                                    },
                                    "Emphasize the new callout.",
                                ),
                                (
                                    "transform_object",
                                    {
                                        "slide_id": slide["slide_id"],
                                        "object_id": {"created_by": 1},
                                        "replacement_geometry": {
                                            "x_emu": 500000,
                                            "y_emu": 500000,
                                            "width_emu": 4000000,
                                            "height_emu": 750000,
                                        },
                                    },
                                    "Place it near the slide's top edge.",
                                ),
                            ]
                        ],
                    },
                )
            if request.question in {"Group two new pilot callouts.", "Ungroup the pilot callouts."}:
                if request.question.startswith("Group"):
                    entries = [
                        ("create_text_box", {"slide_id": slide["slide_id"], "text": "Pilot owner"}),
                        (
                            "transform_object",
                            {
                                "slide_id": slide["slide_id"],
                                "object_id": {"created_by": 1},
                                "replacement_geometry": {
                                    "x_emu": 1000000,
                                    "y_emu": 4400000,
                                    "width_emu": 2400000,
                                    "height_emu": 500000,
                                },
                            },
                        ),
                        ("create_text_box", {"slide_id": slide["slide_id"], "text": "Review date"}),
                        (
                            "transform_object",
                            {
                                "slide_id": slide["slide_id"],
                                "object_id": {"created_by": 3},
                                "replacement_geometry": {
                                    "x_emu": 4000000,
                                    "y_emu": 4400000,
                                    "width_emu": 2400000,
                                    "height_emu": 500000,
                                },
                            },
                        ),
                        (
                            "group_objects",
                            {
                                "slide_id": slide["slide_id"],
                                "objects": [
                                    {"object_id": {"created_by": 1}},
                                    {"object_id": {"created_by": 3}},
                                ],
                            },
                        ),
                    ]
                else:
                    group = next(
                        item
                        for item in reversed(slide["objects"])
                        if item["kind"] == "grpSp" and item["group_editable"]
                    )
                    entries = [
                        (
                            "ungroup_object",
                            {"slide_id": slide["slide_id"], "object_id": group["object_id"]},
                        )
                    ]
                output = validate_provider_output(
                    request.task_type,
                    {
                        "summary": "Review pilot callout grouping.",
                        "operations": [
                            {
                                "type": kind,
                                "params": values,
                                "rationale": "Preserve child content and placement.",
                                "evidence_ids": [],
                            }
                            for kind, values in entries
                        ],
                    },
                )
            if request.question in {
                "Add a three-step pilot diagram on a new slide.",
                "Convert the pilot diagram into a cycle.",
                "Remove the pilot diagram.",
            }:
                if request.question.startswith("Add"):
                    data = {
                        "name": "Pilot workflow",
                        "kind": "process",
                        "palette": "classic",
                        "nodes": [
                            {"id": f"step{i + 1}", "label": label, "parent": None}
                            for i, label in enumerate(["Prepare", "Run pilot", "Review outcomes"])
                        ],
                    }
                    entries = [
                        (
                            "create_authored_slide",
                            {
                                "slide_id": slide["slide_id"],
                                "layout_source_slide_id": slide["slide_id"],
                                "title": "Pilot workflow",
                                "bullets": [],
                                "notes": "Review the pilot workflow before the decision.",
                                "template": "classic",
                                "layout": "statement",
                            },
                        ),
                        (
                            "create_diagram",
                            {
                                "slide_id": {"created_by": 1},
                                "data": data,
                                "geometry": {
                                    "x_emu": snapshot["slide_width_emu"] // 10,
                                    "y_emu": snapshot["slide_height_emu"] * 3 // 10,
                                    "width_emu": snapshot["slide_width_emu"] * 8 // 10,
                                    "height_emu": snapshot["slide_height_emu"] * 6 // 10,
                                },
                            },
                        ),
                    ]
                else:
                    diagram = next(item for item in slide["diagrams"] if item["editable"])
                    values = {"slide_id": slide["slide_id"], "object_id": diagram["object_id"]}
                    if request.question.startswith("Convert"):
                        values.update(
                            data={**diagram["data"], "kind": "cycle"}, geometry=diagram["geometry"]
                        )
                    entries = [
                        (
                            "replace_diagram"
                            if request.question.startswith("Convert")
                            else "delete_diagram",
                            values,
                        )
                    ]
                output = validate_provider_output(
                    request.task_type,
                    {
                        "summary": "Review the requested pilot diagram changes.",
                        "operations": [
                            {
                                "type": kind,
                                "params": values,
                                "rationale": "Review native diagram changes.",
                                "evidence_ids": [],
                            }
                            for kind, values in entries
                        ],
                    },
                )
            if snapshot.get("previous_proposal") and request.question == (
                "Keep the title change and make the notes more specific."
            ):
                output = json.loads(json.dumps(snapshot["previous_proposal"]["proposal"]))
                note = next(
                    op for op in output["operations"] if op["type"] == "replace_speaker_notes"
                )
                note["params"]["replacement_text"] = "Name the pilot owner and review the outcome."
                output["summary"] = "Review the refined title and specific pilot notes."
                output = validate_provider_output(request.task_type, output)
            if snapshot.get("previous_proposal") and request.question == (
                "Try a malformed refinement."
            ):
                output["operations"][0]["evidence_ids"] = ["not-supplied-to-refinement"]
            if request.question in {
                "Add a pilot metrics slide with a table and chart.",
                "Update the pilot metrics values.",
                "Expand the pilot table and chart with targets.",
            }:
                data = {
                    "title": "Pilot revenue",
                    "chart_type": "column",
                    "categories": ["Current", "Pilot"],
                    "series": [{"name": "Revenue", "values": [10, 12.25]}],
                }
                cells = [["Metric", "Value"], ["Revenue", "12.25"]]
                if request.question.startswith("Add"):
                    geometry = {
                        "x_emu": 500000,
                        "y_emu": 2200000,
                        "width_emu": 5000000,
                        "height_emu": 3600000,
                    }
                    entries = [
                        (
                            "create_authored_slide",
                            {
                                "slide_id": slide["slide_id"],
                                "layout_source_slide_id": slide["slide_id"],
                                "title": "Pilot metrics",
                                "bullets": [],
                                "notes": "Review metrics and evidence.",
                                "template": "classic",
                                "layout": "statement",
                            },
                        ),
                        (
                            "create_table",
                            {
                                "slide_id": {"created_by": 1},
                                "geometry": geometry,
                                "header_row": True,
                                "cells": cells,
                            },
                        ),
                        (
                            "create_chart",
                            {
                                "slide_id": {"created_by": 1},
                                "geometry": {**geometry, "x_emu": 6300000},
                                **data,
                            },
                        ),
                    ]
                else:
                    table = next(v for v in slide["tables"] if v["editable"])
                    chart = next(v for v in slide["charts"] if v["editable"])
                    data = json.loads(json.dumps(chart["data"]))
                    cells = json.loads(json.dumps(table["cells"]))
                    if request.question.startswith("Update"):
                        cells[1][1] = "12.5"
                        data["series"][0]["values"][1] = 12.5
                        entries = [
                            (
                                "replace_table_cells",
                                {
                                    "slide_id": slide["slide_id"],
                                    "object_id": table["object_id"],
                                    "cells": cells,
                                },
                            ),
                            (
                                "replace_chart_data",
                                {
                                    "slide_id": slide["slide_id"],
                                    "object_id": chart["object_id"],
                                    **data,
                                },
                            ),
                        ]
                    else:
                        cells = [
                            ["Metric", "Value", "Owner"],
                            ["Revenue", "12.5", "Pilot team"],
                            ["Cost", "9", "Finance"],
                        ]
                        data["categories"].append("Target")
                        data["series"][0]["values"].append(15)
                        data["series"].append({"name": "Cost", "values": [8, 9, 10]})
                        entries = [
                            (
                                "reshape_table",
                                {
                                    "slide_id": slide["slide_id"],
                                    "object_id": table["object_id"],
                                    "cells": cells,
                                    "row_sources": [0, 1, None],
                                    "column_sources": [0, 1, None],
                                },
                            ),
                            (
                                "reshape_chart",
                                {
                                    "slide_id": slide["slide_id"],
                                    "object_id": chart["object_id"],
                                    **data,
                                    "category_sources": [0, 1, None],
                                    "series_sources": [0, None],
                                },
                            ),
                        ]
                output = validate_provider_output(
                    request.task_type,
                    {
                        "summary": "Review native pilot metrics.",
                        "operations": [
                            {
                                "type": kind,
                                "params": values,
                                "rationale": "Review the synthetic pilot data and placement.",
                                "evidence_ids": [],
                            }
                            for kind, values in entries
                        ],
                    },
                )
            if request.question == "Style the pilot table header.":
                target = next(
                    item
                    for item in slide["tables"]
                    if item["editable"] and item["formatting"]["editable"]
                )
                output = validate_provider_output(
                    request.task_type,
                    {
                        "summary": "Review pilot table header and numeric alignment.",
                        "operations": [
                            {
                                "type": "format_table_cells",
                                "params": {
                                    "slide_id": slide["slide_id"],
                                    "object_id": target["object_id"],
                                    "row_start": a,
                                    "row_end": b,
                                    "column_start": c,
                                    "column_end": d,
                                    "style": {
                                        "bold": None,
                                        "italic": None,
                                        "underline": None,
                                        "font_size_pt": None,
                                        "font_color": None,
                                        "fill_color": None,
                                        "alignment": None,
                                        "vertical_alignment": None,
                                        **cast(dict[str, Any], style),
                                    },
                                },
                                "rationale": "Review exact cell styles and retained table text.",
                                "evidence_ids": [],
                            }
                            for a, b, c, d, style in [
                                (
                                    0,
                                    0,
                                    0,
                                    len(target["cells"][0]) - 1,
                                    {
                                        "bold": True,
                                        "font_color": "#FFFFFF",
                                        "fill_color": "#6A2EB5",
                                        "alignment": "center",
                                    },
                                ),
                                (1, len(target["cells"]) - 1, 1, 1, {"alignment": "right"}),
                            ]
                        ],
                    },
                )
            if request.question == "Merge then split the pilot table header.":
                target = next(item for item in slide["tables"] if item["editable"])
                output = validate_provider_output(
                    request.task_type,
                    {
                        "summary": "Review native header merge then split.",
                        "operations": [
                            {
                                "type": kind,
                                "params": {
                                    "slide_id": slide["slide_id"],
                                    "object_id": target["object_id"],
                                    "row_start": 0,
                                    "row_end": 0,
                                    "column_start": 0,
                                    "column_end": 1,
                                },
                                "rationale": "Review staged text distribution and merged cells.",
                                "evidence_ids": [],
                            }
                            for kind in ["merge_table_cells", "split_table_cells"]
                        ],
                    },
                )
            if request.question == "Fit the pilot text box.":
                output = validate_provider_output(
                    request.task_type,
                    {
                        "summary": "Review a constrained callout and fit its text.",
                        "operations": [
                            {
                                "type": kind,
                                "params": values,
                                "rationale": "Review fitted text and nearby content.",
                                "evidence_ids": [],
                            }
                            for kind, values in [
                                (
                                    "create_text_box",
                                    {
                                        "slide_id": slide["slide_id"],
                                        "text": (
                                            "A reviewed pilot needs careful measurement "
                                            "before a decision. "
                                        )
                                        * 4,
                                    },
                                ),
                                (
                                    "transform_object",
                                    {
                                        "slide_id": slide["slide_id"],
                                        "object_id": {"created_by": 1},
                                        "replacement_geometry": {
                                            "x_emu": 914400,
                                            "y_emu": 914400,
                                            "width_emu": 3657600,
                                            "height_emu": 457200,
                                        },
                                    },
                                ),
                                (
                                    "fit_text_shape",
                                    {
                                        "slide_id": slide["slide_id"],
                                        "object_id": {"created_by": 1},
                                        "strategy": "shrink",
                                        "minimum_size_pt": 6,
                                    },
                                ),
                                (
                                    "fit_text_shape",
                                    {
                                        "slide_id": slide["slide_id"],
                                        "object_id": {"created_by": 1},
                                        "strategy": "grow",
                                        "minimum_size_pt": 6,
                                    },
                                ),
                            ]
                        ],
                    },
                )
            if request.question == "Fit the pilot table rows.":
                target = next(
                    item for item in slide["tables"] if item["editable"] and item["fit"]["editable"]
                )
                output = validate_provider_output(
                    request.task_type,
                    {
                        "summary": "Review compact rows then retain their fitted minimums.",
                        "operations": [
                            {
                                "type": "fit_table_rows",
                                "params": {
                                    "slide_id": slide["slide_id"],
                                    "object_id": target["object_id"],
                                    "strategy": strategy,
                                },
                                "rationale": "Review measured row heights and nearby content.",
                                "evidence_ids": [],
                            }
                            for strategy in ["compact", "grow"]
                        ],
                    },
                )
            if request.question == "Style the pilot table borders.":
                target = next(
                    item
                    for item in slide["tables"]
                    if item["editable"] and item["borders"]["editable"]
                )
                output = validate_provider_output(
                    request.task_type,
                    {
                        "summary": "Review shared table border edges.",
                        "operations": [
                            {
                                "type": "set_table_borders",
                                "params": {
                                    "slide_id": slide["slide_id"],
                                    "object_id": target["object_id"],
                                    "row_start": 0,
                                    "row_end": len(target["cells"]) - 1,
                                    "column_start": 0,
                                    "column_end": len(target["cells"][0]) - 1,
                                    "border_scope": scope,
                                    "line_style": style,
                                    "width_pt": width,
                                    "color": color,
                                },
                                "rationale": "Review borders while preserving text and layout.",
                                "evidence_ids": [],
                            }
                            for scope, style, width, color in [
                                ("all", "solid", 3, "#A12266"),
                                ("inside", "none", None, None),
                            ]
                        ],
                    },
                )
            if request.question == "Set the pilot chart axes.":
                target = next(
                    item
                    for item in slide["charts"]
                    if item["editable"] and item["axes"]["editable"]
                )
                output = validate_provider_output(
                    request.task_type,
                    {
                        "summary": "Review native value and category axes.",
                        "operations": [
                            {
                                "type": "set_chart_axis",
                                "params": {
                                    "slide_id": slide["slide_id"],
                                    "object_id": target["object_id"],
                                    "axis_kind": "value",
                                    "visible": True,
                                    "tick_labels": "next_to",
                                    "major_gridlines": True,
                                    "minor_gridlines": False,
                                    "title": title,
                                    "number_format": fmt,
                                    "minimum": minimum,
                                    "maximum": maximum,
                                    "major_unit": major,
                                    "minor_unit": minor,
                                },
                                "rationale": "Review native axis range, units and labels.",
                                "evidence_ids": [],
                            }
                            for title, fmt, minimum, maximum, major, minor in [
                                ("Revenue ($)", "$0.0", 0, 30, 5, 1),
                                (None, None, None, None, None, None),
                            ]
                        ],
                    },
                )
            if request.question == "Label the pilot chart values.":
                target = next(
                    item
                    for item in slide["charts"]
                    if item["editable"] and item["labels"]["editable"]
                )
                output = validate_provider_output(
                    request.task_type,
                    {
                        "summary": "Review pilot chart value labels.",
                        "operations": [
                            {
                                "type": "set_chart_labels",
                                "params": {
                                    "slide_id": slide["slide_id"],
                                    "object_id": target["object_id"],
                                    "series_index": index,
                                    "position": position,
                                    "show_value": True,
                                    "show_category": False,
                                    "show_series": False,
                                    "show_percent": False,
                                    "number_format": fmt,
                                },
                                "rationale": "Review actual values, placement and label fit.",
                                "evidence_ids": [],
                            }
                            for index, position, fmt in [
                                (None, "outside_end", "0.0"),
                                (0, "inside_end", None),
                            ]
                        ],
                    },
                )
            if request.question == "Recolor the pilot chart.":
                target = next(
                    item
                    for item in slide["charts"]
                    if item["editable"] and item["colors"]["editable"]
                )
                output = validate_provider_output(
                    request.task_type,
                    {
                        "summary": "Review native pilot chart colors.",
                        "operations": [
                            {
                                "type": "set_chart_color",
                                "params": {
                                    "slide_id": slide["slide_id"],
                                    "object_id": target["object_id"],
                                    "series_index": series,
                                    "point_index": point,
                                    "color": color,
                                },
                                "rationale": "Review the series/point RGB and retained chart data.",
                                "evidence_ids": [],
                            }
                            for series, point, color in [(0, None, "#6A2EB5"), (1, 1, "#D63621")]
                        ],
                    },
                )
            if request.question == "Show a bottom legend for the pilot chart.":
                target = next(
                    item
                    for item in slide["charts"]
                    if item["editable"] and item["legend"]["editable"]
                )
                output = validate_provider_output(
                    request.task_type,
                    {
                        "summary": "Review a visible bottom legend for the pilot chart.",
                        "operations": [
                            {
                                "type": "set_chart_legend",
                                "params": {
                                    "slide_id": slide["slide_id"],
                                    "object_id": target["object_id"],
                                    "legend_position": "bottom",
                                    "legend_overlay": False,
                                },
                                "rationale": "Review the pilot series legend and plot fit.",
                                "evidence_ids": [],
                            }
                        ],
                    },
                )
        elif request.task_type == "presentation_rehearsal_objection_equivalence":
            selected = json.loads(request.current_slide_summary or "{}")
            output = validate_provider_output(
                request.task_type,
                {
                    "comparisons": [
                        {
                            "left_finding_id": left["finding_id"],
                            "right_finding_id": right["finding_id"],
                            "relationship": "unclear",
                            "reason": "Fixture provider: semantic equivalence requires review.",
                        }
                        for left in selected["left"]["candidates"]
                        for right in selected["right"]["candidates"]
                    ]
                },
            )
        elif request.task_type == "presentation_rehearsal_objections":
            output = validate_provider_output(request.task_type, {"observations": []})
        elif request.task_type == "presentation_rehearsal_coverage":
            output = validate_provider_output(
                request.task_type,
                {
                    "status": "unclear",
                    "reason": "Fixture provider: semantic coverage requires review.",
                    "quotes": [],
                },
            )
        elif request.task_type == "presentation_claim_extraction":
            objects = json.loads(request.current_slide_summary or "{}")["objects"]
            output = validate_provider_output(
                request.task_type,
                {
                    "summary": "Review these exact object quotes; evidence remains unverified.",
                    "candidates": [
                        {
                            "object_id": item["object_id"],
                            "quote": item["text"].splitlines()[0][:2000],
                            "kind": "interpretation",
                            "reason": "Review the assertion in this text object.",
                            "confidence": None,
                        }
                        for item in objects[:3]
                    ],
                },
            )
        elif request.task_type == "presentation_narrative_review":
            from presenter_core.presentation.narrative import FIELD_LIMITS

            snapshot = json.loads(request.current_slide_summary or "{}")[
                "presentation_narrative_snapshot"
            ]
            fields = {key: snapshot["draft_fields"][key][:500] for key in FIELD_LIMITS}
            fields["thesis"] = "Validate the decision through a reviewed, reversible pilot."
            output = validate_provider_output(
                request.task_type,
                {
                    "summary": "Review the narrative against the supplied slide text and notes.",
                    "fields": fields,
                    "findings": [
                        {
                            "slide_id": slide["slide_id"],
                            "role": "recommendation",
                            "takeaway": "Make the requested decision explicit.",
                            "issue": "The decision and its owner need review.",
                            "action": "Clarify the decision owner and the next checkpoint.",
                            "evidence_ids": [],
                        }
                        for slide in snapshot["slides"][:2]
                    ],
                },
            )
        elif request.task_type == "presentation_outline":
            brief = json.loads(request.user_input or "{}")
            count = brief.get("slide_count", 3)
            output = validate_provider_output(
                request.task_type,
                {
                    "title": brief.get("objective", "Presentation")[:120],
                    "rationale": "A review-only outline from your briefing.",
                    "slides": [
                        {
                            "title": f"Decision outline {index + 1}",
                            "bullets": ["Review the proposed decision", "Evidence needs review"],
                            "notes": "Confirm the supporting evidence before presenting.",
                            "evidence_ids": [],
                        }
                        for index in range(count)
                    ],
                },
            )
        else:
            raise ProviderError("PROVIDER_REQUEST_FAILED", "Unsupported fake provider task.")
        return ReasoningResult(
            output=output,
            input_token_count=None,
            output_token_count=None,
            latency_ms=max(0, int((monotonic() - started) * 1000)),
        )

    @staticmethod
    def _challenge_question(request: ReasoningRequest) -> dict[str, Any]:
        profile = request.audience_context[0] if request.audience_context else {}
        role = str(profile.get("role") or "audience member")
        role_lower = role.casefold()
        observation_text = " ".join(
            str(item.get("text", ""))
            for item in profile.get("observations", [])
            if isinstance(item, dict)
        ).casefold()
        is_finance = any(
            marker in f"{role_lower} {observation_text}"
            for marker in ("cfo", "finance", "cost", "budget", "status quo")
        )
        is_technical = any(
            marker in f"{role_lower} {observation_text}"
            for marker in ("cto", "technical", "rto", "availability", "rollback", "migration")
        )
        intensity = request.challenge_intensity
        if intensity not in CHALLENGE_INTENSITIES:
            intensity = "normal"
        if is_finance:
            stems = {
                "normal": "What is the cost and downside case for this proposal "
                "compared with keeping the current platform?",
                "skeptical": "What evidence supports the cost and downside case "
                "instead of extending the current platform?",
                "adversarial": "Why should we accept this cost and downside exposure "
                "instead of keeping the current platform?",
            }
        elif is_technical:
            stems = {
                "normal": "What is the migration rollback and recovery plan if "
                "availability is threatened?",
                "skeptical": "What evidence shows the migration can meet the recovery "
                "target and still roll back safely?",
                "adversarial": "What fails first in this migration, and how will you "
                "restore service within the recovery target?",
            }
        else:
            stems = {
                "normal": "What decision or trade-off should this audience understand "
                "about the proposal?",
                "skeptical": "Which assumption or trade-off in the proposal has the "
                "weakest supporting evidence?",
                "adversarial": "What is the strongest professional counterargument to "
                "this proposal?",
            }
        question = stems[intensity]
        prior_count = len(request.prior_question_context)
        if request.task_type == "challenge_follow_up":
            question = (
                "What specific evidence or next step would resolve the concern raised "
                "by your prior answer?"
            )
        elif prior_count:
            question = question.rstrip("?") + " Which part of that case remains least tested?"
        grounding = (
            request.grounding_evidence or request.evidence or request.preferred_user_explanations
        )
        evidence_ids = [
            str(item["evidence_id"])
            for item in grounding[:2]
            if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
        ]
        observation_ids = [
            str(item["id"])
            for item in profile.get("observations", [])[:2]
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        rationale = (
            f"This {intensity} question reflects the selected {role} audience context and "
            f"the supplied project evidence."
        )
        return validate_provider_output(
            request.task_type,
            {
                "question": question,
                "rationale": rationale,
                "evidence_ids": evidence_ids,
                "audience_observation_ids": observation_ids,
            },
            conflict_metadata=request.conflict_metadata,
        )

    @staticmethod
    def _challenge_evaluation(request: ReasoningRequest) -> dict[str, Any]:
        answer = (request.user_input or "").strip()
        answer_lower = answer.casefold()
        words = answer_lower.split()
        grounding = (
            request.grounding_evidence or request.evidence or request.preferred_user_explanations
        )
        grounding_text = " ".join(
            str(item.get("text", "")) for item in grounding if isinstance(item, dict)
        ).casefold()
        overlap = sum(1 for token in set(words) if len(token) >= 4 and token in grounding_text)
        correctness = min(1.0, 0.35 + (0.1 * min(overlap, 4)) + (0.1 if len(words) >= 12 else 0.0))
        directness = min(1.0, 0.55 + (0.1 if len(words) <= 55 else -0.15))
        completeness = min(1.0, 0.35 + (0.1 * min(overlap, 5)))
        concision = max(0.2, min(1.0, 0.9 - max(0, len(words) - 35) * 0.01))
        if request.speaker_evidence:
            style = {
                "score": 0.8,
                "feedback": "The answer is consistent with approved style evidence.",
            }
        else:
            style = {"score": None, "feedback": "Not enough style evidence to assess style match."}
        if request.conflict_metadata:
            support_status = "conflicted"
            support_feedback = (
                "Relevant project evidence contains a conflict; state the ambiguity explicitly."
            )
        elif overlap >= 2:
            support_status = "supported"
            support_feedback = "The answer uses terms supported by the supplied project evidence."
        elif overlap >= 1:
            support_status = "partially_supported"
            support_feedback = "Only part of the answer is connected to the supplied evidence."
        else:
            support_status = "unsupported"
            support_feedback = "The answer did not provide source-supported content."
        supported_ids = [
            str(item["evidence_id"])
            for item in grounding[:2]
            if isinstance(item, dict) and isinstance(item.get("evidence_id"), str) and overlap >= 1
        ]
        result = {
            "correctness": {
                "score": round(correctness, 3),
                "feedback": "The answer addresses the question using the available evidence."
                if overlap
                else "Add a project-supported claim or example.",
            },
            "directness": {
                "score": round(directness, 3),
                "feedback": "The answer is focused on the question."
                if len(words) <= 55
                else "Lead with the answer before adding detail.",
            },
            "completeness": {
                "score": round(completeness, 3),
                "feedback": "The answer covers the main supported point."
                if overlap >= 2
                else "Cover the main cost, risk, or decision point explicitly.",
            },
            "concision": {
                "score": round(concision, 3),
                "feedback": "The answer is a usable length."
                if len(words) <= 55
                else "Trim repeated context and keep the decision point.",
            },
            "style_match": style,
            "source_support": {"status": support_status, "feedback": support_feedback},
            "missing_points": []
            if overlap >= 2
            else ["Connect the answer to a specific project source or decision."],
            "supported_evidence_ids": supported_ids,
        }
        return validate_provider_output(
            request.task_type,
            result,
            conflict_metadata=request.conflict_metadata,
        )
