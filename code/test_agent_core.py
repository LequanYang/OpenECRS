# -*- coding: utf-8 -*-
"""Tests for the LLM-required agent loop (planner -> tools -> responder)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_core  # noqa: E402
import agent_providers  # noqa: E402
from agent_settings import DEFAULT_API, DEFAULT_LOCAL  # noqa: E402
from agent_tools import ScenarioData  # noqa: E402


def settings_with_key() -> dict:
    api = json.loads(json.dumps(DEFAULT_API))
    api["api_key"] = "test-key"
    return {"version": 3, "active": "api-default", "profiles": [
        {"id": "api-default", "name": "test-api", "backend": "api",
         "api": api, "local": json.loads(json.dumps(DEFAULT_LOCAL))},
    ]}


class FakeProvider:
    def __init__(self, planner: dict | None = None, responder: dict | None = None,
                 invalid_plan: bool = False, invalid_answer: bool = False):
        self.calls = []
        self.planner = planner or {"intent": "ranking", "scenarios": [], "focus": "none",
                                   "tools": [{"name": "ranking", "args": {}}], "reason": "test"}
        self.responder = responder or {"heading": "Ranking", "advice": "Prioritise Knowledge Management & Document QA (57.3, feasibility 0.61).",
                                       "reply": "Security has the largest gap but only 0.37 feasibility.",
                                       "actions": ["Run a 2-week PoC."], "risks": ["No human gold labels yet."]}
        self.invalid_plan = invalid_plan
        self.invalid_answer = invalid_answer

    def complete(self, messages, max_tokens=None, temperature=None):
        self.calls.append(messages)
        system = messages[0]["content"]
        planning = "PLANNING phase" in system or "规划阶段" in system
        if planning:
            content = "not json" if self.invalid_plan else json.dumps(self.planner, ensure_ascii=False)
        else:
            content = "not json" if self.invalid_answer else json.dumps(self.responder, ensure_ascii=False)
        return {"content": content, "model": "fake-model", "latency_ms": 7, "usage": {"tokens": 10}}


class AgentRuntimeTests(unittest.TestCase):
    def runtime(self, provider):
        return agent_core.AgentRuntime(settings_with_key(), ScenarioData(), provider=provider)

    def test_ranking_answer_uses_plan_tools_and_llm_text(self):
        provider = FakeProvider()
        answer = self.runtime(provider).chat("Which scenario should we prioritise?", {}, "en")
        self.assertEqual(answer["kind"], "ranking")
        self.assertEqual(answer["advice"], "Prioritise Knowledge Management & Document QA (57.3, feasibility 0.61).")
        self.assertEqual(len(answer["ranking"]), 12)
        self.assertEqual(answer["scenarios"][0], "Security, Compliance & Privacy")
        self.assertEqual(answer["engine"]["backend"], "api")
        self.assertEqual(answer["engine"]["calls"], 2)
        self.assertEqual([step["step"] for step in answer["trace"]], ["plan", "tools", "answer"])
        self.assertEqual(len(provider.calls), 2)

    def test_scenario_answer_in_chinese(self):
        provider = FakeProvider(
            planner={"intent": "scenario", "scenarios": ["安全合规与隐私"], "focus": "feasibility",
                     "tools": [{"name": "scenario", "args": {"name": "安全合规与隐私"}}], "reason": "scenario"},
            responder={"heading": "安全合规与隐私", "advice": "供给缺口最大但可行性只有 0.37，先做 2 周 PoC。",
                       "reply": "该场景 293 条样本中 4 条通过四门判定。", "actions": ["做 PoC"], "risks": ["无金标"]},
        )
        answer = self.runtime(provider).chat("「安全合规与隐私」值不值得做？", {}, "zh")
        self.assertEqual(answer["scenario"] if "scenario" in answer else answer["scenarios"][0], "安全合规与隐私")
        self.assertTrue(answer["advice"].startswith("供给缺口"))
        self.assertTrue(answer["metrics"])
        self.assertTrue(answer["evidence"])

    def test_compare_answer(self):
        provider = FakeProvider(
            planner={"intent": "compare", "scenarios": ["安全合规与隐私", "多智能体与任务编排"],
                     "focus": "none", "tools": [{"name": "compare", "args": {"names": ["安全合规与隐私", "多智能体与任务编排"]}}],
                     "reason": "compare"},
            responder={"heading": "Compare", "advice": "Security scores higher but Multi-agent is easier.",
                       "reply": "Feasibility differs.", "actions": ["a"], "risks": ["r"]},
        )
        answer = self.runtime(provider).chat("Compare Security and Multi-agent", {}, "en")
        self.assertEqual(answer["kind"], "compare")
        self.assertTrue(answer["comparison"])
        self.assertEqual(len(answer["scenarios"]), 2)

    def test_invalid_plan_is_retried_then_errors(self):
        provider = FakeProvider(invalid_plan=True)
        with self.assertRaises(agent_core.AgentError):
            self.runtime(provider).chat("hello", {}, "en")
        self.assertEqual(len(provider.calls), 2)  # two planner attempts

    def test_invalid_answer_is_retried_then_errors(self):
        provider = FakeProvider(invalid_answer=True)
        with self.assertRaises(agent_core.AgentError):
            self.runtime(provider).chat("hello", {}, "en")

    def test_llm_is_required(self):
        settings = settings_with_key()
        settings["profiles"][0]["api"]["api_key"] = ""
        runtime = agent_core.AgentRuntime(settings, ScenarioData())
        with self.assertRaises(agent_providers.LLMRequiredError):
            runtime.chat("hello", {}, "en")

    def test_role_is_forwarded_to_prompts(self):
        provider = FakeProvider()
        answer = self.runtime(provider).chat("Which scenario should we prioritise?", {}, "en", role="investor")
        self.assertEqual(answer["role"], "investor")
        planner_system = provider.calls[0][0]["content"]
        self.assertIn("investor", planner_system.lower())

    def test_smalltalk_does_not_force_a_recommendation(self):
        provider = FakeProvider(
            planner={"intent": "smalltalk", "scenarios": [], "focus": "none", "tools": [], "reason": "greeting"},
            responder={"heading": "Hello", "advice": "Hi, I'm OpenECRS, an evidence-driven opportunity agent.",
                       "reply": "Ask me to rank scenarios or show evidence.", "actions": [], "risks": []},
        )
        answer = self.runtime(provider).chat("Hello", {}, "en")
        self.assertEqual(answer["kind"], "smalltalk")
        self.assertEqual(answer["metrics"], {})
        self.assertEqual(answer["ranking"], [])
        self.assertEqual(answer["evidence"], [])
        self.assertEqual(answer["advice"], "Hi, I'm OpenECRS, an evidence-driven opportunity agent.")
        self.assertTrue(answer["chips"])
        self.assertEqual(answer["trace"], [])
        self.assertEqual(answer["heading"], "Hello")
        self.assertEqual(len(provider.calls), 2)

    def test_video_request_is_routed_to_videos(self):
        provider = FakeProvider(planner={"intent": "smalltalk", "scenarios": [], "focus": "none",
                                         "tools": [], "reason": "greeting"},
                                responder={"heading": "Videos", "advice": "Here are external videos.",
                                           "reply": "Pick a scenario for sharper results.",
                                           "actions": [], "risks": []})
        answer = self.runtime(provider).chat("recommend videos", {}, "en")
        self.assertEqual(answer["kind"], "video")
        self.assertGreater(len(answer["videos"]), 0)
        self.assertTrue(all(item["platform"] in ("youtube", "bilibili") for item in answer["videos"]))
        tool_names = [call["name"] for call in answer["trace"][1]["calls"]]
        self.assertIn("videos", tool_names)

    def test_session_history_is_kept(self):
        provider = FakeProvider()
        runtime = self.runtime(provider)
        session = {}
        runtime.chat("first question", session, "en")
        runtime.chat("second question", session, "en")
        self.assertEqual(len(session["history"]), 4)
        self.assertEqual(session["turns"], 2)


if __name__ == "__main__":
    unittest.main()
