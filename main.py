import streamlit as st
import requests
import pandas as pd
from collections import defaultdict
import matplotlib.pyplot as plt

st.title("GitHub Repo Contributor Analyzer")

repo_url = st.text_input("Enter GitHub repo URL (e.g. https://github.com/owner/repo)")
github_token = st.text_input("GitHub Personal Access Token (optional, avoids rate limits)", type="password")

GITHUB_API = "https://api.github.com"


def get_headers():
    """FIX 1: Include auth token to avoid the 60 req/hour rate limit."""
    if github_token:
        return {"Authorization": f"token {github_token}"}
    return {}


def parse_repo(url):
    """FIX 2: Validate URL and handle malformed input gracefully."""
    try:
        cleaned = url.strip("/").replace("https://github.com/", "")
        parts = cleaned.split("/")
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise ValueError
        return parts[0], parts[1]
    except (ValueError, IndexError):
        st.error("Invalid GitHub URL. Expected format: https://github.com/owner/repo")
        st.stop()


def get_commits(owner, repo):
    commits = []
    page = 1
    while True:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/commits?per_page=100&page={page}"
        r = requests.get(url, headers=get_headers())
        if r.status_code != 200 or len(r.json()) == 0:
            break
        commits.extend(r.json())
        page += 1
    return commits


def get_commit_detail(owner, repo, sha):
    """FIX 3: Check HTTP status before returning; return empty dict on failure."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/commits/{sha}"
    r = requests.get(url, headers=get_headers())
    if r.status_code != 200:
        return {}
    return r.json()


def get_prs(owner, repo):
    """FIX 4: Paginate through all PRs, not just the first 100."""
    prs = []
    page = 1
    while True:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls?state=all&per_page=100&page={page}"
        r = requests.get(url, headers=get_headers())
        if r.status_code != 200 or len(r.json()) == 0:
            break
        prs.extend(r.json())
        page += 1
    return prs


if repo_url:
    owner, repo = parse_repo(repo_url)
    st.info(f"Analyzing {owner}/{repo} ...")

    commits = get_commits(owner, repo)

    if not commits:
        st.error("No commits found. Check the repo URL or your token permissions.")
        st.stop()

    contributor_stats = defaultdict(lambda: {
        "commits": 0,
        "additions": 0,
        "deletions": 0,
        "files": 0,
        "dates": [],
        # FIX 5: Track GitHub login separately for PR join
        "login": None,
    })

    commit_timeseries = []

    # FIX 6: Show a progress bar so the app doesn't appear frozen
    progress = st.progress(0, text="Fetching commit details...")
    total = len(commits)

    for i, c in enumerate(commits):
        sha = c["sha"]
        detail = get_commit_detail(owner, repo, sha)

        if not detail:
            continue

        author_name = (detail.get("commit", {})
                             .get("author", {})
                             .get("name", "unknown"))

        # FIX 5 (cont.): Capture the GitHub login alongside the git author name
        login = None
        if detail.get("author"):
            login = detail["author"].get("login")
        contributor_stats[author_name]["login"] = login

        stats = detail.get("stats", {})
        contributor_stats[author_name]["commits"] += 1
        contributor_stats[author_name]["additions"] += stats.get("additions", 0)
        contributor_stats[author_name]["deletions"] += stats.get("deletions", 0)
        contributor_stats[author_name]["files"] += len(detail.get("files", []))

        date = detail.get("commit", {}).get("author", {}).get("date")
        if date:
            contributor_stats[author_name]["dates"].append(date)
            commit_timeseries.append(date)

        progress.progress((i + 1) / total, text=f"Processing commit {i + 1}/{total}")

    progress.empty()

    # FIX 5 (cont.): Build PR counts keyed by GitHub login
    prs = get_prs(owner, repo)
    pr_counts_by_login = defaultdict(int)
    for pr in prs:
        if isinstance(pr, dict) and pr.get("user"):
            login = pr["user"].get("login", "unknown")
            pr_counts_by_login[login] += 1

    # Build dataframe
    rows = []
    for author_name, data in contributor_stats.items():
        churn = data["additions"] + data["deletions"]
        login = data["login"] or ""
        pr_count = pr_counts_by_login.get(login, 0)

        score = (
            data["commits"] * 1 +
            churn / 100 +
            data["files"] * 0.5 +
            pr_count * 2
        )

        rows.append({
            "Contributor": author_name,
            "GitHub Login": login,
            "Commits": data["commits"],
            "Additions": data["additions"],
            "Deletions": data["deletions"],
            "Churn": churn,
            "Files Changed": data["files"],
            "PRs": pr_count,
            # FIX 7: Removed "Commit Frequency" — it was identical to "Commits"
            "Score": round(score, 2)
        })

    df = pd.DataFrame(rows).sort_values(by="Score", ascending=False)

    st.subheader("Contributor Stats")
    st.dataframe(df)

    # Plot: commits per contributor
    st.subheader("Commits per Contributor")
    fig, ax = plt.subplots()
    ax.bar(df["Contributor"], df["Commits"])
    plt.xticks(rotation=45, ha="right")
    st.pyplot(fig)

    # Plot: code churn
    st.subheader("Code Churn (Additions + Deletions)")
    fig2, ax2 = plt.subplots()
    ax2.bar(df["Contributor"], df["Churn"])
    plt.xticks(rotation=45, ha="right")
    st.pyplot(fig2)

    # Commit activity over time
    st.subheader("Commit Activity Over Time")
    if commit_timeseries:
        # FIX 8: Set the datetime column as index BEFORE resampling
        ts = pd.to_datetime(commit_timeseries)
        ts_df = pd.DataFrame({"date": ts})
        ts_df = ts_df.set_index("date").assign(count=1).resample("D").sum().fillna(0)
        st.line_chart(ts_df)