# SAFe / EAP API Access — Roles & Least Privilege Reference

Covers the minimum roles needed for two common API use cases against a ServiceNow instance
running the Strategic Planning Workspace (EAP) with `safe_*` / `sn_apw_advanced.*` role naming.

## SAFe / EAP Role Reference

| Role | Purpose |
|------|---------|
| `sn_apw_advanced.eap_read_only` | EAP read-only — query stories, sprints, PI data |
| `sn_apw_advanced.eap_user` | EAP full user — read + write via workspace UI |
| `safe_scrum_user` | Base SAFe/scrum access |
| `safe_story_creator` | Create stories |
| `safe_story_editor` | Edit stories |
| `scrum_user` | Base scrum module access |
| `scrum_team_member` | Team member level access |
| `scrum_master` | Scrum master functions |
| `scrum_sprint_planner` | Assign stories to sprints |
| `scrum_story_creator` | Create stories (classic naming — overlaps `safe_story_creator`) |
| `scrum_story_editor` | Edit stories (classic naming — overlaps `safe_story_editor`) |
| `rm_scrum_task_admin` | Scrum task administration |

---

## Scenario A: Read-Only (Reporting)

**Goal:** query PI planning data, story points, sprint status — no writes.

**Minimum roles:**
- `sn_apw_advanced.eap_read_only`

**Access Policy scope:**
- Tables: `rm_story`, `rm_sprint`, `sys_user`
- Methods: GET only

**Auth Scope on the API Key:** set to `sn_apw_advanced.eap_read_only` explicitly. Without
this, a key tied to an account that also holds write roles (`safe_story_editor`,
`scrum_sprint_planner`, etc.) will silently inherit those — making the key fully write-capable
despite the intent to be read-only.

---

## Scenario B: Read-Write (Story + Sprint Management)

**Goal:** reporting plus moving stories between sprints, editing fields, creating stories.

**Minimum roles:**
- `safe_story_creator` / `scrum_story_creator` — create new stories
- `safe_story_editor` / `scrum_story_editor` — edit existing stories
- `scrum_sprint_planner` — move stories into/out of sprints

**Access Policy scope:**
- Tables: `rm_story`, `rm_sprint`, `sys_user`
- Methods: GET + POST + PATCH (no DELETE, no PUT needed)

**Auth Scope on the API Key:** restrict to the three roles above. Exclude `rm_scrum_task_admin`,
`scrum_master`, and any EAP admin roles unless the use case explicitly requires them.

---

## ⚠️ Auth Scope and over-privilege

ServiceNow API keys inherit the full role set of their associated user account unless **Auth
Scope** is explicitly set on the API Key record. On a PDI where the account carries `admin`,
this means every key is implicitly admin unless scoped down.

For a PDI this is low risk, but it's worth knowing:
- A read-only key against an admin account is only read-only if Auth Scope is set
- The safer pattern for any shared or long-lived key is a dedicated service account with only
  the roles the key actually needs, rather than relying on Auth Scope to trim a broad account

---

## Quick reference

| Component | Read-only | Read-write |
|-----------|-----------|------------|
| Roles | `eap_read_only` | `safe_story_creator/editor`, `scrum_sprint_planner` |
| Tables | `rm_story`, `rm_sprint`, `sys_user` | same |
| Methods | GET | GET, POST, PATCH |
| Auth Scope | Required — prevents write role bleed | Restrict to story/sprint roles only |
| Key expiry | Set an expiry and rotate | same |
