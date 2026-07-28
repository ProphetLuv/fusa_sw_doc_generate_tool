# -*- coding: utf-8 -*-
"""routers 包 —— 按域拆分的 FastAPI 路由。"""

from server.routers import config, upload, modules, estimate, generate, docs

__all__ = ["config", "upload", "modules", "estimate", "generate", "docs"]
