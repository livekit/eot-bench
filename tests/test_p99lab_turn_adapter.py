from __future__ import annotations

import numpy as np
import pytest

from eot_harness import p99lab_turn_adapter
from eot_harness.p99lab_turn_adapter import P99LabTurn1Adapter, P99LabTurn1MiniAdapter


class _FakeTurn1:
    def __init__(self) -> None:
        self.calls = []

    def score_windows(self, windows, contexts):
        self.calls.append((windows, contexts))
        return [len(window) / 100.0 for window in windows]


class _FakeTurn1Mini:
    def __init__(self) -> None:
        self.calls = []

    def score(self, audio):
        self.calls.append(audio)
        return 0.25


@pytest.fixture
def turn1(monkeypatch):
    fake = _FakeTurn1()
    monkeypatch.setattr(p99lab_turn_adapter, "_load_turn1", lambda **_: fake)
    return fake


@pytest.fixture
def turn1_mini(monkeypatch):
    fake = _FakeTurn1Mini()
    monkeypatch.setattr(p99lab_turn_adapter, "_load_turn1_mini", lambda **_: fake)
    return fake


def _item(n, messages=None, channels=1, sample_rate=16_000):
    array = np.ones((n, channels), dtype=np.float32) if channels > 1 else np.ones(n, dtype=np.float32)
    return {"audio": {"array": array, "sampling_rate": sample_rate}, "messages": messages or []}


def test_turn1_reads_only_the_last_assistant_message(turn1) -> None:
    adapter = P99LabTurn1Adapter()
    assert adapter.display_name == "p99lab turn-1"
    assert adapter.adapter_id == "p99lab/turn-1"
    assert adapter.max_audio_sec == 8.0
    assert getattr(adapter, "score_point", None) is None

    messages = [
        {"role": "assistant", "content": "First question"},
        {"role": "user", "content": "an earlier answer"},
        {"role": "assistant", "content": "What is your phone number?"},
        # Current-turn words appended by the harness: the model must not get them.
        {"role": "user", "content": "five five five"},
    ]
    scores = adapter.predict_batch([_item(10, messages), _item(20), _item(30, channels=2)])

    assert scores == pytest.approx([0.1, 0.2, 0.3])
    assert len(turn1.calls) == 1
    windows, contexts = turn1.calls[0]
    assert contexts == ["What is your phone number?", "", ""]
    assert [window.ndim for window in windows] == [1, 1, 1]
    assert all(window.dtype == np.float32 for window in windows)
    assert adapter.predict_batch([]) == []


def test_turn1_mini_is_audio_only_and_scores_each_prefix_alone(turn1_mini) -> None:
    adapter = P99LabTurn1MiniAdapter(revision="abc123")
    assert adapter.display_name == "p99lab turn-1-mini"
    assert adapter.adapter_id == "p99lab/turn-1-mini-abc123"
    assert adapter.max_audio_sec == 40.0
    assert getattr(adapter, "score_point", None) is None

    scores = adapter.predict_batch(
        [_item(320, [{"role": "assistant", "content": "ignored"}]), _item(640, channels=2)],
    )

    assert scores == [0.25, 0.25]
    assert [call.shape for call in turn1_mini.calls] == [(320,), (640,)]


def test_adapters_declare_english_only(turn1, turn1_mini) -> None:
    for adapter in (P99LabTurn1Adapter(), P99LabTurn1MiniAdapter()):
        assert adapter.supports_language("en")
        assert adapter.supports_language(" EN ")
        assert not adapter.supports_language("de")


def test_other_sample_rates_are_resampled_to_16k(monkeypatch, turn1_mini) -> None:
    seen = []

    def resample(array, *, sample_rate):
        seen.append((len(array), sample_rate))
        return np.zeros(len(array) * 2, dtype=np.float32)

    monkeypatch.setattr(p99lab_turn_adapter, "_resample_audio", resample)
    adapter = P99LabTurn1MiniAdapter()
    adapter.predict_batch([_item(800, sample_rate=8_000)])

    assert seen == [(800, 8_000)]
    assert turn1_mini.calls[0].shape == (1600,)
