# -*- coding: utf-8 -*-
"""Deterministic product features for OpenECRS: wizard, PoC plan, portfolio.

Every number in this module comes from ``agent_tools.ScenarioData`` or from
plain arithmetic defined here (and labelled heuristic where it is an estimate).
The LLM is used only to rewrite a computed result as prose: the
``build_*_messages`` helpers produce a strict-JSON prompt and
``parse_narrative`` validates the model output.

Public API
----------
wizard(prefs, data)                -> {"constraints": {...}, "shortlist": [top 3]}
poc_plan(scenario, weeks, team_size, data, lang)
                                   -> {"scenario", "weeks", "milestones", ...}
portfolio(team_size, weeks, budget_usd, data, lang)
                                   -> {"picks", "excluded", "total_effort", ...}
build_wizard_messages(payload, lang, role)
build_poc_messages(payload, lang, role)
build_portfolio_messages(payload, lang, role)
                                   -> [{"role": "system", ...}, {"role": "user", ...}]
parse_narrative(text)              -> {"summary", "bullets", "risks"} | None
normalize_weeks(value)             -> 2 | 4 | 8

Scoring model used by ``wizard`` (deterministic, documented in constraints)::

    score = (1 - w) * opportunity + w * feasibility * 100 + goal_bonus
    w     = feasibility weight, raised for low risk appetite, small teams and
            small budgets (and by role), clamped to [0.15, 0.75]
    bonus = up to 20 points when the goal text matches the scenario name,
            one of its aliases, or its recommended route

``poc_plan`` returns ``{"error": ...}`` for an unknown scenario; every other
function is tolerant of partial input so the HTTP layer can stay thin.
"""
from __future__ import annotations

import json
import re
import statistics

from agent_tools import NAME_ALIASES, ScenarioData, display_route
from scenario_names import ROUTE_NAMES_EN, SCENARIO_NAMES_EN

__all__ = [
    "ROLES",
    "RISK_LEVELS",
    "POC_WEEKS",
    "normalize_weeks",
    "wizard",
    "poc_plan",
    "portfolio",
    "build_wizard_messages",
    "build_poc_messages",
    "build_portfolio_messages",
    "parse_narrative",
]

ROLES = ("founder", "enterprise", "investor", "pm")
RISK_LEVELS = ("low", "medium", "high")
POC_WEEKS = (2, 4, 8)

ROLE_LABELS = {
    "founder": {"en": "founder", "zh": "创业者"},
    "enterprise": {"en": "enterprise team", "zh": "企业团队"},
    "investor": {"en": "investor", "zh": "投资人"},
    "pm": {"en": "product manager", "zh": "产品经理"},
}

# Base feasibility weight per role: a founder needs something buildable, an
# investor is mostly chasing opportunity size.
_ROLE_FEASIBILITY = {"founder": 0.42, "enterprise": 0.38, "investor": 0.28, "pm": 0.35}

_RISK_ADJUST = {"low": 0.15, "medium": 0.0, "high": -0.10}


# ---------------------------------------------------------------- utilities
def _lang(value) -> str:
    return "zh" if str(value or "").strip().lower().startswith("zh") else "en"


def _role(value) -> str:
    text = str(value or "").strip().lower()
    if text in ROLES:
        return text
    aliases = {
        "found": "founder", "startup": "founder", "entrepreneur": "founder",
        "enterpris": "enterprise", "company": "enterprise", "b2b": "enterprise",
        "invest": "investor", "vc": "investor", "fund": "investor",
        "pm": "pm", "product": "pm",
    }
    for needle, role in aliases.items():
        if needle in text:
            return role
    return "founder"


def _as_int(value, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ensure_data(data) -> ScenarioData:
    if isinstance(data, ScenarioData):
        return data
    if data is None:
        return ScenarioData()
    if isinstance(data, dict):
        return ScenarioData(data)
    if hasattr(data, "scenarios") and hasattr(data, "resolve"):
        return data  # duck-typed stand-in (useful in tests)
    raise TypeError("data must be an agent_tools.ScenarioData instance or dict")


def _name_en(name: str) -> str:
    return SCENARIO_NAMES_EN.get(name, name)


def _route_display(route: str, lang: str) -> str:
    if not route:
        return ""
    return display_route(route, lang)


def _meta_caveat(data: ScenarioData, lang: str) -> str:
    meta = getattr(data, "meta", {}) or {}
    gold = _as_int(meta.get("gold_records"), 0)
    calibration = str(meta.get("calibration") or "").strip().lower()
    if gold == 0 or calibration in ("pending", ""):
        if lang == "zh":
            return "证据为规则影子审查、置信度未校准（无人工金标）。"
        return "Evidence is rule-shadow reviewed and uncalibrated (no human gold labels)."
    if lang == "zh":
        return "证据来源以 Hacker News / GitHub 为主，占比只能作方向性参考。"
    return "Sources are HN/GitHub heavy, so evidence shares are directional only."


# ---------------------------------------------------------------- wizard
def _wizard_feasibility_weight(role: str, risk: str, team: int, budget: int,
                               horizon: int) -> float:
    weight = _ROLE_FEASIBILITY[role]
    weight += _RISK_ADJUST.get(risk, 0.0)
    if team <= 2:
        weight += 0.08
    elif team <= 4:
        weight += 0.04
    elif team >= 10:
        weight -= 0.05
    if budget <= 50_000:
        weight += 0.08
    elif budget <= 150_000:
        weight += 0.04
    elif budget >= 500_000:
        weight -= 0.05
    if horizon <= 4:
        weight += 0.04
    elif horizon >= 16:
        weight -= 0.03
    return round(min(0.75, max(0.15, weight)), 4)


def _alias_label(alias: str, name: str, lang: str) -> str:
    if lang == "en" and not alias.isascii():
        return _name_en(name)
    return alias if lang == "zh" else alias.lower()


def _match_name_tokens(text: str, name: str, name_en: str) -> bool:
    """True when the goal contains the scenario name or a meaningful token of it."""
    if name and name in text:
        return True
    if name_en and name_en.lower() in text:
        return True
    for token in re.findall(r"[a-z0-9]{3,}", text):
        if name_en and token in name_en.lower():
            return True
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if name and run in name:
            return True
    return False


def _goal_match(goal: str, scenario: dict, lang: str) -> tuple[list[str], float]:
    """Match the free-text goal against a scenario name, aliases and its route."""
    text = (goal or "").strip().lower()
    if not text:
        return [], 0.0
    name = scenario["name"]
    name_en = scenario.get("name_en") or _name_en(name)
    hits: list[str] = []
    score = 0.0
    if _match_name_tokens(text, name, name_en):
        hits.append(name_en if lang == "en" else name)
        score = 15.0
    else:
        for alias in NAME_ALIASES.get(name, []):
            if alias.lower() in text:
                hits.append(_alias_label(alias, name, lang))
                score = 12.0
                break
    route = scenario.get("route") or ""
    route_en = ROUTE_NAMES_EN.get(route, route)
    if (route_en and route_en.lower() in text) or (route and route in text):
        score += 5.0
        label = _route_display(route, lang)
        if label:
            hits.append(label)
    seen: list[str] = []
    for hit in hits:
        if hit and hit not in seen:
            seen.append(hit)
    return seen[:3], min(20.0, score)


def _wizard_fit_reasons(s: dict, lang: str, role: str, weight: float,
                        hits: list[str], team: int, rank: int) -> list[str]:
    opportunity = _as_float(s.get("opportunity"))
    feasibility = _as_float(s.get("feasibility"))
    gap = _as_float(s.get("gap"))
    route = _route_display(s.get("route") or "", lang)
    role_label = ROLE_LABELS[role][lang]
    if lang == "zh":
        reasons = [f"机会总分 {opportunity:.2f}/100，在证据库 12 个场景中排第 {rank} 名。"]
        if weight >= 0.5:
            reasons.append(f"作为{role_label}，可行性 {feasibility:.2f}，"
                           f"{team} 人小团队有机会独立做出来。")
        else:
            reasons.append(f"作为{role_label}，供给缺口 {gap:.2f} 与可行性 "
                           f"{feasibility:.2f}，收益与投入之间较均衡。")
        if hits:
            reasons.append("命中你的目标关键词：" + "、".join(hits[:2]) + "。")
        else:
            reasons.append(f"建议路线：{route}。")
        return reasons[:3]
    reasons = [f"Opportunity {opportunity:.2f}/100, evidence-base rank #{rank} of 12."]
    if weight >= 0.5:
        reasons.append(f"As a {role_label}, feasibility {feasibility:.2f} keeps a "
                       f"{team}-person team within reach.")
    else:
        reasons.append(f"As a {role_label}, supply gap {gap:.2f} and feasibility "
                       f"{feasibility:.2f} balance upside against effort.")
    if hits:
        reasons.append("Matches your goal keywords: " + ", ".join(hits[:2]) + ".")
    else:
        reasons.append(f"Suggested route: {route}.")
    return reasons[:3]


def _wizard_watchouts(s: dict, lang: str, feasibility: float,
                      median_feasibility: float, data: ScenarioData) -> list[str]:
    barrier = _as_float(s.get("barrier"))
    gap = _as_float(s.get("gap"))
    if lang == "zh":
        out = []
        if barrier >= 0.55:
            out.append(f"采用门槛 {barrier:.2f} 偏高，集成与组织变革可能吃掉时间。")
        else:
            out.append(f"采用门槛 {barrier:.2f}，需尽早确认流程改造意愿与预算负责人。")
        if feasibility < median_feasibility:
            out.append(f"可行性 {feasibility:.2f} 低于 12 个场景中位数，建议先收敛到一个工作流。")
        elif gap < 0.15:
            out.append(f"供给缺口仅 {gap:.2f}，赛道拥挤，需靠执行差异化。")
        else:
            out.append(f"可行性 {feasibility:.2f} 只是建设前代理指标，需用真实试点校准。")
        out.append(_meta_caveat(data, lang))
        return out[:3]
    out = []
    if barrier >= 0.55:
        out.append(f"High adoption barrier ({barrier:.2f}): integration and change management can eat the timeline.")
    else:
        out.append(f"Adoption barrier {barrier:.2f}: confirm workflow change appetite and the budget owner early.")
    if feasibility < median_feasibility:
        out.append(f"Feasibility {feasibility:.2f} is below the 12-scenario median; scope down to one workflow first.")
    elif gap < 0.15:
        out.append(f"Thin supply gap ({gap:.2f}): crowded space, differentiate on execution.")
    else:
        out.append(f"Feasibility {feasibility:.2f} is a pre-build proxy only; calibrate with a real pilot.")
    out.append(_meta_caveat(data, lang))
    return out[:3]


def wizard(prefs: dict, data: ScenarioData | None = None) -> dict:
    """Rank the 12 scenarios for a user profile and return the top 3.

    ``prefs`` accepts role / goal / team_size / budget_usd / horizon_weeks /
    risk / lang. Unknown or missing values fall back to safe defaults, so the
    HTTP layer can pass the raw request body.
    """
    prefs = prefs if isinstance(prefs, dict) else {}
    data = _ensure_data(data)
    lang = _lang(prefs.get("lang"))
    role = _role(prefs.get("role"))
    goal = str(prefs.get("goal") or "").strip()[:400]
    team = _as_int(prefs.get("team_size"), 3, 1, 50)
    horizon = _as_int(prefs.get("horizon_weeks"), 8, 1, 52)
    budget = _as_int(prefs.get("budget_usd"), 0, 0)
    if budget <= 0:
        budget = team * horizon * 8_000
    risk = str(prefs.get("risk") or "medium").strip().lower()
    if risk not in RISK_LEVELS:
        risk = "medium"

    weight = _wizard_feasibility_weight(role, risk, team, budget, horizon)
    median_feasibility = statistics.median(
        _as_float(s.get("feasibility")) for s in data.scenarios.values()
    )

    scored = []
    for name, s in data.scenarios.items():
        opportunity = _as_float(s.get("opportunity"))
        feasibility = _as_float(s.get("feasibility"))
        hits, bonus = _goal_match(goal, s, lang)
        raw = (1.0 - weight) * opportunity + weight * feasibility * 100.0 + bonus
        scored.append({
            "id": name,
            "score": round(min(100.0, max(0.0, raw)), 2),
            "opportunity": opportunity,
            "feasibility": feasibility,
            "hits": hits,
        })
    scored.sort(key=lambda row: (-row["score"], -row["opportunity"],
                                 -row["feasibility"], row["id"]))

    shortlist = []
    for row in scored[:3]:
        name = row["id"]
        s = data.scenarios[name]
        rank = _as_int(s.get("rank"), 0)
        shortlist.append({
            "id": name,
            "name": data.display(name, lang),
            "name_en": _name_en(name),
            "score": row["score"],
            "opportunity": round(row["opportunity"], 2),
            "feasibility": round(row["feasibility"], 4),
            "gap": round(_as_float(s.get("gap")), 4),
            "route": _route_display(s.get("route") or "", lang),
            "fit_reasons": _wizard_fit_reasons(s, lang, role, weight,
                                               row["hits"], team, rank),
            "watchouts": _wizard_watchouts(s, lang, row["feasibility"],
                                           median_feasibility, data),
        })

    constraints = {
        "role": role,
        "goal": goal,
        "team_size": team,
        "budget_usd": budget,
        "horizon_weeks": horizon,
        "risk": risk,
        "lang": lang,
        "feasibility_weight": weight,
        "opportunity_weight": round(1.0 - weight, 4),
        "goal_bonus_max": 20.0,
        "top_n": 3,
        "score_formula": "(1-w)*opportunity + w*feasibility*100 + goal_bonus",
        "heuristic": True,
    }
    return {"constraints": constraints, "shortlist": shortlist}


# ---------------------------------------------------------------- PoC plan
_MILESTONES = {
    2: {
        "en": [
            {"week": 1, "title": "Scope & baseline",
             "deliverables": ["Pick one workflow and define the success metric",
                              "Build a small, documented evaluation set"],
             "exit_criteria": "Metric, baseline and data scope signed off by the decision owner"},
            {"week": 2, "title": "Thin-slice build",
             "deliverables": ["End-to-end thin slice on the chosen workflow",
                              "Automated evaluation run against the baseline"],
             "exit_criteria": "Thin slice runs end-to-end on held-in data without manual glue"},
            {"week": 2, "title": "Evaluate & decide",
             "deliverables": ["Scorecard vs baseline",
                              "Go / adjust / stop recommendation"],
             "exit_criteria": "Decision memo shared and the next step agreed"},
        ],
        "zh": [
            {"week": 1, "title": "范围与基线",
             "deliverables": ["选定一个工作流并写清成功指标",
                              "准备一小份有文档的评测集"],
             "exit_criteria": "指标、基线与数据范围由决策人确认"},
            {"week": 2, "title": "最小闭环",
             "deliverables": ["在选定工作流上打通端到端最小闭环",
                              "对照基线跑一遍自动评测"],
             "exit_criteria": "最小闭环在留出数据上无需人工拼接即可运行"},
            {"week": 2, "title": "评估与决策",
             "deliverables": ["对照基线的评分卡",
                              "继续 / 调整 / 停止 的建议"],
             "exit_criteria": "决策备忘已同步并确定下一步"},
        ],
    },
    4: {
        "en": [
            {"week": 1, "title": "Scope & baseline",
             "deliverables": ["Pick one workflow and define the success metric",
                              "Build a small, documented evaluation set"],
             "exit_criteria": "Metric, baseline and data scope signed off by the decision owner"},
            {"week": 2, "title": "Thin-slice build",
             "deliverables": ["End-to-end thin slice on the chosen workflow",
                              "Integration spike on the riskiest dependency"],
             "exit_criteria": "Thin slice runs end-to-end on held-in data without manual glue"},
            {"week": 3, "title": "Hardening & evaluation",
             "deliverables": ["Failure-mode review and fixes",
                              "Evaluation report with per-case results",
                              "Measured throughput and cost re-estimate"],
             "exit_criteria": "Evaluation report reviewed; blockers and owners listed"},
            {"week": 4, "title": "Pilot readout & decision",
             "deliverables": ["Pilot readout with the evaluation owner",
                              "Build / extend / stop recommendation",
                              "Next-phase scope and budget draft"],
             "exit_criteria": "Decision recorded and next-phase owner named"},
        ],
        "zh": [
            {"week": 1, "title": "范围与基线",
             "deliverables": ["选定一个工作流并写清成功指标",
                              "准备一小份有文档的评测集"],
             "exit_criteria": "指标、基线与数据范围由决策人确认"},
            {"week": 2, "title": "最小闭环",
             "deliverables": ["在选定工作流上打通端到端最小闭环",
                              "对风险最高的依赖做集成验证"],
             "exit_criteria": "最小闭环在留出数据上无需人工拼接即可运行"},
            {"week": 3, "title": "加固与评估",
             "deliverables": ["失败模式复盘与修复",
                              "含逐条结果的评测报告",
                              "基于实测吞吐重估成本与工作量"],
             "exit_criteria": "评测报告已评审，阻塞项与责任人明确"},
            {"week": 4, "title": "试点复盘与决策",
             "deliverables": ["与评测负责人完成试点复盘",
                              "继续 / 扩展 / 停止 的建议",
                              "下一阶段范围与预算草案"],
             "exit_criteria": "决策已记录并指定下一阶段负责人"},
        ],
    },
    8: {
        "en": [
            {"week": 1, "title": "Scope & baseline",
             "deliverables": ["Pick one workflow and define the success metric",
                              "Build a small, documented evaluation set"],
             "exit_criteria": "Metric, baseline and data scope signed off by the decision owner"},
            {"week": 2, "title": "Thin-slice build",
             "deliverables": ["End-to-end thin slice on the chosen workflow",
                              "Integration spike on the riskiest dependency"],
             "exit_criteria": "Thin slice runs end-to-end on held-in data without manual glue"},
            {"week": 4, "title": "Evaluation & hardening",
             "deliverables": ["Failure-mode review and fixes",
                              "Evaluation report with per-case results",
                              "Measured throughput and cost re-estimate"],
             "exit_criteria": "Evaluation report reviewed; blockers and owners listed"},
            {"week": 6, "title": "Limited pilot",
             "deliverables": ["Limited pilot with a small user group",
                              "Instrumentation for usage and task success",
                              "Weekly issue triage and fix list"],
             "exit_criteria": "Pilot users onboarded and usage data flowing"},
            {"week": 8, "title": "Readout & roadmap",
             "deliverables": ["Pilot readout vs the baseline",
                              "Build / extend / stop decision",
                              "Roadmap and budget for the next phase"],
             "exit_criteria": "Roadmap approved and funded for the next window"},
        ],
        "zh": [
            {"week": 1, "title": "范围与基线",
             "deliverables": ["选定一个工作流并写清成功指标",
                              "准备一小份有文档的评测集"],
             "exit_criteria": "指标、基线与数据范围由决策人确认"},
            {"week": 2, "title": "最小闭环",
             "deliverables": ["在选定工作流上打通端到端最小闭环",
                              "对风险最高的依赖做集成验证"],
             "exit_criteria": "最小闭环在留出数据上无需人工拼接即可运行"},
            {"week": 4, "title": "评估与加固",
             "deliverables": ["失败模式复盘与修复",
                              "含逐条结果的评测报告",
                              "基于实测吞吐重估成本与工作量"],
             "exit_criteria": "评测报告已评审，阻塞项与责任人明确"},
            {"week": 6, "title": "小范围试点",
             "deliverables": ["小范围用户试点",
                              "埋点采集使用与任务成功数据",
                              "每周问题分诊与修复清单"],
             "exit_criteria": "试点用户完成入驻，使用数据开始回流"},
            {"week": 8, "title": "复盘与路线图",
             "deliverables": ["对照基线完成试点复盘",
                              "继续 / 扩展 / 停止 的决策",
                              "下一阶段的路线图与预算"],
             "exit_criteria": "路线图获批并为下一周期立项"},
        ],
    },
}

_SCENARIO_STAKEHOLDER = {
    "安全合规与隐私": {"en": "Security & privacy reviewer", "zh": "安全与隐私评审"},
    "多智能体与任务编排": {"en": "Platform engineer", "zh": "平台工程师"},
    "知识管理与文档问答": {"en": "Knowledge manager", "zh": "知识管理负责人"},
    "编程与代码智能": {"en": "Developer productivity lead", "zh": "研发效能负责人"},
    "办公协作与会议效率": {"en": "Workplace IT owner", "zh": "办公 IT 负责人"},
    "垂直行业应用": {"en": "Industry domain expert", "zh": "行业领域专家"},
    "客户服务与智能客服": {"en": "Support operations lead", "zh": "客服运营负责人"},
    "浏览器与工作流自动化": {"en": "Process owner", "zh": "流程负责人"},
    "语音与实时交互": {"en": "Conversation designer", "zh": "对话设计"},
    "内容创作与营销": {"en": "Brand / editorial lead", "zh": "品牌与内容负责人"},
    "教育学习与知识辅导": {"en": "Learning designer", "zh": "教学设计"},
    "数据分析与商业洞察": {"en": "Analytics owner", "zh": "数据分析负责人"},
}


def normalize_weeks(value) -> int:
    """Normalise an arbitrary duration to the supported PoC lengths {2, 4, 8}."""
    weeks = _as_int(value, 2, minimum=0)
    if weeks <= 3:
        return 2
    if weeks <= 6:
        return 4
    return 8


def _poc_roles(name: str, team: int, lang: str) -> list[str]:
    stakeholder = _SCENARIO_STAKEHOLDER.get(name, {"en": "Domain expert", "zh": "领域专家"})
    if lang == "zh":
        roles = ["产品负责人", "技术负责人 / 架构师"]
        if team <= 2:
            roles.append("全栈 / 算法工程师（兼评测）")
        else:
            roles.append("算法 / Prompt 工程师")
            if team >= 4:
                roles.append("后端 / 平台工程师")
        roles.extend([stakeholder["zh"], "评测 / 数据管理员"])
    else:
        roles = ["Product owner", "Tech lead / architect"]
        if team <= 2:
            roles.append("Full-stack / ML engineer (also owns evaluation)")
        else:
            roles.append("ML / prompt engineer")
            if team >= 4:
                roles.append("Backend / platform engineer")
        roles.extend([stakeholder["en"], "Evaluation / data steward"])
    return list(dict.fromkeys(roles))


def _poc_metrics(weeks: int, s: dict, lang: str) -> list[str]:
    opportunity = _as_float(s.get("opportunity"))
    feasibility = _as_float(s.get("feasibility"))
    gap = _as_float(s.get("gap"))
    samples = _as_int(s.get("n_docs"), 0)
    if lang == "zh":
        items = [
            f"评测集任务成功率（基线：机会 {opportunity:.2f}、可行性 {feasibility:.2f}）",
            f"供给缺口 {gap:.2f}：结果是否明显优于现有替代方案",
            f"可行性门 {feasibility:.2f}：窗口内遇到的集成阻塞数量",
        ]
        if weeks >= 4:
            items[0] = (f"评测集任务成功率，对照手动基线（证据：机会 {opportunity:.2f}、"
                        f"可行性 {feasibility:.2f}、样本 {samples} 条）")
            items.append("首次可用输出的时间成本 vs 手动流程")
        if weeks >= 8:
            items.append("单个成功任务的实测成本（非估算）")
        return items[:5]
    items = [
        f"Task success rate on the evaluation set (baseline: opportunity {opportunity:.2f}, "
        f"feasibility {feasibility:.2f})",
        f"Supply gap {gap:.2f}: does the output clearly beat the current workaround?",
        f"Feasibility gate {feasibility:.2f}: count integration blockers hit inside the window",
    ]
    if weeks >= 4:
        items[0] = (f"Task success rate on the evaluation set vs the manual baseline "
                    f"(evidence: opportunity {opportunity:.2f}, feasibility {feasibility:.2f}, "
                    f"{samples} samples)")
        items.append("Time to first useful output vs the manual workflow")
    if weeks >= 8:
        items.append("Measured cost per successful task (not modelled)")
    return items[:5]


def _poc_compliance(name: str, weeks: int, lang: str) -> list[str]:
    if lang == "zh":
        items = [
            "试点数据放在有访问控制的存储中，记录每次读取与导出。",
            "入库前脱敏或合成个人与客户数据。",
            "记录 Prompt 与模型版本，确保结果可复现。",
        ]
        if weeks >= 4:
            if name == "安全合规与隐私":
                items.append("使用受限沙箱凭据；生产密钥不进入 Prompt。")
            else:
                items.append("窗口结束后删除试点数据，除非负责人书面确认保留。")
        return items[:4]
    items = [
        "Keep pilot data in an access-controlled store; log every read and export.",
        "Redact or synthesise personal and customer data before indexing.",
        "Record prompt and model versions so every result is reproducible.",
    ]
    if weeks >= 4:
        if name == "安全合规与隐私":
            items.append("Use scoped sandbox credentials; keep production secrets out of prompts.")
        else:
            items.append("Delete pilot data at the end of the window unless retention is signed off.")
    return items[:4]


def _poc_risks(weeks: int, s: dict, lang: str) -> list[str]:
    barrier = _as_float(s.get("barrier"))
    feasibility = _as_float(s.get("feasibility"))
    gap = _as_float(s.get("gap"))
    if lang == "zh":
        risks = []
        if barrier >= 0.55:
            risks.append(f"采用门槛 {barrier:.2f} 偏高，集成与采购可能吃掉时间。")
        else:
            risks.append(f"采用门槛 {barrier:.2f}，尽早验证流程改造意愿与付费意愿。")
        if feasibility < 0.5:
            risks.append(f"可行性 {feasibility:.2f} 一般，把范围收敛到一个工作流和一个数据源。")
        else:
            risks.append(f"可行性 {feasibility:.2f} 看似可行，但证据来自规则影子审查、置信度未校准。")
        if weeks >= 4:
            if gap >= 0.3:
                risks.append(f"供给缺口 {gap:.2f} 也会吸引竞争对手，窗口可能关闭。")
            else:
                risks.append(f"供给缺口仅 {gap:.2f}，必须在工作流上做出差异，而不是拼新奇。")
        else:
            risks.append("2 周只能证明最小闭环，不等同于生产可用。")
        risks.append("成本区间是启发式估算（团队人数 × 周数 × 每人周 $4,000–8,000），不是供应商报价。")
        return risks
    risks = []
    if barrier >= 0.55:
        risks.append(f"High adoption barrier ({barrier:.2f}): integration and procurement can dominate the timeline.")
    else:
        risks.append(f"Adoption barrier {barrier:.2f}: validate workflow change and willingness to pay early.")
    if feasibility < 0.5:
        risks.append(f"Feasibility {feasibility:.2f} is modest; keep scope to one workflow and one data source.")
    else:
        risks.append(f"Feasibility {feasibility:.2f} looks workable, but evidence is rule-shadow reviewed and uncalibrated.")
    if weeks >= 4:
        if gap >= 0.3:
            risks.append(f"Supply gap {gap:.2f} also attracts competitors; the window may close.")
        else:
            risks.append(f"Thin supply gap ({gap:.2f}): differentiate on workflow, not novelty.")
    else:
        risks.append("Two weeks only proves a thin slice; it is not production readiness.")
    risks.append("Cost range is a heuristic (team size × weeks × $4,000–8,000/person-week), not a vendor quote.")
    return risks


def poc_plan(scenario: str, weeks: int, team_size: int,
             data: ScenarioData | None = None, lang: str = "en") -> dict:
    """Build a deterministic proof-of-concept plan for one scenario.

    ``weeks`` is normalised to {2, 4, 8}; milestones, effort and the cost range
    are all derived from the duration and team size (never from the LLM).
    Unknown scenarios return ``{"error": ...}`` so the HTTP layer can answer 400.
    """
    data = _ensure_data(data)
    lang = _lang(lang)
    key = data.resolve(str(scenario or ""))
    if not key:
        return {"error": f"unknown scenario: {scenario}"}
    team = _as_int(team_size, 3, 1, 50)
    duration = normalize_weeks(weeks)
    s = data.scenarios[key]

    milestones = [
        {"week": m["week"], "title": m["title"],
         "deliverables": list(m["deliverables"]),
         "exit_criteria": m["exit_criteria"]}
        for m in _MILESTONES[duration][lang]
    ]
    effort = round(duration * team * 0.6, 1)
    return {
        "scenario": {
            "id": key,
            "name": data.display(key, lang),
            "name_en": _name_en(key),
        },
        "weeks": duration,
        "team_size": team,
        "route": _route_display(s.get("route") or "", lang),
        "effort_person_weeks": effort,
        "cost_range_usd": [team * duration * 4_000, team * duration * 8_000],
        "heuristic": True,
        "cost_basis": ("team_size × weeks × $4,000–8,000 per person-week"
                       if lang == "en" else "团队人数 × 周数 × 每人周 $4,000–8,000"),
        "milestones": milestones,
        "roles": _poc_roles(key, team, lang),
        "metrics": _poc_metrics(duration, s, lang),
        "data_compliance": _poc_compliance(key, duration, lang),
        "risks": _poc_risks(duration, s, lang),
    }


# ---------------------------------------------------------------- portfolio
def portfolio(team_size: int, weeks: int, budget_usd: int,
              data: ScenarioData | None = None, lang: str = "en") -> dict:
    """Greedy, budget-aware portfolio: at most three scenarios in one window.

    Weighting shifts towards feasibility when the budget is tight relative to a
    full team window. Each pick gets a phase (one build bet, the rest are
    validation tracks) and every non-pick is listed with a reason.
    """
    data = _ensure_data(data)
    lang = _lang(lang)
    team = _as_int(team_size, 3, 1, 50)
    window = _as_int(weeks, 12, 1, 52)
    budget = _as_int(budget_usd, 0, 0)
    defaulted = budget <= 0
    if defaulted:
        budget = team * window * 8_000

    # People assigned per parallel pick if the team is split across the max 3.
    allocation = max(1, team // 3)
    cost_low = allocation * window * 4_000
    cost_high = allocation * window * 8_000
    effort_per_pick = window * allocation * 0.6
    full_window_cost = team * window * 4_000
    ratio = (budget / full_window_cost) if full_window_cost else 9.0

    weight = 0.35
    if ratio < 1.0:
        weight += 0.20
    elif ratio < 1.5:
        weight += 0.10
    elif ratio >= 3.0:
        weight -= 0.05
    if team <= 3:
        weight += 0.05
    if window <= 2:
        weight += 0.03
    weight = round(min(0.70, max(0.20, weight)), 4)

    scored = []
    for name, s in data.scenarios.items():
        opportunity = _as_float(s.get("opportunity"))
        feasibility = _as_float(s.get("feasibility"))
        scored.append({
            "id": name,
            "score": round((1.0 - weight) * opportunity + weight * feasibility * 100.0, 2),
            "opportunity": opportunity,
            "feasibility": feasibility,
        })
    scored.sort(key=lambda row: (-row["score"], -row["opportunity"],
                                 -row["feasibility"], row["id"]))

    affordable = max(1, budget // cost_low) if cost_low else 1
    max_picks = min(3, team, affordable)
    chosen = scored[:max_picks]
    build_top = budget >= cost_low * 2

    picks = []
    for index, row in enumerate(chosen):
        name = row["id"]
        phase = "build" if (index == 0 and build_top) else "validate"
        if lang == "zh":
            why = (f"加权得分 {row['score']:.2f}（机会 {row['opportunity']:.2f}、"
                   f"可行性 {row['feasibility']:.2f}）；"
                   + ("预算支持它作为唯一主攻方向。" if phase == "build"
                      else "作为并行的验证项保留。"))
        else:
            why = (f"Weighted score {row['score']:.2f} (opportunity {row['opportunity']:.2f}, "
                   f"feasibility {row['feasibility']:.2f}); "
                   + ("the budget funds one build bet here." if phase == "build"
                      else "keep it as a parallel validation track."))
        picks.append({"id": name, "name": data.display(name, lang),
                      "phase": phase, "score": row["score"], "why": why})

    chosen_ids = {row["id"] for row in chosen}
    excluded = []
    for index, row in enumerate(scored):
        if row["id"] in chosen_ids:
            continue
        name = row["id"]
        if index < 3 and len(picks) < 3:
            plural = "s" if len(picks) != 1 else ""
            why = (f"团队与预算只覆盖 {len(picks)} 个场景；该场景排在下一顺位。"
                   if lang == "zh" else
                   f"Team and budget cover {len(picks)} pick{plural}; this scenario is next in line.")
        else:
            why = (f"加权得分（{row['score']:.2f}）低于入选场景。"
                   if lang == "zh" else
                   f"Lower weighted score ({row['score']:.2f}) than the selected picks.")
        excluded.append({"id": name, "name": data.display(name, lang), "why": why})

    return {
        "budget_usd": budget,
        "team_size": team,
        "weeks": window,
        "picks": picks,
        "excluded": excluded,
        "total_effort": round(len(picks) * effort_per_pick, 1),
        "heuristic": True,
        "assumptions": {
            "team_per_pick": allocation,
            "cost_per_person_week_usd": [4_000, 8_000],
            "cost_per_pick_usd": [cost_low, cost_high],
            "feasibility_weight": weight,
            "max_picks": 3,
            "budget_defaulted": defaulted,
        },
    }


# --------------------------------------------------------------- narratives
_KIND_LABELS = {
    "wizard": {"en": "decision-wizard", "zh": "决策向导"},
    "poc": {"en": "proof-of-concept plan", "zh": "PoC 计划"},
    "portfolio": {"en": "portfolio plan", "zh": "组合预算"},
}


def _role_label(role: str, lang: str) -> str:
    return ROLE_LABELS[_role(role)][lang]


def _payload_json(payload) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, indent=1, default=str)
    except (TypeError, ValueError):
        return "{}"


def _system_prompt(kind: str, lang: str, role: str) -> str:
    label = _KIND_LABELS[kind][lang]
    speaker = _role_label(role, lang)
    if lang == "zh":
        return (
            f"你是 OpenECRS 的{label}叙述助手，服务对象是一位{speaker}。\n"
            "用户消息会给出一个由确定性算法算出的结果 JSON，其中的场景、指标与数字都来自证据库；"
            "你只负责把结果改写成简短叙述，绝不计算、修改或编造数字。\n\n"
            "【输出格式】只输出严格 JSON，不要 Markdown、不要代码块、不要任何多余文字：\n"
            '{"summary": "2-3 句总结", "bullets": ["3-5 条要点"], "risks": ["2-3 条风险或局限"]}\n'
            "【规则】1) 只引用输入 JSON 中出现的数字，并保持原值；2) 不得编造场景、来源、链接或市场数据；"
            "3) 若输入中 heuristic 为 true，必须说明这是启发式估算；4) 必须用简体中文输出。"
        )
    return (
        f"You are the OpenECRS narrative writer for a {label} request from a {speaker}.\n"
        "The user message contains one deterministic result JSON computed from the OpenECRS evidence "
        "base. Rewrite that result as a short narrative; you never compute, change or invent numbers.\n\n"
        "[Output format] Return strict JSON only, no Markdown, no code fences, no extra text:\n"
        '{"summary": "2-3 sentence summary", "bullets": ["3-5 short bullets"], '
        '"risks": ["2-3 risks or limitations"]}\n'
        "[Rules] 1) Cite only numbers that appear in the input JSON, with identical values; "
        "2) never invent scenarios, sources, links or market data; "
        "3) if heuristic is true, say that the estimate is heuristic; "
        "4) answer in English."
    )


def _user_prompt(kind: str, payload, lang: str) -> str:
    if lang == "zh":
        return (f"确定性{_KIND_LABELS[kind]['zh']}结果（JSON，唯一允许引用的数字来源）：\n"
                f"{_payload_json(payload)}\n\n"
                "请用简体中文撰写叙述，只引用以上 JSON 中出现的数字，并保留 heuristic 标记。")
    return (f"Deterministic {_KIND_LABELS[kind]['en']} result "
            f"(JSON, the only allowed source of numbers):\n{_payload_json(payload)}\n\n"
            "Write the narrative in English. Only cite numbers that appear in the JSON above, "
            "and keep the heuristic flag if present.")


def _messages(kind: str, payload, lang, role) -> list[dict]:
    lang = _lang(lang)
    return [
        {"role": "system", "content": _system_prompt(kind, lang, role)},
        {"role": "user", "content": _user_prompt(kind, payload, lang)},
    ]


def build_wizard_messages(payload, lang: str = "en", role: str = "founder") -> list[dict]:
    """Prompt for narrating a wizard result; output schema is strict JSON."""
    return _messages("wizard", payload, lang, role)


def build_poc_messages(payload, lang: str = "en", role: str = "founder") -> list[dict]:
    """Prompt for narrating a PoC plan; output schema is strict JSON."""
    return _messages("poc", payload, lang, role)


def build_portfolio_messages(payload, lang: str = "en", role: str = "founder") -> list[dict]:
    """Prompt for narrating a portfolio result; output schema is strict JSON."""
    return _messages("portfolio", payload, lang, role)


# ------------------------------------------------------------- parse helper
_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.S)


def _dict_from_text(text: str) -> dict | None:
    candidates = [block.strip() for block in _FENCE_RE.findall(text)]
    candidates.append(text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for candidate in candidates:
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            return value
    return None


def _string_list(value, limit: int = 6) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    out = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            text = str(item)
        else:
            continue
        if text:
            out.append(text[:400])
    return out[:limit]


def parse_narrative(text) -> dict | None:
    """Parse the LLM narrative: tolerate code fences and surrounding prose.

    Returns ``{"summary", "bullets", "risks"}`` with missing fields filled in,
    or ``None`` when no usable JSON object is found.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    parsed = _dict_from_text(text)
    if parsed is None:
        return None
    keys = ("summary", "bullets", "risks")
    if not any(key in parsed for key in keys):
        return None
    summary = parsed.get("summary")
    if isinstance(summary, str):
        summary = summary.strip()[:1200]
    elif isinstance(summary, (int, float)) and not isinstance(summary, bool):
        summary = str(summary)[:1200]
    else:
        summary = ""
    return {
        "summary": summary,
        "bullets": _string_list(parsed.get("bullets")),
        "risks": _string_list(parsed.get("risks")),
    }
