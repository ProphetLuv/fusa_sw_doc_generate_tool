# -*- coding: utf-8 -*-
"""
app_utils.py — 公共工具函数、常量、持久化、日志、引擎创建、缓存校验。
被所有其他 app_* 模块依赖，自身不依赖任何 app_* 模块。
"""

import streamlit as st
import time
import json
import os
import sys
import threading
import stat
import difflib

from llm_engine import LLMEngine, estimate_tokens, estimate_cost
from validator import validate_document
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

# Agent 元数据
_AGENT_META = {
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

# ── 文件路径 ──
_SAVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "saved_results.json")
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "generation_log.jsonl")


# ======================================================================
# Session State 初始化
# ======================================================================

def init_session_state():
    """初始化所有 session_state 键（幂等，可多次调用）。"""
    defaults = {
        "generated_docs": {},
        "generation_history": [],
        "current_agent": None,
        "shared_code": "",
        "agent_templates": {},
        "doc_versions": {},        # {agent_type: [old_content, ...]}
        "batch_checkpoint": {},    # {module: {agent_type: status}}
        "cancel_generation": False,  # 取消标志
        "last_failed_agent": None,  # 上次失败的 Agent
        # ── 工程级多模块支持 ──
        "project_modules": {},     # {module_name: code_str}
        "module_files": {},        # {module_name: [rel_path,...]}
        "active_module": None,     # 工作区当前选中的模块名
        "selected_modules": [],    # 仪表盘批量选中的模块名
        "docs_by_module": {},      # {module_name: {agent_type: content}}
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ======================================================================
# 多模块辅助函数（活动模块派生视图）
# ======================================================================

def _default_module_name() -> str:
    """默认模块名（单文件/粘贴上传时使用）。"""
    return st.session_state.get("_config_module_name") or "目标模块"


def active_module_name() -> str:
    """返回当前活动模块名；若无模块则回退到默认模块名。"""
    am = st.session_state.get("active_module")
    mods = st.session_state.get("project_modules", {})
    if am and am in mods:
        return am
    if mods:
        return next(iter(mods))
    return _default_module_name()


def get_module_docs(module: str = None) -> dict:
    """获取指定模块（默认活动模块）的文档字典引用（懒创建）。"""
    mod = module or active_module_name()
    dbm = st.session_state.setdefault("docs_by_module", {})
    return dbm.setdefault(mod, {})


def active_docs() -> dict:
    """获取活动模块的文档字典引用（懒创建）。"""
    return get_module_docs(active_module_name())


def active_code() -> str:
    """获取活动模块的代码串。"""
    mods = st.session_state.get("project_modules", {})
    am = active_module_name()
    return mods.get(am, st.session_state.get("shared_code", ""))


def sync_active_views():
    """将 shared_code / generated_docs 同步为活动模块的派生视图。"""
    st.session_state.shared_code = active_code()
    st.session_state.generated_docs = active_docs()


# ======================================================================
# 工具函数
# ======================================================================

def _get_agent_token_defaults(asil_level: str) -> dict:
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
    """综合预估单个 Agent 的真实 Token 消耗（含上下文注入和额外调用轮次）。

    分段并发模式的消耗模型：
      - N 个 chunk 并行调用：每个 chunk 都完整传入 code + prior_docs
      - 1 次合并审查调用：传入拼接后全文
      - 可选 1 次双模型审查：传入合并后全文

    Returns:
        {
            "code_tokens": int,        # 源代码 Token
            "template_tokens": int,    # Prompt 模板开销
            "knowledge_tokens": int,   # 安全知识库注入
            "prior_docs_tokens": int,  # 前置文档注入
            "input_total": int,        # 单轮输入合计（普通模式）
            "output_estimated": int,   # 预估输出
            "call_rounds": float,      # LLM 调用轮次
            "grand_total": int,        # 全部轮次总消耗
        }
    """
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
    # 前置文档注入时的额外格式化文本（标题/分隔符）
    if prior_docs_tokens > 0:
        prior_docs_tokens += len(prior_keys) * 30

    # 5. 单轮输入合计（普通模式）
    input_total = code_tokens + template_tokens + knowledge_tokens + prior_docs_tokens

    # 6. 预估输出（使用 Agent 推荐 max_tokens 的 70% 作为实际输出估计）
    output_estimated = int(_AGENT_TOKEN_DEFAULT_B.get(agent_type, 8192) * 0.7)

    # 7. 计算调用轮次和总消耗
    if not chunked_mode:
        # ── 普通模式：1 次生成 + 可选 1 次审查 ──
        call_rounds = 1.0 + (1.0 if review_mode else 0.0)
        grand_total = input_total + output_estimated
        if review_mode:
            # 审查调用：输入 = 已生成文档 + 审查Prompt开销 + 代码
            grand_total += (output_estimated + _REVIEW_PROMPT_OVERHEAD + code_tokens) + output_estimated
    else:
        # ── 分段并发模式：N 次 chunk + 1 次合并 + 可选 1 次审查 ──
        n_chunks = _AGENT_CHUNK_COUNT.get(agent_type, 3)
        chunk_output = output_estimated // n_chunks  # 每个 chunk 的输出

        # N 个 chunk 调用：每个都完整传入 code + prior_docs + chunk模板
        chunk_input_per_call = code_tokens + prior_docs_tokens + _CHUNK_TEMPLATE_OVERHEAD
        chunks_total = n_chunks * (chunk_input_per_call + chunk_output)

        # 合并审查调用：输入 = 拼接后全文 + 合并Prompt + 代码
        merge_input = output_estimated + _MERGE_PROMPT_OVERHEAD + code_tokens
        merge_total = merge_input + output_estimated

        call_rounds = float(n_chunks + 1)  # N chunks + 1 merge
        grand_total = chunks_total + merge_total

        if review_mode:
            # 额外审查调用
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
    order = ["SRS", "SAD", "FMEA", "DFA", "SDD", "TC-UNIT", "TC-INTEGRATION"]
    per_agent = {}
    total = 0
    for agent in order:
        est = estimate_agent_total_tokens(agent, code, asil_level,
                                          generated_docs=docs)
        per_agent[agent] = est
        total += est["grand_total"]
        # 模拟生成后文档加入上下文（用预估输出作为文档大小近似）
        docs[agent] = "x" * (est["output_estimated"] * 3)  # 粗略模拟文档字符数
    return {"per_agent": per_agent, "total": total}


def _mask_api_key(key: str) -> str:
    """对 API Key 进行脱敏处理，只保留前4位和后4位。"""
    if not key or len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"


def _empty_config() -> dict:
    """返回空配置模板。"""
    return {
        "provider": "openai", "api_key": "", "api_base": None, "model": "gpt-4o",
        "max_tokens": 8192, "temperature": 0.2, "module_name": "目标模块",
        "asil_level": "ASIL B", "api_keys": [],
    }


# ======================================================================
# 持久化
# ======================================================================

def _load_persisted():
    """启动时从本地 JSON 加载历史结果。"""
    save_path = os.path.normpath(_SAVE_FILE)
    if os.path.exists(save_path):
        try:
            with open(save_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                return  # 空文件，跳过
            data = json.loads(content)
            # 优先加载多模块嵌套结构
            if data.get("docs_by_module"):
                st.session_state.docs_by_module = data["docs_by_module"]
            elif data.get("generated_docs"):
                # 旧存档兼容：扁平文档归入默认模块
                st.session_state.generated_docs = data["generated_docs"]
                mod = _default_module_name()
                st.session_state.docs_by_module.setdefault(mod, {}).update(data["generated_docs"])
            if data.get("history"):
                st.session_state.generation_history = data["history"]
            sync_active_views()
        except Exception as e:
            print(f"[WARN] 加载持久化数据失败: {e}", file=sys.stderr)


def _persist():
    """将当前结果保存到本地 JSON（防抖写入，500ms 内多次调用只执行一次）。"""
    save_path = os.path.normpath(_SAVE_FILE)

    def _do_save():
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump({
                    "generated_docs": st.session_state.generated_docs,
                    "docs_by_module": st.session_state.get("docs_by_module", {}),
                    "history": st.session_state.generation_history[-50:],
                }, f, ensure_ascii=False)
            # 设置文件权限为仅用户可读写（Windows 兼容）
            try:
                os.chmod(save_path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass
        except Exception as e:
            print(f"[WARN] 保存数据失败: {e}", file=sys.stderr)

    # 取消上次定时器（如有），重新计时
    if hasattr(_persist, "_timer") and _persist._timer is not None:
        _persist._timer.cancel()
    _persist._timer = threading.Timer(0.5, _do_save)
    _persist._timer.daemon = True
    _persist._timer.start()


# 模块级定时器初始化
_persist._timer = None


# ======================================================================
# 日志
# ======================================================================

def _log_generation(doc_type: str, module_name: str, provider: str, model: str,
                    prompt_tokens: int, output_tokens: int, duration: float,
                    success: bool, error: str = ""):
    """记录每次生成的详细日志（追加写入 JSONL 文件）。"""
    log_path = os.path.normpath(_LOG_FILE)
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "doc_type": doc_type,
        "module": module_name,
        "provider": provider,
        "model": model,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "duration_sec": round(duration, 1),
        "success": success,
        "error": error,
    }
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[WARN] 日志写入失败: {e}", file=sys.stderr)


# ======================================================================
# 引擎 & 单文档生成
# ======================================================================

def _make_engine(cfg: dict) -> LLMEngine:
    """根据配置字典创建 LLMEngine 实例。"""
    return LLMEngine(
        provider=cfg["provider"], api_key=cfg["api_key"],
        api_base=cfg.get("api_base"), model=cfg.get("model"),
        max_tokens=cfg.get("max_tokens", 8192), temperature=cfg.get("temperature", 0.2),
    )


def _generate_single_doc(engine, prompt_mgr, doc_type, code, context, custom_template, display_container=None):
    """执行单次文档生成（流式输出），返回完整文本。"""
    prompt = prompt_mgr.get_prompt(doc_type, code, context, custom_template=custom_template)
    full_text = ""
    error_msg = ""
    t0 = time.time()
    try:
        for chunk in engine.stream_generate(prompt):
            full_text += chunk
            if display_container is not None:
                display_container.markdown(full_text + "▌")
                time.sleep(0.003)  # 轻微延迟保证渲染流畅，但不过度拖慢
    except Exception as e:
        full_text = f"生成失败: {e}"
        error_msg = str(e)
        # 记录失败 Agent，供重试按钮使用
        st.session_state.last_failed_agent = doc_type
    duration = time.time() - t0
    if display_container is not None:
        display_container.markdown(full_text)
    # 生成成功时清除失败标志
    if not error_msg:
        if st.session_state.last_failed_agent == doc_type:
            st.session_state.last_failed_agent = None

    # 写入日志（优先使用 API 返回的实际用量，否则回退到估算）
    actual_usage = getattr(engine, "last_usage", None) or {}
    real_prompt = actual_usage.get("prompt_tokens", 0)
    real_output = actual_usage.get("completion_tokens", 0)
    _log_generation(
        doc_type=doc_type,
        module_name=context.get("module_name", "目标模块"),
        provider=engine.provider,
        model=engine.model,
        prompt_tokens=real_prompt if real_prompt > 0 else estimate_tokens(prompt),
        output_tokens=real_output if real_output > 0 else estimate_tokens(full_text),
        duration=duration,
        success=not error_msg,
        error=error_msg,
    )

    # 将实际 Token 用量存入 session_state，供 Agent 工作区展示
    if actual_usage.get("total_tokens", 0) > 0:
        st.session_state[f"token_usage_{doc_type}"] = {
            "prompt_tokens": actual_usage["prompt_tokens"],
            "completion_tokens": actual_usage["completion_tokens"],
            "total_tokens": actual_usage["total_tokens"],
            "duration_sec": round(duration, 1),
            "provider": engine.provider,
            "model": engine.model,
            "is_actual": True,
        }
    else:
        # API 未返回用量时用估算值兜底
        st.session_state[f"token_usage_{doc_type}"] = {
            "prompt_tokens": estimate_tokens(prompt),
            "completion_tokens": estimate_tokens(full_text),
            "total_tokens": estimate_tokens(prompt) + estimate_tokens(full_text),
            "duration_sec": round(duration, 1),
            "provider": engine.provider,
            "model": engine.model,
            "is_actual": False,
        }

    return full_text


# ======================================================================
# Diff 生成
# ======================================================================

def _generate_diff(old_text: str, new_text: str) -> str:
    """生成简易的文本 Diff 输出（unified diff 格式）。"""
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile="上一版本", tofile="当前版本", lineterm="")
    return "".join(diff)


# ======================================================================
# 缓存校验（避免每次 re-run 重复执行 validate_document）
# ======================================================================

def _get_cached_validation(agent_type: str, content: str):
    """获取校验报告，使用 session_state 缓存避免重复计算。"""
    if "_validation_cache" not in st.session_state:
        st.session_state._validation_cache = {}
    cache_key = (agent_type, hash(content))
    if cache_key not in st.session_state._validation_cache:
        st.session_state._validation_cache[cache_key] = validate_document(agent_type, content)
    return st.session_state._validation_cache[cache_key]
