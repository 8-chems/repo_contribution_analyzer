# GitHub Repo Contributor Analyzer

> An interactive Streamlit app that fetches commit history, code statistics, and pull request data from any GitHub repository — then computes and visualizes contribution metrics for every contributor.

**Stack:** Python · Streamlit · GitHub REST API · Pandas · Matplotlib

---

## Overview

This tool is designed for:

- **Team leads & engineering managers** — get a quick health snapshot of a codebase
- **Educators & students** — study open-source contribution patterns
- **Researchers** — analyze developer activity and code churn
- **Due diligence** — assess the activity level of any public GitHub project

---

## Features

- Fetches the **full commit history** with automatic pagination (handles repos > 100 commits)
- Retrieves per-commit statistics: additions, deletions, and files changed
- Collects **all pull requests** (paginated) and links them to contributors via GitHub login
- Computes a **composite activity Score** per contributor
- Renders an **interactive sortable table** of contributor stats
- Plots bar charts for **commits per contributor** and **code churn**
- Displays a **daily commit activity** time-series line chart
- Accepts an optional **GitHub Personal Access Token** to avoid API rate limits

---

## Requirements

```bash
pip install streamlit requests pandas matplotlib
```

### GitHub Personal Access Token *(recommended)*

Without authentication, the GitHub API limits requests to **60 per hour**. Since each commit triggers one additional detail request, any repo with more than ~60 commits will fail mid-analysis without a token.

**How to generate one:**

1. Go to [github.com](https://github.com) → Profile picture → **Settings**
2. Scroll to **Developer settings** → **Personal access tokens** → **Tokens (classic)**
3. Click **Generate new token**, set a name, check the `repo` scope, click **Generate**
4. **Copy it immediately** — GitHub will not display it again

---

## Usage

```bash
streamlit run github_analyzer.py
```

In the browser:

1. Paste a GitHub repo URL (e.g. `https://github.com/owner/repo`)
2. Optionally enter your GitHub Personal Access Token
3. A progress bar will track commit detail fetching
4. Results appear as a sortable table followed by charts

---

## Output Columns

| Column | Description |
|---|---|
| Contributor | Git author name of the committer |
| GitHub Login | GitHub username (used to join PR data) |
| Commits | Total number of commits made |
| Additions | Total lines of code added |
| Deletions | Total lines of code removed |
| Churn | Additions + Deletions (code volatility metric) |
| Files Changed | Total number of distinct files modified |
| PRs | Number of pull requests opened |
| Score | Composite activity score (see formula below) |

---

## Scoring Formula

```
Score = (Commits × 1) + (Churn ÷ 100) + (Files Changed × 0.5) + (PRs × 2)
```

Pull requests are weighted highest as they represent deliberate, reviewed contributions. Commit count and file breadth contribute linearly. Churn is scaled down to avoid inflating scores from large automated refactors.

---

## Bug Fixes (v1 → v2)

| # | Issue | Problem | Fix |
|---|---|---|---|
| 1 | Rate limiting | No auth token — 60 req/hr cap exceeded on any large repo | Added optional GitHub PAT header to all requests |
| 2 | URL parsing crash | `parse_repo()` throws `IndexError` on malformed URLs | Wrapped in `try/except` with `st.stop()` |
| 3 | Silent API failures | `get_commit_detail()` returned error JSON silently | Added HTTP status check; returns `{}` on failure |
| 4 | Incomplete PR data | `get_prs()` only fetched page 1 (max 100 PRs) | Added full pagination loop |
| 5 | PR/commit join mismatch | PRs use GitHub login; commits use git author name — join never matched | Captured login from commit detail; PR counts keyed by login |
| 6 | `resample()` crash | `groupby('date')` dropped `DatetimeIndex` before `resample()` | Switched to `set_index('date')` before resampling |
| 7 | Redundant column | `Commit Frequency` was identical to `Commits` | Removed duplicate column |
| 8 | No progress feedback | App appeared frozen on large repos | Added `st.progress()` bar per commit |
| 9 | Truncated axis labels | `xticks(rotation=45)` cut off contributor names | Added `ha='right'` for proper alignment |

---

## Known Limitations

- Git author names and GitHub logins can differ when a contributor uses different local git config values. The app captures both but the Score join is best-effort.
- Private repositories require a token with the `repo` scope.
- The GitHub API does not expose all historical data for very large repositories (> 10,000 commits) without using the GraphQL API.

---

## File Structure

```
github_analyzer.py    # Main Streamlit application (single-file)
```

No additional configuration files are required.

---

## License

Released for educational and personal use. Please respect the [GitHub API Terms of Service](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service) when using this tool at scale.
