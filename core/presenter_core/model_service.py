"""Explicit local model bootstrap and cache lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from presenter_core.asr.service import ASRService
from presenter_core.errors import CoreDomainError, invalid_request, reject_unknown_fields
from presenter_core.retrieval.embeddings import EmbeddingAdapter
from presenter_core.storage.service import StorageManager


class ModelService:
    """Expose model state without allowing normal runtime paths to download."""

    def __init__(
        self,
        storage: StorageManager,
        asr: ASRService,
        embeddings: EmbeddingAdapter,
        event_sink: Any | None = None,
        before_remove: Callable[[], None] | None = None,
    ) -> None:
        self._storage = storage
        self._asr = asr
        self._embeddings = embeddings
        self._event_sink = event_sink
        self._before_remove = before_remove
        self._preparing: str | None = None

    def status(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, set())
        asr_status = self._asr.status({})
        asr_model_status = str(asr_status.get("model_status", "unavailable"))
        embedding_status = self._embedding_status()
        return {
            "network_policy": {
                "runtime": "local_files_only",
                "prepare": "explicit_user_action_only",
            },
            "models": [
                {
                    "kind": "asr",
                    "adapter_id": asr_status.get("adapter_id"),
                    "model_id": asr_status.get("model_id"),
                    "status": asr_model_status,
                    "local_only": True,
                    "cache_location": "app-data/models/asr",
                    "disk_requirement_mb": None,
                    "preparing": self._preparing == "asr",
                    "error_code": asr_status.get("last_error_code"),
                },
                {
                    "kind": "embeddings",
                    "adapter_id": self._embeddings.adapter_id,
                    "model_id": self._embeddings.model_id,
                    "status": embedding_status,
                    "local_only": True,
                    "cache_location": "app-data/models/embeddings",
                    "disk_requirement_mb": None,
                    "preparing": self._preparing == "embeddings",
                    "error_code": (
                        None
                        if embedding_status in {"ready", "installed"}
                        else "EMBEDDING_MODEL_UNAVAILABLE"
                    ),
                },
            ],
        }

    def prepare(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"kind"})
        kind = params.get("kind")
        if kind not in {"asr", "embeddings"}:
            raise invalid_request("kind must be asr or embeddings.", field="kind")
        if self._preparing is not None:
            raise CoreDomainError(
                "MODEL_PREPARE_BUSY",
                "Another local model preparation is already in progress.",
                retryable=True,
            )
        self._preparing = str(kind)
        self._emit(
            "models.progress",
            {"kind": kind, "phase": "prepare", "progress": 0},
        )
        try:
            if kind == "asr":
                self._asr.prepare_model({})
            else:
                health = self._embeddings.prepare_explicit()
                if health.status != "ready":
                    raise CoreDomainError(
                        health.error_code or "EMBEDDING_MODEL_PREPARE_FAILED",
                        "The local embedding model could not be prepared.",
                        retryable=True,
                    )
            self._emit(
                "models.progress",
                {"kind": kind, "phase": "prepare", "progress": 1},
            )
        except CoreDomainError as error:
            self._emit(
                "models.progress",
                {"kind": kind, "phase": "prepare", "progress": 0, "error_code": error.code},
            )
            raise
        except Exception as error:
            self._emit(
                "models.progress",
                {
                    "kind": kind,
                    "phase": "prepare",
                    "progress": 0,
                    "error_code": "MODEL_PREPARE_FAILED",
                },
            )
            raise CoreDomainError(
                "MODEL_PREPARE_FAILED",
                "The local model could not be prepared.",
                retryable=True,
            ) from error
        finally:
            self._preparing = None
        return self.status({})

    def remove(self, params: dict[str, Any]) -> dict[str, Any]:
        reject_unknown_fields(params, {"kind", "confirm"})
        kind = params.get("kind")
        if kind not in {"asr", "embeddings", "all"}:
            raise invalid_request("kind must be asr, embeddings, or all.", field="kind")
        if params.get("confirm") is not True:
            raise CoreDomainError(
                "MODEL_REMOVE_CONFIRMATION_REQUIRED",
                "Model cache removal requires explicit confirmation.",
            )
        if self._before_remove is not None:
            self._before_remove()
        if kind in {"asr", "all"}:
            self._asr.release_models()
        if kind in {"embeddings", "all"}:
            self._embeddings.close()
        removed = self._storage.paths.delete_model_cache(str(kind))
        return {
            "kind": kind,
            "removed": removed,
            "model_cache_retained": False,
        }

    def _embedding_status(self) -> str:
        try:
            return self._embeddings.model_status()
        except Exception:
            return "unavailable"

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self._event_sink is not None:
            self._event_sink(event, payload)
