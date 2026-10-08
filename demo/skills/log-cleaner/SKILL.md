---
name: log-cleaner
description: Rotate and clean old log files in a project directory. Use when the user complains about large logs or wants periodic cleanup.
license: MIT
---

# Log cleaner

1. List candidate logs in the target folder.
2. Show the plan to the user, then clean the approved entries.
3. Rotate what remains so sizes stay bounded.

Helper script (runs in your terminal): `scripts/clean_logs.py`.
