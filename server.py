#!/usr/bin/env python3
"""Local web app: python3 server.py  ->  http://localhost:8765

The browser does scoring, rules and learning; this server only adds what a static site can't:
fetching jobs, mirroring the app state to data/state.json (so Claude Code can read decisions),
manual job entry and serving generated application packs.
"""
import json
import re
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import jobfinder as jf

PORT = 8765
WEB = jf.ROOT / "web"
PACKS = jf.ROOT / "packs"
STATE = jf.DATA / "state.json"
LOCK = threading.Lock()
FETCH = {"running": False, "log": []}


def now():
    return datetime.now(timezone.utc).isoformat()


def run_fetch():
    FETCH.update(running=True, log=[])
    try:
        jf.fetch_all(progress=lambda m: FETCH["log"].append(m))
    except Exception as e:
        FETCH["log"].append(f"HATA: {e}")
    finally:
        FETCH["running"] = False


def packs_index():
    if not PACKS.is_dir():
        return {}
    return {d.name: sorted(p.name for p in d.iterdir() if p.is_file()) for d in PACKS.iterdir() if d.is_dir()}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/api/data", "/data/static.json"):
            return self.send_json(jf.app_data())
        if path == "/api/state":
            return self.send_json(jf.load_json(STATE, {}))
        if path == "/api/fetch":
            return self.send_json(FETCH)
        if path == "/api/packs":
            return self.send_json(packs_index())
        if path.startswith("/packs/"):
            f = (PACKS / unquote(path[len("/packs/"):])).resolve()
            if PACKS.resolve() in f.parents and f.is_file():
                self.send_response(200)
                self.send_header("Content-Type", {".md": "text/plain; charset=utf-8", ".pdf": "application/pdf"}
                                 .get(f.suffix, "application/octet-stream"))
                self.end_headers()
                return self.wfile.write(f.read_bytes())
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        b = self.body()
        if path == "/api/state":
            with LOCK:
                jf.save_json(STATE, b)
                queue = [d["id"] for d in b.get("decisions", {}).values() if d.get("status") == "Paket istendi"]
                jf.save_json(jf.DATA / "pack_queue.json", queue)
            return self.send_json({"ok": True})
        if path == "/api/fetch":
            if not FETCH["running"]:
                threading.Thread(target=run_fetch, daemon=True).start()
            return self.send_json({"ok": True})
        if path == "/api/manual":
            with LOCK:
                j = jf.job(b["company"], "manual-" + re.sub(r"\W+", "-", b["title"].lower())[:40],
                           b["title"], [b.get("location", "")], b.get("url", ""), b.get("description", ""), now())
                j["manual"] = True
                manual = [m for m in jf.load_json(jf.DATA / "manual_jobs.json", []) if m["id"] != j["id"]] + [j]
                jf.save_json(jf.DATA / "manual_jobs.json", manual)
                j["first_seen"], j["is_new"] = now(), True
                profile, cities, companies = jf.configs()
                jobs = [x for x in jf.load_json(jf.DATA / "jobs.json", []) if x["id"] != j["id"]]
                jobs += jf.analyse_all([j], profile, cities, companies)
                jf.save_json(jf.DATA / "jobs.json", jobs)
                return self.send_json({"ok": True, "id": j["id"],
                                       "location_matched": bool(jf.Matcher(profile, cities).location(*j["locations"]))})
        self.send_error(404)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Pusula çalışıyor: http://localhost:{PORT}  (durdurmak için Ctrl+C)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    srv.serve_forever()
