"""Render recent public GitHub activity into README.md between activity markers."""

import json
import os
import re
import sys
import urllib.request

USER = os.environ.get("GH_USER", "Ysoseri1224")
TOKEN = os.environ.get("GITHUB_TOKEN")
README = "README.md"
MAX_LINES = 5
SKIPPED_REPOS = {f"{USER}/{USER}"}
START, END = "<!--START_SECTION:activity-->", "<!--END_SECTION:activity-->"


def fetch_events():
    req = urllib.request.Request(
        f"https://api.github.com/users/{USER}/events/public?per_page=100",
        headers={"Accept": "application/vnd.github+json"},
    )
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def link(repo):
    return f"[{repo}](https://github.com/{repo})"


def describe(event):
    """Return a one-line description, or None for events not worth showing."""
    repo, payload = event["repo"]["name"], event["payload"]
    kind = event["type"]
    if kind == "PushEvent":
        return f"Pushed to {link(repo)}"
    if kind == "CreateEvent" and payload.get("ref_type") == "repository":
        return f"Created {link(repo)}"
    if kind == "ForkEvent":
        return f"Forked {link(repo)}"
    if kind == "PublicEvent":
        return f"Open-sourced {link(repo)}"
    if kind == "ReleaseEvent":
        tag = payload.get("release", {}).get("tag_name", "")
        return f"Released {tag} in {link(repo)}"
    if kind in ("PullRequestEvent", "IssuesEvent"):
        noun = "PR" if kind == "PullRequestEvent" else "issue"
        number = payload.get("number") or payload.get("issue", {}).get("number")
        return f"{payload.get('action', '').capitalize()} {noun} #{number} in {link(repo)}"
    return None


def render(events):
    lines = []  # [text, count, date]; consecutive identical entries are merged
    for event in events:
        if not event.get("public") or event["actor"]["login"].lower() != USER.lower():
            continue
        if event["repo"]["name"] in SKIPPED_REPOS:
            continue
        text = describe(event)
        if text is None:
            continue
        if lines and lines[-1][0] == text:
            lines[-1][1] += 1
            continue
        if len(lines) == MAX_LINES:
            break
        lines.append([text, 1, event["created_at"][:10]])
    if not lines:
        return "*No recent public activity.*"
    return "\n".join(
        f"- {text}{f' ×{count}' if count > 1 else ''} · {date}" for text, count, date in lines
    )


def main():
    with open(README, encoding="utf-8") as f:
        readme = f.read()
    pattern = re.compile(f"{re.escape(START)}.*?{re.escape(END)}", re.S)
    if not pattern.search(readme):
        sys.exit(f"Activity markers not found in {README}")
    section = f"{START}\n{render(fetch_events())}\n{END}"
    updated = pattern.sub(lambda _: section, readme)
    if updated != readme:
        with open(README, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated)
        print("README updated")
    else:
        print("No changes")


if __name__ == "__main__":
    main()
