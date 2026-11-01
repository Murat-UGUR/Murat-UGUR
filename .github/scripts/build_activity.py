#!/usr/bin/env python3
"""Builds assets/activity.svg (GitHub activity + languages) and assets/tryhackme.svg (TryHackMe profile).

Runs in GitHub Actions on a schedule, so the profile does not depend on any third-party
stats or badge service. Standard library only.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from xml.sax.saxutils import escape

USER = os.environ.get("GH_USER", "Murat-UGUR")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = os.environ.get("OUT", "assets/activity.svg")
# Repos left out of the language breakdown: the profile repo itself and coursework.
EXCLUDE = {USER, "PatikaDevProjects"}
TOP_N = 5
# Build/config files are not counted as languages.
IGNORE_LANGS = {"Dockerfile", "Makefile"}

COLORS = {
    "Python": "#3572A5", "TSQL": "#e38c00", "PowerShell": "#5391FE", "Shell": "#89e051",
    "Rust": "#dea584", "Go": "#00ADD8", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "HTML": "#e34c26", "CSS": "#663399", "Java": "#b07219", "Dockerfile": "#6b8a99",
    "Makefile": "#427819", "C#": "#178600", "C": "#555555", "C++": "#f34b7d",
}
FALLBACK = "#64748b"


def api(url, data=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-activity-card"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def collect():
    repos = [r for r in api(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner")
             if not r["fork"] and not r["private"]]
    langs = {}
    for r in repos:
        if r["name"] in EXCLUDE:
            continue
        for lang, size in api(r["languages_url"]).items():
            if lang in IGNORE_LANGS:
                continue
            langs[lang] = langs.get(lang, 0) + size
    contributions = None
    try:
        q = {"query": "query($l:String!){user(login:$l){contributionsCollection{contributionCalendar{totalContributions}}}}",
             "variables": {"l": USER}}
        res = api("https://api.github.com/graphql", q)
        contributions = res["data"]["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    except Exception as e:  # GraphQL needs a token; the card still renders without it
        print(f"contributions unavailable: {e}", file=sys.stderr)
    return {
        "public_repos": len([r for r in repos if r["name"] != USER]),
        "contributions": contributions,
        "langs": langs,
    }


def render(d):
    W, H = 1200, 230
    total = sum(d["langs"].values()) or 1
    top = sorted(d["langs"].items(), key=lambda kv: kv[1], reverse=True)
    shown = top[:TOP_N]
    other = sum(v for _, v in top[TOP_N:])
    if other:
        shown.append(("Other", other))

    stats = [("Public repos", str(d["public_repos"]))]
    if d["contributions"] is not None:
        stats.insert(0, ("Contributions · last 12 months", f"{d['contributions']:,}"))
    stats.append(("Languages", str(len(d["langs"]))))

    o = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="GitHub activity and languages">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b1220"/><stop offset="1" stop-color="#111c33"/></linearGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#ef4444"/></linearGradient>
    <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="#1e2a44" stroke-width="1"/></pattern>
    <clipPath id="bar"><rect x="480" y="100" width="680" height="14" rx="7"/></clipPath>
    <style>
      .t{{font-family:'Segoe UI',Ubuntu,'Helvetica Neue',Arial,sans-serif}}
      .m{{font-family:'JetBrains Mono',Consolas,'Courier New',monospace}}
    </style>
  </defs>
  <rect width="{W}" height="{H}" rx="18" fill="url(#bg)"/>
  <rect width="{W}" height="{H}" rx="18" fill="url(#grid)" opacity=".5"/>
  <text x="40" y="44" class="m" font-size="15" fill="#22d3ee">$ gh api users/{escape(USER)}</text>
  <text x="40" y="72" class="t" font-size="24" font-weight="700" fill="#f1f5f9">GitHub activity</text>
  <rect x="236" y="62" width="90" height="4" rx="2" fill="url(#accent)"/>''']

    y = 112
    for label, value in stats:
        o.append(f'  <text x="40" y="{y}" class="t" font-size="15" fill="#94a3b8">{escape(label)}</text>')
        o.append(f'  <text x="400" y="{y}" class="t" font-size="18" font-weight="700" fill="#f1f5f9" text-anchor="end">{escape(value)}</text>')
        y += 34

    o.append('  <text x="480" y="84" class="t" font-size="15" fill="#94a3b8">Languages (bytes of code, own public repos)</text>')
    o.append('  <g clip-path="url(#bar)">')
    x = 480.0
    for lang, size in shown:
        w = 680 * size / total
        o.append(f'    <rect x="{x:.2f}" y="100" width="{w + 0.5:.2f}" height="14" fill="{COLORS.get(lang, FALLBACK)}"/>')
        x += w
    o.append('  </g>')
    for i, (lang, size) in enumerate(shown):
        col, row = i % 3, i // 3
        lx, ly = 480 + col * 230, 146 + row * 30
        pct = 100 * size / total
        pct_s = f"{pct:.1f}%" if pct >= 0.1 else "&lt;0.1%"
        o.append(f'  <circle cx="{lx + 6}" cy="{ly - 5}" r="6" fill="{COLORS.get(lang, FALLBACK)}"/>')
        o.append(f'  <text x="{lx + 20}" y="{ly}" class="t" font-size="15" fill="#e2e8f0">{escape(lang)} '
                 f'<tspan fill="#94a3b8">{pct_s}</tspan></text>')
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    o.append(f'  <text x="{W - 40}" y="{H - 16}" class="m" font-size="11" fill="#475569" text-anchor="end">updated {stamp}</text>')
    o.append("</svg>\n")
    return "\n".join(o)


# --------------------------------------------------------------------------- TryHackMe card
THM_USER = os.environ.get("THM_USER", "MuRAT")
THM_OUT = os.environ.get("THM_OUT", "assets/tryhackme.svg")


def collect_thm():
    url = f"https://tryhackme.com/api/v2/public-profile?username={THM_USER}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (profile-card)", "Accept": "application/json"})
    for attempt in range(1, 5):  # TryHackMe rate-limits shared CI IPs; back off and retry
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)["data"]
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 4:
                raise
            wait = int(e.headers.get("Retry-After") or 0) or 30 * attempt
            print(f"TryHackMe returned 429, retrying in {wait}s", file=sys.stderr)
            time.sleep(min(wait, 120))


def render_thm(d):
    W, H = 1200, 200
    tiles = [
        ("Rooms completed", f"{d['completedRoomsNumber']:,}"),
        ("Badges", f"{d['badgesNumber']:,}"),
        ("Points", f"{d['totalPoints']:,}"),
        ("Longest streak", f"{d['largestStreak']:,} days"),
    ]
    o = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="TryHackMe profile of {escape(THM_USER)}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b1220"/><stop offset="1" stop-color="#111c33"/></linearGradient>
    <linearGradient id="thm" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#88cc14"/><stop offset="1" stop-color="#ef4444"/></linearGradient>
    <pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="#1e2a44" stroke-width="1"/></pattern>
    <style>
      .t{{font-family:'Segoe UI',Ubuntu,'Helvetica Neue',Arial,sans-serif}}
      .m{{font-family:'JetBrains Mono',Consolas,'Courier New',monospace}}
    </style>
  </defs>
  <rect width="{W}" height="{H}" rx="18" fill="url(#bg)"/>
  <rect width="{W}" height="{H}" rx="18" fill="url(#grid)" opacity=".5"/>
  <text x="40" y="44" class="m" font-size="15" fill="#88cc14">$ thm whoami --user {escape(THM_USER)}</text>
  <text x="40" y="78" class="t" font-size="26" font-weight="700" fill="#f1f5f9">TryHackMe</text>
  <rect x="40" y="90" width="90" height="4" rx="2" fill="url(#thm)"/>
  <rect x="40" y="118" width="118" height="32" rx="16" fill="none" stroke="#88cc14"/>
  <text x="99" y="139" class="m" font-size="14" font-weight="700" fill="#88cc14" text-anchor="middle">LEVEL {int(d['level'])}</text>
  <rect x="168" y="118" width="118" height="32" rx="16" fill="none" stroke="#ef4444"/>
  <text x="227" y="139" class="m" font-size="14" font-weight="700" fill="#f87171" text-anchor="middle">{escape(str(d['rank']).upper())}</text>''']
    x0, tw, gap = 340, 195, 13
    for i, (label, value) in enumerate(tiles):
        x = x0 + i * (tw + gap)
        o.append(f'  <rect x="{x}" y="40" width="{tw}" height="120" rx="14" fill="#0f172a" stroke="#1f2b47" stroke-width="1.5"/>')
        o.append(f'  <text x="{x + tw / 2:.0f}" y="102" class="t" font-size="32" font-weight="700" fill="#f1f5f9" text-anchor="middle">{escape(value)}</text>')
        o.append(f'  <text x="{x + tw / 2:.0f}" y="132" class="t" font-size="14" fill="#94a3b8" text-anchor="middle">{escape(label)}</text>')
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    o.append(f'  <text x="{W - 40}" y="{H - 14}" class="m" font-size="11" fill="#475569" text-anchor="end">updated {stamp}</text>')
    o.append("</svg>\n")
    return "\n".join(o)


def build_thm(sample=None):
    """Writes the TryHackMe card. On any error the previous card is kept as it is."""
    try:
        d = sample or collect_thm()
        svg = render_thm(d)
    except Exception as e:
        print(f"TryHackMe card not updated: {e}", file=sys.stderr)
        return
    os.makedirs(os.path.dirname(THM_OUT) or ".", exist_ok=True)
    with open(THM_OUT, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {THM_OUT}: level {d['level']}, {d['rank']}, {d['completedRoomsNumber']} rooms")

if __name__ == "__main__":
    if len(sys.argv) > 1:  # render from a saved JSON sample (local preview)
        with open(sys.argv[1], encoding="utf-8") as fh:
            data = json.load(fh)
        data["langs"] = {k: v for k, v in data["langs"].items() if k not in IGNORE_LANGS}
    else:
        data = collect()
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(render(data))
    print(f"wrote {OUT}: {data['public_repos']} repos, {len(data['langs'])} languages")
    build_thm(json.load(open(sys.argv[2], encoding="utf-8")) if len(sys.argv) > 2 else None)
