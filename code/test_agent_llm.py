# -*- coding: utf-8 -*-
"""Tests for the optional LLM API bridge (settings, mock endpoint, fallbacks)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

import agent_llm  # noqa: E402
from agent_engine import OpenECRSAgent  # noqa: E402

ADVICE = "建议先做 2 周合规证据链 PoC：供给缺口 1.00、可行性 0.37，用付费意愿决定是否加码。"
REPLY = "该场景 293 条样本中 4 条通过四门机会判定，最高置信度 0.84。"


class MockLLMHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            request = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            request = {}
        if self.path != "/v1/chat/completions":
            return self._send(404, {"error": {"message": "no route"}})
        if self.headers.get("Authorization") != "Bearer test-key":
            return self._send(401, {"error": {"message": "invalid key"}})
        if request.get("model") == "broken":
            return self._send(500, {"error": {"message": "server exploded"}})
        if request.get("model") == "plain":
            content = "直接给一句建议，没有 JSON。"
        else:
            content = json.dumps({"advice": ADVICE, "reply": REPLY}, ensure_ascii=False)
        return self._send(200, {
            "model": request.get("model", "mock-model"),
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        })


def fake_answer() -> dict:
    return {
        "kind": "scenario",
        "heading": "安全合规与隐私 · 证据与行动建议",
        "advice": "规则引擎的一句话建议。",
        "reply": "规则引擎的补充说明。",
        "scenarios": ["安全合规与隐私"],
        "metrics": {"安全合规与隐私": {
            "rank": 1, "opportunity": 62.4087, "demand": 0.6549, "gap": 1.0,
            "feasibility": 0.3686, "value": 0.1086, "n_docs": 293,
            "need_rate": 0.9711, "wtp_rate": 0.1429, "growth_slope": 0.00436,
            "supply_maturity": 0.273, "route": "联合研发/跟踪技术",
        }},
        "ranking": [{"rank": 1, "scenario": "安全合规与隐私", "opportunity": 62.4087,
                     "demand": 0.6549, "gap": 1.0, "feasibility": 0.3686,
                     "value": 0.1086, "route": "联合研发/跟踪技术"}],
        "evidence": [{"source": "HackerNews", "year": 2026, "confidence": 0.84,
                      "quote": "Looking for security engineering or AI security roles.",
                      "title": "Ask HN: Who wants to be hired?", "scenario": "安全合规与隐私"}],
    }


class LLMUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings_file = Path(self.tmp.name) / "settings.json"
        self.patch = mock.patch.object(agent_llm, "SETTINGS_FILE", self.settings_file)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_settings_are_masked(self):
        agent_llm.save_settings({"enabled": True, "base_url": "https://api.deepseek.com/v1",
                                 "model": "deepseek-chat", "api_key": "sk-secret-1234"})
        public = agent_llm.public_settings()
        self.assertTrue(public["has_key"])
        self.assertTrue(public["ready"])
        self.assertEqual(public["key_hint"], "…1234")
        self.assertNotIn("sk-secret-1234", json.dumps(public))
        stored = json.loads(self.settings_file.read_text(encoding="utf-8"))
        self.assertEqual(stored["api_key"], "sk-secret-1234")
        self.assertEqual(self.settings_file.stat().st_mode & 0o777, 0o600)

    def test_empty_key_keeps_previous_value(self):
        agent_llm.save_settings({"api_key": "sk-first"})
        agent_llm.save_settings({"model": "deepseek-reasoner"})
        self.assertEqual(agent_llm.load_settings()["api_key"], "sk-first")

    def test_env_key_fallback(self):
        agent_llm.save_settings({"base_url": "https://api.deepseek.com/v1"})
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "env-key-9999"}, clear=False):
            config = agent_llm.resolve_config()
        self.assertEqual(config["api_key"], "env-key-9999")
        self.assertEqual(config["key_source"], "env:DEEPSEEK_API_KEY")

    def test_bad_base_url_is_rejected(self):
        with self.assertRaises(agent_llm.LLMError):
            agent_llm.save_settings({"base_url": "ftp://example.com"})

    def test_missing_key_raises(self):
        with self.assertRaises(agent_llm.LLMError):
            agent_llm.chat_completion({"base_url": "https://example.com/v1", "api_key": "", "model": "m"},
                                      [{"role": "user", "content": "hi"}])


class MockEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), MockLLMHandler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def config(self, model="mock-model", key="test-key"):
        return {"base_url": self.base, "model": model, "api_key": key,
                "temperature": 0.3, "max_tokens": 200, "timeout": 15}

    def test_chat_completion(self):
        result = agent_llm.chat_completion(self.config(), [{"role": "user", "content": "hi"}])
        self.assertIn("advice", result["content"])
        self.assertEqual(result["model"], "mock-model")

    def test_test_connection(self):
        result = agent_llm.test_connection(self.config())
        self.assertTrue(result["ok"])
        self.assertEqual(result["error"], "")

    def test_wrong_key_reports_401(self):
        with self.assertRaises(agent_llm.LLMError) as ctx:
            agent_llm.chat_completion(self.config(key="wrong"), [{"role": "user", "content": "hi"}])
        self.assertIn("API Key", str(ctx.exception))

    def test_server_error_is_wrapped(self):
        with self.assertRaises(agent_llm.LLMError):
            agent_llm.chat_completion(self.config(model="broken"), [{"role": "user", "content": "hi"}])

    def test_generate_advice_parses_json(self):
        result = agent_llm.generate_advice(fake_answer(), "安全合规值不值得做？", self.config())
        self.assertEqual(result["advice"], ADVICE)
        self.assertEqual(result["reply"], REPLY)
        self.assertFalse(result["partial"])

    def test_generate_advice_falls_back_to_text(self):
        result = agent_llm.generate_advice(fake_answer(), "安全合规值不值得做？", self.config(model="plain"))
        self.assertTrue(result["partial"])
        self.assertIn("直接给一句建议", result["advice"])


class LLMEndpointTests(unittest.TestCase):
    """End-to-end: /api/settings -> /api/test -> /api/chat with the mock model."""

    @classmethod
    def setUpClass(cls):
        import agent_app
        cls.agent_app = agent_app
        cls.tmp = tempfile.TemporaryDirectory()
        cls.settings_file = Path(cls.tmp.name) / "settings.json"
        cls.patch = mock.patch.object(agent_llm, "SETTINGS_FILE", cls.settings_file)
        cls.patch.start()
        agent_app.AGENT = OpenECRSAgent()
        cls.mock = ThreadingHTTPServer(("127.0.0.1", 0), MockLLMHandler)
        threading.Thread(target=cls.mock.serve_forever, daemon=True).start()
        cls.mock_base = f"http://127.0.0.1:{cls.mock.server_address[1]}/v1"
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), agent_app.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.mock.shutdown()
        cls.mock.server_close()
        cls.patch.stop()
        cls.tmp.cleanup()

    def _post(self, path, payload):
        request = urllib.request.Request(self.base + path, method="POST",
                                         data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read())
            finally:
                exc.close()

    def test_settings_and_model_chat(self):
        status, public = self._post("/api/settings", {
            "enabled": True, "base_url": self.mock_base, "model": "mock-model", "api_key": "test-key"})
        self.assertEqual(status, 200)
        self.assertTrue(public["ready"])

        status, test = self._post("/api/test", {})
        self.assertEqual(status, 200)
        self.assertTrue(test["ok"])

        status, answer = self._post("/api/chat", {"session": "llm-e2e", "message": "「安全合规与隐私」值不值得做？"})
        self.assertEqual(status, 200)
        self.assertEqual(answer["engine"]["kind"], "llm")
        self.assertEqual(answer["engine"]["model"], "mock-model")
        self.assertEqual(answer["advice"], ADVICE)
        self.assertNotIn("llm_error", answer)

        # disable again and make sure we fall back to rule mode
        self._post("/api/settings", {"enabled": False})
        status, answer = self._post("/api/chat", {"session": "llm-e2e", "message": "哪个场景最值得优先做？"})
        self.assertEqual(answer["engine"]["kind"], "rule")

    def test_chat_uses_rule_engine_when_key_invalid(self):
        self._post("/api/settings", {
            "enabled": True, "base_url": self.mock_base, "model": "mock-model", "api_key": "wrong-key"})
        status, answer = self._post("/api/chat", {"session": "llm-bad", "message": "哪个场景最值得优先做？"})
        self.assertEqual(status, 200)
        self.assertEqual(answer["engine"]["kind"], "rule")
        self.assertIn("API Key", answer.get("llm_error", ""))
        self._post("/api/settings", {"enabled": False, "clear_key": True})


if __name__ == "__main__":
    unittest.main()
