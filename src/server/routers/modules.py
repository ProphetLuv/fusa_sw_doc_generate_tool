# -*- coding: utf-8 -*-
"""modules.py — 模块管理路由（列表 / 合并 / 重命名 / 删除 / 活动 / 选择 / 代码 / 分析）。"""

from fastapi import APIRouter, HTTPException

from server.state import STATE
from server.models import (
    MergeRequest, RenameRequest, DeleteRequest,
    ActiveModuleRequest, SelectedModulesRequest,
)
from server import upload as up
from server.generation import get_code_analysis
from module_detector import (
    merge_modules, rename_module, delete_module, build_module_code,
)

router = APIRouter(prefix="/api/modules", tags=["modules"])


@router.get("")
def list_modules():
    return STATE.modules_snapshot()


@router.post("/merge")
def merge(req: MergeRequest):
    if len(req.names) < 2:
        raise HTTPException(status_code=400, detail="至少选择两个模块合并")
    new_files = merge_modules(STATE.module_files, req.names, req.new_name)
    file_tuples = up.file_tuples_from_modules(STATE.module_files, STATE.project_modules)
    STATE.module_files = new_files
    STATE.project_modules = {
        mn: build_module_code(file_tuples, paths) for mn, paths in new_files.items()
    }
    STATE.active_module = req.new_name
    STATE.selected_modules = list(STATE.project_modules.keys())
    return STATE.modules_snapshot()


@router.post("/rename")
def rename(req: RenameRequest):
    if req.old_name not in STATE.project_modules:
        raise HTTPException(status_code=404, detail="模块不存在")
    STATE.module_files = rename_module(STATE.module_files, req.old_name, req.new_name)
    STATE.project_modules = rename_module(STATE.project_modules, req.old_name, req.new_name)
    # docs_by_module 同步重命名（含 result_doc 落盘文件夹）
    if req.old_name in STATE.docs_by_module:
        STATE.docs_by_module[req.new_name] = STATE.docs_by_module.pop(req.old_name)
    STATE.rename_module_result_dir(req.old_name, req.new_name)
    # 同步迁移所有 {module}::{agent} 格式的 key
    for src_dict in (STATE.doc_versions, STATE.token_usage):
        for old_key, val in list(src_dict.items()):
            if old_key.startswith(req.old_name + "::"):
                agent = old_key[len(req.old_name) + 2:]
                src_dict[f"{req.new_name}::{agent}"] = src_dict.pop(old_key)
    if req.old_name in STATE.batch_checkpoint:
        STATE.batch_checkpoint[req.new_name] = STATE.batch_checkpoint.pop(req.old_name)
    if STATE.active_module == req.old_name:
        STATE.active_module = req.new_name
    STATE.selected_modules = [req.new_name if m == req.old_name else m for m in STATE.selected_modules]
    return STATE.modules_snapshot()


@router.post("/delete")
def delete(req: DeleteRequest):
    if len(STATE.project_modules) <= 1:
        raise HTTPException(status_code=400, detail="至少保留一个模块")
    STATE.module_files = delete_module(STATE.module_files, req.name)
    STATE.project_modules = delete_module(STATE.project_modules, req.name)
    STATE.docs_by_module.pop(req.name, None)
    STATE.remove_module_result_dir(req.name)
    if STATE.active_module == req.name:
        STATE.active_module = next(iter(STATE.project_modules), None)
    STATE.selected_modules = [m for m in STATE.selected_modules if m != req.name]
    return STATE.modules_snapshot()


@router.put("/active")
def set_active(req: ActiveModuleRequest):
    if req.module not in STATE.project_modules:
        raise HTTPException(status_code=404, detail="模块不存在")
    STATE.active_module = req.module
    return STATE.modules_snapshot()


@router.put("/selected")
def set_selected(req: SelectedModulesRequest):
    valid = [m for m in req.modules if m in STATE.project_modules]
    STATE.selected_modules = valid
    return STATE.modules_snapshot()


@router.get("/{name}/code")
def get_module_code(name: str):
    if name not in STATE.project_modules:
        raise HTTPException(status_code=404, detail="模块不存在")
    return {"module": name, "code": STATE.project_modules[name]}


@router.get("/{name}/analysis")
def module_analysis(name: str):
    """代码解析（按 code hash 缓存）。"""
    if name not in STATE.project_modules:
        raise HTTPException(status_code=404, detail="模块不存在")
    code = STATE.project_modules[name]
    info = get_code_analysis(code)
    return {"module": name, "analysis": info, "size_kb": len(code) // 1024}
