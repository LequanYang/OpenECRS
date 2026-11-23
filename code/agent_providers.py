# -*- coding: utf-8 -*-
"""LLM providers: hosted OpenAI-compatible API or a local fine-tuned adapter."""
from __future__ import annotations

import json
import time

import agent_llm
import agent_local
import agent_settings


class LLMRequiredError(RuntimeError):
    """Raised when the agent has no usable LLM configured."""

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


class ProviderError(RuntimeError):
    """Raised when the configured LLM fails."""


class APIProvider:
    def __init__(self, config: dict):
        self.config = config
        self.model_name = config["model"]

    def complete(self, messages: list[dict], max_tokens: int | None = None,
                 temperature: float | None = None) -> dict:
        config = dict(self.config)
        if temperature is not None:
            config["temperature"] = temperature
        try:
            result = agent_llm.chat_completion(config, messages, max_tokens=max_tokens)
        except agent_llm.LLMError as exc:
            raise ProviderError(str(exc))
        return {
            "content": result["content"],
            "model": result.get("model") or config["model"],
            "latency_ms": result.get("latency_ms", 0),
            "usage": result.get("usage") or {},
        }


class LocalProvider(agent_local.LocalProvider):
    def __init__(self, config: dict):
        super().__init__(config)
        self.model_name = f"local:{config['adapter'].rstrip('/').split('/')[-1]}"


def provider_info(settings: dict | None = None) -> dict:
    settings = settings or agent_settings.load_settings()
    if settings["backend"] == "api":
        api = agent_settings.resolve_api(settings)
        return {"backend": "api", "model": api["model"], "label": f"API · {api['model']}"}
    local = agent_settings.resolve_local(settings)
    name = local["adapter"].rstrip("/").split("/")[-1] or "local"
    return {"backend": "local", "model": name, "label": f"Local · {name}"}


def get_provider(settings: dict | None = None):
    settings = settings or agent_settings.load_settings()
    if settings["backend"] == "api":
        api = agent_settings.resolve_api(settings)
        if not api["api_key"]:
            raise LLMRequiredError(
                "OpenECRS requires an LLM: no API key is configured.",
                "Open Settings → API, paste your OpenAI-compatible key and click Test connection.",
            )
        return APIProvider(api)
    local = agent_settings.resolve_local(settings)
    status = agent_settings.local_status(settings)
    if not status["ready"]:
        raise LLMRequiredError(
            "OpenECRS requires an LLM: the local model is not ready.",
            "; ".join(status["missing"]),
        )
    return LocalProvider(local)


def test_provider(settings: dict | None = None) -> dict:
    settings = settings or agent_settings.load_settings()
    started = time.time()
    if settings["backend"] == "api":
        api = agent_settings.resolve_api(settings)
        if not api["api_key"]:
            return {"ok": False, "backend": "api", "model": api["model"], "latency_ms": 0,
                    "error": "No API key configured. / 还没有配置 API Key"}
        try:
            result = agent_llm.chat_completion(api, [
                {"role": "system", "content": "Reply with exactly: ok"},
                {"role": "user", "content": "ping"},
            ], max_tokens=16)
            return {"ok": True, "backend": "api", "model": result["model"],
                    "latency_ms": result["latency_ms"], "reply": result["content"].strip()[:40], "error": ""}
        except agent_llm.LLMError as exc:
            return {"ok": False, "backend": "api", "model": api["model"], "latency_ms": 0,
                    "error": str(exc)}
    status = agent_settings.local_status(settings)
    local = agent_settings.resolve_local(settings)
    if not status["ready"]:
        return {"ok": False, "backend": "local", "model": local["adapter"],
                "latency_ms": int((time.time() - started) * 1000),
                "error": "; ".join(status["missing"])}
    return {"ok": True, "backend": "local", "model": local["adapter"],
            "latency_ms": int((time.time() - started) * 1000),
            "reply": "local model files found; the first generation may take a while",
            "error": ""}
