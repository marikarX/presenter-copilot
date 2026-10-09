"""Plain numbering schemes stay consistent across Core, Copilot schema and text fitting."""

import pytest

from presenter_core.presentation.fidelity import (
    PARAGRAPH_AUTONUM_TYPE_BY_MODE,
    PARAGRAPH_BULLET_MODES,
)
from presenter_core.presentation.text_fit import numbering_marker
from presenter_core.providers.edit_plan_schema import _STYLE_PROPERTIES


def test_copilot_schema_offers_exactly_the_core_bullet_modes():
    assert set(_STYLE_PROPERTIES["bullet_mode"]["enum"]) == PARAGRAPH_BULLET_MODES


@pytest.mark.parametrize(
    ("kind", "value", "marker"),
    [
        ("arabicPeriod", 3, "3."),
        ("arabicParenR", 12, "12)"),
        ("arabicPlain", 7, "7"),
        ("alphaLcPeriod", 1, "a."),
        ("alphaLcPeriod", 26, "z."),
        ("alphaLcPeriod", 27, "aa."),
        ("alphaUcPeriod", 28, "BB."),
        ("romanLcPeriod", 4, "iv."),
        ("romanUcPeriod", 1994, "MCMXCIV."),
        ("romanUcPeriod", 3999, "MMMCMXCIX."),
    ],
)
def test_numbering_markers_match_native_schemes(kind, value, marker):
    assert numbering_marker(kind, value) == marker


@pytest.mark.parametrize(("kind", "value"), [("romanUcPeriod", 4000), ("circleNumDbPlain", 1)])
def test_unsupported_numbering_markers_are_declined(kind, value):
    assert numbering_marker(kind, value) is None


def test_every_numbering_mode_has_a_measurable_marker():
    for kind in PARAGRAPH_AUTONUM_TYPE_BY_MODE.values():
        assert numbering_marker(kind, 1)
