# -*- coding: utf-8 -*-
"""Tests for the deterministic OpenECRS product features.

Run with::

    cd code && python3 -m unittest test_agent_features -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_features import (  # noqa: E402
    POC_WEEKS,
    ROLES,
    build_poc_messages,
    build_portfolio_messages,
    build_wizard_messages,
    normalize_weeks,
    parse_narrative,
    poc_plan,
    portfolio,
    wizard,
)
from agent_tools import ScenarioData  # noqa: E402

BASE_PREFS = {
    "role": "pm",
    "goal": "",
    "team_size": 4,
    "budget_usd": 120_000,
    "horizon_weeks": 8,
    "risk": "medium",
    "lang": "en",
}

LOW_PREFS = {
    "role": "founder",
    "goal": "",
    "team_size": 2,
    "budget_usd": 30_000,
    "horizon_weeks": 4,
    "risk": "low",
    "lang": "en",
}

HIGH_PREFS = {
    "role": "investor",
    "goal": "",
    "team_size": 20,
    "budget_usd": 900_000,
    "horizon_weeks": 20,
    "risk": "high",
    "lang": "en",
}


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


class WizardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ScenarioData()

    def test_shortlist_shape_and_ranges(self):
        result = wizard(BASE_PREFS, self.data)
        self.assertIn("constraints", result)
        self.assertIn("shortlist", result)
        self.assertEqual(len(result["shortlist"]), 3)
        keys = ("id", "name", "name_en", "score", "opportunity", "feasibility",
                "gap", "route", "fit_reasons", "watchouts")
        for row in result["shortlist"]:
            for key in keys:
                self.assertIn(key, row)
            self.assertEqual(row["score"], round(row["score"], 2))
            self.assertGreaterEqual(row["score"], 0.0)
            self.assertLessEqual(row["score"], 100.0)
            self.assertTrue(2 <= len(row["fit_reasons"]) <= 3)
            self.assertTrue(2 <= len(row["watchouts"]) <= 3)
            self.assertTrue(all(isinstance(text, str) and text for text in row["fit_reasons"]))
            self.assertTrue(all(isinstance(text, str) and text for text in row["watchouts"]))
            self.assertTrue(any("uncalibrated" in text.lower() for text in row["watchouts"]))
            self.assertEqual(row["id"], self.data.resolve(row["name"]))
        self.assertTrue(any("product manager" in reason
                            for reason in result["shortlist"][0]["fit_reasons"]))

    def test_shortlist_is_deterministic(self):
        first = wizard(BASE_PREFS, self.data)
        second = wizard(dict(BASE_PREFS), self.data)
        self.assertEqual(first, second)
        self.assertEqual(len({row["id"] for row in first["shortlist"]}), 3)

    def test_language_only_changes_wording_not_scores(self):
        english = wizard(BASE_PREFS, self.data)
        chinese = wizard({**BASE_PREFS, "lang": "zh"}, self.data)
        self.assertEqual([row["id"] for row in english["shortlist"]],
                         [row["id"] for row in chinese["shortlist"]])
        self.assertEqual([row["score"] for row in english["shortlist"]],
                         [row["score"] for row in chinese["shortlist"]])

    def test_risk_team_budget_shift_feasibility_weight_and_ranking(self):
        low = wizard(LOW_PREFS, self.data)
        high = wizard(HIGH_PREFS, self.data)
        low_weight = low["constraints"]["feasibility_weight"]
        high_weight = high["constraints"]["feasibility_weight"]
        self.assertGreater(low_weight, high_weight)
        self.assertGreaterEqual(low_weight, 0.15)
        self.assertLessEqual(low_weight, 0.75)
        self.assertNotEqual([row["id"] for row in low["shortlist"]],
                            [row["id"] for row in high["shortlist"]])

    def test_goal_keywords_change_top_ranking(self):
        baseline = wizard(BASE_PREFS, self.data)
        matched = wizard({**BASE_PREFS, "goal": "security compliance audit"}, self.data)
        self.assertNotEqual(baseline["shortlist"][0]["id"], "安全合规与隐私")
        self.assertEqual(matched["shortlist"][0]["id"], "安全合规与隐私")
        self.assertIn("安全合规与隐私", [row["id"] for row in matched["shortlist"]])
        reasons = " ".join(matched["shortlist"][0]["fit_reasons"]).lower()
        self.assertIn("security", reasons)

    def test_coding_goal_surfaces_coding_scenario(self):
        baseline = wizard({**BASE_PREFS, "goal": ""}, self.data)
        matched = wizard({**BASE_PREFS, "goal": "coding copilot for developers"}, self.data)
        self.assertEqual(matched["shortlist"][0]["id"], "编程与代码智能")
        self.assertNotEqual(baseline["shortlist"][0]["id"], "编程与代码智能")

    def test_chinese_partial_name_goal_surfaces_scenario(self):
        prefs = {"role": "founder", "goal": "安全合规", "team_size": 3,
                 "budget_usd": 60_000, "horizon_weeks": 8, "risk": "low", "lang": "zh"}
        result = wizard(prefs, self.data)
        self.assertEqual(result["shortlist"][0]["id"], "安全合规与隐私")
        self.assertIn("安全合规与隐私",
                      " ".join(result["shortlist"][0]["fit_reasons"]))

    def test_route_keywords_add_a_bonus(self):
        result = wizard({**BASE_PREFS, "goal": "red-ocean differentiation"}, self.data)
        self.assertTrue(any("Red-ocean differentiation" in reason
                            for row in result["shortlist"]
                            for reason in row["fit_reasons"]))

    def test_constraints_echo_coerces_strings(self):
        result = wizard({"role": "investor", "team_size": "6", "budget_usd": "180000",
                         "horizon_weeks": "12", "risk": "high", "lang": "en"}, self.data)
        constraints = result["constraints"]
        self.assertEqual(constraints["role"], "investor")
        self.assertEqual(constraints["team_size"], 6)
        self.assertEqual(constraints["budget_usd"], 180_000)
        self.assertEqual(constraints["horizon_weeks"], 12)
        self.assertEqual(constraints["risk"], "high")
        self.assertEqual(constraints["lang"], "en")
        self.assertIn("score_formula", constraints)

    def test_invalid_or_missing_prefs_use_defaults(self):
        result = wizard({}, self.data)
        constraints = result["constraints"]
        self.assertEqual(constraints["role"], "founder")
        self.assertEqual(constraints["risk"], "medium")
        self.assertEqual(constraints["lang"], "en")
        self.assertEqual(constraints["team_size"], 3)
        self.assertEqual(len(result["shortlist"]), 3)
        self.assertEqual(wizard({"budget_usd": 0}, self.data)["constraints"]["budget_usd"],
                         3 * 8 * 8_000)
        # Unknown role/risk and an unmatched goal must not crash.
        tolerant = wizard({"role": "wizard", "risk": "extreme",
                           "goal": "quantum banana"}, self.data)
        self.assertEqual(tolerant["constraints"]["role"], "founder")
        self.assertEqual(tolerant["constraints"]["risk"], "medium")
        # Non-dict payloads (defensive against a bad request body).
        for payload in (None, [], "founder"):
            self.assertEqual(len(wizard(payload, self.data)["shortlist"]), 3)

    def test_chinese_output_is_localised(self):
        result = wizard({**BASE_PREFS, "goal": "客服", "lang": "zh"}, self.data)
        self.assertEqual(result["constraints"]["lang"], "zh")
        for row in result["shortlist"]:
            self.assertEqual(row["name"], row["id"])
            self.assertTrue(row["name_en"])
            self.assertFalse(_has_cjk(row["name_en"]))
            self.assertTrue(_has_cjk(row["fit_reasons"][0]))
            self.assertTrue(any("产品经理" in reason for reason in row["fit_reasons"]))
            self.assertTrue(_has_cjk(row["watchouts"][0]))
            self.assertTrue(_has_cjk(row["route"]))

    def test_roles_constant(self):
        self.assertEqual(ROLES, ("founder", "enterprise", "investor", "pm"))


class PocPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ScenarioData()

    def test_normalize_weeks(self):
        self.assertEqual(POC_WEEKS, (2, 4, 8))
        expected = {1: 2, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 8, 8: 8, 100: 8, 0: 2, -3: 2}
        for value, weeks in expected.items():
            self.assertEqual(normalize_weeks(value), weeks, value)

    def test_milestone_counts_for_supported_weeks(self):
        counts = {2: 3, 4: 4, 8: 5}
        for weeks, count in counts.items():
            plan = poc_plan("知识管理与文档问答", weeks, 4, self.data, "en")
            self.assertEqual(plan["weeks"], weeks)
            self.assertEqual(len(plan["milestones"]), count)
            schedule = [milestone["week"] for milestone in plan["milestones"]]
            self.assertEqual(schedule, sorted(schedule))
            self.assertEqual(schedule[-1], weeks)
            self.assertTrue(all(1 <= week <= weeks for week in schedule))
            for milestone in plan["milestones"]:
                self.assertTrue(milestone["title"])
                self.assertTrue(2 <= len(milestone["deliverables"]) <= 3)
                self.assertTrue(milestone["exit_criteria"])

    def test_weeks_are_normalised(self):
        for value in (1, 3, 5, 6, 7, 100):
            plan = poc_plan("安全合规与隐私", value, 3, self.data, "en")
            self.assertIn(plan["weeks"], (2, 4, 8))
            self.assertEqual(plan["weeks"], normalize_weeks(value))

    def test_effort_and_cost_are_heuristic_formulas(self):
        for team in (1, 3, 5):
            plan = poc_plan("知识管理与文档问答", 4, team, self.data, "en")
            self.assertEqual(plan["effort_person_weeks"], round(4 * team * 0.6, 1))
            self.assertEqual(plan["cost_range_usd"], [team * 4 * 4_000, team * 4 * 8_000])
            self.assertIs(plan["heuristic"], True)
            self.assertTrue(plan["cost_basis"])
        two_week = poc_plan("编程与代码智能", 8, 5, self.data, "en")
        self.assertEqual(two_week["effort_person_weeks"], 24.0)

    def test_roles_metrics_compliance_and_risks_bounds(self):
        for weeks in (2, 4, 8):
            plan = poc_plan("多智能体与任务编排", weeks, 4, self.data, "en")
            self.assertGreaterEqual(len(plan["roles"]), 3)
            self.assertTrue(3 <= len(plan["metrics"]) <= 5)
            self.assertTrue(3 <= len(plan["data_compliance"]) <= 4)
            self.assertTrue(3 <= len(plan["risks"]) <= 4)
            self.assertTrue(plan["roles"] == list(dict.fromkeys(plan["roles"])))

    def test_unknown_scenario_returns_error(self):
        for value in ("不存在的场景", "", "not-a-scenario"):
            result = poc_plan(value, 4, 3, self.data, "en")
            self.assertIn("error", result)
            self.assertIn("unknown scenario", result["error"])
        # Non-string input must not raise.
        self.assertIn("error", poc_plan(None, 4, 3, self.data, "en"))

    def test_bilingual_plan(self):
        english = poc_plan("安全合规与隐私", 4, 4, self.data, "en")
        chinese = poc_plan("安全合规与隐私", 4, 4, self.data, "zh")
        self.assertEqual(english["scenario"]["id"], "安全合规与隐私")
        self.assertEqual(english["scenario"]["name"], "Security, Compliance & Privacy")
        self.assertEqual(chinese["scenario"]["name"], "安全合规与隐私")
        self.assertEqual(english["milestones"][0]["title"], "Scope & baseline")
        self.assertEqual(chinese["milestones"][0]["title"], "范围与基线")
        self.assertTrue(_has_cjk(chinese["milestones"][1]["deliverables"][0]))
        self.assertTrue(_has_cjk(chinese["risks"][0]))
        self.assertTrue(_has_cjk(chinese["roles"][0]))

    def test_metrics_and_risks_cite_dataset_numbers(self):
        plan = poc_plan("安全合规与隐私", 4, 4, self.data, "en")
        joined = " ".join(plan["metrics"])
        self.assertIn("62.41", joined)   # opportunity 62.4087
        self.assertIn("0.37", joined)    # feasibility 0.3686
        self.assertIn("0.70", " ".join(plan["risks"]))  # barrier 0.7
        self.assertTrue(any("samples" in metric for metric in plan["metrics"]))

    def test_longer_plans_add_compliance_items(self):
        short = poc_plan("安全合规与隐私", 2, 4, self.data, "en")
        long = poc_plan("安全合规与隐私", 4, 4, self.data, "en")
        self.assertEqual(len(short["data_compliance"]), 3)
        self.assertEqual(len(long["data_compliance"]), 4)
        self.assertTrue(any("sandbox" in item for item in long["data_compliance"]))


class PortfolioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ScenarioData()

    def test_generous_budget_selects_three_picks(self):
        result = portfolio(6, 4, 400_000, self.data, "en")
        self.assertEqual(result["picks"][0]["phase"], "build")
        self.assertEqual(len(result["picks"]), 3)
        self.assertLessEqual(len(result["picks"]), 3)
        for row in result["picks"]:
            self.assertIn(row["phase"], ("validate", "build"))
            self.assertEqual(row["score"], round(row["score"], 2))
            self.assertTrue(row["why"])
            self.assertTrue(row["name"])
        self.assertEqual(sum(1 for row in result["picks"] if row["phase"] == "build"), 1)
        self.assertIs(result["heuristic"], True)

    def test_picks_and_excluded_cover_all_scenarios_once(self):
        result = portfolio(6, 4, 400_000, self.data, "en")
        picked = [row["id"] for row in result["picks"]]
        excluded = [row["id"] for row in result["excluded"]]
        self.assertEqual(len(set(picked)), len(picked))
        self.assertEqual(len(picked) + len(excluded), 12)
        self.assertEqual(set(picked) | set(excluded),
                         {row["id"] for row in self.data.catalog("en")})
        self.assertTrue(all(row["why"] for row in result["excluded"]))

    def test_total_effort_is_bounded_and_consistent(self):
        for team, weeks, budget in ((6, 4, 400_000), (6, 4, 40_000),
                                    (1, 2, 1_000), (2, 12, 0), (8, 12, 300_000)):
            result = portfolio(team, weeks, budget, self.data, "en")
            window = result["weeks"]
            allocation = result["assumptions"]["team_per_pick"]
            expected = round(len(result["picks"]) * window * allocation * 0.6, 1)
            self.assertEqual(result["total_effort"], expected)
            self.assertGreater(result["total_effort"], 0.0)
            self.assertLessEqual(result["total_effort"], team * window * 0.6 + 1e-9)

    def test_tight_budget_weights_feasibility_more_and_trims_picks(self):
        tight = portfolio(6, 4, 40_000, self.data, "en")
        generous = portfolio(6, 4, 400_000, self.data, "en")
        self.assertGreater(tight["assumptions"]["feasibility_weight"],
                           generous["assumptions"]["feasibility_weight"])
        self.assertLessEqual(len(tight["picks"]), len(generous["picks"]))
        self.assertEqual(tight["picks"][0]["phase"], "validate")

    def test_budget_is_echoed_or_defaulted(self):
        explicit = portfolio(3, 8, 123_456, self.data, "en")
        self.assertEqual(explicit["budget_usd"], 123_456)
        self.assertFalse(explicit["assumptions"]["budget_defaulted"])
        defaulted = portfolio(3, 8, 0, self.data, "en")
        self.assertEqual(defaulted["budget_usd"], 3 * 8 * 8_000)
        self.assertTrue(defaulted["assumptions"]["budget_defaulted"])

    def test_very_small_budget_still_validates_one_scenario(self):
        result = portfolio(6, 4, 1_000, self.data, "en")
        self.assertEqual(len(result["picks"]), 1)
        self.assertEqual(result["picks"][0]["phase"], "validate")
        self.assertEqual(len(result["excluded"]), 11)

    def test_chinese_portfolio_is_localised(self):
        result = portfolio(6, 4, 400_000, self.data, "zh")
        self.assertTrue(result["picks"])
        for row in result["picks"]:
            self.assertEqual(row["name"], row["id"])
            self.assertTrue(_has_cjk(row["why"]))
        for row in result["excluded"][:5]:
            self.assertTrue(_has_cjk(row["why"]))


class NarrativePromptTests(unittest.TestCase):
    PAYLOAD = {"score": 57.28, "opportunity": 62.4087, "heuristic": True,
               "shortlist": [{"id": "安全合规与隐私", "score": 62.41}]}

    def test_each_builder_returns_system_and_user_messages(self):
        builders = (build_wizard_messages, build_poc_messages, build_portfolio_messages)
        for builder in builders:
            messages = builder(self.PAYLOAD, "en", "founder")
            self.assertEqual([message["role"] for message in messages], ["system", "user"])
            system = messages[0]["content"]
            for token in ("summary", "bullets", "risks", "strict JSON", "heuristic"):
                self.assertIn(token, system)
            self.assertIn("founder", system)
            user = messages[1]["content"]
            self.assertIn("57.28", user)
            self.assertIn('"heuristic": true', user)

    def test_chinese_builder_requires_chinese_strict_json(self):
        for builder in (build_wizard_messages, build_poc_messages, build_portfolio_messages):
            messages = builder(self.PAYLOAD, "zh", "pm")
            system = messages[0]["content"]
            self.assertIn("严格 JSON", system)
            self.assertIn("简体中文", system)
            self.assertIn("产品经理", system)
            self.assertTrue(_has_cjk(messages[1]["content"]))

    def test_builders_tolerate_awkward_payloads(self):
        for builder in (build_wizard_messages, build_poc_messages, build_portfolio_messages):
            for payload in (None, {}, {"nested": {"value": 1}}, [1, 2, 3], "plain"):
                messages = builder(payload, "en", "unknown-role")
                self.assertEqual(len(messages), 2)
                self.assertTrue(messages[0]["content"])
                self.assertTrue(messages[1]["content"])


class ParseNarrativeTests(unittest.TestCase):
    def test_parse_plain_json(self):
        parsed = parse_narrative('{"summary": "ok", "bullets": ["a", "b"], "risks": ["r"]}')
        self.assertEqual(parsed, {"summary": "ok", "bullets": ["a", "b"], "risks": ["r"]})

    def test_parse_json_fenced_block(self):
        text = '```json\n{"summary": "ok", "bullets": ["a"], "risks": []}\n```'
        parsed = parse_narrative(text)
        self.assertEqual(parsed["summary"], "ok")
        self.assertEqual(parsed["bullets"], ["a"])
        self.assertEqual(parsed["risks"], [])

    def test_parse_json_with_surrounding_text(self):
        parsed = parse_narrative('Here is the result:\n{"summary": "s"}\nThanks!')
        self.assertEqual(parsed, {"summary": "s", "bullets": [], "risks": []})

    def test_parse_uses_first_fenced_block(self):
        text = ('```json\n{"summary": "first"}\n```\n'
                'and a trailing block:\n```\n{"summary": "second"}\n```')
        self.assertEqual(parse_narrative(text)["summary"], "first")

    def test_parse_fills_missing_fields(self):
        self.assertEqual(parse_narrative('{"bullets": ["x"]}'),
                         {"summary": "", "bullets": ["x"], "risks": []})
        self.assertEqual(parse_narrative('{"summary": "only"}'),
                         {"summary": "only", "bullets": [], "risks": []})

    def test_parse_coerces_bullet_types(self):
        parsed = parse_narrative('{"summary": "s", "bullets": "one", "risks": [3, {"x": 1}]}')
        self.assertEqual(parsed["bullets"], ["one"])
        self.assertEqual(parsed["risks"], ["3"])

    def test_parse_returns_none_for_unusable_text(self):
        for text in (None, "", "   ", "not json", "```\nno json here\n```",
                     "[1, 2, 3]", '{"foo": 1}', '{"summary": '):
            self.assertIsNone(parse_narrative(text), repr(text))


if __name__ == "__main__":
    unittest.main()
