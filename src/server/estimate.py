# -*- coding: utf-8 -*-
"""
estimate.py — Token 预估纯逻辑（从原 app_utils 平移，无任何 UI 依赖）。

包含 Agent 元数据、ASIL 基准、各 Agent Token 默认值与分段/审查开销，
以及单 Agent 与批量的 Token 消耗综合预估函数。
"""

from llm_engine import estimate_tokens
from safety_knowledge import get_safety_knowledge, get_asil_decomposition_guidance


# ======================================================================
# 常量
# ======================================================================

# ASIL 等级对应的全局基准 token 数
_ASIL_BASE_TOKENS = {
    "QM": 4096,
    "ASIL A": 8192,
    "ASIL B": 8192,
    "ASIL C": 12288,
    "ASIL D": 16384,
}

# 每个 Agent 在 ASIL B 下的推荐 Max Tokens
_AGENT_TOKEN_DEFAULT_B = {
    "SRS": 8192, "SAD": 12288, "FMEA": 16384, "DFA": 16384,
    "SDD": 12288, "TC-UNIT": 12288, "TC-INTEGRATION": 12288,
}

# 每个 Agent Prompt 模板的固定开销（不含代码/前置文档/知识库）
_PROMPT_TEMPLATE_OVERHEAD = {
    "SRS": 2200, "SAD": 2000, "FMEA": 2500, "DFA": 2500,
    "SDD": 2000, "TC-UNIT": 2400, "TC-INTEGRATION": 2200,
}

# 每个 Agent 依赖的前置文档（用于 Token 预估）
_AGENT_PRIOR_DOCS = {
    "SRS": [],
    "SAD": [],
    "FMEA": ["SRS", "SAD"],
    "DFA": ["SAD", "FMEA", "SRS"],
    "SDD": [],
    "TC-UNIT": ["SRS", "SAD", "FMEA", "DFA"],
    "TC-INTEGRATION": ["SRS", "SAD", "FMEA", "DFA"],
}

# 每个 Agent 分段并发时的 chunk 数量（对应 PromptManager.DOC_CHUNKS）
_AGENT_CHUNK_COUNT = {
    "SRS": 3, "SAD": 3, "FMEA": 4, "DFA": 4,
    "SDD": 2, "TC-UNIT": 3, "TC-INTEGRATION": 2,
}

# 分段并发时每个 chunk 的 Prompt 开销（不含代码/前置文档）
_CHUNK_TEMPLATE_OVERHEAD = 800
# 合并审查 Prompt 的额外开销
_MERGE_PROMPT_OVERHEAD = 1000
# 审查修订 Prompt 的额外开销
_REVIEW_PROMPT_OVERHEAD = 1200

# Agent 顺序（批量生成 + 前端展示）
AGENT_ORDER = ["SRS", "SAD", "FMEA", "DFA", "SDD", "TC-UNIT", "TC-INTEGRATION"]

# Agent 元数据（图标 / 名称 / 描述 / 卡片配色）
AGENT_META = {
    "SRS":  {"icon": "📋", "name": "SRS Agent", "full": "软件需求规格说明",
             "desc": "从代码提取功能需求、接口需求、安全需求，生成完整的 SRS 文档",
             "color": "linear-gradient(135deg, #3a4a6b 0%, #4a4068 100%)"},
    "SAD":  {"icon": "🏗️", "name": "SAD Agent", "full": "软件架构设计",
             "desc": "分析模块分解、组件接口、数据流、中断调度，生成架构设计文档",
             "color": "linear-gradient(135deg, #6b4a58 0%, #5a3d50 100%)"},
    "FMEA": {"icon": "⚠️", "name": "FMEA Agent", "full": "失效模式与影响分析",
             "desc": "识别失效模式、评估 RPN、制定缓解措施（自动注入 SRS + SAD 上下文）",
             "color": "linear-gradient(135deg, #3d5a6b 0%, #3a5260 100%)"},
    "DFA":  {"icon": "🔗", "name": "DFA Agent", "full": "相关失效分析",
             "desc": "CCF/级联/单点/FFI 四维分析（自动注入 SAD + FMEA 上下文）",
             "color": "linear-gradient(135deg, #4a3d6b 0%, #3d3560 100%)"},
    "SDD":  {"icon": "📐", "name": "SDD Agent", "full": "软件详细设计",
             "desc": "深入分析函数级设计、数据结构、算法逻辑，生成详细设计文档",
             "color": "linear-gradient(135deg, #3d6b5a 0%, #3a5a50 100%)"},
    "TC-UNIT":   {"icon": "🧪", "name": "TC-UNIT Agent",  "full": "单元测试用例",
             "desc": "针对每个函数设计单元测试，含 Unity/GTest 代码、覆盖矩阵和通过准则",
             "color": "linear-gradient(135deg, #6b5a4a 0%, #5a4a3d 100%)"},
    "TC-INTEGRATION": {"icon": "🔗", "name": "TC-INTEG Agent", "full": "集成测试用例",
             "desc": "验证模块间接口、数据流、控制流、时序与故障注入的集成测试",
             "color": "linear-gradient(135deg, #5a5a3d 0%, #4a4a35 100%)"},
}

# 前置文档注入规则（供生成编排复用）：agent → 需注入的前置文档键（按优先顺序）
AGENT_PRIOR_INJECT = {
    "FMEA": ["SRS", "SAD"],
    "DFA": ["SAD", "FMEA", "SRS"],
    "TC-UNIT": ["SRS", "SAD", "FMEA", "DFA"],
    "TC-INTEGRATION": ["SRS", "SAD", "FMEA", "DFA"],
}


# ======================================================================
# 预估函数
# ======================================================================

def get_agent_token_defaults(asil_level: str) -> dict:
    """根据 ASIL 等级计算各 Agent 推荐 token 数（缩放逻辑统一入口）。"""
    scale = _ASIL_BASE_TOKENS.get(asil_level, 8192) / 8192
    return {
        k: max(1024, int(v * scale / 1024) * 1024)
        for k, v in _AGENT_TOKEN_DEFAULT_B.items()
    }


def estimate_agent_total_tokens(
    agent_type: str,
    code: str,
    asil_level: str = "ASIL B",
    chunked_mode: bool = False,
    review_mode: bool = False,
    generated_docs: dict = None,
) -> dict:
    """综合预估单个 Agent 的真实 Token 消耗（含上下文注入和额外调用轮次）。"""
    docs = generated_docs if generated_docs is not None else {}

    # 1. 源代码
    code_tokens = estimate_tokens(code) if code else 0

    # 2. Prompt 模板固定开销
    template_tokens = _PROMPT_TEMPLATE_OVERHEAD.get(agent_type, 2000)

    # 3. 安全知识库注入
    knowledge_text = get_safety_knowledge(asil_level, agent_type)
    if agent_type == "SRS" and asil_level not in ("QM", "ASIL A"):
        knowledge_text += get_asil_decomposition_guidance(asil_level)
    knowledge_tokens = estimate_tokens(knowledge_text) if knowledge_text else 0

    # 4. 前置文档注入
    prior_keys = _AGENT_PRIOR_DOCS.get(agent_type, [])
    prior_docs_tokens = 0
    for dk in prior_keys:
        if dk in docs and docs[dk]:
            prior_docs_tokens += estimate_tokens(docs[dk])
    if prior_docs_tokens > 0:
        prior_docs_tokens += len(prior_keys) * 30

    # 5. 单轮输入合计（普通模式）
    input_total = code_tokens + template_tokens + knowledge_tokens + prior_docs_tokens

    # 6. 预估输出：基于代码量动态缩放（4000 token 为基准，0.3x ~ 2.0x）
    ref = max(code_tokens, 1) if code_tokens else 1
    scale = max(0.3, min(2.0, ref / 4000.0))
    output_estimated = int(_AGENT_TOKEN_DEFAULT_B.get(agent_type, 8192) * 0.7 * scale)

    # 7. 计算调用轮次和总消耗
    if not chunked_mode:
        call_rounds = 1.0 + (1.0 if review_mode else 0.0)
        grand_total = input_total + output_estimated
        if review_mode:
            grand_total += (output_estimated + _REVIEW_PROMPT_OVERHEAD + code_tokens) + output_estimated
    else:
        n_chunks = _AGENT_CHUNK_COUNT.get(agent_type, 3)
        chunk_output = output_estimated // n_chunks

        chunk_input_per_call = code_tokens + prior_docs_tokens + _CHUNK_TEMPLATE_OVERHEAD
        chunks_total = n_chunks * (chunk_input_per_call + chunk_output)

        merge_input = output_estimated + _MERGE_PROMPT_OVERHEAD + code_tokens
        merge_total = merge_input + output_estimated

        call_rounds = float(n_chunks + 1)
        grand_total = chunks_total + merge_total

        if review_mode:
            grand_total += (output_estimated + _REVIEW_PROMPT_OVERHEAD + code_tokens) + output_estimated
            call_rounds += 1.0

    return {
        "code_tokens": code_tokens,
        "template_tokens": template_tokens,
        "knowledge_tokens": knowledge_tokens,
        "prior_docs_tokens": prior_docs_tokens,
        "input_total": input_total,
        "output_estimated": output_estimated,
        "call_rounds": call_rounds,
        "grand_total": int(grand_total),
    }


def estimate_batch_total_tokens(
    code: str,
    asil_level: str = "ASIL B",
    generated_docs: dict = None,
) -> dict:
    """预估批量生成全部 7 个 Agent 的总 Token 消耗（顺序累加前置文档）。"""
    docs = dict(generated_docs or {})
    per_agent = {}
    total = 0
    for agent in AGENT_ORDER:
        est = estimate_agent_total_tokens(agent, code, asil_level, generated_docs=docs)
        per_agent[agent] = est
        total += est["grand_total"]
        docs[agent] = "x" * (est["output_estimated"] * 3)
    return {"per_agent": per_agent, "total": total}
