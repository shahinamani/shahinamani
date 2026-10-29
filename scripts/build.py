#!/usr/bin/env python3
"""Build the SVG assets used by the profile README.

    python3 scripts/build.py                  # rebuild from cached stats
    python3 scripts/build.py --refresh-stats  # fetch fresh numbers with `gh` first

Requires: Python 3, fontTools, Pillow. Fonts are embedded as subsets because
GitHub shows SVGs through <img>, where external fonts and images never load.
"""
import base64
import datetime as dt
import io
import json
import math
import random
import subprocess
import sys
from html import escape
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "scripts"
OUT = ROOT / "assets"
LOGIN = "shahinamani"
W = 840

# ---------------------------------------------------------------- palette

THEMES = {
    "dark": dict(
        text="#e6edf3", text2="#aab3bf", muted="#7d8590", line="#262c36",
        card="#0f141a", border="#262c36", accent="#5b9ef0", chip="#151b23",
        chipb="#30363d", icon="#c3cbd5", bar="#1f2a37",
    ),
    "light": dict(
        text="#1f2328", text2="#4b5561", muted="#6e7781", line="#d8dee4",
        card="#ffffff", border="#d0d7de", accent="#0969da", chip="#f6f8fa",
        chipb="#d0d7de", icon="#424a53", bar="#dde3ea",
    ),
}
# Dashboard illustrations stay dark in both themes, like screenshots would.
D = dict(bg="#0a0e14", panel="#10161e", line="#1c2430", dim="#263040",
         txt="#3a4656", acc="#4c8ff0", acc2="#2c64b8", glow="#7db8ff",
         up="#3f9d6a", down="#c9524c")

FONT_STACK = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"

# ---------------------------------------------------------------- fonts

_inst = {}


def _font_bytes(weight, opsz):
    key = (weight, opsz)
    if key not in _inst:
        vf = TTFont(SRC / "fonts" / "InterVariable.ttf")
        f = instancer.instantiateVariableFont(vf, {"wght": weight, "opsz": opsz})
        buf = io.BytesIO()
        f.save(buf)
        _inst[key] = buf.getvalue()
    return _inst[key]


_metrics = {}


def text_width(s, size, weight=400, ls=0.0, opsz=14):
    key = (weight, opsz)
    if key not in _metrics:
        f = TTFont(io.BytesIO(_font_bytes(weight, opsz)))
        _metrics[key] = (f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm)
    cmap, hmtx, upm = _metrics[key]
    units = sum(hmtx[cmap.get(ord(c), cmap[32])][0] for c in s)
    return units * size / upm + ls * len(s)


def wrap(s, size, max_w, weight=400):
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if cur and text_width(trial, size, weight) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def font_face(weight, opsz, chars):
    f = TTFont(io.BytesIO(_font_bytes(weight, opsz)))
    opts = subset.Options()
    opts.flavor = "woff"
    opts.layout_features = ["kern", "liga", "calt"]
    opts.name_IDs = []
    opts.hinting = False
    opts.desubroutinize = True
    sub = subset.Subsetter(opts)
    sub.populate(text="".join(sorted(chars | {" "})))
    sub.subset(f)
    f.flavor = "woff"
    buf = io.BytesIO()
    f.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return (f"@font-face{{font-family:'f{weight}-{opsz}';"
            f"src:url(data:font/woff;base64,{b64}) format('woff')}}")


# ---------------------------------------------------------------- svg doc

class Doc:
    def __init__(self, w, h, title, desc):
        self.w, self.h, self.title, self.desc = w, h, title, desc
        self.parts, self.defs, self.css, self.used = [], [], [], {}

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, size, fill, weight=400, ls=0.0, anchor="start",
             opsz=14, extra=""):
        self.used.setdefault((weight, opsz), set()).update(s)
        fam = f"'f{weight}-{opsz}', {FONT_STACK}"
        lsa = f' letter-spacing="{ls:g}"' if ls else ""
        anc = f' text-anchor="{anchor}"' if anchor != "start" else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{fam}" '
                 f'font-size="{size}" font-weight="{weight}" fill="{fill}"'
                 f'{lsa}{anc} {extra}>{escape(s)}</text>')

    def render(self):
        faces = "".join(font_face(w, o, c) for (w, o), c in sorted(self.used.items()))
        reduce = ("@media (prefers-reduced-motion: reduce){*{animation:none!important;"
                  "transition:none!important}}")
        style = f"<style>{faces}{''.join(self.css)}{reduce}</style>"
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
                f'viewBox="0 0 {self.w} {self.h}" role="img" aria-labelledby="t d">'
                f'<title id="t">{escape(self.title)}</title><desc id="d">{escape(self.desc)}</desc>'
                f'{style}<defs>{"".join(self.defs)}</defs>{"".join(self.parts)}</svg>')


def write(name, doc):
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(doc.render(), encoding="utf-8")
    print(f"  {name:28s} {(OUT / name).stat().st_size / 1024:6.1f} KB")


def section_heading(doc, x, y, num, label, t, width):
    doc.text(x, y, num, 14, t["accent"], 400)
    nx = x + text_width(num, 14) + 12
    doc.add(f'<line x1="{nx:.1f}" y1="{y - 13}" x2="{nx:.1f}" y2="{y + 3}" stroke="{t["line"]}"/>')
    doc.text(nx + 13, y, label, 15, t["text"], 600, ls=0.6)
    doc.add(f'<line x1="{x}" y1="{y + 14}" x2="{x + width}" y2="{y + 14}" stroke="{t["line"]}"/>')


# ---------------------------------------------------------------- icons

def brand_icon(name, x, y, size, color):
    raw = (SRC / "icons" / f"{name}.svg").read_text()
    d = raw.split(' d="', 1)[1].split('"', 1)[0]
    s = size / 24
    return f'<path transform="translate({x:.1f} {y:.1f}) scale({s:.4f})" d="{d}" fill="{color}"/>'


def line_icon(kind, x, y, c):
    """18x18 outline icons drawn for this profile."""
    g = f'<g transform="translate({x:.1f} {y:.1f})" fill="none" stroke="{c}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
    if kind == "agents":  # processor
        b = ('<rect x="4" y="4" width="10" height="10" rx="2"/><rect x="7" y="7" width="4" height="4" rx=".6"/>'
             + "".join(f'<path d="M{p} 1.5v2.5M{p} 14v2.5M1.5 {p}h2.5M14 {p}h2.5"/>' for p in (7, 11)))
    elif kind == "code":
        b = '<path d="M5.5 4.5 1.5 9l4 4.5M12.5 4.5l4 4.5-4 4.5M10.5 3l-3 12"/>'
    elif kind == "layers":
        b = '<path d="M9 2 16.5 6 9 10 1.5 6z"/><path d="M1.5 9.5 9 13.5l7.5-4"/><path d="M1.5 13 9 17l7.5-4"/>'
    elif kind == "enterprise":
        b = ('<rect x="2" y="2" width="6" height="6" rx="1.2"/><rect x="10" y="2" width="6" height="6" rx="1.2"/>'
             '<rect x="2" y="10" width="6" height="6" rx="1.2"/><rect x="10" y="10" width="6" height="6" rx="1.2"/>')
    elif kind == "fintech":
        b = '<path d="M2 16.5h14"/><path d="M4 13V9M8 13V5M12 13V7.5M16 13V2.5"/>'
    elif kind == "risk":
        b = '<path d="M2 13.5a7 7 0 0 1 14 0"/><path d="M9 13.5l3.5-4.5"/><circle cx="9" cy="13.5" r="1"/>'
    elif kind == "shield":
        b = '<path d="M9 1.8 15.5 4.3v4.4c0 3.9-2.7 6.6-6.5 7.7-3.8-1.1-6.5-3.8-6.5-7.7V4.3z"/><path d="m6.3 9 1.9 1.9 3.6-3.7"/>'
    elif kind == "ops":  # gear
        pts = []
        for i in range(16):
            a = math.pi * 2 * i / 16
            r = 8 if i % 2 == 0 else 6.2
            pts.append(f"{9 + r * math.cos(a):.2f},{9 + r * math.sin(a):.2f}")
        b = f'<polygon points="{" ".join(pts)}"/><circle cx="9" cy="9" r="2.6"/>'
    elif kind == "pin":
        b = '<path d="M9 16.5s5.5-5 5.5-9.2a5.5 5.5 0 0 0-11 0C3.5 11.5 9 16.5 9 16.5z"/><circle cx="9" cy="7.3" r="2"/>'
    elif kind == "arrow":
        b = '<path d="M4 9h10M10 5l4 4-4 4"/>'
    elif kind == "pulse":
        b = '<path d="M1.5 9.5h3.5l2-5 4 9 2-4h3.5"/>'
    elif kind == "repo":
        b = '<ellipse cx="9" cy="4" rx="6" ry="2.3"/><path d="M3 4v10c0 1.3 2.7 2.3 6 2.3s6-1 6-2.3V4"/><path d="M3 9c0 1.3 2.7 2.3 6 2.3s6-1 6-2.3"/>'
    elif kind == "calendar":
        b = '<rect x="2" y="3.5" width="14" height="12.5" rx="2"/><path d="M2 7.5h14M6 1.8v3.4M12 1.8v3.4"/>'
    elif kind == "bars":
        b = '<path d="M3 16V11M7 16V8M11 16V5M15 16V2"/>'
    else:
        raise ValueError(kind)
    return g + b + "</g>"


# ---------------------------------------------------------------- data

def refresh_stats():
    q = """{ user(login:"%s") { createdAt
      repositories(ownerAffiliations:OWNER) { totalCount }
      contributionsCollection { contributionCalendar { totalContributions
        weeks { contributionDays { date contributionCount } } } } } }""" % LOGIN
    out = subprocess.run(["gh", "api", "graphql", "-f", f"query={q}"],
                         check=True, capture_output=True, text=True).stdout
    u = json.loads(out)["data"]["user"]
    cal = u["contributionsCollection"]["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    monthly = {}
    for d in days:
        monthly[d["date"][:7]] = monthly.get(d["date"][:7], 0) + d["contributionCount"]
    data = dict(
        as_of=dt.date.today().isoformat(),
        member_since=u["createdAt"][:4],
        repositories=u["repositories"]["totalCount"],
        contributions=cal["totalContributions"],
        active_days=sum(1 for d in days if d["contributionCount"] > 0),
        monthly=[[k, monthly[k]] for k in sorted(monthly)][-12:],
    )
    (SRC / "data" / "stats.json").write_text(json.dumps(data, indent=2) + "\n")
    return data


def load_stats():
    return json.loads((SRC / "data" / "stats.json").read_text())


# ---------------------------------------------------------------- hero

HERO_TAGS = ["AI SYSTEMS", "FULL-STACK", "PRODUCT ARCHITECTURE",
             "FINTECH & TRADING", "AUTOMATION", "SECURITY & MONITORING"]


def build_hero():
    H = 240
    doc = Doc(W, H, "Shahin Amani — AI Developer & Product Builder",
              "Building intelligent software products, scalable platforms and operational "
              "systems for real-world business challenges. Focus areas: " + ", ".join(HERO_TAGS).title() + ".")
    photo = Image.open(SRC / "src" / "hero-photo.jpg").convert("RGB")
    ph = H * 2
    pw = round(photo.width * ph / photo.height)
    photo = photo.resize((pw, ph), Image.LANCZOS)
    buf = io.BytesIO()
    photo.save(buf, "JPEG", quality=82, optimize=True, progressive=True)
    img_w = pw / 2
    img_x = 300
    b64 = base64.b64encode(buf.getvalue()).decode()

    doc.defs.append(f'<clipPath id="c"><rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12"/></clipPath>')
    doc.defs.append('<linearGradient id="fl" x1="0" x2="1"><stop offset="0" stop-color="#090c11"/>'
                    '<stop offset="1" stop-color="#090c11" stop-opacity="0"/></linearGradient>')
    doc.defs.append('<linearGradient id="fb" x1="0" y1="0" x2="0" y2="1"><stop offset=".55" stop-color="#090c11" stop-opacity="0"/>'
                    '<stop offset="1" stop-color="#090c11" stop-opacity=".75"/></linearGradient>')
    doc.defs.append('<linearGradient id="sw" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
                    '<stop offset=".5" stop-color="#cfe3ff" stop-opacity=".07"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
    doc.css.append(
        "@keyframes glint{0%{stroke-dashoffset:60;opacity:0}20%{opacity:1}100%{stroke-dashoffset:-60;opacity:0}}"
        ".glint{stroke-dasharray:14 60;animation:glint 2.4s ease-in-out .6s 1 both}"
        "@keyframes ring{0%{r:5.5px;opacity:.7}100%{r:13px;opacity:0}}"
        ".ring{animation:ring 2.2s ease-out .4s 1 both}"
        "@keyframes sweep{from{transform:translateX(-260px)}to{transform:translateX(620px)}}"
        ".sweep{animation:sweep 9s ease-in-out 1.2s 1 both}"
    )
    doc.add('<g clip-path="url(#c)">')
    doc.add(f'<rect width="{W}" height="{H}" fill="#090c11"/>')
    doc.add(f'<image x="{img_x}" y="0" width="{img_w:.1f}" height="{H}" preserveAspectRatio="xMidYMid slice" '
            f'href="data:image/jpeg;base64,{b64}"/>')
    doc.add(f'<rect x="{img_x - 1}" y="0" width="190" height="{H}" fill="url(#fl)"/>')
    doc.add(f'<rect width="{W}" height="{H}" fill="url(#fb)"/>')
    doc.add(f'<rect class="sweep" x="{img_x}" y="0" width="200" height="{H}" fill="url(#sw)"/>')
    # right panel with focus areas
    px = 650
    doc.add(f'<rect x="{px}" y="0" width="{W - px}" height="{H}" fill="#07090d" fill-opacity=".86"/>')
    doc.add(f'<line x1="{px}" y1="0" x2="{px}" y2="{H}" stroke="#1d232c"/>')
    y0, step = 58, 26
    for i, tag in enumerate(HERO_TAGS):
        y = y0 + i * step
        assert text_width(tag, 8.5, 500, 1.6) < W - px - 34, tag
        doc.add("<g>")
        doc.text(px + 22, y, tag, 8.5, "#b7c0cb", 500, ls=1.6)
        if i < len(HERO_TAGS) - 1:
            doc.add(f'<line x1="{px + 14}" y1="{y + 10}" x2="{W - 14}" y2="{y + 10}" stroke="#1f262f"/>')
        doc.add("</g>")
    # identity
    doc.add('<circle cx="45" cy="38" r="5.5" fill="none" stroke="#5b9ef0" stroke-opacity=".8" stroke-width="1.3"/>'
            '<circle cx="45" cy="38" r="1.8" fill="#5b9ef0"/>'
            '<circle class="ring" cx="45" cy="38" r="5.5" fill="none" stroke="#7db8ff" stroke-width="1"/>')
    doc.text(40, 70, "AI DEVELOPER & PRODUCT BUILDER", 10, "#8d96a2", 500, ls=3.2)
    doc.text(38, 118, "SHAHIN", 44, "#f2f4f7", 700, opsz=32)
    doc.text(38 + text_width("SHAHIN ", 44, 700, opsz=32), 118, "AMANI", 44, "#a9b2bf", 300, opsz=32)
    doc.add('<line x1="40" y1="140" x2="84" y2="140" stroke="#5b9ef0" stroke-width="1.5" stroke-opacity=".85"/>'
            '<line class="glint" x1="40" y1="140" x2="84" y2="140" stroke="#cfe3ff" stroke-width="1.5"/>')
    for i, ln in enumerate(["Building intelligent software products,",
                            "scalable platforms and operational systems",
                            "for real-world business challenges."]):
        doc.text(40, 170 + i * 20, ln, 13.5, "#b3bcc7", 400)
    doc.add("</g>")
    doc.add(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="none" stroke="#262c36"/>')
    write("hero.svg", doc)


# ---------------------------------------------------------------- about + expertise

ABOUT = ("Software developer and product builder with a focus on AI-driven systems, "
         "full-stack development, fintech, automation and enterprise technology. "
         "I design and build real-world platforms from idea to deployment, combining "
         "technology, business understanding and operational experience.")
EXPERTISE = [
    ("agents", "AI Agents & Automation"), ("fintech", "FinTech & Trading Systems"),
    ("code", "Full-Stack Development"), ("risk", "Risk Management Systems"),
    ("layers", "Systems Architecture"), ("shield", "Security & Monitoring"),
    ("enterprise", "Enterprise Software"), ("ops", "Technical Operations"),
]


def build_about(theme):
    t = THEMES[theme]
    H = 186
    doc = Doc(W, H, "About me and core expertise",
              ABOUT + " Core expertise: " + ", ".join(e[1] for e in EXPERTISE) + ".")
    lw, rx = 414, 452
    section_heading(doc, 0, 24, "01", "ABOUT ME", t, lw)
    for i, ln in enumerate(wrap(ABOUT, 13, lw)):
        doc.text(0, 68 + i * 22, ln, 13, t["text2"], 400)
    section_heading(doc, rx, 24, "02", "CORE EXPERTISE", t, W - rx)
    cw = (W - rx) / 2
    for i, (icon, label) in enumerate(EXPERTISE):
        x = rx + (i % 2) * cw
        y = 58 + (i // 2) * 34
        assert text_width(label, 12) < cw - 34, label
        doc.add(line_icon(icon, x, y, t["icon"]))
        doc.text(x + 28, y + 13.5, label, 12, t["text2"], 400)
    write(f"about-{theme}.svg", doc)


# ---------------------------------------------------------------- dashboards

def _series(n, seed, start=50, vol=6, drift=0.6):
    r = random.Random(seed)
    v, out = start, []
    for _ in range(n):
        v = max(8, min(92, v + r.uniform(-vol, vol) + drift))
        out.append(v)
    return out


def _chrome(x, y, w, h):
    s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{D["bg"]}" stroke="{D["line"]}"/>',
         f'<rect x="{x}" y="{y}" width="{w}" height="11" rx="6" fill="{D["panel"]}"/>',
         f'<rect x="{x}" y="{y + 6}" width="{w}" height="5" fill="{D["panel"]}"/>']
    for i in range(3):
        s.append(f'<circle cx="{x + 7 + i * 6}" cy="{y + 5.5}" r="1.6" fill="{D["dim"]}"/>')
    s.append(f'<rect x="{x + w / 2 - 30}" y="{y + 3.5}" width="60" height="4" rx="2" fill="{D["line"]}"/>')
    return s


def _sidebar(x, y, h, active, rows=9):
    s = [f'<rect x="{x}" y="{y}" width="30" height="{h}" fill="{D["panel"]}"/>']
    for i in range(rows):
        c = D["acc"] if i == active else D["dim"]
        s.append(f'<rect x="{x + 6}" y="{y + 8 + i * 10}" width="{18 if i != active else 18}" height="3" rx="1.5" fill="{c}"/>')
    return s


def _panel(x, y, w, h):
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="3" fill="{D["panel"]}" stroke="{D["line"]}" stroke-width=".6"/>'


def _area(x, y, w, h, vals, gid, line_cls=""):
    n = len(vals)
    pts = [(x + i * w / (n - 1), y + h - v / 100 * h) for i, v in enumerate(vals)]
    line = "M" + " L".join(f"{a:.1f} {b:.1f}" for a, b in pts)
    area = line + f" L{x + w:.1f} {y + h:.1f} L{x:.1f} {y + h:.1f}Z"
    return [f'<path d="{area}" fill="url(#{gid})"/>',
            f'<path d="{line}" fill="none" stroke="{D["glow"]}" stroke-width=".9" stroke-linejoin="round"/>',
            f'<path class="{line_cls}" d="{line}" fill="none" stroke="#e6f1ff" stroke-width="1.1" stroke-linejoin="round"/>']


def dash_ops(x, y, w, h):
    s = _chrome(x, y, w, h)
    s += _sidebar(x, y + 11, h - 11, 2)
    mx, mw = x + 36, w - 42
    kw = (mw - 8) / 3
    for i in range(3):
        kx = mx + i * (kw + 4)
        s.append(_panel(kx, y + 16, kw, 24))
        s.append(f'<rect x="{kx + 5:.1f}" y="{y + 21}" width="22" height="2.5" rx="1" fill="{D["txt"]}"/>')
        s.append(f'<rect x="{kx + 5:.1f}" y="{y + 27}" width="{14 + i * 4}" height="6" rx="1.5" fill="#c9d4e2" fill-opacity=".75"/>')
        vals = _series(10, 10 + i, 40, 12, 2)
        pts = " ".join(f"{kx + kw - 30 + j * 2.8:.1f},{y + 36 - v / 100 * 12:.1f}" for j, v in enumerate(vals))
        s.append(f'<polyline points="{pts}" fill="none" stroke="{D["acc"]}" stroke-width=".8"/>')
    cy = y + 45
    cw = mw * 0.64
    s.append(_panel(mx, cy, cw, 50))
    for g in range(4):
        s.append(f'<line x1="{mx + 4}" y1="{cy + 10 + g * 10}" x2="{mx + cw - 4:.1f}" y2="{cy + 10 + g * 10}" stroke="{D["line"]}" stroke-width=".5"/>')
    s += _area(mx + 4, cy + 8, cw - 8, 38, _series(28, 3, 30, 9, 1.6), "ga", "ln")
    dx = mx + cw + 4
    dw = mw - cw - 4
    s.append(_panel(dx, cy, dw, 50))
    ccx, ccy, r = dx + dw / 2, cy + 25, 15
    circ = 2 * math.pi * r
    s.append(f'<circle cx="{ccx:.1f}" cy="{ccy}" r="{r}" fill="none" stroke="{D["dim"]}" stroke-width="4"/>')
    s.append(f'<circle cx="{ccx:.1f}" cy="{ccy}" r="{r}" fill="none" stroke="{D["acc"]}" stroke-width="4" '
             f'stroke-dasharray="{circ * .68:.1f} {circ:.1f}" transform="rotate(-90 {ccx:.1f} {ccy})"/>')
    s.append(f'<circle cx="{ccx:.1f}" cy="{ccy}" r="{r}" fill="none" stroke="{D["glow"]}" stroke-width="4" stroke-opacity=".5" '
             f'stroke-dasharray="{circ * .14:.1f} {circ:.1f}" stroke-dashoffset="{-circ * .68:.1f}" transform="rotate(-90 {ccx:.1f} {ccy})"/>')
    by = cy + 55
    bw = (mw - 4) / 2
    for i in range(2):
        bx = mx + i * (bw + 4)
        s.append(_panel(bx, by, bw, h - (by - y) - 5))
        for j in range(4):
            s.append(f'<rect x="{bx + 5:.1f}" y="{by + 6 + j * 6}" width="{bw * (.35 + .1 * ((j * 3 + i) % 4)):.1f}" height="2.2" rx="1" fill="{D["dim"]}"/>')
    return s


WORLD = [
    "      ##### ##   ####        ##############     ",
    "   ###########  ####     ###################    ",
    "  ##############  #     #####################   ",
    "   ############        ######################   ",
    "    ##########        #####################     ",
    "     ########         ######################    ",
    "      ######         ##########  ##########     ",
    "       ####          ##########   #######  #    ",
    "        ###           ########     ####   #     ",
    "          ####         ######       ##    ##    ",
    "           ######      ######             ###   ",
    "           ########     ####                    ",
    "            #######     ####              ##    ",
    "             #####      ###              ####   ",
    "             ####        #              ######  ",
    "             ###                         ####   ",
    "             ##                                 ",
]


def dash_security(x, y, w, h):
    s = _chrome(x, y, w, h)
    s += _sidebar(x, y + 11, h - 11, 0)
    mx, mw = x + 36, w - 42
    mapw = mw * 0.68
    s.append(_panel(mx, y + 16, mapw, 72))
    step = (mapw - 10) / 48
    for r, row in enumerate(WORLD):
        for c, ch in enumerate(row[:48]):
            if ch == "#":
                s.append(f'<circle cx="{mx + 5 + c * step:.1f}" cy="{y + 22 + r * 3.7:.1f}" r=".75" fill="{D["acc2"]}" fill-opacity=".75"/>')
    for cx, cy in [(0.22, 0.30), (0.53, 0.28), (0.60, 0.38), (0.80, 0.42), (0.30, 0.70), (0.86, 0.80)]:
        px, py = mx + 5 + cx * (mapw - 10), y + 22 + cy * 60
        s.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.2" fill="{D["glow"]}" fill-opacity=".18"/>'
                 f'<circle cx="{px:.1f}" cy="{py:.1f}" r="1.2" fill="{D["glow"]}"/>')
    rx = mx + mapw + 4
    rw = mw - mapw - 4
    s.append(_panel(rx, y + 16, rw, 72))
    for j in range(6):
        s.append(f'<rect x="{rx + 5:.1f}" y="{y + 23 + j * 10}" width="{rw - 10:.1f}" height="2.4" rx="1" fill="{D["dim"]}"/>')
        s.append(f'<rect x="{rx + 5:.1f}" y="{y + 23 + j * 10}" width="{(rw - 10) * (.25 + (j * 37 % 60) / 100):.1f}" height="2.4" rx="1" fill="{D["acc"]}"/>')
    by = y + 92
    bh = h - (by - y) - 5
    s.append(_panel(mx, by, mapw, bh))
    vals = _series(30, 7, 45, 18, 0)
    bw = (mapw - 10) / 30
    for i, v in enumerate(vals):
        hh = v / 100 * (bh - 8)
        s.append(f'<rect x="{mx + 5 + i * bw:.1f}" y="{by + bh - 4 - hh:.1f}" width="{bw * .6:.1f}" height="{hh:.1f}" fill="{D["acc"]}" fill-opacity="{.55 + v / 250:.2f}"/>')
    s.append(_panel(rx, by, rw, bh))
    gx, gy, gr = rx + rw / 2, by + bh - 7, 13
    s.append(f'<path d="M{gx - gr:.1f} {gy:.1f} A{gr} {gr} 0 0 1 {gx + gr:.1f} {gy:.1f}" fill="none" stroke="{D["dim"]}" stroke-width="3"/>')
    s.append(f'<path d="M{gx - gr:.1f} {gy:.1f} A{gr} {gr} 0 0 1 {gx + gr * math.cos(math.radians(130)) * -1:.1f} {gy - gr * math.sin(math.radians(130)):.1f}" fill="none" stroke="{D["acc"]}" stroke-width="3"/>')
    return s


def dash_trading(x, y, w, h):
    s = _chrome(x, y, w, h)
    s += _sidebar(x, y + 11, h - 11, 4)
    mx, mw = x + 36, w - 42
    cw = mw * 0.72
    s.append(_panel(mx, y + 16, cw, 78))
    s.append(f'<rect x="{mx + 5}" y="{y + 21}" width="26" height="3" rx="1" fill="#c9d4e2" fill-opacity=".7"/>'
             f'<rect x="{mx + 35}" y="{y + 21}" width="14" height="3" rx="1" fill="{D["up"]}"/>')
    r = random.Random(42)
    n, price = 34, 40.0
    candles = []
    for _ in range(n):
        o = price
        c = max(10, min(90, o + r.uniform(-6, 7.2)))
        hi, lo = max(o, c) + r.uniform(0.5, 4), min(o, c) - r.uniform(0.5, 4)
        candles.append((o, c, hi, lo))
        price = c
    top, bot = y + 30, y + 88
    lo_v = min(c[3] for c in candles)
    hi_v = max(c[2] for c in candles)

    def py(v):
        return bot - (v - lo_v) / (hi_v - lo_v) * (bot - top)
    step = (cw - 10) / n
    for g in range(4):
        gy = top + g * (bot - top) / 3
        s.append(f'<line x1="{mx + 4}" y1="{gy:.1f}" x2="{mx + cw - 4:.1f}" y2="{gy:.1f}" stroke="{D["line"]}" stroke-width=".5"/>')
    ma = []
    for i, (o, c, hi, lo) in enumerate(candles):
        cx = mx + 5 + i * step + step / 2
        col = D["up"] if c >= o else D["down"]
        s.append(f'<line x1="{cx:.1f}" y1="{py(hi):.1f}" x2="{cx:.1f}" y2="{py(lo):.1f}" stroke="{col}" stroke-width=".6"/>')
        y1, y2 = sorted((py(o), py(c)))
        s.append(f'<rect x="{cx - step * .3:.1f}" y="{y1:.1f}" width="{step * .6:.1f}" height="{max(.8, y2 - y1):.1f}" fill="{col}"/>')
        win = [k[1] for k in candles[max(0, i - 5):i + 1]]
        ma.append((cx, py(sum(win) / len(win))))
    ma_d = "M" + " L".join(f"{a:.1f} {b:.1f}" for a, b in ma)
    s.append(f'<path d="{ma_d}" fill="none" stroke="{D["glow"]}" stroke-width=".9"/>'
             f'<path class="ln" d="{ma_d}" fill="none" stroke="#e6f1ff" stroke-width="1.1"/>')
    vy = y + 98
    vh = h - (vy - y) - 5
    s.append(_panel(mx, vy, cw, vh))
    for i, (o, c, *_x) in enumerate(candles):
        hh = (3 + abs(c - o) * 1.3) / 14 * (vh - 6)
        hh = min(hh, vh - 6)
        col = D["up"] if c >= o else D["down"]
        s.append(f'<rect x="{mx + 5 + i * step + step * .2:.1f}" y="{vy + vh - 3 - hh:.1f}" width="{step * .6:.1f}" height="{hh:.1f}" fill="{col}" fill-opacity=".55"/>')
    ox = mx + cw + 4
    ow = mw - cw - 4
    s.append(_panel(ox, y + 16, ow, 60))
    for j in range(8):
        col = D["down"] if j < 4 else D["up"]
        frac = [.7, .45, .55, .3, .4, .65, .5, .8][j]
        s.append(f'<rect x="{ox + ow - 4 - (ow - 8) * frac:.1f}" y="{y + 21 + j * 6.5:.1f}" width="{(ow - 8) * frac:.1f}" height="3.6" fill="{col}" fill-opacity=".45"/>')
    s.append(_panel(ox, y + 80, ow, h - 85))
    rcx, rcy, rr = ox + ow / 2, y + 80 + (h - 85) / 2, 10
    circ = 2 * math.pi * rr
    s.append(f'<circle cx="{rcx:.1f}" cy="{rcy:.1f}" r="{rr}" fill="none" stroke="{D["dim"]}" stroke-width="3"/>'
             f'<circle cx="{rcx:.1f}" cy="{rcy:.1f}" r="{rr}" fill="none" stroke="{D["acc"]}" stroke-width="3" '
             f'stroke-dasharray="{circ * .72:.1f} {circ:.1f}" transform="rotate(-90 {rcx:.1f} {rcy:.1f})"/>')
    return s


# ---------------------------------------------------------------- projects

PROJECTS = [
    ("Executive Operations Command Center",
     "A centralized platform for managing corporate operations, including legal, personnel, "
     "payments, contracts, company records and operational workflows.",
     ["Full-Stack", "Automation", "Operations"], dash_ops),
    ("AI Security & Monitoring Platform",
     "An intelligent security and monitoring platform designed to detect suspicious behavior, "
     "analyze risk, monitor infrastructure and support security operations.",
     ["AI", "Security", "Monitoring", "Analytics"], dash_security),
    ("Trading AI Command Center",
     "A unified platform for trading intelligence, market monitoring, portfolio visibility, "
     "risk analysis and AI-assisted decision support.",
     ["Trading", "Analytics", "AI Agents", "Risk"], dash_trading),
]


def build_projects(theme):
    t = THEMES[theme]
    gap, top = 12, 52
    cw = (W - 2 * gap) / 3
    pad = 14
    inner = cw - 2 * pad
    shot_h = 136
    # layout pass to find the tallest card
    layouts = []
    for title, desc, tags, _ in PROJECTS:
        tl = wrap(title, 15, inner, 600)
        dl = wrap(desc, 12, inner)
        layouts.append((tl, dl))
    max_title = max(len(a) for a, _ in layouts)
    max_desc = max(len(b) for _, b in layouts)
    title_y = pad + shot_h + 26
    desc_y = title_y + max_title * 20 + 6
    tags_y = desc_y + max_desc * 18 + 8
    foot_y = tags_y + 40
    ch = foot_y + 18
    H = top + ch + 2
    doc = Doc(W, round(H), "Featured projects",
              " ".join(f"{p[0]}: {p[1]} Tags: {', '.join(p[2])}. Private repository." for p in PROJECTS))
    doc.defs.append(f'<linearGradient id="ga" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{D["acc"]}" stop-opacity=".45"/>'
                    f'<stop offset="1" stop-color="{D["acc"]}" stop-opacity="0"/></linearGradient>')
    doc.css.append("@keyframes ln{0%{stroke-dashoffset:40;opacity:0}15%{opacity:.9}100%{stroke-dashoffset:-260;opacity:0}}"
                   ".ln{stroke-dasharray:30 400;animation:ln 3.2s ease-in-out .6s 1 both}")
    section_heading(doc, 0, 24, "03", "FEATURED PROJECTS", t, W)
    link = "View all repositories"
    lx = W - 18 - text_width(link, 12, 500)
    doc.text(lx, 24, link, 12, t["accent"], 500)
    doc.add(f'<g transform="translate({W - 14} 12.5) scale(.78)">' + line_icon("arrow", 0, 0, t["accent"]) + "</g>")
    for i, ((title, desc, tags, dash), (tl, dl)) in enumerate(zip(PROJECTS, layouts)):
        x = i * (cw + gap)
        y = top
        doc.add(f'<rect x="{x + .5:.1f}" y="{y + .5}" width="{cw - 1:.1f}" height="{ch - 1:.1f}" rx="8" fill="{t["card"]}" stroke="{t["border"]}"/>')
        doc.add("".join(dash(round(x + pad, 1), y + pad, round(inner, 1), shot_h)))
        for j, ln in enumerate(tl):
            doc.text(x + pad, y + title_y + j * 20, ln, 15, t["text"], 600)
        for j, ln in enumerate(dl):
            doc.text(x + pad, y + desc_y + j * 18, ln, 12, t["text2"], 400)
        tx = x + pad
        for tag in tags:
            tw = text_width(tag, 10, 500) + 16
            doc.add(f'<rect x="{tx:.1f}" y="{y + tags_y:.1f}" width="{tw:.1f}" height="22" rx="11" fill="{t["chip"]}" stroke="{t["chipb"]}"/>')
            doc.text(tx + tw / 2, y + tags_y + 14.6, tag, 10, t["text2"], 500, anchor="middle")
            tx += tw + 5
        assert tx - x - 5 <= cw - pad, title
        doc.add(f'<line x1="{x + pad:.1f}" y1="{y + foot_y - 16:.1f}" x2="{x + cw - pad:.1f}" y2="{y + foot_y - 16:.1f}" stroke="{t["line"]}"/>')
        doc.add(brand_icon("github", x + pad, y + foot_y - 6, 15, t["icon"]))
        doc.text(x + pad + 23, y + foot_y + 5.5, "Private Repository", 11.5, t["muted"], 400)
        doc.add(f'<g transform="translate({x + cw - pad - 14:.1f} {y + foot_y - 6:.1f}) scale(.78)">' +
                line_icon("arrow", 0, 0, t["muted"]) + "</g>")
    write(f"projects-{theme}.svg", doc)


# ---------------------------------------------------------------- technology stack

STACK = [
    ("Languages", [("python", "Python", "#3776AB"), ("javascript", "JavaScript", "#F7DF1E"),
                   ("typescript", "TypeScript", "#3178C6")]),
    ("Data & Infrastructure", [("postgresql", "PostgreSQL", "#4169E1"), ("docker", "Docker", "#2496ED")]),
]
CAPABILITIES = ["LLMs", "AI Agents", "APIs", "Automation", "Workflow Design"]


def build_stack(theme):
    t = THEMES[theme]
    H = 150
    doc = Doc(W, H, "Technology stack",
              "Languages: Python, JavaScript, TypeScript. Data and infrastructure: PostgreSQL, Docker. "
              "AI and integration: " + ", ".join(CAPABILITIES) + ".")
    section_heading(doc, 0, 24, "04", "TECHNOLOGY STACK", t, W)
    gap, top, bh = 12, 52, 96
    widths = [220, 150]
    widths.append(W - sum(widths) - 2 * gap)
    x = 0
    groups = STACK + [("AI & Integration", None)]
    for (name, items), bw in zip(groups, widths):
        doc.add(f'<rect x="{x + .5}" y="{top + .5}" width="{bw - 1}" height="{bh - 1}" rx="8" fill="{t["card"]}" stroke="{t["border"]}"/>')
        doc.text(x + 18, top + 26, name, 12.5, t["text"], 600)
        if items:
            slot = (bw - 36) / len(items)
            for j, (icon, label, color) in enumerate(items):
                cx = x + 18 + slot * j + slot / 2
                doc.add(brand_icon(icon, cx - 13, top + 38, 26, color))
                doc.text(cx, top + 82, label, 10, t["muted"], 400, anchor="middle")
        else:
            cx, cy = x + 18, top + 42
            for cap in CAPABILITIES:
                cwid = text_width(cap, 11, 500) + 22
                if cx + cwid > x + bw - 18:
                    cx, cy = x + 18, cy + 30
                doc.add(f'<rect x="{cx:.1f}" y="{cy}" width="{cwid:.1f}" height="24" rx="12" fill="{t["chip"]}" stroke="{t["chipb"]}"/>')
                doc.text(cx + cwid / 2, cy + 16, cap, 11, t["text2"], 500, anchor="middle")
                cx += cwid + 8
        x += bw + gap
    write(f"stack-{theme}.svg", doc)


# ---------------------------------------------------------------- stats

def build_stats(theme, s):
    t = THEMES[theme]
    H = 150
    as_of = dt.date.fromisoformat(s["as_of"]).strftime("%-d %b %Y")
    tiles = [("pulse", f'{s["contributions"]:,}', "Contributions"),
             ("calendar", f'{s["active_days"]}', "Active days"),
             ("repo", f'{s["repositories"]}', "Repositories"),
             ("bars", s["member_since"], "Member since")]
    doc = Doc(W, H, "GitHub statistics",
              f'{s["contributions"]:,} contributions and {s["active_days"]} active days in the last 12 months, '
              f'including private work. {s["repositories"]} repositories. On GitHub since {s["member_since"]}. As of {as_of}.')
    lw = 500
    section_heading(doc, 0, 24, "05", "GITHUB STATS", t, lw)
    gap = 10
    tw = (lw - 3 * gap) / 4
    for i, (icon, num, label) in enumerate(tiles):
        x = i * (tw + gap)
        doc.add(f'<rect x="{x + .5:.1f}" y="52.5" width="{tw - 1:.1f}" height="63" rx="8" fill="{t["card"]}" stroke="{t["border"]}"/>')
        doc.add(line_icon(icon, x + 14, 75, t["icon"]))
        doc.text(x + 42, 81, num, 18, t["text"], 600)
        doc.text(x + 42, 99, label, 10.5, t["muted"], 400)
    doc.text(0, 140, f"Contributions and active days cover the last 12 months, including private work · as of {as_of}",
             10.5, t["muted"], 400)
    # monthly activity
    rx = 540
    doc.text(rx, 24, "Contribution activity", 13, t["accent"], 500)
    doc.text(W, 24, "last 12 months", 10.5, t["muted"], 400, anchor="end")
    doc.add(f'<line x1="{rx}" y1="38" x2="{W}" y2="38" stroke="{t["line"]}"/>')
    months = s["monthly"]
    peak = max(v for _, v in months) or 1
    cw = (W - rx) / len(months)
    base = 112
    for i, (m, v) in enumerate(months):
        bh = max(2, v / peak * 54)
        x = rx + i * cw + cw * 0.2
        doc.add(f'<rect x="{x:.1f}" y="{base - bh:.1f}" width="{cw * .6:.1f}" height="{bh:.1f}" rx="2" fill="{t["accent"]}" fill-opacity="{.35 + .65 * v / peak:.2f}"/>')
        label = dt.date.fromisoformat(m + "-01").strftime("%b")[0]
        doc.text(x + cw * .3, base + 16, label, 10, t["muted"], 400, anchor="middle")
    doc.add(f'<line x1="{rx}" y1="{base + .5}" x2="{W}" y2="{base + .5}" stroke="{t["line"]}"/>')
    write(f"stats-{theme}.svg", doc)


# ---------------------------------------------------------------- connect

def build_connect(theme):
    t = THEMES[theme]
    H = 64
    doc = Doc(W, H, "Connect", "GitHub: github.com/shahinamani. Location: Istanbul, Türkiye.")
    doc.text(0, 36, "06", 14, t["accent"], 400)
    nx = text_width("06", 14) + 12
    doc.add(f'<line x1="{nx:.1f}" y1="23" x2="{nx:.1f}" y2="39" stroke="{t["line"]}"/>')
    doc.text(nx + 13, 36, "CONNECT", 15, t["text"], 600, ls=0.6)
    x = 190
    for kind, label in [("github", "github.com/shahinamani"), ("pin", "Istanbul, Türkiye")]:
        bw = text_width(label, 12, 500) + 62
        doc.add(f'<rect x="{x + .5:.1f}" y="10.5" width="{bw:.1f}" height="39" rx="8" fill="{t["card"]}" stroke="{t["border"]}"/>')
        if kind == "github":
            doc.add(brand_icon("github", x + 20, 22, 16, t["icon"]))
        else:
            doc.add(line_icon("pin", x + 19, 21, t["icon"]))
        doc.text(x + 46, 34.5, label, 12, t["text2"], 500)
        x += bw + 14
    write(f"connect-{theme}.svg", doc)


# ---------------------------------------------------------------- main

def main():
    stats = refresh_stats() if "--refresh-stats" in sys.argv else load_stats()
    print("Building assets:")
    build_hero()
    for theme in THEMES:
        build_about(theme)
        build_projects(theme)
        build_stack(theme)
        build_stats(theme, stats)
        build_connect(theme)
    sync_readme_alt(stats)


def sync_readme_alt(s):
    """Keep the stats image's alt text in the README in step with the numbers."""
    import re
    readme = ROOT / "README.md"
    alt = (f'GitHub statistics: {s["contributions"]:,} contributions and {s["active_days"]} active days '
           f'in the last 12 months, including private work. {s["repositories"]} repositories. '
           f'On GitHub since {s["member_since"]}.')
    text = readme.read_text(encoding="utf-8")
    new = re.sub(r'(<img src="assets/stats-dark.svg" width="100%" alt=")[^"]*(")', lambda m: m.group(1) + alt + m.group(2), text)
    if new != text:
        readme.write_text(new, encoding="utf-8")


if __name__ == "__main__":
    main()
