# -*- coding: utf-8 -*-
"""
app_results.py — 结果展示、文档版本 Diff、下载、历史记录。
"""

import streamlit as st
import time

from doc_exporter import export_to_word, export_fmea_to_excel

from app.app_utils import _get_cached_validation, _generate_diff, active_docs, active_module_name


def _render_agent_result(agent_type: str, config: dict):
    """渲染单个 Agent 的结果和下载按钮。"""
    docs = active_docs()
    if agent_type not in docs:
        return

    content = docs[agent_type]
    st.markdown("---")
    st.markdown("## 📄 生成结果")
    st.markdown(content)

    # 质量校验报告（使用缓存，避免每次 re-run 重复校验）
    validation = _get_cached_validation(agent_type, content)
    with st.expander(f"🔍 质量校验报告 ({validation.summary()})", expanded=False):
        for result in validation.results:
            icon = {"error": "❌", "warning": "⚠️", "info": "✅"}.get(result.severity, "ℹ️")
            st.markdown(f"{icon} **{result.check_name}**: {result.message}")
            if result.details:
                st.caption(result.details)

    # 文档版本对比/Diff（使用副本避免修改 session_state 中的原始列表）
    stored_versions = st.session_state.doc_versions.get(agent_type, [])
    orig_key = f"original_{agent_type}"
    # 拼接历史版本 + 审查前原始版本（不修改 stored_versions）
    versions = list(stored_versions)
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

    mod_label = active_module_name()
    with dl1:
        st.download_button("📄 下载 Markdown", data=content.encode("utf-8"),
                            file_name=f"{mod_label}_{agent_type}.md",
                            mime="text/markdown", use_container_width=True,
                            key=f"dl_md_{agent_type}")
    with dl2:
        try:
            metadata = {
                "doc_id": f"DOC-{agent_type}-{mod_label}",
                "version": "1.0",
                "module_name": mod_label,
                "asil_level": config["asil_level"],
                "date": time.strftime("%Y-%m-%d"),
            }
            word_bytes = export_to_word(title=f"{mod_label} {agent_type} 文档", markdown=content, metadata=metadata)
            st.download_button("📝 下载 Word (.docx)", data=word_bytes,
                                file_name=f"{mod_label}_{agent_type}.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                use_container_width=True, key=f"dl_docx_{agent_type}")
        except Exception as e:
            st.error(f"Word 导出失败: {e}")

    with dl3:
        if agent_type == "FMEA":
            try:
                excel_bytes = export_fmea_to_excel(content)
                st.download_button("📊 下载 Excel (.xlsx)", data=excel_bytes,
                                    file_name=f"{mod_label}_FMEA.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True, key=f"dl_xlsx_{agent_type}")
            except Exception as e:
                st.error(f"Excel 导出失败: {e}")
        else:
            st.info("Excel 导出仅适用于 FMEA 文档")

    # 生成历史
    _render_history()


def _render_history():
    """渲染生成历史记录。"""
    history = st.session_state.generation_history
    if not history:
        return
    st.markdown("---")
    with st.expander(f"📜 生成历史 ({len(history)} 条)"):
        for r in reversed(history[-20:]):
            icon = "✅" if r["status"] == "成功" else "❌"
            st.text(f"{icon} [{r['timestamp']}] {r['module']} | {r['doc_type']} | {r['status']}")
