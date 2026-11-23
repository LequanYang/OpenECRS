# -*- coding: utf-8 -*-
"""Optional LLM API bridge (OpenAI-compatible chat completions).

The evidence agent stays fully usable offline. When a user configures an
OpenAI-compatible endpoint (DeepSeek / OpenAI / Moonshot / Qwen DashScope
compatible mode / local Ollama), the one-sentence advice and the explanation are
rewritten by the model, while all numbers, tables and evidence quotes still come
from the deterministic rule engine.

Settings live in outputs/agent_ui/settings.json (local only, chmod 600) and can
also come from environment variables:
    DEEPSEEK_API_KEY / OPENAI_API_KEY / LLM_API_KEY
    LLM_BASE_URL / LLM_MODEL
"""
from __future__ import annotations

import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parents[1]
SETTINGS_FILE = BASE / "outputs" / "agent_ui" / "settings.json"

DEFAULT_SETTINGS = {
    "enabled": False,
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "",
    "temperature": 0.3,
    "max_tokens": 500,
    "timeout": 60,
}

ALLOWED_KEYS = set(DEFAULT_SETTINGS)

SYSTEM_PROMPT_ZH = (
    "你是中文商业分析智能体「OpenECRS · AI 应用场景机会雷达」。"
    "你只能使用用户消息中给出的证据数据（指标、排名、原文引文）来回答，"
    "严禁编造任何数字、场景、来源或链接；数据里没有的就直说没有。"
    "请只返回一个严格 JSON 对象，不要 Markdown、不要代码块、不要多余文字："
    '{"advice": "一句话建议，不超过 60 个汉字，必须包含关键数字和明确动作",'
    ' "reply": "2-3 句补充说明，可引用指标与证据原句"}'
)

SYSTEM_PROMPT_EN = (
    "You are the English business-analysis agent \"OpenECRS · AI Opportunity Radar\". "
    "Use ONLY the evidence data supplied in the user message (metrics, ranking, quoted spans). "
    "Never invent numbers, scenarios, sources or links; if the data does not contain something, say so. "
    "Return exactly one strict JSON object, no Markdown, no code fences, no extra text: "
    '{"advice": "one-sentence recommendation, max 45 words, include key numbers and a concrete action",'
    ' "reply": "2-3 supporting sentences that may cite metrics and evidence quotes"}'
)

SYSTEM_PROMPT = SYSTEM_PROMPT_EN


class LLMError(RuntimeError):
    """Raised when the remote model cannot be used."""


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    stored = _read_json(SETTINGS_FILE)
    if isinstance(stored, dict):
        for key in ALLOWED_KEYS:
            if key in stored:
                settings[key] = stored[key]
    return settings


def save_settings(patch: dict | None = None, clear_key: bool = False) -> dict:
    settings = load_settings()
    patch = patch or {}
    for key in ALLOWED_KEYS:
        if key == "api_key" or key not in patch:
            continue
        settings[key] = patch[key]
    if clear_key:
        settings["api_key"] = ""
    if patch.get("api_key"):
        settings["api_key"] = str(patch["api_key"]).strip()
    base_url = str(settings.get("base_url") or "").strip().rstrip("/")
    if base_url and not base_url.startswith(("http://", "https://")):
        raise LLMError("Base URL 必须以 http:// 或 https:// 开头")
    settings["base_url"] = base_url or DEFAULT_SETTINGS["base_url"]
    settings["model"] = str(settings.get("model") or "").strip() or DEFAULT_SETTINGS["model"]
    try:
        settings["temperature"] = max(0.0, min(2.0, float(settings.get("temperature", 0.3))))
        settings["max_tokens"] = max(64, min(4000, int(settings.get("max_tokens", 500))))
        settings["timeout"] = max(5, min(180, int(settings.get("timeout", 60))))
    except (TypeError, ValueError):
        raise LLMError("temperature / max_tokens / timeout 需要是数字")
    settings["enabled"] = bool(settings.get("enabled"))
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(SETTINGS_FILE, 0o600)
    except OSError:
        pass
    return settings


def _env_key(base_url: str) -> tuple[str, str]:
    for name in ("LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value, name
    return "", ""


def resolve_config(settings: dict | None = None) -> dict:
    settings = settings or load_settings()
    base_url = str(settings.get("base_url") or DEFAULT_SETTINGS["base_url"]).strip().rstrip("/")
    model = str(settings.get("model") or DEFAULT_SETTINGS["model"]).strip()
    base_url = os.environ.get("LLM_BASE_URL", base_url).strip().rstrip("/") or base_url
    model = os.environ.get("LLM_MODEL", model).strip() or model
    api_key = str(settings.get("api_key") or "").strip()
    key_source = "settings" if api_key else ""
    if not api_key:
        api_key, env_name = _env_key(base_url)
        key_source = f"env:{env_name}" if env_name else ""
    return {
        "enabled": bool(settings.get("enabled")),
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "key_source": key_source,
        "temperature": float(settings.get("temperature", 0.3)),
        "max_tokens": int(settings.get("max_tokens", 500)),
        "timeout": int(settings.get("timeout", 60)),
    }


def public_settings() -> dict:
    settings = load_settings()
    config = resolve_config(settings)
    key = config["api_key"]
    return {
        "enabled": bool(settings.get("enabled")),
        "base_url": config["base_url"],
        "model": config["model"],
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
        "timeout": config["timeout"],
        "has_key": bool(key),
        "key_hint": f"…{key[-4:]}" if key else "",
        "key_source": config["key_source"],
        "env_key_available": bool(os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
                                  or os.environ.get("LLM_API_KEY")),
        "ready": bool(config["enabled"] and config["api_key"]),
    }


def provider_label(base_url: str) -> str:
    host = urlparse(base_url).netloc or base_url
    return host


def _ssl_context():
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # pragma: no cover - fallback for minimal environments
        return ssl.create_default_context()


def _endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def chat_completion(config: dict, messages: list[dict], max_tokens: int | None = None) -> dict:
    if not config.get("api_key"):
        raise LLMError("还没有配置 API Key")
    payload = {
        "model": config["model"],
        "messages": messages,
        "temperature": config.get("temperature", 0.3),
        "max_tokens": int(max_tokens or config.get("max_tokens", 500)),
        "stream": False,
    }
    request = urllib.request.Request(
        _endpoint(config["base_url"]),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {config['api_key']}",
            "User-Agent": "OpenECRS/1.0",
        },
        method="POST",
    )
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=config.get("timeout", 60), context=_ssl_context()) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "ignore")[:300]
        except Exception:
            pass
        finally:
            try:
                exc.close()
            except Exception:
                pass
        if exc.code in (401, 403):
            raise LLMError(f"API Key 无效或没有权限（HTTP {exc.code}），请检查 Key 与 Base URL 是否匹配")
        if exc.code == 404:
            raise LLMError("接口路径不存在：Base URL 需要是 OpenAI 兼容地址，通常以 /v1 结尾")
        if exc.code == 402:
            raise LLMError("模型账户余额不足（HTTP 402），请先在服务商控制台充值")
        if exc.code == 429:
            raise LLMError("调用频率或额度超限（HTTP 429），请稍后重试")
        raise LLMError(f"模型接口返回 HTTP {exc.code}：{body or exc.reason}")
    except (TimeoutError, socket.timeout):
        raise LLMError("连接超时：请检查网络、Base URL 或代理设置")
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise LLMError(f"无法连接 {provider_label(config['base_url'])}：{reason}")
    except OSError as exc:
        raise LLMError(f"网络错误：{exc}")
    latency_ms = int((time.time() - started) * 1000)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise LLMError("模型返回的不是 JSON，请确认 Base URL 指向 OpenAI 兼容接口")
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        error = data.get("error") if isinstance(data, dict) else None
        raise LLMError(f"返回结构异常：{json.dumps(error or data, ensure_ascii=False)[:200]}")
    return {"content": str(content or ""), "usage": data.get("usage") or {}, "latency_ms": latency_ms,
            "model": data.get("model") or config["model"]}


def _parse_json_block(text: str) -> dict | None:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    for candidate in (text, text[text.find("{"): text.rfind("}") + 1]):
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            return value
    return None


def test_connection(config: dict | None = None) -> dict:
    config = config or resolve_config()
    try:
        result = chat_completion(config, [
            {"role": "system", "content": "只回复两个字符：ok"},
            {"role": "user", "content": "ping"},
        ], max_tokens=16)
        return {"ok": True, "model": result["model"], "latency_ms": result["latency_ms"],
                "reply": result["content"].strip()[:40], "error": ""}
    except LLMError as exc:
        return {"ok": False, "model": config.get("model", ""), "latency_ms": 0,
                "reply": "", "error": str(exc)}


def _evidence_context(answer: dict, limit: int = 4) -> list[dict]:
    items = []
    for ev in (answer.get("evidence") or [])[:limit]:
        items.append({
            "scenario": ev.get("scenario") or (answer.get("scenarios") or [""])[0],
            "source": ev.get("source", ""),
            "year": ev.get("year", ""),
            "confidence": ev.get("confidence"),
            "quote": ev.get("quote", ""),
            "title": ev.get("title", ""),
        })
    return items


def _metrics_context(answer: dict) -> dict:
    out = {}
    for name, metric in (answer.get("metrics") or {}).items():
        out[name] = {
            key: metric.get(key) for key in
            ("rank", "opportunity", "demand", "gap", "feasibility", "value", "n_docs",
             "need_rate", "wtp_rate", "growth_slope", "supply_maturity", "route")
        }
    return out


def generate_advice(answer: dict, question: str, config: dict | None = None, lang: str = "en") -> dict:
    """Ask the model to rewrite the one-sentence advice + a short explanation."""
    config = config or resolve_config()
    system_prompt = SYSTEM_PROMPT_ZH if lang == "zh" else SYSTEM_PROMPT_EN
    if not config.get("api_key"):
        raise LLMError("还没有配置 API Key")
    context = {
        "question": question,
        "intent": answer.get("kind", ""),
        "heading": answer.get("heading", ""),
        "ranking_top": [
            {"rank": row.get("rank"), "scenario": row.get("scenario"), "opportunity": row.get("opportunity"),
             "demand": row.get("demand"), "gap": row.get("gap"), "feasibility": row.get("feasibility"),
             "value": row.get("value"), "route": row.get("route")}
            for row in (answer.get("ranking") or [])[:5]
        ],
        "metrics": _metrics_context(answer),
        "evidence": _evidence_context(answer),
        "rule_advice": answer.get("advice", ""),
        "rule_reply": answer.get("reply", ""),
        "data_note": "机会总分 = 需求 45% + 缺口 25% + 可行性 18% + 价值 12%；置信度未人工校准。",
    }
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]
    result = chat_completion(config, messages)
    content = result["content"].strip()
    parsed = _parse_json_block(content)
    advice = reply = ""
    partial = False
    if parsed:
        advice = str(parsed.get("advice") or "").strip()
        reply = str(parsed.get("reply") or "").strip()
    if not advice:
        partial = True
        advice = content.replace("\n", " ").strip()[:160]
    return {
        "advice": advice[:160],
        "reply": reply[:500] or answer.get("reply", ""),
        "partial": partial,
        "raw": content[:2000],
        "model": result["model"],
        "usage": result["usage"],
        "latency_ms": result["latency_ms"],
    }
