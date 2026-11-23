# -*- coding: utf-8 -*-
"""Agent Skill and prompt templates for the OpenECRS LLM agent.

The same skill text powers the planner and the responder, so the agent behaves
consistently no matter whether the LLM is a hosted API or a local fine-tuned
adapter. The skill is also published as skills/openecrs_agent.md.
"""
from __future__ import annotations

import json

INTENTS = ("overview", "ranking", "scenario", "compare", "evidence", "advice")
TOOL_NAMES = ("catalog", "ranking", "scenario", "compare", "evidence", "search", "meta")


def _language(lang: str) -> str:
    return "Chinese (简体中文)" if lang == "zh" else "English"


def skill_text(lang: str = "en") -> str:
    """The Agent Skill: role, grounded data contract, workflows and guardrails."""
    if lang == "zh":
        return (
            "你是 OpenECRS（Open Evidence-Centric Recommendation System）的证据驱动机会推荐智能体。\n"
            "你只依据工具返回的证据库数据工作，绝不编造数字、场景、来源或链接。\n\n"
            "【数据事实】12 个 AI 应用场景；评分 = 需求强度 45% + 供给缺口 25% + 技术可行性 18% + 商业价值 12%"
            "（AHP，CR=0.0002）；数据快照 2026-11-20；证据为规则影子审查，置信度未校准（无人工金标）；"
            "来源以 Hacker News / GitHub 为主，存在采集偏差。\n"
            "【证据规则】每条结论应能对应工具返回的指标或原文 span；引用原文时保持原样，不翻译、不改写。\n"
            "【工作流】1) 读取问题与历史；2) 规划 intent、scenarios 与要调用的工具；3) 依据工具结果作答。\n"
            "【回答风格】先给一句话建议（≤60 字，必须包含关键数字与明确动作），再给 2–3 句说明；"
            "行动建议 3–4 条；风险/局限 3–4 条；只输出严格 JSON。"
        )
    return (
        "You are OpenECRS (Open Evidence-Centric Recommendation System), an evidence-driven opportunity agent.\n"
        "Work only from the data returned by tools. Never invent numbers, scenarios, sources or links.\n\n"
        "[Data facts] 12 AI application scenarios; score = demand 45% + supply gap 25% + technical feasibility 18% "
        "+ business value 12% (AHP, CR=0.0002); snapshot 2026-11-20; evidence is rule-shadow reviewed and "
        "uncalibrated (no human gold labels); sources are Hacker News / GitHub heavy, so shares are biased.\n"
        "[Evidence rules] Every claim must map to a tool metric or quoted span; quote spans verbatim.\n"
        "[Workflow] 1) read question and history; 2) plan intent, scenarios and tools; 3) answer from tool results.\n"
        "[Answer style] one-sentence advice (<=45 words, must include key numbers and a concrete action), then "
        "2–3 supporting sentences; 3–4 actions; 3–4 risks/limits; output strict JSON only."
    )


def planner_system(catalog: list[dict], lang: str = "en") -> str:
    catalog_json = json.dumps(catalog, ensure_ascii=False, indent=1)
    if lang == "zh":
        return (
            f"{skill_text(lang)}\n\n"
            "你现在处于【规划阶段】。根据问题和场景目录，输出严格 JSON（不要 Markdown、不要代码块、不要多余文字）：\n"
            '{"intent": "overview|ranking|scenario|compare|evidence|advice", '
            '"scenarios": ["场景id"], "focus": "value|feasibility|gap|demand|risk|action|none", '
            '"tools": [{"name": "catalog|ranking|scenario|compare|evidence|search|meta", "args": {}}], '
            '"reason": "一句话规划理由"}\n'
            "规则：compare 必须给 2 个场景；scenario/advice/evidence 至少给 1 个场景；"
            "最多调用 4 个工具；场景 id 必须来自目录（中文 id）。\n\n"
            f"【场景目录】\n{catalog_json}"
        )
    return (
        f"{skill_text(lang)}\n\n"
        "You are in the PLANNING phase. Given the question and scenario catalog, return strict JSON "
        "(no Markdown, no code fences, no extra text):\n"
        '{"intent": "overview|ranking|scenario|compare|evidence|advice", '
        '"scenarios": ["scenario id"], "focus": "value|feasibility|gap|demand|risk|action|none", '
        '"tools": [{"name": "catalog|ranking|scenario|compare|evidence|search|meta", "args": {}}], '
        '"reason": "one-line planning rationale"}\n'
        "Rules: compare needs exactly two scenarios; scenario/advice/evidence need at least one scenario; "
        "call at most four tools; scenario ids must come from the catalog.\n\n"
        f"[Scenario catalog]\n{catalog_json}"
    )


def planner_user(question: str, history: list[dict], lang: str = "en") -> str:
    transcript = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in history[-6:]) or "(none)"
    if lang == "zh":
        return f"最近对话：\n{transcript}\n\n当前问题：{question}\n用{_language(lang)}回答。"
    return f"Recent conversation:\n{transcript}\n\nCurrent question: {question}\nAnswer in {_language(lang)}."


def responder_system(lang: str = "en") -> str:
    if lang == "zh":
        return (
            f"{skill_text(lang)}\n\n"
            "你现在处于【作答阶段】。只能使用用户消息中给出的工具结果，输出严格 JSON：\n"
            '{"heading": "简短标题", "advice": "一句话建议（含关键数字与动作）", '
            '"reply": "2-3 句说明", "actions": ["3-4 条行动建议"], "risks": ["3-4 条风险或局限"]}\n'
            "不要输出 Markdown、代码块或额外文字；数字必须与工具结果一致；用简体中文。"
        )
    return (
        f"{skill_text(lang)}\n\n"
        "You are in the RESPONSE phase. Use only the tool results in the user message and return strict JSON:\n"
        '{"heading": "short heading", "advice": "one-sentence advice with key numbers and an action", '
        '"reply": "2-3 supporting sentences", "actions": ["3-4 concrete actions"], '
        '"risks": ["3-4 risks or limitations"]}\n'
        "No Markdown, no code fences, no extra text; numbers must match the tool results; answer in English."
    )


def responder_user(question: str, plan: dict, tool_results: list[dict], lang: str = "en") -> str:
    payload = {
        "question": question,
        "plan": plan,
        "tool_results": tool_results,
    }
    if lang == "zh":
        return "请基于以下数据作答（只使用这些数据）：\n" + json.dumps(payload, ensure_ascii=False, indent=1)
    return "Answer from this data only:\n" + json.dumps(payload, ensure_ascii=False, indent=1)


def chips_for(intent: str, lang: str = "en") -> list[str]:
    if lang == "zh":
        return {
            "overview": ["哪个场景最值得优先做？", "对比 安全合规 和 多智能体",
                         "知识管理与文档问答 的证据", "给我一个 2 周 PoC 方案"],
            "ranking": ["对比第 1 名和第 2 名", "为什么安全合规可行性低？",
                        "看多智能体与任务编排的证据", "给我一个 2 周 PoC 方案"],
            "scenario": ["它最大的风险是什么？", "给我一个 2 周 PoC 方案",
                         "对比它和第 1 名", "看它的证据摘录"],
            "compare": ["看两边的证据", "给我一个 2 周 PoC 方案",
                        "哪个更值得先做？", "哪个场景最值得优先做？"],
            "evidence": ["这些证据能说明什么？", "哪个场景最值得优先做？",
                         "给我一个 2 周 PoC 方案"],
            "advice": ["它最大的风险是什么？", "看它的证据摘录",
                       "给我一个 2 周 PoC 方案"],
        }.get(intent, ["哪个场景最值得优先做？", "对比 安全合规 和 多智能体"])
    return {
        "overview": ["Which scenario should we prioritise?",
                     "Compare Security, Compliance & Privacy vs Multi-agent",
                     "Show evidence for Knowledge Management & Document QA",
                     "Give me a 2-week PoC plan"],
        "ranking": ["Compare the #1 and #2", "Why is Security & Compliance hard to build?",
                    "Show evidence for Multi-agent", "Give me a 2-week PoC plan"],
        "scenario": ["What is its biggest risk?", "Give me a 2-week PoC plan",
                     "Compare it with the #1", "Show its evidence"],
        "compare": ["Show the evidence for both", "Give me a 2-week PoC plan",
                    "Which one should we start with?", "Which scenario should we prioritise?"],
        "evidence": ["What do these quotes imply?", "Which scenario should we prioritise?",
                     "Give me a 2-week PoC plan"],
        "advice": ["What is its biggest risk?", "Show its evidence",
                   "Give me a 2-week PoC plan"],
    }.get(intent, ["Which scenario should we prioritise?"])
