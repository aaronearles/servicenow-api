# ServiceNow Authentication

## Instance
- URL: https://dev432501.service-now.com
- Auth method: API key (preferred) or session cookies

## API Key Approach (Phase 1 — preferred for PDI)

For a PDI, API key auth is the simplest path — no browser session management.
See `servicenow-pdi-api-key-setup.md` for the full setup walkthrough (~5 min, UI-only).

Once you have a key, copy `.env.example` to `.env` and set `SNOW_API_KEY=<key>`.
`SnowClient` picks it up automatically and sends it as `x-sn-apikey` on every request.

## Session Cookie Approach (Phase 2 — fallback)

ServiceNow maintains session state via cookies after login. The REST API
accepts the same session cookies the browser uses, so we can borrow them.

### Cookies to capture

Open DevTools (F12) → Network tab → click any XHR/Fetch request to
dev432501.service-now.com → copy the **Cookie** request header. The key cookies:

| Cookie | Purpose |
|--------|---------|
| `JSESSIONID` | Primary session token |
| `glide_session_store` | Session state |
| `glide_user_route` | Server affinity |
| `CookieConsentPolicy` | (harmless, include anyway) |

### Cookie-Monster (recommended for cookie auth)

Install from `gh_aaronearles/cookie-monster` and run `agent/install.ps1` once.
After logging in, click **Send to Agent** — cookies land at
`%USERPROFILE%\.session-cookies\dev432501.service-now.com.env` and are picked up automatically.

### Manual extraction

1. Open Chrome/Edge and navigate to https://dev432501.service-now.com
2. Log in with your PDI credentials
3. Press **F12** → **Network** tab → check **Preserve log**
4. Refresh the page or click around
5. Find any request to `dev432501.service-now.com` in the list
6. Right-click → **Copy** → **Copy as cURL (bash)**
7. Paste into a text file — the `-H 'Cookie: ...'` portion is what you need
8. Save to `~/.snow_cookies`

### Cookie file format (`~/.snow_cookies`)

```ini
JSESSIONID=abc123...
glide_session_store=def456...
glide_user_route=ghi789...
```

### Lifespan

Session cookies typically last 8 hours or until logout. Re-extract when you
get 401/302 redirects back to the login page.

## OAuth2 Bearer Token Approach (Phase 3, future)

Requires creating an OAuth2 Application Record in the instance:
- Application: `snow-api-client`
- Grant type: Authorization Code + PKCE (interactive) or Client Credentials (service)
- Redirect URI: `http://localhost:9999/callback`

Once configured, the client can exchange tokens without cookie management.

## Playwright Automation Approach (Phase 4, CI/CD)

Automates the full browser login flow headlessly:
1. Launch headless Chromium
2. Navigate to ServiceNow and complete login
3. Harvest post-auth cookies from browser context
4. Serialize to cookie jar for requests library

See `auth_playwright.py` (future).
