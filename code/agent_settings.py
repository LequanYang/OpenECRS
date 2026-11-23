# -*- coding: utf-8 -*-
"""OpenECRS settings: the agent always requires an LLM (API or local fine-tune)."""
from __future__ import annotations

import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SETTINGS_FILE = BASE / "outputs" / "agent_ui" / "settings.json"

DEFAULT_SETTINGS = {
    "backend": "api",
    "api": {
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "api_key": "",
        "temperature": 0.3,
        "max_tokens": 700,
        "timeout": 60,
    },
    "local": {
        "base_model": "models/Qwen2.5-3B-Instruct",
        "adapter": "outputs/lora/adapter_pilot",
        "max_new_tokens": 512,
        "temperature": 0.2,
    },
}


class SettingsError(RuntimeError):
    pass


def _merge_legacy(stored: dict) -> dict:
    """Migrate v1 settings (enabled/base_url/model/api_key at root)."""
    if "backend" in stored:
        return stored
    migrated = {"backend": "api"}
    if stored.get("base_url") or stored.get("model") or stored.get("api_key"):
        migrated["api"] = {
            "base_url": stored.get("base_url", DEFAULT_SETTINGS["api"]["base_url"]),
            "model": stored.get("model", DEFAULT_SETTINGS["api"]["model"]),
            "api_key": stored.get("api_key", ""),
            "temperature": stored.get("temperature", 0.3),
            "max_tokens": stored.get("max_tokens", 700),
            "timeout": stored.get("timeout", 60),
        }
    return migrated


def load_settings() -> dict:
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    if isinstance(stored, dict):
        stored = _merge_legacy(stored)
        if stored.get("backend") in ("api", "local"):
            settings["backend"] = stored["backend"]
        for section in ("api", "local"):
            if isinstance(stored.get(section), dict):
                settings[section].update({k: v for k, v in stored[section].items() if k in settings[section]})
    return settings


def save_settings(patch: dict | None = None, clear_key: bool = False) -> dict:
    settings = load_settings()
    patch = patch or {}
    if patch.get("backend") in ("api", "local"):
        settings["backend"] = patch["backend"]
    for section in ("api", "local"):
        incoming = patch.get(section)
        if isinstance(incoming, dict):
            for key in settings[section]:
                if key in incoming and incoming[key] not in (None, ""):
                    settings[section][key] = incoming[key]
    if patch.get("api_key"):
        settings["api"]["api_key"] = str(patch["api_key"]).strip()
    if isinstance(patch.get("api"), dict) and patch["api"].get("api_key"):
        settings["api"]["api_key"] = str(patch["api"]["api_key"]).strip()
    if clear_key:
        settings["api"]["api_key"] = ""
    url = str(settings["api"].get("base_url") or "").strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise SettingsError("Base URL 必须以 http:// 或 https:// 开头（Base URL must start with http:// or https://）")
    settings["api"]["base_url"] = url
    settings["api"]["model"] = str(settings["api"].get("model") or "").strip() or DEFAULT_SETTINGS["api"]["model"]
    try:
        settings["api"]["temperature"] = max(0.0, min(2.0, float(settings["api"]["temperature"])))
        settings["api"]["max_tokens"] = max(64, min(4000, int(settings["api"]["max_tokens"])))
        settings["api"]["timeout"] = max(5, min(180, int(settings["api"]["timeout"])))
        settings["local"]["max_new_tokens"] = max(64, min(2048, int(settings["local"]["max_new_tokens"])))
        settings["local"]["temperature"] = max(0.0, min(2.0, float(settings["local"]["temperature"])))
    except (TypeError, ValueError):
        raise SettingsError("temperature / max_tokens / timeout 需要是数字")
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(SETTINGS_FILE, 0o600)
    except OSError:
        pass
    return settings


def _env_api_key(base_url: str) -> tuple[str, str]:
    for name in ("LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value, name
    return "", ""


def resolve_api(settings: dict | None = None) -> dict:
    settings = settings or load_settings()
    api = settings["api"]
    base_url = os.environ.get("LLM_BASE_URL", api["base_url"]).strip().rstrip("/")
    model = os.environ.get("LLM_MODEL", api["model"]).strip()
    key = str(api.get("api_key") or "").strip()
    source = "settings" if key else ""
    if not key:
        key, env_name = _env_api_key(base_url)
        source = f"env:{env_name}" if env_name else ""
    return {
        "base_url": base_url,
        "model": model,
        "api_key": key,
        "key_source": source,
        "temperature": float(api.get("temperature", 0.3)),
        "max_tokens": int(api.get("max_tokens", 700)),
        "timeout": int(api.get("timeout", 60)),
    }


def resolve_local(settings: dict | None = None) -> dict:
    settings = settings or load_settings()
    local = settings["local"]
    return {
        "base_model": str(local.get("base_model") or "").strip(),
        "adapter": str(local.get("adapter") or "").strip(),
        "max_new_tokens": int(local.get("max_new_tokens", 512)),
        "temperature": float(local.get("temperature", 0.2)),
    }


def local_status(settings: dict | None = None) -> dict:
    import importlib.util
    local = resolve_local(settings)
    deps = {name: importlib.util.find_spec(name) is not None
            for name in ("torch", "transformers", "peft")}
    base = (BASE / local["base_model"]).resolve() if local["base_model"] else None
    adapter = (BASE / local["adapter"]).resolve() if local["adapter"] else None
    base_ok = bool(base and base.exists())
    adapter_ok = bool(adapter and adapter.exists())
    ready = all(deps.values()) and base_ok and adapter_ok
    missing = []
    if not all(deps.values()):
        missing.append("pip install -r requirements-lora.txt")
    if not base_ok:
        missing.append(f"base model not found: {local['base_model']}")
    if not adapter_ok:
        missing.append(f"adapter not found: {local['adapter']}")
    return {"deps": deps, "base_exists": base_ok, "adapter_exists": adapter_ok,
            "base_model": local["base_model"], "adapter": local["adapter"],
            "ready": ready, "missing": missing}


def public_settings() -> dict:
    settings = load_settings()
    api = resolve_api(settings)
    status = local_status(settings)
    backend = settings["backend"]
    if backend == "api":
        ready = bool(api["api_key"])
        detail = "API key is configured." if ready else "Add an API key to start chatting."
    else:
        ready = status["ready"]
        detail = "Local model is ready." if ready else "; ".join(status["missing"])
    return {
        "backend": backend,
        "api": {
            "base_url": api["base_url"],
            "model": api["model"],
            "temperature": api["temperature"],
            "max_tokens": api["max_tokens"],
            "timeout": api["timeout"],
            "has_key": bool(api["api_key"]),
            "key_hint": f"…{api['api_key'][-4:]}" if api["api_key"] else "",
            "key_source": api["key_source"],
            "env_key_available": bool(os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
                                      or os.environ.get("LLM_API_KEY")),
            "ready": bool(api["api_key"]),
        },
        "local": {
            **status,
            "max_new_tokens": settings["local"]["max_new_tokens"],
            "temperature": settings["local"]["temperature"],
        },
        "ready": ready,
        "ready_detail": detail,
    }


def backend_label(settings: dict | None = None) -> str:
    settings = settings or load_settings()
    if settings["backend"] == "api":
        return resolve_api(settings)["model"] or "api"
    return resolve_local(settings)["adapter"] or "local"
