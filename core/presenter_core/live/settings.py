"""App-scope Live HUD preferences with fail-closed defaults."""

from __future__ import annotations

import re
from typing import Any

from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.storage.service import StorageManager

HUD_METADATA_KEY = "hud.settings.v1"
HUD_SHORTCUT_KEYS = (
    "push_to_assist",
    "show_hide",
    "expand_collapse",
    "previous_cue",
    "next_cue",
    "clear",
    "previous_slide",
    "next_slide",
)
DEFAULT_HUD_SETTINGS: dict[str, Any] = {
    "display_id": None,
    "width": 560,
    "font_size": 24,
    "top_offset": 32,
    "shortcuts": {
        "push_to_assist": "Ctrl+Alt+Space",
        "show_hide": "Ctrl+Alt+H",
        "expand_collapse": "Ctrl+Alt+Enter",
        "previous_cue": "Ctrl+Alt+Left",
        "next_cue": "Ctrl+Alt+Right",
        "clear": "Ctrl+Alt+Backspace",
        "previous_slide": "Ctrl+Alt+PageUp",
        "next_slide": "Ctrl+Alt+PageDown",
    },
}


class HudSettingsService:
    """Persist only safe HUD geometry and shortcut metadata in app scope."""

    def __init__(self, storage: StorageManager) -> None:
        self._storage = storage

    def get(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, set())
        value = self._read_stored()
        return {"settings": self.normalize(value)}

    def update(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"settings"})
        settings = params.get("settings")
        if not isinstance(settings, dict):
            raise invalid_request("settings must be an object.", field="settings")
        reject_unknown_fields(
            settings,
            {"display_id", "width", "font_size", "top_offset", "shortcuts"},
        )
        current = self._read_stored()
        merged = self.normalize(current)
        for key in ("display_id", "width", "font_size", "top_offset"):
            if key in settings:
                merged[key] = settings[key]
        if "shortcuts" in settings:
            if not isinstance(settings["shortcuts"], dict):
                raise invalid_request("shortcuts must be an object.", field="settings")
            reject_unknown_fields(settings["shortcuts"], set(HUD_SHORTCUT_KEYS))
            merged["shortcuts"] = {**merged["shortcuts"], **settings["shortcuts"]}
        normalized = self.normalize(merged)
        self._storage.set_app_metadata(HUD_METADATA_KEY, normalized)
        return {"settings": normalized}

    def _read_stored(self) -> Any | None:
        """Treat damaged device preferences as absent and use safe defaults."""
        try:
            return self._storage.get_app_metadata(HUD_METADATA_KEY)
        except CoreDomainError as error:
            if error.code == "APP_METADATA_INVALID":
                return None
            raise

    @staticmethod
    def normalize(value: Any) -> dict[str, Any]:
        result = {
            **DEFAULT_HUD_SETTINGS,
            "shortcuts": dict(DEFAULT_HUD_SETTINGS["shortcuts"]),
        }
        if not isinstance(value, dict):
            return result
        display_id = value.get("display_id")
        if display_id is None or (
            isinstance(display_id, str)
            and len(display_id) <= 120
            and "\n" not in display_id
            and "\r" not in display_id
        ):
            result["display_id"] = display_id
        for key, minimum, maximum in (
            ("width", 360, 900),
            ("font_size", 16, 48),
            ("top_offset", 0, 240),
        ):
            candidate = value.get(key)
            if isinstance(candidate, (int, float)) and not isinstance(candidate, bool):
                result[key] = max(minimum, min(maximum, round(float(candidate))))
        shortcuts = value.get("shortcuts")
        if isinstance(shortcuts, dict):
            for key in HUD_SHORTCUT_KEYS:
                candidate = shortcuts.get(key)
                if (
                    isinstance(candidate, str)
                    and len(candidate) <= 80
                    and re.search(
                        r"(?:CommandOrControl|Ctrl|Alt|Shift|Command|Super)\+",
                        candidate,
                        re.I,
                    )
                    and "\n" not in candidate
                    and "\r" not in candidate
                ):
                    result["shortcuts"][key] = candidate.strip()
        return result
