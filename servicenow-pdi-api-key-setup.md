# ServiceNow PDI: API Key Authentication Setup

Quick reference for standing up inbound API Key auth on a fresh PDI (Zurich+ release). Three records, then one policy link — none of it is automatable via API, so budget ~5 minutes of manual clicks per fresh instance.

## Prerequisites

- Confirm the **API Key and HMAC Authentication** plugin (`com.glide.tokenbased_auth`) is active: **System Definitions > Plugins**. Usually active by default, but check on fresh PDIs.
- Have a user record ready that the key will represent (create one under **User Administration > Users** if needed, with the `admin` role or whatever scope you require).

## Step 1 — Create the Authentication Profile

**System Web Services > API Access Policies > Inbound Authentication Profile > New**

1. Select **Create API Key authentication profiles**.
2. **Name**: descriptive, e.g. `vm-provisioning-api-key-profile`
3. **Auth Parameter**: click into the field, select **`x-sn-apikey`** with **Type: Auth Header** from the popup.
   - Auth Header (not Query Parameter) is the right choice — keeps the key out of URLs/logs.
4. Submit.

> This record only defines *which header name to look for*. It does not yet contain a token or link to a user.

## Step 2 — Create the API Key

**System Web Services > API Access Policies > REST API Key > New**

1. **Name**: e.g. `vm-provisioning-api-key`
2. **User**: the account this key should authenticate as
3. **Active**: checked
4. Leave **Auth Scope** / **Expiry** blank unless you need to restrict scope or set an expiration
5. Submit — ServiceNow auto-generates the **Token**. Click the lock icon to reveal, then copy it (won't be shown in plaintext again by default).

> No direct link field exists between this record and the Authentication Profile from Step 1 — the two are tied together implicitly by the token value at request time, and explicitly via the Access Policy in Step 3.

## Step 3 — Create the REST API Access Policy (the step that's easy to miss)

**System Web Services > API Access Policies > REST API Access Policies > New**

This step is mandatory — API Key auth is **not** accepted by default like Basic Auth/OAuth are. Without a policy explicitly attaching the profile, requests fail with `"User is not authenticated"` even with a valid token.

1. **Name**: e.g. `table-api-key-policy`
2. **Active**: checked
3. **REST API**: select what this policy governs (e.g. `Table API` for broad coverage, or a specific Scripted REST API for narrower scope)
4. Leave "Apply to all methods / resources / versions / tables" checked for initial testing; narrow later for production use
5. Scroll to **Inbound authentication profiles** related list at the bottom → click **"Insert a new row..."** → search for and select the profile from Step 1 (`vm-provisioning-api-key-profile`)
6. Submit.

## Step 4 — Test

```bash
curl -X GET \
  "https://<instance>.service-now.com/api/now/table/sys_user?sysparm_limit=1" \
  -H "x-sn-apikey: YOUR_TOKEN_HERE" \
  -H "Accept: application/json"
```

Expect a JSON `result` array back. If you get `"User is not authenticated"`, check in this order:
1. Policy → Profile link (Step 3) — most common miss
2. Plugin active (prerequisites)
3. API Key record `Active` checkbox
4. Token copied without truncation/whitespace

## ⚠️ Security considerations (from initial test setup)

The walkthrough above, followed exactly, produces a **fully-privileged, unscoped key** if you're not deliberate about a couple of choices:

- **User type**: if the User field points to a *human* account (e.g. a personal admin login) rather than a dedicated service/integration account, the key is fragile — it breaks or changes behavior if that person's password resets, role changes, or account gets deactivated for unrelated reasons. Prefer a dedicated service account, and check **Web service access only** on it to block interactive login.
- **Role scope**: if that user carries the `admin` role and you leave **Auth Scope** blank on the API Key record, the key can perform *any* Table API operation that admin can — full read/write/delete across all tables, not scoped to what your integration actually needs.
- **Access Policy scope**: leaving "Apply to all tables / methods / resources / versions" checked (the default, useful for initial testing) means the policy itself adds no additional restriction either.

None of this is dangerous for PDI testing, but before this pattern touches anything real:
1. Create a dedicated service account, not a personal/human login, with only the roles the integration actually needs (not blanket `admin`).
2. Set **Auth Scope** on the API Key record if you want to restrict what the key can do independent of the user's own role assignments.
3. Narrow the Access Policy from "all tables" to the specific table(s)/API(s) the integration touches.

## Notes for repeatability across fresh PDIs

- None of steps 1–3 have a documented Table API path for scripted automation — they're UI-only admin actions each time you get a new PDI.
- If scripting the *user* creation (Step 0) via Table API, you can still speed things up — POST to `sys_user` + role assignment is straightforward. The three auth records above are what you'll be redoing by hand each cycle.
- Before going to production use (beyond a PDI), narrow the Access Policy's scope from "all tables" to the specific table/API you actually need — broad scope is fine for testing, not for anything real.
