# -*- coding: utf-8 -*-
"""
app_workspace.py — Agent 工作区、代码状态展示、单 Agent 生成。
"""

import streamlit as st
import time

from llm_engine import DEFAULT_MODELS, PROVIDER_BASE_URLS
from prompts import PromptManager
from validator import validate_document, validate_code_document_consistency

from app.app_utils import (
    _AGENT_META,
    _get_agent_token_defaults,
    _persist,
    _make_engine,
    _generate_single_doc,
    estimate_agent_total_tokens,
    active_module_name,
    active_docs,
    active_code,
    get_module_docs,
    sync_active_views,
)
from app.app_sidebar import _render_agent_template_upload


def _render_agent_workspace(agent_type: str, config: dict):
    """渲染单个 Agent 的工作区：代码输入 + 选项 + 生成 + 结果。"""
    meta = _AGENT_META.get(agent_type, {"icon": "📄", "name": agent_type, "full": agent_type, "desc": ""})
    # 记录配置中的模块名（供多模块默认命名使用）
    st.session_state._config_module_name = config.get("module_name", "目标模块")

    # 顶部导航栏
    nav_col1, nav_col2, nav_col3 = st.columns([1, 4, 1])
    with nav_col1:
        if st.button("← 返回总览", use_container_width=True):
            st.session_state.current_agent = None
            st.rerun()
    with nav_col2:
        st.markdown(f"### {meta['icon']} {meta['name']} — {meta['full']}")
    with nav_col3:
        if st.button("🗑️ 清空", use_container_width=True, key=f"clear_{agent_type}"):
            active_docs().pop(agent_type, None)
            sync_active_views()
            _persist()
            st.rerun()

    st.caption(meta["desc"])
    st.markdown("---")

    # ── 自定义文档模板 ──
    agent_template = _render_agent_template_upload(agent_type)

    # ── 代码状态（上传在总览页管理）──
    code = _render_code_status_bar()

    # ── FMEA 前置上下文提示 ──
    _fmea_missing_prior = False
    if agent_type == "FMEA":
        has_srs = "SRS" in active_docs()
        has_sad = "SAD" in active_docs()
        _fmea_missing_prior = not (has_srs and has_sad)
        prior_info = []
        prior_info.append("✅ SRS 已就绪" if has_srs else "❌ SRS 未生成")
        prior_info.append("✅ SAD 已就绪" if has_sad else "❌ SAD 未生成")
        if _fmea_missing_prior:
            st.warning(
                "⚠️ **FMEA 前置文档不完整**：" + " | ".join(prior_info) + "\n\n"
                "建议先完成 SRS 和 SAD Agent 的生成，FMEA 将自动引用其分析结果，"
                "使失效影响可追溯到安全需求、失效模式可关联到架构组件，显著提升分析覆盖度和追溯性。\n\n"
                "如跳过，FMEA 仍可基于源代码独立生成，但追溯矩阵和覆盖分析将不完整。"
            )
        else:
            st.success("🔗 **FMEA 前置上下文**: " + " | ".join(prior_info) + " — 将自动注入生成")

    # ── DFA 前置上下文提示 ──
    _dfa_missing_prior = False
    if agent_type == "DFA":
        has_sad = "SAD" in active_docs()
        has_fmea = "FMEA" in active_docs()
        _dfa_missing_prior = not (has_sad and has_fmea)
        prior_info = []
        prior_info.append("✅ SAD 已就绪" if has_sad else "❌ SAD 未生成")
        prior_info.append("✅ FMEA 已就绪" if has_fmea else "❌ FMEA 未生成")
        if _dfa_missing_prior:
            st.warning(
                "⚠️ **DFA 前置文档不完整**：" + " | ".join(prior_info) + "\n\n"
                "DFA 需要引用架构分解（SAD）和已识别的失效模式（FMEA），"
                "建议先完成 SAD 和 FMEA Agent 的生成。\n\n"
                "如跳过，DFA 仍可基于源代码独立生成，但架构元素识别和失效模式引用将不完整。"
            )
        else:
            st.success("🔗 **DFA 前置上下文**: " + " | ".join(prior_info) + " — 将自动注入生成")

    # ── 生成选项（默认展开）──
    _AGENT_TOKEN_DEFAULT = _get_agent_token_defaults(config.get("asil_level", "ASIL B"))
    with st.expander("⚙️ 生成选项", expanded=True):
        opt_col1, opt_col2, opt_col3 = st.columns(3)
        with opt_col1:
            chunked_mode = st.checkbox("📑 分段并发生成", value=False,
                                        help="按章节拆分并行生成，提速 2~3 倍",
                                        key=f"chunked_{agent_type}")
        with opt_col2:
            review_mode = st.checkbox("🔍 双模型审查修订", value=False,
                                       help="生成后由第二个模型审查修正",
                                       key=f"review_{agent_type}")
        with opt_col3:
            agent_max_tokens = st.number_input(
                "📏 单次生成长度", min_value=1024, max_value=65536,
                value=_AGENT_TOKEN_DEFAULT.get(agent_type, 8192),
                step=1024,
                help=f"当前 Agent 单次生成文档的最大长度（{config.get('asil_level', 'ASIL B')} 推荐值: {_AGENT_TOKEN_DEFAULT.get(agent_type, 8192)}）。"
                     f"若生成的文档被截断不完整，请增大此值。",
                key=f"max_tokens_{agent_type}",
            )

        review_provider_cfg = {}
        if review_mode:
            st.markdown("##### 审查模型配置")
            rv_col1, rv_col2 = st.columns(2)
            with rv_col1:
                rv_provider = st.selectbox(
                    "审查供应商",
                    options=["openai", "anthropic", "dashscope", "deepseek", "glm", "kimi", "custom"],
                    format_func=lambda x: {"openai": "OpenAI", "anthropic": "Claude",
                                           "dashscope": "通义千问", "deepseek": "DeepSeek",
                                           "glm": "智谱GLM", "kimi": "Kimi", "custom": "自定义"}.get(x, x),
                    key=f"rv_prov_{agent_type}",
                )
                rv_key = st.text_input("审查 API Key", type="password", key=f"rv_key_{agent_type}")
            with rv_col2:
                rv_base = st.text_input("审查 Base URL",
                                         value=PROVIDER_BASE_URLS.get(rv_provider, ""),
                                         key=f"rv_base_{agent_type}")
                rv_model = st.text_input("审查模型",
                                          value=DEFAULT_MODELS.get(rv_provider, "gpt-4o"),
                                          key=f"rv_model_{agent_type}")
            review_provider_cfg = {
                "provider": rv_provider, "api_key": rv_key,
                "api_base": rv_base or None, "model": rv_model,
            }

    st.markdown("---")

    # ── 当前 Agent Token 消耗预估 ──
    if code:
        _est = estimate_agent_total_tokens(
            agent_type, code,
            asil_level=config.get("asil_level", "ASIL B"),
            chunked_mode=chunked_mode,
            review_mode=review_mode,
            generated_docs=active_docs(),
        )
        _parts = [
            f"代码 {_est['code_tokens']:,}",
            f"模板 {_est['template_tokens']:,}",
            f"知识库 {_est['knowledge_tokens']:,}",
        ]
        if _est['prior_docs_tokens'] > 0:
            _parts.append(f"前置文档 {_est['prior_docs_tokens']:,}")
        _rounds_txt = f" × {_est['call_rounds']:.0f} 轮" if _est['call_rounds'] > 1 else ""
        st.info(
            f"📊 **{agent_type} 预估消耗**：输入 {_est['input_total']:,} + 输出 ~{_est['output_estimated']:,}"
            f" = **{_est['grand_total']:,} tokens**{_rounds_txt}"
            f"（{_parts[0]} | {_parts[1]} | {_parts[2]}"
            + (f" | {_parts[3]}" if len(_parts) > 3 else "") + "）"
        )

    # ── 生成按钮 ──
    can_generate = bool(code) and bool(config["api_key"])
    if not config["api_key"]:
        st.warning("⚠️ 请在侧边栏输入 API Key")


    gen_col1, gen_col2 = st.columns([3, 1])
    with gen_col1:
        generate_clicked = st.button(
            f"🚀 生成 {agent_type} 文档", type="primary",
            use_container_width=True, disabled=not can_generate,
        )
    with gen_col2:
        # 重试按钮：上次生成失败时可用
        last_failed = st.session_state.last_failed_agent
        retry_clicked = st.button(
            "🔄 重试",
            use_container_width=True,
            disabled=(last_failed != agent_type or not can_generate),
            key=f"retry_{agent_type}",
            help="重新生成上次失败的文档",
        )

    if agent_template:
        st.info(f" 已启用 {agent_type} 自定义文档模板")

    # ── 执行生成 ──
    if (generate_clicked or retry_clicked) and can_generate:
        # 使用 Agent 级别的 max_tokens 覆盖全局配置
        agent_config = dict(config)
        agent_config["max_tokens"] = agent_max_tokens
        _run_single_agent_generation(agent_type, code, agent_config, chunked_mode,
                                      review_mode, review_provider_cfg, agent_template)

    # ── 显示结果 ──
    from app.app_results import _render_agent_result
    _render_agent_result(agent_type, config)

    # ── 持久展示上次生成的 Token 消耗 ──
    if st.session_state.get(f"token_usage_{agent_type}"):
        st.markdown("---")
        _render_token_usage(agent_type)


# ======================================================================
# 代码状态栏（轻量提示，上传在 Dashboard 管理）
# ======================================================================

def _render_token_usage(agent_type: str):
    """展示当前 Agent 最近一次生成的实际 Token 消耗。"""
    usage = st.session_state.get(f"token_usage_{agent_type}")
    if not usage:
        return
    tag = "实际" if usage.get("is_actual") else "估算"
    st.metric(
        label=f"📊 {agent_type} Token 消耗（{tag}）",
        value=f"{usage['total_tokens']:,}",
        delta=f"耗时 {usage['duration_sec']}s",
        delta_color="off",
    )
    st.caption(
        f"输入 {usage['prompt_tokens']:,} + 输出 {usage['completion_tokens']:,} "
        f"| {usage['provider']} / {usage['model']}"
    )


def _render_code_status_bar() -> str:
    """在 Agent 工作区显示代码加载状态（紧凑单行），返回活动模块代码。"""
    code = active_code()
    mods = st.session_state.get("project_modules", {})
    mod_names = list(mods.keys())

    if code:
        am_name = active_module_name()
        mod_files = st.session_state.module_files.get(am_name, [])
        lines = code.count("\n") + 1
        if len(mod_names) > 1:
            st.info(
                f"📦 当前模块：**{am_name}**（{len(mod_files)} 文件 / {lines:,} 行）| "
                f"工程共 {len(mod_names)} 个模块 | 如需调整代码请返回总览页"
            )
        else:
            st.info(
                f"📎 已加载：**{am_name}**（{len(mod_files)} 文件 / {lines:,} 行）| "
                f"如需修改代码请返回总览页"
            )
    else:
        st.warning("⚠️ 尚未上传代码 — 请点击「← 返回总览」在总览页上传 C/C++ 代码")

    return code


# ======================================================================
# 单 Agent 生成
# ======================================================================

def _run_single_agent_generation(agent_type, code, config, chunked_mode, review_mode, review_provider, custom_template=None):
    """为单个 Agent 执行文档生成（支持分段并发 + 审查修订）。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    prompt_mgr = PromptManager()
    base_context = {"module_name": config["module_name"], "asil_level": config["asil_level"]}

    # 前置文档注入（从活动模块的文档中读取）
    mod_docs = active_docs()
    ctx = dict(base_context)
    if agent_type == "FMEA":
        prior = {}
        if "SRS" in mod_docs:
            prior["SRS"] = mod_docs["SRS"]
        if "SAD" in mod_docs:
            prior["SAD"] = mod_docs["SAD"]
        if prior:
            ctx["prior_docs"] = prior

    # DFA 注入前置文档（SAD + FMEA）
    if agent_type == "DFA":
        prior = {}
        if "SAD" in mod_docs:
            prior["SAD"] = mod_docs["SAD"]
        if "FMEA" in mod_docs:
            prior["FMEA"] = mod_docs["FMEA"]
        if "SRS" in mod_docs:
            prior["SRS"] = mod_docs["SRS"]
        if prior:
            ctx["prior_docs"] = prior

    # TC-UNIT / TC-INTEGRATION 注入前置文档（SRS + FMEA + DFA + SAD）
    if agent_type in ("TC-UNIT", "TC-INTEGRATION"):
        prior = {}
        for doc_key in ("SRS", "SAD", "FMEA", "DFA"):
            if doc_key in mod_docs:
                prior[doc_key] = mod_docs[doc_key]
        if prior:
            ctx["prior_docs"] = prior

    try:
        engine = _make_engine(config)
    except Exception as e:
        st.error(f"❌ 引擎初始化失败: {e}")
        return

    status = st.empty()
    result_container = st.empty()

    # ── 分段并发 or 普通 ──
    if chunked_mode:
        chunks = prompt_mgr.get_chunk_prompts(agent_type, code, ctx, custom_template=custom_template)
        if len(chunks) > 1:
            # ── 构建多 Key 引擎池（轮转分配）──
            api_keys = config.get("api_keys") or []
            api_keys = [k for k in api_keys if k]  # 过滤空值
            if len(api_keys) > 1:
                engine_pool = []
                for k in api_keys:
                    cfg_copy = dict(config)
                    cfg_copy["api_key"] = k
                    engine_pool.append(_make_engine(cfg_copy))
                status.info(f"📑 分为 {len(chunks)} 段并发生成 | 🔑 使用 {len(engine_pool)} 个 Key 轮转")
            else:
                engine_pool = [engine]
                status.info(f"📑 分为 {len(chunks)} 段并发生成")

            cols = st.columns(min(len(chunks), 3))
            containers = []
            for i, (title, _) in enumerate(chunks):
                with cols[i % len(cols)]:
                    key_label = f" (Key#{i % len(engine_pool) + 1})" if len(engine_pool) > 1 else ""
                    st.markdown(f"**{title}**{key_label}")
                    containers.append(st.empty())

            chunk_results = [None] * len(chunks)
            # 线程安全锁：串行化对 Streamlit 容器的写入
            _container_lock = threading.Lock()
            # Token 用量累计器（线程安全）
            _usage_lock = threading.Lock()
            _chunk_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

            def _worker(ci, _, cprompt):
                chunk_engine = engine_pool[ci % len(engine_pool)]
                text = ""
                try:
                    for c in chunk_engine.stream_generate(cprompt):
                        text += c
                        with _container_lock:
                            containers[ci].markdown(text + "▌")
                except Exception as e:
                    text = f"生成失败: {e}"
                with _container_lock:
                    containers[ci].markdown(text)
                # 累计本次调用的实际 Token 用量
                u = getattr(chunk_engine, "last_usage", None) or {}
                if u.get("total_tokens", 0) > 0:
                    with _usage_lock:
                        _chunk_usage["prompt_tokens"] += u["prompt_tokens"]
                        _chunk_usage["completion_tokens"] += u["completion_tokens"]
                        _chunk_usage["total_tokens"] += u["total_tokens"]
                return ci, text

            with ThreadPoolExecutor(max_workers=min(len(chunks), 8)) as executor:
                futures = {executor.submit(_worker, ci, t, p): ci for ci, (t, p) in enumerate(chunks)}
                for f in as_completed(futures):
                    ci, text = f.result()
                    chunk_results[ci] = text

            doc_title = f"# {config['module_name']} {agent_type} 文档\n\n"
            full_text = doc_title + "\n\n".join(chunk_results)

            # ── 分段一致性合并审查 ──
            if len(chunks) > 1 and not full_text.startswith("生成失败"):
                status.info("🔗 分段一致性合并审查中...")
                try:
                    merge_prompt = prompt_mgr.get_consistency_merge_prompt(
                        agent_type, full_text, code, ctx
                    )
                    merge_container = st.empty()
                    merged_text = ""
                    for c in engine.stream_generate(merge_prompt):
                        merged_text += c
                        merge_container.markdown(merged_text + "▌")
                        time.sleep(0.003)
                    merge_container.markdown(merged_text)
                    if merged_text and not merged_text.startswith("生成失败"):
                        full_text = merged_text
                        status.success("✅ 一致性合并审查完成")
                except Exception as e:
                    status.warning(f"⚠️ 一致性合并审查失败（保留原始拼接结果）: {e}")

            # 合并审查步骤的 Token 也累加
            merge_usage = getattr(engine, "last_usage", None) or {}
            if merge_usage.get("total_tokens", 0) > 0:
                _chunk_usage["prompt_tokens"] += merge_usage["prompt_tokens"]
                _chunk_usage["completion_tokens"] += merge_usage["completion_tokens"]
                _chunk_usage["total_tokens"] += merge_usage["total_tokens"]

            # 存储分段模式的累计 Token 用量
            if _chunk_usage["total_tokens"] > 0:
                st.session_state[f"token_usage_{agent_type}"] = {
                    "prompt_tokens": _chunk_usage["prompt_tokens"],
                    "completion_tokens": _chunk_usage["completion_tokens"],
                    "total_tokens": _chunk_usage["total_tokens"],
                    "duration_sec": 0,  # 分段模式耗时在下方统一计算
                    "provider": engine.provider,
                    "model": engine.model,
                    "is_actual": True,
                }

            result_container.empty()
        else:
            status.info(f"📝 正在生成 {agent_type} ...")
            full_text = _generate_single_doc(engine, prompt_mgr, agent_type, code, ctx,
                                              custom_template, result_container)
    else:
        status.info(f"📝 正在生成 {agent_type} ...")
        full_text = _generate_single_doc(engine, prompt_mgr, agent_type, code, ctx,
                                          custom_template, result_container)

    # 保存结果到活动模块
    mod_docs = active_docs()
    # 版本记录：保存旧版本用于 Diff
    if agent_type in mod_docs:
        if agent_type not in st.session_state.doc_versions:
            st.session_state.doc_versions[agent_type] = []
        st.session_state.doc_versions[agent_type].append(mod_docs[agent_type])
        st.session_state.doc_versions[agent_type] = st.session_state.doc_versions[agent_type][-5:]

    mod_docs[agent_type] = full_text
    sync_active_views()

    # 质量校验
    validation = validate_document(agent_type, full_text, custom_template=custom_template)

    # 代码-文档一致性校验（LLM 幻觉缓解）
    if not full_text.startswith("生成失败"):
        # 确保解析缓存可用（即使用户未展开 Dashboard 预览）
        if not st.session_state.get("_parser_cache_info") and code:
            from code_parser import CodeParser
            st.session_state._parser_cache_info = CodeParser().analyze(code)
        if st.session_state.get("_parser_cache_info"):
            code_analysis = st.session_state._parser_cache_info
            consistency_report = validate_code_document_consistency(
                agent_type, full_text, code_analysis
            )
            validation.results.extend(consistency_report.results)

    st.session_state.generation_history.append({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "module": config["module_name"], "doc_type": agent_type,
        "status": "成功" if not full_text.startswith("生成失败") else "失败",
        "validation": validation.summary(),
    })
    _persist()

    # ── 审查修订 ──
    if review_mode and review_provider.get("api_key") and not full_text.startswith("生成失败"):
        status.info(f"🔍 审查修订中...")
        try:
            review_engine = _make_engine(review_provider)
        except Exception as e:
            st.error(f"❌ 审查引擎初始化失败: {e}")
            return

        review_prompt = prompt_mgr.get_review_prompt(agent_type, full_text, code, base_context)
        review_container = st.empty()
        reviewed = ""
        try:
            for c in review_engine.stream_generate(review_prompt):
                reviewed += c
                review_container.markdown(reviewed + "▌")
                time.sleep(0.003)
        except Exception as e:
            review_container.error(f"❌ 审查出错: {e}")
            return
        review_container.markdown(reviewed)
        st.session_state[f"original_{agent_type}"] = full_text
        active_docs()[agent_type] = reviewed
        sync_active_views()
        st.session_state.generation_history.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "module": config["module_name"],
            "doc_type": f"{agent_type} (审查修订)", "status": "成功",
        })
        _persist()

    status.success(f"✅ {agent_type} 文档生成完成！")

    # ── 显示实际 Token 消耗 ──
    _render_token_usage(agent_type)
