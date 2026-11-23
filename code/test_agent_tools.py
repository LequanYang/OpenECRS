# -*- coding: utf-8 -*-
"""Tests for the grounded tools used by the OpenECRS LLM agent."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_tools import ScenarioData, display_name  # noqa: E402


class ToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ScenarioData()

    def test_catalog_has_twelve_scenarios(self):
        catalog = self.data.catalog("en")
        self.assertEqual(len(catalog), 12)
        self.assertEqual(catalog[0]["name"], "Security, Compliance & Privacy")
        self.assertTrue(all("opportunity" in row for row in catalog))
        zh = self.data.catalog("zh")
        self.assertEqual(zh[0]["name"], "安全合规与隐私")

    def test_resolve_names_and_aliases(self):
        self.assertEqual(self.data.resolve("安全合规与隐私"), "安全合规与隐私")
        self.assertEqual(self.data.resolve("Security, Compliance & Privacy"), "安全合规与隐私")
        self.assertEqual(self.data.resolve("RAG"), "知识管理与文档问答")
        self.assertEqual(self.data.resolve("multi agent"), "多智能体与任务编排")
        self.assertIsNone(self.data.resolve("not-a-scenario"))

    def test_scenario_metrics_and_evidence(self):
        scenario = self.data.scenario("安全合规与隐私", "en")
        self.assertAlmostEqual(scenario["opportunity"], 62.4087, places=3)
        self.assertEqual(scenario["route"], "Joint R&D / track the tech")
        self.assertTrue(scenario["evidence"])
        self.assertTrue(scenario["evidence"][0]["quote"])

    def test_ranking_compare_and_search(self):
        ranking = self.data.ranking("en")
        self.assertEqual(len(ranking), 12)
        self.assertEqual(ranking[0]["rank"], 1)
        comparison = self.data.compare(["Security, Compliance & Privacy", "Multi-agent"], "en")
        self.assertEqual(len(comparison["scenarios"]), 2)
        self.assertTrue(comparison["rows"])
        self.assertIn("Metric", comparison["rows"][0])
        hits = self.data.search("security agent", "en", 3)
        self.assertTrue(hits)
        self.assertTrue(all(hit["confidence"] is not None for hit in hits))

    def test_run_tool_returns_grounded_payloads(self):
        self.assertIn("ranking", self.data.run_tool("ranking", {}, "en"))
        self.assertIn("scenario", self.data.run_tool("scenario", {"name": "安全合规与隐私"}, "zh"))
        self.assertIn("error", self.data.run_tool("scenario", {"name": "unknown"}, "en")["scenario"])
        self.assertIn("catalog", self.data.run_tool("catalog", {}, "en"))

    def test_report_context(self):
        answer = {
            "kind": "scenario", "scenarios": ["Security, Compliance & Privacy"],
            "metrics": {"Security, Compliance & Privacy": self.data.scenario("安全合规与隐私", "en")},
            "advice": "x", "reply": "y", "actions": [], "risks": [], "ranking": [], "comparison": [],
            "evidence": [],
        }
        context = self.data.report_context(answer, "en")
        self.assertEqual(context["title"], "OpenECRS · Scenario Opportunity Brief")
        self.assertTrue(context["metrics_rows"])
        self.assertEqual(display_name("安全合规与隐私", "zh"), "安全合规与隐私")


if __name__ == "__main__":
    unittest.main()
