"""Fail-closed policy for project-local observable audience observations."""

from __future__ import annotations

import re
from typing import Final

from presenter_core.errors import CoreDomainError

_PROHIBITED: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "race_ethnicity",
        re.compile(r"\b(?:race|racial|ethnic|ethnicity|nationality|ancestry)\b", re.I),
    ),
    (
        "religion",
        re.compile(
            r"\b(?:religion|religious|faith|christian|muslim|jewish|hindu|buddhist|atheist)\b",
            re.I,
        ),
    ),
    (
        "political_belief",
        re.compile(
            r"\b(?:politic|republican|democrat|liberal|conservative|libertarian|socialist|"
            r"party affiliation|party member|left-wing|right-wing)\b",
            re.I,
        ),
    ),
    (
        "sexual_orientation_or_sex_life",
        re.compile(
            r"\b(?:sexual orientation|sex life|gay|lesbian|bisexual|heterosexual|"
            r"transgender|queer)\b",
            re.I,
        ),
    ),
    (
        "medical_or_health",
        re.compile(
            r"\b(?:medical|health|medication|prescription|diagnos(?:is|ed)|disease|"
            r"illness|sick|pregnan)\b",
            re.I,
        ),
    ),
    (
        "disability",
        re.compile(
            r"\b(?:disab(?:ility|led)|adhd|autis(?:m|tic)|bipolar|dyslex|wheelchair|"
            r"blind|deaf|impairment)\b",
            re.I,
        ),
    ),
    (
        "criminal_history",
        re.compile(
            r"\b(?:criminal|convict(?:ed|ion)?|felon|arrest(?:ed)?|jail|prison|probation)\b",
            re.I,
        ),
    ),
    (
        "union_membership",
        re.compile(r"\b(?:union member(?:ship)?|trade union|labor union|unionized)\b", re.I),
    ),
    (
        "psychology_or_hidden_emotion",
        re.compile(
            r"\b(?:psycholog(?:y|ical)|personality|depress(?:ed|ion)|anxious|anxiety|"
            r"emotion(?:al|ally)?|mood|mentally|unstable|low confidence|insecure|"
            r"happy|sad|angry|frustrat(?:ed|ion)|excited|calm|confiden(?:t|ce)|stress(?:ed)?)\b",
            re.I,
        ),
    ),
    (
        "deception",
        re.compile(
            r"\b(?:deceiv\w*|decept\w*|lie(?:s|d)?|lie detector|liar|lying|"
            r"untruth\w*|dishonest)\b",
            re.I,
        ),
    ),
    (
        "intelligence",
        re.compile(r"\b(?:intelligen(?:ce|t)|iq|smart|stupid|dumb|brilliant)\b", re.I),
    ),
    (
        "employability",
        re.compile(r"\b(?:unemployable|employab(?:ility|le)|hireability|fit to work)\b", re.I),
    ),
)


class ObservationPolicy:
    """Validate all user-visible observation wording at every lifecycle gate."""

    @classmethod
    def validate_text(cls, text: str) -> str:
        normalized = text.strip()
        for category, pattern in _PROHIBITED:
            if pattern.search(normalized):
                raise CoreDomainError(
                    "AUDIENCE_OBSERVATION_PROHIBITED",
                    "This audience observation describes a prohibited sensitive or hidden trait.",
                    details={"category": category},
                )
        return normalized
