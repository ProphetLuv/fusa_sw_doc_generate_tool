# -*- coding: utf-8 -*-
"""estimate.py — Token 预估路由（单 Agent / 批量 / 全工程）。"""

from fastapi import APIRouter, HTTPException

from server.state import STATE
from server.estimate import (
    estimate_agent_total_tokens, estimate_batch_total_tokens,
    get_agent_token_defaults, AGENT_ORDER,
)
from llm_engine import estimate_cost

router = APIRouter(prefix="/api/estimate", tags=["estimate"])


def _resolve_module(module: str = None) -> str:
    return module or STATE.active_module_name()


@router.get("/agent/{agent}")
def estimate_agent(agent: str, module: str = None,
                   chunked: bool = False, review: bool = False):
    """单 Agent Token 预估。"""
    agent = agent.upper()
    if agent not in AGENT_ORDER:
        raise HTTPException(status_code=400, detail=f"未知 Agent: {agent}")
    mod = _resolve_module(module)
    code = STATE.module_code(mod) or STATE.active_code()
    est = estimate_agent_total_tokens(
        agent, code,
        asil_level=STATE.config.get("asil_level", "ASIL B"),
        chunked_mode=chunked, review_mode=review,
        generated_docs=STATE.get_module_docs(mod),
    )
    est["cost"] = estimate_cost(est["grand_total"], STATE.config.get("provider", "openai"))
    est["default_max_tokens"] = get_agent_token_defaults(
        STATE.config.get("asil_level", "ASIL B")).get(agent, 8192)
    return est


@router.get("/batch")
def estimate_batch(module: str = None):
    """批量预估。指定 module 则单模块；否则按 selected_modules 汇总全工程。"""
    asil = STATE.config.get("asil_level", "ASIL B")
    provider = STATE.config.get("provider", "openai")

    if module or len(STATE.project_modules) <= 1:
        mod = _resolve_module(module)
        code = STATE.module_code(mod) or STATE.active_code()
        result = estimate_batch_total_tokens(code, asil, STATE.get_module_docs(mod))
        result["cost"] = estimate_cost(result["total"], provider)
        result["scope"] = "single"
        return result

    # 多模块：按 selected_modules 汇总
    selected = STATE.selected_modules or list(STATE.project_modules.keys())
    total = 0
    for mn in selected:
        mc = STATE.project_modules.get(mn, "")
        if mc:
            total += estimate_batch_total_tokens(mc, asil, STATE.get_module_docs(mn))["total"]
    return {
        "total": total, "cost": estimate_cost(total, provider),
        "scope": "project", "module_count": len(selected),
    }
