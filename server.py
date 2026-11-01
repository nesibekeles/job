#!/usr/bin/env python3
"""Local web app: python3 server.py  ->  http://localhost:8765

The browser does scoring, rules and learning; this server only adds what a static site can't:
fetching jobs, mirroring the app state to data/state.json (so Claude Code can read decisions),
manual job entry and serving generated application packs.
"""
import base64
import json
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.request
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
        FETCH["log"].append(f"ERROR: {e}")
    finally:
        FETCH["running"] = False


# ---- shared view: the live site (GitHub Pages) shows Nesibe's state as she left it here ----
GH = jf.ROOT / "private" / "gh"
SHARED_API = "https://api.github.com/repos/nesibekeles/job/contents/data/shared_state.json"
PUBLISH = {"timer": None, "at": None, "error": None, "tries": 0}
PUBLISH_DELAY = 90  # seconds of quiet after the last change, so a swiping session becomes one commit


def shared_view(state):
    """Everything except pack edits: cover letter drafts and form answers never leave this computer."""
    view = {k: v for k, v in state.items() if k != "packs"}
    view["published_at"] = now()
    return view


def publish_state():
    PUBLISH["timer"] = None
    PUBLISH["tries"] += 1
    try:
        token = subprocess.run([str(GH), "auth", "token"], capture_output=True, text=True, timeout=30).stdout.strip()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "jobness"}
        try:
            with urllib.request.urlopen(urllib.request.Request(SHARED_API, headers=headers), timeout=90) as r:
                sha = json.load(r)["sha"]
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            sha = None
        content = json.dumps(shared_view(jf.load_json(STATE, {})), ensure_ascii=False, indent=1).encode()
        body = {"message": "Update shared view", "content": base64.b64encode(content).decode()}
        if sha:
            body["sha"] = sha
        req = urllib.request.Request(SHARED_API, data=json.dumps(body).encode(), method="PUT",
                                     headers=dict(headers, **{"Content-Type": "application/json"}))
        urllib.request.urlopen(req, timeout=90).close()
        PUBLISH.update(at=now(), error=None, tries=0)
    except Exception as e:  # slow or flaky connection: try again a few times before giving up
        PUBLISH["error"] = str(e)[:200]
        if PUBLISH["tries"] < 5:
            schedule_publish(delay=120, retry=True)


def schedule_publish(delay=PUBLISH_DELAY, retry=False):
    if not GH.exists():
        return
    if not retry:
        PUBLISH["tries"] = 0
    if PUBLISH["timer"]:
        PUBLISH["timer"].cancel()
    PUBLISH["timer"] = threading.Timer(delay, publish_state)
    PUBLISH["timer"].daemon = True
    PUBLISH["timer"].start()


def packs_index():
    """{job_id: pack.json contents} for every prepared pack; the app renders and edits them."""
    if not PACKS.is_dir():
        return {}
    return {d.name: jf.load_json(d / "pack.json") for d in PACKS.iterdir() if (d / "pack.json").is_file()}


FEED_TEST = {
    "greenhouse": lambda c: len(jf.http_json(f"https://boards-api.greenhouse.io/v1/boards/{c['slug']}/jobs")["jobs"]),
    "lever": lambda c: len(jf.http_json(f"https://api.lever.co/v0/postings/{c['slug']}?mode=json")),
    "ashby": lambda c: len(jf.http_json(f"https://api.ashbyhq.com/posting-api/job-board/{c['slug']}")["jobs"]),
    "smartrecruiters": lambda c: jf.http_json(f"https://api.smartrecruiters.com/v1/companies/{c['slug']}/postings?limit=1")["totalFound"],
    "workday": lambda c: jf.http_json(f"https://{c['host']}/wday/cxs/{c['tenant']}/{c['site']}/jobs",
                                      {"limit": 1, "offset": 0, "searchText": "", "appliedFacets": {}})["total"],
}


def add_company(b):
    """Adds a company with a readable job feed to config/companies.json so the next fetch includes it."""
    if b.get("ats") not in FEED_TEST:
        return {"ok": False, "error": "No automatic job feed found"}, 400
    try:
        n = FEED_TEST[b["ats"]](b)
    except Exception as e:
        return {"ok": False, "error": f"Could not read the feed: {str(e)[:80]}"}, 400
    keys = ("name", "ats", "slug", "host", "tenant", "site", "tier", "pay", "sponsor", "tags", "priority")
    entry = {k: b[k] for k in keys if b.get(k) not in (None, "")}
    with LOCK:
        cfg = jf.load_json(jf.CONFIG / "companies.json")
        cfg["companies"] = [c for c in cfg["companies"] if c["name"] != b["name"]] + [entry]
        jf.save_json(jf.CONFIG / "companies.json", cfg)
    return {"ok": True, "open_roles": n}, 200


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
        if path == "/api/publish":
            return self.send_json({"at": PUBLISH["at"], "error": PUBLISH["error"], "pending": bool(PUBLISH["timer"])})
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
                queue = [d["id"] for d in b.get("decisions", {}).values() if d.get("status") == "Pack requested"]
                jf.save_json(jf.DATA / "pack_queue.json", queue)
            schedule_publish()
            return self.send_json({"ok": True})
        if path == "/api/company":
            return self.send_json(*add_company(b))
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
    print(f"Jobness is running: http://localhost:{PORT}  (Ctrl+C to stop)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    srv.serve_forever()
