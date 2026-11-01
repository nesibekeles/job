#!/usr/bin/env python3
"""Builds the resume PDF of an application pack.

    python3 packs.py <job_id>    # packs/<job_id>/pack.json  ->  packs/<job_id>/<Name>_CV_<Company>.pdf
    python3 packs.py             # every pack

pack.json["resume"] holds only what differs from private/resume_base.json (top-level keys replace the base).
The layout mirrors the original Word CV; Chrome prints it so fonts and spacing match.
"""
import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKS = ROOT / "packs"
BASE = ROOT / "private" / "resume_base.json"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CALIBRI = "/Applications/Microsoft Word.app/Contents/Resources/DFonts"

CSS = """
@font-face { font-family: Cal; src: url("file://%(f)s/Calibri.ttf"); }
@font-face { font-family: Cal; font-weight: bold; src: url("file://%(f)s/Calibrib.ttf"); }
@font-face { font-family: Cal; font-style: italic; src: url("file://%(f)s/Calibrii.ttf"); }
@page { size: A4; margin: 10mm 14mm 9mm; }
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: Cal, Calibri, Carlito, sans-serif; font-size: 9.5pt; line-height: 1.25; color: #000; }
h1 { font-size: 18pt; font-weight: bold; letter-spacing: .2px; }
.headline { color: #595959; font-size: 10.5pt; margin-top: 1px; }
.contact { font-size: 9.3pt; margin-top: 1px; }
h2 { font-size: 9.3pt; font-weight: bold; text-transform: uppercase; border-bottom: 1.4px solid #000; padding-bottom: 1px; margin: 9px 0 4px; }
.profile, .line { text-align: justify; }
.job { margin-top: 5px; }
.row { display: flex; justify-content: space-between; align-items: baseline; }
.row b { font-weight: bold; }
.row i, .org { font-style: italic; color: #595959; }
.org { font-size: 9pt; }
ul { margin: 1px 0 0 22px; }
li { margin: 0.5px 0; padding-left: 4px; text-align: justify; }
li::marker { content: "●  "; font-size: 7pt; }
"""


def esc(s):
    return html.escape(str(s))


def render(r, title="Resume"):
    dot = "  •  "
    parts = [f"<h1>{esc(r['name'])}</h1>", f"<div class='headline'>{esc(r['headline'])}</div>",
             f"<div class='contact'>{'&nbsp;&nbsp;|&nbsp;&nbsp;'.join(esc(c) for c in r['contact'])}</div>",
             "<h2>Profile</h2>", f"<div class='profile'>{esc(r['profile'])}</div>",
             "<h2>Core Expertise</h2>", f"<div class='line'>{esc(dot.join(r['expertise']))}</div>",
             "<h2>Work Experience</h2>"]
    for x in r["experience"]:
        parts.append(f"<div class='job'><div class='row'><b>{esc(x['title'])}</b><i>{esc(x['dates'])}</i></div>"
                     f"<div class='org'>{esc(x['org'])}</div><ul>{''.join(f'<li>{esc(b)}</li>' for b in x['bullets'])}</ul></div>")
    parts.append("<h2>Education</h2>")
    for e in r["education"]:
        parts.append(f"<div class='row'><b>{esc(e['degree'])}</b><i>{esc(e['dates'])}</i></div><div>{esc(e['detail'])}</div>")
    parts += ["<h2>Skills &amp; Languages</h2>",
              f"<div class='line'>{esc(dot.join(r['skills']))}&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;Languages: {esc(r['languages'])}</div>",
              "<h2>Interests</h2>", f"<div class='line'>{esc(dot.join(r['interests']))}</div>"]
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{esc(title)}</title><style>{CSS % {'f': CALIBRI.replace(' ', '%20')}}</style>"
            f"</head><body>{''.join(parts)}</body></html>")


def pdf_pages(path):
    return len(re.findall(rb"/Type\s*/Page(?!s)", Path(path).read_bytes()))


def build(job_id):
    folder = PACKS / job_id
    pack = json.loads((folder / "pack.json").read_text(encoding="utf-8"))
    resume = {**json.loads(BASE.read_text(encoding="utf-8")), **pack.get("resume", {})}
    out = folder / pack["resume_file"]
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "resume.html"
        src.write_text(render(resume, out.stem), encoding="utf-8")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--allow-file-access-from-files",
                        f"--user-data-dir={tmp}/profile", f"--print-to-pdf={out}", src.as_uri()],
                       check=True, capture_output=True, timeout=120)
    pages = pdf_pages(out)
    print(f"{out.name}: {pages} page{'s' if pages > 1 else ''}" + ("  <-- longer than one page, shorten it" if pages > 1 else ""))
    return pages


if __name__ == "__main__":
    ids = sys.argv[1:] or [p.name for p in PACKS.iterdir() if (p / "pack.json").exists()]
    for i in ids:
        build(i)
