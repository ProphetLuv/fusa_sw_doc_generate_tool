# -*- coding: utf-8 -*-
"""
软件功能安全文档生成器 —— Streamlit 主界面入口
7 Agent 架构：SRS / SAD / FMEA / DFA / SDD / TC-UNIT / TC-INTEGRATION 各一个独立 Agent

模块拆分结构：
  app/
    app_utils.py      — 工具函数、常量、持久化、引擎创建
    app_sidebar.py    — 侧边栏配置面板
    app_dashboard.py  — 仪表盘渲染与批量生成
    app_workspace.py  — Agent 工作区与单文档生成
    app_results.py    — 结果展示与历史记录
"""

import streamlit as st

from app.app_utils import init_session_state, _load_persisted
from app.app_sidebar import render_sidebar
from app.app_dashboard import render_main_area


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
    :root {
        --metric-card-bg: #f8f9fa;
        --metric-card-border: #1f4e79;
        --disclaimer-bg: #fff3cd;
        --disclaimer-border: #ffc107;
        --disclaimer-color: #856404;
    }
    .main-title {
        font-size: 2.2rem; font-weight: 700; color: inherit;
        text-align: center; margin-bottom: 0.5rem;
    }
    .sub-title {
        font-size: 1rem; color: inherit; opacity: 0.75; text-align: center; margin-bottom: 2rem;
    }
    .metric-card {
        background: var(--metric-card-bg); border-radius: 8px; padding: 12px 16px;
        text-align: center; border-left: 4px solid var(--metric-card-border);
    }
    .agent-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 12px; padding: 24px; color: white; cursor: pointer;
        display: flex; flex-direction: column; transition: transform 0.2s; min-height: 200px;
    }
    .agent-card:hover { transform: translateY(-4px); box-shadow: 0 8px 25px rgba(0,0,0,0.15); }
    .agent-card h3 { margin: 8px 0 4px 0; font-size: 1.3rem; text-align: center; }
    .agent-card p { font-size: 0.85rem; opacity: 0.95; margin: 4px 0; }
    .agent-card .status { font-size: 0.75rem; margin-top: 12px; padding: 4px 10px;
        border-radius: 12px; display: inline-block; }
    .status-done { background: rgba(255,255,255,0.4); color: #1a1a2e; font-weight: 600; }
    .status-pending { background: rgba(255,255,255,0.18); color: rgba(255,255,255,0.95); }
    .disclaimer-box {
        background: var(--disclaimer-bg); border: 1px solid var(--disclaimer-border); border-radius: 6px;
        padding: 12px; margin-top: 16px; font-size: 0.85rem; color: var(--disclaimer-color);
    }
    .stDownloadButton > button { width: 100%; }

    /* ---- 响应式布局：窄屏自动换行 ---- */
    @media (max-width: 900px) {
        [data-testid="column"] { min-width: 45% !important; }
    }
    @media (max-width: 600px) {
        [data-testid="column"] { min-width: 100% !important; }
    }

    /* ---- 暗色主题适配 ---- */
    @media (prefers-color-scheme: dark) {
        .metric-card { background: #1e1e2e; border-left-color: #5b8def; }
        .disclaimer-box { background: #3b2e00; border-color: #b8860b; color: #f0d060; }
    }
    /* Streamlit 内置暗色主题适配 */
    [data-testid="stAppViewContainer"][data-theme="dark"] .metric-card {
        background: #1e1e2e; border-left-color: #5b8def;
    }
    [data-testid="stAppViewContainer"][data-theme="dark"] .disclaimer-box {
        background: #3b2e00; border-color: #b8860b; color: #f0d060;
    }
    /* Streamlit 暗色主题下 info/warning 提示框文字可读性增强 */
    [data-testid="stAlert"] p { color: inherit; }
</style>
""", unsafe_allow_html=True)


# ======================================================================
# Session State 初始化 & 历史加载
# ======================================================================

init_session_state()
_load_persisted()


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
