# -*- coding: utf-8 -*-
"""config.py — 配置读写 / 导入 / 导出路由。"""

import json

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from server.state import STATE
from server.models import ConfigPatch
from llm_engine import DEFAULT_MODELS, PROVIDER_BASE_URLS

router = APIRouter(prefix="/api/config", tags=["config"])


def _mask_api_key(key: str) -> str:
    if not key or len(key) <= 8:
        return "****" if key else ""
    return f"{key[:4]}****{key[-4:]}"


@router.get("")
def get_config():
    """返回当前配置（api_key 明文，仅本地单用户场景）。

    注意：api_keys 仅存储附加 Key，不包含主 Key。
    前端 password 输入框会自动遮蔽 api_key；textarea 中的附加 Key
    为用户显式配置，不做后端脱敏（与 api_key 策略一致）。
    """
    return {
        "config": dict(STATE.config),
        "provider_base_urls": PROVIDER_BASE_URLS,
        "default_models": DEFAULT_MODELS,
    }


@router.put("")
def update_config(patch: ConfigPatch):
    """局部更新配置（仅更新非 None 字段）。"""
    data = {k: v for k, v in patch.dict().items() if v is not None}
    STATE.update_config(data)
    return {"config": STATE.config}


@router.post("/import")
async def import_config(file: UploadFile = File(...)):
    """从上传的 JSON 文件导入 LLM 连接参数。"""
    try:
        raw = (await file.read()).decode("utf-8")
        full = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"解析失败: {e}")

    api_keys = full.get("api_keys", [])
    if isinstance(api_keys, str):
        api_keys = [k.strip() for k in api_keys.splitlines() if k.strip()]
    primary = full.get("api_key", "")
    # api_keys 仅存储附加 Key，不与主 Key 混合（主 Key 通过 api_key 字段单独管理）
    # 注意：导入时若 api_keys 与 api_key 重复则跳过，避免前端 textarea 暴露明文
    final_api_keys = [k for k in api_keys if k and k != primary]

    STATE.update_config({
        "provider": full.get("provider", "openai"),
        "api_key": primary,
        "api_keys": final_api_keys,
        "api_base": full.get("api_base") or None,
        "model": full.get("model", ""),
        "thinking_enabled": full.get("thinking_enabled", False),
        "thinking_intensity": full.get("thinking_intensity", 5),
        "background_prompt": full.get("background_prompt", ""),
    })
    return {"config": STATE.config}


@router.get("/export")
def export_config():
    """导出当前 LLM 连接配置（API Key 脱敏）。"""
    cfg = STATE.config
    provider = cfg.get("provider", "openai")
    export = {
        "provider": provider,
        "api_key": _mask_api_key(cfg.get("api_key", "")),
        "api_base": cfg.get("api_base") or "",
        "model": cfg.get("model") or DEFAULT_MODELS.get(provider, "gpt-4o"),
    }
    return JSONResponse(
        content=export,
        headers={"Content-Disposition": 'attachment; filename="llm_config.json"'},
    )
