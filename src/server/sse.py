# -*- coding: utf-8 -*-
"""sse.py — Server-Sent Events 格式化与流封装。"""

import json
from fastapi.responses import StreamingResponse


def format_event(event: dict) -> str:
    """将 {"event": name, "data": {...}} 格式化为 SSE 文本帧。"""
    name = event.get("event", "message")
    data = json.dumps(event.get("data", {}), ensure_ascii=False)
    return f"event: {name}\ndata: {data}\n\n"


def sse_response(event_gen) -> StreamingResponse:
    """将事件字典生成器封装为 SSE StreamingResponse。"""
    def _stream():
        try:
            for ev in event_gen:
                yield format_event(ev)
        except Exception as e:  # 兜底：把异常作为 error 事件送出
            yield format_event({"event": "error", "data": {"message": str(e)}})

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
