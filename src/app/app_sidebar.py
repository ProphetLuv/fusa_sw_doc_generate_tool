# -*- coding: utf-8 -*-
"""
app_sidebar.py — 侧边栏配置面板（手动填写 / JSON 导入、模板上传）。
"""

import streamlit as st
import json

from llm_engine import DEFAULT_MODELS, PROVIDER_BASE_URLS
from template_parser import get_supported_extensions, parse_template

from app.app_utils import _mask_api_key, _empty_config


# ======================================================================
# 模块级常量（避免每次 rerun 重建）
# ======================================================================

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

_TEMP_HINT = {
    "QM":     "可适当提高创造性（0.3~0.5）",
    "ASIL A": "建议 0.2~0.3",
    "ASIL B": "建议 0.1~0.2，确保准确性",
    "ASIL C": "建议 0.1~0.15，高确定性",
    "ASIL D": "建议 0.0~0.1，最高确定性",
}


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
  "api_base": "https://api.deepseek.com/v1",
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
    st.sidebar.text(f"生成长度: {cfg.get('max_tokens', 8192)}")
    st.sidebar.text(f"Temperature: {cfg.get('temperature', 0.2)}")
    st.sidebar.text(f"模块名称: {cfg.get('module_name', '目标模块')}")
    st.sidebar.text(f"ASIL:     {cfg.get('asil_level', 'ASIL B')}")
    if cfg.get("api_key"):
        st.sidebar.caption("🔑 API Key 已加载（已隐藏）")

    # ── 配置导出（紧跟 LLM 配置）──
    # API Key 脱敏导出，避免明文泄露
    masked_key = _mask_api_key(cfg.get("api_key", "")) if cfg.get("api_key") else ""
    export_cfg = {
        "provider": provider,
        "api_key": masked_key,
        "api_base": cfg.get("api_base") or "",
        "model": cfg.get("model") or DEFAULT_MODELS.get(provider, "gpt-4o"),
        "max_tokens": cfg.get("max_tokens", 8192),
        "temperature": cfg.get("temperature", 0.2),
        "module_name": cfg.get("module_name", "目标模块"),
        "asil_level": cfg.get("asil_level", "ASIL B"),
    }
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
    if "_last_asil" not in st.session_state or st.session_state._last_asil != asil_level:
        st.session_state._last_asil = asil_level
        st.session_state._auto_tokens = _TOKEN_DEFAULT.get(asil_level, 8192)
        st.session_state._auto_temp = _TEMP_DEFAULT.get(asil_level, 0.20)

    # max_tokens 随 ASIL 自动设定，不做独立滑块（各 Agent 可在内部单独调整）
    max_tokens = st.session_state.get("_auto_tokens", _TOKEN_DEFAULT.get(asil_level, 8192))

    temp_hint = _TEMP_HINT.get(asil_level, "")

    temperature = st.sidebar.slider(
        "Temperature",
        min_value=0.0, max_value=1.0,
        value=st.session_state.get("_auto_temp", 0.20), step=0.01,
        help="输出随机性。0=完全确定，0.2=推荐值，0.5+=创造性增强（需求文档不建议）。"
    )
    st.sidebar.caption(f"💡 {temp_hint}")
    st.sidebar.caption(f"💡 单次生成文档长度随 ASIL 等级自动调整（当前上限约 {max_tokens} 字）。如需微调，可展开各 Agent 的「生成选项」。")

    # ── 配置导出（所有参数已就绪后导出）──
    masked_key = _mask_api_key(api_key) if api_key.strip() else ""
    export_cfg = {
        "provider": provider,
        "api_key": masked_key,
        "api_base": api_base or "",
        "model": model or default_model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "module_name": module_name,
        "asil_level": asil_level,
    }
    st.sidebar.download_button(
        "💾 导出当前 LLM 配置为 JSON",
        data=json.dumps(export_cfg, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="llm_config.json", mime="application/json",
        use_container_width=True, key="export_config_btn",
    )

    # 合并主 Key + 额外 Key 池（过滤空白 Key）
    all_keys = ([api_key] + extra_keys) if api_key.strip() else extra_keys

    return {
        "provider": provider, "api_key": api_key, "api_base": api_base or None,
        "model": model or default_model, "max_tokens": max_tokens,
        "temperature": temperature, "module_name": module_name,
        "asil_level": asil_level, "api_keys": all_keys,
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
