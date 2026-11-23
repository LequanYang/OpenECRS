# -*- coding: utf-8 -*-
"""Tests for the conversational evidence-agent UI (engine, report, HTTP layer)."""
from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from agent_engine import OpenECRSAgent, load_data  # noqa: E402
from agent_pdf import build_report_html, find_browser, render_pdf  # noqa: E402


class AgentDataTests(unittest.TestCase):
    def test_dataset_is_complete(self):
        data = load_data()
        self.assertEqual(len(data["scenarios"]), 12)
        self.assertEqual(data["meta"]["demand_units"], 15525)
        self.assertEqual(data["scenarios"][0]["name"], "安全合规与隐私")
        self.assertAlmostEqual(data["scenarios"][0]["opportunity"], 62.4087, places=3)
        evidence = sum(len(s["evidence"]) for s in data["scenarios"])
        self.assertGreaterEqual(evidence, 60)
        for scenario in data["scenarios"]:
            self.assertTrue(scenario["evidence"], scenario["name"])
            self.assertIn("quote", scenario["evidence"][0])


class AgentReasoningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = OpenECRSAgent()

    def test_ranking_answer_has_one_sentence_and_full_table(self):
        answer = self.agent.answer("哪个场景最值得优先做？", {})
        self.assertEqual(answer["kind"], "ranking")
        self.assertTrue(answer["advice"])
        self.assertIn("前三名", answer["advice"])
        self.assertEqual(len(answer["ranking"]), 12)
        self.assertEqual(len(answer["actions"]), 3)

    def test_scenario_answer_contains_metrics_and_evidence(self):
        answer = self.agent.answer("「安全合规与隐私」值不值得做？给我建议和证据。", {})
        self.assertEqual(answer["kind"], "scenario")
        self.assertEqual(answer["scenario"], "安全合规与隐私")
        self.assertTrue(answer["advice"].startswith("供给缺口最大"))
        self.assertGreaterEqual(len(answer["evidence"]), 3)
        self.assertIn("安全合规与隐私", answer["metrics"])

    def test_compare_answer(self):
        answer = self.agent.answer("对比 安全合规 和 多智能体", {})
        self.assertEqual(answer["kind"], "compare")
        self.assertEqual(len(answer["scenarios"]), 2)
        self.assertTrue(answer["comparison"])
        self.assertIn("机会分", answer["advice"])

    def test_follow_up_uses_session_context(self):
        session = {}
        self.agent.answer("哪个场景最值得优先做？", session)
        answer = self.agent.answer("第二个呢", session)
        self.assertEqual(answer["kind"], "scenario")
        self.assertEqual(answer["scenario"], "多智能体与任务编排")
        follow = self.agent.answer("它的证据呢", session)
        self.assertEqual(follow["scenario"], "多智能体与任务编排")
        self.assertTrue(follow["evidence"])

    def test_risk_and_metric_focus(self):
        answer = self.agent.answer("客户服务为什么价值高？", {})
        self.assertEqual(answer["scenario"], "客户服务与智能客服")
        self.assertIn("商业价值", answer["reply"])

    def test_unknown_question_gets_guided_overview(self):
        answer = self.agent.answer("今天天气怎么样", {})
        self.assertEqual(answer["kind"], "overview")
        self.assertTrue(answer["chips"])


class AgentReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = OpenECRSAgent()

    def _context(self):
        answer = self.agent.answer("「知识管理与文档问答」值不值得做？", {})
        return self.agent.report_context(answer)

    def test_report_html_has_required_sections(self):
        html = build_report_html(self._context())
        for token in ("一句话建议", "详细数据", "证据摘录", "行动建议", "口径与局限", "知识管理与文档问答"):
            self.assertIn(token, html)
        self.assertIn("@page", html)

    def test_pdf_export_when_browser_available(self):
        if not find_browser():
            self.skipTest("no local Chromium browser")
        payload, error = render_pdf(build_report_html(self._context()))
        self.assertEqual(error, "")
        self.assertIsNotNone(payload)
        self.assertTrue(payload.startswith(b"%PDF"))


class AgentHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import agent_app
        cls.agent_app = agent_app
        agent_app.AGENT = OpenECRSAgent()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), agent_app.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _post(self, path, payload):
        request = urllib.request.Request(self.base + path, method="POST",
                                         data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read(), response.headers.get("Content-Type")
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read()
            finally:
                exc.close()
            return exc.code, body, exc.headers.get("Content-Type")

    def test_health_and_index(self):
        with urllib.request.urlopen(self.base + "/api/health", timeout=10) as response:
            payload = json.loads(response.read())
        self.assertTrue(payload["ok"])
        with urllib.request.urlopen(self.base + "/", timeout=10) as response:
            html = response.read().decode("utf-8")
        self.assertIn("OpenECRS", html)

    def test_chat_endpoint(self):
        status, body, _ = self._post("/api/chat", {"session": "pytest", "message": "对比 安全合规 和 多智能体"})
        self.assertEqual(status, 200)
        answer = json.loads(body)
        self.assertEqual(answer["kind"], "compare")
        self.assertTrue(answer["advice"])

    def test_http_language_switch(self):
        request = urllib.request.Request(
            self.base + "/api/chat", method="POST",
            data=json.dumps({"session": "en-test", "message": "Which scenario should we prioritise?",
                             "lang": "en"}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read())
        self.assertEqual(data["kind"], "ranking")
        self.assertIn("top three", data["advice"].lower())

        request = urllib.request.Request(
            self.base + "/api/chat", method="POST",
            data=json.dumps({"session": "zh-test", "message": "哪个场景最值得优先做？",
                             "lang": "zh"}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read())
        self.assertIn("前三名", data["advice"])

    def test_pdf_requires_conversation_first(self):
        status, body, _ = self._post("/api/pdf", {"session": "empty-session"})
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(body))


class EnglishModeTests(unittest.TestCase):
    """The GitHub release defaults to English; Chinese must remain available."""

    @classmethod
    def setUpClass(cls):
        cls.agent = OpenECRSAgent()

    def test_dataset_has_english_names(self):
        data = load_data()
        first = data["scenarios"][0]
        self.assertIn("name_en", first)
        self.assertIn("route_en", first)
        self.assertTrue(first["name_en"].isascii())

    def test_english_overview_and_ranking(self):
        overview = self.agent.answer("hello", {}, lang="en")
        self.assertEqual(overview["kind"], "overview")
        self.assertIn("Start with three directions", overview["advice"])
        self.assertTrue(overview["scenarios"][0].isascii())
        ranking = self.agent.answer("Which scenario should we prioritise?", {}, lang="en")
        self.assertEqual(ranking["kind"], "ranking")
        self.assertIn("Opportunity Score" if "Opportunity Score" in ranking["advice"] else "top three",
                      ranking["advice"])
        self.assertEqual(len(ranking["ranking"]), 12)
        self.assertTrue(ranking["ranking"][0]["scenario"].isascii())

    def test_english_scenario_compare_and_followup(self):
        session = {}
        answer = self.agent.answer("Is Security, Compliance & Privacy worth building?", session, lang="en")
        self.assertEqual(answer["kind"], "scenario")
        self.assertEqual(answer["scenario"], "Security, Compliance & Privacy")
        self.assertIn("supply gap", answer["advice"])
        self.assertTrue(all(e["source"] for e in answer["evidence"]))
        compare = self.agent.answer("Compare Security, Compliance & Privacy vs Multi-agent", session, lang="en")
        self.assertEqual(compare["kind"], "compare")
        self.assertEqual(len(compare["scenarios"]), 2)
        follow = self.agent.answer("second", session, lang="en")
        self.assertEqual(follow["scenario"], "Multi-agent & Task Orchestration")

    def test_english_report_html(self):
        answer = self.agent.answer("Compare Security, Compliance & Privacy vs Multi-agent", {}, lang="en")
        html = build_report_html(self.agent.report_context(answer))
        for token in ("One-sentence advice", "Detailed data", "Evidence excerpts", "Action plan",
                      "Scope & limitations", "OpenECRS"):
            self.assertIn(token, html)

    def test_english_pdf_export(self):
        if not find_browser():
            self.skipTest("no local Chromium browser")
        answer = self.agent.answer("Which scenario should we prioritise?", {}, lang="en")
        payload, error = render_pdf(build_report_html(self.agent.report_context(answer)))
        self.assertEqual(error, "")
        self.assertTrue(payload.startswith(b"%PDF"))
        from pypdf import PdfReader
        import io
        text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(payload)).pages)
        self.assertIn("One-sentence advice", text)
        self.assertNotIn("一句话建议", text)



if __name__ == "__main__":
    unittest.main()
