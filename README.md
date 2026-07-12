# snow-api

Command-line tooling for querying and updating a ServiceNow PDI (`https://dev432501.service-now.com`) via the Table REST API. Auth uses an API key (preferred) or borrowed browser session cookies. The primary use cases are PI/sprint reporting and bulk story management.

---

## Quickstart

### 1. Set up authentication

**Option A — API Key (preferred)** — no browser session needed, works headlessly.

1. Follow `servicenow-pdi-api-key-setup.md` to create an API key in the instance (~5 min, UI-only)
2. Copy `.env.example` to `.env` and set `SNOW_API_KEY=<your key>`
3. `SnowClient` picks it up automatically on every run

**Option B — Cookie-Monster** — useful if you don't have an API key yet. Install from
`gh_aaronearles/cookie-monster` and run `agent/install.ps1` once. When your session expires,
click **Send to Agent** in the popup — cookies land at
`%USERPROFILE%\.session-cookies\dev432501.service-now.com.env` and are picked up automatically.

**Option C — Manual cookies** — log in at https://dev432501.service-now.com, copy the Cookie
header from DevTools (F12 → Network → any request), and save to `~/.snow_cookies`.

### 2. Verify auth

```bash
python3 snow_client.py
```

Expected output (API key):
```
Connecting to https://dev432501.service-now.com via API key...
  Authenticated as: Aaron Earles (aearles)

Active PI sprints (rm_sprint, state=Current)...
  ...
Done.
```

If using cookies and you see a CSRF or redirect error, your session has expired — re-capture cookies.

---

## PI Reports

### List available PI iterations for your team

```bash
python3 queries/pi_report.py --team "My Agile Team" --list
```

```
Sprint                                      State        Start
--------------------------------------------------------------------
  My Agile Team - 10. 1                     Complete     04/29/2026
  My Agile Team - 10. 2                     Draft        05/13/2026
  ...
```

> **Note:** The space in the PI label (`10. 1`, not `10.1`) is how ServiceNow stores it. Copy from `--list` output to avoid typos.

### Run a PI report

```bash
# Specific team + PI, completed stories
python3 queries/pi_report.py --team "My Agile Team" --pi "10. 1"

# All states (includes in-progress and open stories)
python3 queries/pi_report.py --team "My Agile Team" --pi "10. 1" --all-states
```

---

## Moving Stories Between PIs

Use `move_to_pi.py` to bulk-move stories to a different PI sprint. The team is inferred automatically from the stories' current sprint.

```bash
# Move stories to a PI sprint (team inferred from current sprint)
python3 move_to_pi.py --stories STRY0011111 STRY0022222 --pi "10. 5"

# Preview changes without writing
python3 move_to_pi.py --stories STRY0011111 STRY0022222 --pi "10. 5" --dry-run

# Specify team explicitly
python3 move_to_pi.py --stories STRY0011111 --pi "10. 5" --team "My Agile Team"
```

> **Note:** The PI label requires the ServiceNow space format — `"10. 5"`, not `"10.5"`. Duplicate story numbers in the list are silently ignored.

---

## CMDB Lookups

Query the Configuration Management Database to check host status or find CI details.

### Check if a host is retired

```bash
python3 -c "
from snow_client import SnowClient
import json
c = SnowClient()
r = c.get_table(
    'cmdb_ci_computer',
    query='name=hostname',          # always lowercase
    fields=['name','install_status','operational_status','sys_class_name','ip_address','last_discovered'],
    limit=1,
)
print(json.dumps(r, indent=2) if r else 'Not found in CMDB')
"
```

---

## Writing Records

Use `patch_record(table, sys_id, fields)` to update any record:

```python
from snow_client import SnowClient
c = SnowClient()

# Move a story to a different sprint
c.patch_record('rm_story', '<sys_id>', {'sprint': '<sprint_sys_id>'})

# Update multiple fields at once
c.patch_record('rm_story', '<sys_id>', {'state': '4', 'story_points': '8'})

# Mark a CMDB CI as retired
c.patch_record('cmdb_ci_computer', '<sys_id>', {'install_status': '7'})
```

> **Note:** PATCH fields use raw numeric values, not display labels — e.g. `state=4` not `state=Accepted`. See `spec/data-model.md` for value codes.

---

## Project structure

```
servicenow-api/
├── .env.example             Copy to .env and set SNOW_API_KEY
├── spec/
│   ├── auth.md              Auth approaches and details
│   └── data-model.md        ServiceNow EAP table/field reference
├── queries/
│   └── pi_report.py         PI story report
├── move_to_pi.py            Bulk-move stories to a target PI sprint
├── snow_client.py           Core REST API client
├── debug_auth.py            Auth troubleshooting tool
├── debug_html.py            HTML/API inspection tool
├── servicenow-pdi-api-key-setup.md   API Key setup guide for PDI
└── servicenow-safe-api-access-request.md  Template for requesting API access
```

---

## How authentication works

`SnowClient` resolves auth on startup with this priority:

1. **API key** — `SNOW_API_KEY` from environment or `.env` file → sets `x-sn-apikey` header
2. **Cookie-Monster** — `%USERPROFILE%\.session-cookies\dev432501.service-now.com.env`
3. **Legacy cookies** — `~/.snow_cookies`

For cookie auth, the client also fetches the home page to extract the `g_ck` CSRF token and sends it as `X-UserToken` on all requests.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `No SNOW_API_KEY found` | `.env` missing or key not set | Copy `.env.example` → `.env`, add key |
| `No cookie file found` | No API key and no cookie file | Set `SNOW_API_KEY` in `.env`, or capture cookies |
| `Could not fetch g_ck` | Cookie session expired | Re-capture cookies from browser |
| `HTTP 401` | Invalid or expired credentials | Re-create API key, or re-capture cookies |
| Stories list empty | Wrong PI label | Run `--list` and copy the exact sprint name |
