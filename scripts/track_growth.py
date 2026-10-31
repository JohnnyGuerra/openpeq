#!/usr/bin/env python3
"""
Growth & Traffic Tracker for dac-peq-manager
Archives GitHub traffic (views, clones, referrers), star history, and release metrics
to permanently prevent data loss from GitHub's 14-day rolling traffic window.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_DEFAULT = "JohnnyGuerra/openpeq"
BASE_DIR = Path(__file__).resolve().parent.parent
METRICS_DIR = BASE_DIR / "metrics"


def get_token():
    token = os.environ.get("METRICS_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    try:
        proc = subprocess.run(["gh", "auth", "token"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except FileNotFoundError:
        pass
    return None


def github_api_get(endpoint: str, token: str, repo: str):
    url = f"https://api.github.com/repos/{repo}/{endpoint}".rstrip("/")
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "dac-peq-growth-tracker",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[WARN] HTTP {e.code} on {url}: {body}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[ERROR] Request failed on {url}: {e}", file=sys.stderr)
        return None


def load_json(path: Path, default):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def merge_time_series(existing_items: list, new_items: list) -> list:
    """Merges daily metrics by timestamp key, updating counts if new data has non-zero values."""
    by_date = {item["timestamp"][:10]: dict(item) for item in existing_items if "timestamp" in item}
    for item in new_items:
        date_key = item["timestamp"][:10]
        if date_key in by_date:
            # Keep max of counts / uniques to avoid overwriting complete days with partials
            by_date[date_key]["count"] = max(by_date[date_key].get("count", 0), item.get("count", 0))
            by_date[date_key]["uniques"] = max(by_date[date_key].get("uniques", 0), item.get("uniques", 0))
        else:
            by_date[date_key] = dict(item)
    return sorted(by_date.values(), key=lambda x: x["timestamp"])


def update_referrers(existing_referrers: dict, new_referrers: list, today_str: str) -> dict:
    """Tracks cumulative referrers along with last observed date."""
    for ref in new_referrers:
        name = ref.get("referrer")
        if not name:
            continue
        count = ref.get("count", 0)
        uniques = ref.get("uniques", 0)
        if name not in existing_referrers:
            existing_referrers[name] = {
                "referrer": name,
                "first_seen": today_str,
                "last_seen": today_str,
                "count": count,
                "uniques": uniques,
            }
        else:
            existing_referrers[name]["last_seen"] = today_str
            existing_referrers[name]["count"] = max(existing_referrers[name].get("count", 0), count)
            existing_referrers[name]["uniques"] = max(existing_referrers[name].get("uniques", 0), uniques)
    return existing_referrers


def render_dashboard(repo: str, repo_info: dict, views_data: list, clones_data: list, referrers: dict, releases: list) -> str:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    total_views = sum(item.get("count", 0) for item in views_data)
    total_unique_views = sum(item.get("uniques", 0) for item in views_data)
    total_clones = sum(item.get("count", 0) for item in clones_data)
    total_unique_cloners = sum(item.get("uniques", 0) for item in clones_data)

    stars = repo_info.get("stargazers_count", 0) if repo_info else "N/A"
    forks = repo_info.get("forks_count", 0) if repo_info else "N/A"
    watchers = repo_info.get("subscribers_count", 0) if repo_info else "N/A"
    open_issues = repo_info.get("open_issues_count", 0) if repo_info else "N/A"

    lines = [
        f"# 📊 Growth & Analytics Dashboard: [{repo}](https://github.com/{repo})",
        "",
        f"> **Last Updated**: `{now_utc}`  ",
        "> **Archival Status**: Traffic data is permanently retained and preserved beyond GitHub's 14-day deletion limit.",
        "",
        "## 🌟 Repository Overview",
        "",
        "| Metric | Count | Description |",
        "| :--- | :---: | :--- |",
        f"| **Stars** | ⭐️ **{stars}** | Stargazers |",
        f"| **Forks** | 🍴 **{forks}** | Network forks |",
        f"| **Watchers** | 👁️ **{watchers}** | Active subscribers |",
        f"| **Open Issues** | ⚠️ **{open_issues}** | Feature requests & bugs |",
        f"| **Total Page Views** | 📈 **{total_views}** | Cumulative views recorded |",
        f"| **Unique Visitors** | 👤 **{total_unique_views}** | Cumulative daily unique visitors |",
        f"| **Total Clones** | 📦 **{total_clones}** | Cumulative git clone operations |",
        f"| **Unique Cloners** | 🧑‍💻 **{total_unique_cloners}** | Cumulative daily unique cloners |",
        "",
        "---",
        "",
        "## 🔗 Top Referrers",
        "",
        "| Referrer Source | Views | Unique Visitors | First Seen | Last Seen |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ]

    sorted_refs = sorted(referrers.values(), key=lambda r: r.get("count", 0), reverse=True)
    if sorted_refs:
        for ref in sorted_refs:
            lines.append(f"| **{ref.get('referrer')}** | {ref.get('count', 0)} | {ref.get('uniques', 0)} | {ref.get('first_seen', '-')} | {ref.get('last_seen', '-')} |")
    else:
        lines.append("| *No referral data captured yet* | - | - | - | - |")

    lines.extend([
        "",
        "---",
        "",
        "## 📅 Daily Traffic History",
        "",
        "| Date | Views | Unique Visitors | Clones | Unique Cloners |",
        "| :---: | :---: | :---: | :---: | :---: |",
    ])

    # Combine views & clones by date descending
    all_dates = set([x["timestamp"][:10] for x in views_data] + [x["timestamp"][:10] for x in clones_data])
    v_map = {x["timestamp"][:10]: x for x in views_data}
    c_map = {x["timestamp"][:10]: x for x in clones_data}

    for d in sorted(all_dates, reverse=True):
        v = v_map.get(d, {})
        c = c_map.get(d, {})
        v_count = v.get("count", 0)
        v_u = v.get("uniques", 0)
        c_count = c.get("count", 0)
        c_u = c.get("uniques", 0)
        lines.append(f"| `{d}` | {v_count} | {v_u} | {c_count} | {c_u} |")

    # Release downloads
    if releases:
        lines.extend([
            "",
            "---",
            "",
            "## 🚀 Release Downloads",
            "",
            "| Release | Asset | Downloads | Size | Published |",
            "| :--- | :--- | :---: | :---: | :---: |",
        ])
        for rel in releases:
            tag = rel.get("tag_name", "")
            pub = rel.get("published_at", "")[:10]
            assets = rel.get("assets", [])
            if not assets:
                lines.append(f"| `{tag}` | *(source tarball/zip only)* | - | - | {pub} |")
            for asset in assets:
                name = asset.get("name", "")
                dl = asset.get("download_count", 0)
                size_mb = f"{asset.get('size', 0) / (1024 * 1024):.2f} MB"
                lines.append(f"| `{tag}` | `{name}` | **{dl}** | {size_mb} | {pub} |")

    lines.append("")
    return "\n".join(lines)


def main():
    repo = os.environ.get("GITHUB_REPOSITORY") or REPO_DEFAULT
    token = get_token()

    if not token:
        print("[ERROR] No GitHub token found. Please set GITHUB_TOKEN or authenticate with 'gh auth login'.", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Fetching growth metrics for {repo}...")
    METRICS_DIR.mkdir(parents=True, exist_ok=True)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Fetch Repository Info
    repo_info = github_api_get("", token, repo)

    # 2. Fetch Traffic Views
    views_path = METRICS_DIR / "traffic_views.json"
    existing_views = load_json(views_path, [])
    views_resp = github_api_get("traffic/views", token, repo)
    if views_resp and "views" in views_resp:
        merged_views = merge_time_series(existing_views, views_resp["views"])
        save_json(views_path, merged_views)
    else:
        merged_views = existing_views

    # 3. Fetch Traffic Clones
    clones_path = METRICS_DIR / "traffic_clones.json"
    existing_clones = load_json(clones_path, [])
    clones_resp = github_api_get("traffic/clones", token, repo)
    if clones_resp and "clones" in clones_resp:
        merged_clones = merge_time_series(existing_clones, clones_resp["clones"])
        save_json(clones_path, merged_clones)
    else:
        merged_clones = existing_clones

    # 4. Fetch Traffic Referrers
    refs_path = METRICS_DIR / "referrers.json"
    existing_refs = load_json(refs_path, {})
    refs_resp = github_api_get("traffic/popular/referrers", token, repo)
    if refs_resp and isinstance(refs_resp, list):
        updated_refs = update_referrers(existing_refs, refs_resp, today_str)
        save_json(refs_path, updated_refs)
    else:
        updated_refs = existing_refs

    # 5. Fetch Popular Paths
    paths_path = METRICS_DIR / "popular_paths.json"
    paths_resp = github_api_get("traffic/popular/paths", token, repo)
    if paths_resp and isinstance(paths_resp, list):
        save_json(paths_path, paths_resp)

    # 6. Fetch Releases
    releases_resp = github_api_get("releases", token, repo) or []

    # 7. Snapshot record
    snapshots_path = METRICS_DIR / "snapshots.json"
    snapshots = load_json(snapshots_path, [])
    current_snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stars": repo_info.get("stargazers_count", 0) if repo_info else None,
        "forks": repo_info.get("forks_count", 0) if repo_info else None,
        "watchers": repo_info.get("subscribers_count", 0) if repo_info else None,
        "open_issues": repo_info.get("open_issues_count", 0) if repo_info else None,
        "cumulative_views": sum(x.get("count", 0) for x in merged_views),
        "cumulative_clones": sum(x.get("count", 0) for x in merged_clones),
    }
    snapshots.append(current_snapshot)
    save_json(snapshots_path, snapshots)

    # 8. Render GROWTH.md Dashboard
    dashboard_md = render_dashboard(repo, repo_info, merged_views, merged_clones, updated_refs, releases_resp)
    dashboard_path = METRICS_DIR / "GROWTH.md"
    with open(dashboard_path, "w", encoding="utf-8") as f:
        f.write(dashboard_md)

    print(f"[+] Successfully updated growth metrics in {METRICS_DIR}")
    print(f"[+] Dashboard written to {dashboard_path}")


if __name__ == "__main__":
    main()
