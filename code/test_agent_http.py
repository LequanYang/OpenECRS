# -*- coding: utf-8 -*-
"""HTTP tests for the LLM-required OpenECRS app using a mock model endpoint."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_settings  # noqa: E402

ADVICE_EN = "Prioritise Knowledge Management & Document QA (57.3, feasibility 0.61)."
ADVICE_ZH = "优先做知识管理与文档问答：机会 57.3、可行性 0.61。"


class MockLLM(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, payload):
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
        if self.path.rstrip("/") != "/v1/chat/completions":
            return self._send(404, {"error": {"message": "no route"}})
        if self.headers.get("Authorization") != "Bearer test-key":
            return self._send(401, {"error": {"message": "invalid key"}})
        messages = request.get("messages") or []
        system = messages[0].get("content", "") if messages else ""
        user = messages[-1].get("content", "") if messages else ""
        planning = "PLANNING phase" in system or "规划阶段" in system
        if planning:
            content = json.dumps({"intent": "ranking", "scenarios": [], "focus": "none",
                                  "tools": [{"name": "ranking", "args": {}}],
                                  "reason": "mock planner"}, ensure_ascii=False)
        else:
            zh = ("作答阶段" in system) or ("用简体中文" in system)
            content = json.dumps({
                "heading": "机会排名" if zh else "Opportunity ranking",
                "advice": ADVICE_ZH if zh else ADVICE_EN,
                "reply": "Mock reply for testing." if not zh else "用于测试的模拟说明。",
                "actions": ["Run a 2-week PoC."] if not zh else ["做 2 周 PoC。"],
                "risks": ["No gold labels."] if not zh else ["没有人工金标。"],
            }, ensure_ascii=False)
        return self._send(200, {
            "model": "mock-model",
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 30},
        })


class HTTPAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.settings_file = Path(cls.tmp.name) / "settings.json"
        cls.patch = mock.patch.object(agent_settings, "SETTINGS_FILE", cls.settings_file)
        cls.patch.start()
        cls.mock = ThreadingHTTPServer(("127.0.0.1", 0), MockLLM)
        threading.Thread(target=cls.mock.serve_forever, daemon=True).start()
        cls.mock_base = f"http://127.0.0.1:{cls.mock.server_address[1]}/v1"
        import agent_app
        import agent_pdf
        cls.pdf_tmp = tempfile.TemporaryDirectory()
        cls.pdf_patch = mock.patch.object(agent_pdf, "PDF_DIR", Path(cls.pdf_tmp.name))
        cls.pdf_patch.start()
        cls.app = agent_app
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
        cls.pdf_patch.stop()
        cls.pdf_tmp.cleanup()
        cls.tmp.cleanup()

    def _post(self, path, payload, timeout=60):
        request = urllib.request.Request(self.base + path, method="POST",
                                         data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, exc.read(), exc.headers
            finally:
                exc.close()

    def _configure(self, key="test-key"):
        status, body, _ = self._post("/api/settings", {
            "backend": "api",
            "api": {"base_url": self.mock_base, "model": "mock-model", "api_key": key},
        })
        return status, json.loads(body)

    def test_01_health_and_settings(self):
        with urllib.request.urlopen(self.base + "/api/health", timeout=10) as response:
            health = json.loads(response.read())
        self.assertTrue(health["ok"])
        status, public = self._configure()
        self.assertEqual(status, 200)
        self.assertTrue(public["ready"])
        self.assertTrue(public["api"]["has_key"])
        self.assertNotIn("test-key", json.dumps(public))
        status, body, _ = self._post("/api/test", {})
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertEqual(data["backend"], "api")

    def test_02_chat_english_and_chinese(self):
        self._configure()
        status, body, _ = self._post("/api/chat", {"session": "en", "message": "Which scenario should we prioritise?", "lang": "en"})
        self.assertEqual(status, 200)
        answer = json.loads(body)
        self.assertEqual(answer["kind"], "ranking")
        self.assertEqual(answer["engine"]["backend"], "api")
        self.assertEqual(answer["advice"], ADVICE_EN)
        self.assertEqual(len(answer["ranking"]), 12)
        self.assertEqual([step["step"] for step in answer["trace"]], ["plan", "tools", "answer"])
        self.assertTrue(answer["chips"])

        status, body, _ = self._post("/api/chat", {"session": "zh", "message": "哪个场景最值得优先做？", "lang": "zh"})
        self.assertEqual(status, 200)
        answer = json.loads(body)
        self.assertEqual(answer["advice"], ADVICE_ZH)
        self.assertTrue(answer["scenarios"][0].isascii() is False)

    def test_03_pdf_export(self):
        if not __import__("agent_pdf").find_browser():
            self.skipTest("no local browser for PDF")
        self._configure()
        self._post("/api/chat", {"session": "pdf", "message": "Which scenario should we prioritise?", "lang": "en"})
        status, body, headers = self._post("/api/pdf", {"session": "pdf", "lang": "en"})
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("Content-Type"), "application/pdf")
        self.assertTrue(body.startswith(b"%PDF"))

    def test_04_llm_is_required(self):
        self._configure()
        self._post("/api/settings", {"backend": "api", "clear_key": True})
        status, body, _ = self._post("/api/chat", {"session": "none", "message": "hello", "lang": "en"})
        self.assertEqual(status, 428)
        data = json.loads(body)
        self.assertEqual(data["code"], "llm_required")

    def test_05_invalid_key_surfaces_error(self):
        self._configure(key="wrong-key")
        status, body, _ = self._post("/api/chat", {"session": "bad", "message": "hello", "lang": "en"})
        self.assertEqual(status, 502)
        data = json.loads(body)
        self.assertEqual(data["code"], "llm_error")
        self.assertIn("API Key", data["error"])


if __name__ == "__main__":
    unittest.main()
