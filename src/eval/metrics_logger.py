"""把评估结果以追加方式写入 docs/metrics.md(格式对齐 testing.md §4)。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

DEFAULT_METRICS_PATH = Path("docs/metrics.md")


def _format_config(config: dict) -> str:
    lines = []
    for k, v in config.items():
        lines.append(f"- {k}: `{v}`")
    return "\n".join(lines)


def _format_metrics_table(metrics: dict[str, float], baseline: dict | None = None) -> str:
    header = "| Metric | Value | Δ vs baseline |\n|--------|-------|---------------|"
    rows = []
    for name, val in metrics.items():
        if baseline and name in baseline:
            delta = val - baseline[name]
            delta_str = f"{delta:+.4f}"
        else:
            delta_str = "-"
        rows.append(f"| {name} | {val:.4f} | {delta_str} |")
    return header + "\n" + "\n".join(rows)


def append_phase_report(
    phase: int | str,
    title: str,
    config: dict,
    metrics: dict[str, float],
    notes: str = "",
    baseline: dict[str, float] | None = None,
    path: Path = DEFAULT_METRICS_PATH,
    today: str | None = None,
) -> Path:
    """追加一份 phase 报告到 metrics.md 末尾。

    Args:
        phase: 阶段编号(int 或 字符串)
        title: 简短主题,如 "Dense Baseline"
        config: 配置字典(Embedding / Retriever / Reranker / LLM / Eval set 等)
        metrics: 指标字典,例 {"Recall@3": 0.62, "MRR": 0.55}
        notes: 备注(可多行),建议写一两句关键发现
        baseline: 对比基线指标(可选,用于自动计算 Δ)
        path: 输出文件,默认 docs/metrics.md
        today: 日期字符串,默认今天

    Returns:
        被写入的文件路径。
    """
    day = today or date.today().isoformat()
    block = [
        "",
        f"## Phase {phase} - {title} - {day}",
        "",
        "**配置**:",
        "",
        _format_config(config),
        "",
        "**主指标**:",
        "",
        _format_metrics_table(metrics, baseline),
        "",
    ]
    if notes:
        block.extend(["**备注**:", "", notes, ""])
    block.append("")  # trailing newline

    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("# Metrics\n\n<!-- 评估结果从下面开始追加 -->\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(block))
    return path
