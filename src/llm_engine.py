# -*- coding: utf-8 -*-
"""
LLM 统一调用引擎
支持 OpenAI、Anthropic Claude、通义千问（DashScope 兼容接口）、
DeepSeek、智谱 GLM（ChatGLM）、Kimi（Moonshot）以及自定义兼容 API。
含自动重试、超时保护、Token 估算。
"""

import time as _time
from typing import Generator, Optional

import streamlit as st

# 系统级角色提示，固定为功能安全工程师角色
SYSTEM_PROMPT = (
    "你是一位资深的功能安全工程师，精通 ISO 26262、IEC 61508、ASPICE 等标准。"
    "请严格按照要求的格式输出文档。"
)

# 各供应商默认模型映射
DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-3-5-sonnet-20241022",
    "dashscope": "qwen3.7-max",
    "deepseek": "deepseek-v4-pro",
    "glm": "glm-5.2",
    "kimi": "kimi-k3",
}

# 各供应商 OpenAI 兼容接口 base_url
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
KIMI_BASE_URL = "https://api.moonshot.cn/v1"

# provider → 默认 base_url 映射（None 表示使用 SDK 默认值）
PROVIDER_BASE_URLS = {
    "dashscope": DASHSCOPE_BASE_URL,
    "deepseek": DEEPSEEK_BASE_URL,
    "glm": GLM_BASE_URL,
    "kimi": KIMI_BASE_URL,
}


class LLMEngine:
    """
    大模型统一调用引擎。
    通过 provider 参数选择底层供应商，对外暴露统一的 stream_generate 接口。
    """

    def __init__(
        self,
        provider: str,
        api_key: str,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 8192,
        temperature: float = 0.2,
        max_retries: int = 3,
        timeout: int = 300,
    ):
        """
        初始化 LLM 引擎。

        Args:
            provider:    供应商名称，可选 openai / anthropic / dashscope / deepseek / glm / custom
            api_key:     API 密钥（仅保存在内存，不落盘）
            api_base:    自定义 base_url（custom 模式必填；其他模式可留空使用默认值）
            model:       模型名称，为空时使用供应商默认值
            max_tokens:  单次响应最大 token 数
            temperature: 温度参数，控制随机性
            max_retries: 失败自动重试次数（默认 3）
            timeout:     单次请求超时秒数（默认 300）
        """
        self.provider = provider.lower().strip()
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.timeout = timeout

        # 确定 base_url
        if self.provider == "custom":
            if not api_base:
                raise ValueError("使用自定义 API 时必须提供 api_base 参数")
            self.api_base = api_base
        else:
            # 优先使用用户传入的 api_base，否则从映射表查找（openai/anthropic 为 None）
            self.api_base = api_base or PROVIDER_BASE_URLS.get(self.provider)

        # 确定模型名称
        if model:
            self.model = model
        elif self.provider in DEFAULT_MODELS:
            self.model = DEFAULT_MODELS[self.provider]
        else:
            self.model = "gpt-4o"  # 兜底默认

        # 复用客户端实例（避免每次请求都重建 HTTP 连接池）
        self._openai_client = None
        self._anthropic_client = None

        # 最近一次生成的实际 Token 用量（由 API 返回）
        self.last_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def _get_openai_client(self):
        """获取或创建 OpenAI 兼容客户端（复用连接池）。"""
        if self._openai_client is None:
            from openai import OpenAI
            client_kwargs = {"api_key": self.api_key, "timeout": self.timeout}
            if self.api_base:
                client_kwargs["base_url"] = self.api_base
            self._openai_client = OpenAI(**client_kwargs)
        return self._openai_client

    def _get_anthropic_client(self):
        """获取或创建 Anthropic 客户端（复用连接池）。"""
        if self._anthropic_client is None:
            import anthropic
            self._anthropic_client = anthropic.Anthropic(
                api_key=self.api_key, timeout=self.timeout
            )
        return self._anthropic_client

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def stream_generate(self, prompt: str) -> Generator[str, None, None]:
        """
        流式生成文本（含自动重试 + 超时保护）。

        重试策略：实时逐 chunk yield 以保证流式体验。
        若首次尝试在接收到任何 chunk 之前即失败，则自动重试；
        若已有部分输出后失败，则直接抛出异常由调用方处理。
        """
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                start = _time.time()
                received_any = False
                if self.provider in ("openai", "dashscope", "deepseek", "glm", "kimi", "custom"):
                    for chunk in self._stream_openai(prompt, start):
                        received_any = True
                        yield chunk
                elif self.provider == "anthropic":
                    for chunk in self._stream_anthropic(prompt, start):
                        received_any = True
                        yield chunk
                else:
                    raise ValueError(f"不支持的 provider: {self.provider}")
                return  # 成功完成
            except Exception as e:
                last_error = e
                # 已有部分输出后失败 → 不重试，直接抛出
                if received_any:
                    raise RuntimeError(
                        f"API 调用中途失败: {last_error}"
                    ) from last_error
                if attempt < self.max_retries:
                    _time.sleep(2 * attempt)  # 指数退避: 2s, 4s, 6s
                    continue
                raise RuntimeError(
                    f"API 调用失败（已重试 {self.max_retries} 次）: {last_error}"
                ) from last_error

    # ------------------------------------------------------------------
    # OpenAI 兼容接口（含通义千问 DashScope、DeepSeek、智谱 GLM）
    # ------------------------------------------------------------------

    def _stream_openai(self, prompt: str, start: float) -> Generator[str, None, None]:
        """通过 OpenAI SDK（兼容 DashScope / DeepSeek / GLM / 自定义 API）进行流式生成。"""
        client = self._get_openai_client()

        stream = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=True,
            stream_options={"include_usage": True},
        )

        for chunk in stream:
            if _time.time() - start > self.timeout:
                raise TimeoutError(f"生成超时（>{self.timeout}s）")
            # 捕获最后一个 chunk 中的 usage 信息
            if hasattr(chunk, "usage") and chunk.usage:
                self.last_usage = {
                    "prompt_tokens": chunk.usage.prompt_tokens or 0,
                    "completion_tokens": chunk.usage.completion_tokens or 0,
                    "total_tokens": chunk.usage.total_tokens or 0,
                }
            # 部分兼容接口可能返回空 choices
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content

    # ------------------------------------------------------------------
    # Anthropic Claude 接口
    # ------------------------------------------------------------------

    def _stream_anthropic(self, prompt: str, start: float) -> Generator[str, None, None]:
        """通过 Anthropic SDK 进行流式生成。"""
        client = self._get_anthropic_client()

        with client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                if _time.time() - start > self.timeout:
                    raise TimeoutError(f"生成超时（>{self.timeout}s）")
                yield text
            # 流结束后获取最终消息中的 usage
            try:
                final_msg = stream.get_final_message()
                if final_msg and final_msg.usage:
                    self.last_usage = {
                        "prompt_tokens": final_msg.usage.input_tokens or 0,
                        "completion_tokens": final_msg.usage.output_tokens or 0,
                        "total_tokens": (final_msg.usage.input_tokens or 0) + (final_msg.usage.output_tokens or 0),
                    }
            except Exception:
                pass  # 部分版本不支持，静默跳过


# ======================================================================
# Token 估算工具
# ======================================================================

@st.cache_data(ttl=3600, max_entries=256)
def estimate_tokens(text: str) -> int:
    """粗略估算文本 token 数（中文 ~1.5字/token，代码 ~3.5字符/token）。"""
    if not text:
        return 0
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other = len(text) - chinese
    return int(chinese / 1.5 + other / 3.5)


@st.cache_data(ttl=3600, max_entries=256)
def estimate_cost(tokens: int, provider: str) -> str:
    """根据 token 数估算费用（仅供参考）。"""
    PRICING = {
        "openai": (0.005, 0.015), "anthropic": (0.003, 0.015),
        "dashscope": (0.002, 0.006), "deepseek": (0.001, 0.002),
        "glm": (0.001, 0.001), "kimi": (0.002, 0.002),
    }
    inp, out = PRICING.get(provider, (0.003, 0.006))
    input_t = int(tokens * 0.67)
    output_t = tokens - input_t
    cost = (input_t / 1000 * inp) + (output_t / 1000 * out)
    return f"~${cost:.4f}"
