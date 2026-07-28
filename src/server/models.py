# -*- coding: utf-8 -*-
"""models.py — FastAPI 请求/响应 Pydantic 模型。"""

from typing import List, Optional
from pydantic import BaseModel


class ConfigModel(BaseModel):
    provider: str = "openai"
    api_key: str = ""
    api_keys: List[str] = []
    api_base: Optional[str] = None
    model: str = ""
    temperature: float = 0.15
    module_name: str = "目标模块"
    asil_level: str = "ASIL B"
    thinking_enabled: bool = False
    thinking_intensity: int = 5  # 1-10, 默认中档
    background_prompt: str = ""  # 项目背景描述，注入到所有 Agent Prompt 开头


class ConfigPatch(BaseModel):
    provider: Optional[str] = None
    api_key: Optional[str] = None
    api_keys: Optional[List[str]] = None
    api_base: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    module_name: Optional[str] = None
    asil_level: Optional[str] = None
    thinking_enabled: Optional[bool] = None
    thinking_intensity: Optional[int] = None
    background_prompt: Optional[str] = None


class PasteRequest(BaseModel):
    code: str
    module_name: Optional[str] = None


class LocalPathRequest(BaseModel):
    path: str


class MergeRequest(BaseModel):
    names: List[str]
    new_name: str


class RenameRequest(BaseModel):
    old_name: str
    new_name: str


class DeleteRequest(BaseModel):
    name: str


class ActiveModuleRequest(BaseModel):
    module: str


class SelectedModulesRequest(BaseModel):
    modules: List[str]


class CrossValidateRequest(BaseModel):
    module: Optional[str] = None
