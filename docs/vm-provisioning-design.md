# VM Provisioning via ServiceNow Catalog + Terraform + Proxmox

## Goal

Submit a "Deploy a Server" catalog request in ServiceNow → variables flow into a
Terraform apply → VM is provisioned in Proxmox. ServiceNow RITM is updated with
the result.

---

## Architecture Overview

```
[ServiceNow Catalog Item]
        │  user submits request (hostname, cpu, memory, ...)
        ▼
[sc_request / sc_req_item + sc_item_option]
        │  trigger (see Phase 2 options)
        ▼
[Integration Layer]
        │  reads RITM variables → writes terraform.tfvars
        ▼
[Terraform Apply]   ←── Proxmox provider
        │  VM created
        ▼
[RITM state → Closed Complete + VM IP written back]
```

---

## Phase 1 — ServiceNow Catalog Item

### Catalog Item: "Deploy a Server"

Create via **Service Catalog > Catalog Definitions > Maintain Items > New**
(or via the API — see Phase 1 API section below).

**Variables** (stored in `sc_item_option` / `item_option_new`):

| Variable name | Type | Label | Notes |
|---------------|------|-------|-------|
| `hostname` | Single Line Text | Hostname | Validated: lowercase, no spaces |
| `cpu_count` | Integer | CPU Count | Default: 2 |
| `memory_mb` | Integer | Memory (MB) | Default: 2048 |
| `vm_template` | Select Box | Template | Options: ubuntu-2404, debian-12 |
| `description` | Multi Line Text | Purpose / Notes | Optional |

**Workflow:** Catalog Item → auto-approve (PDI) or single-approver flow → RITM state
transitions to `Approved` → integration layer picks it up.

### Key tables

| Table | Purpose |
|-------|---------|
| `sc_request` | The parent request (REQ) |
| `sc_req_item` | The RITM — one per catalog item ordered |
| `sc_item_option_mtom` | Links RITM to its variable values |
| `sc_item_option` | The variable values themselves |
| `item_option_new` | Variable definitions on the catalog item |

### Reading RITM variables via API

```python
from snow_client import SnowClient

c = SnowClient()

def _val(field) -> str:
    if isinstance(field, dict):
        return field.get('value') or field.get('display_value') or ''
    return str(field) if field else ''

def get_ritm_variables(ritm_number: str) -> dict:
    """Return {variable_name: value} for a given RITM number.

    Keyed by the variable's internal Name field (not its label) — set this
    on each catalog item variable so you get 'memory_mb' not 'How many memories?'
    """
    ritms = c.get_table(
        'sc_req_item',
        query=f'number={ritm_number}',
        fields=['sys_id', 'number', 'state', 'cat_item'],
        limit=1,
        display_value=False,
    )
    if not ritms:
        raise ValueError(f'RITM {ritm_number} not found')

    ritm_sys_id = _val(ritms[0].get('sys_id'))

    # Dot-walk through mtom join directly on sc_item_option
    options = c.get_table(
        'sc_item_option',
        query=f'sc_item_option_mtom.request_item={ritm_sys_id}',
        fields=['item_option_new', 'value'],
        limit=50,
    )

    variables = {}
    for opt in options:
        name = opt.get('item_option_new', {})
        name = name.get('display_value', '') if isinstance(name, dict) else name
        variables[name] = opt.get('value', '')

    return variables
```

---

## Phase 2 — Trigger / Integration Layer

Three options, increasing in complexity. **Start with Option A** to prove the
pipeline end-to-end, then upgrade.

### Option A — Local script (manual trigger)

Run `python3 provision.py --ritm RITM0010001` after submitting the catalog request.
Reads variables, generates tfvars, runs `terraform apply`, writes result back.

- No infrastructure needed
- Good for initial development and testing
- Not automated

### Option B — GitHub Actions polling on self-hosted runner (recommended next step)

A scheduled workflow queries ServiceNow for RITMs in `state=Approved` on the
"Deploy a Server" catalog item, then runs the provision pipeline for each.
Runs on a self-hosted runner that has local network access to Proxmox.

```yaml
on:
  schedule:
    - cron: '*/15 * * * *'   # every 15 minutes
  workflow_dispatch:
runs-on: self-hosted
```

- No public endpoint required
- ~15 min latency (acceptable for VM provisioning)
- Terraform state + Proxmox credentials stored as GitHub Actions secrets
- Self-hosted runner handles local Proxmox network access

> **Note — MID Server:** ServiceNow's own on-prem agent (MID Server) is the
> enterprise-correct answer for this kind of outbound integration. Skipping it
> here because useful MID Server capabilities (Orchestration, IntegrationHub
> workflows) require licensing that isn't available on a PDI.

### Option C — ServiceNow outbound REST → webhook (future)

Flow Designer triggers a POST to a public endpoint (GitHub Actions `repository_dispatch`
or a small relay server) the moment a RITM is approved. Near-real-time.

- Requires a publicly accessible endpoint or inbound firewall rule
- Most "production-like" approach
- Worth revisiting if latency matters

---

## Phase 3 — Terraform / Proxmox

### Provider

Use `bpg/proxmox` (maintained, full-featured):

```hcl
terraform {
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "~> 0.77"
    }
  }
}

provider "proxmox" {
  endpoint = var.proxmox_url
  api_token = var.proxmox_api_token
  insecure  = true   # set false if using valid TLS cert
}
```

### Variables (terraform.tfvars generated per request)

```hcl
hostname     = "web01"
cpu_count    = 2
memory_mb    = 4096
vm_template  = "ubuntu-2404"
proxmox_node = "pve"
```

### Open questions — Proxmox

- [ ] Which Proxmox node(s) are available?
- [ ] VM template names/IDs on the host (need to match `vm_template` select options)
- [ ] Network: which bridge, VLAN tag if any?
- [ ] Storage pool name
- [ ] Proxmox API token setup (separate from ServiceNow API key)
- [ ] Where does Terraform run? (local, GitHub Actions, dedicated VM?)
  - If GitHub Actions: does the runner have network access to Proxmox?
  - If local: can skip the GH Actions complexity for now

---

## Phase 4 — tfvars generation + apply script

`provision.py` — the integration glue:

```
1. Accept --ritm RITMXXXXXXX (or discover approved RITMs automatically)
2. Read variables from ServiceNow (Phase 1 helper)
3. Validate: hostname format, cpu/memory within allowed ranges
4. Write terraform.tfvars to the terraform/ directory
5. Run: terraform init (if needed) && terraform apply -auto-approve
6. Capture output (VM IP, etc.)
7. Write result back to RITM (close complete + work notes with IP)
```

### RITM state values

| Value | Label |
|-------|-------|
| `1` | Pending |
| `2` | Open |
| `3` | Work In Progress |
| `6` | Closed Complete |
| `4` | Closed Incomplete |
| `7` | Closed Skipped |

---

## Phase 5 — Write result back to ServiceNow

```python
def close_ritm(client, ritm_sys_id: str, vm_ip: str, success: bool):
    client.patch_record('sc_req_item', ritm_sys_id, {
        'state': '6' if success else '4',
        'work_notes': f'VM provisioned at {vm_ip}' if success else 'Provisioning failed — check logs',
    })
```

---

## Build Order

- [ ] **Phase 1** — Create catalog item + variables in ServiceNow UI, verify RITM is created on submit
- [ ] **Phase 1** — Write + test `get_ritm_variables()` against a real RITM
- [ ] **Phase 3** — Set up Terraform Proxmox config, test a manual apply outside of ServiceNow
- [ ] **Phase 4** — Write `provision.py` (Option A — manual trigger first)
- [ ] **Phase 4** — Test full pipeline: submit catalog request → run script → VM appears in Proxmox
- [ ] **Phase 5** — Add RITM writeback
- [ ] **Phase 2B** — Wrap in GitHub Actions scheduled workflow once Option A is solid
- [ ] **Phase 2C** — Outbound webhook trigger (optional, if latency matters)

---

## Open Questions

- [ ] Proxmox host URL and API token — add to `.env` + GitHub secrets alongside `SNOW_API_KEY`
- [ ] Terraform state backend — local file is fine for POC; revisit if moving to shared/prod
- [ ] Approval flow — auto-approve on PDI for now, add approver step later
- [ ] `provision.py` lives in this repo for POC; move to a dedicated `proxmox-iac` repo when productionizing
- [ ] Proxmox VM template names — need to confirm what's available on the host
