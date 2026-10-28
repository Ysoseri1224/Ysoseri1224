"""Draw GitHub-styled SVG cards (banner, languages, recently starred) in light and dark variants."""

import base64
import json
import os
import re
import subprocess
import tempfile
import unicodedata
import urllib.request
from datetime import datetime, timezone
from html import escape

USER = os.environ.get("GH_USER", "Ysoseri1224")
TOKEN = os.environ["GITHUB_TOKEN"]
OUT_DIR = "assets"
WIDTH = 830
IGNORED_LANGUAGES = {"Jupyter Notebook"}
SCC = os.environ.get("SCC", "scc")
SCC_EXCLUDED_DIRS = ".git,node_modules,vendor,dist,build"
# scc language names that differ from GitHub linguist's
SCC_ALIASES = {"JSX": "JavaScript", "Powershell": "PowerShell", "Batch": "Batchfile", "Jupyter": "Jupyter Notebook"}
STAR_LIMIT = 4

# Primer functional colors
THEMES = {
    "light": {
        "fg": "#1f2328", "muted": "#59636e", "accent": "#0969da", "border": "#d1d9e0",
        "canvas": "#ffffff", "subtle": "#f6f8fa", "other": "#818b98",
    },
    "dark": {
        "fg": "#f0f6fc", "muted": "#9198a1", "accent": "#4493f8", "border": "#3d444d",
        "canvas": "#0d1117", "subtle": "#151b23", "other": "#656c76",
    },
}

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"

ICONS = {
    "repo": "M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8ZM5 12.25a.25.25 0 0 1 .25-.25h3.5a.25.25 0 0 1 .25.25v3.25a.25.25 0 0 1-.4.2l-1.45-1.087a.249.249 0 0 0-.3 0L5.4 15.7a.25.25 0 0 1-.4-.2Z",
    "star": "M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Zm0 2.445L6.615 5.5a.75.75 0 0 1-.564.41l-3.097.45 2.24 2.184a.75.75 0 0 1 .216.664l-.528 3.084 2.769-1.456a.75.75 0 0 1 .698 0l2.77 1.456-.53-3.084a.75.75 0 0 1 .216-.664l2.24-2.183-3.096-.45a.75.75 0 0 1-.564-.41L8 2.694Z",
    "fork": "M5 5.372v.878c0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75v-.878a2.25 2.25 0 1 1 1.5 0v.878a2.25 2.25 0 0 1-2.25 2.25h-1.5v2.128a2.251 2.251 0 1 1-1.5 0V8.5h-1.5A2.25 2.25 0 0 1 3.5 6.25v-.878a2.25 2.25 0 1 1 1.5 0ZM5 3.25a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Zm6.75.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Zm-3 8.75a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Z",
    "code": "m11.28 3.22 4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.749.749 0 0 1-1.275-.326.749.749 0 0 1 .215-.734L13.94 8l-3.72-3.72a.749.749 0 0 1 .326-1.275.749.749 0 0 1 .734.215Zm-6.56 0a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042L2.06 8l3.72 3.72a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215L.47 8.53a.75.75 0 0 1 0-1.06Z",
}

# Greeting printed by the Windows PowerShell profile (figlet "slant")
BANNER = r"""
            __                                           _
 _      __ / /_   __  __ _____ ____   _____ ___   _____ (_)____   __  __ _____
| | /| / // __ \ / / / // ___// __ \ / ___// _ \ / ___// // __ \ / / / // ___/
| |/ |/ // / / // /_/ /(__  )/ /_/ /(__  )/  __// /   / // /_/ // /_/ /(__  )
|__/|__//_/ /_/ \__, //____/ \____//____/ \___//_/   /_/ \____/ \__,_//____/
               /____/
""".strip("\n").split("\n")

QUERY = """
query($login: String!, $stars: Int!) {
  user(login: $login) {
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      nodes {
        nameWithOwner
        languages(first: 20) { nodes { name color } }
      }
    }
    starredRepositories(first: $stars, orderBy: {field: STARRED_AT, direction: DESC}) {
      edges {
        starredAt
        node {
          nameWithOwner description stargazerCount forkCount
          primaryLanguage { name color }
        }
      }
    }
  }
}
"""


def graphql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.load(resp)
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


# ---------- text helpers ----------

def char_width(ch, size):
    if unicodedata.east_asian_width(ch) in "WF":
        return size
    if ch in "il.,:;|!'":
        return size * 0.3
    if ch.isupper() or ch in "mwMW@":
        return size * 0.68
    return size * 0.52


def text_width(text, size):
    return sum(char_width(ch, size) for ch in text)


def truncate(text, size, max_width):
    if text_width(text, size) <= max_width:
        return text
    while text and text_width(text + "…", size) > max_width:
        text = text[:-1]
    return text.rstrip() + "…"


def wrap(text, size, max_width, max_lines):
    """Greedy wrap (CJK breaks per character); overflow is folded into an ellipsis on the last line."""
    lines = [""]
    for token in re.findall(r"[⺀-￿]|[^\s⺀-￿]+|\s+", text):
        if text_width(lines[-1] + token, size) <= max_width:
            lines[-1] += token
        else:
            lines.append(token.lstrip())
    lines = [line.strip() for line in lines if line.strip()]
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1] + [lines[max_lines - 1] + " " + lines[max_lines]]
    return [truncate(line, size, max_width) for line in lines]


def compact(n):
    if n >= 1000:
        return f"{n / 1000:.1f}".rstrip("0").rstrip(".") + "k"
    return str(n)


def ago(iso):
    days = (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    return f"on {iso[:10]}"


def icon(name, x, y, color, scale=1.0):
    return f'<path transform="translate({x},{y}) scale({scale})" fill="{color}" d="{ICONS[name]}"/>'


def text(x, y, content, *, size=14, color, weight=400, anchor="start", family=SANS):
    return (
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
        f'fill="{color}" text-anchor="{anchor}">{escape(content)}</text>'
    )


def svg(height, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}">{body}</svg>\n'
    )


def box(height, title, icon_name, aside, t):
    """GitHub Box: rounded border with a subtle header row."""
    return (
        f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" rx="6" fill="{t["canvas"]}" stroke="{t["border"]}"/>'
        f'<path d="M0.5 6.5a6 6 0 0 1 6-6h{WIDTH - 13}a6 6 0 0 1 6 6V44.5H0.5Z" fill="{t["subtle"]}"/>'
        f'<line x1="0.5" y1="44.5" x2="{WIDTH - 0.5}" y2="44.5" stroke="{t["border"]}"/>'
        + icon(icon_name, 16, 15, t["muted"])
        + text(40, 28, title, color=t["fg"], weight=600)
        + text(WIDTH - 16, 28, aside, size=12, color=t["muted"], anchor="end")
    )


# ---------- cards ----------

def banner(t):
    size, line_height = 14, 16
    columns = max(len(line) for line in BANNER)
    char_w = size * 0.6
    left = (WIDTH - columns * char_w) / 2
    # Place each run of non-space characters at its exact column so renderers can't collapse spaces
    runs = []
    for i, line in enumerate(BANNER):
        for match in re.finditer(r"\S+", line):
            run = match.group()
            runs.append(
                f'<text x="{left + match.start() * char_w:.1f}" y="{18 + i * line_height}" '
                f'textLength="{len(run) * char_w:.1f}" lengthAdjust="spacingAndGlyphs">{escape(run)}</text>'
            )
    return svg(
        18 + len(BANNER) * line_height,
        f'<g font-family="{MONO}" font-size="{size}" fill="{t["fg"]}">{"".join(runs)}</g>',
    )


def git_env():
    """Authenticate clones via an extra header so the token never appears in command arguments or errors."""
    credentials = base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()
    return {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {credentials}",
    }


def count_lines(repos):
    """Shallow-clone each repo and count code lines with scc.

    Languages GitHub detects in a repo are ranked individually; everything else scc counts (docs, data,
    config, type declarations, ...) is pooled into "Others". Covers every repo the token can see, so
    private repos are included when the token has read access to them.
    """
    totals, others, colors = {}, {}, {}
    env = git_env()
    with tempfile.TemporaryDirectory() as workdir:
        for i, repo in enumerate(repos):
            detected = {lang["name"]: lang["color"] for lang in repo["languages"]["nodes"]}
            colors.update(detected)
            path = os.path.join(workdir, str(i))
            subprocess.run(
                ["git", "clone", "--quiet", "--depth", "1", f"https://github.com/{repo['nameWithOwner']}.git", path],
                check=True, env=env,
            )
            report = subprocess.run(
                # Clones only hold tracked files, so ignore files would only hide code that was committed anyway
                [SCC, "--no-min-gen", "--no-gitignore", "--no-ignore", "--exclude-dir", SCC_EXCLUDED_DIRS,
                 "--format", "json", path],
                check=True, capture_output=True, text=True,
            ).stdout
            for entry in json.loads(report or "[]"):
                name = SCC_ALIASES.get(entry["Name"], entry["Name"])
                if name in IGNORED_LANGUAGES or not entry["Code"]:
                    continue
                bucket = totals if name in detected else others
                bucket[name] = bucket.get(name, 0) + entry["Code"]
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    others_ranked = sorted(others.items(), key=lambda kv: kv[1], reverse=True)
    return [(name, lines, colors.get(name)) for name, lines in ranked], others_ranked


def readable(color, t):
    """Lift language colors that would vanish against the dark canvas (e.g. PowerShell navy)."""
    if not color or t is not THEMES["dark"]:
        return color
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    if 0.2126 * r + 0.7152 * g + 0.0722 * b >= 70:
        return color
    return "#" + "".join(f"{round(c + (255 - c) * 0.45):02x}" for c in (r, g, b))


def languages_card(rows, others, repo_count, t):
    """Bar chart on one linear scale set by the top language.

    Bars too long for a column span the full width, the rest share two columns, and the pooled
    "Others" row always spans the full width at the bottom; if it outruns the scale it is drawn
    with a break mark instead of shrinking every other bar.
    """
    pad, gutter, row_h, bar_h = 16, 32, 26, 10
    label_w, number_w = 112, 64
    col_w = (WIDTH - 2 * pad - gutter) / 2
    wide_track = WIDTH - 2 * pad - label_w - number_w
    col_track = col_w - label_w - number_w
    scale = wide_track / max((lines for _, lines, _ in rows), default=1)
    spanning = sum(1 for _, lines, _ in rows if lines * scale > col_track)
    rest = rows[spanning:]
    per_column = (len(rest) + 1) // 2
    top = 44 + pad

    def bar_row(x, cy, width, name, lines, color):
        fill = readable(color, t) or t["other"]
        track_x, track_w = x + label_w, width - label_w - number_w
        bar_w = min(track_w, max(bar_h, lines * scale))
        row = (
            f'<circle cx="{x + 5}" cy="{cy}" r="5" fill="{fill}"/>'
            + text(x + 18, cy + 5, truncate(name, 14, label_w - 24), color=t["fg"])
            + f'<rect x="{track_x:.1f}" y="{cy - bar_h / 2}" width="{track_w:.1f}" height="{bar_h}" rx="{bar_h / 2}" fill="{t["subtle"]}"/>'
            + f'<rect x="{track_x:.1f}" y="{cy - bar_h / 2}" width="{bar_w:.1f}" height="{bar_h}" rx="{bar_h / 2}" fill="{fill}"/>'
            + text(round(x + width, 1), cy + 5, f"{lines:,}", color=t["fg"], weight=600, anchor="end")
        )
        if lines * scale > track_w:
            # Axis break: the bar is longer than the scale allows
            bx = track_x + track_w * 0.85
            row += "".join(
                f'<line x1="{bx + dx:.1f}" y1="{cy + bar_h}" x2="{bx + dx + 6:.1f}" y2="{cy - bar_h}" stroke="{t["canvas"]}" stroke-width="2.5"/>'
                for dx in (0, 6)
            )
        return row

    body = [
        bar_row(pad, top + i * row_h + row_h / 2, WIDTH - 2 * pad, name, lines, color)
        for i, (name, lines, color) in enumerate(rows[:spanning])
    ]
    columns_top = top + spanning * row_h
    for i, (name, lines, color) in enumerate(rest):
        x = pad + (i // per_column) * (col_w + gutter)
        body.append(bar_row(x, columns_top + (i % per_column) * row_h + row_h / 2, col_w, name, lines, color))
    height = columns_top + per_column * row_h
    if others:
        others_total = sum(lines for _, lines in others)
        height += 10
        body.append(f'<line x1="{pad}" y1="{height + 0.5}" x2="{WIDTH - pad}" y2="{height + 0.5}" stroke="{t["border"]}"/>')
        height += 6
        body.append(bar_row(pad, height + row_h / 2, WIDTH - 2 * pad, "Others", others_total, None))
        detail = " · ".join(f"{name} {lines:,}" for name, lines in others[:5])
        if len(others) > 5:
            detail += f" · {len(others) - 5} more"
        body.append(text(pad + 18, height + row_h + 12, truncate(detail, 12, WIDTH - 2 * pad - 18), size=12, color=t["muted"]))
        height += row_h + 18
    height += pad
    total = sum(lines for _, lines, _ in rows) + sum(lines for _, lines in others)
    aside = f"{total:,} lines across {repo_count} repositories"
    return svg(height, box(height, "Languages", "code", aside, t) + "".join(body))


def starred_card(edges, t):
    pad, gap, inner = 16, 16, 16
    card_w = (WIDTH - 2 * pad - gap) / 2
    card_h = 116
    body = []
    for i, edge in enumerate(edges):
        repo = edge["node"]
        x = pad + (i % 2) * (card_w + gap)
        y = 44 + pad + (i // 2) * (card_h + gap)
        body.append(f'<rect x="{x + 0.5:.1f}" y="{y + 0.5}" width="{card_w - 1:.1f}" height="{card_h - 1}" rx="6" fill="none" stroke="{t["border"]}"/>')
        body.append(icon("repo", x + inner, y + inner + 1, t["muted"]))
        when = f"starred {ago(edge['starredAt'])}"
        name_max = card_w - 2 * inner - 24 - text_width(when, 12) - 12
        body.append(text(x + inner + 24, y + inner + 13, truncate(repo["nameWithOwner"], 14, name_max), color=t["accent"], weight=600))
        body.append(text(x + card_w - inner, y + inner + 12, when, size=12, color=t["muted"], anchor="end"))
        for j, line in enumerate(wrap(repo["description"] or "No description provided.", 12, card_w - 2 * inner, 2)):
            body.append(text(x + inner, y + inner + 40 + j * 18, line, size=12, color=t["muted"]))
        fy, fx = y + card_h - inner, x + inner
        lang = repo["primaryLanguage"]
        if lang:
            body.append(f'<circle cx="{fx + 6}" cy="{fy - 4}" r="6" fill="{readable(lang["color"], t) or t["other"]}"/>')
            body.append(text(fx + 17, fy, lang["name"], size=12, color=t["muted"]))
            fx += 17 + text_width(lang["name"], 12) + 16
        for name, count in (("star", repo["stargazerCount"]), ("fork", repo["forkCount"])):
            body.append(icon(name, fx, fy - 12, t["muted"]))
            body.append(text(fx + 20, fy, compact(count), size=12, color=t["muted"]))
            fx += 20 + text_width(compact(count), 12) + 16
    rows = (len(edges) + 1) // 2
    height = 44 + pad + rows * card_h + (rows - 1) * gap + pad
    return svg(height, box(height, "Recently starred", "star", f"by @{USER}", t) + "".join(body))


def main():
    data = graphql(QUERY, {"login": USER, "stars": STAR_LIMIT})["user"]
    repos = data["repositories"]["nodes"]
    rows, others = count_lines(repos)
    stars = data["starredRepositories"]["edges"]
    os.makedirs(OUT_DIR, exist_ok=True)
    for theme, t in THEMES.items():
        outputs = {
            "banner": banner(t),
            "languages": languages_card(rows, others, len(repos), t),
            "starred": starred_card(stars, t),
        }
        for name, content in outputs.items():
            with open(f"{OUT_DIR}/{name}-{theme}.svg", "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
    print(f"Rendered {len(rows)} languages and {len(stars)} starred repositories")


if __name__ == "__main__":
    main()
