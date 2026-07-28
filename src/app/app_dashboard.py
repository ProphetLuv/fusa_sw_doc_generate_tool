# -*- coding: utf-8 -*-
"""
app_dashboard.py — 仪表盘渲染、批量生成、zip 打包导出。
"""

import streamlit as st
import time
import io
import os
import sys
import subprocess
import zipfile

from llm_engine import estimate_tokens, estimate_cost
from prompts import PromptManager
from code_parser import CodeParser
from validator import validate_document, validate_cross_document_traceability
from doc_exporter import export_to_word, export_fmea_to_excel

from module_detector import (
    detect_modules, build_module_code, merge_modules,
    rename_module, delete_module, sanitize_module_prefix,
)
from app.app_utils import (
    _AGENT_META,
    _get_agent_token_defaults,
    _persist,
    _make_engine,
    _generate_single_doc,
    estimate_agent_total_tokens,
    estimate_batch_total_tokens,
    active_module_name,
    active_docs,
    active_code,
    get_module_docs,
    sync_active_views,
)


def render_main_area(config: dict):
    """路由：Dashboard 或 Agent Workspace。"""
    current = st.session_state.get("current_agent")
    if current is None:
        _render_dashboard(config)
    else:
        # 延迟导入，避免循环依赖
        from app.app_workspace import _render_agent_workspace
        _render_agent_workspace(current, config)


def _render_dashboard(config: dict):
    """渲染 Agent 仪表盘：7 张卡片 + 批量操作 + 已完成文档汇总。"""
    st.markdown('<p class="main-title">🛡️ 软件功能安全文档生成器</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-title">选择 Agent 开始生成 —— 每个 Agent 专注一份 ISO 26262 / ASPICE 文档</p>',
        unsafe_allow_html=True,
    )

    # ── 📂 代码 / 工程管理区 ──
    _render_code_management(config)

    # 7 张卡片
    cols = st.columns(7, gap="small")
    for col, agent_type in zip(cols, ["SRS", "SAD", "FMEA", "DFA", "SDD", "TC-UNIT", "TC-INTEGRATION"]):
        meta = _AGENT_META[agent_type]
        done = agent_type in st.session_state.generated_docs
        with col:
            st.markdown(f"""
            <div style="background: {meta['color']}; border-radius: 12px; padding: 20px;
                        color: white; display: flex; flex-direction: column;
                        height: 240px; box-shadow: 0 2px 10px rgba(0,0,0,0.25);">
                <div style="text-align: center;">
                    <div style="font-size: 2.5rem; filter: drop-shadow(0 1px 2px rgba(0,0,0,0.3));">{meta['icon']}</div>
                    <h3 style="margin: 6px 0 2px 0; font-size: 1.1rem; line-height: 1.3;
                               color: #ffffff; text-shadow: 0 1px 3px rgba(0,0,0,0.4);">{meta['name']}</h3>
                    <p style="font-size: 0.8rem; opacity: 1; margin: 2px 0;
                              color: rgba(255,255,255,0.95);">{meta['full']}</p>
                </div>
                <p style="font-size: 0.75rem; color: rgba(255,255,255,0.92); flex-grow: 1;
                          margin: 8px 0; line-height: 1.4;">{meta['desc']}</p>
            </div>
            """, unsafe_allow_html=True)

            # 状态标签（卡片与按钮之间）
            if done:
                st.markdown('<div style="text-align: center; margin: 6px 0 2px 0;">'
                            '<span style="font-size: 0.72rem; padding: 3px 10px; border-radius: 10px;'
                            ' background: rgba(76,175,80,0.25); color: #66bb6a; font-weight: 600;">'
                            '✅ 已生成</span></div>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="text-align: center; margin: 6px 0 2px 0;">'
                            '<span style="font-size: 0.72rem; padding: 3px 10px; border-radius: 10px;'
                            ' background: rgba(158,158,158,0.15); color: #757575; font-weight: 500;">'
                            '⏳ 未生成</span></div>', unsafe_allow_html=True)

            btn_label = "📂 打开" if not done else "📂 查看 / 重新生成"
            if st.button(btn_label, key=f"dash_{agent_type}", use_container_width=True):
                st.session_state.current_agent = agent_type
                st.rerun()

    # ── 批量操作区 ──
    st.markdown("---")
    code = active_code()
    docs = active_docs()
    bc1, bc2, bc3, bc4 = st.columns(4)
    with bc1:
        if st.button("🚀 一键全部生成", use_container_width=True,
                     disabled=(not code or not config["api_key"])):
            _batch_generate_all(config)
    with bc2:
        all_docs = st.session_state.get("docs_by_module", {})
        has_any_docs = any(d for d in all_docs.values())
        if has_any_docs or docs:
            zip_bytes = _export_all_as_zip_multi(config)
            st.download_button("📦 打包下载全部 (.zip)", data=zip_bytes,
                               file_name=f"{config['module_name']}_全部文档.zip",
                               mime="application/zip", use_container_width=True, key="zip_all")
        else:
            st.button("📦 打包下载（暂无文档）", disabled=True, use_container_width=True)
    with bc3:
        if st.button("🔗 跨文档追溯校验", use_container_width=True,
                     disabled=(len(docs) < 2)):
            _run_cross_document_validation(docs)
    with bc4:
        if st.button("🗑️ 清空全部结果", use_container_width=True):
            st.session_state.docs_by_module = {}
            st.session_state.generated_docs = {}
            _persist()
            st.rerun()

    if not config["api_key"]:
        st.warning("⚠️ 请在侧边栏输入 API Key 后使用批量功能")

    # 已完成文档汇总（当前活动模块）
    docs = active_docs()
    if docs:
        st.markdown("---")
        am_name = active_module_name()
        st.markdown(f"### 📄 已生成文档汇总 — {am_name}（{len(docs)} / 7）")
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


# ======================================================================
# 代码 / 工程管理（集中在 Dashboard）
# ======================================================================

def _render_code_management(config: dict):
    """在 Dashboard 渲染代码上传 + 工程管理 + Token 预估。"""
    project_modules = st.session_state.get("project_modules", {})
    mods = list(project_modules.keys())
    code = active_code()

    if code:
        # 状态摘要
        am_name = active_module_name()
        if len(mods) > 1:
            selected = st.session_state.get("selected_modules") or mods
            total_lines = sum(project_modules.get(mn, "").count("\n") + 1 for mn in selected)
            st.success(
                f"📦 工程模式：**{len(selected)}** 个模块已加载 | "
                f"当前工作模块：**{am_name}** | 共 **{total_lines:,}** 行代码"
            )
        else:
            lines = code.count("\n") + 1
            mod_files = st.session_state.module_files.get(am_name, [])
            st.success(
                f"📎 已加载代码：模块 **{am_name}** | "
                f"{len(mod_files)} 个文件 / **{lines:,}** 行"
            )

        # 清除已上传内容
        _clr_col1, _clr_col2 = st.columns([4, 1])
        with _clr_col2:
            st.button(
                "🗑️ 清除已上传",
                key="clear_uploaded_code",
                use_container_width=True,
                on_click=_clear_uploaded_code,
                help="清空当前已上传/识别的所有代码与模块，恢复到未上传状态",
            )

        # 管理区（默认收起）
        with st.expander("📂 代码 / 工程管理（上传 · 模块调整 · 预览）", expanded=False):
            _render_code_upload_tabs()
            _render_project_view()
            _render_code_preview(code)

        # Token 综合预估
        asil = config.get("asil_level", "ASIL B")
        if len(mods) > 1:
            selected = st.session_state.get("selected_modules") or mods
            total_tokens = 0
            for mn in selected:
                mc = project_modules.get(mn, "")
                if mc:
                    est = estimate_batch_total_tokens(mc, asil, get_module_docs(mn))
                    total_tokens += est["total"]
            total_cost = estimate_cost(total_tokens, config.get("provider", "openai"))
            st.info(
                f"📊 全量生成预估：**{total_tokens:,}** tokens | 预估费用 {total_cost}"
            )
        else:
            batch_est = estimate_batch_total_tokens(code, asil, active_docs())
            total_tokens = batch_est["total"]
            total_cost = estimate_cost(total_tokens, config.get("provider", "openai"))
            st.info(
                f"📊 全量生成预估：**{total_tokens:,}** tokens（含知识库+前置文档+多轮调用） | "
                f"预估费用 {total_cost}"
            )
            with st.expander("📈 各 Agent Token 消耗明细"):
                est_cols = st.columns(7, gap="small")
                for col, agent in zip(est_cols, ["SRS", "SAD", "FMEA", "DFA", "SDD", "TC-UNIT", "TC-INTEGRATION"]):
                    ae = batch_est["per_agent"][agent]
                    with col:
                        st.markdown(
                            f"<div style='text-align:center;font-size:0.72rem;'>"
                            f"<b>{agent}</b><br/>"
                            f"输入 {ae['input_total']:,}<br/>"
                            f"输出 ~{ae['output_estimated']:,}<br/>"
                            f"<b>合计 {ae['grand_total']:,}</b>"
                            f"</div>", unsafe_allow_html=True
                        )
                st.caption("ℹ️ 输入含：源代码 + Prompt模板 + 安全知识库 + 前置文档注入。")
    else:
        # 未上传代码：显示醒目的上传区域
        st.markdown("### 📂 上传代码")
        st.caption("上传 C/C++ 源文件或工程压缩包，系统将自动识别软件模块")
        _render_code_upload_tabs()
        _render_project_view()


def _clear_uploaded_code():
    """回调：清除当前已上传的所有代码内容与上传控件状态。

    在 on_click 回调中执行（早于组件实例化）。注意：直接 pop 掉 file_uploader 的
    widget key 只能清后端返回值，无法复位其前端已选文件；改变 key（递增 nonce）
    才能让 Streamlit 渲染出全新的空控件。
    """
    # 复位代码 / 模块相关状态
    st.session_state.project_modules = {}
    st.session_state.module_files = {}
    st.session_state.active_module = None
    st.session_state.selected_modules = []
    st.session_state.shared_code = ""
    # 复位上传去重指纹
    st.session_state._upload_fingerprint = None
    st.session_state._zip_fingerprint = None
    st.session_state._had_uploaded_files = False
    # 递增 nonce 强制重建上传控件（文件上传/ZIP/粘贴/本地路径），彻底清空前端已选内容
    st.session_state._upload_nonce = st.session_state.get("_upload_nonce", 0) + 1
    for _k in ("module_selector", "batch_module_select"):
        st.session_state.pop(_k, None)
    sync_active_views()


def _render_code_upload_tabs():
    """渲染代码上传的三个 Tab：文件上传 / ZIP / 粘贴。

    使用 widget 返回值处理上传（Streamlit 官方推荐模式，兼容所有版本）。
    处理成功后先显示即时反馈，再尝试 st.rerun() 刷新布局。
    """
    tab_upload, tab_zip, tab_local, tab_paste = st.tabs(
        ["📂 上传文件", "📁 上传项目压缩包", "📀 本地路径导入", "📝 粘贴代码"]
    )

    # nonce 用于「清除已上传」后强制重建各上传控件（复位其前端已选文件/文本）
    nonce = st.session_state.get("_upload_nonce", 0)

    with tab_upload:
        uploaded_files = st.file_uploader(
            "上传 C/C++ 源文件",
            type=["c", "h", "cpp", "hpp", "cc", "cxx"],
            accept_multiple_files=True,
            help="支持 .c / .h / .cpp / .hpp / .cc / .cxx 文件，可多选。多文件时按目录自动识别模块。",
            key=f"dash_file_upload_{nonce}",
        )
        _had_files = st.session_state.get("_had_uploaded_files", False)
        _has_files_now = bool(uploaded_files)
        if _had_files and not _has_files_now:
            st.session_state.project_modules = {}
            st.session_state.module_files = {}
            st.session_state.active_module = None
            sync_active_views()
        st.session_state._had_uploaded_files = _has_files_now

        if uploaded_files:
            # 指纹防重复：同一批文件只处理一次
            _fp = "files:" + ",".join(f"{f.name}:{f.size}" for f in uploaded_files)
            if st.session_state.get("_upload_fingerprint") != _fp:
                try:
                    file_tuples = []
                    skipped = []
                    for f in uploaded_files:
                        raw = f.read()
                        if len(raw) == 0:
                            skipped.append(f"{f.name}（空文件）")
                            continue
                        if len(raw) > 500 * 1024:
                            skipped.append(f"{f.name}（>{len(raw)//1024}KB，过大）")
                            continue
                        text = raw.decode("utf-8", errors="replace")
                        if not _looks_like_c_code(text):
                            skipped.append(f"{f.name}（非 C/C++ 内容）")
                            continue
                        file_tuples.append((f.name, text))
                    if skipped:
                        st.warning(f"⚠️ 已跳过 {len(skipped)} 个文件: " + "、".join(skipped))
                    if file_tuples:
                        st.session_state._upload_fingerprint = _fp
                        _apply_module_detection(file_tuples)
                        n_mods = len(st.session_state.project_modules)
                        st.success(
                            f"✅ 成功加载 {len(file_tuples)} 个文件，"
                            f"识别出 {n_mods} 个软件模块"
                        )
                        time.sleep(0.3)
                        st.rerun()
                    elif not skipped:
                        st.error("❌ 未能从上传文件中解析出有效内容")
                except Exception as e:
                    st.session_state._upload_fingerprint = None
                    st.error(f"❌ 文件解析异常：{e}")
        elif st.session_state.get("_upload_fingerprint"):
            st.session_state._upload_fingerprint = None

    with tab_zip:
        st.caption("将整个项目文件夹打包为 .zip 上传，自动按目录结构识别软件模块")
        zip_file = st.file_uploader("上传项目压缩包 (.zip)", type=["zip"], key=f"dash_zip_upload_{nonce}")
        if zip_file is not None:
            # 指纹防重复：同一个 zip 只处理一次
            _zip_fp = f"zip:{zip_file.name}:{zip_file.size}"
            if st.session_state.get("_zip_fingerprint") != _zip_fp:
                try:
                    file_tuples = _extract_files_from_zip(zip_file)
                    if file_tuples:
                        st.session_state._zip_fingerprint = _zip_fp
                        _apply_module_detection(file_tuples)
                        n_mods = len(st.session_state.project_modules)
                        st.success(
                            f"✅ 成功提取 {len(file_tuples)} 个源文件，"
                            f"识别出 {n_mods} 个软件模块"
                        )
                        time.sleep(0.3)
                        st.rerun()
                    else:
                        st.error("❌ ZIP 中未找到有效的 C/C++ 源文件")
                except Exception as e:
                    st.session_state._zip_fingerprint = None
                    st.error(f"❌ ZIP 解析异常：{e}")
        elif st.session_state.get("_zip_fingerprint"):
            st.session_state._zip_fingerprint = None

    with tab_local:
        st.caption("点击按钮弹出 Windows 文件选择对话框，服务器直接从磁盘读取（不经过浏览器上传，适用于浏览器上传受限的环境）")
        pick_col1, pick_col2 = st.columns(2)
        picked_path = None
        with pick_col1:
            if st.button("📂 选择 ZIP 文件…", key="dash_local_pick_zip", use_container_width=True):
                picked_path = _pick_local_path("zip")
        with pick_col2:
            if st.button("📁 选择项目文件夹…", key="dash_local_pick_dir", use_container_width=True):
                picked_path = _pick_local_path("dir")
        st.caption("💡 对话框由本机服务进程弹出，若未看到请检查是否被其他窗口遮挡")

        if picked_path:
            _import_local_path(picked_path)

        with st.expander("⌨️ 手动输入路径（备用）"):
            local_path = st.text_input(
                "本地路径（.zip 文件或项目文件夹）",
                placeholder=r"例如：C:\Users\Lenovo\Desktop\safetylib_1.zip 或 D:\projects\my_module",
                key=f"dash_local_path_{nonce}",
            )
            if st.button("📥 导入", key="dash_local_import_btn", disabled=not local_path.strip()):
                _import_local_path(local_path.strip().strip('"').strip("'"))

    with tab_paste:
        pasted = st.text_area(
            "粘贴 C/C++ 代码", height=300,
            placeholder="// 在此粘贴嵌入式 C/C++ 代码...",
            key=f"dash_paste_{nonce}",
        )
        if pasted:
            if not _looks_like_c_code(pasted):
                st.warning("⚠️ 粘贴内容不像 C/C++ 代码（缺少 #include、函数定义等特征），仍可使用但结果可能不佳")
            mod_name = st.session_state.get("_config_module_name") or "目标模块"
            st.session_state.project_modules = {mod_name: pasted}
            st.session_state.module_files = {mod_name: ["pasted_code.c"]}
            st.session_state.active_module = mod_name
            sync_active_views()


def _apply_module_detection(file_tuples):
    """对上传的文件列表执行模块检测，写入 session_state。"""
    modules = detect_modules(file_tuples)
    project_modules = {}
    module_files = {}
    for mod_name, rel_paths in modules.items():
        project_modules[mod_name] = build_module_code(file_tuples, rel_paths)
        module_files[mod_name] = rel_paths
    st.session_state.project_modules = project_modules
    st.session_state.module_files = module_files
    if project_modules:
        st.session_state.active_module = next(iter(project_modules))
    if not st.session_state.selected_modules:
        st.session_state.selected_modules = list(project_modules.keys())
    sync_active_views()


def _render_project_view():
    """渲染工程视图：模块列表 + 合并/重命名/删除操作。"""
    mods = st.session_state.get("project_modules", {})
    if not mods:
        return

    mod_names = list(mods.keys())

    if len(mod_names) >= 2:
        st.markdown("---")
        st.markdown(f"### 📦 工程视图（{len(mod_names)} 个模块）")

        current_active = st.session_state.get("active_module") or mod_names[0]
        if current_active not in mod_names:
            current_active = mod_names[0]
        selected = st.selectbox(
            "🎯 当前工作模块", options=mod_names,
            index=mod_names.index(current_active),
            help="选择后各 Agent 页面针对该模块生成文档",
            key="module_selector",
        )
        if selected != st.session_state.get("active_module"):
            st.session_state.active_module = selected
            sync_active_views()
            st.rerun()

        # 批量生成模块选择
        batch_selected = st.multiselect(
            "🚀 批量生成范围（一键全部生成时使用）",
            mod_names, default=st.session_state.get("selected_modules") or mod_names,
            key="batch_module_select",
        )
        st.session_state.selected_modules = batch_selected

        # 模块信息表
        for mn in mod_names:
            files = st.session_state.module_files.get(mn, [])
            code_str = mods[mn]
            lines = code_str.count("\n") + 1
            prefix = sanitize_module_prefix(mn)
            is_active = " 🎯" if mn == selected else ""
            with st.expander(f"📁 **{mn}**{is_active} — {len(files)} 文件 / {lines:,} 行 / ID前缀: {prefix}"):
                st.code("\n".join(f"  {fp}" for fp in files), language="text")

        # 操作区
        st.markdown("##### 🔧 模块操作")
        op_col1, op_col2, op_col3 = st.columns(3)
        with op_col1:
            merge_names = st.multiselect("选择要合并的模块", mod_names, key="merge_select")
            merge_new = st.text_input("合并后名称", value="merged_module", key="merge_name")
            if st.button("🔀 合并", disabled=(len(merge_names) < 2), key="merge_btn"):
                new_mods = merge_modules(
                    st.session_state.module_files, merge_names, merge_new
                )
                file_tuples = _modules_to_file_tuples(new_mods)
                st.session_state.module_files = new_mods
                st.session_state.project_modules = {
                    mn: build_module_code(file_tuples, paths)
                    for mn, paths in new_mods.items()
                }
                st.session_state.active_module = merge_new
                sync_active_views()
                st.rerun()
        with op_col2:
            rename_old = st.selectbox("重命名模块", mod_names, key="rename_select")
            rename_new = st.text_input("新名称", value=rename_old, key="rename_input")
            if st.button("✏️ 重命名", disabled=(rename_new == rename_old), key="rename_btn"):
                st.session_state.module_files = rename_module(
                    st.session_state.module_files, rename_old, rename_new
                )
                st.session_state.project_modules = rename_module(
                    st.session_state.project_modules, rename_old, rename_new
                )
                if st.session_state.active_module == rename_old:
                    st.session_state.active_module = rename_new
                sync_active_views()
                st.rerun()
        with op_col3:
            del_name = st.selectbox("删除模块", mod_names, key="del_select")
            if st.button("🗑️ 删除", disabled=(len(mod_names) <= 1), key="del_btn"):
                st.session_state.module_files = delete_module(
                    st.session_state.module_files, del_name
                )
                st.session_state.project_modules = delete_module(
                    st.session_state.project_modules, del_name
                )
                if st.session_state.active_module == del_name:
                    st.session_state.active_module = next(iter(st.session_state.project_modules), None)
                sync_active_views()
                st.rerun()

    elif len(mod_names) == 1:
        mn = mod_names[0]
        files = st.session_state.module_files.get(mn, [])
        if len(files) > 1:
            st.caption(f"📁 模块 **{mn}**：{len(files)} 文件 / ID前缀 {sanitize_module_prefix(mn)}")
        st.session_state.active_module = mn


def _modules_to_file_tuples(module_files: dict):
    """从当前 project_modules 代码串中还原 file_tuples（用于合并后重建）。"""
    import re
    file_tuples = []
    for mn, paths in module_files.items():
        code = st.session_state.project_modules.get(mn, "")
        parts = re.split(r"// ===== (.+?) =====\n", code)
        for i in range(1, len(parts) - 1, 2):
            file_tuples.append((parts[i], parts[i + 1].rstrip("\n")))
    return file_tuples


def _looks_like_c_code(text: str) -> bool:
    """简单检测文本是否具有 C/C++ 代码特征。"""
    strong_indicators = ["#include", "#define", "int ", "void ", "char ", "struct ",
                         "typedef ", "return ", "if (", "for (", "while (",
                         "->", "::", "uint8_t", "uint16_t", "uint32_t"]
    sample = text[:3000]
    hits = sum(1 for ind in strong_indicators if ind in sample)
    return hits >= 2


_TK_PICKER_SCRIPT = """
import sys
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
root.update()
if sys.argv[1] == "zip":
    path = filedialog.askopenfilename(
        title="\u9009\u62e9\u9879\u76ee\u538b\u7f29\u5305",
        filetypes=[("ZIP \u538b\u7f29\u5305", "*.zip"), ("\u6240\u6709\u6587\u4ef6", "*.*")],
    )
else:
    path = filedialog.askdirectory(title="\u9009\u62e9\u9879\u76ee\u6587\u4ef6\u5939")
root.destroy()
sys.stdout.write(path or "")
"""


def _pick_local_path(mode: str):
    """在服务器本机弹出 Windows 原生文件/文件夹选择对话框。

    用子进程跑 tkinter，避免在 Streamlit 脚本线程中创建 Tk 实例的线程问题。
    返回选中的路径，未选择/取消时返回 None。
    """
    try:
        result = subprocess.run(
            [sys.executable, "-c", _TK_PICKER_SCRIPT, mode],
            capture_output=True, text=True, timeout=300,
        )
        path = (result.stdout or "").strip()
        return path or None
    except subprocess.TimeoutExpired:
        st.warning("⚠️ 文件选择对话框超时未操作，已取消")
        return None
    except Exception as e:
        st.error(f"❌ 无法弹出文件选择对话框：{e}，请改用下方手动输入路径")
        return None


def _import_local_path(path: str):
    """从本地路径导入源文件并执行模块识别，成功后 rerun。"""
    try:
        file_tuples = _load_files_from_local_path(path)
        if file_tuples:
            _apply_module_detection(file_tuples)
            n_mods = len(st.session_state.project_modules)
            st.success(
                f"✅ 成功导入 {len(file_tuples)} 个源文件，"
                f"识别出 {n_mods} 个软件模块"
            )
            time.sleep(0.3)
            st.rerun()
        # file_tuples 为空时，_load_files_from_local_path 内部已给出错误提示
    except Exception as e:
        st.error(f"❌ 本地路径导入异常：{e}")


def _load_files_from_local_path(path: str) -> list:
    """从本地路径（zip 文件或文件夹）加载 C/C++ 源文件，返回 [(rel_path, content), ...]。

    服务器直接读磁盘，不经过浏览器上传通道。
    """
    CPP_EXTENSIONS = {".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".hxx", ".hh", ".inl"}
    if not os.path.exists(path):
        st.error(f"❌ 路径不存在：{path}")
        return []

    # zip 文件：复用现有解压逻辑
    if os.path.isfile(path):
        if not path.lower().endswith(".zip"):
            st.error("❌ 仅支持 .zip 文件或文件夹路径")
            return []
        with open(path, "rb") as f:
            return _extract_files_from_zip(f)

    # 文件夹：递归扫描源文件
    file_tuples = []
    skip_dirs = {".git", ".svn", ".venv", "node_modules", "__pycache__", "build", "out"}
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fn in sorted(files):
            ext = os.path.splitext(fn)[1].lower()
            if ext not in CPP_EXTENSIONS:
                continue
            fp = os.path.join(root, fn)
            try:
                if os.path.getsize(fp) > 500 * 1024:
                    continue
                with open(fp, "rb") as f:
                    text = f.read().decode("utf-8", errors="replace")
            except OSError:
                continue
            if not text.strip():
                continue
            rel = os.path.relpath(fp, path).replace("\\", "/")
            file_tuples.append((rel, text))

    if not file_tuples:
        st.warning("⚠️ 该文件夹中未找到 C/C++ 源文件")
        return []

    st.success(f"✅ 扫描到 **{len(file_tuples)}** 个源文件")
    return file_tuples


def _extract_files_from_zip(zip_file) -> list:
    """从 zip 中提取 C/C++ 源文件，返回 [(rel_path, content), ...]。"""
    CPP_EXTENSIONS = {".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".hxx", ".hh", ".inl"}
    try:
        raw = zip_file.read()
        zf = zipfile.ZipFile(io.BytesIO(raw), "r")
    except zipfile.BadZipFile:
        st.error("❌ 无效的 zip 文件")
        return []

    file_tuples = []
    with zf:
        all_names = zf.namelist()
        for name in sorted(all_names):
            if name.endswith("/"):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in CPP_EXTENSIONS:
                continue
            try:
                text = zf.read(name).decode("utf-8", errors="replace")
            except Exception:
                continue
            if not text.strip():
                continue
            file_tuples.append((name, text))

    if not file_tuples:
        st.warning("⚠️ zip 中未找到 C/C++ 源文件")
        return []

    st.success(f"✅ 提取了 **{len(file_tuples)}** 个源文件")
    return file_tuples


def _render_code_preview(code: str):
    """渲染代码统计信息（在管理 expander 内使用）。"""
    _code_hash = hash(code)
    if st.session_state.get("_parser_cache_hash") != _code_hash:
        parser = CodeParser()
        st.session_state._parser_cache_info = parser.analyze(code)
        st.session_state._parser_cache_hash = _code_hash
    info = st.session_state._parser_cache_info
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


def _batch_generate_all(config: dict):
    """按模块 × Agent 顺序批量生成全部文档。"""
    order = ["SRS", "SAD", "FMEA", "DFA", "SDD", "TC-UNIT", "TC-INTEGRATION"]
    _AGENT_TOKEN_DEFAULT = _get_agent_token_defaults(config.get("asil_level", "ASIL B"))
    prompt_mgr = PromptManager()

    # 确定要处理的模块列表
    project_modules = st.session_state.get("project_modules", {})
    if project_modules:
        modules_to_process = st.session_state.get("selected_modules") or list(project_modules.keys())
        modules_to_process = [m for m in modules_to_process if m in project_modules]
    else:
        modules_to_process = [config["module_name"]]
        project_modules = {config["module_name"]: st.session_state.shared_code}

    try:
        _make_engine(config)  # 验证配置有效性（fail-fast）
    except Exception as e:
        st.error(f"❌ 引擎初始化失败: {e}")
        return

    total_steps = len(modules_to_process) * len(order)
    progress = st.progress(0, text="批量生成中...")

    cancel_col, _ = st.columns([1, 5])
    with cancel_col:
        if st.button("⛔ 取消生成", key="cancel_batch"):
            st.session_state.cancel_generation = True
            st.rerun()

    checkpoint = st.session_state.batch_checkpoint  # {module: {agent: "done"}}
    step = 0
    cancelled = False

    for mod_name in modules_to_process:
        mod_code = project_modules.get(mod_name, "")
        if not mod_code:
            continue
        mod_docs = get_module_docs(mod_name)
        mod_checkpoint = checkpoint.setdefault(mod_name, {})
        base_ctx = {"module_name": mod_name, "asil_level": config["asil_level"]}

        st.markdown(f"---\n#### 📦 模块：{mod_name}")

        for i, agent_type in enumerate(order):
            # 断点续传：跳过已完成
            if mod_checkpoint.get(agent_type) == "done":
                step += 1
                continue

            if st.session_state.cancel_generation:
                st.warning("⚠️ 用户已取消批量生成，已完成部分已保存。")
                st.session_state.cancel_generation = False
                cancelled = True
                break

            step += 1
            progress.progress(
                step / total_steps,
                text=f"[{mod_name}] 正在生成 {agent_type}（{step}/{total_steps}）..."
            )

            ctx = dict(base_ctx)
            if agent_type == "FMEA":
                prior = {k: mod_docs[k] for k in ("SRS", "SAD") if k in mod_docs}
                if prior:
                    ctx["prior_docs"] = prior
            if agent_type == "DFA":
                prior = {k: mod_docs[k] for k in ("SAD", "FMEA", "SRS") if k in mod_docs}
                if prior:
                    ctx["prior_docs"] = prior
            if agent_type in ("TC-UNIT", "TC-INTEGRATION"):
                prior = {k: mod_docs[k] for k in ("SRS", "SAD", "FMEA", "DFA") if k in mod_docs}
                if prior:
                    ctx["prior_docs"] = prior

            container = st.empty()
            agent_engine = _make_engine({**config, "max_tokens": _AGENT_TOKEN_DEFAULT.get(agent_type, config.get("max_tokens", 8192))})
            text = _generate_single_doc(agent_engine, prompt_mgr, agent_type, mod_code, ctx,
                                        st.session_state.agent_templates.get(agent_type), container)
            mod_docs[agent_type] = text

            template = st.session_state.agent_templates.get(agent_type)
            validation = validate_document(agent_type, text, custom_template=template)
            st.session_state.generation_history.append({
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "module": mod_name, "doc_type": agent_type,
                "status": "成功" if not text.startswith("生成失败") else "失败",
                "validation": validation.summary(),
            })

            mod_checkpoint[agent_type] = "done"
            sync_active_views()
            _persist()

        if cancelled:
            break

    progress.progress(1.0, text="✅ 全部完成！")
    if not cancelled:
        st.session_state.batch_checkpoint = {}
    _persist()
    sync_active_views()

    done_count = sum(1 for m in modules_to_process for a in order
                     if checkpoint.get(m, {}).get(a) == "done")
    st.success(f"✅ 批量生成完成（{done_count}/{total_steps} 份文档）")

    # 对每个模块执行跨文档追溯校验
    for mod_name in modules_to_process:
        mod_docs = get_module_docs(mod_name)
        if len(mod_docs) >= 2:
            st.markdown(f"##### 🔗 {mod_name} 追溯校验")
            _run_cross_document_validation(mod_docs)


def _export_all_as_zip_multi(config: dict) -> bytes:
    """将所有模块的已生成文档打包为 zip（按模块子目录组织）。"""
    asil_level = config.get("asil_level", "ASIL B")
    docs_by_module = st.session_state.get("docs_by_module", {})
    # 兼容：如果 docs_by_module 为空但 generated_docs 有内容
    if not any(docs_by_module.values()) and st.session_state.generated_docs:
        docs_by_module = {config["module_name"]: st.session_state.generated_docs}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for mod_name, docs in docs_by_module.items():
            if not docs:
                continue
            prefix = f"{mod_name}/" if len(docs_by_module) > 1 else ""
            for dt, doc_content in docs.items():
                zf.writestr(f"{prefix}{mod_name}_{dt}.md", doc_content)
                try:
                    metadata = {
                        "doc_id": f"DOC-{dt}-{mod_name}",
                        "version": "1.0",
                        "module_name": mod_name,
                        "asil_level": asil_level,
                        "date": time.strftime("%Y-%m-%d"),
                    }
                    word_bytes = export_to_word(title=f"{mod_name} {dt} 文档",
                                               markdown=doc_content, metadata=metadata)
                    zf.writestr(f"{prefix}{mod_name}_{dt}.docx", word_bytes)
                except Exception:
                    pass
                if dt == "FMEA":
                    try:
                        zf.writestr(f"{prefix}{mod_name}_FMEA.xlsx", export_fmea_to_excel(doc_content))
                    except Exception:
                        pass
    return buf.getvalue()


def _run_cross_document_validation(docs: dict):
    """执行跨文档追溯一致性校验并展示结果。"""
    report = validate_cross_document_traceability(docs)

    st.markdown("---")
    st.markdown("### 🔗 跨文档追溯校验报告")

    if report.passed and not report.warnings:
        st.success(f"✅ {report.summary()}")
    else:
        if report.errors:
            st.error(f"❌ {report.summary()}")
        elif report.warnings:
            st.warning(f"⚠️ {report.summary()}")

    for r in report.results:
        if r.severity == "error":
            st.markdown(f"- ❌ **{r.check_name}**: {r.message}")
            if r.details:
                st.caption(f"  {r.details}")
        elif r.severity == "warning":
            st.markdown(f"- ⚠️ **{r.check_name}**: {r.message}")
            if r.details:
                st.caption(f"  {r.details}")
        else:
            st.markdown(f"- ✅ **{r.check_name}**: {r.message}")
