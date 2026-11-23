# -*- coding: utf-8 -*-
"""Deterministic tools that the LLM agent can call over the OpenECRS evidence base.

The LLM is required for planning and wording; these tools only retrieve and
format grounded data (scores, ranking, evidence quotes). Numbers never come from
the model.
"""
from __future__ import annotations

import json
from pathlib import Path

from scenario_names import ROUTE_NAMES_EN, SCENARIO_NAMES_EN

BASE = Path(__file__).resolve().parents[1]
DATA_FILE = BASE / "outputs" / "agent_ui" / "data.json"

NAME_ALIASES = {
    "安全合规与隐私": ["安全", "合规", "隐私", "security", "compliance", "privacy", "audit"],
    "多智能体与任务编排": ["多智能体", "智能体", "编排", "agent", "agents", "multi-agent", "orchestration"],
    "知识管理与文档问答": ["知识管理", "文档", "rag", "knowledge", "document", "qa"],
    "编程与代码智能": ["编程", "代码", "coding", "code", "copilot"],
    "办公协作与会议效率": ["办公", "会议", "office", "meeting", "collaboration"],
    "垂直行业应用": ["垂直", "行业", "vertical", "industry"],
    "客户服务与智能客服": ["客服", "客户服务", "customer service", "support"],
    "浏览器与工作流自动化": ["浏览器", "工作流", "browser", "workflow", "automation", "rpa"],
    "语音与实时交互": ["语音", "voice", "speech", "realtime", "real-time", "tts"],
    "内容创作与营销": ["内容", "营销", "content", "marketing", "creation"],
    "教育学习与知识辅导": ["教育", "学习", "education", "learning", "tutoring"],
    "数据分析与商业洞察": ["数据分析", "数据", "data analysis", "analytics", "bi"],
}


def load_data(path: Path | None = None) -> dict:
    path = Path(path or DATA_FILE)
    return json.loads(path.read_text(encoding="utf-8"))


def display_name(name: str, lang: str = "en") -> str:
    return name if lang == "zh" else SCENARIO_NAMES_EN.get(name, name)


def display_route(route: str, lang: str = "en") -> str:
    return route if lang == "zh" else ROUTE_NAMES_EN.get(route, route)


class ScenarioData:
    def __init__(self, data: dict | None = None):
        self.data = data or load_data()
        self.meta = self.data["meta"]
        self.scenarios = {s["name"]: s for s in self.data["scenarios"]}
        self.ranked = sorted(self.data["scenarios"], key=lambda s: s["rank"])

    # ------------------------------------------------------------ resolution
    def resolve(self, value: str) -> str | None:
        value = (value or "").strip()
        if not value:
            return None
        if value in self.scenarios:
            return value
        lowered = value.lower()
        for name, scenario in self.scenarios.items():
            if (scenario.get("name_en") or "").lower() == lowered or name == value:
                return name
        for name in self.scenarios:
            if name in value:
                return name
        for name, aliases in NAME_ALIASES.items():
            for alias in aliases:
                if alias.lower() in lowered:
                    return name
        return None

    def display(self, name: str, lang: str = "en") -> str:
        return display_name(name, lang)

    # ---------------------------------------------------------------- tools
    def catalog(self, lang: str = "en") -> list[dict]:
        rows = []
        for s in self.ranked:
            rows.append({
                "id": s["name"],
                "name": self.display(s["name"], lang),
                "rank": s["rank"],
                "opportunity": s["opportunity"],
                "demand": s["demand"],
                "gap": s["gap"],
                "feasibility": s["feasibility"],
                "value": s["value"],
                "n_docs": s["n_docs"],
                "route": display_route(s["route"], lang),
            })
        return rows

    def scenario(self, name: str, lang: str = "en", evidence_limit: int = 5) -> dict:
        key = self.resolve(name)
        if not key:
            return {"error": f"unknown scenario: {name}"}
        s = self.scenarios[key]
        return {
            "id": key,
            "name": self.display(key, lang),
            "rank": s["rank"],
            "n_docs": s["n_docs"],
            "demand": s["demand"],
            "gap": s["gap"],
            "feasibility": s["feasibility"],
            "value": s["value"],
            "opportunity": s["opportunity"],
            "supply_maturity": s["supply_maturity"],
            "need_rate": s["need_rate"],
            "wtp_rate": s["wtp_rate"],
            "value_rate": s["value_rate"],
            "growth_slope": s["growth_slope"],
            "source_entropy": s["source_entropy"],
            "answer_rate": s["answer_rate"],
            "repo_n": s["repo_n"],
            "paper_n": s["paper_n"],
            "show_n": s["show_n"],
            "barrier": s["barrier"],
            "route": display_route(s["route"], lang),
            "opportunity_records": s["opportunity_records"],
            "evidence": self.evidence(key, lang, evidence_limit),
        }

    def ranking(self, lang: str = "en") -> list[dict]:
        rows = []
        for s in self.ranked:
            rows.append({
                "rank": s["rank"],
                "scenario": self.display(s["name"], lang),
                "id": s["name"],
                "opportunity": s["opportunity"],
                "demand": s["demand"],
                "gap": s["gap"],
                "feasibility": s["feasibility"],
                "value": s["value"],
                "n_docs": s["n_docs"],
                "route": display_route(s["route"], lang),
            })
        return rows

    def compare(self, names: list[str], lang: str = "en") -> dict:
        keys = [k for k in (self.resolve(n) for n in names[:3]) if k]
        if len(keys) < 2:
            return {"error": "compare needs at least two known scenarios"}
        rows = []
        label_key = "Metric" if lang != "zh" else "指标"
        labels = ("Rank", "Opportunity", "Demand", "Supply gap", "Feasibility", "Business value",
                  "Samples", "Route") if lang != "zh" else ("综合排名", "机会总分", "需求强度", "供给缺口",
                                                             "技术可行性", "商业价值", "样本量", "建议路线")
        metrics = [("rank", None), ("opportunity", 1), ("demand", 2), ("gap", 2), ("feasibility", 2),
                   ("value", 2), ("n_docs", 0), ("route", None)]
        for label, (field, digits) in zip(labels, metrics):
            row = {label_key: label}
            for key in keys:
                s = self.scenarios[key]
                if field == "route":
                    row[self.display(key, lang)] = display_route(s["route"], lang)
                elif digits is None:
                    row[self.display(key, lang)] = f"#{s['rank']}" if lang != "zh" else f"第 {s['rank']} 名"
                elif field == "n_docs":
                    row[self.display(key, lang)] = str(s["n_docs"])
                else:
                    row[self.display(key, lang)] = f"{s[field]:.{digits}f}"
            rows.append(row)
        return {"scenarios": [self.display(k, lang) for k in keys], "rows": rows}

    def evidence(self, name: str, lang: str = "en", limit: int = 5) -> list[dict]:
        key = self.resolve(name)
        if not key:
            return []
        out = []
        for ev in self.scenarios[key].get("evidence", [])[:limit]:
            out.append({
                "scenario": self.display(key, lang),
                "source": ev.get("source", ""),
                "year": ev.get("year", ""),
                "confidence": ev.get("confidence"),
                "is_opportunity": ev.get("is_opportunity", 0),
                "title": ev.get("title", ""),
                "quote": ev.get("quote", ""),
                "url": ev.get("url", ""),
            })
        return out

    def search(self, query: str, lang: str = "en", limit: int = 5) -> list[dict]:
        words = [w for w in (query or "").lower().split() if w]
        if not words:
            return []
        scored = []
        for s in self.ranked:
            for ev in s.get("evidence", []):
                haystack = " ".join([ev.get("title", ""), ev.get("quote", ""), ev.get("snippet", "")]).lower()
                score = sum(2 if w in ev.get("title", "").lower() else 1 for w in words if w in haystack)
                if score:
                    scored.append((score, s["name"], ev))
        scored.sort(key=lambda item: (item[0], item[2].get("confidence") or 0), reverse=True)
        out = []
        for _, key, ev in scored[:limit]:
            out.append({
                "scenario": self.display(key, lang),
                "source": ev.get("source", ""),
                "year": ev.get("year", ""),
                "confidence": ev.get("confidence"),
                "is_opportunity": ev.get("is_opportunity", 0),
                "title": ev.get("title", ""),
                "quote": ev.get("quote", ""),
                "url": ev.get("url", ""),
            })
        return out

    def meta_info(self, lang: str = "en") -> dict:
        m = self.meta
        if lang == "zh":
            return {
                "records_clean": m.get("records_clean"), "demand_units": m.get("demand_units"),
                "high_conf_samples": m.get("high_conf_samples"),
                "evidence_records": m.get("evidence_records"),
                "evidence_opportunities": m.get("evidence_opportunities"),
                "data_cutoff": m.get("data_cutoff"),
                "calibration": m.get("calibration"),
                "gold_records": m.get("gold_records"),
                "source_hhi": m.get("source_hhi"),
            }
        return {
            "records_clean": m.get("records_clean"), "demand_units": m.get("demand_units"),
            "high_conf_samples": m.get("high_conf_samples"),
            "evidence_records": m.get("evidence_records"),
            "evidence_opportunities": m.get("evidence_opportunities"),
            "data_cutoff": m.get("data_cutoff"),
            "calibration": m.get("calibration"),
            "gold_records": m.get("gold_records"),
            "source_hhi": m.get("source_hhi"),
        }

    # ------------------------------------------------------------- executor
    def run_tool(self, tool: str, args: dict, lang: str = "en") -> dict:
        args = args or {}
        if tool == "catalog":
            return {"catalog": self.catalog(lang)}
        if tool == "ranking":
            return {"ranking": self.ranking(lang)}
        if tool == "scenario":
            return {"scenario": self.scenario(args.get("name", ""), lang,
                                             int(args.get("evidence_limit", 5)))}
        if tool == "compare":
            names = args.get("names") or ([args.get("a"), args.get("b")] if args.get("a") else [])
            return {"comparison": self.compare([n for n in names if n], lang)}
        if tool == "evidence":
            return {"evidence": self.evidence(args.get("name", ""), lang, int(args.get("limit", 5)))}
        if tool == "search":
            return {"evidence": self.search(args.get("query", ""), lang, int(args.get("limit", 5)))}
        if tool == "meta":
            return {"meta": self.meta_info(lang)}
        return {"error": f"unknown tool: {tool}"}

    # ------------------------------------------------------------ reporting
    def report_context(self, answer: dict, lang: str = "en") -> dict:
        en = lang != "zh"
        names = answer.get("scenarios") or []
        metrics = answer.get("metrics") or {}
        first = metrics.get(names[0]) if names else None
        metrics_rows = []
        if first:
            if en:
                metrics_rows = [
                    ("Rank", f"#{first['rank']}"),
                    ("Opportunity score", f"{first['opportunity']:.2f}"),
                    ("Demand strength", f"{first['demand']:.2f} (weight 45%)"),
                    ("Supply gap", f"{first['gap']:.2f} (weight 25%)"),
                    ("Technical feasibility", f"{first['feasibility']:.2f} (weight 18%)"),
                    ("Business value", f"{first['value']:.2f} (weight 12%)"),
                    ("Samples", f"{first['n_docs']} high-confidence samples"),
                    ("Demand signal", f"need_rate {first['need_rate']:.2f} / growth {first['growth_slope']:+.2%}"),
                    ("Payment signal", f"wtp_rate {first['wtp_rate']:.2f} / value_rate {first['value_rate']:.2f}"),
                    ("Supply proxy", f"repos {first['repo_n']} / papers {first['paper_n']} / Show HN {first['show_n']}"),
                    ("Recommended route", first["route"]),
                ]
            else:
                metrics_rows = [
                    ("综合排名", f"第 {first['rank']} 名"),
                    ("机会总分", f"{first['opportunity']:.2f}"),
                    ("需求强度", f"{first['demand']:.2f}（权重 45%）"),
                    ("供给缺口", f"{first['gap']:.2f}（权重 25%）"),
                    ("技术可行性", f"{first['feasibility']:.2f}（权重 18%）"),
                    ("商业价值", f"{first['value']:.2f}（权重 12%）"),
                    ("样本量", f"{first['n_docs']} 条高置信样本"),
                    ("需求信号", f"need_rate {first['need_rate']:.2f} / 增速 {first['growth_slope']:+.2%}"),
                    ("付费信号", f"wtp_rate {first['wtp_rate']:.2f} / value_rate {first['value_rate']:.2f}"),
                    ("供给镜像", f"仓库 {first['repo_n']} / 论文 {first['paper_n']} / Show HN {first['show_n']}"),
                    ("建议路线", first["route"]),
                ]
        return {
            "kind": answer.get("kind", ""),
            "lang": lang,
            "title": "OpenECRS · Scenario Opportunity Brief" if en else "OpenECRS · 场景机会建议书",
            "subtitle": answer.get("question") or answer.get("heading", ""),
            "heading": answer.get("heading", ""),
            "advice": answer.get("advice", ""),
            "reply": answer.get("reply", ""),
            "metrics_rows": metrics_rows,
            "comparison": answer.get("comparison") or [],
            "ranking": answer.get("ranking") or [],
            "evidence": answer.get("evidence") or [],
            "actions": answer.get("actions") or [],
            "risks": answer.get("risks") or [],
            "meta": self.meta,
            "scenarios": names,
            "engine": answer.get("engine") or {},
        }
