"""Fetch repository stats from the GitHub API (needs outbound network)."""

import json

import urllib.request

API = "https://api.github.com/repos/"


def fetch_stats(slug: str) -> dict:
    with urllib.request.urlopen(API + slug, timeout=30) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


if __name__ == "__main__":
    print(json.dumps(fetch_stats("anthropics/skills"), indent=2)[:400])
