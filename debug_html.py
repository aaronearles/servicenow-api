"""
Dump relevant snippets from the ServiceNow home page to find session globals
and inspect raw API responses.

Run: python3 debug_html.py
"""

import json
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from snow_client import INSTANCE, COOKIE_FILE, load_cookies, cookie_header, SnowClient

cookies = load_cookies(COOKIE_FILE)

print("=== Fetching home page HTML ===\n")
req = urllib.request.Request(
    f"{INSTANCE}/",
    headers={"Cookie": cookie_header(cookies), "User-Agent": "Mozilla/5.0", "Accept": "text/html"},
)
with urllib.request.urlopen(req) as resp:
    html = resp.read().decode(errors="replace")

print(f"Page size: {len(html):,} bytes\n")

# Dump window.NOW.user block
print("=== window.NOW.user object ===\n")
m = re.search(r'window\.NOW\.user\s*=\s*(\{.*?\});', html, re.DOTALL)
if m:
    print(m.group(1)[:1000])
else:
    print("  NOT FOUND")

# Dump uxGlobals.session user portion
print("\n=== uxGlobals.session (first 400 chars) ===\n")
m2 = re.search(r'uxGlobals\.session\s*=.*', html)
if m2:
    print(m2.group(0)[:400])
else:
    print("  NOT FOUND")

client = SnowClient(cookies)
print(f"\nSession user_id : {client.session_user_id}")
print(f"Session username: {client.session_username}")
print(f"Session name    : {client.session_full_name}")

def probe(label, url):
    req = urllib.request.Request(url, headers=client._headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            records = data.get("result", [])
            print(f"  [{label}] OK — {len(records)} records")
            for r in records:
                fields = {k: v for k, v in r.items() if k in ("name","short_description","state","sys_class_name","type","sprint_type","phase_type")}
                print(f"    {fields}")
            return records
    except urllib.error.HTTPError as e:
        print(f"  [{label}] HTTP {e.code}: {e.read().decode()[:100]}")
        return []

from urllib.parse import urlencode

BASE = f"{INSTANCE}/api/now/table"

def table_url(table, **params):
    params.setdefault("sysparm_display_value", "true")
    return f"{BASE}/{table}?{urlencode(params)}"

print("\n=== rm_story: first 3 stories (sprint/release/scrum_team fields) ===")
records = probe(
    "rm_story lookup",
    table_url("rm_story",
              sysparm_query="active=true",
              sysparm_limit=3,
              sysparm_fields="number,short_description,state,sprint,release,scrum_team"),
)
for r in records:
    print(f"    sprint    = {r.get('sprint')}")
    print(f"    release   = {r.get('release')}")
    print(f"    scrum_team= {r.get('scrum_team')}")

print("\n=== rm_sprint: first 10 sprints ===")
probe("rm_sprint", table_url("rm_sprint",
    sysparm_query="active=true",
    sysparm_limit=10,
    sysparm_fields="sys_id,name,short_description,state,start_date"))

print("\n=== rm_release: first 10 releases ===")
probe("rm_release", table_url("rm_release",
    sysparm_query="active=true",
    sysparm_limit=10,
    sysparm_fields="sys_id,short_description,state,start_date"))
