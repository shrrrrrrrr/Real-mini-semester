"""Prompt 模板与 LLM 输出契约（Pydantic）。

三层内容（开发文档 §5.2 技术点①）：
- QA：双层答案（doc 分区带 [n] 引用 / general 分区通识）；
- 讲解大纲：章节树，节点可挂资料片段；
- 测验题目：仅基于资料出题，解析必须含依据。
"""

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 双层问答
# ---------------------------------------------------------------------------

QA_SYSTEM = """你是"航友"的课程学习助教。你的回答必须严格遵守"双层答案"契约。

【输出格式】输出一个 JSON 对象：{"segments": [{"layer": "doc", "text": "..."}, {"layer": "general", "text": "..."}]}

【分层规则】
1. layer="doc" 的分段：回答"资料内"的部分。
   - 只能依据下方给出的【课程资料片段】作答，禁止使用片段之外的知识；
   - 每一处依据必须在句末标注片段编号，如 [1]、[2][3]；
   - 资料片段与你的通用知识冲突时，以资料为准，并在 doc 分段末尾追加一句"注：本资料与通用教材在此处的表述存在差异，已按资料回答"；
   - 若资料片段完全无法回答问题：doc 分段输出"资料中未找到相关内容。"，此时不要编造引用。
2. layer="general" 的分段：回答"资料外补充"的部分。
   - 使用你的通用学科知识补充资料未覆盖的内容（更深入的原理、背景、例子、易错点）；
   - 这是默认应有的分层——除非资料已经完整回答了问题，否则都应给出 general 分段；
   - 不得在 general 分段里使用 [n] 引用标记，不得声称内容来自资料。
3. 两个分段都应自然、连贯、成段地书写；分段数量 1-3 个（可以只有 doc 或只有 general，但通常两者都有）。
4. 使用与用户提问相同的语言回答。"""

# 仅资料模式：不出通识层（考前"只要课件口径"场景）
QA_SYSTEM_DOCS_ONLY = """你是"航友"的课程资料助教，当前处于"仅资料"严格模式。

【输出格式】输出一个 JSON 对象：{"segments": [{"layer": "doc", "text": "..."}]}

【严格规则】
1. 只能依据下方给出的【课程资料片段】作答，严禁使用任何片段之外的知识；
2. 每处依据在句末标注片段编号，如 [1]、[2][3]；
3. segments 只包含 layer="doc" 的分段，禁止出现 general 分段；
4. 若资料片段无法回答问题：只输出"资料中未找到相关内容。"，不得编造或补充课外知识；
5. 使用与用户提问相同的语言回答。"""

QA_USER_TMPL = """【课程资料片段】
{context}

【对话历史】
{history}

【用户问题】
{question}"""


class AnswerSegment(BaseModel):
    """双层答案的一个分段——LLM 必须按此契约输出。"""

    layer: Literal["doc", "general"]  # 枚举约束，杜绝第三种标签
    text: str = Field(min_length=1)


class AnswerSpec(BaseModel):
    """问答输出的整体契约。"""

    segments: list[AnswerSegment] = Field(min_length=1, max_length=6)


# ---------------------------------------------------------------------------
# 讲解模式
# ---------------------------------------------------------------------------

EXPLAIN_SYSTEM = """你是"航友"的课程讲解助手。用户给出一个书名、学科名或章节名，你需要生成结构化讲解大纲。

【输出格式】
{"sections": [{"title": "章节标题", "nodes": [{"title": "知识点标题", "summary": "一句话内容概述（不超过60字）", "linked_hint": "该知识点可能对应资料中的什么内容（如：红黑树的定义与性质，可能出现在'查找'相关章节）"}]}]}

【要求】
1. 大纲 4-8 个 section，每个 section 2-5 个 node；
2. 按学科知识体系的合理学习顺序组织，从基础到进阶；
3. summary 用一句话概括该知识点讲什么，供用户决定是否展开；
4. linked_hint 描述该知识点与课程资料的潜在对应关系（不要求精确，用于后续自动挂接资料片段）；
5. 使用与用户输入相同的语言。"""

EXPLAIN_USER_TMPL = """【课程名】{course_name}
【已上传的资料清单】
{doc_list}

【要讲解的主题】{topic}"""


class ExplainNode(BaseModel):
    title: str
    summary: str = ""
    linked_hint: str = ""


class ExplainSection(BaseModel):
    title: str
    nodes: list[ExplainNode] = Field(min_length=1)


class ExplainSpec(BaseModel):
    sections: list[ExplainSection] = Field(min_length=1, max_length=12)


# ---------------------------------------------------------------------------
# 测验生成
# ---------------------------------------------------------------------------

QUIZ_SYSTEM = """你是"航友"的出题助手。基于给出的课程资料片段出一组单选题，检验学生对资料内容的掌握。

【输出格式】
{"questions": [{"stem": "题干", "options": ["A选项", "B选项", "C选项", "D选项"], "answer": "A"|"B"|"C"|"D", "explanation": "解析", "difficulty": "基础"|"进阶"|"挑战"}]}

【出题规则】
1. 题干和正确答案必须来自资料片段的内容，不得出资料外的知识；
2. options 必须恰好 4 项；answer 是正确选项的字母；干扰项要有迷惑性但不能也对；
3. explanation 必须解释为什么正确、其他项为什么错，并指明依据资料片段的哪部分内容；
4. difficulty 分配大致均匀（基础约一半，进阶和挑战合计一半）；
5. 使用与资料相同的语言出题。"""

QUIZ_USER_TMPL = """【课程资料片段】
{context}

【出题要求】共 {count} 道题，覆盖片段中的核心知识点。"""


class QuizQuestionSpec(BaseModel):
    """单道测验题的输出契约。"""

    stem: str = Field(min_length=8)
    options: list[str] = Field(min_length=4, max_length=4)  # 恰好 4 项
    answer: Literal["A", "B", "C", "D"]  # 枚举约束
    explanation: str = Field(min_length=10)
    difficulty: Literal["基础", "进阶", "挑战"]


class QuizSpec(BaseModel):
    """一次测验的整体契约。"""

    questions: list[QuizQuestionSpec] = Field(min_length=1)


def build_context(chunks: list, doc_names: dict[str, str] | None = None) -> str:
    """把检索结果组装为带编号的上下文文本（编号即 [n] 引用编号）。

    兼容两种输入：
    - RetrievedChunk（检索管线产物，自带 filename/locator 字段）；
    - ORM Chunk（document_id 通过 doc_names 映射显示名）。
    """
    names = doc_names or {}
    lines = []
    for i, c in enumerate(chunks, start=1):
        filename = getattr(c, "filename", None)
        if filename is None:  # ORM Chunk：查映射表（文件名或书名）
            filename = names.get(c.document_id, "资料")
        locator = getattr(c, "locator_value", None) or getattr(c, "locator", "")
        content = c.content
        lines.append(f"[{i}] 《{filename}》{locator}\n{content}")
    return "\n\n".join(lines)


def build_history(messages: list) -> str:
    """把近期对话历史组装为文本（多轮上下文）。"""
    if not messages:
        return "（无）"
    lines = []
    for m in messages[-6:]:  # 最近 3 轮（user+assistant）
        role = "用户" if m.role == "user" else "助教"
        lines.append(f"{role}: {m.content[:300]}")
    return "\n".join(lines)
