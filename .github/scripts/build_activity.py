#!/usr/bin/env python3
"""Builds assets/activity.svg (GitHub activity + language card) from the public GitHub API.

Runs in GitHub Actions on a schedule, so the profile does not depend on any third-party
stats service. Standard library only.
"""

import json
import os
import sys
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
