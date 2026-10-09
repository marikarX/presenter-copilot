from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from presenter_core.tools import embedding_acceptance

REPOSITORY_ROOT = Path(__file__).parents[2]


def test_fixture_generator_preserves_real_retrieval_goldens(tmp_path: Path) -> None:
    generator_path = REPOSITORY_ROOT / "samples" / "synthetic-deck" / "generate_fixture.py"
    spec = importlib.util.spec_from_file_location("synthetic_deck_generator", generator_path)
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)

    generated = tmp_path / "retrieval-goldens.json"
    generator.generate_expected(generated)
    checked_in = (
        REPOSITORY_ROOT / "samples" / "synthetic-deck" / "expected" / "retrieval-goldens.json"
    )

    assert json.loads(generated.read_text(encoding="utf-8")) == json.loads(
        checked_in.read_text(encoding="utf-8")
    )
    assert len(embedding_acceptance._acceptance_cases()) == 7


def test_embedding_acceptance_fails_closed_without_goldens(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unexpected_adapter(*args: object, **kwargs: object) -> None:
        raise AssertionError("acceptance must validate its cases before loading the model")

    monkeypatch.setattr(embedding_acceptance, "_acceptance_cases", lambda: [])
    monkeypatch.setattr(embedding_acceptance, "FastEmbedAdapter", unexpected_adapter)

    assert embedding_acceptance.main([]) == 1
    assert json.loads(capsys.readouterr().err) == {
        "status": "error",
        "code": "RETRIEVAL_ACCEPTANCE_NO_GOLDENS",
        "message": "No semantic or hybrid retrieval acceptance cases are configured.",
    }
