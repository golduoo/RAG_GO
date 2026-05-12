"""评估集数据结构(对齐 docs/rules/data-schemas.md §2)。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


QuestionType = Literal["single_hop", "multi_hop", "yesno", "chat"]


class EvalSample(BaseModel):
    """评估集中的一条样本。"""

    qid: str = Field(..., description="全局唯一")
    question: str
    gold_answer: str
    gold_doc_ids: list[str] = Field(..., description="相关 chunk ID 列表(用于 Recall 计算)")
    question_type: QuestionType = "single_hop"
    metadata: dict = Field(default_factory=dict)
