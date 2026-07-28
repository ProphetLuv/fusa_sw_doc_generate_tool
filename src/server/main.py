# -*- coding: utf-8 -*-
"""
main.py — FastAPI 应用入口。

挂载各域路由 + 静态前端（src/webui），启动时加载持久化数据。
运行：在 src 目录下 `python -m uvicorn server.main:app --host 127.0.0.1 --port 8000`
"""

import os
import sys
import logging

# 确保 src 目录在 sys.path 中（业务模块以 src 为根 import）
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# 配置日志（INFO 级别，模板解析等关键操作可追踪）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from server.state import STATE
from server.routers import config, upload, modules, estimate, generate, docs

app = FastAPI(title="软件功能安全文档生成器", version="2.0")

app.include_router(config.router)
app.include_router(upload.router)
app.include_router(modules.router)
app.include_router(estimate.router)
app.include_router(generate.router)
app.include_router(docs.router)

_WEBUI_DIR = os.path.join(_SRC_DIR, "webui")


@app.on_event("startup")
def _on_startup():
    STATE.load_persisted()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(os.path.join(_WEBUI_DIR, "index.html"))


# 静态资源（css / js）挂载到 /static，SPA 页面从根路由提供
app.mount("/static", StaticFiles(directory=_WEBUI_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
