"""Replaceable local embedding adapters used by the project retrieval index."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from presenter_core.errors import CoreDomainError
from presenter_core.ingestion.parsers.utils import lexical_normalize
from presenter_core.storage.paths import resolve_app_data_root

EMBEDDING_MODEL_ID = "BAAI/bge-small-en-v1.5"
EMBEDDING_ADAPTER_ID = "fastembed"
EMBEDDING_BATCH_SIZE = 256


@dataclass(frozen=True)
class EmbeddingHealth:
    """Renderer-safe state for one embedding adapter."""

    status: str
    adapter_id: str
    model_id: str
    model_fingerprint: str | None
    dimension: int | None
    model_loaded: bool
    model_load_ms: float | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "adapter_id": self.adapter_id,
            "model_id": self.model_id,
            "model_fingerprint": self.model_fingerprint,
            "dimension": self.dimension,
            "model_loaded": self.model_loaded,
            "model_load_ms": (
                round(self.model_load_ms, 3) if self.model_load_ms is not None else None
            ),
            "error_code": self.error_code,
        }


class EmbeddingAdapter:
    """Small adapter contract so retrieval never depends on a provider SDK."""

    adapter_id: str
    model_id: str

    @property
    def dimension(self) -> int | None:
        raise NotImplementedError

    @property
    def model_fingerprint(self) -> str | None:
        raise NotImplementedError

    def health(self) -> EmbeddingHealth:
        raise NotImplementedError

    def embed_documents(
        self,
        texts: Iterable[str],
        *,
        batch_size: int = EMBEDDING_BATCH_SIZE,
    ) -> Iterator[np.ndarray[Any, Any]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> np.ndarray[Any, Any]:
        raise NotImplementedError

    def close(self) -> None:
        """Release optional model/runtime state."""


def embedding_model_cache_dir(data_root: str | Path | None = None) -> Path:
    """Return the shared model cache, never a project-owned directory."""
    return resolve_app_data_root(data_root) / "models" / "embeddings"


def normalize_vector(
    vector: Sequence[float] | np.ndarray[Any, Any],
    *,
    dimension: int | None = None,
    error_code: str = "EMBEDDING_MODEL_INVALID",
) -> np.ndarray[Any, Any]:
    """Validate and normalize one vector without allowing float64 persistence."""
    try:
        result = np.asarray(vector, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise CoreDomainError(
            error_code,
            "The embedding adapter returned an invalid vector.",
        ) from exc
    if result.ndim != 1 or (dimension is not None and result.shape[0] != dimension):
        raise CoreDomainError(
            "EMBEDDING_DIMENSION_MISMATCH" if dimension is not None else error_code,
            "The embedding vector dimension is invalid.",
            details={"expected_dimension": dimension} if dimension is not None else {},
        )
    if result.shape[0] == 0 or not np.isfinite(result).all():
        raise CoreDomainError(error_code, "The embedding adapter returned a non-finite vector.")
    norm = float(np.linalg.norm(result))
    if not np.isfinite(norm) or norm <= 0.0:
        raise CoreDomainError(error_code, "The embedding adapter returned a zero vector.")
    normalized = result / np.float32(norm)
    return np.ascontiguousarray(normalized, dtype=np.float32)


def fingerprint_model_artifact(model_directory: Path, cache_root: Path) -> str:
    """Hash all local model files in stable order, including relative names."""
    try:
        resolved_root = cache_root.resolve(strict=True)
        if model_directory.is_symlink():
            raise CoreDomainError(
                "EMBEDDING_MODEL_INVALID",
                "The local embedding model directory is not safe.",
            )
        resolved_directory = model_directory.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise CoreDomainError(
            "EMBEDDING_MODEL_UNAVAILABLE",
            "The local embedding model files are unavailable.",
        ) from exc
    if not resolved_directory.is_dir() or not resolved_directory.is_relative_to(resolved_root):
        raise CoreDomainError(
            "EMBEDDING_MODEL_INVALID",
            "The local embedding model directory is not inside the model cache.",
        )

    files: list[Path] = []
    try:
        for path in resolved_directory.rglob("*"):
            if path.is_symlink():
                raise CoreDomainError(
                    "EMBEDDING_MODEL_INVALID",
                    "The local embedding model contains an unsafe link.",
                )
            if path.is_file():
                files.append(path)
    except OSError as exc:
        raise CoreDomainError(
            "EMBEDDING_MODEL_UNAVAILABLE",
            "The local embedding model files are unavailable.",
        ) from exc
    if not files:
        raise CoreDomainError(
            "EMBEDDING_MODEL_INVALID",
            "The local embedding model contains no files.",
        )

    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(resolved_directory).as_posix()):
        relative = path.relative_to(resolved_directory).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        try:
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
        except OSError as exc:
            raise CoreDomainError(
                "EMBEDDING_MODEL_UNAVAILABLE",
                "The local embedding model files are unavailable.",
            ) from exc
    return digest.hexdigest()


class FastEmbedAdapter(EmbeddingAdapter):
    """CPU/ONNX FastEmbed adapter with explicit local-only normal operation."""

    adapter_id = EMBEDDING_ADAPTER_ID
    model_id = EMBEDDING_MODEL_ID

    def __init__(
        self,
        *,
        cache_dir: str | Path | None = None,
        local_files_only: bool = True,
        threads: int | None = None,
    ) -> None:
        self._cache_dir = Path(cache_dir or embedding_model_cache_dir()).expanduser().resolve()
        self._local_files_only = local_files_only
        self._threads = threads
        self._model: Any | None = None
        self._dimension: int | None = None
        self._model_fingerprint: str | None = None
        self._model_load_ms: float | None = None
        self._error: CoreDomainError | None = None

    @property
    def dimension(self) -> int | None:
        return self._dimension

    @property
    def model_fingerprint(self) -> str | None:
        return self._model_fingerprint

    @property
    def model_load_ms(self) -> float | None:
        return self._model_load_ms

    def health(self) -> EmbeddingHealth:
        try:
            self._ensure_model()
        except CoreDomainError as error:
            return EmbeddingHealth(
                status="unavailable",
                adapter_id=self.adapter_id,
                model_id=self.model_id,
                model_fingerprint=self._model_fingerprint,
                dimension=self._dimension,
                model_loaded=False,
                model_load_ms=self._model_load_ms,
                error_code=error.code,
            )
        return EmbeddingHealth(
            status="ready",
            adapter_id=self.adapter_id,
            model_id=self.model_id,
            model_fingerprint=self._model_fingerprint,
            dimension=self._dimension,
            model_loaded=True,
            model_load_ms=self._model_load_ms,
        )

    def embed_documents(
        self,
        texts: Iterable[str],
        *,
        batch_size: int = EMBEDDING_BATCH_SIZE,
    ) -> Iterator[np.ndarray[Any, Any]]:
        model = self._ensure_model()
        try:
            for vector in model.embed(texts, batch_size=batch_size, parallel=None):
                yield normalize_vector(vector, dimension=self._dimension)
        except CoreDomainError:
            raise
        except Exception as exc:
            raise CoreDomainError(
                "EMBEDDING_MODEL_INVALID",
                "The local embedding model could not encode the source text.",
            ) from exc

    def embed_query(self, text: str) -> np.ndarray[Any, Any]:
        model = self._ensure_model()
        try:
            vector = next(iter(model.query_embed(text)))
        except StopIteration as exc:
            raise CoreDomainError(
                "EMBEDDING_MODEL_INVALID",
                "The local embedding model returned no query vector.",
            ) from exc
        except CoreDomainError:
            raise
        except Exception as exc:
            raise CoreDomainError(
                "EMBEDDING_MODEL_INVALID",
                "The local embedding model could not encode the query.",
            ) from exc
        return normalize_vector(
            vector,
            dimension=self._dimension,
            error_code="RETRIEVAL_QUERY_INVALID",
        )

    def prepare(self) -> EmbeddingHealth:
        """Explicitly resolve/load the model; callers choose whether network is allowed."""
        return self.health()

    def close(self) -> None:
        self._model = None

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        if self._error is not None:
            raise self._error

        started = __import__("time").perf_counter()
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            # Import lazily so deterministic CI tests do not initialize any
            # model runtime merely by constructing CoreService.
            from fastembed import TextEmbedding

            model = TextEmbedding(
                model_name=self.model_id,
                cache_dir=str(self._cache_dir),
                threads=self._threads,
                providers=["CPUExecutionProvider"],
                cuda=False,
                lazy_load=False,
                local_files_only=self._local_files_only,
            )
            model_directory = getattr(getattr(model, "model", None), "_model_dir", None)
            if not isinstance(model_directory, (str, os.PathLike)):
                raise CoreDomainError(
                    "EMBEDDING_MODEL_INVALID",
                    "The local embedding model did not expose an artifact directory.",
                )
            self._dimension = int(model.embedding_size)
            self._model_fingerprint = fingerprint_model_artifact(
                Path(model_directory), self._cache_dir
            )
            if self._dimension <= 0:
                raise CoreDomainError(
                    "EMBEDDING_MODEL_INVALID",
                    "The local embedding model reported an invalid dimension.",
                )
            self._model = model
            self._model_load_ms = (__import__("time").perf_counter() - started) * 1000
            return model
        except CoreDomainError as error:
            self._error = error
            raise
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            model_error = CoreDomainError(
                "EMBEDDING_MODEL_UNAVAILABLE",
                "The local embedding model is not available in the model cache.",
                retryable=False,
                details={},
            )
            self._error = model_error
            raise model_error from exc


class DeterministicEmbeddingAdapter(EmbeddingAdapter):
    """Injectable, offline adapter for exact semantic-ranking tests."""

    adapter_id = "deterministic-test"

    def __init__(
        self,
        dimension: int = 8,
        vectors: Mapping[str, Sequence[float]] | None = None,
        *,
        query_vectors: Mapping[str, Sequence[float]] | None = None,
        model_id: str = "deterministic-test-v1",
        model_fingerprint: str | None = None,
        vector_resolver: Callable[[str], Sequence[float] | None] | None = None,
    ) -> None:
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
            raise ValueError("dimension must be a positive integer")
        self.model_id = model_id
        self._dimension = dimension
        self._vectors: dict[str, np.ndarray[Any, Any]] = {}
        self._query_vectors: dict[str, np.ndarray[Any, Any]] = {}
        self._vector_resolver = vector_resolver
        self._model_fingerprint = (
            model_fingerprint
            or hashlib.sha256(f"{self.adapter_id}:{model_id}:{dimension}".encode()).hexdigest()
        )
        self.document_call_count = 0
        self.query_call_count = 0
        self.embedded_texts: list[str] = []
        for text, vector in (vectors or {}).items():
            self.set_vector(text, vector)
        for text, vector in (query_vectors or {}).items():
            self.set_query_vector(text, vector)

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_fingerprint(self) -> str:
        return self._model_fingerprint

    def health(self) -> EmbeddingHealth:
        return EmbeddingHealth(
            status="ready",
            adapter_id=self.adapter_id,
            model_id=self.model_id,
            model_fingerprint=self.model_fingerprint,
            dimension=self.dimension,
            model_loaded=True,
        )

    def embed_documents(
        self,
        texts: Iterable[str],
        *,
        batch_size: int = EMBEDDING_BATCH_SIZE,
    ) -> Iterator[np.ndarray[Any, Any]]:
        del batch_size
        for text in texts:
            self.document_call_count += 1
            self.embedded_texts.append(text)
            yield self._vector_for(text)

    def embed_query(self, text: str) -> np.ndarray[Any, Any]:
        self.query_call_count += 1
        vector: Sequence[float] | np.ndarray[Any, Any] | None = self._query_vectors.get(text)
        if vector is None:
            vector = self._vectors.get(text)
        if vector is None:
            vector = self._vector_resolver(text) if self._vector_resolver is not None else None
        if vector is None:
            vector = self._hashed_vector(text)
        return normalize_vector(
            vector,
            dimension=self.dimension,
            error_code="RETRIEVAL_QUERY_INVALID",
        )

    def set_vector(self, text: str, vector: Sequence[float]) -> None:
        self._vectors[text] = normalize_vector(vector, dimension=self.dimension)

    def set_query_vector(self, text: str, vector: Sequence[float]) -> None:
        self._query_vectors[text] = normalize_vector(vector, dimension=self.dimension)

    def close(self) -> None:
        return None

    def _vector_for(self, text: str) -> np.ndarray[Any, Any]:
        vector: Sequence[float] | np.ndarray[Any, Any] | None = self._vectors.get(text)
        if vector is None:
            vector = self._vector_resolver(text) if self._vector_resolver is not None else None
        if vector is not None:
            return normalize_vector(vector, dimension=self.dimension)
        return self._hashed_vector(text)

    def _hashed_vector(self, text: str) -> np.ndarray[Any, Any]:
        result = np.zeros(self.dimension, dtype=np.float32)
        tokens = lexical_normalize(text).split() or [text]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            result[index] += np.float32(sign)
        return normalize_vector(result, dimension=self.dimension)
