# -*- coding: utf-8 -*-
"""Deterministic, bilingual conversational reasoning over the scenario evidence base.

OpenECRS reads the compact dataset produced by agent_ui_data.py and turns a
question (or a suggested choice) into a structured recommendation:

  1) one-sentence advice
  2) detailed data: metrics, ranking, evidence quotes, actions, limits

The engine is offline and reproducible. It supports English (default for the
GitHub release) and Chinese, selected with the ``lang`` argument. Scenario keys
stay in Chinese internally (they are the dataset keys); display names and every
sentence are localised at the end of a request.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from scenario_names import ROUTE_NAMES_EN, SCENARIO_NAMES_EN

BASE = Path(__file__).resolve().parents[1]
DATA_FILE = BASE / "outputs" / "agent_ui" / "data.json"

SCENARIO_ALIASES = {
    "多智能体与任务编排": ["多智能体", "任务编排", "智能体", "编排", "自主代理", "agent", "agents", "agentic",
                          "multi-agent", "multi agent", "orchestration"],
    "知识管理与文档问答": ["知识管理", "文档问答", "文档", "rag", "检索增强", "知识库", "向量库", "问答",
                          "knowledge management", "document qa", "document question answering",
                          "knowledge base", "documents", "document"],
    "编程与代码智能": ["编程", "代码", "开发", "程序员", "工程效率", "coding", "code intelligence", "code",
                      "copilot", "programming"],
    "安全合规与隐私": ["安全合规", "合规", "隐私", "安全", "风控", "审计", "监管", "泄露",
                      "security", "compliance", "privacy", "audit", "regulatory"],
    "语音与实时交互": ["语音", "实时交互", "语音识别", "转录", "实时语音", "口语",
                      "voice", "realtime", "real-time", "speech", "tts", "transcription"],
    "数据分析与商业洞察": ["数据分析", "商业洞察", "报表", "数据洞察", "分析平台",
                          "data analysis", "business insights", "analytics", "bi", "reporting"],
    "浏览器与工作流自动化": ["浏览器", "工作流", "自动化", "网页自动化", "流程自动化",
                            "browser", "workflow automation", "automation", "rpa"],
    "内容创作与营销": ["内容创作", "营销", "内容", "创作", "文案", "广告",
                      "content creation", "marketing", "copywriting", "content", "seo"],
    "教育学习与知识辅导": ["教育", "学习", "辅导", "教学", "培训",
                          "education", "learning", "tutoring", "teaching", "tutor"],
    "办公协作与会议效率": ["办公协作", "会议", "办公", "协作", "邮件", "日程", "纪要",
                          "office", "collaboration", "meeting", "meetings", "email", "calendar"],
    "客户服务与智能客服": ["客服", "客户服务", "客户支持", "工单",
                          "customer service", "customer support", "support", "helpdesk", "ticket"],
    "垂直行业应用": ["垂直行业", "垂直", "行业应用", "医疗", "法律", "金融", "制造", "建筑",
                    "vertical industry", "vertical", "industry", "healthcare", "legal",
                    "finance", "manufacturing"],
}

TOP_WORDS = ["最值得", "优先", "排名", "第一", "top", "哪些", "推荐", "机会最大", "机会分", "排序", "排行榜",
             "best", "most promising", "priority", "prioritize", "rank", "ranking", "which",
             "recommend", "opportunit"]
EVIDENCE_WORDS = ["证据", "原文", "依据", "出处", "span", "引用", "为什么", "原因",
                  "evidence", "quote", "source", "why", "reason", "according"]
COMPARE_WORDS = ["对比", "比较", " vs ", "vs", "区别", "差异", "哪个更", "哪个好",
                 "compare", "comparison", "versus", " vs", "difference", "better"]
ACTION_WORDS = ["落地", "怎么做", "产品", "创业", "方案", "建议", "切入", "poc", "验证", "行动",
                "action", "plan", "roadmap", "advice", "recommendation", "build", "product",
                "startup", "validate", "next step"]
RISK_WORDS = ["风险", "局限", "坑", "注意", "可行性低", "问题", "缺陷",
              "risk", "limitation", "limitations", "downside", "caveat", "challenge"]
ORDINAL_RE = re.compile(r"第\s*([一二三四五六七八九十\d]+)\s*(名|个|位|条)?")
EN_ORDINAL_RE = re.compile(r"\b(?:number|#)\s*(\d+)\b|\b(\d+)(?:st|nd|rd|th)\b|\b(second|third|fourth|fifth|first)\b", re.I)
EN_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}

_CHINESE_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                   "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

ASCII_ALIAS_RE = re.compile(r"^[\x00-\x7f]+$")


def load_data(path: Path | None = None) -> dict:
    path = Path(path or DATA_FILE)
    if not path.exists():
        from agent_ui_data import build
        build()
    return json.loads(path.read_text(encoding="utf-8"))


def _ordinal_value(token: str) -> int:
    if token.isdigit():
        return int(token)
    if token == "十":
        return 10
    if token.startswith("十"):
        return 10 + _CHINESE_DIGITS.get(token[1:], 0)
    if token.endswith("十"):
        return _CHINESE_DIGITS.get(token[0], 0) * 10
    if "十" in token:
        a, b = token.split("十", 1)
        return _CHINESE_DIGITS.get(a, 0) * 10 + _CHINESE_DIGITS.get(b, 0)
    return _CHINESE_DIGITS.get(token, 0)


def _has_word(text: str, word: str) -> bool:
    if ASCII_ALIAS_RE.match(word):
        return re.search(r"(?<![a-z0-9])" + re.escape(word.lower()) + r"(?![a-z0-9])", text) is not None
    return word in text


class OpenECRSAgent:
    def __init__(self, data: dict | None = None):
        self.data = data or load_data()
        self.meta = self.data["meta"]
        self.scenarios = {s["name"]: s for s in self.data["scenarios"]}
        self.ranked = sorted(self.data["scenarios"], key=lambda s: s["rank"])

    # ------------------------------------------------------------- localising
    @staticmethod
    def _le(lang: str) -> bool:
        return lang != "zh"

    def display(self, key: str, lang: str = "en") -> str:
        if lang == "zh":
            return key
        return SCENARIO_NAMES_EN.get(key, key)

    def route(self, key: str, lang: str = "en") -> str:
        return ROUTE_NAMES_EN.get(key, key) if self._le(lang) else key

    def _localize(self, answer: dict, lang: str) -> dict:
        if not self._le(lang):
            return answer
        out = dict(answer)
        names = answer.get("scenarios") or []
        labels = {name: self.display(name, lang) for name in names}
        out["scenarios"] = [labels.get(n, n) for n in names]
        if answer.get("scenario"):
            out["scenario"] = self.display(answer["scenario"], lang)
        out["labels"] = labels
        if answer.get("metrics"):
            out["metrics"] = {labels.get(k, k): v for k, v in answer["metrics"].items()}
        if answer.get("ranking"):
            out["ranking"] = [dict(row, scenario=self.display(row["scenario"], lang),
                                   route=self.route(row.get("route", ""), lang))
                              for row in answer["ranking"]]
        if answer.get("comparison"):
            out["comparison"] = [{self.display(k, lang) if k != "指标" else k: v for k, v in row.items()}
                                 for row in answer["comparison"]]
        if answer.get("evidence"):
            out["evidence"] = [dict(ev, scenario=self.display(ev["scenario"], lang))
                               if ev.get("scenario") else dict(ev) for ev in answer["evidence"]]
        return out

    # ---------------------------------------------------------------- parsing
    def match_scenarios(self, text: str) -> list[str]:
        lowered = text.lower()
        found = []
        for name in self.scenarios:
            if name in text or self.display(name, "en").lower() in lowered:
                found.append(name)
        aliases = []
        for name, words in SCENARIO_ALIASES.items():
            for word in words:
                if _has_word(lowered, word):
                    aliases.append((len(word), name))
        aliases.sort(reverse=True)
        for _, name in aliases:
            if name not in found:
                found.append(name)
        return found

    def resolve_targets(self, text: str, session: dict) -> list[str]:
        matched = self.match_scenarios(text)
        if len(matched) >= 2:
            return matched[:3]
        if matched:
            return matched[:1]
        order = session.get("last_ranking") or [s["name"] for s in self.ranked]
        for token in ORDINAL_RE.findall(text):
            value = _ordinal_value(token[0] if isinstance(token, tuple) else token)
            if 1 <= value <= len(order):
                return [order[value - 1]]
        for match in EN_ORDINAL_RE.finditer(text):
            token = match.group(1) or match.group(2) or match.group(3) or ""
            value = int(token) if token.isdigit() else EN_ORDINALS.get(token.lower(), 0)
            if 1 <= value <= len(order):
                return [order[value - 1]]
        follow_words = ("它", "这个", "该", "其", "方案", "建议", "怎么", "证据", "风险",
                        "it", "this", "that", "its", "same", "plan", "advice", "evidence", "risk")
        lowered = text.lower()
        follows = any((_has_word(lowered, w.lower()) if ASCII_ALIAS_RE.match(w) else w in text)
                      for w in follow_words)
        if session.get("last_scenario") and follows:
            return [session["last_scenario"]]
        return []

    # -------------------------------------------------------------- answering
    def answer(self, message: str, session: dict | None = None, lang: str = "zh") -> dict:
        session = session if session is not None else {}
        message = (message or "").strip()
        lowered = message.lower()
        targets = self.resolve_targets(message, session)
        want_compare = any(w in lowered for w in COMPARE_WORDS)
        want_evidence = any(w in lowered for w in EVIDENCE_WORDS)
        want_risk = any(w in lowered for w in RISK_WORDS)
        want_action = any(w in lowered for w in ACTION_WORDS)
        want_top = any(w in lowered for w in TOP_WORDS)

        if want_compare and len(targets) >= 2:
            result = self._compare(targets[0], targets[1], lang)
        elif len(targets) == 1 and want_risk:
            result = self._scenario(targets[0], intent="risk", lang=lang)
        elif len(targets) == 1 and want_evidence:
            result = self._scenario(targets[0], intent="evidence", message=message, lang=lang)
        elif len(targets) == 1:
            result = self._scenario(targets[0], intent="action" if want_action else "overview", lang=lang)
        elif want_top:
            result = self._ranking(lang)
        elif want_evidence and not targets:
            result = self._evidence_overview(lang)
        else:
            result = self._overview(lang)

        result["question"] = message
        result["lang"] = lang
        result.setdefault("scenario", (result.get("scenarios") or [None])[0])
        if result.get("scenarios"):
            session["last_scenario"] = result["scenarios"][0]
        if result.get("ranking"):
            session["last_ranking"] = [row["scenario"] for row in result["ranking"]]
        session["last_answer"] = result
        session["turns"] = int(session.get("turns", 0)) + 1
        return self._localize(result, lang)

    # ---------------------------------------------------------------- builders
    def _overview(self, lang: str = "zh") -> dict:
        en = self._le(lang)
        top3 = self.ranked[:3]
        if en:
            advice = (f"Start with three directions: {self.display(top3[0]['name'], lang)} scores highest "
                      f"({top3[0]['opportunity']:.1f}) but is the least feasible; "
                      f"{self.display(top3[1]['name'], lang)} has the strongest demand ({top3[1]['demand']:.2f}) "
                      f"and is executable; {self.display(top3[2]['name'], lang)} sits in between.")
            reply = ("I can explain the four-dimension scores, evidence quotes and action plans for all 12 AI "
                     "application scenarios. Pick a suggestion below or just ask whether a scenario is worth "
                     "building; every answer can be exported as a PDF brief (one-sentence advice + detailed data).")
            actions = ["Pick the scenario you care about most (any of the 12 below).",
                       "Review its demand, gap, feasibility and value scores plus the quoted evidence.",
                       "Use 'Export PDF' to share the conclusion and data with your team or reviewers."]
            chips = ["Which scenario should we prioritise?",
                     "Compare Security, Compliance & Privacy vs Multi-agent",
                     "Show evidence for Knowledge Management & Document QA",
                     "Give me a 3-month execution plan"]
            heading = "Overview: the 12 scenarios on the radar"
        else:
            advice = (
                f"先看三个方向：『{top3[0]['name']}』机会分最高（{top3[0]['opportunity']:.1f}）但可行性最低，"
                f"『{top3[1]['name']}』需求最强（{top3[1]['demand']:.2f}）且可直接落地，"
                f"『{top3[2]['name']}』处于中间。"
            )
            reply = (
                "我可以把 12 个 AI 应用场景的四维评分、证据原文和行动建议直接讲清楚。"
                "你可以点下面的快捷问题，或者直接问某个场景值不值得做；"
                "每条回答都能一键导出含「一句话建议 + 详细数据」的 PDF 建议书。"
            )
            actions = [
                "先选一个你最关心的场景（下面 12 个场景任一）。",
                "看该场景的需求、缺口、可行性、价值四项评分与证据原文。",
                "用「导出 PDF 建议书」把结论和详细数据发给团队/评委。",
            ]
            chips = ["哪个场景最值得优先做？", "对比 安全合规 和 多智能体",
                     "知识管理与文档问答 的证据", "给我一个三个月内的落地建议"]
            heading = "总览：机会雷达的 12 个场景"
        return {
            "kind": "overview",
            "reply": reply,
            "advice": advice,
            "scenarios": [s["name"] for s in top3],
            "metrics": {s["name"]: self._metric(s) for s in top3},
            "ranking": [self._rank_row(s) for s in self.ranked[:5]],
            "evidence": [],
            "actions": actions,
            "risks": self._risks(None, lang),
            "chips": chips,
            "heading": heading,
        }

    def _ranking(self, lang: str = "zh") -> dict:
        en = self._le(lang)
        top3 = self.ranked[:3]
        best_pick = max(top3, key=lambda s: s["opportunity"] * (0.45 + s["feasibility"]))
        if en:
            advice = (f"By the weighted score the top three are {self.display(top3[0]['name'], lang)} "
                      f"{top3[0]['opportunity']:.1f}, {self.display(top3[1]['name'], lang)} "
                      f"{top3[1]['opportunity']:.1f} and {self.display(top3[2]['name'], lang)} "
                      f"{top3[2]['opportunity']:.1f}; balancing score and feasibility, start with "
                      f"{self.display(best_pick['name'], lang)} (score {best_pick['opportunity']:.1f}, "
                      f"feasibility {best_pick['feasibility']:.2f}).")
            reply = ("Below is the 12-scenario ranking. Opportunity score = demand 45% + supply gap 25% + "
                     "technical feasibility 18% + business value 12% (AHP weights, CR=0.0002). "
                     "A high rank does not mean 'build it now': Security, Compliance & Privacy has the largest "
                     f"gap but only {top3[0]['feasibility']:.2f} feasibility, so start with a small PoC.")
            actions = [
                "For quarterly results: prioritise Multi-agent & Task Orchestration or Knowledge Management & "
                "Document QA, as vertical workflow products rather than general platforms.",
                "For high-value validation: run a 2–4 week compliance evidence-chain / audit-trail PoC and use "
                "real willingness-to-pay as the go/no-go signal.",
                "Scenarios with fewer than 90 samples (Education, Customer Service, Office, Vertical Industry) "
                "are directional only — do not budget on the score alone.",
            ]
            chips = ["Compare the #1 and #2", "Why is Security & Compliance hard to build?",
                     "Show evidence for Multi-agent", "Give me a 2-week PoC plan"]
            heading = "Ranking: opportunity score for all 12 scenarios"
        else:
            advice = (
                f"按当前四维评分，前三名依次是『{top3[0]['name']}』{top3[0]['opportunity']:.1f}、"
                f"『{top3[1]['name']}』{top3[1]['opportunity']:.1f}、『{top3[2]['name']}』{top3[2]['opportunity']:.1f}；"
                f"综合分数与可行性，先动手的应是『{best_pick['name']}』（机会 {best_pick['opportunity']:.1f}，可行性 {best_pick['feasibility']:.2f}）。"
            )
            reply = (
                "下面是 12 个场景的机会总分排名。机会总分 = 需求强度 45% + 供给缺口 25% + "
                "技术可行性 18% + 商业价值 12%（AHP 权重，CR=0.0002）。"
                "排名高不等于立刻能做：安全合规与隐私缺口最大，但可行性只有 "
                f"{top3[0]['feasibility']:.2f}，通常要先做小范围 PoC。"
            )
            actions = [
                "若要在季度内出结果：优先『多智能体与任务编排』或『知识管理与文档问答』，做垂直工作流而不是通用平台。",
                "若要做高价值验证：对『安全合规与隐私』做 2–4 周合规证据链/审计留痕 PoC，用付费意愿做 go/no-go。",
                "样本量低于 90 的场景（教育、客服、办公、垂直行业等）只作方向性判断，不要按分数直接立项。",
            ]
            chips = ["对比第 1 名和第 2 名", "为什么安全合规可行性低？",
                     "看多智能体与任务编排的证据", "给我一个 2 周 PoC 方案"]
            heading = "12 个场景机会总分排名"
        return {
            "kind": "ranking",
            "reply": reply,
            "advice": advice,
            "scenarios": [s["name"] for s in top3],
            "metrics": {s["name"]: self._metric(s) for s in top3},
            "ranking": [self._rank_row(s) for s in self.ranked],
            "evidence": [],
            "actions": actions,
            "risks": self._risks(None, lang),
            "chips": chips,
            "heading": heading,
        }

    def _scenario(self, name: str, intent: str = "overview", message: str = "", lang: str = "zh") -> dict:
        en = self._le(lang)
        s = self.scenarios[name]
        label = self.display(name, lang)
        evidence = s.get("evidence", [])[:5]
        if intent == "evidence":
            best = evidence[0] if evidence else None
            advice = self._advice_for(s, lang)
            focus = self._metric_focus(message, s, lang)
            if en:
                reply = (focus + " " if focus else "") + (
                    f"{s['opportunity_records']} of {s['n_docs']} samples pass the four-gate opportunity check"
                    + (f"; the highest confidence is {best['confidence']:.2f} ({best['source']}, {best['year']})" if best else "")
                    + ". Quoted spans below are auditable; rule confidences are uncalibrated, so treat them as leads.")
            else:
                reply = (focus + " " if focus else "") + (
                    f"该场景 {s['n_docs']} 条样本中 {s['opportunity_records']} 条通过四门机会判定"
                    + (f"，最高置信度 {best['confidence']:.2f}（{best['source']}，{best['year']}）" if best else "")
                    + "。下面是可核查的原文证据，规则置信度未经人工校准，请当线索而不是概率。"
                )
        elif intent == "risk":
            if en:
                advice = (f"The main risk for {label}: feasibility {s['feasibility']:.2f}, only {s['n_docs']} samples, "
                          f"route '{self.route(s['route'], lang)}' — validate small before committing budget.")
                reply = "Risks by impact: buildability, sample representativeness, source bias, uncalibrated confidence."
            else:
                advice = (
                    f"『{name}』最大的风险是：可行性 {s['feasibility']:.2f}、样本 {s['n_docs']} 条、route「{s['route']}」；"
                    "它更适合先做小范围验证，而不是直接排预算。"
                )
                reply = "风险按影响排序如下：可落地性、样本代表性、来源偏差、置信度未校准。"
        elif intent == "action":
            advice = self._advice_for(s, lang)
            reply = ("One core recommendation, the detailed data and concrete next steps are below." if en
                     else "下面给出一条核心建议、详细数据与可执行的下一步。")
        else:
            advice = self._advice_for(s, lang)
            if en:
                reply = (f"{label} currently ranks #{s['rank']} (opportunity {s['opportunity']:.1f}); demand "
                         f"{s['demand']:.2f}, supply gap {s['gap']:.2f}, feasibility {s['feasibility']:.2f}, "
                         f"business value {s['value']:.2f}.")
            else:
                reply = (
                    f"『{name}』当前综合排名第 {s['rank']}（机会分 {s['opportunity']:.1f}），"
                    f"需求强度 {s['demand']:.2f}、供给缺口 {s['gap']:.2f}、可行性 {s['feasibility']:.2f}、商业价值 {s['value']:.2f}。"
                )
        chips = ([f"Compare {label} and the #1", "What is its biggest risk?",
                  "Give me a 2-week PoC plan", "Show its evidence"] if en else
                 [f"对比 {name} 和第 1 名", "它最大的风险是什么？", "给我一个 2 周 PoC 方案", "看它的证据摘录"])
        heading = (f"{label} · evidence and action plan" if en else f"{name} · 证据与行动建议")
        return {
            "kind": "scenario",
            "reply": reply,
            "advice": advice,
            "scenarios": [name],
            "metrics": {name: self._metric(s)},
            "ranking": [self._rank_row(x) for x in self.ranked[:5]],
            "evidence": evidence,
            "actions": self._actions_for(s, lang),
            "risks": self._risks(s, lang),
            "chips": chips,
            "heading": heading,
        }

    def _compare(self, a: str, b: str, lang: str = "zh") -> dict:
        en = self._le(lang)
        sa, sb = self.scenarios[a], self.scenarios[b]
        stronger = a if sa["opportunity"] >= sb["opportunity"] else b
        easier = a if sa["feasibility"] >= sb["feasibility"] else b
        la, lb = self.display(a, lang), self.display(b, lang)
        if en:
            advice = (f"{la} scores {sa['opportunity']:.1f} vs {lb} {sb['opportunity']:.1f}; "
                      f"{self.display(stronger, lang)} is stronger on score while "
                      f"{self.display(easier, lang)} is easier to build (feasibility "
                      f"{self.scenarios[easier]['feasibility']:.2f}).")
            reply = ("Four-dimension scores and evidence for both scenarios are below. A high opportunity score "
                     "means worth exploring, not ready to fund.")
            metric_label = "Metric"
        else:
            advice = (
                f"『{a}』机会分 {sa['opportunity']:.1f} vs『{b}』{sb['opportunity']:.1f}；"
                f"分数上『{stronger}』更强，可落地性上『{easier}』更容易（可行性 {self.scenarios[easier]['feasibility']:.2f}）。"
            )
            reply = "两个场景的四维评分与证据对比如下。注意：机会分高只说明值得看，不代表可立即投入。"
            metric_label = "指标"
        rows = [
            {metric_label: "Rank" if en else "综合排名",
             a: f"#{sa['rank']}" if en else f"第 {sa['rank']} 名",
             b: f"#{sb['rank']}" if en else f"第 {sb['rank']} 名"},
            {metric_label: "Opportunity" if en else "机会总分", a: f"{sa['opportunity']:.1f}", b: f"{sb['opportunity']:.1f}"},
            {metric_label: "Demand" if en else "需求强度", a: f"{sa['demand']:.2f}", b: f"{sb['demand']:.2f}"},
            {metric_label: "Supply gap" if en else "供给缺口", a: f"{sa['gap']:.2f}", b: f"{sb['gap']:.2f}"},
            {metric_label: "Feasibility" if en else "技术可行性", a: f"{sa['feasibility']:.2f}", b: f"{sb['feasibility']:.2f}"},
            {metric_label: "Business value" if en else "商业价值", a: f"{sa['value']:.2f}", b: f"{sb['value']:.2f}"},
            {metric_label: "Samples" if en else "样本量",
             a: f"{sa['n_docs']}" if en else f"{sa['n_docs']} 条",
             b: f"{sb['n_docs']}" if en else f"{sb['n_docs']} 条"},
            {metric_label: "Route" if en else "建议路线",
             a: self.route(sa["route"], lang), b: self.route(sb["route"], lang)},
        ]
        actions = (["Prototype the easier scenario (higher feasibility) and position the stronger one for differentiation.",
                    "Pick three evidence quotes per line for user validation, then choose one after two weeks."] if en else
                   [f"用『{easier}』做快速原型（可行性更高），用『{stronger}』做差异化定位。",
                    "两条线各挑 3 条证据做用户验证，两周后按真实反馈二选一。"])
        chips = ([f"Evidence for {la}", f"Evidence for {lb}", "Give me a 2-week PoC plan",
                  "Which scenario should we prioritise?"] if en else
                 [f"{a} 的证据", f"{b} 的证据", "给我一个 2 周 PoC 方案", "哪个场景最值得优先做？"])
        heading = (f"Comparison: {la} vs {lb}" if en else f"对比：{a} vs {b}")
        return {
            "kind": "compare",
            "reply": reply,
            "advice": advice,
            "scenarios": [a, b],
            "metrics": {a: self._metric(sa), b: self._metric(sb)},
            "comparison": rows,
            "ranking": [],
            "evidence": (sa.get("evidence", [])[:2] + sb.get("evidence", [])[:2]),
            "actions": actions,
            "risks": self._risks(sa, lang),
            "chips": chips,
            "heading": heading,
        }

    def _evidence_overview(self, lang: str = "zh") -> dict:
        en = self._le(lang)
        pool = []
        for s in self.ranked:
            pool.extend([(s["name"], e) for e in s.get("evidence", [])[:2]])
        pool.sort(key=lambda item: item[1]["confidence"], reverse=True)
        top = pool[:5]
        if en:
            advice = (f"{self.meta['evidence_records']:,} rule-based evidence reviews in total, "
                      f"{self.meta['evidence_opportunities']} pass the four-gate opportunity check; "
                      f"the highest confidence is {top[0][1]['confidence']:.2f} "
                      f"({self.display(top[0][0], lang)}).")
            reply = ("Evidence chunks across scenarios are listed by confidence below; use them as a starting "
                     "point for manual review and interview guides.")
            actions = ["Pick three of these quotes for a user-interview guide.",
                       "Calibrate probabilities only after 70+ human-labelled samples."]
            chips = ["Which scenario should we prioritise?", "Show evidence for Security, Compliance & Privacy",
                     "Give me a 2-week PoC plan"]
            heading = "Cross-scenario evidence excerpts"
        else:
            advice = (
                f"全库共 {self.meta['evidence_records']:,} 条规则证据审查，其中 {self.meta['evidence_opportunities']} 条通过四门机会判定；"
                f"最高置信度 {top[0][1]['confidence']:.2f}（{top[0][0]}）。"
            )
            reply = "下面按置信度列出跨场景的证据切片，可作为人工复核与访谈提纲的起点。"
            actions = ["从这些证据里挑 3 条做用户访谈提纲。", "人工标注 70 条以上后再谈校准概率。"]
            chips = ["哪个场景最值得优先做？", "看安全合规与隐私的证据", "给我一个 2 周 PoC 方案"]
            heading = "跨场景证据摘录"
        return {
            "kind": "evidence",
            "reply": reply,
            "advice": advice,
            "scenarios": [name for name, _ in top[:3]],
            "metrics": {name: self._metric(self.scenarios[name]) for name, _ in top[:2]},
            "ranking": [],
            "evidence": [dict(item, scenario=name) for name, item in top],
            "actions": actions,
            "risks": self._risks(None, lang),
            "chips": chips,
            "heading": heading,
        }

    # ---------------------------------------------------------------- helpers
    def _metric(self, s: dict) -> dict:
        return {
            "name": s["name"], "rank": s["rank"], "n_docs": s["n_docs"], "share": s["share"],
            "demand": s["demand"], "gap": s["gap"], "feasibility": s["feasibility"],
            "value": s["value"], "opportunity": s["opportunity"],
            "supply_maturity": s["supply_maturity"], "route": s["route"],
            "need_rate": s["need_rate"], "wtp_rate": s["wtp_rate"], "value_rate": s["value_rate"],
            "urgency_rate": s["urgency_rate"], "growth_slope": s["growth_slope"],
            "source_entropy": s["source_entropy"], "answer_rate": s["answer_rate"],
            "repo_n": s["repo_n"], "repo_stars_sum": s["repo_stars_sum"],
            "paper_n": s["paper_n"], "show_n": s["show_n"], "product_n": s["product_n"],
            "barrier": s["barrier"], "top_sources": s["top_sources"],
            "opportunity_records": s["opportunity_records"],
        }

    @staticmethod
    def _rank_row(s: dict) -> dict:
        return {"rank": s["rank"], "scenario": s["name"], "opportunity": s["opportunity"],
                "demand": s["demand"], "gap": s["gap"], "feasibility": s["feasibility"],
                "value": s["value"], "n_docs": s["n_docs"], "route": s["route"]}

    def _metric_focus(self, text: str, s: dict, lang: str = "zh") -> str:
        text = text or ""
        en = self._le(lang)
        if any(w in text for w in ("价值", "付费", "商业", "value", "pay", "commercial")):
            return (f"Business value is {s['value']:.2f}, driven by willingness-to-pay wtp_rate "
                    f"{s['wtp_rate']:.2f} and value signal value_rate {s['value_rate']:.2f}; "
                    f"with only {s['n_docs']} samples this needs manual validation." if en else
                    f"商业价值 {s['value']:.2f}，主要来自付费信号 wtp_rate {s['wtp_rate']:.2f}、"
                    f"价值信号 value_rate {s['value_rate']:.2f}；该场景样本 {s['n_docs']} 条，价值判断需要人工复验。")
        if any(w in text for w in ("可行性", "落地", "技术", "feasib", "build", "technical")):
            return (f"Technical feasibility {s['feasibility']:.2f} = 0.40 supply maturity + 0.20 answer rate "
                    f"+ 0.40 (1 - expert barrier); supply {s['supply_maturity']:.2f}, answer rate "
                    f"{s['answer_rate']:.2f}, barrier {s['barrier']:.2f}." if en else
                    f"技术可行性 {s['feasibility']:.2f} = 0.40 供给成熟度 + 0.20 问答解决率 + 0.40（1−专家壁垒），"
                    f"其中供给 {s['supply_maturity']:.2f}、解决率 {s['answer_rate']:.2f}、壁垒 {s['barrier']:.2f}。")
        if any(w in text for w in ("缺口", "供给", "gap", "supply")):
            return (f"Supply gap {s['gap']:.2f} = demand {s['demand']:.2f} - supply maturity "
                    f"{s['supply_maturity']:.2f}; a large gap means scarce supply, but it often comes with "
                    "harder feasibility." if en else
                    f"供给缺口 {s['gap']:.2f} = 需求强度 {s['demand']:.2f} − 供给成熟度 {s['supply_maturity']:.2f}，"
                    f"缺口大的场景通常供给稀缺，但也更容易撞上可行性门槛。")
        if any(w in text for w in ("需求", "热度", "增长", "demand", "growth")):
            return (f"Demand strength {s['demand']:.2f}, need_rate {s['need_rate']:.2f}, growth slope "
                    f"{s['growth_slope']:+.2%}, source entropy {s['source_entropy']:.2f}." if en else
                    f"需求强度 {s['demand']:.2f}，need_rate {s['need_rate']:.2f}、增长斜率 {s['growth_slope']:+.2%}、"
                    f"来源熵 {s['source_entropy']:.2f}。")
        return ""

    def _advice_for(self, s: dict, lang: str = "zh") -> str:
        en = self._le(lang)
        route = s["route"]
        name = self.display(s["name"], lang)
        if route == "红海差异化":
            return (f"Demand is strong ({s['demand']:.2f}) but supply is already mature "
                    f"({s['supply_maturity']:.2f}); don't build a general platform from scratch — use "
                    f"{name} for a vertical workflow and validate one high-frequency pain point first." if en else
                    f"需求强（{s['demand']:.2f}）但供给也成熟（{s['supply_maturity']:.2f}），别从零自研；"
                    f"用『{s['name']}』在垂直工作流做差异化，先锁定 1 个高频痛点验证。")
        if route == "联合研发/跟踪技术":
            return (f"The supply gap is the largest ({s['gap']:.2f}) but feasibility is only "
                    f"{s['feasibility']:.2f}; run a 2–4 week compliance evidence-chain PoC and let real "
                    "willingness-to-pay decide whether to continue." if en else
                    f"供给缺口最大（{s['gap']:.2f}）但可行性只有 {s['feasibility']:.2f}；"
                    "建议先做 2–4 周合规证据链 PoC，用真实付费意愿决定是否继续。")
        if route == "垂直细分验证":
            return (f"Only {s['n_docs']} samples but a relatively high value signal ({s['value']:.2f}); "
                    "pick one vertical and test purchase intent in a small scope before expanding." if en else
                    f"样本仅 {s['n_docs']} 条但价值信号较高（{s['value']:.2f}）；"
                    "选一个垂直行业做小范围付费意向测试，不要一开始铺开。")
        if s["value"] >= 0.5:
            return (f"Business value is the strongest band ({s['value']:.2f}) while demand and feasibility "
                    f"are weak ({s['feasibility']:.2f}); validate willingness-to-pay with 20–30 samples before "
                    "committing budget." if en else
                    f"商业价值信号是全场景最高档（{s['value']:.2f}），但需求与可行性偏弱（{s['feasibility']:.2f}）；"
                    "建议先用 20–30 条样本做付费意愿验证，不要按总分直接立项。")
        return (f"Opportunity score {s['opportunity']:.1f}, feasibility {s['feasibility']:.2f}; medium priority — "
                "set observation metrics and review monthly before investing core resources." if en else
                f"当前机会分 {s['opportunity']:.1f}、可行性 {s['feasibility']:.2f}；"
                "优先级中等，建议先设观察指标、每月复盘，暂不投入主力资源。")

    def _actions_for(self, s: dict, lang: str = "zh") -> list[str]:
        en = self._le(lang)
        name = self.display(s["name"], lang)
        if en:
            actions = [f"Pick 8–10 of the {s['opportunity_records']} high-confidence evidence records as a user-interview guide."]
            if s["route"] == "红海差异化":
                actions.append(f"Choose one vertical workflow and ship a demo prototype in 2 weeks that solves the single most painful step of {name}.")
            elif s["route"] == "联合研发/跟踪技术":
                actions.append("Run a 2–4 week PoC with compliance/legal (offline deployment + audit trail); use willingness-to-pay as go/no-go.")
            elif s["route"] == "垂直细分验证":
                actions.append("Lock one industry customer and test purchase intent (quote + trial) to verify the value signal.")
            else:
                actions.append("Set observation metrics (demand growth slope, supply changes) and review monthly before investing.")
            actions.append("Define validation metrics: trial conversion, willingness-to-pay, retention; review every 2–4 weeks.")
            actions.append("If three real customers do not give clear feedback within two weeks, stop investing.")
            return actions
        actions = [f"从 {s['opportunity_records']} 条高置信证据里挑 8–10 条做用户访谈提纲。"]
        if s["route"] == "红海差异化":
            actions.append(f"选 1 个垂直工作流，2 周做出可演示原型，只解决「{name}」里最痛的一步。")
        elif s["route"] == "联合研发/跟踪技术":
            actions.append("和合规/法务一起做 2–4 周 PoC（离线部署 + 审计留痕），用是否愿意付费做 go/no-go。")
        elif s["route"] == "垂直细分验证":
            actions.append("锁定 1 个行业客户做付费意向测试（报价 + 试用），验证价值信号是否真实。")
        else:
            actions.append("设置观察指标（需求增长斜率、供给变化），每月复盘后再决定是否投入。")
        actions.append("设定验证指标：试用转化率 / 付费意愿 / 留存；2–4 周复盘一次。")
        actions.append("若两周内拿不到 3 个真实客户的明确反馈，停止加码。")
        return actions

    def _risks(self, s: dict | None, lang: str = "zh") -> list[str]:
        meta = self.meta
        if self._le(lang):
            risks = [
                f"Evidence is rule-shadow judged ({meta['evidence_mode']} mode); confidences are not temperature-calibrated (calibration=pending).",
                f"No human gold labels yet ({meta['gold_records']} records); scenario labels come from weak supervision plus a classifier.",
                f"Source bias: HHI={meta['source_hhi']:.2f}; Hacker News/GitHub dominate, so shares are not true market shares.",
                "Supply maturity is proxied by repos/stars/papers/Show HN; willingness-to-pay is a text signal, not actual payment.",
            ]
            if s is not None:
                if s["n_docs"] < 90:
                    risks.append(f"Only {s['n_docs']} samples for this scenario — directional judgement only.")
                if s["feasibility"] < 0.45:
                    risks.append(f"Feasibility {s['feasibility']:.2f} is low; compliance/data/integration barriers require joint R&D.")
            return risks
        risks = [
            f"证据为规则影子判定（{meta['evidence_mode']} 模式），置信度未经温度校准（calibration=pending）。",
            f"尚无人工金标（{meta['gold_records']} 条），场景标签来自弱监督词典 + 分类器扩展。",
            f"来源偏差：HHI={meta['source_hhi']:.2f}，HackerNews/GitHub 占比高，不能当作真实市场占比。",
            "供给成熟度用仓库/Star/论文/Show HN 近似，不等于技术成熟度；付费意愿来自文本信号，不等同真实付费。",
        ]
        if s is not None:
            if s["n_docs"] < 90:
                risks.append(f"该场景样本仅 {s['n_docs']} 条，结论只适合作方向性判断。")
            if s["feasibility"] < 0.45:
                risks.append(f"技术可行性 {s['feasibility']:.2f} 偏低，存在合规/数据/集成门槛，落地需联合研发。")
        return risks

    # ---------------------------------------------------------------- report
    def report_context(self, answer: dict, lang: str | None = None) -> dict:
        """Normalized structure shared by the PDF/print report."""
        lang = lang or answer.get("lang") or "en"
        en = self._le(lang)
        names = answer.get("scenarios") or []
        metrics = answer.get("metrics") or {}
        metrics_rows = []
        if names:
            first = metrics.get(names[0])
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
                        ("Recommended route", self.route(first["route"], lang)),
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
        }
