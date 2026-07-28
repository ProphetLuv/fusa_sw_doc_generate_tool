# -*- coding: utf-8 -*-
"""generate.py — 生成路由（单 Agent SSE / 批量 SSE / 取消）。"""

from fastapi import APIRouter
from typing import Optional

from server.state import STATE
from server.sse import sse_response
from server import generation as gen
from server.estimate import AGENT_ORDER

router = APIRouter(prefix="/api/generate", tags=["generate"])


@router.get("/{agent}/stream")
def generate_agent_stream(
    agent: str,
    module: Optional[str] = None,
    chunked: bool = False,
    review: bool = False,
    max_tokens: Optional[int] = None,
    review_provider: Optional[str] = None,
    review_api_key: Optional[str] = None,
    review_api_base: Optional[str] = None,
    review_model: Optional[str] = None,
):
    """单 Agent 流式生成（SSE）。"""
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
    )
    return sse_response(ev)


@router.get("/batch/stream")
def generate_batch_stream():
    """批量流式生成（SSE）。"""
    return sse_response(gen.generate_batch_stream(dict(STATE.config)))


@router.post("/cancel")
def cancel_generation():
    """设置取消标志，批量生成将在下一步中断。"""
    STATE.cancel_generation = True
    return {"cancelled": True}
