# -*- coding: utf-8 -*-
"""
软件功能安全文档生成器 —— Streamlit 主界面入口
6 Agent 架构：SRS / SAD / FMEA / SDD / TC-UNIT / TC-INTEGRATION 各一个独立 Agent
"""

import streamlit as st
import time
import json
import os
import io
import zipfile

from llm_engine import LLMEngine, DEFAULT_MODELS, DASHSCOPE_BASE_URL, DEEPSEEK_BASE_URL, GLM_BASE_URL, KIMI_BASE_URL, PROVIDER_BASE_URLS, estimate_tokens, estimate_cost
from code_parser import CodeParser
from prompts import PromptManager
from doc_exporter import export_to_word, export_fmea_to_excel
from template_parser import parse_template, get_supported_extensions
from validator import validate_document

# ======================================================================
# 页面配置
# ======================================================================

st.set_page_config(
    page_title="软件功能安全文档生成器",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ======================================================================
# 自定义样式
# ======================================================================

st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem; font-weight: 700; color: inherit;
        text-align: center; margin-bottom: 0.5rem;
    }
    .sub-title {
        font-size: 1rem; color: inherit; opacity: 0.6; text-align: center; margin-bottom: 2rem;
    }
    .metric-card {
        background: #f8f9fa; border-radius: 8px; padding: 12px 16px;
        text-align: center; border-left: 4px solid #1f4e79;
    }
    .agent-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 12px; padding: 24px; color: white; cursor: pointer;
        display: flex; flex-direction: column; transition: transform 0.2s; min-height: 200px;
    }
    .agent-card:hover { transform: translateY(-4px); box-shadow: 0 8px 25px rgba(0,0,0,0.15); }
    .agent-card h3 { margin: 8px 0 4px 0; font-size: 1.3rem; text-align: center; }
    .agent-card p { font-size: 0.85rem; opacity: 0.9; margin: 4px 0; }
    .agent-card .status { font-size: 0.75rem; margin-top: 12px; padding: 4px 10px;
        border-radius: 12px; display: inline-block; }
    .status-done { background: rgba(255,255,255,0.25); }
    .status-pending { background: rgba(255,255,255,0.1); }
    .disclaimer-box {
        background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px;
        padding: 12px; margin-top: 16px; font-size: 0.85rem; color: #856404;
    }
    .stDownloadButton > button { width: 100%; }

    /* ---- 暗色主题适配 ---- */
    @media (prefers-color-scheme: dark) {
        .metric-card { background: #1e1e2e; border-left-color: #5b8def; }
        .disclaimer-box { background: #3b2e00; border-color: #b8860b; color: #f0d060; }
    }
</style>
""", unsafe_allow_html=True)

# ======================================================================
# Agent 元数据
# ======================================================================

_AGENT_META = {
    "SRS":  {"icon": "📋", "name": "SRS Agent", "full": "软件需求规格说明",
             "desc": "从代码提取功能需求、接口需求、安全需求，生成完整的 SRS 文档",
             "color": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"},
    "SAD":  {"icon": "🏗️", "name": "SAD Agent", "full": "软件架构设计",
             "desc": "分析模块分解、组件接口、数据流、中断调度，生成架构设计文档",
             "color": "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)"},
    "FMEA": {"icon": "⚠️", "name": "FMEA Agent", "full": "失效模式与影响分析",
             "desc": "识别失效模式、评估 RPN、制定缓解措施（自动注入 SRS + SAD 上下文）",
             "color": "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)"},
    "SDD":  {"icon": "📐", "name": "SDD Agent", "full": "软件详细设计",
             "desc": "深入分析函数级设计、数据结构、算法逻辑，生成详细设计文档",
             "color": "linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)"},
    "TC-UNIT":   {"icon": "🧪", "name": "TC-UNIT Agent",  "full": "单元测试用例",
             "desc": "针对每个函数设计单元测试，含 Unity/GTest 代码、覆盖矩阵和通过准则",
             "color": "linear-gradient(135deg, #fa709a 0%, #fee140 100%)"},
    "TC-INTEGRATION": {"icon": "🔗", "name": "TC-INTEG Agent", "full": "集成测试用例",
             "desc": "验证模块间接口、数据流、控制流、时序与故障注入的集成测试",
             "color": "linear-gradient(135deg, #f7971e 0%, #ffd200 100%)"},
}

# ======================================================================
# Session State 初始化
# ======================================================================

if "generated_docs" not in st.session_state:
    st.session_state.generated_docs = {}
if "generation_history" not in st.session_state:
    st.session_state.generation_history = []
if "current_agent" not in st.session_state:
    st.session_state.current_agent = None
if "shared_code" not in st.session_state:
    st.session_state.shared_code = ""
if "agent_templates" not in st.session_state:
    st.session_state.agent_templates = {}
if "doc_versions" not in st.session_state:
    st.session_state.doc_versions = {}  # {agent_type: [old_content, ...]}
if "batch_checkpoint" not in st.session_state:
    st.session_state.batch_checkpoint = {}  # {agent_type: status}

# ── 结果持久化 ──
_SAVE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_results.json")

def _load_persisted():
    """启动时从本地 JSON 加载历史结果。"""
    if os.path.exists(_SAVE_FILE):
        try:
            with open(_SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("generated_docs"):
                st.session_state.generated_docs = data["generated_docs"]
            if data.get("history"):
                st.session_state.generation_history = data["history"]
        except Exception:
            pass

def _persist():
    """将当前结果保存到本地 JSON。"""
    try:
        with open(_SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "generated_docs": st.session_state.generated_docs,
                "history": st.session_state.generation_history[-50:],
            }, f, ensure_ascii=False)
    except Exception:
        pass

_load_persisted()

# ── 日志系统 ──
_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generation_log.jsonl")

def _log_generation(doc_type: str, module_name: str, provider: str, model: str,
                    prompt_tokens: int, output_tokens: int, duration: float,
                    success: bool, error: str = ""):
    """记录每次生成的详细日志（追加写入 JSONL 文件）。"""
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
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

# ======================================================================
# 侧边栏
# ======================================================================

def render_sidebar():
    """渲染侧边栏：共享配置面板（模型 / API Key / ASIL / 模板）。"""
    st.sidebar.markdown("### ⚙️ 配置面板")

    config_mode = st.sidebar.radio(
        "配置方式", options=["手动填写", "导入 JSON 配置"],
        horizontal=True, label_visibility="collapsed",
    )

    _JSON_TEMPLATE = """{
  "provider": "deepseek",
  "api_key": "sk-xxx",
  "api_keys": ["sk-key2", "sk-key3"],
  "api_base_URL": "https://api.deepseek.com/v1",
  "model": "deepseek-v4-pro",
  "max_tokens": 8192,
  "temperature": 0.2,
  "module_name": "MotorController",
  "asil_level": "ASIL B"
}"""

    if "json_config" not in st.session_state:
        st.session_state.json_config = {}

    if config_mode == "导入 JSON 配置":
        config = _render_json_mode(_JSON_TEMPLATE)
    else:
        config = _render_manual_mode()

    return config


def _render_json_mode(template: str):
    """JSON 导入模式。"""
    st.sidebar.markdown("##### 📂 上传配置文件")
    uploaded = st.sidebar.file_uploader("选择 JSON 配置文件", type=["json"],
                                        help="上传后自动填充所有配置项")

    if uploaded is not None:
        try:
            raw = uploaded.read().decode("utf-8")
            cfg = json.loads(raw)
            st.session_state.json_config = cfg
            st.sidebar.success(f"✅ 已加载配置（provider: {cfg.get('provider', '未指定')}）")
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            st.sidebar.error(f"❌ 解析失败: {e}")
            cfg = st.session_state.json_config
    else:
        cfg = st.session_state.json_config

    if not cfg:
        st.sidebar.info("👆 请上传 JSON 配置文件")
        st.sidebar.markdown("---")
        st.sidebar.markdown("##### 📋 配置模板")
        st.sidebar.code(template, language="json")
        st.sidebar.caption("复制上方模板，修改后保存为 .json 文件上传")
        return _empty_config()

    st.sidebar.markdown("---")
    st.sidebar.markdown("##### 📋 已加载配置")
    provider = cfg.get("provider", "openai")
    st.sidebar.text(f"供应商:   {provider}")
    st.sidebar.text(f"模型:     {cfg.get('model', DEFAULT_MODELS.get(provider, 'gpt-4o'))}")
    st.sidebar.text(f"Base URL: {cfg.get('api_base', '默认')}")
    st.sidebar.text(f"Max Tokens: {cfg.get('max_tokens', 8192)}")
    st.sidebar.text(f"Temperature: {cfg.get('temperature', 0.2)}")
    st.sidebar.text(f"模块名称: {cfg.get('module_name', '目标模块')}")
    st.sidebar.text(f"ASIL:     {cfg.get('asil_level', 'ASIL B')}")
    if cfg.get("api_key"):
        st.sidebar.caption("🔑 API Key 已加载（已隐藏）")

    # ── 配置导出（紧跟 LLM 配置）──
    export_cfg = {"provider": provider,
                  "api_key": cfg.get("api_key", ""),
                  "api_base": cfg.get("api_base") or "",
                  "model": cfg.get("model") or DEFAULT_MODELS.get(provider, "gpt-4o")}
    st.sidebar.download_button(
        "💾 导出当前 LLM 配置为 JSON",
        data=json.dumps(export_cfg, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="llm_config.json", mime="application/json",
        use_container_width=True, key="export_config_btn",
    )

    # 支持 JSON 中的 api_keys 数组（多 Key 并发）
    json_api_keys = cfg.get("api_keys", [])
    if isinstance(json_api_keys, str):
        json_api_keys = [k.strip() for k in json_api_keys.splitlines() if k.strip()]
    primary_key = cfg.get("api_key", "")
    all_keys = ([primary_key] + json_api_keys) if primary_key else json_api_keys

    return {
        "provider": provider,
        "api_key": primary_key,
        "api_base": cfg.get("api_base") or None,
        "model": cfg.get("model") or DEFAULT_MODELS.get(provider, "gpt-4o"),
        "max_tokens": cfg.get("max_tokens", 8192),
        "temperature": cfg.get("temperature", 0.2),
        "module_name": cfg.get("module_name", "目标模块"),
        "asil_level": cfg.get("asil_level", "ASIL B"),
        "api_keys": all_keys,
    }


def _render_manual_mode():
    """手动填写模式。"""
    provider = st.sidebar.selectbox(
        "模型提供商",
        options=["openai", "anthropic", "dashscope", "deepseek", "glm", "kimi", "custom"],
        format_func=lambda x: {
            "openai": "OpenAI (GPT)", "anthropic": "Anthropic (Claude)",
            "dashscope": "通义千问 (DashScope)", "deepseek": "DeepSeek",
            "glm": "智谱 GLM (ChatGLM)", "kimi": "Kimi (Moonshot)",
            "custom": "自定义兼容 API",
        }.get(x, x),
        index=0,
    )

    api_key = st.sidebar.text_input("API Key", type="password", placeholder="sk-...",
                                     help="密钥仅保存在当前会话内存中，不会落盘存储")

    # ── 并发 Key 池（可选）──
    with st.sidebar.expander("🔑 并发 Key 池（可选）", expanded=False):
        extra_keys_raw = st.text_area(
            "额外 API Key（每行一个）",
            value="",
            height=100,
            placeholder="sk-key2\nsk-key3\nsk-key4",
            help="分段并发生成时，每个分段使用不同 Key 轮转调用，避免单 Key 速率限制。\n"
                 "留空则所有分段共用上方主 Key。",
            key="extra_api_keys",
        )
        extra_keys = [k.strip() for k in extra_keys_raw.strip().splitlines() if k.strip()]
        if extra_keys:
            st.caption(f"✅ 已配置 {len(extra_keys)} 个额外 Key，并发时将轮转使用共 {len(extra_keys) + 1} 个 Key")

    default_base_url = PROVIDER_BASE_URLS.get(provider, "")
    api_base = st.sidebar.text_input("Base URL", value=default_base_url,
                                      placeholder="https://your-api.com/v1" if provider == "custom" else "留空使用默认地址",
                                      help="可修改为代理地址或内网部署地址")

    default_model = DEFAULT_MODELS.get(provider, "gpt-4o")
    model = st.sidebar.text_input("模型名称", value=default_model, placeholder=default_model)

    # ── 配置导出（紧跟 LLM 配置，紧贴模型名称下方）──
    export_cfg = {"provider": provider, "api_key": api_key, "api_base": api_base or "",
                  "model": model or default_model}
    st.sidebar.download_button(
        "💾 导出当前 LLM 配置为 JSON",
        data=json.dumps(export_cfg, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="llm_config.json", mime="application/json",
        use_container_width=True, key="export_config_btn",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("##### 📦 项目信息")
    module_name = st.sidebar.text_input("软件模块名称", value="目标模块", placeholder="如: MotorController",
                                         help="被测软件模块的名称，将用于文档标题和需求ID前缀")
    asil_level = st.sidebar.selectbox("ASIL 等级",
                                       options=["QM", "ASIL A", "ASIL B", "ASIL C", "ASIL D"], index=2,
                                       help="ISO 26262 安全等级，影响文档内容和方法要求")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🔧 高级选项")

    # 根据 ASIL 等级给出推荐参数值
    _TOKEN_DEFAULT = {
        "QM":     4096,
        "ASIL A": 8192,
        "ASIL B": 8192,
        "ASIL C": 12288,
        "ASIL D": 16384,
    }
    _TEMP_DEFAULT = {
        "QM":     0.30,
        "ASIL A": 0.20,
        "ASIL B": 0.15,
        "ASIL C": 0.10,
        "ASIL D": 0.05,
    }
    _TOKEN_HINT = {
        "QM":     "QM 文档较简略，推荐 4096~8192",
        "ASIL A": "推荐 8192~12288",
        "ASIL B": "推荐 8192~16384",
        "ASIL C": "文档详细，推荐 12288~20480",
        "ASIL D": "最详尽，推荐 16384~32768",
    }
    _TEMP_HINT = {
        "QM":     "可适当提高创造性（0.3~0.5）",
        "ASIL A": "建议 0.2~0.3",
        "ASIL B": "建议 0.1~0.2，确保准确性",
        "ASIL C": "建议 0.1~0.15，高确定性",
        "ASIL D": "建议 0.0~0.1，最高确定性",
    }

    # ASIL 切换时自动更新推荐值
    if "_last_asil" not in st.session_state or st.session_state._last_asil != asil_level:
        st.session_state._last_asil = asil_level
        st.session_state._auto_tokens = _TOKEN_DEFAULT.get(asil_level, 8192)
        st.session_state._auto_temp = _TEMP_DEFAULT.get(asil_level, 0.20)

    token_hint = _TOKEN_HINT.get(asil_level, "")
    temp_hint = _TEMP_HINT.get(asil_level, "")

    max_tokens = st.sidebar.slider(
        "Max Tokens",
        min_value=1024, max_value=32768,
        value=st.session_state.get("_auto_tokens", 8192), step=1024,
        help="单次生成最大 token 数。值越大文档越长，截断时请增大此值或启用分段并发生成。"
    )
    st.sidebar.caption(f"💡 {token_hint}")

    temperature = st.sidebar.slider(
        "Temperature",
        min_value=0.0, max_value=1.0,
        value=st.session_state.get("_auto_temp", 0.20), step=0.01,
        help="输出随机性。0=完全确定，0.2=推荐值，0.5+=创造性增强（需求文档不建议）。"
    )
    st.sidebar.caption(f"💡 {temp_hint}")

    # 合并主 Key + 额外 Key 池
    all_keys = [api_key] + extra_keys if api_key else extra_keys

    return {
        "provider": provider, "api_key": api_key, "api_base": api_base or None,
        "model": model or default_model, "max_tokens": max_tokens,
        "temperature": temperature, "module_name": module_name,
        "asil_level": asil_level, "api_keys": all_keys,
    }


def _empty_config():
    return {
        "provider": "openai", "api_key": "", "api_base": None, "model": "gpt-4o",
        "max_tokens": 8192, "temperature": 0.2, "module_name": "目标模块",
        "asil_level": "ASIL B", "api_keys": [],
    }


def _render_agent_template_upload(agent_type: str):
    """渲染单个 Agent 的自定义文档模板上传区域。"""
    templates = st.session_state.agent_templates
    current = templates.get(agent_type)

    uploaded = st.file_uploader(
        f" 上传 {agent_type} 文档模板（可选）",
        type=get_supported_extensions(),
        help="支持 .md / .txt / .docx / .xlsx 格式，不上传则使用默认模板",
        key=f"template_{agent_type}",
    )

    if uploaded is not None:
        parsed = parse_template(uploaded)
        if parsed:
            templates[agent_type] = parsed
            st.success(f"✅ {agent_type} 模板已加载: {uploaded.name}")
        else:
            templates.pop(agent_type, None)
            st.error(f"❌ 模板解析失败: {uploaded.name}")
    elif current is not None and uploaded is None:
        # 用户清除了上传的文件
        templates.pop(agent_type, None)

    template = templates.get(agent_type)
    if template:
        preview_len = len(template)
        with st.expander(f"👁️ {agent_type} 模板预览 ({preview_len} 字符)"):
            st.code(template[:3000], language="text")
            if preview_len > 3000:
                st.caption(f"... 已截断显示（共 {preview_len} 字符）")
        if st.button(f"✕ 清除 {agent_type} 模板", key=f"clear_tpl_{agent_type}"):
            templates.pop(agent_type, None)
            st.rerun()

    return template


# ======================================================================
# 主区域 — 路由
# ======================================================================

def render_main_area(config: dict):
    """路由：Dashboard 或 Agent Workspace。"""
    current = st.session_state.get("current_agent")
    if current is None:
        _render_dashboard(config)
    else:
        _render_agent_workspace(current, config)


# ======================================================================
# Dashboard — 5 Agent 卡片
# ======================================================================

def _render_dashboard(config: dict):
    """渲染 Agent 仪表盘：6 张卡片 + 批量操作 + 已完成文档汇总。"""
    st.markdown('<p class="main-title">🛡️ 软件功能安全文档生成器</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-title">选择 Agent 开始生成 —— 每个 Agent 专注一份 ISO 26262 / ASPICE 文档</p>',
        unsafe_allow_html=True,
    )

    # 代码状态 + Token 预估
    code = st.session_state.shared_code
    if code:
        lines = code.count("\n") + 1
        tokens = estimate_tokens(code)
        cost = estimate_cost(tokens, config.get("provider", "openai"))
        st.info(f"📎 已加载代码：**{lines:,}** 行 | 预估 **{tokens:,}** tokens | 单次费用 {cost} | 切换 Agent 后代码自动保留")
    else:
        st.info("👆 进入任意 Agent 后上传 C/C++ 代码")

    # 6 张卡片
    cols = st.columns(6, gap="small")
    for col, agent_type in zip(cols, ["SRS", "SAD", "FMEA", "SDD", "TC-UNIT", "TC-INTEGRATION"]):
        meta = _AGENT_META[agent_type]
        done = agent_type in st.session_state.generated_docs
        with col:
            st.markdown(f"""
            <div style="background: {meta['color']}; border-radius: 12px; padding: 20px;
                        color: white; display: flex; flex-direction: column;
                        height: 260px;">
                <div style="text-align: center;">
                    <div style="font-size: 2.5rem;">{meta['icon']}</div>
                    <h3 style="margin: 6px 0 2px 0; font-size: 1.1rem; line-height: 1.3;">{meta['name']}</h3>
                    <p style="font-size: 0.8rem; opacity: 0.85; margin: 2px 0;">{meta['full']}</p>
                </div>
                <p style="font-size: 0.75rem; opacity: 0.75; flex-grow: 1; margin: 8px 0; line-height: 1.4;">{meta['desc']}</p>
                <div style="text-align: center;">
                    <div style="font-size: 0.7rem;
                                padding: 3px 10px; border-radius: 10px; display: inline-block;
                                background: {'rgba(255,255,255,0.3)' if done else 'rgba(255,255,255,0.1)'};">
                        {'✅ 已生成' if done else '⏳ 未生成'}
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            btn_label = "📂 打开" if not done else "📂 查看 / 重新生成"
            if st.button(btn_label, key=f"dash_{agent_type}", use_container_width=True):
                st.session_state.current_agent = agent_type
                st.rerun()

    # ── 批量操作区 ──
    st.markdown("---")
    docs = st.session_state.generated_docs
    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        if st.button("🚀 一键全部生成", use_container_width=True,
                     disabled=(not code or not config["api_key"])):
            _batch_generate_all(config)
    with bc2:
        if docs:
            zip_bytes = _export_all_as_zip(docs, config["module_name"], config.get("asil_level", "ASIL B"))
            st.download_button("📦 打包下载全部 (.zip)", data=zip_bytes,
                               file_name=f"{config['module_name']}_全部文档.zip",
                               mime="application/zip", use_container_width=True, key="zip_all")
        else:
            st.button("📦 打包下载（暂无文档）", disabled=True, use_container_width=True)
    with bc3:
        if st.button("🗑️ 清空全部结果", use_container_width=True):
            st.session_state.generated_docs = {}
            _persist()
            st.rerun()

    if not config["api_key"]:
        st.warning("⚠️ 请在侧边栏输入 API Key 后使用批量功能")

    # 已完成文档汇总
    if docs:
        st.markdown("---")
        st.markdown(f"### 📄 已生成文档汇总（{len(docs)} / 6）")
        sum_cols = st.columns(len(docs))
        for i, (dt, content) in enumerate(docs.items()):
            with sum_cols[i]:
                meta = _AGENT_META.get(dt, {"icon": "📄"})
                st.markdown(f"**{meta['icon']} {dt}**")
                st.caption(f"{len(content):,} 字符")
                st.download_button(
                    "📥 下载 .md", data=content.encode("utf-8"),
                    file_name=f"{config['module_name']}_{dt}.md",
                    mime="text/markdown", key=f"dash_dl_{dt}",
                    use_container_width=True,
                )


def _batch_generate_all(config: dict):
    """按 SRS→SAD→FMEA→SDD→TC-UNIT→TC-INTEGRATION 顺序批量生成全部文档。"""
    order = ["SRS", "SAD", "FMEA", "SDD", "TC-UNIT", "TC-INTEGRATION"]
    _AGENT_TOKEN_DEFAULT = {
        "SRS": 8192, "SAD": 12288, "FMEA": 16384,
        "SDD": 12288, "TC-UNIT": 12288, "TC-INTEGRATION": 12288,
    }
    code = st.session_state.shared_code
    prompt_mgr = PromptManager()
    base_ctx = {"module_name": config["module_name"], "asil_level": config["asil_level"]}

    try:
        engine = _make_engine(config)
    except Exception as e:
        st.error(f"❌ 引擎初始化失败: {e}")
        return

    progress = st.progress(0, text="批量生成中...")

    # #9 断点续传：检查是否有已完成的节点
    checkpoint = st.session_state.batch_checkpoint
    start_idx = 0
    if checkpoint:
        completed = [a for a in order if checkpoint.get(a) == "done"]
        if completed:
            start_idx = order.index(completed[-1]) + 1
            st.info(f"🔄 检测到上次进度，从 {order[start_idx]} 继续生成（已完成 {len(completed)}/{len(order)}）")

    for i, agent_type in enumerate(order):
        if i < start_idx:
            continue

        progress.progress(i / len(order), text=f"正在生成 {agent_type}（{i+1}/{len(order)}）...")

        ctx = dict(base_ctx)
        if agent_type == "FMEA":
            prior = {}
            if "SRS" in st.session_state.generated_docs:
                prior["SRS"] = st.session_state.generated_docs["SRS"]
            if "SAD" in st.session_state.generated_docs:
                prior["SAD"] = st.session_state.generated_docs["SAD"]
            if prior:
                ctx["prior_docs"] = prior

        container = st.empty()
        # 每个 Agent 使用独立的 max_tokens
        engine.max_tokens = _AGENT_TOKEN_DEFAULT.get(agent_type, config.get("max_tokens", 8192))
        text = _generate_single_doc(engine, prompt_mgr, agent_type, code, ctx, st.session_state.agent_templates.get(agent_type), container)
        st.session_state.generated_docs[agent_type] = text

        # #8 质量校验（传入模板用于结构对比）
        template = st.session_state.agent_templates.get(agent_type)
        validation = validate_document(agent_type, text, custom_template=template)
        st.session_state.generation_history.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "module": config["module_name"], "doc_type": agent_type,
            "status": "成功" if not text.startswith("生成失败") else "失败",
            "validation": validation.summary(),
        })

        # #9 保存检查点
        checkpoint[agent_type] = "done"
        _persist()

    progress.progress(1.0, text="✅ 全部完成！")
    st.session_state.batch_checkpoint = {}
    _persist()
    st.success(" 6 份文档全部生成完成！")


def _export_all_as_zip(docs: dict, module_name: str, asil_level: str = "ASIL B") -> bytes:
    """将所有已生成文档打包为 zip（含 .md + .docx，FMEA 额外含 .xlsx）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for dt, content in docs.items():
            zf.writestr(f"{module_name}_{dt}.md", content)
            try:
                metadata = {
                    "doc_id": f"DOC-{dt}-{module_name}",
                    "version": "1.0",
                    "module_name": module_name,
                    "asil_level": asil_level,
                    "date": time.strftime("%Y-%m-%d"),
                }
                word_bytes = export_to_word(title=f"{module_name} {dt} 文档", markdown=content, metadata=metadata)
                zf.writestr(f"{module_name}_{dt}.docx", word_bytes)
            except Exception:
                pass
            if dt == "FMEA":
                try:
                    zf.writestr(f"{module_name}_FMEA.xlsx", export_fmea_to_excel(content))
                except Exception:
                    pass
    return buf.getvalue()


# ======================================================================
# Agent Workspace — 单个 Agent 工作区
# ======================================================================

def _render_agent_workspace(agent_type: str, config: dict):
    """渲染单个 Agent 的工作区：代码输入 + 选项 + 生成 + 结果。"""
    meta = _AGENT_META.get(agent_type, {"icon": "📄", "name": agent_type, "full": agent_type, "desc": ""})

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
            st.session_state.generated_docs.pop(agent_type, None)
            _persist()
            st.rerun()

    st.caption(meta["desc"])
    st.markdown("---")

    # ── 自定义文档模板 ──
    agent_template = _render_agent_template_upload(agent_type)

    # ── 代码输入 ──
    code = _render_code_input()

    # ── FMEA 前置上下文提示 ──
    _fmea_missing_prior = False
    if agent_type == "FMEA":
        has_srs = "SRS" in st.session_state.generated_docs
        has_sad = "SAD" in st.session_state.generated_docs
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

    # ── 生成选项（折叠面板）──
    # 每个 Agent 的推荐 Max Tokens
    _AGENT_TOKEN_DEFAULT = {
        "SRS": 8192, "SAD": 12288, "FMEA": 16384,
        "SDD": 12288, "TC-UNIT": 12288, "TC-INTEGRATION": 12288,
    }
    with st.expander("⚙️ 生成选项", expanded=False):
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
                "📏 Max Tokens", min_value=1024, max_value=65536,
                value=_AGENT_TOKEN_DEFAULT.get(agent_type, config.get("max_tokens", 8192)),
                step=1024,
                help=f"当前 Agent 单次生成最大 token 数（全局值: {config.get('max_tokens', 8192)}）。"
                     f"文档被截断时请增大此值。",
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

    # ── 生成按钮 ──
    can_generate = bool(code) and bool(config["api_key"])
    if not config["api_key"]:
        st.warning("⚠️ 请在侧边栏输入 API Key")
    if not code:
        st.info("👆 请上传 C/C++ 代码文件")

    generate_clicked = st.button(
        f"🚀 生成 {agent_type} 文档", type="primary",
        use_container_width=True, disabled=not can_generate,
    )

    if agent_template:
        st.info(f" 已启用 {agent_type} 自定义文档模板")

    # ── 执行生成 ──
    if generate_clicked and can_generate:
        # 使用 Agent 级别的 max_tokens 覆盖全局配置
        agent_config = dict(config)
        agent_config["max_tokens"] = agent_max_tokens
        _run_single_agent_generation(agent_type, code, agent_config, chunked_mode, review_mode, review_provider_cfg, agent_template)

    # ── 显示结果 ──
    _render_agent_result(agent_type, config)


# ======================================================================
# 代码输入（共享）
# ======================================================================

def _render_code_input() -> str:
    """渲染代码输入区，结果存入 session_state.shared_code。含输入校验。"""
    tab_upload, tab_zip, tab_paste = st.tabs(["📂 上传文件", "📁 上传项目压缩包", "📝 粘贴代码"])

    code = ""
    with tab_upload:
        uploaded_files = st.file_uploader(
            "上传 C/C++ 源文件",
            type=["c", "h", "cpp", "hpp", "cc", "cxx"],
            accept_multiple_files=True,
            help="支持 .c / .h / .cpp / .hpp / .cc / .cxx 文件，可多选",
            key="agent_file_upload",
        )
        # 检测用户是否删除了已上传的文件 → 同步清空缓存
        _had_files = st.session_state.get("_had_uploaded_files", False)
        _has_files_now = bool(uploaded_files)
        if _had_files and not _has_files_now:
            st.session_state.shared_code = ""
        st.session_state._had_uploaded_files = _has_files_now

        if uploaded_files:
            code_parts = []
            skipped = []
            for f in uploaded_files:
                raw = f.read()
                # 校验：空文件
                if len(raw) == 0:
                    skipped.append(f"{f.name}（空文件）")
                    continue
                # 校验：文件过大（>500KB 警告）
                if len(raw) > 500 * 1024:
                    skipped.append(f"{f.name}（>{len(raw)//1024}KB，过大）")
                    continue
                content = raw.decode("utf-8", errors="replace")
                # 校验：是否包含 C/C++ 特征
                if not _looks_like_c_code(content):
                    skipped.append(f"{f.name}（非 C/C++ 内容）")
                    continue
                code_parts.append(f"// ===== {f.name} =====\n{content}")
            if skipped:
                st.warning(f"⚠️ 已跳过 {len(skipped)} 个文件: " + "、".join(skipped))
            if code_parts:
                code = "\n\n".join(code_parts)
                st.session_state.shared_code = code

    with tab_zip:
        st.caption("将整个项目文件夹打包为 .zip 上传")
        zip_file = st.file_uploader("上传项目压缩包 (.zip)", type=["zip"], key="agent_zip_upload")
        if zip_file is not None:
            code = _extract_code_from_zip(zip_file)
            if code:
                st.session_state.shared_code = code

    with tab_paste:
        pasted = st.text_area(
            "粘贴 C/C++ 代码", height=300,
            placeholder="// 在此粘贴嵌入式 C/C++ 代码...",
            key="agent_paste",
        )
        if pasted:
            if not _looks_like_c_code(pasted):
                st.warning("⚠️ 粘贴内容不像 C/C++ 代码（缺少 #include、函数定义等特征），仍可使用但结果可能不佳")
            code = pasted
            st.session_state.shared_code = code

    # 如果没有新输入，使用缓存
    if not code:
        code = st.session_state.shared_code

    if code:
        _render_code_preview(code)

    return code


def _looks_like_c_code(text: str) -> bool:
    """简单检测文本是否具有 C/C++ 代码特征。"""
    indicators = ["#include", "int ", "void ", "char ", "struct ", "typedef ",
                  "return ", "if (", "for (", "while (", "{", "}", "->", "::"]
    sample = text[:3000]  # 只检查前 3000 字符
    hits = sum(1 for ind in indicators if ind in sample)
    return hits >= 2


def _extract_code_from_zip(zip_file) -> str:
    """从 zip 中提取 C/C++ 源文件。"""
    import zipfile, io
    CPP_EXTENSIONS = {".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".hxx", ".hh", ".inl"}
    try:
        raw = zip_file.read()
        zf = zipfile.ZipFile(io.BytesIO(raw), "r")
    except zipfile.BadZipFile:
        st.error("❌ 无效的 zip 文件")
        return ""

    code_parts, file_tree, all_names = [], [], zf.namelist()
    dirs = [n for n in all_names if "/" in n]
    common = os.path.commonprefix(dirs).rstrip("/") if dirs else ""

    for name in sorted(all_names):
        if name.endswith("/"):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in CPP_EXTENSIONS:
            continue
        try:
            content = zf.read(name).decode("utf-8", errors="replace")
        except Exception:
            continue
        rel_path = name
        if common and rel_path.startswith(common + "/"):
            rel_path = rel_path[len(common) + 1:]
        code_parts.append(f"// ===== {rel_path} =====\n{content}")
        file_tree.append(f"  📄 {rel_path}")
    zf.close()

    if not code_parts:
        st.warning("⚠️ zip 中未找到 C/C++ 源文件")
        return ""

    st.success(f"✅ 提取了 **{len(code_parts)}** 个源文件")
    with st.expander(f"📁 文件列表（{len(code_parts)} 个）", expanded=False):
        st.markdown("```\n" + "\n".join(file_tree) + "\n```")
    return "\n\n".join(code_parts)


def _render_code_preview(code: str):
    """渲染代码统计信息 + Token/费用预估。"""
    parser = CodeParser()
    info = parser.analyze(code)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1: st.metric("代码行数", f"{info['lines']:,}")
    with c2: st.metric("函数数量", info["functions"])
    with c3: st.metric("结构体/枚举", info["structs"])
    with c4: st.metric("宏定义", info["macros"])
    with c5: st.metric("预估 Token", f"{info['estimated_tokens']:,}")
    with c6: st.metric("代码大小", f"{len(code) // 1024} KB")

    if info["function_names"]:
        with st.expander(f"🔍 检测到 {info['functions']} 个函数"):
            st.code("\n".join(info["function_names"]), language="text")
    if info["includes"]:
        with st.expander(f"📎 {len(info['includes'])} 个头文件"):
            st.code("\n".join(info["includes"]), language="text")
    with st.expander("👁️ 代码预览"):
        st.code(code, language="c")


# ======================================================================
# 单 Agent 生成
# ======================================================================

def _run_single_agent_generation(agent_type, code, config, chunked_mode, review_mode, review_provider, custom_template=None):
    """为单个 Agent 执行文档生成（支持分段并发 + 审查修订）。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    prompt_mgr = PromptManager()
    base_context = {"module_name": config["module_name"], "asil_level": config["asil_level"]}

    # FMEA 注入前置文档
    ctx = dict(base_context)
    if agent_type == "FMEA":
        prior = {}
        if "SRS" in st.session_state.generated_docs:
            prior["SRS"] = st.session_state.generated_docs["SRS"]
        if "SAD" in st.session_state.generated_docs:
            prior["SAD"] = st.session_state.generated_docs["SAD"]
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

            def _worker(ci, _, cprompt):
                chunk_engine = engine_pool[ci % len(engine_pool)]
                text = ""
                try:
                    for c in chunk_engine.stream_generate(cprompt):
                        text += c
                        containers[ci].markdown(text + "▌")
                        time.sleep(0.008)
                except Exception as e:
                    text = f"生成失败: {e}"
                containers[ci].markdown(text)
                return ci, text

            with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
                futures = {executor.submit(_worker, ci, t, p): ci for ci, (t, p) in enumerate(chunks)}
                for f in as_completed(futures):
                    ci, text = f.result()
                    chunk_results[ci] = text

            doc_title = f"# {config['module_name']} {agent_type} 文档\n\n"
            full_text = doc_title + "\n\n".join(chunk_results)
            result_container.empty()
        else:
            status.info(f"📝 正在生成 {agent_type} ...")
            full_text = _generate_single_doc(engine, prompt_mgr, agent_type, code, ctx,
                                              custom_template, result_container)
    else:
        status.info(f"📝 正在生成 {agent_type} ...")
        full_text = _generate_single_doc(engine, prompt_mgr, agent_type, code, ctx,
                                          custom_template, result_container)

    # 保存结果
    # #10 版本记录：保存旧版本用于 Diff
    if agent_type in st.session_state.generated_docs:
        if agent_type not in st.session_state.doc_versions:
            st.session_state.doc_versions[agent_type] = []
        st.session_state.doc_versions[agent_type].append(st.session_state.generated_docs[agent_type])
        # 只保留最近 5 个版本
        st.session_state.doc_versions[agent_type] = st.session_state.doc_versions[agent_type][-5:]

    st.session_state.generated_docs[agent_type] = full_text

    # #8 质量校验
    validation = validate_document(agent_type, full_text, custom_template=custom_template)
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
                time.sleep(0.008)
        except Exception as e:
            review_container.error(f"❌ 审查出错: {e}")
            return
        review_container.markdown(reviewed)
        st.session_state[f"original_{agent_type}"] = full_text
        st.session_state.generated_docs[agent_type] = reviewed
        st.session_state.generation_history.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "module": config["module_name"],
            "doc_type": f"{agent_type} (审查修订)", "status": "成功",
        })
        _persist()

    status.success(f"✅ {agent_type} 文档生成完成！")


# ======================================================================
# 引擎 & 单文档生成
# ======================================================================

def _make_engine(cfg: dict) -> LLMEngine:
    return LLMEngine(
        provider=cfg["provider"], api_key=cfg["api_key"],
        api_base=cfg.get("api_base"), model=cfg.get("model"),
        max_tokens=cfg.get("max_tokens", 8192), temperature=cfg.get("temperature", 0.2),
    )


def _generate_single_doc(engine, prompt_mgr, doc_type, code, context, custom_template, display_container=None):
    prompt = prompt_mgr.get_prompt(doc_type, code, context, custom_template=custom_template)
    full_text = ""
    error_msg = ""
    t0 = time.time()
    try:
        for chunk in engine.stream_generate(prompt):
            full_text += chunk
            if display_container is not None:
                display_container.markdown(full_text + "▌")
                time.sleep(0.008)
    except Exception as e:
        full_text = f"生成失败: {e}"
        error_msg = str(e)
    duration = time.time() - t0
    if display_container is not None:
        display_container.markdown(full_text)

    # 写入日志
    _log_generation(
        doc_type=doc_type,
        module_name=context.get("module_name", "目标模块"),
        provider=engine.provider,
        model=engine.model,
        prompt_tokens=estimate_tokens(prompt),
        output_tokens=estimate_tokens(full_text),
        duration=duration,
        success=not error_msg,
        error=error_msg,
    )
    return full_text


# ======================================================================
# Agent 结果展示 & 下载
# ======================================================================

def _generate_diff(old_text: str, new_text: str) -> str:
    """生成简易的文本 Diff 输出（unified diff 格式）。"""
    import difflib
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = difflib.unified_diff(old_lines, new_lines, fromfile="上一版本", tofile="当前版本", lineterm="")
    return "".join(diff)


def _render_agent_result(agent_type: str, config: dict):
    """渲染单个 Agent 的结果和下载按钮。"""
    docs = st.session_state.generated_docs
    if agent_type not in docs:
        return

    content = docs[agent_type]
    st.markdown("---")
    st.markdown("## 📄 生成结果")
    st.markdown(content)

    # #8 质量校验报告
    template = st.session_state.agent_templates.get(agent_type)
    validation = validate_document(agent_type, content, custom_template=template)
    with st.expander(f"🔍 质量校验报告 ({validation.summary()})", expanded=False):
        for result in validation.results:
            icon = {"error": "❌", "warning": "⚠️", "info": "️"}.get(result.severity, "ℹ️")
            st.markdown(f"{icon} **{result.check_name}**: {result.message}")
            if result.details:
                st.caption(result.details)

    # #10 文档版本对比/Diff
    versions = st.session_state.doc_versions.get(agent_type, [])
    orig_key = f"original_{agent_type}"
    if orig_key in st.session_state:
        versions.append(st.session_state[orig_key])

    if versions:
        with st.expander(f"📊 文档版本对比（{len(versions)} 个历史版本）", expanded=False):
            st.markdown(f"**当前版本** vs **上一版本**")
            old_content = versions[-1]
            diff_lines = _generate_diff(old_content, content)
            st.code(diff_lines, language="diff")

    # 原始版本对比（如果有审查修订）
    if orig_key in st.session_state:
        with st.expander("📋 查看审查前原始版本"):
            st.markdown(st.session_state[orig_key])

    st.markdown("---")
    st.markdown("#### 📥 下载文档")
    dl1, dl2, dl3 = st.columns(3)

    with dl1:
        st.download_button("📄 下载 Markdown", data=content.encode("utf-8"),
                            file_name=f"{config['module_name']}_{agent_type}.md",
                            mime="text/markdown", use_container_width=True,
                            key=f"dl_md_{agent_type}")
    with dl2:
        try:
            metadata = {
                "doc_id": f"DOC-{agent_type}-{config['module_name']}",
                "version": "1.0",
                "module_name": config["module_name"],
                "asil_level": config["asil_level"],
                "date": time.strftime("%Y-%m-%d"),
            }
            word_bytes = export_to_word(title=f"{config['module_name']} {agent_type} 文档", markdown=content, metadata=metadata)
            st.download_button("📝 下载 Word (.docx)", data=word_bytes,
                                file_name=f"{config['module_name']}_{agent_type}.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                use_container_width=True, key=f"dl_docx_{agent_type}")
        except Exception as e:
            st.error(f"Word 导出失败: {e}")

    with dl3:
        if agent_type == "FMEA":
            try:
                excel_bytes = export_fmea_to_excel(content)
                st.download_button("📊 下载 Excel (.xlsx)", data=excel_bytes,
                                    file_name=f"{config['module_name']}_FMEA.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True, key=f"dl_xlsx_{agent_type}")
            except Exception as e:
                st.error(f"Excel 导出失败: {e}")
        else:
            st.info("Excel 导出仅适用于 FMEA 文档")

    # 生成历史
    _render_history()


def _render_history():
    history = st.session_state.generation_history
    if not history:
        return
    st.markdown("---")
    with st.expander(f"📜 生成历史 ({len(history)} 条)"):
        for r in reversed(history[-20:]):
            icon = "✅" if r["status"] == "成功" else "❌"
            st.text(f"{icon} [{r['timestamp']}] {r['module']} | {r['doc_type']} | {r['status']}")


# ======================================================================
# 页脚
# ======================================================================

def render_footer():
    st.markdown("---")
    st.markdown(
        '<p class="disclaimer-box">'
        "⚠️ <strong>免责声明</strong>：本工具生成的文档由 AI 辅助产出，"
        "仅供功能安全分析参考。所有分析结论和建议措施须由具备资质的功能安全工程师进行人工审查和确认。"
        "</p>", unsafe_allow_html=True,
    )


# ======================================================================
# 入口
# ======================================================================

def main():
    config = render_sidebar()
    render_main_area(config)
    render_footer()


if __name__ == "__main__":
    main()
