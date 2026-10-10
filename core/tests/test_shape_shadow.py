"""Reviewed shape shadow on/off."""

from pathlib import Path

from test_shape_transparency import A, P, _Shapes


def _effects(shapes: _Shapes, name: str):
    color = shapes.color(name)
    shape = color.getparent().getparent().getparent()
    assert shape.tag == f"{P}sp"
    return shape.find(f"{P}spPr/{A}effectLst"), [
        c.tag.removeprefix(A) for c in shape.find(f"{P}spPr")
    ]


def test_shadow_adds_removes_and_reads_back(tmp_path: Path) -> None:
    shapes = _Shapes(tmp_path)
    try:
        style = shapes.shape("Filled")[0]["shape_style"]
        assert style["shadow_editable"] and style["shadow"] is None
        assert shapes.style("Filled", {"shadow": True})["ok"]
        effects, order = _effects(shapes, "Filled")
        assert [child.tag.removeprefix(A) for child in effects] == ["outerShdw"]
        assert order.index("effectLst") > order.index("solidFill")
        assert shapes.shape("Filled")[0]["shape_style"]["shadow"] is True
        assert shapes.style("Filled", {"shadow": False})["ok"]
        effects, _ = _effects(shapes, "Filled")
        assert len(effects) == 0
        assert shapes.shape("Filled")[0]["shape_style"]["shadow"] is False
        bad = shapes.style("Filled", {"shadow": "yes"})
        assert not bad["ok"] and bad["error"]["code"] == "INVALID_REQUEST"
    finally:
        shapes.core.close()


def test_shape_type_changes_and_resets_adjustments(tmp_path: Path) -> None:
    shapes = _Shapes(tmp_path)
    try:
        assert shapes.shape("Filled")[0]["shape_style"]["shape_geometry"] == "rect"
        assert shapes.style("Filled", {"shape_geometry": "roundRect"})["ok"]
        assert shapes.shape("Filled")[0]["shape_style"]["shape_geometry"] == "roundRect"
        _effects_node, _order = _effects(shapes, "Filled")
        geometry = shapes.color("Filled").getparent().getparent().find(f"{A}prstGeom")
        assert geometry.get("prst") == "roundRect" and len(geometry.find(f"{A}avLst")) == 0
        bad = shapes.style("Filled", {"shape_geometry": "star99"})
        assert not bad["ok"] and bad["error"]["code"] == "INVALID_REQUEST"
    finally:
        shapes.core.close()
