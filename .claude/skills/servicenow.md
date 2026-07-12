---
name: servicenow
description: Patterns, working queries, and gotchas for the dev432501 PDI. Use whenever writing or debugging ServiceNow API calls, managing catalog items, plugins, or sprint/story data.
---

# ServiceNow API — Patterns & Gotchas (dev432501 PDI)

## Instance & Auth

- Instance: `https://dev432501.service-now.com`
- **API key is preferred** — set `SNOW_API_KEY` in `.env`. Cookie auth is fallback.
- `SnowClient()` auto-resolves auth. Methods: `get_table`, `get_record`, `create_record`, `patch_record`, `aggregate`.
- **Plugin API (`/api/now/v1/plugins/`)** returns 401 with API key — it's an internal system API not exposed through the Access Policy framework. Use the UI to install plugins.

---

## Confirmed Working Tables

| Table | Purpose | Notes |
|-------|---------|-------|
| `rm_story` | Stories | Requires `com.snc.sdlc.scrum_program` plugin |
| `rm_sprint` | Sprints / PI iterations | Same plugin requirement |
| `rm_release` | Releases | Available after plugin install |
| `rm_epic` | Epics | Available after plugin install |
| `sc_req_item` | RITMs | Core platform — always available |
| `sc_request` | REQ parent | Core platform |
| `sc_item_option` | Catalog variable values | Query via dot-walk (see below) |
| `sc_item_option_mtom` | RITM ↔ variable join | Use for sys_id lookups |
| `item_option_new` | Catalog item variable definitions | CRUD works fine |
| `question_choice` | Select box choices for catalog variables | CRUD works fine |
| `sys_db_object` | Table schema — find table names | Useful when table name is unknown |
| `sys_user` | Users | Always available |
| `sn_apw_advanced_agile_team` | Agile Teams (EAP) | Requires `sn_apw_advanced` plugin |
| `scrum_pp_team` | Scrum Program Teams | Requires `com.snc.sdlc.scrum_program` |

### Tables that do NOT exist on this PDI
- `rm_scrum_team` — wrong name, use `scrum_pp_team`
- `rm_group` — wrong name
- `v_plugin` — times out consistently, do not query

---

## PDI Plugin Setup

Install order matters — `sn_apw_advanced` first (pulls in Agile Development 2.0 as dependency),
then `com.snc.sdlc.scrum_program` separately.

| Plugin ID | Name | Notes |
|-----------|------|-------|
| `sn_apw_advanced` | Strategic Planning Workspace | Install first |
| `com.snc.sdlc.scrum_program` | Scrum Programs | For-fee warning — install anyway on PDI |

See `servicenow-pdi-plugin-setup.md` for full walkthrough.

---

## Catalog Item Variables

### Variable types (item_option_new.type)
| Value | Type |
|-------|------|
| `1` | Single Line Text |
| `3` | Multiple Choice (select box) |
| `5` | Integer |

Select box choices stored in `question_choice` table, linked via `question` field.

### Creating variables via API
```python
c.create_record('item_option_new', {
    'cat_item': '<cat_item_sys_id>',
    'name': 'hostname',           # internal key — use in tfvars, not question_text
    'question_text': 'Hostname',  # display label
    'type': '1',
    'mandatory': 'true',
    'order': '100',
    'active': 'true',
    'default_value': '',
})
```

### Creating select choices
```python
c.create_record('question_choice', {
    'question': '<item_option_new_sys_id>',
    'text': 'Ubuntu 24.04',
    'value': 'ubuntu-2404',
    'order': '100',
})
```

### Reading RITM variables — use dot-walk, not two-hop
```python
# WORKS — dot-walk is simpler and faster
options = c.get_table(
    'sc_item_option',
    query=f'sc_item_option_mtom.request_item={ritm_sys_id}',
    fields=['item_option_new', 'value'],
    limit=50,
)
# options[n]['item_option_new']['display_value'] = variable name
# options[n]['value'] = submitted value

# DOES NOT WORK — two-hop via sc_item_option_mtom returns empty
# (the request_item field on mtom doesn't filter as expected)
```

---

## Deploy a VM Catalog Item

- **sys_id**: `515eb86d73cac3102687fb204ab8b7d4`
- **Variables** (in order):

| order | name | type | default |
|-------|------|------|---------|
| 100 | `hostname` | Single Line Text | — |
| 200 | `cpu_count` | Integer | 2 |
| 300 | `memory_mb` | Integer | 2048 |
| 400 | `vm_template` | Multiple Choice | ubuntu-2404 |

- `vm_template` choices: `ubuntu-2404` (Ubuntu 24.04), `debian-12` (Debian 12)

---

## RITM State Values (sc_req_item)

| Value | Label |
|-------|-------|
| `1` | Pending |
| `2` | Open |
| `3` | Work In Progress |
| `6` | Closed Complete |
| `4` | Closed Incomplete |
| `7` | Closed Skipped |

---

## Sprint Naming Convention (SAFe/EAP)

`{Team Name} - {PI}.{Iteration}` — note the **space before the iteration number**:
`My Team - 1. 1` not `My Team - 1.1`. The pi_report.py queries depend on this.

Demo data sprints use a different convention (`HRDev Sprint 17`, `Mobile Team 1`) —
they don't follow the SAFe PI format and won't work with pi_report.py as-is.

---

## Finding Unknown Table Names

When a table name is unknown, query `sys_db_object` with a targeted filter:
```python
c.get_table('sys_db_object',
    query='nameLIKEscrum^ORlabelLIKEagile',
    fields=['name', 'label'], limit=100)
```
Avoid broad OR queries on `v_plugin` — it times out every time.
