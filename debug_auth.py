"""
Debug authentication — tests API key (preferred) then cookie-based auth.

Run: python3 debug_auth.py
"""

import json
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from snow_client import INSTANCE, COOKIE_FILE, load_cookies, cookie_header, _find_api_key


def try_api_key(key: str) -> bool:
    headers = {
        "Accept": "application/json",
        "x-sn-apikey": key,
    }
    url = f"{INSTANCE}/api/now/table/sys_user?sysparm_limit=1&sysparm_fields=user_name,name"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            rows = data.get("result", [])
            if rows:
                u = rows[0]
                name = u.get("name", {})
                name = name.get("display_value", name) if isinstance(name, dict) else name
                print(f"  SUCCESS — authenticated as: {name}")
                return True
            print(f"  Auth ok but empty result")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        print(f"  FAILED — HTTP {e.code}: {body}")
        return False


def fetch_csrf_token(cookies: dict) -> str | None:
    """Fetch the ServiceNow home page and extract the g_ck CSRF token."""
    req = urllib.request.Request(
        f"{INSTANCE}/",
        headers={
            "Cookie": cookie_header(cookies),
            "User-Agent": "Mozilla/5.0",
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode(errors="replace")
            # g_ck is the CSRF token ServiceNow embeds in every page
            m = re.search(r'g_ck\s*=\s*["\']([a-f0-9]+)["\']', html)
            if m:
                return m.group(1)
            # Sometimes it's in a <meta> tag
            m = re.search(r'name=["\']g_ck["\'][^>]+content=["\']([^"\']+)["\']', html)
            if m:
                return m.group(1)
            return None
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} fetching home page")
        return None


def try_api(cookies: dict, x_user_token: str, label: str):
    headers = {
        "Cookie": cookie_header(cookies),
        "Accept": "application/json",
        "X-UserToken": x_user_token,
    }
    url = f"{INSTANCE}/api/now/table/sys_user?sysparm_limit=1&sysparm_fields=user_name,name"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            rows = data.get("result", [])
            if rows:
                u = rows[0]
                name = u.get("name", {})
                name = name.get("display_value", name) if isinstance(name, dict) else name
                print(f"  [{label}] SUCCESS — user: {name}")
                return True
            print(f"  [{label}] Auth ok but empty result")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        print(f"  [{label}] HTTP {e.code}: {body}")
        return False


def main():
    print("=== ServiceNow Auth Debug ===\n")
    print(f"Instance: {INSTANCE}\n")

    # ---- API Key ----
    print("--- API Key ---")
    key = _find_api_key()
    if key:
        print(f"  Found SNOW_API_KEY: {key[:8]}...")
        try_api_key(key)
    else:
        print("  No SNOW_API_KEY found in environment or .env file")
        print("  See .env.example to set one up\n")

    # ---- Cookie Auth ----
    print("\n--- Cookie Auth ---")
    print("1. Loading cookies from ~/.snow_cookies...")
    try:
        cookies = load_cookies(COOKIE_FILE)
    except FileNotFoundError as e:
        print(f"   ERROR: {e}")
        sys.exit(1)

    print(f"   Loaded {len(cookies)} cookies:")
    for k, v in cookies.items():
        print(f"     {k} = {v[:12]}...")

    print("\n2. Fetching home page to extract g_ck CSRF token...")
    g_ck = fetch_csrf_token(cookies)
    if g_ck:
        print(f"   Found g_ck = {g_ck[:12]}...")
    else:
        print("   g_ck not found (session may be expired, or login page was returned)")

    print("\n3. Testing REST API with different X-UserToken values...")

    # Try with g_ck (correct CSRF token)
    if g_ck:
        try_api(cookies, g_ck, "g_ck CSRF token")

    # Try with glide_session_store value
    session_store = cookies.get("glide_session_store", "")
    if session_store:
        try_api(cookies, session_store, "glide_session_store")

    # Try with empty X-UserToken (some instances allow it for GET)
    try_api(cookies, "", "no X-UserToken")

    print("\n4. Checking if we're being redirected to SSO (session expired)...")
    req = urllib.request.Request(
        f"{INSTANCE}/api/now/table/sys_user?sysparm_limit=1",
        headers={"Cookie": cookie_header(cookies), "Accept": "application/json"},
    )
    # Don't follow redirects so we can detect SSO bounce
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req) as resp:
            print(f"   Response code: {resp.status} (no redirect — session is live)")
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            loc = e.headers.get("Location", "?")
            print(f"   Redirected ({e.code}) → {loc[:80]}")
            print("   Session is EXPIRED — re-extract cookies from browser.")
        else:
            print(f"   HTTP {e.code}")


if __name__ == "__main__":
    main()
