# -*- coding: utf-8 -*-
"""upload.py — 代码上传路由（多文件 / ZIP / 本地路径 / 粘贴 / 本地文件对话框）。"""

import sys
import subprocess

from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List

from server.state import STATE
from server.models import PasteRequest, LocalPathRequest
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


@router.post("/files")
async def upload_files(files: List[UploadFile] = File(...)):
    """多文件上传。"""
    raw_files = [(f.filename, await f.read()) for f in files]
    file_tuples, skipped = up.parse_uploaded_files(raw_files)
    return _apply(file_tuples, skipped)


@router.post("/zip")
async def upload_zip(file: UploadFile = File(...)):
    """项目 ZIP 上传。"""
    try:
        file_tuples = up.extract_files_from_zip(await file.read())
    except up.UploadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _apply(file_tuples)


@router.post("/local-path")
def upload_local_path(req: LocalPathRequest):
    """从本机磁盘路径（.zip 或文件夹）导入。"""
    path = req.path.strip().strip('"').strip("'")
    try:
        file_tuples = up.load_files_from_local_path(path)
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


@router.get("/pick")
def pick_local_path(mode: str = "zip"):
    """在服务器本机弹出原生文件/文件夹选择对话框，返回选中路径。"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", _TK_PICKER_SCRIPT, "zip" if mode == "zip" else "dir"],
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
    """清除已上传的所有代码与模块。"""
    STATE.clear_modules()
    STATE._analysis_cache.clear()
    return STATE.modules_snapshot()
