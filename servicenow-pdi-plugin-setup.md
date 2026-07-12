# ServiceNow PDI: Plugin Setup for EAP / Agile

Run this after provisioning a fresh PDI, before trying any `rm_story` / `rm_sprint` queries.
The two plugins below are required for SAFe/EAP tables — they're not active by default.

| Plugin ID | Name | Required for |
|-----------|------|--------------|
| `com.snc.sdlc.scrum_program` | Agile Development (SAFe/Program) | `rm_story`, `rm_sprint`, scrum roles |
| `sn_apw_advanced` | Strategic Planning Workspace | EAP UI, `sn_apw_advanced.*` roles |

Install `com.snc.sdlc.scrum_program` first — `sn_apw_advanced` depends on it.

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

## Option B — REST API

The Plugin API (`/api/now/v1/plugins/`) requires a separate REST API Access Policy from the
Table API one. Set that up first, then run the script below.

### One-time: add Plugin API access policy

1. **System Web Services > API Access Policies > REST API Access Policies > New**
2. **Name**: `plugin-api-key-policy`
3. **Active**: checked
4. **REST API**: `Plugin Management` (search for it in the picker)
5. Leave "Apply to all methods / resources / versions" checked
6. **Inbound authentication profiles** related list → Insert a new row → select your existing
   API key profile (the one from `servicenow-pdi-api-key-setup.md`)
7. Submit

### Activate plugins via script

```python
from snow_client import SnowClient, INSTANCE
import json, urllib.request, urllib.error

c = SnowClient()

PLUGINS = [
    'com.snc.sdlc.scrum_program',  # install first — sn_apw_advanced depends on it
    'sn_apw_advanced',
]

for pid in PLUGINS:
    print(f'Activating {pid}...')
    req = urllib.request.Request(
        f'{INSTANCE}/api/now/v1/plugins/{pid}/activate',
        data=b'{}',
        method='POST',
        headers=c._headers,
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
