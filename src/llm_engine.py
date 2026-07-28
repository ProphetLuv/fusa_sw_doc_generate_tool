# -*- coding: utf-8 -*-
"""
LLM 统一调用引擎
支持 OpenAI、Anthropic Claude、通义千问（DashScope 兼容接口）、
DeepSeek、智谱 GLM（ChatGLM）、Kimi（Moonshot）以及自定义兼容 API。
含自动重试、超时保护、Token 估算。
"""

import time as _time
from functools import lru_cache
from typing import Generator, Optional

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

# provider 别名映射（用户配置中可能使用的非标准名称 → 内部标准名）
PROVIDER_ALIASES = {
    "zhipu": "glm",
    "chatglm": "glm",
    "bigmodel": "glm",
    "qwen": "dashscope",
    "tongyi": "dashscope",
    "moonshot": "kimi",
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
        max_retries: int = 5,
        timeout: int = 300,
        thinking_enabled: bool = False,
        thinking_intensity: int = 5,
    ):
        """
        初始化 LLM 引擎。

        Args:
            provider:          供应商名称，可选 openai / anthropic / dashscope / deepseek / glm / custom
            api_key:           API 密钥（仅保存在内存，不落盘）
            api_base:          自定义 base_url（custom 模式必填；其他模式可留空使用默认值）
            model:             模型名称，为空时使用供应商默认值
            max_tokens:        单次响应最大 token 数
            temperature:       温度参数，控制随机性
            max_retries:       失败自动重试次数（默认 5）
            timeout:           单次请求超时秒数（默认 300）
            thinking_enabled:  是否启用思考/推理模式（仅部分模型支持）
            thinking_intensity: 思考强度 1-10（越大推理越深，Token 消耗越多）
        """
        self.provider = provider.lower().strip()
        # 别名归一化：zhipu→glm, qwen→dashscope 等
        self.provider = PROVIDER_ALIASES.get(self.provider, self.provider)
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.timeout = timeout
        self.thinking_enabled = thinking_enabled
        self.thinking_intensity = max(1, min(10, thinking_intensity))  # 钳位 1-10

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

    def _thinking_kwargs(self) -> dict:
        """根据 provider 与思考设置，返回需注入的 API 参数字典。

        各 provider 支持情况：
        - OpenAI o1/o3: 使用 reasoning_effort 参数（low/medium/high）
        - DeepSeek V4:  默认开启思考，统一使用 reasoning_effort=high；
                        须通过 extra_body {"thinking": {"type": "enabled"}} 传入
        - DashScope 千问: 通过 extra_body {"enable_thinking": True} 开启，
                        推理过程通过 reasoning_content 字段返回（不混入正文）
        - Anthropic:     使用 thinking 块 {"type": "enabled", "budget_tokens": N}
        - 其他 provider: 返回空字典（不注入，由模型自行忽略）
        """
        if not self.thinking_enabled:
            return {}
        ti = self.thinking_intensity
        # 强度 → 三档映射
        if ti <= 3:
            level = "low"
        elif ti <= 7:
            level = "medium"
        else:
            level = "high"

        if self.provider == "openai":
            return {"reasoning_effort": level}
        elif self.provider == "deepseek":
            # DeepSeek V4 思考模式默认开启，且 low/medium 均映射为 high
            # xhigh→max 仅用于 Agent 类请求，此处统一使用 high
            return {
                "reasoning_effort": "high",
                "extra_body": {"thinking": {"type": "enabled"}},
            }
        elif self.provider == "dashscope":
            # 千问思考模式：通过 extra_body 传入 enable_thinking=True
            # 推理过程以 reasoning_content 返回，_stream_openai 仅取 content 正文
            return {"extra_body": {"enable_thinking": True}}
        elif self.provider == "anthropic":
            budget_map = {"low": 2048, "medium": 4096, "high": 8192}
            return {"thinking": {"type": "enabled", "budget_tokens": budget_map[level]}}
        # glm / kimi / custom：思考参数暂不注入，模型自行决定
        return {}

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
        流式生成文本（含自动重试 + 断点续传 + 超时保护）。

        重试策略：
        - 完全无响应（未收到任何 chunk）：最多重试 max_retries 次，等待递增（2s/4s/6s/8s/10s）
        - 中途断开（已有部分输出）：断点续传，将已生成内容作为上下文，
          请求模型从中断处继续输出，最多续传 max_retries 次
        """
        last_error = None
        accumulated_text = ""  # 累计已收到的文本（用于断点续传）

        for attempt in range(1, self.max_retries + 1):
            try:
                start = _time.time()
                received_any = False

                if self.provider in ("openai", "dashscope", "deepseek", "glm", "kimi", "custom"):
                    for chunk in self._stream_openai(prompt, start, prior_text=accumulated_text or None):
                        received_any = True
                        accumulated_text += chunk
                        yield chunk
                elif self.provider == "anthropic":
                    for chunk in self._stream_anthropic(prompt, start, prior_text=accumulated_text or None):
                        received_any = True
                        accumulated_text += chunk
                        yield chunk
                else:
                    raise ValueError(f"不支持的 provider: {self.provider}")
                return  # 成功完成
            except Exception as e:
                last_error = e
                if received_any and attempt < self.max_retries:
                    # 中途断开 → 断点续传：等待后从已有内容继续
                    _time.sleep(2 * attempt)
                    continue
                if not received_any and attempt < self.max_retries:
                    # 完全无响应 → 等待后重试
                    _time.sleep(2 * attempt)
                    continue
                # 重试次数耗尽
                if accumulated_text:
                    raise RuntimeError(
                        f"API 调用中途失败（已续传 {attempt} 次仍未完成）: {last_error}"
                    ) from last_error
                raise RuntimeError(
                    f"API 调用失败（已重试 {self.max_retries} 次）: {last_error}"
                ) from last_error

    # ------------------------------------------------------------------
    # OpenAI 兼容接口（含通义千问 DashScope、DeepSeek、智谱 GLM）
    # ------------------------------------------------------------------

    def _stream_openai(self, prompt: str, start: float, prior_text: Optional[str] = None) -> Generator[str, None, None]:
        """通过 OpenAI SDK（兼容 DashScope / DeepSeek / GLM / 自定义 API）进行流式生成。

        Args:
            prior_text: 断点续传时已生成的文本，模型将从此处继续输出。
        """
        client = self._get_openai_client()

        if prior_text:
            # 断点续传：将已生成内容作为 assistant 消息，请求继续
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": prior_text},
                {"role": "user", "content": "请从上述内容中断处继续输出，不要重复已有内容，直接输出后续部分。"},
            ]
        else:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

        stream = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=True,
            stream_options={"include_usage": True},
            **self._thinking_kwargs(),
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

    def _stream_anthropic(self, prompt: str, start: float, prior_text: Optional[str] = None) -> Generator[str, None, None]:
        """通过 Anthropic SDK 进行流式生成。

        Args:
            prior_text: 断点续传时已生成的文本，模型将从此处继续输出。
        """
        client = self._get_anthropic_client()

        if prior_text:
            # 断点续传：将已生成内容作为 assistant 消息，请求继续
            messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": prior_text},
                {"role": "user", "content": "请从上述内容中断处继续输出，不要重复已有内容，直接输出后续部分。"},
            ]
        else:
            messages = [{"role": "user", "content": prompt}]

        stream_kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": SYSTEM_PROMPT,
            "messages": messages,
        }
        think = self._thinking_kwargs()
        if think.get("thinking"):
            stream_kwargs["thinking"] = think["thinking"]
        with client.messages.stream(**stream_kwargs) as stream:
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

@lru_cache(maxsize=256)
def estimate_tokens(text: str) -> int:
    """粗略估算文本 token 数（中文 ~1.5字/token，代码 ~3.5字符/token）。"""
    if not text:
        return 0
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other = len(text) - chinese
    return int(chinese / 1.5 + other / 3.5)


@lru_cache(maxsize=256)
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
