# -*- coding: utf-8 -*-
"""
文档模板解析器
支持用户上传 .md / .txt / .docx / .xlsx 格式的自定义文档模板，
提取纯文本内容供 Prompt 模板引用。
"""

import io
from typing import Optional


def parse_template(uploaded_file) -> Optional[str]:
    """
    解析用户上传的模板文件，返回纯文本内容。

    支持格式：
    - .md / .txt / .text / .rst → 直接读取文本
    - .docx → 使用 python-docx 提取段落文本和表格
    - .xlsx → 使用 openpyxl 提取所有 Sheet 的表格内容

    Args:
        uploaded_file: Streamlit UploadedFile 对象

    Returns:
        模板文本内容；解析失败返回 None
    """
    if uploaded_file is None:
        return None

    filename = uploaded_file.name.lower()
    raw = uploaded_file.read()

    # ---- 纯文本类格式 ----
    if filename.endswith((".md", ".txt", ".text", ".rst")):
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            # 尝试 GBK 回退（部分中文 Windows 环境）
            try:
                return raw.decode("gbk")
            except UnicodeDecodeError:
                return None

    # ---- Word 格式 ----
    if filename.endswith(".docx"):
        return _parse_docx(raw)

    # ---- Excel 格式 ----
    if filename.endswith(".xlsx"):
        return _parse_excel(raw)

    # ---- 不支持的格式 ----
    return None


def _parse_docx(raw: bytes) -> Optional[str]:
    """从 .docx 字节流中提取段落和表格文本。"""
    try:
        from docx import Document

        doc = Document(io.BytesIO(raw))
        parts = []

        # 提取段落
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                parts.append(text)

        # 提取表格（转为简易 Markdown 表格）
        for table in doc.tables:
            rows = []
            for row in table.rows:
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                rows.append(cells)

            if rows:
                # 转为 Markdown 表格格式
                header = rows[0]
                parts.append("| " + " | ".join(header) + " |")
                parts.append("| " + " | ".join(["---"] * len(header)) + " |")
                for row_data in rows[1:]:
                    # 补齐列数
                    while len(row_data) < len(header):
                        row_data.append("")
                    parts.append("| " + " | ".join(row_data[: len(header)]) + " |")
                parts.append("")  # 表格后空行

        return "\n".join(parts) if parts else None

    except Exception:
        return None


def get_supported_extensions() -> list:
    """返回支持的模板文件扩展名列表。"""
    return ["md", "txt", "docx", "xlsx"]


def _parse_excel(raw: bytes) -> Optional[str]:
    """
    从 .xlsx 字节流中提取所有 Sheet 的表格内容。
    每个 Sheet 以 Sheet 名作为标题，表格内容转为 Markdown 格式。
    """
    try:
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        parts = []

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = []

            for row in ws.iter_rows(values_only=True):
                # 将每个单元格转为字符串，None 转为空串
                cells = [str(cell).strip().replace("\n", " ") if cell is not None else "" for cell in row]
                # 跳过全空行
                if any(cells):
                    rows.append(cells)

            if not rows:
                continue

            # Sheet 标题
            parts.append(f"## Sheet: {sheet_name}\n")

            # 统一列数（取最大列数）
            max_cols = max(len(r) for r in rows)
            for r in rows:
                while len(r) < max_cols:
                    r.append("")

            # 第一行作为表头
            header = rows[0]
            parts.append("| " + " | ".join(header) + " |")
            parts.append("| " + " | ".join(["---"] * max_cols) + " |")

            # 数据行
            for row_data in rows[1:]:
                parts.append("| " + " | ".join(row_data) + " |")

            parts.append("")  # Sheet 之间空行

        wb.close()
        return "\n".join(parts) if parts else None

    except Exception:
        return None
