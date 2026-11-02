#!/usr/bin/env python3
"""Fetches jobs from company career boards, analyses them against the profile and scores them.

    python3 jobfinder.py fetch     # pull fresh jobs into data/jobs.json
    python3 jobfinder.py rescore   # re-analyse stored jobs after editing config
"""
import concurrent.futures as cf
import html
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
UA = {"User-Agent": "Mozilla/5.0 (personal job search)", "Accept": "application/json"}


# ---------- io ----------

def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def configs():
    return (load_json(CONFIG / "profile.json"), load_json(CONFIG / "cities.json"),
            load_json(CONFIG / "companies.json"))


def http_json(url, body=None, tries=3):
    for i in range(tries):
        try:
            data = json.dumps(body).encode() if body is not None else None
            headers = dict(UA, **({"Content-Type": "application/json"} if body is not None else {}))
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code < 500 or i == tries - 1:
                raise
            time.sleep(3 * (i + 1))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def http_text(url, tries=2):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=dict(UA, **{"Accept": "text/html,application/xhtml+xml", "Accept-Language": "en,tr;q=0.8"}))
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3)


def _first(rx, text):
    m = re.search(rx, text, re.S | re.I)
    return strip_html(m.group(1)).strip() if m else ""


def read_posting(url):
    """A single job the user chose to add (never a crawl): returns (company, ext_id, title, locations, description)."""
    li = re.search(r"linkedin\.com/.*?(?:jobs/view/(?:[^/?]*-)?|currentJobId=)(\d{6,})", url)
    if li:  # LinkedIn's public (logged-out) view of one posting
        h = http_text(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{li.group(1)}")
        title = _first(r'<h2[^>]*top-card-layout__title[^>]*>(.*?)</h2>', h)
        company = _first(r'<a[^>]*topcard__org-name-link[^>]*>(.*?)</a>', h) or _first(r'topcard__flavor">(.*?)</span>', h)
        loc = _first(r'topcard__flavor topcard__flavor--bullet[^>]*>(.*?)</span>', h)
        desc = _first(r'<div[^>]*show-more-less-html__markup[^>]*>(.*?)</div>', h)
        if not title:
            raise ValueError("LinkedIn didn't show this posting without a login")
        return company or "Unknown company", "li-" + li.group(1), title, [loc], desc
    names = {c.get("slug", "").lower(): c["name"] for c in load_json(CONFIG / "companies.json")["companies"] if c.get("slug")}
    co = lambda slug: names.get(slug.lower()) or slug.replace("-", " ").title()
    gh = re.search(r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)/jobs/(\d+)", url)
    if gh:  # Greenhouse job board API
        d = http_json(f"https://boards-api.greenhouse.io/v1/boards/{gh.group(1)}/jobs/{gh.group(2)}")
        return co(gh.group(1)), d["id"], d["title"], [(d.get("location") or {}).get("name", "")], strip_html(d.get("content", ""))
    lv = re.search(r"jobs\.lever\.co/([\w-]+)/([0-9a-f-]{36})", url)
    if lv:
        d = http_json(f"https://api.lever.co/v0/postings/{lv.group(1)}/{lv.group(2)}")
        return co(lv.group(1)), d["id"], d["text"], [(d.get("categories") or {}).get("location", "")], d.get("descriptionPlain") or strip_html(d.get("description", ""))
    ab = re.search(r"jobs\.ashbyhq\.com/([\w.-]+)/([0-9a-f-]{36})", url)
    if ab:
        d = next(x for x in http_json(f"https://api.ashbyhq.com/posting-api/job-board/{ab.group(1)}")["jobs"] if x["id"] == ab.group(2))
        return co(ab.group(1)), d["id"], d["title"], [d.get("location", "")], strip_html(d.get("descriptionHtml", ""))
    h = http_text(url)
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', h, re.S | re.I):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for d in items:
            if isinstance(d, dict) and "JobPosting" in str(d.get("@type")):
                org = d.get("hiringOrganization") or {}
                locs = d.get("jobLocation") or []
                locs = locs if isinstance(locs, list) else [locs]
                places = []
                for l in locs:
                    a = (l or {}).get("address") or {}
                    a = a if isinstance(a, dict) else {"addressLocality": str(a)}
                    places.append(", ".join(x for x in (a.get("addressLocality"), a.get("addressCountry") if isinstance(a.get("addressCountry"), str) else (a.get("addressCountry") or {}).get("name")) if x))
                if d.get("jobLocationType") == "TELECOMMUTE":
                    places.append("Remote")
                return (org.get("name") if isinstance(org, dict) else str(org)) or urllib.parse.urlparse(url).hostname, \
                    re.sub(r"\W+", "-", url.split("?")[0][-60:]), d.get("title", ""), places, strip_html(d.get("description", ""))
    title = _first(r'<meta[^>]*property="og:title"[^>]*content="([^"]*)"', h) or _first(r"<title>(.*?)</title>", h)
    if not title:
        raise ValueError("No job details found on that page")
    site = _first(r'<meta[^>]*property="og:site_name"[^>]*content="([^"]*)"', h)
    return site or urllib.parse.urlparse(url).hostname.replace("www.", ""), re.sub(r"\W+", "-", url.split("?")[0][-60:]), title, [], strip_html(h)[:8000]


def add_url(url, pasted=""):
    """Adds one posting to manual_jobs.json and rescores. Pasted text (the job description copied by hand) fills gaps."""
    try:
        company, ext, title, locs, desc = read_posting(url)
    except Exception as e:
        if not pasted.strip():
            raise
        lines = [l.strip() for l in pasted.strip().splitlines() if l.strip()]
        company, ext, title, locs, desc = "Unknown company", re.sub(r"\W+", "-", url[-40:]), lines[0][:120], [], pasted
    if len(desc) < 200 and pasted.strip():
        desc = pasted
    j = job(company, ext, title, locs, url, desc)
    j["manual"] = True
    manual = [m for m in load_json(DATA / "manual_jobs.json", []) if m["id"] != j["id"]] + [j]
    save_json(DATA / "manual_jobs.json", manual)
    rescore()
    added = next((x for x in load_json(DATA / "jobs.json", []) if x["id"] == j["id"]), j)
    return added


def strip_html(s):
    if not s:
        return ""
    s = html.unescape(html.unescape(s))
    s = re.sub(r"(?i)<li[^>]*>", "\n• ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h\d>|</ul>|</li>", "\n", s)
    s = re.sub(r"(?i)<h\d[^>]*>", "\n\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n\s*\n+", "\n\n", s)
    return s.strip()


# ---------- filters used while fetching ----------

class Matcher:
    def __init__(self, profile, cities):
        self.inc = re.compile("|".join(profile["title_include"]), re.I)
        self.exc = re.compile("|".join(profile["title_exclude"]), re.I)
        self.cities = cities["cities"]
        self.remote = cities.get("remote", {})

    def title_ok(self, title):
        return bool(self.inc.search(title)) and not self.exc.search(title)

    def location(self, *texts):
        """Best-priority city matched in any of the location strings, or remote, or None."""
        text = " | ".join(t for t in texts if t).lower()
        best = None
        for c in self.cities:
            if any(re.search(r"\b" + re.escape(a) + r"\b", text) for a in c["aliases"]):
                if best is None or c["priority"] < best["priority"]:
                    best = c
        if best:
            return {"city": best["name"], "priority": best["priority"], "remote": False, "home": bool(best.get("home"))}
        if self.remote.get("enabled") and any(p in text for p in self.remote.get("patterns", [])):
            return {"city": "Remote (from TR)", "priority": self.remote.get("priority", 6), "remote": True}
        return None


def job(company, ext_id, title, locations, url, description, posted=None, workplace=None, salary_text=None, apply_url=None):
    return {
        "id": re.sub(r"[^a-z0-9]+", "-", f"{company}-{ext_id}".lower()).strip("-"),
        "company": company, "title": title.strip(), "locations": [l for l in locations if l],
        "url": url, "apply_url": apply_url or url, "description": description,
        "posted": posted, "workplace": workplace, "salary_text": salary_text,
    }


# ---------- per-ATS fetchers ----------

def fetch_greenhouse(c, m):
    # the light list first; full content only for matching jobs (content=true on big boards is several MB)
    base = f"https://boards-api.greenhouse.io/v1/boards/{c['slug']}/jobs"
    out = []
    for j in http_json(base).get("jobs", []):
        locs = [j.get("location", {}).get("name", "")]
        if not m.title_ok(j["title"]) or not m.location(*locs):
            continue
        det = http_json(f"{base}/{j['id']}")
        locs += [o.get("name", "") for o in det.get("offices", [])]
        out.append(job(c["name"], j["id"], j["title"], locs, j["absolute_url"], strip_html(det.get("content")),
                       j.get("updated_at")))
    return out


def fetch_lever(c, m):
    d = http_json(f"https://api.lever.co/v0/postings/{c['slug']}?mode=json")
    out = []
    for j in d:
        cat = j.get("categories", {})
        locs = [cat.get("location", "")] + (cat.get("allLocations") or [])
        if not m.title_ok(j["text"]) or not m.location(*locs, j.get("workplaceType", "")):
            continue
        parts = [j.get("descriptionPlain", "")]
        for l in j.get("lists", []):
            parts.append(l.get("text", "") + "\n" + strip_html(l.get("content", "")))
        parts.append(j.get("additionalPlain", ""))
        sal = j.get("salaryRange")
        sal_text = f"{sal['currency']} {sal['min']} - {sal['max']} {sal.get('interval', '')}" if sal else None
        posted = datetime.fromtimestamp(j["createdAt"] / 1000, timezone.utc).isoformat() if j.get("createdAt") else None
        out.append(job(c["name"], j["id"], j["text"], locs, j["hostedUrl"], "\n\n".join(parts), posted,
                       j.get("workplaceType"), sal_text, j.get("applyUrl")))
    return out


def fetch_ashby(c, m):
    d = http_json(f"https://api.ashbyhq.com/posting-api/job-board/{c['slug']}?includeCompensation=true")
    out = []
    for j in d.get("jobs", []):
        locs = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations", [])]
        if j.get("isRemote"):
            locs.append("remote")
        if not m.title_ok(j["title"]) or not m.location(*locs):
            continue
        comp = j.get("compensation") or {}
        sal = comp.get("scrapeableCompensationSalarySummary") or comp.get("compensationTierSummary")
        out.append(job(c["name"], j["id"], j["title"], locs, j["jobUrl"],
                       j.get("descriptionPlain") or strip_html(j.get("descriptionHtml")), j.get("publishedAt"),
                       j.get("workplaceType"), sal, j.get("applyUrl")))
    return out


def fetch_smartrecruiters(c, m):
    base = f"https://api.smartrecruiters.com/v1/companies/{c['slug']}/postings"
    hits, offset = [], 0
    while offset < 1000:
        d = http_json(f"{base}?limit=100&offset={offset}")
        content = d.get("content", [])
        for j in content:
            loc = j.get("location", {})
            locs = [loc.get("city", ""), loc.get("country", ""), "remote" if loc.get("remote") else ""]
            if m.title_ok(j["name"]) and m.location(*locs):
                hits.append((j, locs))
        offset += 100
        if offset >= d.get("totalFound", 0):
            break
    out = []
    for j, locs in hits:
        det = http_json(f"{base}/{j['id']}")
        sec = det.get("jobAd", {}).get("sections", {})
        desc = "\n\n".join(strip_html(sec.get(k, {}).get("text", ""))
                           for k in ("jobDescription", "qualifications", "additionalInformation", "companyDescription"))
        url = det.get("postingUrl") or f"https://jobs.smartrecruiters.com/{c['slug']}/{j['id']}"
        out.append(job(c["name"], j["id"], j["name"], locs, url, desc, j.get("releasedDate"),
                       apply_url=det.get("applyUrl")))
    return out


def fetch_workday(c, m):
    base = f"https://{c['host']}/wday/cxs/{c['tenant']}/{c['site']}"
    seen, cand = set(), []
    for q in c.get("queries", ["marketing", "brand", "growth"]):
        for offset in range(0, 200, 20):
            d = http_json(f"{base}/jobs", {"limit": 20, "offset": offset, "searchText": q, "appliedFacets": {}})
            posts = d.get("jobPostings", [])
            for p in posts:
                path = p.get("externalPath")
                if not path or path in seen or not m.title_ok(p.get("title", "")):
                    continue
                seen.add(path)
                lt = p.get("locationsText", "")
                if re.search(r"\d+ locations", lt, re.I) or m.location(lt):
                    cand.append(p)
            if len(posts) < 20:
                break
    out = []
    for p in cand:
        info = http_json(base + p["externalPath"]).get("jobPostingInfo", {})
        locs = [info.get("location", "")] + (info.get("additionalLocations") or [])
        if not m.location(*locs):
            continue
        url = info.get("externalUrl") or f"https://{c['host']}/{c['site']}{p['externalPath']}"
        out.append(job(c["name"], info.get("jobReqId") or p["externalPath"], p["title"], locs, url,
                       strip_html(info.get("jobDescription")), info.get("startDate"),
                       info.get("remoteType")))
    return out


def fetch_amazon(c, m):
    out, seen = [], set()
    for q in c.get("queries", ["marketing"]):
        for cc in c.get("countries", []):
            params = urllib.parse.urlencode({"base_query": q, "normalized_country_code[]": cc,
                                             "result_limit": 100, "offset": 0, "sort": "recent"})
            d = http_json(f"https://www.amazon.jobs/en/search.json?{params}")
            for j in d.get("jobs", []):
                jid = j.get("id_icims") or j.get("job_path")
                locs = [j.get("normalized_location", ""), j.get("location", "")]
                if jid in seen or not m.title_ok(j["title"]) or not m.location(*locs):
                    continue
                seen.add(jid)
                desc = "\n\n".join([strip_html(j.get("description", "")),
                                    "BASIC QUALIFICATIONS\n" + strip_html(j.get("basic_qualifications", "")),
                                    "PREFERRED QUALIFICATIONS\n" + strip_html(j.get("preferred_qualifications", ""))])
                out.append(job(c["name"], jid, j["title"], locs, "https://www.amazon.jobs" + j["job_path"], desc,
                               j.get("posted_date")))
    return out


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby,
            "smartrecruiters": fetch_smartrecruiters, "workday": fetch_workday, "amazon": fetch_amazon}


# ---------- analysis ----------

NO_SPONSOR = [
    r"(not|unable to|cannot|can't|won't|will not|do not|don't|are not able to|aren't able to) (be able to )?(offer|provide|support|sponsor)[^.]{0,40}(visa|sponsorship|work permit)",
    r"\bno (visa )?sponsorship",
    r"sponsorship (is |will )?(not|n't) (be )?(available|provided|offered|possible)",
    r"must (already )?(have|hold|possess) (the |a |an )?(valid |existing |full |unrestricted |current )?(right|authori[sz]ation|eligibility|permission|permit)[^.]{0,25}work",
    r"(eligible|eligibility|authori[sz]ed|right) to work in (the )?[a-z ]{2,25}[^.]{0,50}(required|without|is a must|necessary|essential)",
    r"without (the need for |requiring |requirement for |the need of )?(visa |employer )?sponsorship",
    r"(eu|european) (citizenship|passport|work permit) (is )?(required|needed|mandatory)",
    r"not (in a position|able) to (sponsor|support)",
]
YES_SPONSOR = [
    r"visa sponsorship (is )?(available|provided|offered|possible)",
    r"\b(we|will|can|happy to|able to) (offer |provide )?(visa )?sponsor(ship)?\b",
    r"relocation (support|package|assistance|bonus|budget|allowance)",
    r"(support|help|assist)[^.]{0,30}(with|your) (visa|relocation|work permit)",
    r"(highly skilled migrant|kennismigrant|blue card|skilled worker visa|critical skills employment permit)",
]
FOREIGN_LANGS = ["german", "dutch", "french", "spanish", "portuguese", "italian", "swedish", "danish",
                 "norwegian", "finnish", "polish", "czech", "hungarian", "greek", "arabic", "russian",
                 "hebrew", "japanese", "mandarin", "korean", "icelandic", "estonian"]
OPERATIONAL = ["execute", "execution", "coordinat", "administrat", "schedul", "assist", "upload", "data entry",
               "ticket", "logistics", "community manage", "posting", "content calendar", "trafficking",
               "proofread", "invoice", "purchase order", "day-to-day", "operational", "support the team",
               "maintain", "update the", "track and report"]
STRATEGIC = ["strategy", "strategic", "own ", "ownership", "lead ", "roadmap", "p&l", "growth", "go-to-market",
             "positioning", "launch", "experiment", "insight", "pricing", "forecast", "budget", "vision",
             "prioriti", "define", "shape", "drive "]
TAG_RULES = [
    ("green", "B2C / Consumer", r"\bb2c\b|consumer|millions of (users|customers|people)"),
    ("green", "Marketplace", r"marketplace|two-sided"),
    ("green", "Young & social audience", r"gen ?z|young audience|creator|tiktok|instagram|social[- ]first|community-led"),
    ("green", "Work-life balance", r"work[- ]life balance|flexible (working|hours)|4[- ]day week|wellbeing"),
    ("green", "AI-focused", r"\bai\b|generative|llm|machine learning"),
    ("green", "Growth / Experiments", r"experimentation|a/b test|growth loop|funnel optimi"),
    ("red", "Fast pace / long hours", r"fast[- ]paced|high[- ]pressure|long hours|weekends|hustle|intense|demanding environment"),
    ("yellow", "Travel", r"travel(ling)? (up to )?\d+ ?%|frequent travel|extensive travel"),
]


def _sentences_with(text, pat):
    m = re.search(r"[^.\n]{0,120}" + pat + r"[^.\n]{0,80}", text)
    return m.group(0).strip() if m else None


def parse_salary(text, fx):
    if not text:
        return None
    cur_map = {"€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP", "nz$": "NZD", "nzd": "NZD", "$": "USD",
               "usd": "USD", "chf": "CHF", "dkk": "DKK", "sek": "SEK", "nok": "NOK"}
    pat = r"(nz\$|€|£|\$|eur|gbp|usd|nzd|chf|dkk|sek|nok)\s?(\d{1,3}(?:[,.\s]\d{3})+|\d{2,3}(?:[.,]\d)?\s?k)\b"
    vals, cur = [], None
    for cm, num in re.findall(pat, text.lower()):
        n = num.replace(" ", "")
        v = float(n[:-1].replace(",", ".")) * 1000 if n.endswith("k") else float(re.sub(r"[,.]", "", n))
        if 15000 <= v <= 500000:
            vals.append(v)
            cur = cur or cur_map[cm]
    if not vals:
        return None
    rate = fx.get(cur, 1)
    return {"min_eur": round(min(vals[:2]) * rate), "max_eur": round(max(vals[:2]) * rate), "currency": cur}


def key_duties(desc):
    m = re.search(r"(?i)(what you('ll| will) do|responsibilities|your role|in this role|the role|your impact|"
                  r"what you('ll| will) be doing|key accountabilities|your mission|about the job)[^\n]*\n", desc)
    chunk = desc[m.end():] if m else desc
    bullets = [b.strip(" •-–*\t") for b in re.findall(r"(?m)^\s*[•\-–*]\s*(.+)$", chunk)]
    bullets = [b for b in bullets if 25 < len(b) < 260]
    if bullets:
        return bullets[:3]
    sents = re.split(r"(?<=[.!?])\s+", chunk.strip())
    return [s for s in sents if 40 < len(s) < 260][:2]


def analyze(j, profile, cities, company, matcher):
    text = (j["title"] + "\n" + j["description"]).lower()
    fx = cities["fx_to_eur"]
    loc = matcher.location(*j["locations"], j.get("workplace") or "") or {"city": "?", "priority": 9, "remote": False}
    no_visa = loc["remote"] or loc.get("home")  # remote from Türkiye, or a job in Türkiye itself
    city = next((c for c in cities["cities"] if c["name"] == loc["city"]), None) or (
        cities.get("remote", {}) if loc["remote"] else {})

    sponsorship, evidence = "unknown", None
    for p in NO_SPONSOR:
        s = _sentences_with(text, p)
        if s:
            sponsorship, evidence = "no", s
            break
    if sponsorship == "unknown":
        for p in YES_SPONSOR:
            s = _sentences_with(text, p)
            if s:
                sponsorship, evidence = "yes", s
                break

    lang_req, lang_plus = [], []
    for lang in FOREIGN_LANGS:
        s = _sentences_with(text, r"\b" + lang + r"\b")
        if not s or not re.search(r"fluen|native|proficien|business[- ]level|professional|excellent|strong|c1|c2|"
                                  r"required|must|mandatory|essential|speak|written and spoken", s):
            continue
        (lang_plus if re.search(r"plus|advantage|nice to have|bonus|preferred|desirable|beneficial", s)
         else lang_req).append(lang.capitalize())

    wp = (j.get("workplace") or "").lower()
    if re.search(r"fully remote|remote[- ]first|100% remote", text) or "remote" in wp or loc["remote"]:
        workplace = "Remote"
    elif "hybrid" in wp or "hybrid" in text:
        workplace = "Hybrid"
    elif re.search(r"office[- ]based|on[- ]?site|in[- ]office|five days a week in|5 days (a|per) week in", text) or "onsite" in wp:
        workplace = "Office"
    else:
        workplace = "?"
    m = re.search(r"\b(\d|two|three|four|five)\s+days\s+(a|per)\s+week\s+(in|at|from)\s+(the|our)?\s*office", text)
    office_days = {"two": 2, "three": 3, "four": 4, "five": 5}.get(m.group(1), None) if m else None
    if m and m.group(1).isdigit():
        office_days = int(m.group(1))

    op = sum(text.count(w) for w in OPERATIONAL)
    st = sum(text.count(w) for w in STRATEGIC)
    role_type = "operational" if op >= 5 and op > st * 0.8 else ("strategic" if st >= 2 * max(op, 1) else "mixed")

    t = j["title"].lower()
    seniority = ("junior" if re.search(r"junior|associate|coordinator|assistant|entry|specialist i\b", t)
                 else "exec" if re.search(r"director|head of|principal|vp\b", t) else "mid-senior")
    ym = re.search(r"(\d{1,2})\s*\+?\s*(?:-|–|to)?\s*(?:\d{1,2})?\s*\+?\s*years", text)
    years = int(ym.group(1)) if ym and int(ym.group(1)) < 25 else None

    kw = profile["cv_keywords"]
    hits = sorted(((w, k) for k, w in kw.items() if k.strip() in text), reverse=True)
    raw = sum(w for w, _ in hits)
    cv_match = min(1.0, raw / 20)
    gaps = [g for g in profile.get("gap_keywords", []) if re.search(r"\b" + re.escape(g) + r"\b", text)]

    sal = parse_salary(j.get("salary_text") or "", fx) or parse_salary(text, fx)

    tags = []
    if sponsorship == "yes":
        tags.append(("green", "Sponsorship / relocation ✓"))
    elif sponsorship == "unknown" and not no_visa:
        tags.append(("yellow", "Sponsorship unclear"))
    for lang in lang_req:
        tags.append(("red", f"{lang} required"))
    for lang in lang_plus:
        tags.append(("yellow", f"{lang} a plus"))
    if "turkish" in text:
        tags.append(("green", "Turkish a plus"))
    if workplace == "Office" or (office_days or 0) >= 4:
        tags.append(("red", "Office-heavy"))
    elif workplace in ("Hybrid", "Remote"):
        tags.append(("green", workplace))
    if role_type == "operational":
        tags.append(("red", "Operational focus"))
    elif role_type == "strategic":
        tags.append(("green", "Strategic role"))
    if seniority == "junior":
        tags.append(("red", "Junior level"))
    if years and years > profile.get("max_years_ok", 8):
        tags.append(("red", f"Asks {years}+ yrs"))
    for color, label, pat in TAG_RULES:
        if re.search(pat, text):
            tags.append((color, label))

    filtered = None
    if sponsorship == "no" and not no_visa:
        filtered = "No sponsorship / work permit required"
    elif lang_req:
        filtered = "Language required: " + ", ".join(lang_req)
    elif sal and city.get("gross_min_eur") and sal["max_eur"] < city["gross_min_eur"]:
        filtered = f"Salary too low (€{sal['max_eur']:,} < min €{city['gross_min_eur']:,})"

    if sal and city.get("gross_target_eur"):
        tags.append(("green" if sal["max_eur"] >= city["gross_target_eur"] else "yellow",
                     "Salary on target" if sal["max_eur"] >= city["gross_target_eur"] else "Salary below target"))

    return {
        "city": loc["city"], "city_priority": loc["priority"], "remote": loc["remote"], "home": bool(loc.get("home")),
        "gross_target_eur": city.get("gross_target_eur"), "gross_min_eur": city.get("gross_min_eur"),
        "sponsorship": sponsorship, "sponsorship_evidence": evidence,
        "languages_required": lang_req, "workplace": workplace, "office_days": office_days,
        "role_type": role_type, "op_count": op, "strategic_count": st,
        "seniority": seniority, "years_required": years,
        "cv_match": round(cv_match, 2), "match_level": max(1, min(5, math.ceil(cv_match * 5))),
        "matched": [k.strip() for _, k in hits[:6]], "gaps": gaps[:5],
        "salary": sal, "duties": key_duties(j["description"]),
        "tags": [{"color": c, "label": l} for c, l in _dedupe(tags)],
        "company_tier": company.get("tier", "?"), "company_pay": company.get("pay", "mid"),
        "company_sponsor": company.get("sponsor", "unknown"),
        "filtered": filtered,
    }


def _dedupe(tags):
    seen, out = set(), []
    for c, l in tags:
        if l not in seen:
            seen.add(l)
            out.append((c, l))
    return out


# ---------- pipeline ----------

def analyse_all(raw_jobs, profile, cities, companies):
    matcher = Matcher(profile, cities)
    comp = {c["name"]: c for c in companies["companies"]}
    notes = load_json(DATA / "ai_notes.json", {})
    decided = decisions_any()
    out, seen = [], set()
    for j in raw_jobs:
        key = (j["company"], j["title"].lower(), tuple(sorted(j["locations"]))[:1])
        if key in seen:  # same role posted once per requisition
            continue
        seen.add(key)
        if not j.get("manual") and j["id"] not in decided and not matcher.title_ok(j["title"]):
            continue  # title filter may have been tightened since the fetch
        j["f"] = analyze(j, profile, cities, comp.get(j["company"], {}), matcher)
        n = notes.get(j["id"])
        if n:  # Claude's manual review overrides the regex guesses
            for k in ("sponsorship", "role_type", "workplace", "filtered"):
                if k in n:
                    j["f"][k] = n[k]
            j["f"]["ai_summary"] = n.get("summary")
            if n.get("scene"):  # 0–1 per scene key; the browser uses these instead of phrase matching
                j["f"]["scene"] = n["scene"]
                j["f"]["scene_note"] = n.get("scene_note")
            j["f"]["tags"] += [{"color": t.get("color", "yellow"), "label": t["label"]} for t in n.get("tags", [])]
        out.append(j)
    return out


def fetch_all(progress=print, only=None):
    profile, cities, companies = configs()
    if only:  # e.g. retry just the boards that failed last time
        companies = dict(companies, companies=[c for c in companies["companies"] if c["name"] in only])
    matcher = Matcher(profile, cities)
    raw, errors = [], {}

    def run(c):
        return c, FETCHERS[c["ats"]](c, matcher)

    old = {j["id"]: j for j in load_json(DATA / "jobs.json", [])}
    with cf.ThreadPoolExecutor(5) as ex:
        futs = {ex.submit(run, c): c for c in companies["companies"]}
        for fu in cf.as_completed(futs):
            c = futs[fu]
            try:
                raw += fu.result()[1]
                progress(f"{c['name']}: {len(fu.result()[1])} matching jobs")
            except Exception as e:
                errors[c["name"]] = str(e)[:120]
                # a failed board keeps its previous jobs instead of wiping them
                raw += [j for j in old.values() if j["company"] == c["name"] and not j.get("manual")]
                progress(f"{c['name']}: ERROR {str(e)[:80]} (keeping previous jobs)")
    fetched = {c["name"] for c in companies["companies"]}
    raw += [j for j in old.values() if j["company"] not in fetched and not j.get("manual")]
    raw += load_json(DATA / "manual_jobs.json", [])

    decisions = decisions_any()
    now = datetime.now(timezone.utc).isoformat()
    by_id = {}
    for j in raw:
        j["first_seen"] = old.get(j["id"], {}).get("first_seen", now)
        j["is_new"] = j["id"] not in old
        by_id[j["id"]] = j
    for jid, j in old.items():  # keep decided jobs even if the posting closed
        if jid not in by_id and jid in decisions:
            j["closed"] = True
            by_id[jid] = j
    jobs = analyse_all(list(by_id.values()), profile, cities, companies)
    save_json(DATA / "jobs.json", jobs)
    meta = {"last_fetch": now, "errors": errors, "count": len(jobs)}
    save_json(DATA / "meta.json", meta)
    progress(f"Done: {len(jobs)} jobs, {len(errors)} errors")
    return meta


def decisions_any():
    """Local app state when it exists (laptop), otherwise the published view (GitHub Actions)."""
    return load_json(DATA / "state.json", {}).get("decisions") or load_json(DATA / "shared_state.json", {}).get("decisions", {})


def rescore():
    profile, cities, companies = configs()
    jobs = load_json(DATA / "jobs.json", [])
    known, stamp = {j["id"] for j in jobs}, datetime.now(timezone.utc).isoformat()
    for j in load_json(DATA / "manual_jobs.json", []):  # jobs added by hand since the last fetch
        if j["id"] not in known:
            jobs.append(dict(j, first_seen=j.get("first_seen", stamp), is_new=True))
    jobs = analyse_all(jobs, profile, cities, companies)
    save_json(DATA / "jobs.json", jobs)
    return len(jobs)


STATUSES = ["Saved", "Pack requested", "Pack ready", "Applied", "Interview", "Offer", "Rejected"]


def app_data():
    """Everything the web app needs; scoring, rules and learning run in the browser."""
    profile, cities, companies = configs()
    return {"jobs": load_json(DATA / "jobs.json", []), "meta": load_json(DATA / "meta.json", {}),
            "watchlist": companies.get("watchlist", []), "statuses": STATUSES,
            "config": {"profile": profile, "cities": cities, "companies": companies},
            "shared_state": load_json(DATA / "shared_state.json")}  # Nesibe's published view, for the live site


def export_static(path):
    save_json(path, app_data())


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    if cmd == "fetch":
        fetch_all(only=sys.argv[2:] or None)
    elif cmd == "rescore":
        print(rescore(), "jobs rescored")
    elif cmd == "export":
        export_static(sys.argv[2])
    elif cmd == "add-url":  # add-url <link> [file with pasted text]; prints a one-line summary (used by the add-job workflow)
        pasted = open(sys.argv[3]).read() if len(sys.argv) > 3 else ""
        j = add_url(sys.argv[2], pasted)
        f = j.get("f", {})
        print(json.dumps({"id": j["id"], "company": j["company"], "title": j["title"], "city": f.get("city"),
                          "filtered": f.get("filtered"), "sponsorship": f.get("sponsorship")}, ensure_ascii=False))
