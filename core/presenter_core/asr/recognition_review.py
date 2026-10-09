"""Bounded ephemeral observations, without inferred recognition accuracy."""

import math
from typing import Any

MAX_REVIEW_CHUNKS = 64


def recognition_review(parts: list[str], scores: list[float | None]) -> dict[str, Any]:
    if len(parts) != len(scores):
        raise ValueError("Recognition review must match the original final phrases.")
    normalized = [
        float(score)
        if not isinstance(score, bool)
        and isinstance(score, (int, float))
        and 0 <= score <= 1
        and math.isfinite(score)
        else None
        for score in scores
    ]
    return {
        "version": 1,
        "chunk_count": len(parts),
        "unavailable_count": sum(score is None for score in normalized),
        "truncated": len(parts) > MAX_REVIEW_CHUNKS,
        "chunks": [
            {"text": text, "adapter_score": score}
            for text, score in zip(
                parts[:MAX_REVIEW_CHUNKS], normalized[:MAX_REVIEW_CHUNKS], strict=True
            )
        ],
    }
