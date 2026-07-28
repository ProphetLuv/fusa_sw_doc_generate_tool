# -*- coding: utf-8 -*-
"""docs.py — 文档 / 校验 / 导出 / 历史 / 模板 路由。"""

import io
import time
import difflib
import zipfile
import sys
import subprocess
import asyncio
import logging
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response

from server.state import STATE
from server.models import CrossValidateRequest, LocalPathRequest
from server.generation import _run_validation
from server.estimate import AGENT_META, AGENT_ORDER
from doc_exporter import export_to_word, export_fmea_to_excel
from validator import validate_cross_document_traceability
from template_parser import parse_template, get_supported_extensions

router = APIRouter(tags=["docs"])
_logger = logging.getLogger("docs")


# ======================================================================
# 文档读取
# ======================================================================

@router.get("/api/docs")
def list_docs(module: str = None):
    """列出指定模块（默认活动模块）的文档摘要。"""
    mod = module or STATE.active_module_name()
    docs = STATE.get_module_docs(mod)
    items = [{
        "agent": dt, "chars": len(content),
        "icon": AGENT_META.get(dt, {}).get("icon", "📄"),
    } for dt, content in docs.items()]
    # 全工程各模块完成度
    overview = {mn: len(d) for mn, d in STATE.docs_by_module.items() if d}
    return {
        "module": mod, "docs": items,
        "agent_order": AGENT_ORDER,
        "overview": overview,
    }


@router.get("/api/docs/{module}/{agent}")
def get_doc(module: str, agent: str):
    """获取单个文档内容 + 校验 + 版本 + Token 用量。"""
    agent = agent.upper()
    docs = STATE.get_module_docs(module)
    if agent not in docs:
        raise HTTPException(status_code=404, detail="文档不存在")
    content = docs[agent]
    code = STATE.module_code(module)
    _, validation = _run_validation(agent, content, code,
                                    STATE.agent_templates.get(agent))
    # 版本 Diff（当前 vs 上一版本）
    versions = STATE.get_versions(module, agent)
    diff = ""
    if versions:
        diff = "".join(difflib.unified_diff(
            versions[-1].splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile="上一版本", tofile="当前版本", lineterm=""))
    return {
        "module": module, "agent": agent, "content": content,
        "validation": validation,
        "version_count": len(versions),
        "diff": diff,
        "token_usage": STATE.get_token_usage(module, agent),
    }


@router.delete("/api/docs/{module}/{agent}")
def delete_doc(module: str, agent: str):
    docs = STATE.get_module_docs(module)
    docs.pop(agent.upper(), None)
    STATE.persist()
    return {"ok": True}


@router.delete("/api/docs")
def clear_all_docs():
    STATE.docs_by_module = {}
    STATE.batch_checkpoint = {}
    STATE.persist()
    return {"ok": True}


# ======================================================================
# 跨文档追溯校验
# ======================================================================

@router.post("/api/validate/cross")
def cross_validate(req: CrossValidateRequest):
    mod = req.module or STATE.active_module_name()
    docs = STATE.get_module_docs(mod)
    if len(docs) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 份文档才能进行跨文档校验")
    report = validate_cross_document_traceability(docs)
    return {
        "module": mod,
        "summary": report.summary(),
        "passed": report.passed,
        "results": [{
            "check_name": r.check_name, "passed": r.passed,
            "severity": r.severity, "message": r.message, "details": r.details,
        } for r in report.results],
    }


# ======================================================================
# 导出
# ======================================================================

def _doc_or_404(module: str, agent: str) -> str:
    docs = STATE.get_module_docs(module)
    if agent not in docs:
        raise HTTPException(status_code=404, detail="文档不存在")
    return docs[agent]


@router.get("/api/export/word")
def export_word(module: str, agent: str):
    agent = agent.upper()
    content = _doc_or_404(module, agent)
    metadata = {
        "doc_id": f"DOC-{agent}-{module}", "version": "1.0",
        "module_name": module, "asil_level": STATE.config.get("asil_level", "ASIL B"),
        "date": time.strftime("%Y-%m-%d"),
    }
    data = export_to_word(title=f"{module} {agent} 文档", markdown=content, metadata=metadata)
    # ASCII fallback for filename param (RFC 6266); full UTF-8 name in filename*
    ascii_name = f"{agent}.docx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(f'{module}_{agent}.docx')}"},
    )


@router.get("/api/export/excel")
def export_excel(module: str, agent: str = "FMEA"):
    agent = agent.upper()
    content = _doc_or_404(module, agent)
    if agent != "FMEA":
        raise HTTPException(status_code=400, detail="Excel 导出仅适用于 FMEA 文档")
    data = export_fmea_to_excel(content)
    ascii_name = f"{agent}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(f'{module}_FMEA.xlsx')}"},
    )


@router.get("/api/export/zip")
def export_zip():
    """将所有模块的已生成文档打包为 zip（按模块子目录组织）。"""
    asil = STATE.config.get("asil_level", "ASIL B")
    docs_by_module = STATE.docs_by_module
    if not any(docs_by_module.values()):
        raise HTTPException(status_code=400, detail="暂无可导出的文档")

    buf = io.BytesIO()
    multi = len([1 for d in docs_by_module.values() if d]) > 1
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for mod_name, docs in docs_by_module.items():
            if not docs:
                continue
            prefix = f"{mod_name}/" if multi else ""
            for dt, content in docs.items():
                zf.writestr(f"{prefix}{mod_name}_{dt}.md", content)
                try:
                    metadata = {
                        "doc_id": f"DOC-{dt}-{mod_name}", "version": "1.0",
                        "module_name": mod_name, "asil_level": asil,
                        "date": time.strftime("%Y-%m-%d"),
                    }
                    zf.writestr(f"{prefix}{mod_name}_{dt}.docx",
                                export_to_word(title=f"{mod_name} {dt} 文档",
                                               markdown=content, metadata=metadata))
                except Exception:
                    pass
                if dt == "FMEA":
                    try:
                        zf.writestr(f"{prefix}{mod_name}_FMEA.xlsx",
                                    export_fmea_to_excel(content))
                    except Exception:
                        pass
    return Response(
        content=buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=\"all_docs.zip\"; filename*=UTF-8''{quote('全部文档.zip')}"},
    )


# ======================================================================
# 历史 & 模板
# ======================================================================

@router.get("/api/history")
def get_history(limit: int = 50):
    return {"history": STATE.generation_history[-limit:][::-1]}


@router.delete("/api/history")
def clear_history():
    """清空所有生成历史记录。"""
    STATE.generation_history = []
    STATE.persist()
    return {"ok": True}


@router.get("/api/templates")
def list_templates():
    return {
        "templates": {k: len(v) for k, v in STATE.agent_templates.items()},
        "supported_extensions": get_supported_extensions(),
    }


@router.post("/api/templates/{agent}")
async def upload_template(agent: str, file: UploadFile = File(...)):
    agent = agent.upper()

    # 文件大小预检（防止超大文件 OOM / 超长解析阻塞）
    MAX_SIZE = 50 * 1024 * 1024  # 50 MB
    raw = await file.read()
    size_mb = len(raw) / (1024 * 1024)
    if len(raw) > MAX_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"模板文件过大（{size_mb:.1f} MB），上限 {MAX_SIZE // (1024 * 1024)} MB")

    # 使用 BytesIO 避免二次拷贝，在线程池中解析避免阻塞事件循环
    buf = io.BytesIO(raw)
    buf.name = file.filename or "template.bin"

    _logger.info("开始解析模板: agent=%s file=%s size=%.2f MB", agent, file.filename, size_mb)
    parsed = await asyncio.to_thread(parse_template, buf)
    if not parsed:
        _logger.warning("模板解析返回空: agent=%s file=%s", agent, file.filename)
        raise HTTPException(status_code=400, detail=f"模板解析失败: {file.filename}")
    _logger.info("模板解析成功: agent=%s chars=%d", agent, len(parsed))
    STATE.agent_templates[agent] = parsed
    return {"agent": agent, "chars": len(parsed), "size_mb": round(size_mb, 2), "preview": parsed[:3000]}


@router.delete("/api/templates/{agent}")
def delete_template(agent: str):
    STATE.agent_templates.pop(agent.upper(), None)
    return {"ok": True}


# ---- 模板本地路径导入（绕过浏览器上传，避免安全软件拦截） ----

_TEMPLATE_PICKER_SCRIPT = """
import sys
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
root.update()
path = filedialog.askopenfilename(
    title="选择模板文件",
    filetypes=[
        ("所有支持的模板", "*.md *.txt *.text *.rst *.docx *.xlsx"),
        ("Markdown 文件", "*.md"),
        ("Word 文档", "*.docx"),
        ("Excel 表格", "*.xlsx"),
        ("文本文件", "*.txt *.text *.rst"),
        ("所有文件", "*.*"),
    ],
)
root.destroy()
sys.stdout.write(path or "")
"""


@router.get("/api/templates/pick")
def pick_template_path():
    """在服务器本机弹出原生文件选择对话框，返回选中的模板文件路径。"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", _TEMPLATE_PICKER_SCRIPT],
            capture_output=True, text=True, timeout=300,
        )
        path = (result.stdout or "").strip()
        return {"path": path or None}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="文件选择对话框超时未操作")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法弹出文件选择对话框：{e}")


@router.post("/api/templates/{agent}/local-path")
def upload_template_local_path(agent: str, req: LocalPathRequest):
    """从本机磁盘路径导入模板文件，绕过浏览器上传通道。

    服务器直接读取本地文件，不受浏览器安全策略或安全软件拦截影响。
    """
    import os

    agent = agent.upper()
    path = req.path.strip().strip('"').strip("'")

    if not os.path.exists(path):
        raise HTTPException(status_code=400, detail=f"文件不存在：{path}")
    if not os.path.isfile(path):
        raise HTTPException(status_code=400, detail=f"路径不是文件：{path}")

    size_mb = os.path.getsize(path) / (1024 * 1024)
    MAX_SIZE = 50 * 1024 * 1024  # 50 MB
    if os.path.getsize(path) > MAX_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"模板文件过大（{size_mb:.1f} MB），上限 {MAX_SIZE // (1024 * 1024)} MB")

    # 检查扩展名（lstrip 去掉 splitext 返回的前导点）
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    supported = get_supported_extensions()
    if ext not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式 {ext}，支持：{', '.join(supported)}")

    _logger.info("本地路径导入模板: agent=%s path=%s size=%.2f MB", agent, path, size_mb)

    # 直接读取文件内容并解析
    with open(path, "rb") as fh:
        raw = fh.read()

    buf = io.BytesIO(raw)
    buf.name = os.path.basename(path)

    parsed = parse_template(buf)
    if not parsed:
        _logger.warning("模板解析返回空: agent=%s path=%s", agent, path)
        raise HTTPException(status_code=400, detail=f"模板解析失败: {os.path.basename(path)}")

    _logger.info("模板本地导入成功: agent=%s chars=%d", agent, len(parsed))
    STATE.agent_templates[agent] = parsed
    return {"agent": agent, "chars": len(parsed), "size_mb": round(size_mb, 2), "preview": parsed[:3000], "filename": os.path.basename(path)}
