"""RAG 用的 prompt 模板。后续 Phase 可在此演化(few-shot / CoT / 改写等)。"""

from __future__ import annotations

RAG_SYSTEM = "你是中文知识问答助手,擅长基于给定资料严谨作答,不臆造。"

RAG_USER_TEMPLATE = """请基于下面的资料回答问题。

资料:
{context}

问题:{query}

要求:
- 仅根据资料作答,不要编造
- 引用资料时用 [1][2] 标注,与资料编号对应
- 资料中找不到答案时,明确说明"知识库中未找到相关信息"
"""


def format_context(passages: list[str]) -> str:
    """把检索结果格式化为 [1] ... [2] ... 形式。"""
    if not passages:
        return "(无)"
    lines = [f"[{i}] {p}" for i, p in enumerate(passages, start=1)]
    return "\n".join(lines)


def build_rag_messages(query: str, passages: list[str]) -> list[dict]:
    """组装 OpenAI Chat Completions 风格的 messages。"""
    return [
        {"role": "system", "content": RAG_SYSTEM},
        {
            "role": "user",
            "content": RAG_USER_TEMPLATE.format(
                context=format_context(passages),
                query=query,
            ),
        },
    ]
