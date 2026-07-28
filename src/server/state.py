# -*- coding: utf-8 -*-
"""
state.py — 应用状态单例（替代 Streamlit 的 st.session_state）。

单用户本地场景：一个进程内内存单例即状态源，配合 saved_results.json 持久化。
封装活动模块派生视图、文档读写、持久化（防抖写盘）、日志、配置管理。
"""

import os
import sys
import json
import stat
import time
import threading

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # -> src/
_SAVE_FILE = os.path.normpath(os.path.join(_BASE_DIR, "..", "saved_results.json"))
_LOG_FILE = os.path.normpath(os.path.join(_BASE_DIR, "..", "generation_log.jsonl"))


def _default_config() -> dict:
    """返回默认配置。"""
    return {
        "provider": "openai",
        "api_key": "",
        "api_keys": [],
        "api_base": None,
        "model": "",
        "temperature": 0.15,
        "module_name": "目标模块",
        "asil_level": "ASIL B",
        "thinking_enabled": False,
        "thinking_intensity": 5,
    }


class AppState:
    """进程内单例应用状态。"""

    def __init__(self):
        # ── 工程级多模块 ──
        self.project_modules = {}   # {module_name: code_str}
        self.module_files = {}      # {module_name: [rel_path, ...]}
        self.active_module = None   # 当前工作模块名
        self.selected_modules = []  # 批量生成范围
        self.docs_by_module = {}    # {module_name: {agent_type: content}}

        # ── 生成相关 ──
        self.generation_history = []      # [{timestamp, module, doc_type, status, validation}]
        self.agent_templates = {}         # {agent_type: template_text}
        self.doc_versions = {}            # {module::agent_type: [old_content, ...]}
        self.token_usage = {}             # {module::agent_type: {...}}
        self.batch_checkpoint = {}        # {module: {agent_type: "done"}}
        self.cancel_generation = False    # 批量取消标志

        # ── 配置（仅内存，api_key 不落盘）──
        self.config = _default_config()

        # 解析缓存：{code_hash: analysis_dict}
        self._analysis_cache = {}
        # 校验缓存：{(agent_type, content_hash): report}
        self._validation_cache = {}

        self._lock = threading.RLock()
        self._persist_timer = None

    # ------------------------------------------------------------------
    # 活动模块派生视图
    # ------------------------------------------------------------------

    def default_module_name(self) -> str:
        return self.config.get("module_name") or "目标模块"

    def active_module_name(self) -> str:
        am = self.active_module
        if am and am in self.project_modules:
            return am
        if self.project_modules:
            return next(iter(self.project_modules))
        return self.default_module_name()

    def get_module_docs(self, module: str = None) -> dict:
        """获取指定模块（默认活动模块）的文档字典引用（懒创建）。"""
        mod = module or self.active_module_name()
        return self.docs_by_module.setdefault(mod, {})

    def active_docs(self) -> dict:
        return self.get_module_docs(self.active_module_name())

    def active_code(self) -> str:
        am = self.active_module_name()
        return self.project_modules.get(am, "")

    def module_code(self, module: str) -> str:
        return self.project_modules.get(module, "")

    def modules_snapshot(self) -> dict:
        """构建模块列表快照（供前端渲染工程视图）。"""
        from module_detector import sanitize_module_prefix
        mods = []
        for name, code in self.project_modules.items():
            files = self.module_files.get(name, [])
            mods.append({
                "name": name,
                "files": files,
                "file_count": len(files),
                "lines": code.count("\n") + 1 if code else 0,
                "prefix": sanitize_module_prefix(name),
                "doc_count": len(self.docs_by_module.get(name, {})),
            })
        return {
            "modules": mods,
            "active_module": self.active_module_name() if self.project_modules else None,
            "selected_modules": self.selected_modules,
            "has_code": bool(self.active_code()),
            "default_module_name": self.default_module_name(),
        }

    # ------------------------------------------------------------------
    # 模块状态更新
    # ------------------------------------------------------------------

    def set_modules(self, project_modules: dict, module_files: dict):
        """写入检测出的模块，重置活动模块与批量范围。"""
        with self._lock:
            self.project_modules = project_modules
            self.module_files = module_files
            self.active_module = next(iter(project_modules), None) if project_modules else None
            self.selected_modules = list(project_modules.keys())

    def clear_modules(self):
        with self._lock:
            self.project_modules = {}
            self.module_files = {}
            self.active_module = None
            self.selected_modules = []

    # ------------------------------------------------------------------
    # 文档版本 / Token 用量（按 模块::agent 组织，跨模块隔离）
    # ------------------------------------------------------------------

    def _vk(self, module: str, agent_type: str) -> str:
        return f"{module}::{agent_type}"

    def push_version(self, module: str, agent_type: str, old_content: str):
        key = self._vk(module, agent_type)
        lst = self.doc_versions.setdefault(key, [])
        lst.append(old_content)
        self.doc_versions[key] = lst[-5:]

    def get_versions(self, module: str, agent_type: str) -> list:
        return self.doc_versions.get(self._vk(module, agent_type), [])

    def set_token_usage(self, module: str, agent_type: str, usage: dict):
        self.token_usage[self._vk(module, agent_type)] = usage

    def get_token_usage(self, module: str, agent_type: str):
        return self.token_usage.get(self._vk(module, agent_type))

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------

    def update_config(self, patch: dict):
        with self._lock:
            self.config.update(patch)
        return self.config

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def load_persisted(self):
        """启动时从本地 JSON 加载历史结果。"""
        if not os.path.exists(_SAVE_FILE):
            return
        try:
            with open(_SAVE_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                return
            data = json.loads(content)
            if data.get("docs_by_module"):
                self.docs_by_module = data["docs_by_module"]
            elif data.get("generated_docs"):
                mod = self.default_module_name()
                self.docs_by_module.setdefault(mod, {}).update(data["generated_docs"])
            if data.get("history"):
                self.generation_history = data["history"]
        except Exception as e:
            print(f"[WARN] 加载持久化数据失败: {e}", file=sys.stderr)

    def persist(self):
        """防抖写盘（500ms 内多次调用只执行一次）。"""
        def _do_save():
            try:
                with open(_SAVE_FILE, "w", encoding="utf-8") as f:
                    json.dump({
                        "docs_by_module": self.docs_by_module,
                        "history": self.generation_history[-50:],
                    }, f, ensure_ascii=False)
                try:
                    os.chmod(_SAVE_FILE, stat.S_IRUSR | stat.S_IWUSR)
                except OSError:
                    pass
            except Exception as e:
                print(f"[WARN] 保存数据失败: {e}", file=sys.stderr)

        with self._lock:
            if self._persist_timer is not None:
                self._persist_timer.cancel()
            self._persist_timer = threading.Timer(0.5, _do_save)
            self._persist_timer.daemon = True
            self._persist_timer.start()

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------

    def log_generation(self, doc_type, module_name, provider, model,
                       prompt_tokens, output_tokens, duration, success, error=""):
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "doc_type": doc_type,
            "module": module_name,
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "duration_sec": round(duration, 1),
            "success": success,
            "error": error,
        }
        try:
            with open(_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[WARN] 日志写入失败: {e}", file=sys.stderr)

    def add_history(self, module, doc_type, status, validation=""):
        self.generation_history.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "module": module,
            "doc_type": doc_type,
            "status": status,
            "validation": validation,
        })


# 进程内单例
STATE = AppState()
