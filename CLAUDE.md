# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo does

Command-line tooling for querying and updating a personal ServiceNow PDI (`https://dev432501.service-now.com`) via the Table REST API. Auth uses either cookie-based session or API key. The primary use cases are PI reporting and bulk story management.

## Running scripts

```bash
# Verify auth and list active sprints
python3 snow_client.py

# PI story report
python3 queries/pi_report.py --team "My Agile Team" --pi "16. 5"
python3 queries/pi_report.py --team "My Agile Team" --pi "16. 5" --all-states
python3 queries/pi_report.py --team "My Agile Team" --list   # show all PI iterations for the team

# Bulk-move stories to a different PI sprint
python3 move_to_pi.py --stories STRY0032845 STRY0032403 --pi "16. 5"
python3 move_to_pi.py --stories STRY0032845 --pi "16. 5" --dry-run

# Auth troubleshooting
python3 debug_auth.py
python3 debug_html.py
```

No build step, no dependencies beyond the Python 3.11+ standard library.

## Authentication

`SnowClient.__init__` resolves auth in this order:

1. **API key** (preferred) — `SNOW_API_KEY` from environment or `.env` file → `x-sn-apikey` header, no browser session needed. Copy `.env.example` to `.env` and set the key. See `servicenow-pdi-api-key-setup.md` for how to create one.
2. **Cookie-Monster** — `%USERPROFILE%\.session-cookies\dev432501.service-now.com.env` — click **Send to Agent** in the extension after logging in.
3. **Legacy cookies** — `~/.snow_cookies` (KEY=VALUE lines).

For cookie auth, the client also GETs the home page to extract the `g_ck` CSRF token and sends it as `X-UserToken`. A 401 always means expired credentials — re-create the API key or re-capture cookies.

## ServiceNow data model

Stories (`rm_story`) link to sprints (`rm_sprint`) via the `sprint` field. Each PI iteration per team is its own `rm_sprint` record named `{Team} - {PI}.{Iteration}` with a **space before the iteration number**: `16. 5`, not `16.5`. The `release` and `scrum_team` fields on `rm_story` are unused in the EAP/SAFe setup — always use `sprint`.

PATCH fields take raw numeric values, not display labels (`state=4` not `state=Accepted`). See `spec/data-model.md` for all value codes.

## Key files

| File | Purpose |
|------|---------|
| `snow_client.py` | `SnowClient` class — `get_table`, `get_record`, `patch_record`, `aggregate` |
| `move_to_pi.py` | Bulk-move stories between PI sprints |
| `queries/pi_report.py` | PI completion report grouped by assignee |
| `debug_auth.py` | Diagnose cookie/auth failures |
| `spec/data-model.md` | Table schemas, field names, raw value codes |
| `spec/auth.md` | Auth approaches and cookie details |
| `servicenow-pdi-api-key-setup.md` | API Key setup guide for PDI instances |
