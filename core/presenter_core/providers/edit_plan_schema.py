"""Strict provider plans contain bounded native operations, never code or paths."""

from __future__ import annotations

import copy
import math
from typing import Any


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties),
    }


def _text(limit: int, minimum: int = 0) -> dict[str, Any]:
    return {"type": "string", "minLength": minimum, "maxLength": limit}


def _integer(minimum: int, maximum: int) -> dict[str, Any]:
    return {"type": "integer", "minimum": minimum, "maximum": maximum}


def _choice(*values: str) -> dict[str, Any]:
    return {"type": "string", "enum": list(values)}


_ID = {"anyOf": [_text(36, 36), _object({"created_by": _integer(1, 20)})]}
_GEOMETRY = _object(
    {
        "x_emu": _integer(0, 2_147_483_647),
        "y_emu": _integer(0, 2_147_483_647),
        "width_emu": _integer(1, 2_147_483_647),
        "height_emu": _integer(1, 2_147_483_647),
    }
)
_CROP = _object({name: _integer(0, 99_999) for name in ("left", "right", "top", "bottom")})
_ADJUSTMENT = _object(
    {
        "brightness_percent": _integer(-100, 100),
        "contrast_percent": _integer(-100, 100),
        "grayscale": {"type": "boolean"},
    }
)
_ROTATION = _object(
    {
        "rotation_degrees": {"type": "number", "minimum": 0, "maximum": 359.999},
        "flip_horizontal": {"type": "boolean"},
        "flip_vertical": {"type": "boolean"},
    }
)
_STYLE_PROPERTIES = {
    "bold": {"type": "boolean"},
    "italic": {"type": "boolean"},
    "underline": {"type": "boolean"},
    "strikethrough": {"type": "boolean"},
    "font_family": _text(31, 1),
    "font_size_pt": _integer(6, 96),
    "font_color": _text(7, 7),
    "alignment": _choice("left", "center", "right", "justify"),
    # Must equal presentation.fidelity.PARAGRAPH_BULLET_MODES (asserted by tests).
    "bullet_mode": _choice(
        "none",
        "numbered",
        "numbered_paren",
        "numbered_alpha_lower",
        "numbered_alpha_upper",
        "numbered_roman_lower",
        "numbered_roman_upper",
        "bullet",
        "bullet_hollow",
        "bullet_square",
        "bullet_dash",
    ),
    "bullet_color": _text(7, 7),
    "bullet_size_percent": _integer(25, 400),
    "numbering_start": _integer(1, 9999),
    "left_indent_pt": _integer(0, 144),
    "first_line_indent_pt": _integer(-144, 144),
    "line_spacing_pt": _integer(1, 144),
    "space_before_pt": _integer(0, 144),
    "space_after_pt": _integer(0, 144),
}
_STYLE = _object(
    {name: {"anyOf": [schema, {"type": "null"}]} for name, schema in _STYLE_PROPERTIES.items()}
)
_SHAPE_STYLE = _object(
    {
        **{
            name: {"anyOf": [_text(7, 7), {"type": "null"}]}
            for name in ("fill_color", "line_color")
        },
        "fill_transparency_percent": {"anyOf": [_integer(0, 100), {"type": "null"}]},
        "line_width_pt": {
            "anyOf": [{"type": "number", "minimum": 0.25, "maximum": 20}, {"type": "null"}]
        },
        "line_dash": {
            "anyOf": [
                _choice(
                    "solid", "dash", "dot", "dashDot", "lgDash", "lgDashDot", "sysDash", "sysDot"
                ),
                {"type": "null"},
            ]
        },
    }
)
_DIAGRAM = _object(
    {
        "name": _text(120, 1),
        "kind": _choice("process", "hierarchy", "cycle"),
        "palette": _choice("classic", "midnight", "paper"),
        "nodes": {
            "type": "array",
            "minItems": 2,
            "maxItems": 8,
            "items": _object(
                {
                    "id": _text(40, 1),
                    "label": _text(80, 1),
                    "parent": {"anyOf": [_text(40, 1), {"type": "null"}]},
                }
            ),
        },
    }
)
_TARGET = {"slide_id": _ID, "object_id": _ID}
_CELLS = {
    "type": "array",
    "minItems": 1,
    "maxItems": 12,
    "items": {"type": "array", "minItems": 1, "maxItems": 8, "items": _text(500)},
}
_CHART_DATA = {
    "title": _text(120, 1),
    "chart_type": _choice("column", "bar", "line", "pie"),
    "categories": {"type": "array", "minItems": 1, "maxItems": 24, "items": _text(80, 1)},
    "series": {
        "type": "array",
        "minItems": 1,
        "maxItems": 6,
        "items": _object(
            {
                "name": _text(80, 1),
                "values": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 24,
                    "items": {"type": "number", "minimum": -1e12, "maximum": 1e12},
                },
            }
        ),
    },
}


def _sources(size: int) -> dict[str, Any]:
    return {
        "type": "array",
        "minItems": 1,
        "maxItems": size,
        "items": {"anyOf": [_integer(0, size - 1), {"type": "null"}]},
    }


PARAMETER_SCHEMAS = {
    "replace_text_shape": _object({**_TARGET, "replacement_text": _text(2000)}),
    "replace_speaker_notes": _object({"slide_id": _ID, "replacement_text": _text(12000)}),
    "fit_text_shape": _object(
        {**_TARGET, "strategy": _choice("grow", "shrink"), "minimum_size_pt": _integer(6, 96)}
    ),
    "format_text_shape": _object({**_TARGET, "replacement_style": _STYLE}),
    "format_shape_style": _object({**_TARGET, "replacement_style": _SHAPE_STYLE}),
    "transform_object": _object({**_TARGET, "replacement_geometry": _GEOMETRY}),
    "group_objects": _object(
        {
            "slide_id": _ID,
            "objects": {
                "type": "array",
                "minItems": 2,
                "maxItems": 20,
                "items": _object({"object_id": _ID}),
            },
        }
    ),
    "ungroup_object": _object(_TARGET),
    "change_object_layer": _object(
        {**_TARGET, "direction": _choice("forward", "backward", "front", "back")}
    ),
    "crop_picture": _object({**_TARGET, "replacement_crop": _CROP}),
    "adjust_picture": _object({**_TARGET, "replacement_adjustment": _ADJUSTMENT}),
    "rotate_object": _object({**_TARGET, "replacement_rotation": _ROTATION}),
    "set_text_hyperlink": _object(
        {**_TARGET, "replacement_url": {"anyOf": [_text(2048, 1), {"type": "null"}]}}
    ),
    "set_slide_background": _object(
        {"slide_id": _ID, "replacement_color": {"anyOf": [_text(7, 7), {"type": "null"}]}}
    ),
    "reorder_slides": _object(
        {"ordered_slide_ids": {"type": "array", "minItems": 1, "maxItems": 5000, "items": _ID}}
    ),
    "apply_slide_layout": _object({"slide_id": _ID, "layout_source_slide_id": _ID}),
    "create_slide": _object({"slide_id": _ID, "layout_source_slide_id": _ID}),
    "create_authored_slide": _object(
        {
            "slide_id": _ID,
            "layout_source_slide_id": _ID,
            "title": _text(120, 1),
            "bullets": {"type": "array", "minItems": 0, "maxItems": 8, "items": _text(200, 1)},
            "notes": _text(4000),
            "template": _choice("classic", "midnight", "paper"),
            "layout": _choice("points", "columns", "cards", "statement"),
        }
    ),
    "duplicate_slide": _object({"slide_id": _ID}),
    "delete_slide": _object({"slide_id": _ID}),
    "create_text_box": _object({"slide_id": _ID, "text": _text(2000, 1)}),
    "create_picture": _object(
        {"slide_id": _ID, "asset_id": _text(64, 64), "geometry": _GEOMETRY, "alt_text": _text(2000)}
    ),
    "create_shape": _object(
        {
            "slide_id": _ID,
            "shape_type": _choice("rect", "ellipse"),
            "geometry": _GEOMETRY,
            "fill_color": _text(7, 7),
            "line_color": _text(7, 7),
        }
    ),
    "create_diagram": _object({"slide_id": _ID, "data": _DIAGRAM, "geometry": _GEOMETRY}),
    "replace_diagram": _object({**_TARGET, "data": _DIAGRAM, "geometry": _GEOMETRY}),
    "delete_diagram": _object(_TARGET),
    "format_table_cells": _object(
        {
            **_TARGET,
            "row_start": _integer(0, 11),
            "row_end": _integer(0, 11),
            "column_start": _integer(0, 7),
            "column_end": _integer(0, 7),
            "style": _object(
                {
                    name: {"anyOf": [value, {"type": "null"}]}
                    for name, value in {
                        "bold": {"type": "boolean"},
                        "italic": {"type": "boolean"},
                        "font_size_pt": _integer(6, 96),
                        "font_color": _text(7, 7),
                        "fill_color": _text(7, 7),
                        "alignment": _choice("left", "center", "right", "justify"),
                        "vertical_alignment": _choice("top", "center", "bottom"),
                    }.items()
                }
            ),
        }
    ),
    "set_chart_marker": _object(
        {
            **_TARGET,
            "series_index": _integer(0, 5),
            "marker_symbol": _choice(
                "none",
                "circle",
                "square",
                "diamond",
                "triangle",
                "x",
                "plus",
                "star",
                "dot",
                "dash",
            ),
            "marker_size": _integer(2, 72),
        }
    ),
    "set_chart_fill": _object(
        {
            **_TARGET,
            "series_index": _integer(0, 5),
            "point_index": {"anyOf": [_integer(0, 23), {"type": "null"}]},
            "fill": {
                "anyOf": [
                    _object(
                        {
                            "kind": _choice("solid"),
                            "color": _text(7, 7),
                            "opacity_percent": _integer(0, 100),
                        }
                    ),
                    _object(
                        {
                            "kind": _choice("linear_gradient"),
                            "angle_degrees": _integer(0, 359),
                            "stops": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 8,
                                "items": _object(
                                    {
                                        "position_percent": _integer(0, 100),
                                        "color": _text(7, 7),
                                        "opacity_percent": _integer(0, 100),
                                    }
                                ),
                            },
                        }
                    ),
                ]
            },
        }
    ),
    "set_chart_color": _object(
        {
            **_TARGET,
            "series_index": _integer(0, 5),
            "point_index": {"anyOf": [_integer(0, 23), {"type": "null"}]},
            "color": _text(7, 7),
        }
    ),
    **{
        kind: _object(
            {
                **_TARGET,
                **{
                    k: _integer(0, 11 if k.startswith("row") else 7)
                    for k in ["row_start", "row_end", "column_start", "column_end"]
                },
            }
        )
        for kind in ["merge_table_cells", "split_table_cells"]
    },
    "fit_table_rows": _object({**_TARGET, "strategy": _choice("grow", "compact")}),
    "set_table_borders": _object(
        {
            **_TARGET,
            "row_start": _integer(0, 11),
            "row_end": _integer(0, 11),
            "column_start": _integer(0, 7),
            "column_end": _integer(0, 7),
            "border_scope": _choice(
                "all",
                "outline",
                "inside",
                "horizontal",
                "vertical",
                "top",
                "bottom",
                "left",
                "right",
            ),
            "line_style": _choice("solid", "dash", "dot", "none"),
            "width_pt": {
                "anyOf": [{"type": "number", "minimum": 0.25, "maximum": 12}, {"type": "null"}]
            },
            "color": {"anyOf": [_text(7, 7), {"type": "null"}]},
        }
    ),
    "set_chart_axis": _object(
        {
            **_TARGET,
            "axis_kind": _choice("category", "value"),
            **{
                field: {"type": "boolean"}
                for field in ["visible", "major_gridlines", "minor_gridlines"]
            },
            "tick_labels": _choice("next_to", "low", "high", "none"),
            "title": {"anyOf": [_text(120), {"type": "null"}]},
            "number_format": {"anyOf": [_text(64, 1), {"type": "null"}]},
            **{
                field: {
                    "anyOf": [
                        {
                            "type": "number",
                            "minimum": -1e12 if field in {"minimum", "maximum"} else 1e-9,
                            "maximum": 1e12,
                        },
                        {"type": "null"},
                    ]
                }
                for field in ["minimum", "maximum", "major_unit", "minor_unit"]
            },
        }
    ),
    "set_chart_labels": _object(
        {
            **_TARGET,
            "series_index": {"anyOf": [_integer(0, 5), {"type": "null"}]},
            "position": _choice(
                "hidden",
                "default",
                "center",
                "inside_end",
                "inside_base",
                "outside_end",
                "best_fit",
                "above",
                "below",
                "left",
                "right",
            ),
            **{
                field: {"type": "boolean"}
                for field in ["show_value", "show_category", "show_series", "show_percent"]
            },
            "number_format": {"anyOf": [_text(64, 1), {"type": "null"}]},
        }
    ),
    "set_chart_legend": _object(
        {
            **_TARGET,
            "legend_position": _choice("hidden", "left", "right", "top", "bottom", "top_right"),
            "legend_overlay": {"type": "boolean"},
        }
    ),
    "create_table": _object(
        {"slide_id": _ID, "geometry": _GEOMETRY, "cells": _CELLS, "header_row": {"type": "boolean"}}
    ),
    "replace_table_cells": _object({**_TARGET, "cells": _CELLS}),
    "reshape_table": _object(
        {**_TARGET, "cells": _CELLS, "row_sources": _sources(12), "column_sources": _sources(8)}
    ),
    "create_chart": _object({"slide_id": _ID, "geometry": _GEOMETRY, **_CHART_DATA}),
    "replace_chart_data": _object({**_TARGET, **_CHART_DATA}),
    "reshape_chart": _object(
        {**_TARGET, **_CHART_DATA, "category_sources": _sources(24), "series_sources": _sources(6)}
    ),
    "delete_object": _object(_TARGET),
    "duplicate_object": _object(_TARGET),
}


PARAMETER_SCHEMAS["set_shape_fill"] = _object(
    {**_TARGET, "fill": copy.deepcopy(PARAMETER_SCHEMAS["set_chart_fill"]["properties"]["fill"])}
)


def edit_plan_output_schema() -> dict[str, Any]:
    schema = _object(
        {
            "summary": _text(500, 1),
            "operations": {
                "type": "array",
                "minItems": 1,
                "maxItems": 20,
                "items": {
                    "anyOf": [
                        _object(
                            {
                                "type": _choice(kind),
                                "params": params,
                                "rationale": _text(300, 1),
                                "evidence_ids": {
                                    "type": "array",
                                    "maxItems": 8,
                                    "items": _text(120, 1),
                                },
                            }
                        )
                        for kind, params in PARAMETER_SCHEMAS.items()
                    ]
                },
            },
        }
    )
    return copy.deepcopy(schema)


def _matches(value: Any, schema: dict[str, Any]) -> bool:
    """Validate precisely the finite schema vocabulary above, before domain binding."""
    if "anyOf" in schema:
        return any(_matches(value, item) for item in schema["anyOf"])
    kind = schema["type"]
    if kind == "object":
        return (
            isinstance(value, dict)
            and set(value) == set(schema["properties"])
            and all(_matches(value[name], child) for name, child in schema["properties"].items())
        )
    if kind == "array":
        return (
            isinstance(value, list)
            and schema.get("minItems", 0) <= len(value) <= schema["maxItems"]
            and all(_matches(item, schema["items"]) for item in value)
        )
    if kind == "string":
        return (
            isinstance(value, str)
            and schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 500)
            and ("enum" not in schema or value in schema["enum"])
            and all(
                code in (9, 10, 13)
                or 0x20 <= code <= 0xD7FF
                or 0xE000 <= code <= 0xFFFD
                or 0x10000 <= code <= 0x10FFFF
                for code in map(ord, value)
            )
        )
    if kind == "integer":
        return type(value) is int and schema["minimum"] <= value <= schema["maximum"]
    if kind == "number":
        return (
            type(value) in (int, float)
            and schema["minimum"] <= value <= schema["maximum"]
            and math.isfinite(value)
        )
    if kind == "boolean":
        return type(value) is bool
    return kind == "null" and value is None


def validate_edit_plan(value: dict[str, Any]) -> dict[str, Any]:
    from .models import ProviderError

    if not _matches(value, edit_plan_output_schema()):
        raise ProviderError("PROVIDER_MALFORMED_OUTPUT", "The proposed edit plan is invalid.")
    if not value["summary"].strip() or any(
        not item["rationale"].strip() for item in value["operations"]
    ):
        raise ProviderError("PROVIDER_MALFORMED_OUTPUT", "The edit plan needs a review summary.")
    return copy.deepcopy(value)
