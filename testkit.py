"""Fake servers for testing against the REAL SDKs/HTTP stack: a Groq-compatible API that misbehaves on demand, and an OpenAlex-like API with PDFs."""
import json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def _serve(handler_cls):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls); threading.Thread(target=srv.serve_forever, daemon=True).start(); return srv, f"http://127.0.0.1:{srv.server_address[1]}"

class FakeGroq:
    """queue: list of (status, headers, body_dict). When empty, answers with `default` content."""
    def __init__(self, default='{"ok": true}', models=("llama-3.3-70b-versatile", "whisper-large-v3", "llama-3.1-8b-instant")):
        self.queue, self.requests, self.default, self.models = [], [], default, models; outer = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _send(self, status, headers, body):
                raw = json.dumps(body).encode(); self.send_response(status); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(raw)))
                for k, v in (headers or {}).items(): self.send_header(k, v)
                self.end_headers(); self.wfile.write(raw)
            def do_GET(self):
                if self.path.endswith("/models"): self._send(200, {}, {"object": "list", "data": [{"id": m, "object": "model", "created": 0, "owned_by": "x", "active": True, "context_window": 8192} for m in outer.models]})
                else: self._send(404, {}, {"error": {"message": "nope"}})
            def do_POST(self):
                n = int(self.headers.get("content-length", 0)); body = json.loads(self.rfile.read(n) or b"{}"); outer.requests.append(body)
                if outer.queue: st, hd, bd = outer.queue.pop(0); return self._send(st, hd, bd)
                self._send(200, {}, FakeGroq.ok(outer.default(body) if callable(outer.default) else outer.default))
        self.server, self.url = _serve(H)
    @staticmethod
    def ok(content, finish="stop"): return {"id": "x", "object": "chat.completion", "created": 0, "model": "m", "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish}], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
    @staticmethod
    def err(status, message, code=None, **extra): return (status, {}, {"error": dict(message=message, type="invalid_request_error", code=code, **extra)})
    def close(self): self.server.shutdown()


class FakeOpenAlex:
    """Serves /works (search + paging + a one-off 429), plus /pdf/<name>, /html and 404 for download tests."""
    def __init__(self, works, pdf_dir=None, rate_limit_first=False):
        self.works, self.pdf_dir, self.calls, self.limit = works, pdf_dir, [], rate_limit_first; outer = self
        from urllib.parse import urlparse, parse_qs
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                u = urlparse(self.path); q = parse_qs(u.query); outer.calls.append((u.path, {k: v[0] for k, v in q.items()}))
                if u.path == "/works":
                    if outer.limit: outer.limit = False; return self._raw(429, b"{}", {"retry-after": "1"})
                    per = int(q.get("per-page", ["25"])[0]); page = int(q.get("page", ["1"])[0]); chunk = outer.works[(page - 1) * per: page * per]
                    return self._raw(200, json.dumps({"results": chunk, "meta": {"count": len(outer.works)}}).encode(), {"content-type": "application/json"})
                if u.path.startswith("/pdf/") and outer.pdf_dir:
                    import pathlib; f = pathlib.Path(outer.pdf_dir) / u.path.split("/pdf/")[1]
                    return self._raw(200, f.read_bytes(), {"content-type": "application/pdf"}) if f.exists() else self._raw(404, b"no", {})
                if u.path == "/html": return self._raw(200, b"<html>Paywall</html>", {"content-type": "text/html"})
                self._raw(404, b"not found", {})
            def _raw(self, status, body, headers):
                self.send_response(status); [self.send_header(k, v) for k, v in headers.items()]; self.send_header("content-length", str(len(body))); self.end_headers(); self.wfile.write(body)
        self.server, self.url = _serve(H)
    def close(self): self.server.shutdown()

def inverted(text):
    inv = {}
    for i, w in enumerate(text.split()): inv.setdefault(w, []).append(i)
    return inv
def work(i, title, abstract, year=2022, pdf=None, cited=10):
    loc = {"pdf_url": pdf, "landing_page_url": f"https://example.org/p{i}"} if pdf else {"pdf_url": None, "landing_page_url": f"https://example.org/p{i}"}
    return {"id": f"https://openalex.org/W{i}", "title": title, "publication_year": year, "doi": f"https://doi.org/10.0000/x.{i}", "cited_by_count": cited, "abstract_inverted_index": inverted(abstract),
            "best_oa_location": loc if pdf else None, "primary_location": {"landing_page_url": f"https://example.org/p{i}", "source": {"display_name": "Synthetic Venue"}}, "open_access": {"oa_url": pdf},
            "authorships": [{"author": {"display_name": "A. Author"}}]}


def smart_content(body, fixtures_dir):
    """Content for a chat request, decided from the prompts (used to run the whole pipeline through the real SDK + HTTP)."""
    import pathlib; msgs = body.get("messages", []); system = msgs[0]["content"]; user = msgs[-1]["content"]
    if system.startswith("You extract facts"):
        text = user.split("TEXT:\n", 1)[1]; best, bestn = None, 0
        for f in pathlib.Path(fixtures_dir).glob("*.json"):
            fx = json.loads(f.read_text(encoding="utf-8")); n = sum(1 for v in fx.values() for it in v if it.get("passage") and it["passage"] in text)
            if n > bestn: best, bestn = fx, n
        if not best: return json.dumps({k: [] for k in ["problems", "methods", "datasets", "contexts", "applications", "evaluations", "results", "limitations", "future_work"]})
        return json.dumps({k: [it for it in v if it.get("passage") and it["passage"] in text] for k, v in best.items()})
    if system.startswith("You answer questions"):
        lines = [l for l in user.split("EXCERPTS:\n", 1)[1].split("\n") if l.startswith("[")]
        if "UNANSWERABLE" in user.split("EXCERPTS:\n")[0] or not lines: return json.dumps(dict(answerable=False, answer="", evidence=[]))
        l = lines[0]; return json.dumps(dict(answerable=True, answer="Mock answer " + l[1:l.index(" |")], evidence=[dict(paper=l[1:l.index(" |")], passage=l.split("] ", 1)[1].split(". ")[0] + ".")]))
    if system.startswith("You explain research gaps"): return "Mock explanation of the gap."
    if system.startswith("Answer with JSON only"): return json.dumps(dict(same=False))
    if system.startswith("You judge whether"): return json.dumps(dict(addressed=False, paper=None, quote=None))
    return "{}"
