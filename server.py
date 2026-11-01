#!/usr/bin/env python3
"""Local web app: python3 server.py  ->  http://localhost:8765"""
import json
import re
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

import jobfinder as jf

PORT = 8765
WEB = jf.ROOT / "web"
PACKS = jf.ROOT / "packs"
LOCK = threading.Lock()
FETCH = {"running": False, "log": []}
STATUSES = jf.STATUSES


def now():
    return datetime.now(timezone.utc).isoformat()


def state():
    jobs = jf.load_json(jf.DATA / "jobs.json", [])
    decisions = jf.load_json(jf.DATA / "decisions.json", {})
    return jobs, decisions


def jobs_payload():
    jobs, decisions = state()
    by_id = {j["id"]: j for j in jobs}
    model = jf.learn(by_id, decisions)
    out = []
    for j in jobs:
        score, adj = jf.final_score(j, model)
        d = decisions.get(j["id"])
        pack = PACKS / j["id"]
        out.append(_merge(j, score, adj, d, pack))
    out.sort(key=lambda x: -x["score"])
    top = sorted(model["weights"].items(), key=lambda kv: kv[1])
    return {"jobs": out, "model": {**model, "top_neg": top[:12], "top_pos": top[::-1][:12]},
            "meta": jf.load_json(jf.DATA / "meta.json", {}), "fetch": FETCH,
            "watchlist": jf.load_json(jf.CONFIG / "companies.json", {}).get("watchlist", []),
            "statuses": STATUSES}


def _merge(j, score, adj, d, pack):
    x = {k: v for k, v in j.items() if k != "description"}
    x.update(score=score, learned_adj=adj, decision=d,
             pack_files=sorted(p.name for p in pack.iterdir()) if pack.is_dir() else [])
    return x


def run_fetch():
    FETCH.update(running=True, log=[])
    try:
        jf.fetch_all(progress=lambda m: FETCH["log"].append(m))
    except Exception as e:
        FETCH["log"].append(f"HATA: {e}")
    finally:
        FETCH["running"] = False


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
        if path == "/api/jobs":
            return self.send_json(jobs_payload())
        if path.startswith("/api/job/"):
            jid = unquote(path.split("/")[-1])
            j = next((j for j in state()[0] if j["id"] == jid), None)
            return self.send_json(j or {}, 200 if j else 404)
        if path.startswith("/api/config/"):
            name = path.split("/")[-1]
            if name in ("profile", "cities", "companies"):
                return self.send_json({"text": (jf.CONFIG / f"{name}.json").read_text(encoding="utf-8")})
        if path == "/api/fetch":
            return self.send_json(FETCH)
        if path.startswith("/packs/"):
            f = (PACKS / unquote(path[len("/packs/"):])).resolve()
            if PACKS.resolve() in f.parents and f.is_file():
                data = f.read_bytes()
                self.send_response(200)
                ctype = {"md": "text/plain; charset=utf-8", "txt": "text/plain; charset=utf-8",
                         "pdf": "application/pdf"}.get(f.suffix[1:], "application/octet-stream")
                self.send_header("Content-Type", ctype)
                self.end_headers()
                return self.wfile.write(data)
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        b = self.body()
        with LOCK:
            if path == "/api/decision":
                decisions = jf.load_json(jf.DATA / "decisions.json", {})
                prev = decisions.get(b["id"], {})
                decisions[b["id"]] = {
                    "id": b["id"], "decision": b["decision"], "reasons": b.get("reasons", []),
                    "note": b.get("note", ""), "at": now(),
                    "status": "Kaydedildi" if b["decision"] == "like" else None,
                } | ({"status": prev.get("status")} if prev.get("decision") == "like" == b["decision"] else {})
                jf.save_json(jf.DATA / "decisions.json", decisions)
                return self.send_json({"ok": True})
            if path == "/api/undo":
                decisions = jf.load_json(jf.DATA / "decisions.json", {})
                decisions.pop(b["id"], None)
                jf.save_json(jf.DATA / "decisions.json", decisions)
                return self.send_json({"ok": True})
            if path == "/api/status":
                decisions = jf.load_json(jf.DATA / "decisions.json", {})
                if b["id"] in decisions:
                    decisions[b["id"]]["status"] = b["status"]
                    decisions[b["id"]]["status_at"] = now()
                    jf.save_json(jf.DATA / "decisions.json", decisions)
                if b["status"] == "Paket istendi":
                    q = jf.load_json(jf.DATA / "pack_queue.json", [])
                    if b["id"] not in q:
                        q.append(b["id"])
                    jf.save_json(jf.DATA / "pack_queue.json", q)
                return self.send_json({"ok": True})
            if path.startswith("/api/config/"):
                name = path.split("/")[-1]
                try:
                    json.loads(b["text"])
                except json.JSONDecodeError as e:
                    return self.send_json({"ok": False, "error": f"JSON hatası: satır {e.lineno}, {e.msg}"}, 400)
                (jf.CONFIG / f"{name}.json").write_text(b["text"], encoding="utf-8")
                n = jf.rescore()
                return self.send_json({"ok": True, "rescored": n})
            if path == "/api/manual":
                manual = jf.load_json(jf.DATA / "manual_jobs.json", [])
                j = jf.job(b["company"], "manual-" + re.sub(r"\W+", "-", b["title"].lower())[:40],
                           b["title"], [b.get("location", "")], b.get("url", ""), b.get("description", ""), now())
                j["manual"] = True
                manual = [m for m in manual if m["id"] != j["id"]] + [j]
                jf.save_json(jf.DATA / "manual_jobs.json", manual)
                jobs = [x for x in jf.load_json(jf.DATA / "jobs.json", []) if x["id"] != j["id"]]
                j["first_seen"], j["is_new"] = now(), True
                profile, cities, companies = jf.configs()
                matcher = jf.Matcher(profile, cities)
                loc_ok = matcher.location(*j["locations"])
                jobs += jf.analyse_all([j], profile, cities, companies)
                jf.save_json(jf.DATA / "jobs.json", jobs)
                return self.send_json({"ok": True, "id": j["id"], "location_matched": bool(loc_ok)})
        if path == "/api/fetch":
            if not FETCH["running"]:
                threading.Thread(target=run_fetch, daemon=True).start()
            return self.send_json({"ok": True})
        self.send_error(404)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"İş bulucu çalışıyor: http://localhost:{PORT}  (durdurmak için Ctrl+C)")
    if "--no-browser" not in __import__("sys").argv:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    srv.serve_forever()
