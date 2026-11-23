# -*- coding: utf-8 -*-
"""Deterministic insight helpers for the OpenECRS evidence UI.

三个可复用能力 / three reusable capabilities:

1. Evidence retrieval — flatten ``data.json`` evidence into a filterable index,
   then filter with :func:`query` and summarise facets with :func:`facets`.
2. Scenario deep-dive — :func:`scenario_detail` joins scenario metrics with the
   yearly trend and source mix aggregated from ``result2.csv``.
3. Outbound video search — :func:`video_links` builds YouTube / Bilibili search
   URLs from scenario names. No network access, no LLM calls.

:func:`build_insights` / :func:`load_insights` manage
``outputs/agent_ui/insights.json``. The builder degrades gracefully to an empty
``scenarios`` mapping when ``result2.csv`` is missing or lacks columns.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from agent_tools import ScenarioData, load_data
from scenario_names import SCENARIO_NAMES_EN

BASE = Path(__file__).resolve().parents[1]
RESULT2_FILE = BASE / "outputs" / "tables" / "result2.csv"
INSIGHTS_FILE = BASE / "outputs" / "agent_ui" / "insights.json"

#: Columns required before yearly / source aggregation is attempted.
REQUIRED_COLUMNS = ("scenario", "year", "source")

#: Compact scenario metrics surfaced as "signals" in the detail panel.
SIGNAL_FIELDS = (
    "need_rate",
    "wtp_rate",
    "value_rate",
    "urgency_rate",
    "growth_slope",
    "answer_rate",
    "barrier",
)

#: Supply-side proxies surfaced as "supply" in the detail panel.
SUPPLY_FIELDS = ("repo_n", "repo_stars_sum", "paper_n", "show_n", "product_n")

#: Bilingual disclaimer attached to every external video link.
VIDEO_NOTE = "外部视频，非证据库 / external video, not part of the evidence base"

YOUTUBE_SEARCH = "https://www.youtube.com/results?search_query="
BILIBILI_SEARCH = "https://search.bilibili.com/all?keyword="

VIDEO_ZH_SUFFIX = "AI 产品 案例 分析"
VIDEO_EN_SUFFIX = "AI product case study"


# --------------------------------------------------------------- small utils
def empty_insights() -> dict:
    """Empty insights payload / 空 insights 结构."""
    return {"generated_at": None, "scenarios": {}}


def _warn(message: str) -> None:
    print(f"[agent_insights] warning: {message}")


def _payload(data) -> dict:
    """Accept ScenarioData, a raw data.json dict, or None (load default)."""
    if data is None:
        return load_data()
    if isinstance(data, ScenarioData):
        return data.data
    if isinstance(data, dict):
        return data
    raise TypeError(f"unsupported data type: {type(data)!r}")


def _as_int(value, default=0):
    try:
        if isinstance(value, bool):
            return int(value)
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _as_optional_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _fold(value) -> str:
    return str(value or "").strip().casefold()


def _coerce_year(value):
    year = _as_int(value, None)
    return year if year is not None else None


def _coerce_scenario_data(data) -> ScenarioData:
    if isinstance(data, ScenarioData):
        return data
    if data is None:
        return ScenarioData()
    if isinstance(data, dict):
        return ScenarioData(data)
    raise TypeError(f"unsupported data type: {type(data)!r}")


# ------------------------------------------------------------- evidence index
def evidence_index(data: ScenarioData | dict | None) -> list[dict]:
    """Flatten every scenario's evidence into one flat list / 展平证据索引.

    Each record carries the Chinese scenario id plus its English display name so
    the UI can filter and label entries without a second lookup.
    """
    payload = _payload(data)
    items: list[dict] = []
    for scenario in payload.get("scenarios") or []:
        if not isinstance(scenario, dict):
            continue
        name = str(scenario.get("name") or "")
        name_en = str(scenario.get("name_en") or SCENARIO_NAMES_EN.get(name, name))
        for evidence in scenario.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            gates = [str(gate) for gate in (evidence.get("gates") or [])]
            items.append({
                "scenario": name,
                "scenario_en": name_en,
                "source": str(evidence.get("source") or ""),
                "year": _as_int(evidence.get("year"), 0),
                "confidence": _as_optional_float(evidence.get("confidence")),
                "is_opportunity": 1 if _as_int(evidence.get("is_opportunity"), 0) else 0,
                "gates": gates,
                "title": str(evidence.get("title") or ""),
                "quote": str(evidence.get("quote") or ""),
                "url": str(evidence.get("url") or ""),
            })
    return items


def query(items: list[dict] | None, scenario=None, source=None, year=None,
          min_confidence=None, kind: str = "all", q=None, limit=100) -> list[dict]:
    """Filter evidence records / 过滤证据列表.

    ``kind`` accepts ``positive``, ``negative`` or ``all``. ``q`` is matched
    case-insensitively against title and quote. Unknown / blank filters are
    ignored; ``limit=None`` means unlimited.
    """
    kind = str(kind or "all").strip().lower()
    if kind not in ("all", "positive", "negative"):
        kind = "all"
    scenario_key = _fold(scenario)
    source_key = _fold(source)
    text_key = _fold(q)
    year_key = _coerce_year(year)
    confidence_key = _as_optional_float(min_confidence)

    if limit is None:
        limit_n: int | None = None
    else:
        try:
            limit_n = int(limit)
        except (TypeError, ValueError):
            limit_n = 100
        limit_n = max(0, limit_n)
        if limit_n == 0:
            return []

    results: list[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        is_opportunity = 1 if _as_int(item.get("is_opportunity"), 0) else 0
        if kind == "positive" and not is_opportunity:
            continue
        if kind == "negative" and is_opportunity:
            continue
        if scenario_key:
            names = (_fold(item.get("scenario")), _fold(item.get("scenario_en")))
            if not any(scenario_key in name for name in names if name):
                continue
        if source_key and source_key not in _fold(item.get("source")):
            continue
        if year_key is not None and _as_int(item.get("year"), None) != year_key:
            continue
        if confidence_key is not None:
            confidence = _as_optional_float(item.get("confidence"))
            if confidence is None or confidence < confidence_key:
                continue
        if text_key:
            haystack = f"{item.get('title') or ''}\n{item.get('quote') or ''}".casefold()
            if text_key not in haystack:
                continue
        results.append(item)
        if limit_n is not None and len(results) >= limit_n:
            break
    return results


def facets(items: list[dict] | None) -> dict:
    """Distinct, sorted facet values / 去重排序的筛选维度."""
    scenarios: set[str] = set()
    sources: set[str] = set()
    years: set[int] = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("scenario") or "").strip()
        if name:
            scenarios.add(name)
        source = str(item.get("source") or "").strip()
        if source:
            sources.add(source)
        year = _as_int(item.get("year"), None)
        if year is not None and year > 0:
            years.add(year)
    return {
        "scenarios": sorted(scenarios),
        "sources": sorted(sources),
        "years": sorted(years),
    }


# ------------------------------------------------------------ scenario detail
def _trend_section(entry) -> dict:
    trend = (entry or {}).get("trend") if isinstance(entry, dict) else None
    trend = trend if isinstance(trend, dict) else {}
    pairs = []
    for raw_year, raw_count in zip(trend.get("years") or [], trend.get("counts") or []):
        year = _as_int(raw_year, None)
        count = _as_int(raw_count, None)
        if year is None or count is None:
            continue
        pairs.append((year, count))
    pairs.sort(key=lambda pair: pair[0])
    return {"years": [pair[0] for pair in pairs], "counts": [pair[1] for pair in pairs]}


def _source_mix_section(entry) -> list[dict]:
    mix = (entry or {}).get("source_mix") if isinstance(entry, dict) else None
    rows = []
    for row in mix or []:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "").strip()
        count = _as_int(row.get("count"), None)
        if source and count is not None:
            rows.append({"source": source, "count": count})
    rows.sort(key=lambda row: (-row["count"], row["source"]))
    return rows


def scenario_detail(name: str, data: ScenarioData | dict | None, insights: dict | None = None) -> dict:
    """Full detail payload for one scenario / 单个场景的完整详情.

    Returns ``{"error": "unknown scenario"}`` when the name cannot be resolved.
    ``insights`` is the object produced by :func:`build_insights`; when it is
    missing or stale the trend / source mix degrade to empty values.
    """
    scenario_data = _coerce_scenario_data(data)
    key = scenario_data.resolve(name)
    if not key:
        return {"error": "unknown scenario"}
    scenario = scenario_data.scenarios[key]
    metrics = {field: value for field, value in scenario.items() if field != "evidence"}
    scenario_insights = (insights or {}).get("scenarios") if isinstance(insights, dict) else None
    entry = (scenario_insights or {}).get(key) if isinstance(scenario_insights, dict) else None
    evidence = [
        item for item in evidence_index(scenario_data.data)
        if item.get("scenario") == key
    ]
    return {
        "id": key,
        "name": key,
        "name_en": scenario.get("name_en") or SCENARIO_NAMES_EN.get(key, key),
        "metrics": metrics,
        "signals": {field: scenario.get(field) for field in SIGNAL_FIELDS},
        "supply": {field: scenario.get(field) for field in SUPPLY_FIELDS},
        "trend": _trend_section(entry),
        "source_mix": _source_mix_section(entry),
        "evidence": evidence,
    }


# ------------------------------------------------------------------ insights
def _write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def _read_insight_frame(csv_path: Path) -> pd.DataFrame | None:
    header = pd.read_csv(csv_path, nrows=0)
    columns = {str(column) for column in header.columns}
    missing = [column for column in REQUIRED_COLUMNS if column not in columns]
    if missing:
        _warn(f"{csv_path} is missing column(s) {missing}; writing empty insights")
        return None
    return pd.read_csv(csv_path, usecols=list(REQUIRED_COLUMNS))


def _aggregate_insights(frame: pd.DataFrame | None) -> dict:
    """Group records by scenario+year and scenario+source / 聚合年度与来源."""
    if frame is None or frame.empty:
        return {}
    scenario_series = frame["scenario"].astype("string").str.strip()
    valid_scenario = scenario_series.notna() & (scenario_series.str.len().fillna(0) > 0)
    years = pd.to_numeric(frame["year"], errors="coerce")
    valid_year = years.notna() & (years % 1 == 0)
    source_series = frame["source"].astype("string").str.strip()
    valid_source = source_series.notna() & (source_series.str.len().fillna(0) > 0)

    trend: dict[str, dict[str, list[int]]] = {}
    trend_frame = pd.DataFrame({
        "scenario": scenario_series[valid_scenario & valid_year],
        "year": years[valid_scenario & valid_year].astype("int64"),
    })
    if not trend_frame.empty:
        counts = trend_frame.groupby(["scenario", "year"], sort=False).size()
        for (scenario, year), count in counts.items():
            entry = trend.setdefault(str(scenario), {"years": [], "counts": []})
            entry["years"].append(int(year))
            entry["counts"].append(int(count))
    for entry in trend.values():
        order = sorted(range(len(entry["years"])), key=lambda index: entry["years"][index])
        entry["years"] = [entry["years"][index] for index in order]
        entry["counts"] = [entry["counts"][index] for index in order]

    source_mix: dict[str, list[dict]] = {}
    source_frame = pd.DataFrame({
        "scenario": scenario_series[valid_scenario & valid_source],
        "source": source_series[valid_scenario & valid_source],
    })
    if not source_frame.empty:
        counts = source_frame.groupby(["scenario", "source"], sort=False).size()
        for (scenario, source), count in counts.items():
            source_mix.setdefault(str(scenario), []).append({
                "source": str(source),
                "count": int(count),
            })
    for rows in source_mix.values():
        rows.sort(key=lambda row: (-row["count"], row["source"]))

    scenarios: dict[str, dict] = {}
    for scenario in sorted(set(trend) | set(source_mix)):
        scenarios[scenario] = {
            "trend": trend.get(scenario, {"years": [], "counts": []}),
            "source_mix": source_mix.get(scenario, []),
        }
    return scenarios


def build_insights(result2_csv_path=None, out_path=None) -> dict:
    """Aggregate ``result2.csv`` into ``insights.json`` / 生成 insights.json.

    Missing files or missing ``scenario`` / ``year`` / ``source`` columns never
    raise: a warning is printed and an empty ``scenarios`` mapping is written.
    """
    csv_path = Path(result2_csv_path) if result2_csv_path is not None else RESULT2_FILE
    target = Path(out_path) if out_path is not None else INSIGHTS_FILE
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scenarios": {},
    }
    if not csv_path.exists():
        _warn(f"{csv_path} not found; writing empty insights")
    else:
        frame = None
        try:
            frame = _read_insight_frame(csv_path)
        except Exception as exc:  # pragma: no cover - defensive, pandas versions differ
            _warn(f"failed to read {csv_path}: {exc}; writing empty insights")
        payload["scenarios"] = _aggregate_insights(frame)
    _write_json(payload, target)
    return payload


def load_insights(path=None) -> dict:
    """Read ``insights.json``, returning an empty structure when unavailable."""
    target = Path(path) if path is not None else INSIGHTS_FILE
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty_insights()
    if not isinstance(payload, dict):
        return empty_insights()
    scenarios = payload.get("scenarios")
    return {
        "generated_at": payload.get("generated_at"),
        "scenarios": scenarios if isinstance(scenarios, dict) else {},
    }


# --------------------------------------------------------------- video links
def _video_names(scenario_id, data) -> tuple[str, str]:
    raw = str(scenario_id or "").strip()
    if not raw:
        return "", ""
    scenario_data = None
    if data is not None:
        try:
            scenario_data = _coerce_scenario_data(data)
        except (TypeError, ValueError, KeyError):
            scenario_data = None
    key = scenario_data.resolve(raw) if scenario_data is not None else None
    if key:
        name_en = scenario_data.scenarios[key].get("name_en") or SCENARIO_NAMES_EN.get(key, key)
        return key, str(name_en)
    return raw, SCENARIO_NAMES_EN.get(raw, raw)


def _search_url(platform: str, query_text: str) -> str:
    base = YOUTUBE_SEARCH if platform == "youtube" else BILIBILI_SEARCH
    return base + quote(query_text, safe="")


def video_links(scenario_id, data=None, lang: str = "zh") -> list[dict]:
    """Four outbound search links (YouTube x2, Bilibili x2) / 外部视频搜索链接.

    Links only open platform search pages; nothing is fetched. The ``note``
    field states explicitly that these videos are not part of the evidence base.
    """
    name_zh, name_en = _video_names(scenario_id, data)
    if not name_zh:
        return []
    chinese = str(lang or "zh").lower().startswith("zh")
    zh_query = f"{name_zh} {VIDEO_ZH_SUFFIX}"
    en_query = f"{name_en} {VIDEO_EN_SUFFIX}"
    specs = [
        ("youtube", zh_query,
         f"YouTube · {name_zh} AI 产品案例",
         f"YouTube · {name_zh} AI product case study (Chinese)"),
        ("youtube", en_query,
         f"YouTube · {name_en} AI 产品案例（英文）",
         f"YouTube · {name_en} AI product case study"),
        ("bilibili", zh_query,
         f"哔哩哔哩 · {name_zh} AI 产品案例",
         f"Bilibili · {name_zh} AI product case study (Chinese)"),
        ("bilibili", en_query,
         f"哔哩哔哩 · {name_en} AI 产品案例（英文）",
         f"Bilibili · {name_en} AI product case study"),
    ]
    links = []
    for platform, query_text, title_zh, title_en in specs:
        links.append({
            "title": title_zh if chinese else title_en,
            "platform": platform,
            "url": _search_url(platform, query_text),
            "kind": "search",
            "note": VIDEO_NOTE,
        })
    return links
