"""NumPy memory-mapped vector index primitives for the M2 corpus size."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np

from presenter_core.errors import CoreDomainError

from .embeddings import normalize_vector


@dataclass(frozen=True)
class MatrixShape:
    rows: int
    dimension: int


class RetrievalIndex:
    """Conceptual index protocol implemented by the NumPy project index."""

    def index(self, items: Any) -> Any:
        raise NotImplementedError

    def delete(self, entity_ids: Any) -> Any:
        raise NotImplementedError

    def query(self, query_vector: Any, *, limit: int) -> Any:
        raise NotImplementedError

    def rebuild(self) -> Any:
        raise NotImplementedError

    def health(self) -> Any:
        raise NotImplementedError


class NumpyEmbeddingIndex(RetrievalIndex):
    """Validate and search a project-local float32 `.npy` matrix."""

    def index(self, items: Any) -> Any:
        raise NotImplementedError("Generation persistence is owned by HybridRetrievalService")

    def delete(self, entity_ids: Any) -> Any:
        raise NotImplementedError("Generation persistence is owned by HybridRetrievalService")

    def rebuild(self) -> Any:
        raise NotImplementedError("Generation persistence is owned by HybridRetrievalService")

    def health(self) -> Any:
        raise NotImplementedError("Generation health is owned by HybridRetrievalService")

    @staticmethod
    def create_staging_matrix(
        path: str | Path,
        *,
        rows: int,
        dimension: int,
    ) -> np.memmap | np.ndarray[Any, Any]:
        """Allocate a float32 `.npy` matrix, including the empty-index case."""
        if rows < 0 or dimension <= 0:
            raise ValueError("matrix shape must be non-negative by positive")
        matrix_path = Path(path)
        matrix_path.parent.mkdir(parents=True, exist_ok=True)
        if rows == 0:
            np.save(matrix_path, np.empty((0, dimension), dtype=np.float32), allow_pickle=False)
            return np.empty((0, dimension), dtype=np.float32)
        return cast(
            np.memmap,
            np.lib.format.open_memmap(
                matrix_path,
                mode="w+",
                dtype=np.float32,
                shape=(rows, dimension),
            ),  # type: ignore[no-untyped-call]
        )

    @staticmethod
    def flush_and_fsync(matrix: np.memmap | np.ndarray[Any, Any], path: str | Path) -> None:
        """Flush the memory map and durable-file boundary before activation."""
        if isinstance(matrix, np.memmap):
            matrix.flush()
            mmap_handle = getattr(matrix, "_mmap", None)
            if mmap_handle is not None:
                mmap_handle.close()
        try:
            with Path(path).open("r+b") as handle:
                os.fsync(handle.fileno())
        except OSError as exc:
            raise CoreDomainError(
                "RETRIEVAL_REBUILD_FAILED",
                "The embedding matrix could not be flushed to disk.",
            ) from exc

    @staticmethod
    def load_matrix(
        path: str | Path,
        *,
        expected_rows: int,
        expected_dimension: int,
    ) -> np.ndarray[Any, Any]:
        """Load and validate one active matrix without allowing object arrays."""
        try:
            matrix = np.load(
                Path(path),
                mmap_mode="r",
                allow_pickle=False,
                max_header_size=10_000,
            )
        except (
            OSError,
            ValueError,
            EOFError,
            TypeError,
            RuntimeError,
            IndexError,
            OverflowError,
        ) as exc:
            raise CoreDomainError(
                "RETRIEVAL_INDEX_CORRUPT",
                "The active embedding matrix is corrupt or unreadable.",
            ) from exc
        if not isinstance(matrix, np.ndarray) or matrix.dtype != np.dtype(np.float32):
            raise CoreDomainError(
                "RETRIEVAL_INDEX_CORRUPT",
                "The active embedding matrix has an unexpected data type.",
            )
        if (
            matrix.ndim != 2
            or matrix.shape[0] != expected_rows
            or matrix.shape[1] != expected_dimension
        ):
            raise CoreDomainError(
                "RETRIEVAL_INDEX_CORRUPT",
                "The active embedding matrix shape does not match its metadata.",
            )
        if not np.isfinite(matrix).all():
            raise CoreDomainError(
                "RETRIEVAL_INDEX_CORRUPT",
                "The active embedding matrix contains non-finite values.",
            )
        if matrix.shape[0]:
            norms = np.linalg.norm(matrix, axis=1)
            if (
                not np.isfinite(norms).all()
                or np.any(norms <= np.float32(0.0))
                or np.any(np.abs(norms - np.float32(1.0)) > np.float32(1e-3))
            ):
                raise CoreDomainError(
                    "RETRIEVAL_INDEX_CORRUPT",
                    "The active embedding matrix contains invalid normalized vectors.",
                )
        return matrix

    @staticmethod
    def cosine_search(
        matrix: np.ndarray[Any, Any],
        query_vector: np.ndarray[Any, Any],
        *,
        eligible_rows: np.ndarray[Any, Any] | None,
        limit: int,
    ) -> list[tuple[int, float]]:
        """Return bounded, deterministic top rows using one vectorized dot product."""
        if limit < 1:
            return []
        if matrix.ndim != 2 or matrix.dtype != np.dtype(np.float32):
            raise CoreDomainError(
                "RETRIEVAL_INDEX_CORRUPT",
                "The embedding matrix has an unexpected shape or data type.",
            )
        query = normalize_vector(
            query_vector,
            dimension=int(matrix.shape[1]),
            error_code="RETRIEVAL_QUERY_INVALID",
        )
        if matrix.shape[0] == 0:
            return []
        scores = np.asarray(matrix @ query, dtype=np.float32)
        if eligible_rows is not None:
            if np.any(eligible_rows < 0) or np.any(eligible_rows >= matrix.shape[0]):
                raise CoreDomainError(
                    "RETRIEVAL_INDEX_CORRUPT",
                    "The eligible embedding row mapping is out of bounds.",
                )
            allowed = np.zeros(matrix.shape[0], dtype=np.bool_)
            allowed[eligible_rows] = True
            scores[~allowed] = -np.inf
        valid_rows = np.flatnonzero(np.isfinite(scores))
        if valid_rows.size == 0:
            return []
        candidate_count = min(limit, int(valid_rows.size))
        if candidate_count < valid_rows.size:
            partition = np.argpartition(-scores, candidate_count - 1)[:candidate_count]
        else:
            partition = valid_rows
        selected = [int(row) for row in partition if np.isfinite(scores[row])]
        selected.sort(key=lambda row: (-float(scores[row]), row))
        return [(row, float(scores[row])) for row in selected[:limit]]


NumPyEmbeddingIndex = NumpyEmbeddingIndex
