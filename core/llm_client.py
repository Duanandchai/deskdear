# -*- coding: utf-8 -*-
"""LLM 客户端：封装 OpenAI 兼容标准接口（默认支持 DeepSeek）。

特性：
- 内置多套助手人设（system prompt）；
- 网络超时与各类异常统一转为 LLMError，保证程序不崩溃；
- 无第三方 SDK 依赖，仅使用 requests 直连 /chat/completions。
"""
import json

import requests


class LLMError(Exception):
    """聊天接口调用失败（信息已处理为对用户友好的中文提示）。"""


# 内置助手人设（对话风格）
PERSONAS = {
    "academic": (
        "你是一个专业的大语言模型助手，面向科研与工程人员。你擅长学术研究、"
        "编程开发、文献阅读、数据分析等领域，回答严谨准确、逻辑清晰。"
        "请用简洁专业的方式回复,可以使用 Markdown 格式。"
    ),
    "concise": (
        "你是一个高效的大语言模型助手。回答简洁直接、直击要点，不啰嗦。"
        "请用精炼的方式回复,可以使用 Markdown 格式。"
    ),
    "detailed": (
        "你是一个详尽的大语言模型助手。回答全面细致，会展开说明背景与原理，"
        "帮助用户深入理解问题。请用清晰有条理的方式回复，可以使用 Markdown 格式。"
    ),
}

PERSONA_LABELS = {
    "academic": "学术严谨",
    "concise": "简洁高效",
    "detailed": "详尽解答",
}


class LLMClient:
    """OpenAI 兼容接口客户端。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        persona: str = "academic",
        temperature: float = 0.8,
        timeout: int = 30,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or "deepseek-v4-pro"
        self.persona = persona
        self.temperature = temperature
        self.timeout = timeout

    @classmethod
    def from_config(cls, cfg) -> "LLMClient":
        """从 ConfigManager 构建客户端。"""
        return cls(
            base_url=cfg.get_str("llm.base_url"),
            api_key=cfg.get_str("llm.api_key"),
            model=cfg.get_str("llm.model"),
            persona=cfg.get_str("llm.persona") or "academic",
            temperature=cfg.get_float("llm.temperature") or 0.8,
            timeout=max(5, cfg.get_int("llm.timeout_seconds") or 30),
        )

    def system_prompt(self) -> str:
        return PERSONAS.get(self.persona, PERSONAS["academic"])

    def build_messages(self, history: list[dict]) -> list[dict]:
        """在对话历史前注入人设 system 消息。"""
        return [{"role": "system", "content": self.system_prompt()}] + list(history)

    def chat(self, messages: list[dict]) -> str:
        """发送对话并返回回复文本。任何失败都抛出 LLMError（不抛出原生异常）。"""
        if not self.api_key:
            raise LLMError("尚未填写 API 密钥，请在右键菜单 → 设置面板中配置")
        if not self.base_url:
            raise LLMError("接口地址为空，请先在设置面板中配置")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return str(content).strip()
        except requests.exceptions.Timeout:
            raise LLMError("请求超时，网络可能较慢，请稍后重试")
        except requests.exceptions.ConnectionError:
            raise LLMError("连不上服务器……请检查网络或接口地址是否正确")
        except requests.exceptions.HTTPError as exc:
            status = getattr(exc.response, "status_code", "未知")
            if status == 401:
                raise LLMError("API 密钥无效（401），请检查设置面板中的密钥")
            raise LLMError(f"接口返回错误（HTTP {status}），请检查配置")
        except requests.exceptions.RequestException as exc:
            raise LLMError(f"网络请求失败：{exc}")
        except (KeyError, IndexError, TypeError, ValueError):
            raise LLMError("接口返回的数据格式异常，无法解析")

    def chat_stream(self, messages: list[dict]):
        """流式发送对话，逐块 yield 回复文本片段。

        使用 SSE（Server-Sent Events）协议解析流式响应，
        每收到一个 content 片段就 yield 出去。"""
        if not self.api_key:
            raise LLMError("尚未填写 API 密钥，请在右键菜单 → 设置面板中配置")
        if not self.base_url:
            raise LLMError("接口地址为空，请先在设置面板中配置")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": True,
        }
        try:
            resp = requests.post(
                url, headers=headers, json=payload,
                timeout=self.timeout, stream=True,
            )
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
                    continue
        except requests.exceptions.Timeout:
            raise LLMError("请求超时，网络可能较慢，请稍后重试")
        except requests.exceptions.ConnectionError:
            raise LLMError("连不上服务器……请检查网络或接口地址是否正确")
        except requests.exceptions.HTTPError as exc:
            status = getattr(exc.response, "status_code", "未知")
            if status == 401:
                raise LLMError("API 密钥无效（401），请检查设置面板中的密钥")
            raise LLMError(f"接口返回错误（HTTP {status}），请检查配置")
        except requests.exceptions.RequestException as exc:
            raise LLMError(f"网络请求失败：{exc}")
