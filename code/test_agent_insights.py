# -*- coding: utf-8 -*-
"""Tests for the OpenECRS insight helpers (agent_insights.py).

Covers evidence flattening/filtering/facets, scenario detail assembly, the
result2.csv -> insights.json aggregation (including graceful degradation), the
insights loader, and the outbound video links. All fixtures are synthetic or
temporary so the tests never depend on the generated pipeline outputs.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent_insights import (  # noqa: E402
    SIGNAL_FIELDS,
    SUPPLY_FIELDS,
    VIDEO_NOTE,
    build_insights,
    evidence_index,
    facets,
    load_insights,
    query,
    scenario_detail,
    video_links,
)
from agent_tools import ScenarioData  # noqa: E402

DATA_FILE = Path(__file__).resolve().parents[1] / "outputs" / "agent_ui" / "data.json"


def _evidence(source, year, confidence, is_opportunity, gates, title, quote, url=""):
    return {
        "source": source,
        "year": year,
        "confidence": confidence,
        "is_opportunity": is_opportunity,
        "gates": gates,
        "title": title,
        "quote": quote,
        "url": url,
    }


def _payload() -> dict:
    """Two synthetic scenarios plus five evidence records."""
    return {
        "meta": {"title": "test"},
        "scenarios": [
            {
                "name": "知识管理与文档问答",
                "name_en": "Knowledge Management & Document QA",
                "rank": 1,
                "n_docs": 120,
                "opportunity": 88.1,
                "need_rate": 0.9,
                "wtp_rate": 0.3,
                "value_rate": 0.4,
                "urgency_rate": 0.2,
                "growth_slope": 0.01,
                "answer_rate": 0.5,
                "barrier": 0.6,
                "repo_n": 3,
                "repo_stars_sum": 4200,
                "paper_n": 12,
                "show_n": 7,
                "product_n": 2,
                "route": "垂直细分验证",
                "evidence": [
                    _evidence("HackerNews", 2024, 0.9, 1, ["需求", "业务"],
                              "Need better RAG", "we need better retrieval", "https://example.com/1"),
                    _evidence("GitHub", 2025, 0.4, 0, ["需求"],
                              "RAG pipeline", "documents QA slow", "https://example.com/2"),
                    _evidence("Reddit", "", 0.6, 1, ["业务"],
                              "Knowledge base sprawl", "knowledge base is a mess", "https://example.com/3"),
                ],
            },
            {
                "name": "安全合规与隐私",
                "name_en": "Security, Compliance & Privacy",
                "rank": 2,
                "n_docs": 90,
                "opportunity": 62.4,
                "need_rate": 0.7,
                "wtp_rate": 0.2,
                "value_rate": 0.3,
                "urgency_rate": 0.1,
                "growth_slope": 0.004,
                "answer_rate": 0.33,
                "barrier": 0.7,
                "repo_n": 2,
                "repo_stars_sum": 102936,
                "paper_n": 100,
                "show_n": 70,
                "product_n": 0,
                "route": "联合研发/跟踪技术",
                "evidence": [
                    _evidence("HackerNews", 2026, 0.7, 1, ["需求"],
                              "privacy audit", "security compliance pressure", "https://example.com/4"),
                    _evidence("StackOverflow", 2024, 0.2, 0, [],
                              "CSP policy", "audit logs everywhere", "https://example.com/5"),
                ],
            },
        ],
    }


class EvidenceIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = _payload()
        cls.items = evidence_index(cls.raw)

    def test_evidence_index_flattens_evidence(self):
        self.assertEqual(len(self.items), 5)
        expected_fields = {
            "scenario", "scenario_en", "source", "year", "confidence",
            "is_opportunity", "gates", "title", "quote", "url",
        }
        self.assertTrue(expected_fields.issubset(self.items[0]))
        first = self.items[0]
        self.assertEqual(first["scenario"], "知识管理与文档问答")
        self.assertEqual(first["scenario_en"], "Knowledge Management & Document QA")
        self.assertEqual(first["gates"], ["需求", "业务"])
        self.assertEqual(first["year"], 2024)
        self.assertEqual(first["is_opportunity"], 1)
        self.assertEqual(self.items[2]["year"], 0)  # missing year becomes 0
        self.assertTrue(all(item["scenario_en"] for item in self.items))

    def test_evidence_index_accepts_scenario_data(self):
        from_data = evidence_index(ScenarioData(self.raw))
        self.assertEqual(from_data, self.items)

    @unittest.skipUnless(DATA_FILE.exists(), "project data.json unavailable")
    def test_evidence_index_with_project_data(self):
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        items = evidence_index(raw)
        self.assertGreaterEqual(len(items), 1)
        self.assertTrue(all(item["scenario"] and item["scenario_en"] for item in items))


class QueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = evidence_index(_payload())

    def test_query_kind_filter(self):
        self.assertEqual(len(query(self.items, kind="positive")), 3)
        self.assertEqual(len(query(self.items, kind="negative")), 2)
        self.assertEqual(len(query(self.items, kind="all")), 5)
        self.assertEqual(len(query(self.items, kind="unknown")), 5)
        self.assertTrue(all(item["is_opportunity"] == 1 for item in query(self.items, kind="positive")))
        self.assertTrue(all(item["is_opportunity"] == 0 for item in query(self.items, kind="negative")))

    def test_query_scenario_filter_matches_zh_and_en(self):
        self.assertEqual(len(query(self.items, scenario="知识管理与文档问答")), 3)
        self.assertEqual(len(query(self.items, scenario="知识管理")), 3)
        self.assertEqual(len(query(self.items, scenario="knowledge management")), 3)
        self.assertEqual(len(query(self.items, scenario="Security, Compliance & Privacy")), 2)
        self.assertEqual(len(query(self.items, scenario=""), ), 5)
        self.assertEqual(len(query(self.items, scenario="nope")), 0)

    def test_query_source_year_and_confidence_filters(self):
        self.assertEqual(len(query(self.items, source="github")), 1)
        self.assertEqual(len(query(self.items, source="hacker")), 2)
        self.assertEqual(len(query(self.items, year=2024)), 2)
        self.assertEqual(len(query(self.items, year="2024")), 2)
        self.assertEqual(len(query(self.items, year="bad")), 5)
        self.assertEqual(len(query(self.items, min_confidence=0.5)), 3)
        self.assertEqual(len(query(self.items, min_confidence="0.85")), 1)
        self.assertEqual(len(query(self.items, source="HackerNews", min_confidence=0.8)), 1)

    def test_query_text_search_is_case_insensitive(self):
        self.assertEqual(len(query(self.items, q="RAG")), 2)
        self.assertEqual(len(query(self.items, q="security")), 1)
        self.assertEqual(len(query(self.items, q="audit")), 2)
        self.assertEqual(len(query(self.items, q="   ")), 5)
        self.assertEqual(len(query(self.items, q="no-such-text")), 0)

    def test_query_limit_and_invalid_filters(self):
        self.assertEqual(len(query(self.items, limit=2)), 2)
        self.assertEqual(query(self.items, limit=0), [])
        self.assertEqual(len(query(self.items, limit=None)), 5)
        self.assertEqual(len(query(self.items, limit="bad")), 5)
        self.assertEqual(len(query(self.items, limit=999)), 5)
        filtered = query(self.items, kind="negative", limit=1)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["is_opportunity"], 0)

    def test_facets_are_deduped_and_sorted(self):
        result = facets(self.items)
        self.assertEqual(result["scenarios"], ["安全合规与隐私", "知识管理与文档问答"])
        self.assertEqual(result["sources"], ["GitHub", "HackerNews", "Reddit", "StackOverflow"])
        self.assertEqual(result["years"], [2024, 2025, 2026])
        self.assertEqual(facets([]), {"scenarios": [], "sources": [], "years": []})


class ScenarioDetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = _payload()
        cls.insights = {
            "generated_at": "2026-11-23T00:00:00+00:00",
            "scenarios": {
                "知识管理与文档问答": {
                    "trend": {"years": [2024, 2025], "counts": [2, 1]},
                    "source_mix": [
                        {"source": "GitHub", "count": 1},
                        {"source": "HackerNews", "count": 2},
                    ],
                },
            },
        }

    def test_scenario_detail_full_payload(self):
        detail = scenario_detail("知识管理与文档问答", self.raw, self.insights)
        self.assertEqual(detail["id"], "知识管理与文档问答")
        self.assertEqual(detail["name"], "知识管理与文档问答")
        self.assertEqual(detail["name_en"], "Knowledge Management & Document QA")
        self.assertNotIn("evidence", detail["metrics"])
        self.assertEqual(detail["metrics"]["opportunity"], 88.1)
        self.assertEqual(detail["metrics"]["rank"], 1)
        self.assertEqual(
            detail["signals"],
            {
                "need_rate": 0.9,
                "wtp_rate": 0.3,
                "value_rate": 0.4,
                "urgency_rate": 0.2,
                "growth_slope": 0.01,
                "answer_rate": 0.5,
                "barrier": 0.6,
            },
        )
        self.assertEqual(set(detail["signals"]), set(SIGNAL_FIELDS))
        self.assertEqual(set(detail["supply"]), set(SUPPLY_FIELDS))
        self.assertEqual(detail["supply"]["repo_stars_sum"], 4200)
        self.assertEqual(detail["trend"], {"years": [2024, 2025], "counts": [2, 1]})
        self.assertEqual(
            detail["source_mix"],
            [{"source": "HackerNews", "count": 2}, {"source": "GitHub", "count": 1}],
        )
        self.assertEqual(len(detail["evidence"]), 3)
        self.assertTrue(all(item["scenario"] == detail["id"] for item in detail["evidence"]))
        self.assertIn("quote", detail["evidence"][0])

    def test_scenario_detail_accepts_scenario_data_and_english_name(self):
        detail = scenario_detail("Knowledge Management", ScenarioData(self.raw), self.insights)
        self.assertEqual(detail["id"], "知识管理与文档问答")
        self.assertEqual(len(detail["evidence"]), 3)

    def test_scenario_detail_defaults_without_insights(self):
        detail = scenario_detail("安全合规与隐私", self.raw)
        self.assertEqual(detail["trend"], {"years": [], "counts": []})
        self.assertEqual(detail["source_mix"], [])
        self.assertEqual(len(detail["evidence"]), 2)

    def test_scenario_detail_tolerates_malformed_insights(self):
        malformed = {
            "generated_at": None,
            "scenarios": {
                "知识管理与文档问答": {
                    "trend": {"years": ["2024", "bad"], "counts": [2]},
                    "source_mix": [{"source": "X", "count": "3"}, {"bad": 1}, "junk"],
                },
            },
        }
        detail = scenario_detail("知识管理与文档问答", self.raw, malformed)
        self.assertEqual(detail["trend"], {"years": [2024], "counts": [2]})
        self.assertEqual(detail["source_mix"], [{"source": "X", "count": 3}])
        weird = scenario_detail("知识管理与文档问答", self.raw, {"scenarios": []})
        self.assertEqual(weird["trend"], {"years": [], "counts": []})

    def test_scenario_detail_unknown_scenario(self):
        self.assertEqual(scenario_detail("不存在的场景", self.raw), {"error": "unknown scenario"})
        self.assertEqual(scenario_detail("", self.raw), {"error": "unknown scenario"})


class BuildInsightsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def _write_csv(self, name: str, text: str) -> Path:
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_build_insights_aggregates_years_and_sources(self):
        csv_path = self._write_csv(
            "result2.csv",
            "scenario,year,source,title\n"
            "知识管理与文档问答,2024,HackerNews,a\n"
            "知识管理与文档问答,2024,GitHub,b\n"
            "知识管理与文档问答,2025,HackerNews,c\n"
            "知识管理与文档问答,,HackerNews,d\n"
            "知识管理与文档问答,not-a-year,GitHub,e\n"
            "安全合规与隐私,2024,HackerNews,f\n"
            "安全合规与隐私,2024,StackOverflow,g\n",
        )
        out_path = self.tmp / "nested" / "insights.json"
        payload = build_insights(csv_path, out_path)

        self.assertTrue(out_path.exists())
        self.assertGreaterEqual(len(payload["generated_at"]), 10)
        scenarios = payload["scenarios"]
        self.assertEqual(sorted(scenarios), ["安全合规与隐私", "知识管理与文档问答"])
        self.assertEqual(scenarios["知识管理与文档问答"]["trend"], {"years": [2024, 2025], "counts": [2, 1]})
        # source counts include rows whose year is missing/invalid
        self.assertEqual(
            scenarios["知识管理与文档问答"]["source_mix"],
            [{"source": "HackerNews", "count": 3}, {"source": "GitHub", "count": 2}],
        )
        self.assertEqual(scenarios["安全合规与隐私"]["trend"], {"years": [2024], "counts": [2]})
        self.assertEqual(
            scenarios["安全合规与隐私"]["source_mix"],
            [{"source": "HackerNews", "count": 1}, {"source": "StackOverflow", "count": 1}],
        )
        # the written file matches the returned payload and is loadable
        on_disk = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, payload)
        self.assertEqual(load_insights(out_path)["scenarios"], scenarios)

    def test_build_insights_degrades_without_required_columns(self):
        cases = {
            "no_year_no_source.csv": "scenario,title\n知识管理与文档问答,a\n",
            "no_year.csv": "scenario,source,title\n知识管理与文档问答,HackerNews,a\n",
            "no_source.csv": "scenario,year,title\n知识管理与文档问答,2024,a\n",
            "no_scenario.csv": "year,source,title\n2024,HackerNews,a\n",
        }
        for filename, text in cases.items():
            with self.subTest(filename=filename):
                csv_path = self._write_csv(filename, text)
                out_path = self.tmp / f"{filename}.json"
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    payload = build_insights(csv_path, out_path)
                self.assertEqual(payload["scenarios"], {})
                self.assertGreaterEqual(len(payload["generated_at"]), 10)
                self.assertIn("warning", buffer.getvalue().lower())
                self.assertTrue(out_path.exists())
                self.assertEqual(json.loads(out_path.read_text(encoding="utf-8"))["scenarios"], {})

    def test_build_insights_degrades_when_csv_missing(self):
        missing = self.tmp / "missing.csv"
        out_path = self.tmp / "insights.json"
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            payload = build_insights(missing, out_path)
        self.assertEqual(payload["scenarios"], {})
        self.assertIn("not found", buffer.getvalue())
        self.assertTrue(out_path.exists())
        self.assertEqual(load_insights(out_path), {"generated_at": payload["generated_at"], "scenarios": {}})

    def test_build_insights_handles_empty_csv(self):
        csv_path = self._write_csv("empty.csv", "scenario,year,source\n")
        out_path = self.tmp / "insights.json"
        payload = build_insights(csv_path, out_path)
        self.assertEqual(payload["scenarios"], {})

    def test_scenario_detail_uses_built_insights(self):
        csv_path = self._write_csv(
            "result2.csv",
            "scenario,year,source\n知识管理与文档问答,2024,HackerNews\n知识管理与文档问答,2024,GitHub\n",
        )
        insights = build_insights(csv_path, self.tmp / "insights.json")
        detail = scenario_detail("知识管理与文档问答", _payload(), insights)
        self.assertEqual(detail["trend"], {"years": [2024], "counts": [2]})
        self.assertEqual(
            detail["source_mix"],
            [{"source": "GitHub", "count": 1}, {"source": "HackerNews", "count": 1}],
        )


class LoadInsightsTests(unittest.TestCase):
    def test_load_insights_missing_returns_empty_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = load_insights(Path(tmp) / "nope.json")
        self.assertEqual(payload, {"generated_at": None, "scenarios": {}})

    def test_load_insights_normalises_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "insights.json"
            path.write_text(json.dumps({"scenarios": []}), encoding="utf-8")
            self.assertEqual(load_insights(path), {"generated_at": None, "scenarios": {}})
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(load_insights(path), {"generated_at": None, "scenarios": {}})


class VideoLinksTests(unittest.TestCase):
    def test_video_links_returns_four_encoded_links(self):
        links = video_links("知识管理与文档问答", _payload(), "zh")
        self.assertEqual(len(links), 4)
        self.assertEqual([link["platform"] for link in links], ["youtube", "youtube", "bilibili", "bilibili"])
        self.assertTrue(all(link["kind"] == "search" for link in links))
        self.assertTrue(all(link["note"] == VIDEO_NOTE for link in links))
        self.assertIn("外部视频", links[0]["note"])
        self.assertIn("not part of the evidence base", links[0]["note"])
        self.assertTrue(links[0]["url"].startswith("https://www.youtube.com/results?search_query="))
        self.assertTrue(links[2]["url"].startswith("https://search.bilibili.com/all?keyword="))
        self.assertNotIn(" ", links[0]["url"])
        self.assertIn(quote("知识管理与文档问答 AI 产品 案例 分析", safe=""), links[0]["url"])
        self.assertIn(quote("Knowledge Management & Document QA AI product case study", safe=""),
                      links[1]["url"])
        parsed = urlparse(links[2]["url"])
        self.assertEqual(parse_qs(parsed.query)["keyword"][0], "知识管理与文档问答 AI 产品 案例 分析")
        parsed = urlparse(links[3]["url"])
        self.assertEqual(parse_qs(parsed.query)["keyword"][0],
                         "Knowledge Management & Document QA AI product case study")
        self.assertIn("AI 产品案例", links[0]["title"])
        self.assertIn("哔哩哔哩", links[2]["title"])

    def test_video_links_language_and_empty_input(self):
        links = video_links("知识管理与文档问答", _payload(), "en")
        self.assertEqual(len(links), 4)
        self.assertEqual(links[1]["title"],
                         "YouTube · Knowledge Management & Document QA AI product case study")
        self.assertIn("(Chinese)", links[0]["title"])
        self.assertIn("Bilibili", links[2]["title"])
        self.assertEqual(video_links("", _payload(), "zh"), [])
        # unknown but non-empty names still produce search links without raising
        unknown = video_links("不存在的场景", _payload(), "zh")
        self.assertEqual(len(unknown), 4)
        self.assertIn(quote("不存在的场景 AI 产品 案例 分析", safe=""), unknown[0]["url"])


class IntegrationTests(unittest.TestCase):
    def test_agent_ui_data_exposes_insights_builder(self):
        import agent_ui_data

        self.assertTrue(callable(getattr(agent_ui_data, "build_insights_file", None)))


if __name__ == "__main__":
    unittest.main()
