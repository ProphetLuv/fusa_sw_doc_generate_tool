# -*- coding: utf-8 -*-
"""
upload.py — 代码上传与模块检测（从原 dashboard 平移，去除 UI 依赖）。

提供 4 条上传链路的纯逻辑：多文件、ZIP、本地路径、粘贴，
统一产出 [(rel_path, content), ...]，交给 module_detector 识别模块。
"""

import io
import os
import re
import zipfile

from module_detector import detect_modules, build_module_code

CPP_EXTENSIONS = {".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".hxx", ".hh", ".inl"}
MAX_FILE_BYTES = 500 * 1024


class UploadError(Exception):
    """上传/解析类错误，供路由转换为 400 响应。"""


def looks_like_c_code(text: str) -> bool:
    """简单检测文本是否具有 C/C++ 代码特征。"""
    strong_indicators = ["#include", "#define", "int ", "void ", "char ", "struct ",
                         "typedef ", "return ", "if (", "for (", "while (",
                         "->", "::", "uint8_t", "uint16_t", "uint32_t"]
    sample = text[:3000]
    hits = sum(1 for ind in strong_indicators if ind in sample)
    return hits >= 2


def parse_uploaded_files(raw_files: list) -> tuple:
    """处理多文件上传。

    Args:
        raw_files: [(filename, bytes), ...]

    Returns:
        (file_tuples, skipped) — file_tuples: [(name, text)], skipped: [说明字符串]
    """
    file_tuples = []
    skipped = []
    for name, raw in raw_files:
        if not raw:
            skipped.append(f"{name}（空文件）")
            continue
        if len(raw) > MAX_FILE_BYTES:
            skipped.append(f"{name}（>{len(raw) // 1024}KB，过大）")
            continue
        text = raw.decode("utf-8", errors="replace")
        if not looks_like_c_code(text):
            skipped.append(f"{name}（非 C/C++ 内容）")
            continue
        file_tuples.append((name, text))
    return file_tuples, skipped


def extract_files_from_zip(raw: bytes) -> list:
    """从 zip 字节流中提取 C/C++ 源文件，返回 [(rel_path, content), ...]。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw), "r")
    except zipfile.BadZipFile:
        raise UploadError("无效的 zip 文件")

    file_tuples = []
    with zf:
        for name in sorted(zf.namelist()):
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
    return file_tuples


def load_files_from_local_path(path: str) -> list:
    """从本地路径（zip 文件或文件夹）加载 C/C++ 源文件。

    服务器直接读磁盘，不经过浏览器上传通道。
    """
    if not os.path.exists(path):
        raise UploadError(f"路径不存在：{path}")

    # zip 文件
    if os.path.isfile(path):
        if not path.lower().endswith(".zip"):
            raise UploadError("仅支持 .zip 文件或文件夹路径")
        with open(path, "rb") as f:
            return extract_files_from_zip(f.read())

    # 文件夹：递归扫描
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
                if os.path.getsize(fp) > MAX_FILE_BYTES:
                    continue
                with open(fp, "rb") as f:
                    text = f.read().decode("utf-8", errors="replace")
            except OSError:
                continue
            if not text.strip():
                continue
            rel = os.path.relpath(fp, path).replace("\\", "/")
            file_tuples.append((rel, text))
    return file_tuples


def build_modules_from_file_tuples(file_tuples: list) -> tuple:
    """对文件列表执行模块检测，返回 (project_modules, module_files)。"""
    modules = detect_modules(file_tuples)
    project_modules = {}
    module_files = {}
    for mod_name, rel_paths in modules.items():
        project_modules[mod_name] = build_module_code(file_tuples, rel_paths)
        module_files[mod_name] = rel_paths
    return project_modules, module_files


def file_tuples_from_modules(module_files: dict, project_modules: dict) -> list:
    """从现有 project_modules 代码串中还原 file_tuples（合并/拆分后重建用）。"""
    file_tuples = []
    for mn, paths in module_files.items():
        code = project_modules.get(mn, "")
        parts = re.split(r"// ===== (.+?) =====\n", code)
        for i in range(1, len(parts) - 1, 2):
            file_tuples.append((parts[i], parts[i + 1].rstrip("\n")))
    return file_tuples
