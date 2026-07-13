"""
ServiceNow REST API client — API key (preferred) or cookie-based session auth.

Auth resolution order:
    1. SNOW_API_KEY env var or .env file  (preferred — no browser session needed)
    2. Cookie-Monster store: %USERPROFILE%\.session-cookies\<hostname>.env
    3. Legacy ~/.snow_cookies

Usage:
    python snow_client.py   # verify auth and list active sprints
"""

import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlencode
import urllib.request
import urllib.error


def _load_dotenv(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE pairs from a .env file, stripping quotes."""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# .env in project root, loaded once at import
_DOTENV = _load_dotenv(Path(__file__).parent / ".env")

INSTANCE = (
    os.environ.get("SNOW_INSTANCE") or _DOTENV.get("SNOW_INSTANCE") or "https://dev432501.service-now.com"
).rstrip("/")
SNOW_HOSTNAME = INSTANCE.removeprefix("https://").removeprefix("http://")
COOKIE_FILE = Path.home() / ".snow_cookies"

# Cookie-Monster store — preferred source for cookie-based auth
_CM_STORE_WIN = Path(os.environ.get("USERPROFILE", "")) / ".session-cookies"
_CM_STORE_WSL = Path(f"/mnt/c/Users/{os.environ.get('USER', '')}/.session-cookies")
_CM_FILE = (
    _CM_STORE_WIN / f"{SNOW_HOSTNAME}.env"
    if _CM_STORE_WIN.exists()
    else _CM_STORE_WSL / f"{SNOW_HOSTNAME}.env"
)


def _find_api_key() -> str | None:
    """Return SNOW_API_KEY from environment or .env file, or None."""
    return os.environ.get("SNOW_API_KEY") or _DOTENV.get("SNOW_API_KEY") or None


def _parse_cookie_string(s: str) -> dict[str, str]:
    cookies = {}
    for part in s.split(";"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            cookies[k.strip()] = v.strip()
    return cookies


def load_cookies(path: Path | None = None) -> dict[str, str]:
    """Load session cookies, preferring Cookie-Monster store over legacy ~/.snow_cookies.

    Resolution order:
      1. Explicit path argument (if provided)
      2. %USERPROFILE%\.session-cookies\<hostname>.env  (Cookie-Monster)
      3. ~/.snow_cookies  (legacy, supports KEY=VALUE and .env shell-variable format)
    """
    if path is not None:
        source = path
    elif _CM_FILE.exists():
        source = _CM_FILE
    elif COOKIE_FILE.exists():
        source = COOKIE_FILE
    else:
        raise FileNotFoundError(
            f"No cookie file found and no SNOW_API_KEY set. Options:\n"
            f"  API key (preferred): set SNOW_API_KEY in .env (see .env.example)\n"
            f"  Cookie-Monster: visit {INSTANCE} in browser, click extension, Send to Agent\n"
            f"  Legacy fallback: save cookies to {COOKIE_FILE} (see spec/auth.md)"
        )

    cookies: dict[str, str] = {}
    for line in source.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            # Legacy .env shell-variable format: VARNAME="key=val; key2=val2"
            if "; " in v or (v.startswith("{") and "token" in v.lower()):
                cookies.update(_parse_cookie_string(v))
            else:
                cookies[k.strip()] = v
    return cookies


def cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def _fetch_session_info(cookies: dict[str, str]) -> tuple[str, str]:
    """Fetch the home page and return (g_ck, user_sys_id).

    window.NOW.user only exposes userID (sys_id) and isImpersonating.
    The caller can look up the sys_id against sys_user to get the display name.
    """
    req = urllib.request.Request(
        f"{INSTANCE}/",
        headers={
            "Cookie": cookie_header(cookies),
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode(errors="replace")
            ck_m = re.search(r'g_ck\s*=\s*["\']([a-f0-9]+)["\']', html)
            g_ck = ck_m.group(1) if ck_m else ""
            user_m = re.search(r'window\.NOW\.user\s*=\s*(\{.*?\});', html, re.DOTALL)
            user_id = ""
            if user_m:
                try:
                    user_id = json.loads(user_m.group(1)).get("userID", "")
                except (json.JSONDecodeError, AttributeError):
                    pass
            return g_ck, user_id
    except urllib.error.HTTPError:
        return "", ""


class SnowClient:
    def __init__(self, cookies: dict[str, str] | None = None, api_key: str | None = None):
        key = api_key or _find_api_key()
        if key:
            self._headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "x-sn-apikey": key,
            }
            self.session_user_id = ""
            self.session_username, self.session_full_name = self._resolve_current_user()
        else:
            self.cookies = cookies or load_cookies()
            g_ck, self.session_user_id = _fetch_session_info(self.cookies)
            if not g_ck:
                raise RuntimeError(
                    "No API key found and could not fetch g_ck CSRF token.\n"
                    "Set SNOW_API_KEY in .env, or re-extract browser cookies (see spec/auth.md)."
                )
            self._headers = {
                "Cookie": cookie_header(self.cookies),
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-UserToken": g_ck,
            }
            self.session_username, self.session_full_name = self._resolve_user(self.session_user_id)

    def _resolve_current_user(self) -> tuple[str, str]:
        """Resolve current user via API call (used with API key auth)."""
        try:
            result = self._request("/api/now/table/sys_user", {
                "sysparm_query": "user_name=javascript:gs.getUserName()",
                "sysparm_limit": "1",
                "sysparm_fields": "user_name,name",
            })
            rows = result if isinstance(result, list) else result.get("result", [])
            if rows:
                r = rows[0]
                uname = r.get("user_name", "")
                uname = uname.get("display_value", "") if isinstance(uname, dict) else uname
                name = r.get("name", "")
                name = name.get("display_value", "") if isinstance(name, dict) else name
                return uname, name
        except RuntimeError:
            pass
        return "", ""

    def _resolve_user(self, sys_id: str) -> tuple[str, str]:
        """Resolve username and display name from a sys_user sys_id (used with cookie auth)."""
        if not sys_id:
            return "", ""
        try:
            r = self.get_record("sys_user", sys_id, fields=["user_name", "name"])
            return (
                r.get("user_name", "") if isinstance(r.get("user_name"), str) else r.get("user_name", {}).get("display_value", ""),
                r.get("name", "") if isinstance(r.get("name"), str) else r.get("name", {}).get("display_value", ""),
            )
        except RuntimeError:
            return "", ""

    def _request(self, path: str, params: dict | None = None) -> dict:
        url = f"{INSTANCE}{path}"
        if params:
            url += "?" + urlencode(params)

        req = urllib.request.Request(url, headers=self._headers)
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            if e.code in (301, 302, 303):
                raise RuntimeError(
                    "Redirected — session cookies have expired. Re-extract from browser."
                ) from e
            raise RuntimeError(f"HTTP {e.code}: {body[:500]}") from e

    def get_table(
        self,
        table: str,
        query: str = "",
        fields: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
        display_value: bool = True,
    ) -> list[dict]:
        """Query a ServiceNow table via the Table API."""
        params: dict = {
            "sysparm_limit": limit,
            "sysparm_offset": offset,
            "sysparm_display_value": "true" if display_value else "false",
        }
        if query:
            params["sysparm_query"] = query
        if fields:
            params["sysparm_fields"] = ",".join(fields)

        result = self._request(f"/api/now/table/{table}", params)
        return result.get("result", [])

    def create_record(self, table: str, fields: dict) -> dict:
        """Create a new record via POST. Returns the created record."""
        url = f"{INSTANCE}/api/now/table/{table}"
        body = json.dumps(fields).encode()
        req = urllib.request.Request(url, data=body, method="POST", headers=self._headers)
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read()).get("result", {})
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            raise RuntimeError(f"HTTP {e.code}: {body[:500]}") from e

    def patch_record(self, table: str, sys_id: str, fields: dict) -> dict:
        """Update fields on a single record via PATCH."""
        url = f"{INSTANCE}/api/now/table/{table}/{sys_id}"
        body = json.dumps(fields).encode()
        req = urllib.request.Request(url, data=body, method="PATCH", headers=self._headers)
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read()).get("result", {})
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            raise RuntimeError(f"HTTP {e.code}: {body[:500]}") from e

    def delete_record(self, table: str, sys_id: str) -> None:
        """Delete a record via DELETE."""
        url = f"{INSTANCE}/api/now/table/{table}/{sys_id}"
        req = urllib.request.Request(url, method="DELETE", headers=self._headers)
        try:
            with urllib.request.urlopen(req) as resp:
                return  # 204 No Content on success
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            raise RuntimeError(f"HTTP {e.code}: {body[:500]}") from e

    def get_record(self, table: str, sys_id: str, fields: list[str] | None = None) -> dict:
        params = {}
        if fields:
            params["sysparm_fields"] = ",".join(fields)
        result = self._request(f"/api/now/table/{table}/{sys_id}", params or None)
        return result.get("result", {})

    def aggregate(
        self,
        table: str,
        query: str = "",
        group_by: str | None = None,
        count: bool = True,
        sum_fields: list[str] | None = None,
    ) -> dict:
        """Use the Stats API for aggregations (counts, sums)."""
        params: dict = {"sysparm_count": str(count).lower()}
        if query:
            params["sysparm_query"] = query
        if group_by:
            params["sysparm_group_by"] = group_by
        if sum_fields:
            params["sysparm_sum_fields"] = ",".join(sum_fields)

        result = self._request(f"/api/now/stats/{table}", params)
        return result.get("result", {})

    def whoami(self) -> dict:
        """Verify auth by fetching the current user's profile."""
        result = self._request("/api/now/table/sys_user", {
            "sysparm_query": "user_name=javascript:gs.getUserName()",
            "sysparm_limit": "1",
            "sysparm_fields": "sys_id,user_name,name,email",
        })
        rows = result if isinstance(result, list) else result.get("result", [])
        return rows[0] if rows else {}


# ---------------------------------------------------------------------------
# Quick-test: python snow_client.py
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    key = _find_api_key()
    auth_method = "API key" if key else "session cookies"
    print(f"Connecting to {INSTANCE} via {auth_method}...")
    try:
        client = SnowClient()
    except (FileNotFoundError, RuntimeError) as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    print(f"  Authenticated as: {client.session_full_name} ({client.session_username})")

    print("\nActive PI sprints (rm_sprint, state=Current)...")
    try:
        sprints = client.get_table(
            "rm_sprint",
            query="state=Current",
            fields=["short_description", "start_date", "end_date"],
            limit=20,
        )
        for s in sprints:
            sd = s.get("short_description", "")
            print(f"  {sd}")
        if not sprints:
            print("  (none found)")
    except RuntimeError as e:
        print(f"  Could not fetch sprints: {e}")

    print("\nDone.")
