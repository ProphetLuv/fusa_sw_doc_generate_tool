# -*- coding: utf-8 -*-
"""generate.py — 生成路由（单 Agent SSE / 批量 SSE / 取消）。"""

from fastapi import APIRouter
from typing import Optional

from server.state import STATE
from server.sse import sse_response
from server import generation as gen
from server.estimate import AGENT_ORDER

router = APIRouter(prefix="/api/generate", tags=["generate"])


@router.get("/batch/stream")
def generate_batch_stream(agents: Optional[str] = None, modules: Optional[str] = None):
    """批量流式生成（SSE）。

    agents：逗号分隔的 Agent 名（如 SRS,SAD），缺省为全部 7 个。
    modules：逗号分隔的模块名，缺省用 STATE.selected_modules（工程总览的勾选范围）。
        单文档工作台多选模块时会显式传入，避免与工程总览的勾选状态相互干扰。

    注：此路由必须定义在 /{agent}/stream 之前，否则 "batch" 会被动态路由当作 agent 名抢先匹配。
    """
    agent_list = None
    if agents:
        agent_list = [a.strip().upper() for a in agents.split(",") if a.strip()]
    module_list = None
    if modules:
        module_list = [m.strip() for m in modules.split(",") if m.strip()]
    return sse_response(gen.generate_batch_stream(dict(STATE.config), agents=agent_list, modules=module_list))


@router.get("/{agent}/stream")
def generate_agent_stream(
    agent: str,
    module: Optional[str] = None,
    chunked: bool = False,
    chunk_inject: bool = False,
    review: bool = False,
    max_tokens: Optional[int] = None,
    review_provider: Optional[str] = None,
    review_api_key: Optional[str] = None,
    review_api_base: Optional[str] = None,
    review_model: Optional[str] = None,
):
    """单 Agent 流式生成（SSE）。chunk_inject：分段并发时每段同步注入安全知识库。"""
    agent = agent.upper()
    review_cfg = None
    if review and review_api_key:
        review_cfg = {
            "provider": review_provider or "openai",
            "api_key": review_api_key,
            "api_base": review_api_base or None,
            "model": review_model or "",
            "temperature": STATE.config.get("temperature", 0.2),
        }
    custom_template = STATE.agent_templates.get(agent)
    ev = gen.generate_single_stream(
        agent, module, dict(STATE.config),
        chunked_mode=chunked, review_mode=review, review_cfg=review_cfg,
        max_tokens=max_tokens, custom_template=custom_template,
        chunk_inject=chunk_inject,
    )
    return sse_response(ev)


@router.post("/cancel")
def cancel_generation():
    """设置取消标志，批量生成将在下一步中断。"""
    STATE.cancel_generation = True
    return {"cancelled": True}
