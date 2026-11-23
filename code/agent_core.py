# -*- coding: utf-8 -*-
"""OpenECRS agent runtime.

The LLM is mandatory: it plans the answer (intent + scenarios + tools), the
runtime executes grounded tools over the evidence base, and the LLM writes the
final advice. If no LLM is configured or the model fails, the agent refuses to
answer instead of falling back to templates.
"""
from __future__ import annotations

import json
import time

import agent_prompts as prompts
import agent_providers
import agent_settings
from agent_tools import ScenarioData

INTENTS = set(prompts.INTENTS)
TOOLS = set(prompts.TOOL_NAMES)


class AgentError(RuntimeError):
    """The LLM was reachable but produced an unusable plan/answer."""


def _json_object(text: str) -> dict | None:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    for candidate in (text, text[text.find("{"): text.rfind("}") + 1]):
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
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]


class AgentRuntime:
    def __init__(self, settings: dict | None = None, data: ScenarioData | None = None,
                 provider=None):
        self.settings = settings or agent_settings.load_settings()
        self.data = data or ScenarioData()
        self._provider = provider
        self.info = agent_providers.provider_info(self.settings)

    # ------------------------------------------------------------- provider
    def provider(self):
        if self._provider is None:
            self._provider = agent_providers.get_provider(self.settings)
        return self._provider

    # ----------------------------------------------------------------- main
    def chat(self, message: str, session: dict | None = None, lang: str = "en") -> dict:
        session = session if session is not None else {}
        lang = "zh" if lang == "zh" else "en"
        provider = self.provider()
        history = session.get("history") or []
        started = time.time()

        plan, plan_meta = self._plan(provider, message, history, lang)
        tool_calls = self._tools_for(plan, message)
        tool_results = [self.data.run_tool(call["name"], call["args"], lang) for call in tool_calls]
        answer_fields, answer_meta = self._respond(provider, message, plan, tool_results, lang)

        answer = self._assemble(message, lang, plan, tool_calls, tool_results, answer_fields,
                                plan_meta, answer_meta, started)
        history.extend([{"role": "user", "content": message},
                        {"role": "assistant", "content": answer.get("advice", "")}])
        session["history"] = history[-12:]
        session["last_answer"] = answer
        session["turns"] = int(session.get("turns", 0)) + 1
        return answer

    # --------------------------------------------------------------- steps
    def _plan(self, provider, message: str, history: list[dict], lang: str) -> tuple[dict, dict]:
        catalog = self.data.catalog(lang)
        messages = [
            {"role": "system", "content": prompts.planner_system(catalog, lang)},
            {"role": "user", "content": prompts.planner_user(message, history, lang)},
        ]
        last_error = ""
        for attempt in range(2):
            result = provider.complete(messages, max_tokens=360, temperature=0.1)
            parsed = _json_object(result["content"])
            plan = self._normalise_plan(parsed, message, lang)
            if plan:
                return plan, {"model": result.get("model", ""), "latency_ms": result.get("latency_ms", 0),
                              "usage": result.get("usage") or {}, "attempt": attempt + 1,
                              "raw": result["content"][:800]}
            last_error = result["content"][:160]
            messages.append({"role": "assistant", "content": result["content"]})
            messages.append({"role": "user",
                             "content": "Return ONLY the strict JSON plan described above, nothing else."})
        raise AgentError("The LLM did not return a valid plan. / 模型没有返回有效的规划 JSON. "
                         f"Raw: {last_error}")

    def _normalise_plan(self, parsed: dict | None, message: str, lang: str) -> dict | None:
        if not parsed:
            return None
        intent = str(parsed.get("intent") or "").strip().lower()
        synonyms = {"comparison": "compare", "evidence_only": "evidence", "scenario_analysis": "scenario",
                    "recommendation": "advice", "action": "advice", "overview": "overview"}
        intent = synonyms.get(intent, intent)
        if intent not in INTENTS:
            intent = "overview"
        keys = []
        for raw in _string_list(parsed.get("scenarios"), 3):
            key = self.data.resolve(raw)
            if key and key not in keys:
                keys.append(key)
        focus = str(parsed.get("focus") or "none").strip().lower()
        if focus not in {"value", "feasibility", "gap", "demand", "risk", "action", "none"}:
            focus = "none"
        tools = []
        for item in (parsed.get("tools") or [])[:4]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if name not in TOOLS:
                continue
            tools.append({"name": name, "args": item.get("args") if isinstance(item.get("args"), dict) else {}})
        return {"intent": intent, "scenarios": keys, "focus": focus, "tools": tools,
                "reason": str(parsed.get("reason") or "")[:300]}

    def _tools_for(self, plan: dict, message: str) -> list[dict]:
        keys = plan["scenarios"]
        intent = plan["intent"]
        if intent in ("scenario", "advice") and not keys:
            keys = [self.data.ranked[0]["name"]]
        if intent == "compare" and len(keys) < 2:
            keys = [s["name"] for s in self.data.ranked[:2]]
        calls = []
        for item in plan["tools"]:
            name = item["name"]
            args = dict(item.get("args") or {})
            if name == "scenario":
                key = self.data.resolve(str(args.get("name") or (keys[0] if keys else "")))
                if key:
                    calls.append({"name": "scenario", "args": {"name": key, "evidence_limit": 5}})
            elif name == "evidence":
                key = self.data.resolve(str(args.get("name") or (keys[0] if keys else "")))
                if key:
                    calls.append({"name": "evidence", "args": {"name": key, "limit": 5}})
            elif name == "compare":
                names = args.get("names")
                if not isinstance(names, list) or len(names) < 2:
                    names = [args.get("a"), args.get("b")] if isinstance(args, list) is False else names
                resolved = [self.data.resolve(str(n)) for n in (names or [])]
                resolved = [r for r in resolved if r]
                if len(resolved) < 2:
                    resolved = [s["name"] for s in self.data.ranked[:2]]
                calls.append({"name": "compare", "args": {"names": resolved[:3]}})
            elif name == "search":
                calls.append({"name": "search", "args": {"query": str(args.get("query") or message), "limit": 5}})
            else:
                calls.append({"name": name, "args": {}})
        # defaults if the planner did not call anything usable
        if not calls:
            if intent == "ranking":
                calls = [{"name": "ranking", "args": {}}]
            elif intent == "compare":
                calls = [{"name": "compare", "args": {"names": keys[:2]}}]
            elif intent == "evidence":
                calls = [{"name": "evidence", "args": {"name": keys[0] if keys else self.data.ranked[0]["name"],
                                                       "limit": 5}}]
            elif intent in ("scenario", "advice"):
                key = keys[0] if keys else self.data.ranked[0]["name"]
                calls = [{"name": "scenario", "args": {"name": key, "evidence_limit": 5}},
                         {"name": "evidence", "args": {"name": key, "limit": 5}}]
            else:
                calls = [{"name": "catalog", "args": {}}, {"name": "ranking", "args": {}}]
        # de-duplicate and cap
        seen, unique = set(), []
        for call in calls:
            token = call["name"] + json.dumps(call["args"], sort_keys=True, ensure_ascii=False)
            if token not in seen:
                seen.add(token)
                unique.append(call)
        return unique[:4]

    def _respond(self, provider, message: str, plan: dict, tool_results: list[dict], lang: str):
        messages = [
            {"role": "system", "content": prompts.responder_system(lang)},
            {"role": "user", "content": prompts.responder_user(message, plan, tool_results, lang)},
        ]
        last_error = ""
        for attempt in range(2):
            result = provider.complete(messages, max_tokens=900, temperature=0.3)
            parsed = _json_object(result["content"])
            if parsed and str(parsed.get("advice") or "").strip():
                fields = {
                    "heading": str(parsed.get("heading") or "").strip()[:120],
                    "advice": str(parsed.get("advice") or "").strip()[:400],
                    "reply": str(parsed.get("reply") or "").strip()[:800],
                    "actions": _string_list(parsed.get("actions"), 4),
                    "risks": _string_list(parsed.get("risks"), 4),
                }
                return fields, {"model": result.get("model", ""), "latency_ms": result.get("latency_ms", 0),
                                "usage": result.get("usage") or {}, "attempt": attempt + 1,
                                "raw": result["content"][:800]}
            last_error = result["content"][:160]
            messages.append({"role": "assistant", "content": result["content"]})
            messages.append({"role": "user",
                             "content": "Return ONLY the strict JSON answer described above, nothing else."})
        raise AgentError("The LLM did not return a usable answer JSON. / 模型没有返回有效的作答 JSON. "
                         f"Raw: {last_error}")

    # ------------------------------------------------------------- assembly
    def _assemble(self, message, lang, plan, tool_calls, tool_results, fields,
                  plan_meta, answer_meta, started) -> dict:
        intent = plan["intent"]
        keys = list(plan["scenarios"])
        if intent == "compare" and len(keys) < 2:
            keys = [s["name"] for s in self.data.ranked[:2]]
        if intent in ("scenario", "advice", "evidence") and not keys:
            keys = [self.data.ranked[0]["name"]]
        names = [self.data.display(k, lang) for k in keys]

        metrics = {}
        for key in keys[:3]:
            scenario = self.data.scenario(key, lang)
            metrics[scenario["name"]] = scenario

        ranking = None
        comparison = None
        evidence = []
        for call, result in zip(tool_calls, tool_results):
            if call["name"] in ("ranking", "catalog"):
                ranking = self.data.ranking(lang)
            elif call["name"] == "compare":
                comparison = (result.get("comparison") or {}).get("rows")
            if isinstance(result.get("evidence"), list):
                evidence.extend(result["evidence"])
            if isinstance(result.get("scenario"), dict) and result["scenario"].get("evidence"):
                evidence.extend(result["scenario"]["evidence"])
        if comparison is None and intent == "compare" and len(keys) >= 2:
            comparison = self.data.compare(keys[:2], lang)["rows"]
        if ranking is None and intent in ("ranking", "overview"):
            ranking = self.data.ranking(lang)
        if not evidence:
            for key in keys[:2]:
                evidence.extend(self.data.evidence(key, lang, 5))
        # de-duplicate evidence by title
        seen, unique_evidence = set(), []
        for item in evidence:
            token = (item.get("title") or "")[:90]
            if token and token not in seen:
                seen.add(token)
                unique_evidence.append(item)
        evidence = unique_evidence[:6]

        if intent == "ranking":
            top = self.data.ranked[:3]
            for key in top:
                if self.data.display(key["name"], lang) not in metrics:
                    metrics[self.data.display(key["name"], lang)] = self.data.scenario(key["name"], lang)
            names = [self.data.display(s["name"], lang) for s in top]
        elif intent == "overview":
            names = [self.data.display(s["name"], lang) for s in self.data.ranked[:3]]
            for key in self.data.ranked[:3]:
                metrics.setdefault(self.data.display(key["name"], lang), self.data.scenario(key["name"], lang))

        heading = fields["heading"] or self._default_heading(intent, names, lang)
        engine = {
            "backend": self.info["backend"],
            "model": answer_meta.get("model") or plan_meta.get("model") or self.info["model"],
            "label": self.info["label"],
            "calls": 2,
            "latency_ms": int((time.time() - started) * 1000),
            "planner_latency_ms": plan_meta.get("latency_ms", 0),
            "responder_latency_ms": answer_meta.get("latency_ms", 0),
            "usage": {"planner": plan_meta.get("usage") or {}, "responder": answer_meta.get("usage") or {}},
        }
        trace = [
            {"step": "plan", "intent": intent, "scenarios": names, "focus": plan["focus"],
             "reason": plan.get("reason", ""), "model": plan_meta.get("model", ""),
             "latency_ms": plan_meta.get("latency_ms", 0)},
            {"step": "tools", "calls": [{"name": call["name"],
                                         "args": self._display_args(call, lang)} for call in tool_calls]},
            {"step": "answer", "model": answer_meta.get("model", ""),
             "latency_ms": answer_meta.get("latency_ms", 0)},
        ]
        return {
            "kind": intent,
            "lang": lang,
            "question": message,
            "heading": heading,
            "advice": fields["advice"],
            "reply": fields["reply"],
            "scenarios": names,
            "metrics": metrics,
            "ranking": ranking or [],
            "comparison": comparison or [],
            "evidence": evidence,
            "actions": fields["actions"],
            "risks": fields["risks"],
            "chips": prompts.chips_for(intent, lang),
            "engine": engine,
            "trace": trace,
        }

    def _display_args(self, call: dict, lang: str) -> dict:
        args = {}
        for key, value in (call.get("args") or {}).items():
            if key == "name":
                args[key] = self.data.display(value, lang)
            elif key == "names":
                args[key] = [self.data.display(item, lang) for item in value]
            else:
                args[key] = value
        return args

    def _default_heading(self, intent: str, names: list[str], lang: str) -> str:
        first = names[0] if names else ""
        if lang == "zh":
            return {
                "overview": "总览：机会雷达的 12 个场景",
                "ranking": "12 个场景机会总分排名",
                "scenario": f"{first} · 证据与行动建议",
                "compare": f"对比：{' vs '.join(names[:2])}",
                "evidence": "跨场景证据摘录",
                "advice": f"{first} · 行动建议",
            }.get(intent, "OpenECRS")
        return {
            "overview": "Overview: the 12 scenarios on the radar",
            "ranking": "Ranking: opportunity score for all 12 scenarios",
            "scenario": f"{first} · evidence and action plan",
            "compare": f"Comparison: {' vs '.join(names[:2])}",
            "evidence": "Cross-scenario evidence excerpts",
            "advice": f"{first} · action plan",
        }.get(intent, "OpenECRS")
