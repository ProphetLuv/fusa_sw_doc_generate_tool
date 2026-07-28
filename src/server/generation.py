# -*- coding: utf-8 -*-
"""
generation.py — LLM 生成编排（SSE 事件生成器）。

从原 workspace/dashboard 平移单 Agent（含分段并发 + 一致性合并 + 审查修订）、
批量生成（模块×Agent 顺序 + 断点续传 + 取消）逻辑，去除 Streamlit 依赖，
改为产出统一的事件字典，由路由层格式化为 SSE。

事件字典形状：{"event": <name>, "data": <dict>}
- status   : {"message": str}
- chunk_init: {"titles": [str], "keys": int}
- token    : {"text": str, "phase": "main"|"chunk"|"merge"|"review", "chunk": int?}
- progress : {"step": int, "total": int, "module": str, "agent": str}
- done     : {"module": str, "agent": str, "content": str, "validation": {...}, "token_usage": {...}}
- batch_done: {"summary": str}
- error    : {"message": str}
"""

import time
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

from llm_engine import LLMEngine, estimate_tokens
from prompts import PromptManager
from validator import validate_document, validate_code_document_consistency
from code_parser import CodeParser

from server.state import STATE
from server.estimate import AGENT_ORDER, AGENT_PRIOR_INJECT, get_agent_token_defaults

_PROMPT_MGR = PromptManager()


# ======================================================================
# 引擎 & 上下文辅助
# ======================================================================

def make_engine(cfg: dict, max_tokens: int = None) -> LLMEngine:
    """根据配置字典创建 LLMEngine 实例。"""
    return LLMEngine(
        provider=cfg["provider"], api_key=cfg["api_key"],
        api_base=cfg.get("api_base"), model=cfg.get("model") or None,
        max_tokens=max_tokens or cfg.get("max_tokens", 8192),
        temperature=cfg.get("temperature", 0.2),
    )


def build_context(agent_type: str, module_name: str, asil_level: str, mod_docs: dict) -> dict:
    """构建生成上下文，按规则注入前置文档。"""
    ctx = {"module_name": module_name, "asil_level": asil_level}
    prior_keys = AGENT_PRIOR_INJECT.get(agent_type, [])
    if prior_keys:
        prior = {k: mod_docs[k] for k in prior_keys if k in mod_docs and mod_docs[k]}
        if prior:
            ctx["prior_docs"] = prior
    return ctx


def get_code_analysis(code: str) -> dict:
    """获取代码解析结果（按 code hash 缓存）。"""
    h = hash(code)
    cache = STATE._analysis_cache
    if cache.get("_hash") != h:
        cache.clear()
        cache["_hash"] = h
        cache["info"] = CodeParser().analyze(code)
    return cache["info"]


def _run_validation(agent_type: str, full_text: str, code: str, custom_template: str = None):
    """质量校验 + 代码一致性校验，返回 (report, summary)。"""
    report = validate_document(agent_type, full_text, custom_template=custom_template)
    if not full_text.startswith("生成失败") and code:
        try:
            analysis = get_code_analysis(code)
            consistency = validate_code_document_consistency(agent_type, full_text, analysis)
            report.results.extend(consistency.results)
        except Exception:
            pass
    details = [
        {"check_name": r.check_name, "passed": r.passed,
         "severity": r.severity, "message": r.message, "details": r.details}
        for r in report.results
    ]
    return report, {"summary": report.summary(), "passed": report.passed, "results": details}


def _record_usage(engine: LLMEngine, prompt: str, full_text: str, duration: float,
                  module: str, agent_type: str, provider: str, model: str) -> dict:
    """依据引擎实际用量（或估算兜底）记录并存储 token 用量，返回用量 dict。"""
    actual = getattr(engine, "last_usage", None) or {}
    if actual.get("total_tokens", 0) > 0:
        usage = {
            "prompt_tokens": actual["prompt_tokens"],
            "completion_tokens": actual["completion_tokens"],
            "total_tokens": actual["total_tokens"],
            "duration_sec": round(duration, 1),
            "provider": provider, "model": model, "is_actual": True,
        }
    else:
        pt, ot = estimate_tokens(prompt), estimate_tokens(full_text)
        usage = {
            "prompt_tokens": pt, "completion_tokens": ot, "total_tokens": pt + ot,
            "duration_sec": round(duration, 1),
            "provider": provider, "model": model, "is_actual": False,
        }
    STATE.set_token_usage(module, agent_type, usage)
    return usage


# ======================================================================
# 单 Agent 生成（SSE 事件生成器）
# ======================================================================

def generate_single_stream(agent_type, module, cfg, chunked_mode=False,
                           review_mode=False, review_cfg=None, max_tokens=None,
                           custom_template=None):
    """单 Agent 生成的 SSE 事件生成器。"""
    module = module or STATE.active_module_name()
    code = STATE.module_code(module) or STATE.active_code()
    if not code:
        yield {"event": "error", "data": {"message": "当前模块无代码"}}
        return
    if not cfg.get("api_key"):
        yield {"event": "error", "data": {"message": "未配置 API Key"}}
        return

    asil = cfg.get("asil_level", "ASIL B")
    mod_docs = STATE.get_module_docs(module)
    ctx = build_context(agent_type, module, asil, mod_docs)

    try:
        engine = make_engine(cfg, max_tokens=max_tokens)
    except Exception as e:
        yield {"event": "error", "data": {"message": f"引擎初始化失败: {e}"}}
        return

    t0 = time.time()
    full_text = ""
    prompt_for_log = ""

    try:
        if chunked_mode:
            yield from _chunked_generate(agent_type, code, ctx, cfg, engine, custom_template,
                                         out := _Collector())
            full_text = out.text
            prompt_for_log = out.text  # 分段模式无单一 prompt，用输出估算
        else:
            prompt_for_log = _PROMPT_MGR.get_prompt(agent_type, code, ctx, custom_template=custom_template)
            yield {"event": "status", "data": {"message": f"正在生成 {agent_type} ..."}}
            for chunk in engine.stream_generate(prompt_for_log):
                full_text += chunk
                yield {"event": "token", "data": {"text": chunk, "phase": "main"}}
    except Exception as e:
        full_text = f"生成失败: {e}"
        yield {"event": "token", "data": {"text": full_text, "phase": "main"}}

    duration = time.time() - t0

    # 保存结果到活动模块（保留旧版本用于 Diff）
    if agent_type in mod_docs:
        STATE.push_version(module, agent_type, mod_docs[agent_type])
    mod_docs[agent_type] = full_text

    # 校验
    report, validation = _run_validation(agent_type, full_text, code, custom_template)
    STATE.add_history(module, agent_type,
                      "成功" if not full_text.startswith("生成失败") else "失败",
                      report.summary())

    # 日志 + token 用量
    STATE.log_generation(
        doc_type=agent_type, module_name=module,
        provider=engine.provider, model=engine.model,
        prompt_tokens=estimate_tokens(prompt_for_log),
        output_tokens=estimate_tokens(full_text),
        duration=duration,
        success=not full_text.startswith("生成失败"),
    )
    usage = _record_usage(engine, prompt_for_log, full_text, duration,
                          module, agent_type, engine.provider, engine.model)
    STATE.persist()

    # ── 审查修订 ──
    if review_mode and review_cfg and review_cfg.get("api_key") and not full_text.startswith("生成失败"):
        yield {"event": "status", "data": {"message": "审查修订中..."}}
        try:
            review_engine = make_engine(review_cfg, max_tokens=max_tokens)
            review_prompt = _PROMPT_MGR.get_review_prompt(
                agent_type, full_text, code,
                {"module_name": module, "asil_level": asil})
            reviewed = ""
            for c in review_engine.stream_generate(review_prompt):
                reviewed += c
                yield {"event": "token", "data": {"text": c, "phase": "review"}}
            if reviewed and not reviewed.startswith("生成失败"):
                STATE.push_version(module, agent_type, full_text)
                mod_docs[agent_type] = reviewed
                full_text = reviewed
                report, validation = _run_validation(agent_type, full_text, code, custom_template)
                STATE.add_history(module, f"{agent_type} (审查修订)", "成功")
                STATE.persist()
        except Exception as e:
            yield {"event": "status", "data": {"message": f"审查修订失败（保留原文）: {e}"}}

    yield {"event": "done", "data": {
        "module": module, "agent": agent_type, "content": full_text,
        "validation": validation, "token_usage": usage,
    }}


class _Collector:
    """在分段生成器与外层之间传递最终合并文本。"""
    def __init__(self):
        self.text = ""


def _chunked_generate(agent_type, code, ctx, cfg, engine, custom_template, collector):
    """分段并发生成 + 一致性合并（生成器，yield 事件；结果写入 collector.text）。"""
    chunks = _PROMPT_MGR.get_chunk_prompts(agent_type, code, ctx, custom_template=custom_template)
    if len(chunks) <= 1:
        prompt = chunks[0][1] if chunks else _PROMPT_MGR.get_prompt(agent_type, code, ctx, custom_template=custom_template)
        yield {"event": "status", "data": {"message": f"正在生成 {agent_type} ..."}}
        text = ""
        for c in engine.stream_generate(prompt):
            text += c
            yield {"event": "token", "data": {"text": c, "phase": "main"}}
        collector.text = text
        return

    # 多 Key 引擎池（轮转）
    api_keys = [k for k in (cfg.get("api_keys") or []) if k]
    if len(api_keys) > 1:
        engine_pool = [make_engine({**cfg, "api_key": k}) for k in api_keys]
    else:
        engine_pool = [engine]

    titles = [t for t, _ in chunks]
    yield {"event": "chunk_init", "data": {"titles": titles, "keys": len(engine_pool)}}
    yield {"event": "status", "data": {
        "message": f"分为 {len(chunks)} 段并发生成"
                   + (f" | 使用 {len(engine_pool)} 个 Key 轮转" if len(engine_pool) > 1 else "")}}

    q = queue.Queue()
    chunk_results = [None] * len(chunks)
    usage_lock = threading.Lock()
    chunk_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def _worker(ci, cprompt):
        chunk_engine = engine_pool[ci % len(engine_pool)]
        text = ""
        try:
            for c in chunk_engine.stream_generate(cprompt):
                text += c
                q.put({"event": "token", "data": {"text": c, "phase": "chunk", "chunk": ci}})
        except Exception as e:
            text = f"生成失败: {e}"
            q.put({"event": "token", "data": {"text": text, "phase": "chunk", "chunk": ci}})
        chunk_results[ci] = text
        u = getattr(chunk_engine, "last_usage", None) or {}
        if u.get("total_tokens", 0) > 0:
            with usage_lock:
                for k in chunk_usage:
                    chunk_usage[k] += u[k]
        q.put({"event": "status", "data": {"message": f"✅ {titles[ci]} 完成"}})

    executor = ThreadPoolExecutor(max_workers=min(len(chunks), 8))
    futures = [executor.submit(_worker, ci, p) for ci, (_, p) in enumerate(chunks)]
    done_flag = {"n": 0}

    def _watch():
        for _ in as_completed(futures):
            done_flag["n"] += 1
        q.put(None)  # 结束哨兵

    threading.Thread(target=_watch, daemon=True).start()

    while True:
        item = q.get()
        if item is None:
            break
        yield item
    executor.shutdown(wait=True)

    doc_title = f"# {ctx['module_name']} {agent_type} 文档\n\n"
    full_text = doc_title + "\n\n".join(r or "" for r in chunk_results)

    # ── 一致性合并审查 ──
    if not any((r or "").startswith("生成失败") for r in chunk_results):
        yield {"event": "status", "data": {"message": "🔗 分段一致性合并审查中..."}}
        try:
            merge_prompt = _PROMPT_MGR.get_consistency_merge_prompt(agent_type, full_text, code, ctx)
            merged = ""
            yield {"event": "merge_start", "data": {}}
            for c in engine.stream_generate(merge_prompt):
                merged += c
                yield {"event": "token", "data": {"text": c, "phase": "merge"}}
            if merged and not merged.startswith("生成失败"):
                full_text = merged
                mu = getattr(engine, "last_usage", None) or {}
                if mu.get("total_tokens", 0) > 0:
                    for k in chunk_usage:
                        chunk_usage[k] += mu[k]
                yield {"event": "status", "data": {"message": "✅ 一致性合并审查完成"}}
        except Exception as e:
            yield {"event": "status", "data": {"message": f"⚠️ 合并审查失败（保留拼接结果）: {e}"}}

    collector.text = full_text


# ======================================================================
# 批量生成（SSE 事件生成器）
# ======================================================================

def generate_batch_stream(cfg):
    """按模块 × Agent 顺序批量生成，SSE 事件生成器。支持断点续传与取消。"""
    if not cfg.get("api_key"):
        yield {"event": "error", "data": {"message": "未配置 API Key"}}
        return

    agent_defaults = get_agent_token_defaults(cfg.get("asil_level", "ASIL B"))
    project_modules = STATE.project_modules
    if project_modules:
        modules = [m for m in (STATE.selected_modules or list(project_modules.keys()))
                   if m in project_modules]
    else:
        modules = [cfg.get("module_name", "目标模块")]
        project_modules = {modules[0]: STATE.active_code()}

    try:
        make_engine(cfg)  # fail-fast 验证配置
    except Exception as e:
        yield {"event": "error", "data": {"message": f"引擎初始化失败: {e}"}}
        return

    total_steps = len(modules) * len(AGENT_ORDER)
    checkpoint = STATE.batch_checkpoint
    STATE.cancel_generation = False
    step = 0
    cancelled = False

    for mod_name in modules:
        mod_code = project_modules.get(mod_name, "")
        if not mod_code:
            step += len(AGENT_ORDER)
            continue
        mod_docs = STATE.get_module_docs(mod_name)
        mod_checkpoint = checkpoint.setdefault(mod_name, {})

        for agent_type in AGENT_ORDER:
            if mod_checkpoint.get(agent_type) == "done":
                step += 1
                continue
            if STATE.cancel_generation:
                yield {"event": "status", "data": {"message": "⚠️ 已取消批量生成，已完成部分已保存"}}
                cancelled = True
                break

            step += 1
            yield {"event": "progress", "data": {
                "step": step, "total": total_steps, "module": mod_name, "agent": agent_type}}

            ctx = build_context(agent_type, mod_name, cfg["asil_level"], mod_docs)
            t0 = time.time()
            agent_engine = make_engine(cfg, max_tokens=agent_defaults.get(agent_type))
            prompt = _PROMPT_MGR.get_prompt(agent_type, mod_code, ctx,
                                            custom_template=STATE.agent_templates.get(agent_type))
            text = ""
            try:
                for c in agent_engine.stream_generate(prompt):
                    text += c
                    yield {"event": "token", "data": {
                        "text": c, "phase": "batch", "module": mod_name, "agent": agent_type}}
            except Exception as e:
                text = f"生成失败: {e}"
                yield {"event": "token", "data": {
                    "text": text, "phase": "batch", "module": mod_name, "agent": agent_type}}
            duration = time.time() - t0

            mod_docs[agent_type] = text
            report, _ = _run_validation(agent_type, text, mod_code,
                                        STATE.agent_templates.get(agent_type))
            STATE.add_history(mod_name, agent_type,
                              "成功" if not text.startswith("生成失败") else "失败",
                              report.summary())
            STATE.log_generation(
                doc_type=agent_type, module_name=mod_name,
                provider=agent_engine.provider, model=agent_engine.model,
                prompt_tokens=estimate_tokens(prompt), output_tokens=estimate_tokens(text),
                duration=duration, success=not text.startswith("生成失败"))
            _record_usage(agent_engine, prompt, text, duration, mod_name, agent_type,
                          agent_engine.provider, agent_engine.model)
            mod_checkpoint[agent_type] = "done"
            STATE.persist()

        if cancelled:
            break

    if not cancelled:
        STATE.batch_checkpoint = {}
    STATE.persist()

    done_count = sum(1 for m in modules for a in AGENT_ORDER
                     if checkpoint.get(m, {}).get(a) == "done")
    yield {"event": "batch_done", "data": {
        "summary": f"批量生成完成（{done_count}/{total_steps} 份文档）",
        "cancelled": cancelled, "done_count": done_count, "total": total_steps}}
