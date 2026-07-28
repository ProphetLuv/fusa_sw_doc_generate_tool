# -*- coding: utf-8 -*-
"""upload.py — 代码上传路由（本地路径 / 网络URL / 粘贴 / 本地文件对话框）。"""

import sys
import subprocess

from fastapi import APIRouter, HTTPException

from server.state import STATE
from server.models import PasteRequest, LocalPathRequest, UrlRequest
from server import upload as up

router = APIRouter(prefix="/api/upload", tags=["upload"])


def _apply(file_tuples, skipped=None):
    """执行模块检测并写入状态，返回模块快照 + 提示。"""
    if not file_tuples:
        raise HTTPException(status_code=400, detail="未解析出有效的 C/C++ 源文件")
    project_modules, module_files = up.build_modules_from_file_tuples(file_tuples)
    STATE.set_modules(project_modules, module_files)
    snap = STATE.modules_snapshot()
    snap["file_count"] = len(file_tuples)
    snap["skipped"] = skipped or []
    return snap


@router.post("/local-path")
def upload_local_path(req: LocalPathRequest):
    """从本机磁盘路径（.zip、文件夹、单个源文件、或多文件 | 分隔）导入。"""
    raw = req.path.strip().strip('"').strip("'")
    # 支持多文件选择（tkinter 返回 | 分隔）
    paths = [p.strip() for p in raw.split("|") if p.strip()] if "|" in raw else [raw]
    try:
        file_tuples = []
        for p in paths:
            file_tuples.extend(up.load_files_from_local_path(p))
    except up.UploadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _apply(file_tuples)


@router.post("/url")
def upload_url(req: UrlRequest):
    """从网络 URL 下载文件（.zip 或单个源文件）并导入。"""
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL 不能为空")
    try:
        file_tuples = up.load_files_from_url(url)
    except up.UploadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _apply(file_tuples)


@router.post("/paste")
def upload_paste(req: PasteRequest):
    """粘贴代码作为单模块。"""
    code = req.code
    if not code.strip():
        raise HTTPException(status_code=400, detail="粘贴内容为空")
    mod_name = req.module_name or STATE.default_module_name()
    STATE.set_modules({mod_name: code}, {mod_name: ["pasted_code.c"]})
    snap = STATE.modules_snapshot()
    snap["looks_like_c"] = up.looks_like_c_code(code)
    return snap


_TK_PICKER_SCRIPT = """
import sys
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
root.update()
mode = sys.argv[1]
if mode == "zip":
    path = filedialog.askopenfilename(
        title="\u9009\u62e9\u9879\u76ee\u538b\u7f29\u5305",
        filetypes=[("ZIP \u538b\u7f29\u5305", "*.zip"), ("\u6240\u6709\u6587\u4ef6", "*.*")],
    )
elif mode == "file":
    paths = filedialog.askopenfilenames(
        title="\u9009\u62e9 C/C++ \u6e90\u6587\u4ef6",
        filetypes=[("C/C++ \u6e90\u6587\u4ef6", "*.c *.h *.cpp *.hpp *.cc *.cxx *.hxx"), ("\u6240\u6709\u6587\u4ef6", "*.*")],
    )
    path = "|".join(paths) if paths else ""
else:
    path = filedialog.askdirectory(title="\u9009\u62e9\u9879\u76ee\u6587\u4ef6\u5939")
root.destroy()
sys.stdout.write(path or "")
"""


@router.get("/pick")
def pick_local_path(mode: str = "zip"):
    """在服务器本机弹出原生文件/文件夹选择对话框，返回选中路径。

    mode: "zip" | "dir" | "file"
    file 模式返回多个路径以 | 分隔。
    """
    try:
        result = subprocess.run(
            [sys.executable, "-c", _TK_PICKER_SCRIPT, mode if mode in ("zip", "file") else "dir"],
            capture_output=True, text=True, timeout=300,
        )
        path = (result.stdout or "").strip()
        return {"path": path or None}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="文件选择对话框超时未操作")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法弹出文件选择对话框：{e}")


@router.delete("")
def clear_uploaded():
    """清除已上传的所有代码与模块，同时清空关联文档。"""
    STATE.clear_modules()
    STATE.docs_by_module = {}
    STATE.batch_checkpoint = {}
    STATE._analysis_cache.clear()
    STATE.persist()
    return STATE.modules_snapshot()
