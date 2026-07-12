# ServiceNow EAP Data Model

ServiceNow's **Enterprise Agile Planning (EAP)** module lives at the
Strategic Planning Workspace (`/now/sow/home`). The workspace drives its
UI via GraphQL (`/api/now/graphql`), but the underlying data is queryable
via the standard REST Table API.

## Key Tables

| Table | Label | Notes |
|-------|-------|-------|
| `rm_story` | Story (STRY) | Work items; links to sprint via `sprint` field |
| `rm_sprint` | Sprint / PI iteration | Each team+PI combination is one record |
| `rm_release` | Release | Legacy waterfall releases — NOT used for SAFe PIs |
| `sys_user` | User | Assignees; look up by sys_id or user_name |

## Sprint Naming Convention

Each PI iteration per team is stored as a separate `rm_sprint` record:

```
{Team Name} - {PI}.{Iteration}
```

Examples:
- `My Agile Team - 10. 1`
- `Another Team - 10. 1`
- `Another Team - 10. 2`

Note the **space before the iteration number**: `10. 1`, not `10.1`.

## rm_sprint States

| Value | Label |
|-------|-------|
| Draft | Not started |
| Current | Active sprint |
| Complete | Finished |
| Cancelled | Abandoned |

## rm_story Key Fields

| Field | Notes |
|-------|-------|
| `number` | STRY0001234 |
| `short_description` | Title |
| `state` | 1=Open, 2=In Progress, 3=Complete, 4=Accepted |
| `story_points` | Estimate |
| `assigned_to` | → sys_user (display_value = full name) |
| `sprint` | → rm_sprint (display_value = "{Team} - {PI}.{Iter}") |
| `release` | Empty for EAP stories — use `sprint` instead |
| `scrum_team` | Null for EAP stories — team is encoded in sprint name |
| `closed_at` | Completion datetime |

## Story State Values

Use raw values when writing: `client.patch_record('rm_story', sys_id, {'state': '4'})`

| Raw Value | Label |
|-----------|-------|
| `-5` | Draft |
| `1` | Open |
| `2` | In Progress |
| `3` | Complete |
| `4` | Accepted |

## Query Patterns

### Find sprint sys_id for a team + PI

```
GET /api/now/table/rm_sprint
  ?sysparm_query=short_descriptionLIKEMy Agile Team - 10. 1
  &sysparm_fields=sys_id,short_description,state
  &sysparm_display_value=true
```

### All completed stories for a team PI 10.1

```
GET /api/now/table/rm_story
  ?sysparm_query=sprint.short_descriptionLIKEMy Agile Team - 10. 1^state=3
  &sysparm_fields=number,short_description,story_points,assigned_to,state,closed_at,sprint
  &sysparm_display_value=true
  &sysparm_limit=500
```

### All stories across all PI 16 iterations for one team

```
sysparm_query=sprint.short_descriptionLIKEMy Agile Team - 10.^state=3
```

---

# CMDB Data Model

## Key Tables

| Table | Label | Notes |
|-------|-------|-------|
| `cmdb_ci_computer` | Computer | Base table for all computers; use this for most host lookups |
| `cmdb_ci_win_server` | Windows Server | Subclass of `cmdb_ci_computer`; same records, more specific |
| `cmdb_ci_server` | Server | Another subclass; overlaps with `cmdb_ci_computer` |
| `cmdb_ci` | Configuration Item | Base CI table; use when class is unknown |

All three computer subclass tables return the same Windows Server records — `cmdb_ci_computer` is the safest default.

## Naming Convention

- Names are stored **lowercase** in CMDB (e.g. `coclaimgrap01p`, not `COCLAIMGRAP01P`)
- Exact match queries (`name=hostname`) must use lowercase
- `LIKE` queries are also case-sensitive; use lowercase
- Some CIs are stored with FQDN (e.g. `hostname.corp.example.com`) as separate `DNS Name` class records in `cmdb_ci`

## Key Fields

| Field | Notes |
|-------|-------|
| `name` | Hostname (lowercase, short name) |
| `install_status` | Lifecycle state — see values below |
| `operational_status` | Runtime state — see values below |
| `sys_class_name` | CI class (e.g. `Windows Server`, `Nutanix Virtual Machine Instance`) |
| `ip_address` | Primary IP |
| `serial_number` | Hardware serial |
| `last_discovered` | Last discovery scan timestamp |
| `short_description` | Free-text description |
| `support_group` | Owning support group |
| `owned_by` | → sys_user |
| `managed_by` | → sys_user |

## install_status Values

| Raw Value | Display Value | Notes |
|-----------|---------------|-------|
| `1` | `Installed` | Active, in production |
| `7` | `Retired` | Decommissioned |
| `3` | `In Maintenance` | Undergoing maintenance |
| `2` | `On Order` | Not yet deployed |
| `6` | `Absent` | Missing/not found by discovery |

Use raw values when writing: `client.patch_record('cmdb_ci_computer', sys_id, {'install_status': '7'})`

## operational_status Values

| Raw Value | Display Value | Notes |
|-----------|---------------|-------|
| `1` | `Operational` | Running normally |
| `2` | `Non-Operational` | Down or decommissioned |
| `3` | `Repair In Progress` | Under repair |

## Query Patterns

### Look up a host by name
```
GET /api/now/table/cmdb_ci_computer
  ?sysparm_query=name=coclaimgrap01p
  &sysparm_fields=name,install_status,operational_status,sys_class_name,ip_address,last_discovered
  &sysparm_display_value=true
  &sysparm_limit=1
```

### Check if a host is retired
```python
results = client.get_table(
    'cmdb_ci_computer',
    query=f'name={hostname.lower()}',
    fields=['name', 'install_status', 'operational_status', 'last_discovered'],
    limit=1,
)
if not results:
    # Not in CMDB — cannot confirm retirement
elif results[0]['install_status'] == 'Retired':
    # Confirmed retired in CMDB
```

### Find all retired servers
```
sysparm_query=install_status=7
```
(Note: when `sysparm_display_value=false`, `Retired` = `7`, `Installed` = `1`)

### Find servers not discovered recently (potentially stale)
```
sysparm_query=last_discoveredRELATIVELE@dayofweek@ago@90
```

### Wildcard search by hostname prefix
```
sysparm_query=nameSTARTSWITHcoclaimgrap
```

## Gotchas

- **No CMDB record ≠ Retired**: a missing CI means the host was never added or was hard-deleted, not necessarily decommissioned through proper process
- **Subclass tables overlap**: querying `cmdb_ci_computer`, `cmdb_ci_win_server`, and `cmdb_ci_server` for the same host returns the same record — pick one
- **Case sensitivity**: all name queries must use lowercase hostnames
