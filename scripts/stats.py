"""Generate GitHub stats and language cards as SVG (light + dark).

Runs in GitHub Actions with the built-in GITHUB_TOKEN. Standard library only.
Usage: python scripts/stats.py <username> <output_dir> [mock.json]
"""
import json
import math
import os
import sys
import urllib.request
from html import escape

QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes {
        name
        stargazerCount
        forkCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar { totalContributions }
    }
  }
}
"""

THEMES = {
    "light": dict(bg="#ffffff", border="#d0d7de", title="#0f5c63", text="#1f2328", muted="#59636e", track="#eaeef2"),
    "dark": dict(bg="#0d1117", border="#30363d", title="#5eead4", text="#e6edf3", muted="#9198a1", track="#21262d"),
}
FONT = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"


def fetch(login):
    token = os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        payload = json.load(r)
    if "errors" in payload:
        raise SystemExit(json.dumps(payload["errors"], indent=2))
    return payload["data"]["user"]


def summarize(user, login):
    repos = [r for r in user["repositories"]["nodes"] if r["name"].lower() != login.lower()]
    langs = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            name, color = e["node"]["name"], e["node"]["color"] or "#8b949e"
            size, _ = langs.get(name, (0, color))
            langs[name] = (size + e["size"], color)
    c = user["contributionsCollection"]
    return {
        "repos": len(repos),
        "stars": sum(r["stargazerCount"] for r in repos),
        "forks": sum(r["forkCount"] for r in repos),
        "followers": user["followers"]["totalCount"],
        "commits": c["totalCommitContributions"],
        "prs_issues": c["totalPullRequestContributions"] + c["totalIssueContributions"],
        "contributions": c["contributionCalendar"]["totalContributions"],
        "langs": sorted(langs.items(), key=lambda kv: -kv[1][0]),
    }


def card(t, w, h, title, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="{FONT}">'
        f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="10" fill="{t["bg"]}" stroke="{t["border"]}"/>'
        f'<text x="24" y="36" font-size="17" font-weight="600" fill="{t["title"]}">{escape(title)}</text>'
        f"{body}</svg>"
    )


ICONS = {
    # simple 16px glyphs drawn with paths
    "repo": "M3 2h8l2 2v10H3z M6 2v6l1.5-1 1.5 1V2",
    "star": "M8 1.5l1.9 4 4.3.5-3.2 3 .9 4.3L8 11.1 4.1 13.3 5 9 1.8 6l4.3-.5z",
    "commit": "M1 8h4 M11 8h4 M8 5a3 3 0 1 1 0 6 3 3 0 0 1 0-6z",
    "pr": "M4 3v10 M4 3a1.5 1.5 0 1 0 0 .1 M12 13V6c0-1.5-1-2.5-2.5-2.5H7 M8.5 2 7 3.5 8.5 5",
    "calendar": "M2 4h12v10H2z M2 7h12 M5 2v3 M11 2v3",
}


def stats_svg(s, t):
    rows = [
        ("repo", "Public repositories", s["repos"]),
        ("star", "Stars earned", s["stars"]),
        ("commit", "Commits, last 12 months", s["commits"]),
        ("pr", "PRs and issues opened", s["prs_issues"]),
        ("calendar", "Contributions, last 12 months", s["contributions"]),
    ]
    body = []
    for i, (icon, label, value) in enumerate(rows):
        y = 70 + i * 26
        body.append(
            f'<g transform="translate(24,{y - 12})"><path d="{ICONS[icon]}" fill="none" stroke="{t["title"]}" '
            f'stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"/></g>'
            f'<text x="50" y="{y}" font-size="14" fill="{t["muted"]}">{label}</text>'
            f'<text x="330" y="{y}" font-size="14" font-weight="600" fill="{t["text"]}" text-anchor="end">{value:,}</text>'
        )
    # decorative mini KM curve on the right
    body.append(
        f'<g transform="translate(355,62)" opacity="0.9">'
        f'<path d="M0 0H22V12H44V22H66V30H88V36H112" fill="none" stroke="{t["title"]}" stroke-width="2"/>'
        f'<path d="M0 0H14V20H34V40H56V56H80V66H112" fill="none" stroke="#f59e0b" stroke-width="2"/>'
        f'<line x1="0" y1="80" x2="112" y2="80" stroke="{t["border"]}"/>'
        f'<line x1="0" y1="-6" x2="0" y2="80" stroke="{t["border"]}"/></g>'
    )
    return card(t, 495, 205, "GitHub stats", "".join(body))


def donut_svg(s, t):
    top = s["langs"][:6]
    total = sum(v[0] for _, v in s["langs"]) or 1
    other = total - sum(v[0] for _, v in top)
    items = [(n, v[0], v[1]) for n, v in top]
    if other > 0:
        items.append(("Other", other, "#8b949e"))
    cx, cy, r, sw = 100, 118, 52, 22
    circ = 2 * math.pi * r
    arcs, offset = [], 0.0
    for name, size, color in items:
        frac = size / total
        arcs.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{sw}" '
            f'stroke-dasharray="{frac * circ:.2f} {circ:.2f}" stroke-dashoffset="{-offset * circ:.2f}" '
            f'transform="rotate(-90 {cx} {cy})"/>'
        )
        offset += frac
    if not items:
        arcs.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{t["track"]}" stroke-width="{sw}"/>')
    legend = []
    for i, (name, size, color) in enumerate(items):
        y = 66 + i * 21
        legend.append(
            f'<rect x="200" y="{y - 10}" width="11" height="11" rx="2" fill="{color}"/>'
            f'<text x="220" y="{y}" font-size="13" fill="{t["text"]}">{escape(name)}</text>'
            f'<text x="470" y="{y}" font-size="13" fill="{t["muted"]}" text-anchor="end">{size / total * 100:.1f}%</text>'
        )
    centre = (
        f'<text x="{cx}" y="{cy - 2}" font-size="20" font-weight="700" fill="{t["text"]}" text-anchor="middle">{len(s["langs"])}</text>'
        f'<text x="{cx}" y="{cy + 16}" font-size="11" fill="{t["muted"]}" text-anchor="middle">languages</text>'
    )
    return card(t, 495, 205, "Languages by code size", "".join(arcs) + centre + "".join(legend))


def main():
    login, out = sys.argv[1], sys.argv[2]
    user = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else fetch(login)
    s = summarize(user, login)
    os.makedirs(out, exist_ok=True)
    for theme, t in THEMES.items():
        with open(os.path.join(out, f"stats-{theme}.svg"), "w") as f:
            f.write(stats_svg(s, t))
        with open(os.path.join(out, f"langs-{theme}.svg"), "w") as f:
            f.write(donut_svg(s, t))
    print(json.dumps({k: v for k, v in s.items() if k != "langs"}))


if __name__ == "__main__":
    main()
