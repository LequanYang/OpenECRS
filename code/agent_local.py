# -*- coding: utf-8 -*-
"""Local fine-tuned LLM provider (Qwen2.5 + LoRA adapter). Optional."""
from __future__ import annotations

import importlib.util
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]


class LocalProviderError(RuntimeError):
    pass


_CACHE: dict = {}


def deps_available() -> dict:
    return {name: importlib.util.find_spec(name) is not None for name in ("torch", "transformers", "peft")}


def paths_status(base_model: str, adapter: str) -> dict:
    base = (BASE / base_model).resolve() if base_model else None
    adapt = (BASE / adapter).resolve() if adapter else None
    return {
        "base_model": base_model,
        "adapter": adapter,
        "base_exists": bool(base and base.exists()),
        "adapter_exists": bool(adapt and adapt.exists()),
    }


class LocalProvider:
    """Loads a HF base model plus a PEFT LoRA adapter and generates text."""

    model_name = "local-lora"

    def __init__(self, config: dict):
        self.config = config

    def _load(self):
        if "model" in _CACHE:
            return _CACHE["model"], _CACHE["tokenizer"]
        deps = deps_available()
        missing = [name for name, ok in deps.items() if not ok]
        if missing:
            raise LocalProviderError(
                "Local model dependencies are missing: " + ", ".join(missing)
                + ". Install them with `pip install -r requirements-lora.txt`."
            )
        status = paths_status(self.config["base_model"], self.config["adapter"])
        if not status["base_exists"]:
            raise LocalProviderError(
                f"Base model not found: {self.config['base_model']}. "
                "Download Qwen2.5-3B-Instruct into models/Qwen2.5-3B-Instruct."
            )
        if not status["adapter_exists"]:
            raise LocalProviderError(f"LoRA adapter not found: {self.config['adapter']}.")
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        tokenizer = AutoTokenizer.from_pretrained(self.config["base_model"], local_files_only=True)
        model = AutoModelForCausalLM.from_pretrained(
            self.config["base_model"], local_files_only=True,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        )
        model = PeftModel.from_pretrained(model, self.config["adapter"], local_files_only=True)
        model.to(device).eval()
        _CACHE.update({"model": model, "tokenizer": tokenizer, "device": device})
        return model, tokenizer

    def complete(self, messages: list[dict], max_tokens: int | None = None,
                 temperature: float | None = None) -> dict:
        started = time.time()
        model, tokenizer = self._load()
        import torch

        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
        device = _CACHE.get("device", "cpu")
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=int(max_tokens or self.config["max_new_tokens"]),
                do_sample=float(temperature if temperature is not None else self.config["temperature"]) > 0,
                temperature=max(float(temperature if temperature is not None else self.config["temperature"]), 0.01),
                pad_token_id=tokenizer.eos_token_id,
            )
        generated = output[0][inputs["input_ids"].shape[1]:]
        content = tokenizer.decode(generated, skip_special_tokens=True)
        return {
            "content": content,
            "model": f"local:{Path(self.config['adapter']).name}",
            "latency_ms": int((time.time() - started) * 1000),
            "usage": {"completion_tokens": int(generated.shape[0])},
        }
