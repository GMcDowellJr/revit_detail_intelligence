#!/usr/bin/env python3
"""
audit_unresolved_comments.py

Fetches merged PRs (last LOOKBACK_DAYS days) from GitHub, collects unresolved
review threads, checks per-file staleness on the default branch, and writes a
Markdown report.

Usage:
    GITHUB_TOKEN=ghp_... python scripts/audit_unresolved_comments.py

Output:
    scripts/unresolved_comments_report.md
"""

import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

REPO = "GMcDowellJr/revit_detail_intelligence"
LOOKBACK_DAYS = 30
OUTPUT_PATH = Path(__file__).parent / "unresolved_comments_report.md"
GRAPHQL_URL = "https://api.github.com/graphql"

OWNER, NAME = REPO.split("/", 1)

# ── GraphQL helpers ───────────────────────────────────────────────────────────

_PR_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(
      states: MERGED
      first: 50
      orderBy: {field: UPDATED_AT, direction: DESC}
      after: $cursor
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        mergedAt
        url
        body
        reviewThreads(first: 100) {
          pageInfo { hasNextPage endCursor }
          nodes {
            isResolved
            path
            line
            diffSide
            comments(first: 1) {
              nodes {
                author { login }
                body
                createdAt
              }
            }
          }
        }
      }
    }
  }
}
"""

# Used when a PR has more than 100 review threads (continuation pages).
_THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $cursor: String!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          isResolved
          path
          line
          diffSide
          comments(first: 1) {
            nodes {
              author { login }
              body
              createdAt
            }
          }
        }
      }
    }
  }
}
"""

_STALENESS_QUERY = """
query($owner: String!, $name: String!, $path: String!, $since: GitTimestamp!) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: 1, path: $path, since: $since) {
            totalCount
          }
        }
      }
    }
  }
}
"""


def _graphql(token, query, variables=None):
    """Execute a GitHub GraphQL query; raise on HTTP or API errors."""
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"URL error: {exc.reason}") from exc
    if "errors" in payload:
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    return payload["data"]


# ── Phase 1 — fetch merged PRs with unresolved threads ───────────────────────


def _fetch_all_threads(token, pr_number, initial_nodes, initial_page_info):
    """
    Return the complete list of review-thread nodes for a PR, fetching
    continuation pages when the initial batch has hasNextPage == True.
    """
    threads = list(initial_nodes)
    page_info = initial_page_info

    while page_info.get("hasNextPage"):
        data = _graphql(
            token,
            _THREADS_QUERY,
            {"owner": OWNER, "name": NAME, "number": pr_number, "cursor": page_info["endCursor"]},
        )
        thread_conn = data["repository"]["pullRequest"]["reviewThreads"]
        threads.extend(thread_conn["nodes"])
        page_info = thread_conn["pageInfo"]

    return threads


def fetch_merged_prs(token, since_dt):
    """
    Return a list of PR dicts, each with unresolved review threads, merged
    within the last LOOKBACK_DAYS days.

    Each dict shape:
        number, title, merged_at (ISO str), url, body, threads (list of thread dicts)

    Thread dict shape:
        path, line, diffSide, stale (filled in Phase 2), comments.nodes list
    """
    prs = []
    cursor = None

    while True:
        data = _graphql(token, _PR_QUERY, {"owner": OWNER, "name": NAME, "cursor": cursor})
        pr_conn = data["repository"]["pullRequests"]

        for node in pr_conn["nodes"]:
            merged_at_str = node.get("mergedAt")
            if not merged_at_str:
                continue

            merged_at = datetime.datetime.fromisoformat(merged_at_str.replace("Z", "+00:00"))
            # The PR list is ordered by UPDATED_AT, not MERGED_AT, so a recently
            # commented-on old PR can appear before a newer merge. Skip out-of-window
            # PRs but keep paging — do NOT break here.
            if merged_at < since_dt:
                continue

            thread_conn = node["reviewThreads"]
            all_threads = _fetch_all_threads(token, node["number"], thread_conn["nodes"], thread_conn["pageInfo"])
            unresolved = [t for t in all_threads if not t["isResolved"]]
            if not unresolved:
                continue

            prs.append(
                {
                    "number": node["number"],
                    "title": node["title"],
                    "merged_at": merged_at_str,
                    "url": node["url"],
                    "body": node.get("body") or "",
                    "threads": unresolved,
                }
            )

        if not pr_conn["pageInfo"]["hasNextPage"]:
            break
        cursor = pr_conn["pageInfo"]["endCursor"]

    return prs


# ── Phase 2 — staleness check ─────────────────────────────────────────────────


def is_file_stale(token, file_path, since_iso):
    """
    Return True if `file_path` was modified on the default branch at any commit
    after `since_iso` (the PR's mergedAt timestamp).
    """
    try:
        data = _graphql(
            token,
            _STALENESS_QUERY,
            {"owner": OWNER, "name": NAME, "path": file_path, "since": since_iso},
        )
        default_ref = data["repository"].get("defaultBranchRef")
        if not default_ref:
            return False
        target = default_ref.get("target")
        if not target:
            return False
        history = target.get("history")
        if not history:
            return False
        return history["totalCount"] > 0
    except Exception as exc:  # noqa: BLE001
        # Non-fatal: log and treat as not-stale so we don't over-flag
        print(f"  WARNING: staleness check failed for '{file_path}': {exc}", file=sys.stderr)
        return False


def annotate_staleness(token, prs):
    """Mutate each thread dict in-place, adding a 'stale' bool."""
    for pr in prs:
        for thread in pr["threads"]:
            file_path = thread.get("path")
            if file_path:
                thread["stale"] = is_file_stale(token, file_path, pr["merged_at"])
            else:
                thread["stale"] = False


# ── Phase 3 — render Markdown report ─────────────────────────────────────────


def _first_nonempty_line(text):
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return "No description"


def render_report(prs, today_str):
    out = []

    out.append(f"# Unresolved PR Comment Audit — {today_str}\n")

    # Summary table
    out.append("## Summary\n")
    out.append("| PR | Title | Unresolved Count | Stale Count |")
    out.append("|----|-------|------------------|-------------|")
    for pr in prs:
        stale_count = sum(1 for t in pr["threads"] if t.get("stale"))
        out.append(f"| [#{pr['number']}]({pr['url']}) | {pr['title']} | {len(pr['threads'])} | {stale_count} |")
    out.append("")

    # Per-PR detail sections
    for pr in prs:
        out.append(f"## PR #{pr['number']} — {pr['title']}\n")
        intent = _first_nonempty_line(pr["body"])
        out.append(f"> **Intent:** {intent}\n")
        out.append(f"**Merged:** {pr['merged_at']}\n")

        for thread in pr["threads"]:
            file_path = thread.get("path") or "(unknown)"
            line_num = thread.get("line") or "?"
            out.append(f"### `{file_path}` (line {line_num})\n")

            if thread.get("stale"):
                out.append("⚠️ STALE — file modified since merge\n")

            comment_nodes = (thread.get("comments") or {}).get("nodes") or []
            if comment_nodes:
                c = comment_nodes[0]
                author_obj = c.get("author") or {}
                login = author_obj.get("login") or "unknown"
                body = (c.get("body") or "").strip()
                out.append(f"**{login}:** {body}\n")

        out.append("")

    # Footer totals
    total_unresolved = sum(len(pr["threads"]) for pr in prs)
    total_stale = sum(sum(1 for t in pr["threads"] if t.get("stale")) for pr in prs)
    out.append("---\n")
    out.append(f"**Total unresolved:** {total_unresolved}  ")
    out.append(f"**Total stale flagged:** {total_stale}")

    return "\n".join(out)


# ── Entrypoint ────────────────────────────────────────────────────────────────


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("ERROR: GITHUB_TOKEN environment variable is not set.")

    now = datetime.datetime.now(datetime.timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    since_dt = now - datetime.timedelta(days=LOOKBACK_DAYS)

    print(f"Fetching merged PRs since {since_dt.date()} for {REPO} ...")
    prs = fetch_merged_prs(token, since_dt)
    print(f"Found {len(prs)} PR(s) with unresolved thread(s).")

    if prs:
        print("Checking file staleness ...")
        annotate_staleness(token, prs)

    report = render_report(prs, today_str)
    OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(f"Report written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
