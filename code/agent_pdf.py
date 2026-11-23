# -*- coding: utf-8 -*-
"""Render the agent recommendation as a printable A4 report and export it to PDF.

PDF export uses a locally installed Chromium browser in headless mode
(Chrome / Edge / Chromium / Brave). No network and no extra Python package is
required. If no browser is found the caller can fall back to opening the
print-ready HTML in the user's browser.
"""
from __future__ import annotations

import html
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
PDF_DIR = BASE / "outputs" / "agent_ui" / "pdf"

BROWSER_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/microsoft-edge",
]

CSS = """
@page { size: A4; margin: 16mm 15mm 18mm; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: "Arial", "STHeiti", "Arial Unicode MS", "Microsoft YaHei",
               "Noto Sans CJK SC", "WenQuanYi Micro Hei", sans-serif;
  color: #111827; font-size: 10.5pt; line-height: 1.62; -webkit-print-color-adjust: exact;
}
.doc-head { border-bottom: 2px solid #111827; padding-bottom: 10px; margin-bottom: 16px; }
.doc-head .kicker { font-size: 8.5pt; letter-spacing: .18em; color: #6b7280; text-transform: uppercase; }
h1 { font-size: 20pt; line-height: 1.25; margin: 6px 0 4px; letter-spacing: -.01em; }
.subtitle { color: #4b5563; font-size: 9.5pt; }
h2 { font-size: 12pt; margin: 18px 0 8px; padding-bottom: 4px; border-bottom: 1px solid #e5e7eb; }
h2 .num { color: #9ca3af; margin-right: 6px; font-weight: 400; }
.advice {
  border-left: 3px solid #111827; padding: 8px 0 8px 12px; margin: 6px 0 2px;
  font-size: 12.5pt; line-height: 1.7; font-weight: 600;
}
.note { color: #4b5563; font-size: 9pt; margin: 4px 0 10px; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 4px; font-size: 9pt; }
th, td { border: 1px solid #e5e7eb; padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: #f9fafb; font-weight: 600; }
td.k { width: 24%; color: #374151; background: #fcfcfd; }
.num-cell { text-align: right; font-variant-numeric: tabular-nums; }
.best { font-weight: 700; }
.evidence { margin: 8px 0 0; padding: 0; list-style: none; }
.evidence li { margin: 0 0 10px; padding: 0 0 8px; border-bottom: 1px dashed #e5e7eb; }
.evidence .ev-head { font-size: 8.5pt; color: #6b7280; }
.evidence .ev-head .tag { display: inline-block; border: 1px solid #d1d5db; border-radius: 3px;
  padding: 0 4px; margin-right: 6px; color: #374151; }
.evidence .ev-title { font-weight: 600; margin: 2px 0; font-size: 9.5pt; }
.evidence blockquote { margin: 4px 0 0; padding: 4px 8px; background: #f9fafb; color: #1f2937;
  border-left: 2px solid #d1d5db; font-size: 9pt; }
.evidence .ev-url { font-size: 7.5pt; color: #6b7280; word-break: break-all; }
ol, ul { margin: 4px 0 0 18px; padding: 0; }
li { margin: 2px 0; }
.risk { color: #4b5563; font-size: 9pt; }
footer { margin-top: 20px; padding-top: 8px; border-top: 1px solid #e5e7eb;
  color: #9ca3af; font-size: 7.5pt; line-height: 1.5; }
"""


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _fmt(value: float, digits: int = 2) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def find_browser() -> str | None:
    override = os.environ.get("AGENT_PDF_BROWSER")
    if override and Path(override).exists():
        return override
    for candidate in BROWSER_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    for name in ("google-chrome", "chrome", "chromium", "msedge", "microsoft-edge", "brave"):
        found = shutil.which(name)
        if found:
            return found
    return None


def build_report_html(context: dict) -> str:
    meta = context.get("meta", {})
    now = time.strftime("%Y-%m-%d %H:%M")
    en = (context.get("lang") or "en") != "zh"
    parts: list[str] = []
    parts.append("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">")
    parts.append(f"<title>{_esc(context.get('title'))}</title><style>{CSS}</style></head><body>")
    parts.append("<div class=\"doc-head\">")
    parts.append("<div class=\"kicker\">OPENECRS · EVIDENCE-CENTRIC RECOMMENDATION</div>")
    parts.append(f"<h1>{_esc(context.get('title'))}</h1>")
    subtitle = context.get("question") or context.get("subtitle") or ""
    if en:
        parts.append(
            f"<div class=\"subtitle\">Question: {_esc(subtitle)} · Generated {now} · "
            f"{meta.get('evidence_records', 0):,} evidence reviews · data cut-off {meta.get('data_cutoff', '')}</div>"
        )
    else:
        parts.append(
            f"<div class=\"subtitle\">问题：{_esc(subtitle)} · 生成时间 {now} · "
            f"证据审查 {meta.get('evidence_records', 0):,} 条 · 数据截至 {meta.get('data_cutoff', '')}</div>"
        )
    parts.append("</div>")

    parts.append(f"<h2><span class=\"num\">01</span>{'One-sentence advice' if en else '一句话建议'}</h2>")
    parts.append(f"<div class=\"advice\">{_esc(context.get('advice'))}</div>")
    if context.get("reply"):
        parts.append(f"<p class=\"note\">{_esc(context['reply'])}</p>")

    parts.append(f"<h2><span class=\"num\">02</span>{'Detailed data' if en else '详细数据'}</h2>")
    rows = context.get("metrics_rows") or []
    if rows:
        parts.append("<table><colgroup><col style=\"width:24%\"><col></colgroup>")
        parts.append(f"<tr><th>{'Metric' if en else '指标'}</th><th>{'Value' if en else '数值'}</th></tr>")
        for key, value in rows:
            parts.append(f"<tr><td class=\"k\">{_esc(key)}</td><td>{_esc(value)}</td></tr>")
        parts.append("</table>")
    comparison = context.get("comparison") or []
    if comparison:
        metric_key = "Metric" if en else "指标"
        names = [key for key in comparison[0] if key != metric_key]
        parts.append(f"<table><tr><th>{metric_key}</th>" + "".join(f"<th>{_esc(n)}</th>" for n in names) + "</tr>")
        for row in comparison:
            cells = "".join(f"<td>{_esc(row.get(n, ''))}</td>" for n in names)
            parts.append(f"<tr><td class=\"k\">{_esc(row.get(metric_key))}</td>{cells}</tr>")
        parts.append("</table>")
    ranking = context.get("ranking") or []
    if ranking:
        if en:
            parts.append("<table><tr><th>Rank</th><th>Scenario</th><th class=\"num-cell\">Opportunity</th>"
                         "<th class=\"num-cell\">Demand</th><th class=\"num-cell\">Gap</th>"
                         "<th class=\"num-cell\">Feasibility</th><th class=\"num-cell\">Value</th>"
                         "<th>Route</th></tr>")
        else:
            parts.append("<table><tr><th>排名</th><th>场景</th><th class=\"num-cell\">机会分</th>"
                         "<th class=\"num-cell\">需求</th><th class=\"num-cell\">缺口</th>"
                         "<th class=\"num-cell\">可行性</th><th class=\"num-cell\">价值</th>"
                         "<th>路线</th></tr>")
        for row in ranking:
            cls = " class=\"best\"" if row.get("rank") == 1 else ""
            parts.append(
                f"<tr><td{cls}>{_esc(row.get('rank'))}</td><td{cls}>{_esc(row.get('scenario'))}</td>"
                f"<td class=\"num-cell\">{_fmt(row.get('opportunity'), 1)}</td>"
                f"<td class=\"num-cell\">{_fmt(row.get('demand'))}</td>"
                f"<td class=\"num-cell\">{_fmt(row.get('gap'))}</td>"
                f"<td class=\"num-cell\">{_fmt(row.get('feasibility'))}</td>"
                f"<td class=\"num-cell\">{_fmt(row.get('value'))}</td>"
                f"<td>{_esc(row.get('route'))}</td></tr>"
            )
        parts.append("</table>")
        parts.append("<p class=\"note\">" + ("Opportunity score = demand 45% + supply gap 25% + technical feasibility 18% + business value 12% (AHP, CR=0.0002)." if en else "机会总分 = 需求强度 45% + 供给缺口 25% + 技术可行性 18% + 商业价值 12%（AHP，CR=0.0002）。") + "</p>")

    evidence = context.get("evidence") or []
    if evidence:
        parts.append(f"<h2><span class=\"num\">03</span>{'Evidence excerpts (quoted spans)' if en else '证据摘录（原文 span）'}</h2>")
        parts.append("<ul class=\"evidence\">")
        for ev in evidence[:6]:
            scenario = ev.get("scenario") or (context.get("scenarios") or [""])[0]
            tag = f"{ev.get('source', '')} · {ev.get('year', '')} · " + (
                f"confidence {_fmt(ev.get('confidence'))}" if en else f"置信度 {_fmt(ev.get('confidence'))}")
            if ev.get("is_opportunity"):
                tag += " · four gates passed" if en else " · 四门通过"
            parts.append("<li>")
            parts.append(f"<div class=\"ev-head\"><span class=\"tag\">{_esc(scenario)}</span>{_esc(tag)}</div>")
            parts.append(f"<div class=\"ev-title\">{_esc(ev.get('title'))}</div>")
            parts.append(f"<blockquote>{_esc(ev.get('quote'))}</blockquote>")
            if ev.get("url"):
                parts.append(f"<div class=\"ev-url\">{_esc(ev['url'])}</div>")
            parts.append("</li>")
        parts.append("</ul>")

    actions = context.get("actions") or []
    if actions:
        parts.append(f"<h2><span class=\"num\">04</span>{'Action plan' if en else '行动建议'}</h2><ol>")
        for item in actions:
            parts.append(f"<li>{_esc(item)}</li>")
        parts.append("</ol>")

    risks = context.get("risks") or []
    if risks:
        parts.append(f"<h2><span class=\"num\">05</span>{'Scope & limitations' if en else '口径与局限'}</h2><ul class=\"risk\">")
        for item in risks:
            parts.append(f"<li>{_esc(item)}</li>")
        parts.append("</ul>")

    engine = context.get("engine") or {}
    label = engine.get("label") or engine.get("model") or ""
    if label:
        engine_note = (f"The advice and explanation in this brief were written by the LLM ({_esc(label)}); "
                       "numbers, ranking and quoted evidence come from offline tools. " if en else
                       f"本建议的「一句话建议/说明」由大模型（{_esc(label)}）规划并撰写，数字、排名与证据来自离线工具；")
    else:
        engine_note = ("This brief was generated by the OpenECRS LLM agent. " if en else
                       "本建议由 OpenECRS LLM 智能体生成；")
    if en:
        parts.append(
            "<footer>Data scope: 52,007 raw records → 45,306 cleaned records → 19,621 demand/supply units "
            f"({meta.get('demand_units', 0):,} demand units) → {meta.get('high_conf_samples', 0):,} high-confidence samples; "
            f"{meta.get('evidence_records', 0):,} evidence reviews, {meta.get('evidence_opportunities', 0)} pass the four-gate check. "
            f"{engine_note}Confidences are not human-calibrated; for decision support only.</footer>"
        )
    else:
        parts.append(
            "<footer>数据口径：52,007 条原始记录 → 45,306 条清洗记录 → 19,621 个需求/供给单元"
            f"（需求 {meta.get('demand_units', 0):,} 条）→ {meta.get('high_conf_samples', 0):,} 条高置信场景样本；"
            f"证据审查 {meta.get('evidence_records', 0):,} 条，其中 {meta.get('evidence_opportunities', 0)} 条通过四门机会判定。"
            f"{engine_note}置信度未经人工标注校准，仅供决策参考。</footer>"
        )
    parts.append("</body></html>")
    return "".join(parts)


def _chrome_command(browser: str, profile: str, pdf_path: str, url: str) -> list[str]:
    return [
        browser,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        "--disable-crash-reporter",
        "--disable-breakpad",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        f"--user-data-dir={profile}",
        "--no-pdf-header-footer",
        "--virtual-time-budget=6000",
        f"--print-to-pdf={pdf_path}",
        url,
    ]


def render_pdf(report_html: str, out_path: Path | None = None, timeout: int = 90) -> tuple[bytes | None, str]:
    """Return (pdf_bytes, error). Uses a headless Chromium browser."""
    browser = find_browser()
    if not browser:
        return None, "No local Chrome/Edge/Chromium found; cannot render PDF directly."
    workdir = Path(tempfile.mkdtemp(prefix="agent-pdf-"))
    html_path = workdir / "report.html"
    pdf_path = workdir / "report.pdf"
    profile = workdir / "profile"
    html_path.write_text(report_html, encoding="utf-8")
    url = html_path.resolve().as_uri()
    try:
        subprocess.run(_chrome_command(browser, str(profile), str(pdf_path), url),
                       capture_output=True, timeout=timeout)
        if not pdf_path.exists() or pdf_path.stat().st_size == 0:
            return None, "The browser did not produce a PDF file."
        payload = pdf_path.read_bytes()
        if not payload.startswith(b"%PDF"):
            return None, "The generated PDF file is invalid."
        if out_path is not None:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(payload)
        return payload, ""
    except subprocess.TimeoutExpired:
        return None, "Timed out while rendering the PDF."
    except OSError as exc:
        return None, f"Failed to launch the browser: {exc}"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def safe_filename(context: dict) -> str:
    kind = context.get("kind") or ""
    en = (context.get("lang") or "en") != "zh"
    if en:
        labels = {"ranking": "ranking", "compare": "comparison", "overview": "overview", "evidence": "evidence"}
        base = labels.get(kind) or (context.get("scenarios") or ["AI_scenario"])[0]
        stamp = time.strftime("%Y%m%d-%H%M")
        cleaned = "".join(ch if (ch.isalnum() or ch in "._- ") else "_" for ch in str(base)).strip()
        return f"OpenECRS_brief_{cleaned or 'scenario'}_{stamp}.pdf"
    labels = {"ranking": "机会排名", "compare": "场景对比", "overview": "机会总览", "evidence": "证据摘录"}
    base = labels.get(kind) or (context.get("scenarios") or ["AI应用场景"])[0]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    cleaned = "".join(ch for ch in str(base) if ch.isalnum() or ch in "._- ")
    return f"OpenECRS建议书_{cleaned or 'AI应用场景'}_{stamp}.pdf"
