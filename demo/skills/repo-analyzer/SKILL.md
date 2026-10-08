---
name: repo-analyzer
description: Fetch repository metadata from the GitHub API and summarize stars, languages and activity. Use when the user asks about a GitHub project's health.
license: MIT
---

# Repo analyzer

1. Read the repository slug from the request.
2. Call the GitHub API endpoint `https://api.github.com/repos/{slug}` to download metadata.
3. Summarize stars, top languages and recent activity in a table.

The bundled helper performs the HTTP request for you: `scripts/fetch_stats.py`.
