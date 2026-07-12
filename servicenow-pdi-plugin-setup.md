# ServiceNow PDI: Plugin Setup for EAP / Agile

Run this after provisioning a fresh PDI, before trying any `rm_story` / `rm_sprint` queries.
The two plugins below are required for SAFe/EAP tables — they're not active by default.

| Plugin ID | Name | Required for |
|-----------|------|--------------|
| `sn_apw_advanced` | Strategic Planning Workspace | EAP UI, `sn_apw_advanced.*` roles — install first |
| `com.snc.sdlc.scrum_program` | Scrum Programs (SAFe/PI planning) | SAFe nav, Program Increments, Agile Teams |

Install `sn_apw_advanced` first — it pulls in Agile Development 2.0 (`com.snc.sdlc.agile.2.0`)
as a dependency. Then install `com.snc.sdlc.scrum_program` separately — it shows a for-fee
subscription warning but PDIs allow installation without an entitlement, just click Install.
After both are installed, log out and back in (or hit `/cache.do` first) for SAFe nav items to
appear. The Strategic Planning Workspace is at `/now/sow/home`.

---

## Option A — UI (recommended, ~5–10 min per plugin)

1. Navigate to **System Definition > Plugins** (or go directly to `/v_plugin_list.do`)
2. Search for the plugin by ID or name
3. Click the plugin row → **Install** (or **Activate** if it's already loaded but inactive)
4. Accept any dependency installs the wizard offers
5. Wait for the progress bar — do not navigate away
6. Repeat for the second plugin

**Verify after install:**

```
GET /api/now/table/rm_sprint?sysparm_limit=1
```

Should return `{"result": []}` (empty is fine — means the table exists). A `400 Invalid table` means the plugin didn't activate yet.

---

## Option B — REST API *(untested — may be worth exploring)*

The Plugin API (`/api/now/v1/plugins/`) is an internal system API — it does not appear in the
REST API Access Policy picker and cannot be unlocked for API key auth that way. It requires
an active admin browser session (cookie auth). Use `debug_auth.py` to confirm you have a valid
cookie session, then run the script below.

### Activate plugins via script (cookie auth required)

```python
# Requires cookie auth — API key is not accepted by the Plugin API.
# Capture cookies via Cookie-Monster first, then run this.
from snow_client import SnowClient, INSTANCE, _find_api_key, load_cookies
import json, urllib.request, urllib.error

# Force cookie auth even if SNOW_API_KEY is set
if _find_api_key():
    cookies = load_cookies()
    from snow_client import _fetch_session_info, cookie_header
    g_ck, _ = _fetch_session_info(cookies)
    headers = {
        "Cookie": cookie_header(cookies),
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-UserToken": g_ck,
    }
else:
    c = SnowClient()
    headers = c._headers

PLUGINS = [
    'sn_apw_advanced',             # install first — pulls in Agile Development 2.0
    'com.snc.sdlc.scrum_program',  # for-fee warning but installs fine on PDI
]

for pid in PLUGINS:
    print(f'Activating {pid}...')
    req = urllib.request.Request(
        f'{INSTANCE}/api/now/v1/plugins/{pid}/activate',
        data=b'{}',
        method='POST',
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read()).get('result', {})
            print(f'  status: {result.get("status")}')
    except urllib.error.HTTPError as e:
        print(f'  HTTP {e.code}: {e.read().decode()[:200]}')
```

Plugin activation is async — the POST returns immediately but install runs in the background.
Poll until the table is accessible:

```python
import time

def wait_for_table(client, table, retries=20, delay=15):
    for i in range(retries):
        try:
            client.get_table(table, limit=1)
            print(f'{table} is ready')
            return True
        except RuntimeError as e:
            if '400' in str(e):
                print(f'  [{i+1}/{retries}] waiting... ({delay}s)')
                time.sleep(delay)
            else:
                raise
    print(f'{table} still not ready after {retries * delay}s')
    return False

wait_for_table(c, 'rm_sprint')
wait_for_table(c, 'rm_story')
```

---

## Verify everything is working

```bash
python3 snow_client.py
```

Should show active PI sprints if any exist, or `(none found)` — not a `400 Invalid table` error.

```bash
python3 queries/pi_report.py --team "My Agile Team" --list
```
