# -*- coding: utf-8 -*-
"""Local web app for the conversational evidence agent.

Run:
    python code/agent_app.py                 # http://127.0.0.1:8765
    python code/agent_app.py --port 9000 --open

The app serves a minimal chat UI (code/agent_ui.html), the compact evidence
dataset (outputs/agent_ui/data.json) and two JSON endpoints:
    POST /api/chat   {"session": "...", "message": "..."}
    POST /api/pdf    {"session": "..."}            -> application/pdf
If no local Chrome/Edge is available, /api/pdf returns a fallback link to a
print-ready report page instead of failing.
"""
from __future__ import annotations

import argparse
import json
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from agent_engine import OpenECRSAgent, load_data
from agent_llm import (LLMError, generate_advice, load_settings, provider_label,
                       public_settings, resolve_config, save_settings, test_connection)
from agent_pdf import PDF_DIR, build_report_html, find_browser, render_pdf, safe_filename

BASE = Path(__file__).resolve().parents[1]
UI_FILE = BASE / "code" / "agent_ui.html"
DATA_FILE = BASE / "outputs" / "agent_ui" / "data.json"

SESSIONS: dict[str, dict] = {}
LOCK = threading.Lock()
AGENT: OpenECRSAgent | None = None


def get_agent() -> OpenECRSAgent:
    global AGENT
    if AGENT is None:
        AGENT = OpenECRSAgent(load_data())
    return AGENT


def _session(sid: str) -> dict:
    if not sid:
        sid = "default"
    with LOCK:
        return SESSIONS.setdefault(sid, {"turns": 0})


class Handler(BaseHTTPRequestHandler):
    server_version = "OpenECRS/1.0"

    def log_message(self, fmt, *args):  # keep the console clean
        pass

    # ------------------------------------------------------------ utilities
    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 2_000_000:
            return {}
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    # --------------------------------------------------------------- routes
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send(200, UI_FILE.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/data":
            return self._send(200, DATA_FILE.read_bytes(), "application/json; charset=utf-8")
        if path == "/api/health":
            config = resolve_config()
            return self._json(200, {"ok": True, "pdf_backend": bool(find_browser()),
                                    "data_ready": DATA_FILE.exists(),
                                    "llm_enabled": bool(config["enabled"]),
                                    "llm_ready": bool(config["enabled"] and config["api_key"])})
        if path == "/api/settings":
            return self._json(200, public_settings())
        if path == "/report":
            query = parse_qs(urlparse(self.path).query)
            sid = (query.get("sid") or ["default"])[0]
            return self._print_report(sid)
        return self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_json()
        try:
            if path == "/api/chat":
                return self._chat(body)
            if path == "/api/pdf":
                return self._pdf(body)
            if path == "/api/settings":
                return self._saveSettings(body)
            if path == "/api/test":
                return self._testConnection(body)
        except Exception as exc:  # never kill the connection silently
            return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
        return self._json(404, {"error": "not found"})

    # -------------------------------------------------------------- handlers
    def _chat(self, body: dict):
        message = str(body.get("message") or "").strip()
        if not message:
            return self._json(400, {"error": "message is required"})
        sid = str(body.get("session") or "default")
        lang = str(body.get("lang") or "en").lower()
        if lang not in ("en", "zh"):
            lang = "en"
        state = _session(sid)
        try:
            answer = get_agent().answer(message, state, lang=lang)
            answer["engine"] = self._apply_llm(answer, message)
            # keep the localised payload for the PDF endpoint (session internals stay keyed in Chinese)
            state["last_answer"] = answer
        except Exception as exc:  # keep the UI alive, surface the reason
            return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
        return self._json(200, answer)

    @staticmethod
    def _apply_llm(answer: dict, message: str) -> dict:
        """Rewrite advice/reply with the configured model; never break the answer."""
        config = resolve_config()
        if not config["enabled"]:
            return {"kind": "rule", "model": "", "provider": ""}
        if not config["api_key"]:
            error = "已启用大模型，但没有配置 API Key，本次已回退规则结果。"
            answer["llm_error"] = error
            return {"kind": "rule", "model": "", "provider": "", "error": error}
        try:
            llm = generate_advice(answer, message, config, lang=answer.get("lang") or "en")
        except LLMError as exc:
            answer["llm_error"] = str(exc)
            return {"kind": "rule", "model": "", "provider": "", "error": str(exc)}
        answer["advice"] = llm["advice"]
        answer["reply"] = llm["reply"]
        if llm.get("partial"):
            answer["llm_error"] = "模型返回的 JSON 不完整，已直接采用模型文本。"
        return {"kind": "llm", "model": llm["model"], "provider": provider_label(config["base_url"]),
                "latency_ms": llm["latency_ms"], "usage": llm.get("usage") or {},
                "partial": bool(llm.get("partial"))}

    def _pdf(self, body: dict):
        sid = str(body.get("session") or "default")
        state = _session(sid)
        answer = state.get("last_answer")
        if not answer:
            return self._json(400, {"error": "先进行一次对话，再导出 PDF"})
        agent = get_agent()
        context = agent.report_context(answer)
        context["engine"] = answer.get("engine") or {"kind": "rule"}
        report_html = build_report_html(context)
        filename = safe_filename(context)
        out_path = PDF_DIR / filename
        payload, error = render_pdf(report_html, out_path)
        if payload is None:
            return self._json(200, {"fallback": f"/report?sid={sid}", "filename": filename, "hint": error})
        return self._send(200, payload, "application/pdf",
                          {"Content-Disposition": f"attachment; filename*=UTF-8''{_quote(filename)}",
                           "X-PDF-Path": f"outputs/agent_ui/pdf/{_quote(filename)}"})

    def _saveSettings(self, body: dict):
        try:
            save_settings(body, clear_key=bool(body.get("clear_key")))
        except LLMError as exc:
            return self._json(400, {"error": str(exc)})
        return self._json(200, public_settings())

    def _testConnection(self, body: dict):
        settings = load_settings()
        merged = dict(settings)
        for key in ("base_url", "model", "temperature", "max_tokens", "timeout"):
            if body.get(key) not in (None, ""):
                merged[key] = body[key]
        if body.get("api_key"):
            merged["api_key"] = body["api_key"]
        config = resolve_config(merged)
        config["enabled"] = True
        if not config["api_key"]:
            return self._json(200, {"ok": False, "model": config["model"], "latency_ms": 0,
                                    "reply": "", "error": "还没有配置 API Key"})
        return self._json(200, test_connection(config))

    def _print_report(self, sid: str):
        state = _session(sid)
        answer = state.get("last_answer")
        if not answer:
            hint = "<meta charset='utf-8'>先进行一次对话，再导出报告。"
            return self._send(200, hint.encode("utf-8"), "text/html; charset=utf-8")
        context = get_agent().report_context(answer)
        report_html = build_report_html(context)
        print_js = ("<script>window.addEventListener('load',function(){"
                    "setTimeout(function(){window.print();},350);});</script>")
        page = report_html.replace("</body>", print_js + "</body>")
        return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")


def _quote(value: str) -> str:
    from urllib.parse import quote
    return quote(value, safe="")


def find_free_port(host: str, port: int) -> int:
    for offset in range(0, 30):
        candidate = port + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, candidate))
                return candidate
            except OSError:
                continue
    raise SystemExit("没有可用端口，请用 --port 指定其它端口")


def main():
    parser = argparse.ArgumentParser(description="OpenECRS · 本地对话界面")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    parser.add_argument("--rebuild", action="store_true", help="强制从 outputs/tables/ 重建 data.json")
    args = parser.parse_args()

    if args.rebuild or not DATA_FILE.exists():
        from agent_ui_data import build
        build()

    port = find_free_port(args.host, args.port)
    url = f"http://{args.host}:{port}"
    server = ThreadingHTTPServer((args.host, port), Handler)
    print("=" * 62)
    print("  OpenECRS · AI Opportunity Radar (bilingual local agent)")
    print(f"  打开：{url}")
    print(f"  PDF 导出后端：{'本地浏览器可用' if find_browser() else '未找到浏览器（将回退到打印视图）'}")
    llm = resolve_config()
    if llm["enabled"] and llm["api_key"]:
        print(f"  大模型模式：已启用 · {llm['model']} @ {provider_label(llm['base_url'])}")
    elif llm["enabled"]:
        print("  大模型模式：已启用但缺少 API Key，将回退规则结果")
    else:
        print("  大模型模式：关闭（右上角设置里可接入 OpenAI 兼容接口）")
    print("  Ctrl+C 停止")
    print("=" * 62)
    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
