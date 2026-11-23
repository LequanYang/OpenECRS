# -*- coding: utf-8 -*-
"""OpenECRS local web app.

OpenECRS is an LLM-required agent: the model plans and writes every answer; the
offline tools only retrieve grounded data. Configure an OpenAI-compatible API or
a local fine-tuned adapter in Settings before chatting.

Run:
    python code/agent_app.py --open        # http://127.0.0.1:8765
"""
from __future__ import annotations

import argparse
import json
import socket
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import agent_core
import agent_pdf
import agent_providers
import agent_settings
import agent_tools

BASE = Path(__file__).resolve().parents[1]
UI_FILE = BASE / "code" / "agent_ui.html"
DATA_FILE = BASE / "outputs" / "agent_ui" / "data.json"
LOG_FILE = BASE / "outputs" / "agent_ui" / "agent.log"

SESSIONS: dict[str, dict] = {}
LOCK = threading.Lock()
DATA = None


def get_data() -> agent_tools.ScenarioData:
    global DATA
    if DATA is None:
        DATA = agent_tools.ScenarioData(agent_tools.load_data())
    return DATA


def log_event(**fields) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **fields}
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _session(sid: str) -> dict:
    sid = sid or "default"
    with LOCK:
        return SESSIONS.setdefault(sid, {"turns": 0, "history": []})


def _merge_for_test(body: dict) -> dict:
    """Apply unsaved form values on top of the saved settings (for Test)."""
    settings = agent_settings.load_settings()
    if body.get("backend") in ("api", "local"):
        settings["backend"] = body["backend"]
    for section in ("api", "local"):
        incoming = body.get(section)
        if isinstance(incoming, dict):
            for key in settings[section]:
                value = incoming.get(key)
                if value not in (None, ""):
                    settings[section][key] = value
    key = body.get("api_key") or (body.get("api") or {}).get("api_key")
    if key:
        settings["api"]["api_key"] = str(key).strip()
    return settings


class Handler(BaseHTTPRequestHandler):
    server_version = "OpenECRS/2.0"

    def log_message(self, fmt, *args):
        pass

    # ------------------------------------------------------------ utilities
    def _send(self, status, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, payload: dict):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 2_000_000:
            return {}
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
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
            info = agent_providers.provider_info()
            public = agent_settings.public_settings()
            return self._json(200, {"ok": True, "llm_ready": public["ready"],
                                    "backend": info["backend"], "model": info["model"],
                                    "pdf_backend": bool(agent_pdf.find_browser()),
                                    "data_ready": DATA_FILE.exists()})
        if path == "/api/settings":
            return self._json(200, agent_settings.public_settings())
        if path == "/report":
            query = parse_qs(urlparse(self.path).query)
            return self._print_report((query.get("sid") or ["default"])[0])
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
                return self._save_settings(body)
            if path == "/api/test":
                return self._test(body)
        except Exception as exc:  # never kill the connection silently
            log_event(route=path, ok=False, error=f"{type(exc).__name__}: {exc}")
            return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
        return self._json(404, {"error": "not found"})

    # -------------------------------------------------------------- handlers
    def _chat(self, body: dict):
        message = str(body.get("message") or "").strip()
        if not message:
            return self._json(400, {"error": "message is required"})
        session_id = str(body.get("session") or "default")
        lang = str(body.get("lang") or "en").lower()
        settings = agent_settings.load_settings()
        public = agent_settings.public_settings()
        if not public["ready"]:
            log_event(route="/api/chat", ok=False, error="llm_required", message=message[:120])
            return self._json(428, {
                "error": "OpenECRS requires an LLM. Configure an API key or a local model first.",
                "code": "llm_required",
                "hint": public["ready_detail"],
            })
        state = _session(session_id)
        try:
            runtime = agent_core.AgentRuntime(settings, get_data())
            answer = runtime.chat(message, state, lang=lang)
        except agent_providers.LLMRequiredError as exc:
            log_event(route="/api/chat", ok=False, error=str(exc), message=message[:120])
            return self._json(428, {"error": str(exc), "hint": exc.hint, "code": "llm_required"})
        except (agent_core.AgentError, agent_providers.ProviderError) as exc:
            log_event(route="/api/chat", ok=False, error=str(exc), message=message[:120])
            return self._json(502, {"error": str(exc), "code": "llm_error"})
        log_event(route="/api/chat", ok=True, lang=lang, session=session_id,
                  kind=answer.get("kind"), engine=(answer.get("engine") or {}).get("label"),
                  latency_ms=(answer.get("engine") or {}).get("latency_ms"),
                  message=message[:120])
        return self._json(200, answer)

    def _pdf(self, body: dict):
        session_id = str(body.get("session") or "default")
        state = _session(session_id)
        answer = state.get("last_answer")
        if not answer:
            return self._json(400, {"error": "Have a conversation first. / 先进行一次对话，再导出 PDF"})
        lang = str(body.get("lang") or answer.get("lang") or "en")
        context = get_data().report_context(answer, lang)
        context["engine"] = answer.get("engine") or {}
        report_html = agent_pdf.build_report_html(context)
        filename = agent_pdf.safe_filename(context)
        out_path = agent_pdf.PDF_DIR / filename
        payload, error = agent_pdf.render_pdf(report_html, out_path)
        log_event(route="/api/pdf", lang=lang, ok=bool(payload), error=error)
        if payload is None:
            return self._json(200, {"fallback": f"/report?sid={session_id}", "filename": filename, "hint": error})
        return self._send(200, payload, "application/pdf",
                          {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
                           "X-PDF-Path": f"outputs/agent_ui/pdf/{quote(filename)}"})

    def _print_report(self, session_id: str):
        state = _session(session_id)
        answer = state.get("last_answer")
        if not answer:
            hint = "<meta charset='utf-8'>Have a conversation first. / 先进行一次对话。"
            return self._send(200, hint.encode("utf-8"), "text/html; charset=utf-8")
        lang = answer.get("lang") or "en"
        context = get_data().report_context(answer, lang)
        context["engine"] = answer.get("engine") or {}
        page = agent_pdf.build_report_html(context)
        print_js = ("<script>window.addEventListener('load',function(){"
                    "setTimeout(function(){window.print();},350);});</script>")
        return self._send(200, (page.replace("</body>", print_js + "</body>")).encode("utf-8"),
                          "text/html; charset=utf-8")

    def _save_settings(self, body: dict):
        try:
            agent_settings.save_settings(body, clear_key=bool(body.get("clear_key")))
        except agent_settings.SettingsError as exc:
            log_event(route="/api/settings", ok=False, error=str(exc))
            return self._json(400, {"error": str(exc)})
        public = agent_settings.public_settings()
        log_event(route="/api/settings", ok=True, backend=public["backend"], ready=public["ready"])
        return self._json(200, public)

    def _test(self, body: dict):
        settings = _merge_for_test(body)
        result = agent_providers.test_provider(settings)
        log_event(route="/api/test", backend=result.get("backend"), ok=result.get("ok"),
                  model=result.get("model"), latency_ms=result.get("latency_ms"),
                  error=result.get("error"))
        return self._json(200, result)


def find_free_port(host: str, port: int) -> int:
    for offset in range(30):
        candidate = port + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, candidate))
                return candidate
            except OSError:
                continue
    raise SystemExit("No free port; use --port to choose another one.")


def main():
    parser = argparse.ArgumentParser(description="OpenECRS · LLM-required bilingual agent")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--rebuild", action="store_true", help="rebuild outputs/agent_ui/data.json")
    args = parser.parse_args()

    if args.rebuild or not DATA_FILE.exists():
        from agent_ui_data import build
        build()

    port = find_free_port(args.host, args.port)
    url = f"http://{args.host}:{port}"
    server = ThreadingHTTPServer((args.host, port), Handler)
    public = agent_settings.public_settings()
    info = agent_providers.provider_info()
    print("=" * 66)
    print("  OpenECRS · LLM-required evidence agent")
    print(f"  Open: {url}")
    print(f"  Backend: {public['backend']} · {info['label']}")
    if public["ready"]:
        print("  LLM: ready")
    else:
        print(f"  LLM: NOT configured — open Settings first ({public['ready_detail']})")
    print(f"  PDF: {'local browser found' if agent_pdf.find_browser() else 'no browser (print fallback)'}")
    print("  Ctrl+C to stop")
    print("=" * 66)
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
