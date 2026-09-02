"""Narrow, local transcript adapters for standard text representations.

Transcript files are untrusted data.  These adapters only parse bounded UTF-8
text and never interpret transcript markup as executable content.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Final, cast

from presenter_core.errors import CoreDomainError
from presenter_core.ingestion.models import ParsedSourceUnit
from presenter_core.ingestion.parsers.utils import normalize_text

MAX_TRANSCRIPT_SPEAKER_LABEL_LENGTH: Final = 120
MAX_TRANSCRIPT_SEGMENT_TEXT_LENGTH: Final = 20_000
MAX_TRANSCRIPT_TIMESTAMP_MS: Final = 7 * 24 * 60 * 60 * 1_000
MAX_TRANSCRIPT_JSON_DEPTH: Final = 8

_TIME_TOKEN = r"(?:\d+:)?\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3}"
_TIMING_RE = re.compile(rf"^\s*(?P<start>{_TIME_TOKEN})\s+-->\s+(?P<end>{_TIME_TOKEN})(?:\s+.*)?$")
_NAMED_TIME_RE = re.compile(
    rf"^\s*\[(?P<start>{_TIME_TOKEN})\s+-->\s+(?P<end>{_TIME_TOKEN})\]\s*(?P<body>.*)$"
)
_VTT_V_TAG_RE = re.compile(r"<v(?:\s+([^>\r\n]*?))?>", re.IGNORECASE)
_VTT_PRESENTATION_TAG_RE = re.compile(
    r"</?(?:v|c(?:\.[A-Za-z0-9_-]+)*|i|b|u|ruby|rt|lang|br)(?:\s+[^>\r\n]*)?>",
    re.IGNORECASE,
)
_SPEAKER_PREFIX_RE = re.compile(
    r"^(?P<label>[A-Za-z][A-Za-z0-9 .,'’&/_()\-]{0,119})\s*:\s*(?P<body>.+)$"
)


def transcript_parser_for(source_type: str) -> TranscriptParser:
    """Return the parser for one supported transcript file type."""
    parsers: dict[str, TranscriptParser] = {
        "vtt": WebVttParser(),
        "srt": SrtParser(),
        "txt": NamedTextTranscriptParser(),
        "json": StructuredJsonTranscriptParser(),
    }
    try:
        return parsers[source_type]
    except KeyError as exc:
        raise CoreDomainError(
            "SOURCE_TYPE_UNSUPPORTED",
            "This file type is not supported for transcript import.",
            details={"source_type": source_type, "kind": "transcript"},
        ) from exc


class TranscriptParser:
    """Small parser protocol implemented without third-party NLP libraries."""

    parser_id: str

    def parse(self, path: Path) -> list[ParsedSourceUnit]:
        raise NotImplementedError


class WebVttParser(TranscriptParser):
    parser_id = "transcript.vtt"

    def parse(self, path: Path) -> list[ParsedSourceUnit]:
        lines = _read_lines(path, self.parser_id)
        first_content = next((line.strip() for line in lines if line.strip()), "")
        if not first_content.casefold().startswith("webvtt"):
            raise _parse_error(self.parser_id, "The VTT header is missing.")

        units: list[ParsedSourceUnit] = []
        index = 0
        while index < len(lines):
            line = lines[index].strip()
            if not line:
                index += 1
                continue
            upper = line.upper()
            if upper.startswith("WEBVTT"):
                index += 1
                continue
            if upper in {"NOTE", "STYLE", "REGION"} or upper.startswith(
                ("NOTE ", "STYLE ", "REGION ")
            ):
                index = _skip_until_blank(lines, index + 1)
                continue

            timing_index = index
            timing_match = _TIMING_RE.match(lines[timing_index])
            if timing_match is None and index + 1 < len(lines):
                timing_index = index + 1
                timing_match = _TIMING_RE.match(lines[timing_index])
            if timing_match is None:
                if "-->" in line:
                    raise _parse_error(self.parser_id, "A VTT cue timestamp is invalid.")
                index += 1
                continue

            start_ms, end_ms = _parse_range(timing_match, self.parser_id)
            text_lines: list[str] = []
            index = timing_index + 1
            while index < len(lines) and lines[index].strip():
                text_lines.append(lines[index])
                index += 1
            text, speaker_label = _vtt_text_and_speaker("\n".join(text_lines), self.parser_id)
            if text:
                units.append(
                    _transcript_unit(
                        self.parser_id,
                        len(units) + 1,
                        text,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        speaker_label=speaker_label,
                        format_name="vtt",
                    )
                )
        return units


class SrtParser(TranscriptParser):
    parser_id = "transcript.srt"

    def parse(self, path: Path) -> list[ParsedSourceUnit]:
        text = _read_text(path, self.parser_id)
        blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n"))
        units: list[ParsedSourceUnit] = []
        for block in blocks:
            lines = block.splitlines()
            while lines and not lines[0].strip():
                lines.pop(0)
            while lines and not lines[-1].strip():
                lines.pop()
            if not lines:
                continue
            timing_index = 0
            if not _TIMING_RE.match(lines[0]):
                if len(lines) < 2 or not _TIMING_RE.match(lines[1]):
                    if "-->" in " ".join(lines):
                        raise _parse_error(self.parser_id, "An SRT cue timestamp is invalid.")
                    continue
                timing_index = 1
            timing_match = _TIMING_RE.match(lines[timing_index])
            assert timing_match is not None
            start_ms, end_ms = _parse_range(timing_match, self.parser_id)
            body = _normalize_transcript_text("\n".join(lines[timing_index + 1 :]))
            if not body:
                continue
            body, speaker_label = _speaker_prefixed_text(body, self.parser_id)
            if body:
                units.append(
                    _transcript_unit(
                        self.parser_id,
                        len(units) + 1,
                        body,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        speaker_label=speaker_label,
                        format_name="srt",
                    )
                )
        return units


class NamedTextTranscriptParser(TranscriptParser):
    parser_id = "transcript.named-text"

    def parse(self, path: Path) -> list[ParsedSourceUnit]:
        text = _read_text(path, self.parser_id)
        units: list[ParsedSourceUnit] = []
        for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = _NAMED_TIME_RE.match(line)
            if match is not None:
                start_ms = _parse_timestamp(match.group("start"), self.parser_id)
                end_ms = _parse_timestamp(match.group("end"), self.parser_id)
                if end_ms < start_ms:
                    raise _parse_error(self.parser_id, "A transcript cue ends before it starts.")
                body = _normalize_transcript_text(match.group("body"))
            else:
                if line.startswith("["):
                    raise _parse_error(self.parser_id, "A named transcript timestamp is invalid.")
                start_ms = None
                end_ms = None
                body = _normalize_transcript_text(line)
            if not body:
                continue
            body, speaker_label = _speaker_prefixed_text(body, self.parser_id)
            if body:
                units.append(
                    _transcript_unit(
                        self.parser_id,
                        len(units) + 1,
                        body,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        speaker_label=speaker_label,
                        format_name="named-text",
                    )
                )
        return units


class StructuredJsonTranscriptParser(TranscriptParser):
    parser_id = "transcript.json"

    def parse(self, path: Path) -> list[ParsedSourceUnit]:
        try:
            parsed = json.loads(_read_text(path, self.parser_id))
        except (json.JSONDecodeError, RecursionError) as exc:
            raise _parse_error(
                self.parser_id, "The structured transcript JSON is invalid."
            ) from exc
        if not isinstance(parsed, dict) or set(parsed) != {"segments"}:
            raise _parse_error(
                self.parser_id,
                "Structured transcript JSON must contain only a segments array.",
            )
        segments = parsed.get("segments")
        if not isinstance(segments, list):
            raise _parse_error(
                self.parser_id, "The structured transcript segments field is invalid."
            )
        if _json_depth(parsed) > MAX_TRANSCRIPT_JSON_DEPTH:
            raise _parse_error(
                self.parser_id, "The structured transcript JSON is too deeply nested."
            )

        units: list[ParsedSourceUnit] = []
        for segment in segments:
            if not isinstance(segment, dict):
                raise _parse_error(self.parser_id, "Each transcript segment must be an object.")
            if set(segment).difference({"speaker", "start_ms", "end_ms", "text"}):
                raise _parse_error(
                    self.parser_id, "Transcript segments contain unsupported fields."
                )
            if "text" not in segment or not isinstance(segment["text"], str):
                raise _parse_error(self.parser_id, "Each transcript segment requires text.")
            speaker = segment.get("speaker")
            if speaker is not None and not isinstance(speaker, str):
                raise _parse_error(self.parser_id, "Transcript speaker must be a string or null.")
            start_ms = _json_timestamp(segment.get("start_ms"), self.parser_id, "start_ms")
            end_ms = _json_timestamp(segment.get("end_ms"), self.parser_id, "end_ms")
            if start_ms is not None and end_ms is not None and end_ms < start_ms:
                raise _parse_error(self.parser_id, "A transcript cue ends before it starts.")
            body = _normalize_transcript_text(segment["text"])
            if not body:
                continue
            speaker_label = _normalize_speaker(speaker, self.parser_id)
            units.append(
                _transcript_unit(
                    self.parser_id,
                    len(units) + 1,
                    body,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    speaker_label=speaker_label,
                    format_name="json",
                )
            )
        return units


def _read_text(path: Path, parser_id: str) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise _parse_error(parser_id, "The transcript could not be decoded as UTF-8.") from exc


def _read_lines(path: Path, parser_id: str) -> list[str]:
    return _read_text(path, parser_id).replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _skip_until_blank(lines: list[str], index: int) -> int:
    while index < len(lines) and lines[index].strip():
        index += 1
    return index


def _parse_range(match: re.Match[str], parser_id: str) -> tuple[int, int]:
    start_ms = _parse_timestamp(match.group("start"), parser_id)
    end_ms = _parse_timestamp(match.group("end"), parser_id)
    if end_ms < start_ms:
        raise _parse_error(parser_id, "A transcript cue ends before it starts.")
    return start_ms, end_ms


def _parse_timestamp(value: str, parser_id: str) -> int:
    parts = re.fullmatch(r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{1,3})", value)
    if parts is not None:
        hours = int(parts.group(1) or 0)
        minutes = int(parts.group(2))
        seconds = int(parts.group(3))
        fraction = parts.group(4)
    else:
        short_parts = re.fullmatch(r"(\d{1,2}):(\d{2})[.,](\d{1,3})", value)
        if short_parts is None:
            raise _parse_error(parser_id, "A transcript timestamp is invalid.")
        hours = 0
        minutes = int(short_parts.group(1))
        seconds = int(short_parts.group(2))
        fraction = short_parts.group(3)
    if minutes >= 60 or seconds >= 60:
        raise _parse_error(parser_id, "A transcript timestamp is invalid.")
    milliseconds = int(fraction.ljust(3, "0"))
    result = ((hours * 60 + minutes) * 60 + seconds) * 1_000 + milliseconds
    if result > MAX_TRANSCRIPT_TIMESTAMP_MS:
        raise _parse_error(parser_id, "A transcript timestamp exceeds the import limit.")
    return result


def _json_timestamp(value: Any, parser_id: str, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _parse_error(parser_id, f"Transcript {field} must be an integer or null.")
    if value < 0 or value > MAX_TRANSCRIPT_TIMESTAMP_MS:
        raise _parse_error(parser_id, f"Transcript {field} is outside the import limit.")
    return cast(int, value)


def _speaker_prefixed_text(text: str, parser_id: str) -> tuple[str, str | None]:
    match = _SPEAKER_PREFIX_RE.match(text)
    if match is None:
        return _bounded_text(text, parser_id), None
    label = _normalize_speaker(match.group("label"), parser_id)
    body = _bounded_text(match.group("body"), parser_id)
    return body, label


def _vtt_text_and_speaker(text: str, parser_id: str) -> tuple[str, str | None]:
    speaker_label: str | None = None

    def remove_v_tag(match: re.Match[str]) -> str:
        nonlocal speaker_label
        if speaker_label is None and match.group(1):
            speaker_label = _normalize_speaker(match.group(1), parser_id)
        return ""

    stripped = _VTT_V_TAG_RE.sub(remove_v_tag, text)
    stripped = _VTT_PRESENTATION_TAG_RE.sub("", stripped)
    normalized = _normalize_transcript_text(stripped)
    if speaker_label is None:
        normalized, speaker_label = _speaker_prefixed_text(normalized, parser_id)
    return normalized, speaker_label


def _transcript_unit(
    parser_id: str,
    ordinal: int,
    text: str,
    *,
    start_ms: int | None,
    end_ms: int | None,
    speaker_label: str | None,
    format_name: str,
) -> ParsedSourceUnit:
    return ParsedSourceUnit(
        unit_type="transcript_segment",
        ordinal=ordinal,
        title=None,
        text=_bounded_text(text, parser_id),
        metadata={"parser": parser_id, "format": format_name},
        start_ms=start_ms,
        end_ms=end_ms,
        speaker_label=speaker_label,
    )


def _normalize_transcript_text(value: str) -> str:
    return re.sub(r"\s+", " ", normalize_text(value))


def _bounded_text(value: str, parser_id: str) -> str:
    normalized = _normalize_transcript_text(value)
    if len(normalized) > MAX_TRANSCRIPT_SEGMENT_TEXT_LENGTH:
        raise _parse_error(parser_id, "A transcript segment exceeds the text limit.")
    return normalized


def _normalize_speaker(value: str | None, parser_id: str) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    if not normalized:
        return None
    if len(normalized) > MAX_TRANSCRIPT_SPEAKER_LABEL_LENGTH or any(
        ord(character) < 32 for character in normalized
    ):
        raise _parse_error(parser_id, "A transcript speaker label is invalid or too long.")
    return normalized


def _json_depth(value: Any, depth: int = 0) -> int:
    maximum = depth
    stack: list[tuple[Any, int]] = [(value, depth)]
    while stack:
        current, current_depth = stack.pop()
        maximum = max(maximum, current_depth)
        if isinstance(current, dict):
            stack.extend((child, current_depth + 1) for child in current.values())
        elif isinstance(current, list):
            stack.extend((child, current_depth + 1) for child in current)
    return maximum


def _parse_error(parser_id: str, message: str) -> CoreDomainError:
    return CoreDomainError(
        "SOURCE_PARSE_FAILED",
        message,
        details={"parser_id": parser_id, "source_type": "transcript"},
    )
