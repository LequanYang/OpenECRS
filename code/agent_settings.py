# -*- coding: utf-8 -*-
"""OpenECRS settings: the agent always requires an LLM.

Settings v3 keeps a list of *model profiles* (API or local fine-tune) and one
active profile, so the UI can switch models in one click.
"""
from __future__ import annotations

import copy
import json
import os
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SETTINGS_FILE = BASE / "outputs" / "agent_ui" / "settings.json"

DEFAULT_API = {
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key": "",
    "temperature": 0.3,
    "max_tokens": 700,
    "timeout": 60,
}
DEFAULT_LOCAL = {
    "base_model": "models/Qwen2.5-3B-Instruct",
    "adapter": "outputs/lora/adapter_pilot",
    "max_new_tokens": 512,
    "temperature": 0.2,
}


def _default_profiles() -> list[dict]:
    return [
        {"id": "api-default", "name": "DeepSeek · deepseek-chat", "backend": "api",
         "api": copy.deepcopy(DEFAULT_API), "local": copy.deepcopy(DEFAULT_LOCAL)},
        {"id": "local-pilot", "name": "Local · adapter_pilot", "backend": "local",
         "api": copy.deepcopy(DEFAULT_API), "local": copy.deepcopy(DEFAULT_LOCAL)},
    ]


def _default_settings() -> dict:
    return {"version": 3, "active": "api-default", "profiles": _default_profiles()}


class SettingsError(RuntimeError):
    pass


def _migrate(stored: dict) -> dict:
    """Migrate v1 (enabled/root fields) or v2 (backend/api/local) to v3 profiles."""
    if isinstance(stored.get("profiles"), list) and stored["profiles"]:
        return stored
    settings = _default_settings()
    api_profile = settings["profiles"][0]
    local_profile = settings["profiles"][1]
    if "api" in stored or "local" in stored:
        if isinstance(stored.get("api"), dict):
            api_profile["api"].update({k: v for k, v in stored["api"].items() if k in DEFAULT_API})
        if isinstance(stored.get("local"), dict):
            local_profile["local"].update({k: v for k, v in stored["local"].items() if k in DEFAULT_LOCAL})
        settings["active"] = "local-pilot" if stored.get("backend") == "local" else "api-default"
    elif "enabled" in stored or stored.get("base_url") or stored.get("api_key"):
        api_profile["api"].update({
            "base_url": stored.get("base_url", DEFAULT_API["base_url"]),
            "model": stored.get("model", DEFAULT_API["model"]),
            "api_key": stored.get("api_key", ""),
            "temperature": stored.get("temperature", 0.3),
            "max_tokens": stored.get("max_tokens", 700),
            "timeout": stored.get("timeout", 60),
        })
    return settings


def _normalise_profile(profile: dict) -> dict:
    profile = copy.deepcopy(profile)
    profile["id"] = str(profile.get("id") or uuid.uuid4().hex[:10])
    profile["backend"] = "local" if profile.get("backend") == "local" else "api"
    api = copy.deepcopy(DEFAULT_API)
    api.update({k: v for k, v in (profile.get("api") or {}).items() if k in DEFAULT_API})
    local = copy.deepcopy(DEFAULT_LOCAL)
    local.update({k: v for k, v in (profile.get("local") or {}).items() if k in DEFAULT_LOCAL})
    profile["api"], profile["local"] = api, local
    profile["name"] = str(profile.get("name") or "").strip()
    if not profile["name"]:
        if profile["backend"] == "api":
            profile["name"] = f"API · {api['model'] or 'model'}"
        else:
            profile["name"] = f"Local · {Path(local['adapter']).name or 'adapter'}"
    return profile


def load_settings() -> dict:
    settings = _default_settings()
    try:
        stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stored = {}
    if isinstance(stored, dict):
        settings = _migrate(stored)
        settings["version"] = 3
        settings["profiles"] = [_normalise_profile(p) for p in settings["profiles"]]
        if not any(p["id"] == settings.get("active") for p in settings["profiles"]):
            settings["active"] = settings["profiles"][0]["id"]
    return settings


def _active(settings: dict | None = None) -> dict:
    """Return the active profile; tolerate legacy v2 dicts used by tests."""
    settings = settings or {}
    if "profiles" in settings:
        for profile in settings["profiles"]:
            if profile.get("id") == settings.get("active"):
                return profile
        return settings["profiles"][0]
    profile = {
        "id": "legacy",
        "name": "legacy",
        "backend": settings.get("backend", "api"),
        "api": copy.deepcopy(DEFAULT_API),
        "local": copy.deepcopy(DEFAULT_LOCAL),
    }
    profile["api"].update(settings.get("api") or {})
    profile["local"].update(settings.get("local") or {})
    return profile


def active_profile(settings: dict | None = None) -> dict:
    return _active(settings or load_settings())


def _validate(profile: dict) -> None:
    api = profile["api"]
    url = str(api.get("base_url") or "").strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        raise SettingsError("Base URL 必须以 http:// 或 https:// 开头（Base URL must start with http:// or https://）")
    api["base_url"] = url
    api["model"] = str(api.get("model") or "").strip() or DEFAULT_API["model"]
    try:
        api["temperature"] = max(0.0, min(2.0, float(api["temperature"])))
        api["max_tokens"] = max(64, min(4000, int(api["max_tokens"])))
        api["timeout"] = max(5, min(180, int(api["timeout"])))
        profile["local"]["max_new_tokens"] = max(64, min(2048, int(profile["local"]["max_new_tokens"])))
        profile["local"]["temperature"] = max(0.0, min(2.0, float(profile["local"]["temperature"])))
    except (TypeError, ValueError):
        raise SettingsError("temperature / max_tokens / timeout 需要是数字")


def _persist(settings: dict) -> dict:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(SETTINGS_FILE, 0o600)
    except OSError:
        pass
    return settings


def save_settings(patch: dict | None = None) -> dict:
    """Create/update a profile, set it active, or delete a profile."""
    patch = patch or {}
    settings = load_settings()
    profiles = settings["profiles"]

    if patch.get("delete_profile"):
        target = str(patch["delete_profile"])
        if len(profiles) <= 1:
            raise SettingsError("至少保留一个模型配置（At least one model profile must remain）")
        profiles = [p for p in profiles if p["id"] != target]
        settings["profiles"] = profiles
        if settings["active"] == target:
            settings["active"] = profiles[0]["id"]
        return _persist(settings)

    if patch.get("profile") is not None and isinstance(patch["profile"], dict):
        incoming = dict(patch["profile"])
    else:
        active = _active(settings)
        incoming = {"id": patch.get("profile_id") or active["id"],
                    "name": patch.get("name") or active.get("name"),
                    "backend": patch.get("backend") or active["backend"],
                    "api": {**(active["api"]), **(patch.get("api") or {})},
                    "local": {**(active["local"]), **(patch.get("local") or {})}}
    if patch.get("api_key"):
        incoming.setdefault("api", {})["api_key"] = str(patch["api_key"]).strip()
    if patch.get("clear_key"):
        incoming.setdefault("api", {})["api_key"] = ""

    profile = _normalise_profile(incoming)
    existing = next((p for p in profiles if p["id"] == profile["id"]), None)
    if existing and not (incoming.get("api") or {}).get("api_key") and existing["api"].get("api_key") and not patch.get("clear_key"):
        profile["api"]["api_key"] = existing["api"]["api_key"]
    _validate(profile)
    if existing:
        profiles[profiles.index(existing)] = profile
    else:
        profiles.append(profile)
    settings["active"] = profile["id"]
    return _persist(settings)


def set_active(profile_id: str) -> dict:
    settings = load_settings()
    if not any(p["id"] == profile_id for p in settings["profiles"]):
        raise SettingsError("unknown profile")
    settings["active"] = profile_id
    return _persist(settings)


def _env_api_key(base_url: str) -> tuple[str, str]:
    for name in ("LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value, name
    return "", ""


def resolve_api(settings: dict | None = None) -> dict:
    settings = settings or load_settings()
    api = _active(settings)["api"]
    base_url = os.environ.get("LLM_BASE_URL", api["base_url"]).strip().rstrip("/")
    model = os.environ.get("LLM_MODEL", api["model"]).strip()
    key = str(api.get("api_key") or "").strip()
    source = "settings" if key else ""
    if not key:
        key, env_name = _env_api_key(base_url)
        source = f"env:{env_name}" if env_name else ""
    return {"base_url": base_url, "model": model, "api_key": key, "key_source": source,
            "temperature": float(api.get("temperature", 0.3)),
            "max_tokens": int(api.get("max_tokens", 700)),
            "timeout": int(api.get("timeout", 60))}


def resolve_local(settings: dict | None = None) -> dict:
    settings = settings or load_settings()
    local = _active(settings)["local"]
    return {"base_model": str(local.get("base_model") or "").strip(),
            "adapter": str(local.get("adapter") or "").strip(),
            "max_new_tokens": int(local.get("max_new_tokens", 512)),
            "temperature": float(local.get("temperature", 0.2))}


def local_status(settings: dict | None = None) -> dict:
    import importlib.util
    local = resolve_local(settings)
    deps = {name: importlib.util.find_spec(name) is not None for name in ("torch", "transformers", "peft")}
    base = (BASE / local["base_model"]).resolve() if local["base_model"] else None
    adapter = (BASE / local["adapter"]).resolve() if local["adapter"] else None
    base_ok = bool(base and base.exists())
    adapter_ok = bool(adapter and adapter.exists())
    missing = []
    if not all(deps.values()):
        missing.append("pip install -r requirements-lora.txt")
    if not base_ok:
        missing.append(f"base model not found: {local['base_model']}")
    if not adapter_ok:
        missing.append(f"adapter not found: {local['adapter']}")
    return {"deps": deps, "base_exists": base_ok, "adapter_exists": adapter_ok,
            "base_model": local["base_model"], "adapter": local["adapter"],
            "ready": all(deps.values()) and base_ok and adapter_ok, "missing": missing}


def _profile_public(profile: dict, active_id: str) -> dict:
    backend = profile["backend"]
    api = profile["api"]
    status = local_status({"profiles": [profile], "active": profile["id"]})
    key = str(api.get("api_key") or "").strip()
    env_key, _ = _env_api_key(api.get("base_url", ""))
    ready = bool(key or env_key) if backend == "api" else status["ready"]
    detail = ("API key is configured." if ready else "Add an API key to start chatting.") if backend == "api" else (
        "Local model is ready." if ready else "; ".join(status["missing"]))
    return {
        "id": profile["id"], "name": profile["name"], "backend": backend,
        "active": profile["id"] == active_id,
        "model": api["model"] if backend == "api" else profile["local"]["adapter"],
        "has_key": bool(key or env_key),
        "key_hint": f"…{key[-4:]}" if key else "",
        "ready": ready, "detail": detail,
    }


def public_settings() -> dict:
    settings = load_settings()
    active = _active(settings)
    backend = active["backend"]
    api = resolve_api(settings)
    status = local_status(settings)
    if backend == "api":
        ready = bool(api["api_key"])
        detail = "API key is configured." if ready else "Add an API key to start chatting."
    else:
        ready = status["ready"]
        detail = "Local model is ready." if ready else "; ".join(status["missing"])
    return {
        "active": settings["active"],
        "profiles": [_profile_public(p, settings["active"]) for p in settings["profiles"]],
        "backend": backend,
        "name": active.get("name", ""),
        "api": {
            "base_url": api["base_url"], "model": api["model"],
            "temperature": api["temperature"], "max_tokens": api["max_tokens"],
            "timeout": api["timeout"], "has_key": bool(api["api_key"]),
            "key_hint": f"…{api['api_key'][-4:]}" if api["api_key"] else "",
            "key_source": api["key_source"],
            "env_key_available": bool(os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
                                      or os.environ.get("LLM_API_KEY")),
            "ready": bool(api["api_key"]),
        },
        "local": {**status, "max_new_tokens": active["local"]["max_new_tokens"],
                  "temperature": active["local"]["temperature"]},
        "ready": ready,
        "ready_detail": detail,
    }


def backend_label(settings: dict | None = None) -> str:
    settings = settings or load_settings()
    active = _active(settings)
    return active.get("name") or active.get("id") or "model"
