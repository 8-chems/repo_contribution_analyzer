import streamlit as st
import requests
import pandas as pd
from collections import defaultdict
import matplotlib.pyplot as plt

GITHUB_API = "https://api.github.com"


# ── Token resolution ──────────────────────────────────────────────────────────
# Priority: st.secrets → session_state (user-entered) → None

def validate_token(token: str) -> bool:
    """Call /user to verify the token is valid and not expired."""
    if not token:
        return False
    r = requests.get(f"{GITHUB_API}/user", headers={"Authorization": f"token {token}"})
    return r.status_code == 200


def resolve_token() -> str | None:
    """
    Return the best available token:
      1. st.secrets["GITHUB_TOKEN"]  — if present and valid
      2. st.session_state token      — entered by the user in the UI
      3. None                        — unauthenticated
    """
    # 1. Check Streamlit secrets
    secret_token = st.secrets.get("GITHUB_TOKEN", "")
    if secret_token:
        if validate_token(secret_token):
            return secret_token
        else:
            st.warning(
                "⚠️ A `GITHUB_TOKEN` was found in `st.secrets` but it is invalid or expired. "
                "Please enter a valid token below.",
                icon="🔑",
            )

    # 2. Fall back to user-entered token in session state
    return st.session_state.get("github_token") or None


def get_headers(token: str | None) -> dict:
    if token:
        return {"Authorization": f"token {token}"}
    return {}


# ── UI ────────────────────────────────────────────────────────────────────────

st.title("GitHub Repo Contributor Analyzer")

# Resolve token first (runs the secrets check + optional validation warning)
token = resolve_token()

# Only show the token input field when no valid secret is available
if token:
    st.success("✅ Authenticated via `st.secrets` — no token input needed.", icon="🔒")
else:
    user_token = st.text_input(
        "GitHub Personal Access Token",
        type="password",
        placeholder="ghp_xxxxxxxxxxxxxxxxxxxx",
        help=(
            "Required for repos with > 60 commits. "
            "Generate one at GitHub → Settings → Developer settings → Personal access tokens."
        ),
        key="github_token",          # stored in session_state automatically
    )
    # Re-resolve after the widget renders so the entered value is picked up
    token = st.session_state.get("github_token") or None

repo_url = st.text_input(
    "GitHub Repository URL",
    placeholder="https://github.com/owner/repo",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_repo(url: str) -> tuple[str, str]:
    try:
        cleaned = url.strip("/").replace("https://github.com/", "")
        parts = cleaned.split("/")
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise ValueError
        return parts[0], parts[1]
    except (ValueError, IndexError):
        st.error("Invalid GitHub URL. Expected format: https://github.com/owner/repo")
        st.stop()


def get_commits(owner: str, repo: str, headers: dict) -> list:
    commits, page = [], 1
    while True:
        r = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/commits?per_page=100&page={page}",
            headers=headers,
        )
        if r.status_code != 200 or not r.json():
            break
        commits.extend(r.json())
        page += 1
    return commits


def get_commit_detail(owner: str, repo: str, sha: str, headers: dict) -> dict:
    r = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/commits/{sha}",
        headers=headers,
    )
    return r.json() if r.status_code == 200 else {}


def get_prs(owner: str, repo: str, headers: dict) -> list:
    prs, page = [], 1
    while True:
        r = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/pulls?state=all&per_page=100&page={page}",
            headers=headers,
        )
        if r.status_code != 200 or not r.json():
            break
        prs.extend(r.json())
        page += 1
    return prs


# ── Main analysis ─────────────────────────────────────────────────────────────

if repo_url:
    owner, repo = parse_repo(repo_url)
    headers = get_headers(token)

    st.info(f"Analyzing **{owner}/{repo}** …")

    commits = get_commits(owner, repo, headers)
    if not commits:
        st.error("No commits found. Check the repo URL or your token permissions.")
        st.stop()

    contributor_stats = defaultdict(lambda: {
        "commits": 0,
        "additions": 0,
        "deletions": 0,
        "files": 0,
        "dates": [],
        "login": None,
    })
    commit_timeseries = []

    progress = st.progress(0, text="Fetching commit details…")
    total = len(commits)

    for i, c in enumerate(commits):
        detail = get_commit_detail(owner, repo, c["sha"], headers)
        if not detail:
            continue

        author_name = (
            detail.get("commit", {}).get("author", {}).get("name", "unknown")
        )
        login = detail.get("author") and detail["author"].get("login")
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

        progress.progress((i + 1) / total, text=f"Processing commit {i + 1} / {total}")

    progress.empty()

    # PR counts keyed by GitHub login
    prs = get_prs(owner, repo, headers)
    pr_counts_by_login = defaultdict(int)
    for pr in prs:
        if isinstance(pr, dict) and pr.get("user"):
            pr_counts_by_login[pr["user"].get("login", "unknown")] += 1

    # Build dataframe
    rows = []
    for author_name, data in contributor_stats.items():
        churn = data["additions"] + data["deletions"]
        login = data["login"] or ""
        pr_count = pr_counts_by_login.get(login, 0)

        score = (
            data["commits"] * 1
            + churn / 100
            + data["files"] * 0.5
            + pr_count * 2
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
            "Score": round(score, 2),
        })

    df = pd.DataFrame(rows).sort_values(by="Score", ascending=False)

    st.subheader("Contributor Stats")
    st.dataframe(df)

    st.subheader("Commits per Contributor")
    fig, ax = plt.subplots()
    ax.bar(df["Contributor"], df["Commits"])
    plt.xticks(rotation=45, ha="right")
    st.pyplot(fig)

    st.subheader("Code Churn (Additions + Deletions)")
    fig2, ax2 = plt.subplots()
    ax2.bar(df["Contributor"], df["Churn"])
    plt.xticks(rotation=45, ha="right")
    st.pyplot(fig2)

    st.subheader("Commit Activity Over Time")
    if commit_timeseries:
        ts = pd.to_datetime(commit_timeseries)
        ts_df = (
            pd.DataFrame({"date": ts})
            .set_index("date")
            .assign(count=1)
            .resample("D")
            .sum()
            .fillna(0)
        )
        st.line_chart(ts_df)