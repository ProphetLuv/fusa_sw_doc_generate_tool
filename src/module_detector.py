# -*- coding: utf-8 -*-
"""
module_detector.py — C/C++ 工程模块化检测。

将上传的整个工程（多文件 / ZIP）按目录结构自动识别为若干软件组件/单元（模块），
并支持手动合并、拆分、重命名。为工程级多模块文档生成提供模块划分基础。

核心数据结构：
    files: List[Tuple[rel_path, content]]  归一化后的 (相对路径, 文件内容) 列表
    检测结果: Dict[module_name, List[rel_path]]  模块名 -> 该模块包含的文件相对路径
"""

import os
import re
from typing import Dict, List, Tuple

# 兜底模块名：根目录散落文件（无子目录）归入此模块
_ROOT_MODULE_NAME = "core"


def _strip_common_prefix(paths: List[str]) -> List[str]:
    """去除所有路径的公共目录前缀，返回归一化（正斜杠）后的相对路径。"""
    norm = [p.replace("\\", "/").lstrip("/") for p in paths]
    norm = [p for p in norm if p]
    if not norm:
        return []
    dirs = [os.path.dirname(p) for p in norm if "/" in p]
    common = os.path.commonprefix(dirs).replace("\\", "/") if dirs else ""
    common = common.rstrip("/")
    if common:
        out = []
        for p in norm:
            if p.startswith(common + "/"):
                out.append(p[len(common) + 1:])
            else:
                out.append(p)
        return out
    return norm


def detect_modules(files: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    """按目录结构将源文件分组为软件模块。

    规则：
      1. 去除公共前缀后，按第一级子目录分组；
      2. 同一目录下的 .c/.h/.cpp 等自动归为同一模块；
      3. 根目录散落文件（无子目录）归入兜底模块 ``core``；
      4. 模块名重名时追加序号。

    Args:
        files: [(rel_path, content), ...]

    Returns:
        {module_name: [rel_path, ...]}（保持插入顺序）
    """
    if not files:
        return {}

    paths = [p for p, _ in files]
    norm_paths = _strip_common_prefix(paths)
    # 建立 归一化路径 -> 原始内容 的映射（按顺序对齐）
    content_by_path = dict(zip(norm_paths, [c for _, c in files]))

    groups: Dict[str, List[str]] = {}
    for p in norm_paths:
        if "/" in p:
            mod = p.split("/", 1)[0]
        else:
            mod = _ROOT_MODULE_NAME
        groups.setdefault(mod, []).append(p)

    # 处理重名（理论上目录名不会重名，此处为健壮性兜底）
    result: Dict[str, List[str]] = {}
    seen = {}
    for mod, plist in groups.items():
        name = mod
        if name in seen:
            seen[name] += 1
            name = f"{mod}_{seen[name]}"
        else:
            seen[name] = 0
        # 按文件名排序，保证 .h/.c 顺序稳定
        result[name] = sorted(plist)

    # 保证 content_by_path 可用（外部通过 build_module_code 使用）
    detect_modules._last_content = content_by_path  # type: ignore[attr-defined]
    return result


def build_module_code(
    files: List[Tuple[str, str]], rel_paths: List[str]
) -> str:
    """将指定文件列表拼接为单模块代码串（复用 ``// ===== path =====`` 分隔格式）。"""
    content_map = {p.replace("\\", "/").lstrip("/"): c for p, c in files}
    # 同时提供去除公共前缀后的映射，便于按 detect_modules 返回的路径查找
    norm_paths = _strip_common_prefix([p for p, _ in files])
    norm_map = dict(zip(norm_paths, [c for _, c in files]))

    parts = []
    for rp in rel_paths:
        content = norm_map.get(rp) or content_map.get(rp.replace("\\", "/").lstrip("/"))
        if content is None:
            continue
        parts.append(f"// ===== {rp} =====\n{content}")
    return "\n\n".join(parts)


def merge_modules(
    modules: Dict[str, List[str]], names: List[str], new_name: str
) -> Dict[str, List[str]]:
    """将多个模块合并为一个新模块。"""
    if not names:
        return modules
    merged: List[str] = []
    result: Dict[str, List[str]] = {}
    for name, plist in modules.items():
        if name in names:
            merged.extend(plist)
        else:
            result[name] = plist
    result[new_name] = sorted(merged)
    return result


def rename_module(
    modules: Dict[str, List[str]], old_name: str, new_name: str
) -> Dict[str, List[str]]:
    """重命名模块（保持顺序）。"""
    if old_name == new_name or old_name not in modules:
        return modules
    result: Dict[str, List[str]] = {}
    for name, plist in modules.items():
        result[new_name if name == old_name else name] = plist
    return result


def delete_module(modules: Dict[str, List[str]], name: str) -> Dict[str, List[str]]:
    """删除一个模块。"""
    return {k: v for k, v in modules.items() if k != name}


def split_module(
    modules: Dict[str, List[str]],
    name: str,
    move_paths: List[str],
    new_name: str,
) -> Dict[str, List[str]]:
    """从模块 ``name`` 中拆出 ``move_paths`` 形成新模块 ``new_name``。"""
    if name not in modules or not move_paths:
        return modules
    move_set = set(move_paths)
    remain = [p for p in modules[name] if p not in move_set]
    moved = [p for p in modules[name] if p in move_set]
    result: Dict[str, List[str]] = {}
    for k, v in modules.items():
        if k == name:
            if remain:
                result[name] = remain
        else:
            result[k] = v
    if moved:
        result[new_name] = sorted(moved)
    return result


def sanitize_module_prefix(name: str) -> str:
    """从模块名生成 2~4 字符的大写追溯 ID 前缀。

    示例：
        MotorControl -> MC
        motor_control -> MC
        brake -> BRK
        abs_mod -> AM
    """
    cleaned = re.sub(r"[^0-9A-Za-z_]", "", name)
    if not cleaned:
        return "MOD"

    # snake_case：取各下划线分段首字母
    if "_" in cleaned:
        parts = [p for p in cleaned.split("_") if p]
        prefix = "".join(p[0] for p in parts).upper()
        if len(prefix) >= 2:
            return prefix[:4]

    # CamelCase：取大写字母
    uppers = re.findall(r"[A-Z]", cleaned)
    if len(uppers) >= 2:
        return "".join(uppers)[:4].upper()

    # 兜底：前 3 个字母
    base = re.sub(r"[^A-Za-z]", "", cleaned)
    if base:
        return base[:3].upper()
    return "MOD"
