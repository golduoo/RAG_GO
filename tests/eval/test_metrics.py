"""metrics.py 单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.eval.metrics import (
    evaluate_batch,
    hit_at_k,
    recall_at_k,
    reciprocal_rank,
)
from src.eval.metrics_logger import append_phase_report


# ---------------------------------------------------------------------------
# hit_at_k
# ---------------------------------------------------------------------------


class TestHitAtK:
    def test_hit_normal(self):
        assert hit_at_k(["a", "b", "c"], ["b"], k=3) == 1.0
        assert hit_at_k(["a", "b", "c"], ["x"], k=3) == 0.0

    def test_hit_k_limits_window(self):
        # gold 在第 3 位,k=2 看不到
        assert hit_at_k(["a", "b", "c"], ["c"], k=2) == 0.0
        assert hit_at_k(["a", "b", "c"], ["c"], k=3) == 1.0

    def test_empty_gold(self):
        assert hit_at_k(["a", "b"], [], k=3) == 0.0

    def test_zero_k(self):
        assert hit_at_k(["a", "b"], ["a"], k=0) == 0.0


# ---------------------------------------------------------------------------
# recall_at_k
# ---------------------------------------------------------------------------


class TestRecallAtK:
    def test_recall_partial(self):
        # gold 2 个,top-3 命中 1 个 -> 0.5
        assert recall_at_k(["a", "b", "c"], ["b", "x"], k=3) == 0.5

    def test_recall_full(self):
        assert recall_at_k(["a", "b", "c"], ["a", "b"], k=3) == 1.0

    def test_recall_zero(self):
        assert recall_at_k(["a", "b"], ["c"], k=2) == 0.0


# ---------------------------------------------------------------------------
# reciprocal_rank
# ---------------------------------------------------------------------------


class TestReciprocalRank:
    def test_first_position(self):
        assert reciprocal_rank(["a", "b"], ["a"]) == 1.0

    def test_third_position(self):
        # gold 在第 3 位 -> 1/3
        assert reciprocal_rank(["a", "b", "c"], ["c"]) == pytest.approx(1 / 3)

    def test_no_hit(self):
        assert reciprocal_rank(["a", "b"], ["x"]) == 0.0

    def test_empty_gold(self):
        assert reciprocal_rank(["a", "b"], []) == 0.0


# ---------------------------------------------------------------------------
# evaluate_batch
# ---------------------------------------------------------------------------


class TestEvaluateBatch:
    def test_empty(self):
        assert evaluate_batch([]) == {}

    def test_simple_batch(self):
        pairs = [
            (["a", "b", "c"], ["a"]),
            (["x", "y", "a"], ["a"]),
            (["m", "n", "o"], ["a"]),
        ]
        m = evaluate_batch(pairs, ks=(3,))
        # Hit@3: 1 + 1 + 0 = 2/3
        assert m["Hit@3"] == pytest.approx(2 / 3)
        # Recall@3: 1 + 1 + 0 = 2/3
        assert m["Recall@3"] == pytest.approx(2 / 3)
        # MRR: 1 + 1/3 + 0 = 4/9
        assert m["MRR"] == pytest.approx(4 / 9)


# ---------------------------------------------------------------------------
# metrics_logger
# ---------------------------------------------------------------------------


class TestMetricsLogger:
    def test_append_phase_report_creates_file(self, tmp_path: Path):
        path = tmp_path / "metrics.md"
        out = append_phase_report(
            phase=1,
            title="Test",
            config={"Embedding": "bge-m3"},
            metrics={"Recall@3": 0.62, "MRR": 0.55},
            notes="hello",
            path=path,
            today="2026-05-13",
        )
        text = out.read_text(encoding="utf-8")
        assert "Phase 1 - Test - 2026-05-13" in text
        assert "Recall@3" in text
        assert "0.6200" in text
        assert "bge-m3" in text
        assert "hello" in text

    def test_append_appends_not_overwrites(self, tmp_path: Path):
        path = tmp_path / "metrics.md"
        append_phase_report(1, "A", {}, {"x": 0.1}, path=path, today="2026-05-13")
        append_phase_report(2, "B", {}, {"x": 0.2}, path=path, today="2026-05-14")
        text = path.read_text(encoding="utf-8")
        assert "Phase 1 - A" in text and "Phase 2 - B" in text

    def test_baseline_delta(self, tmp_path: Path):
        path = tmp_path / "metrics.md"
        append_phase_report(
            phase=2,
            title="Hybrid",
            config={},
            metrics={"Recall@3": 0.78},
            baseline={"Recall@3": 0.62},
            path=path,
            today="2026-05-20",
        )
        text = path.read_text(encoding="utf-8")
        assert "+0.1600" in text
