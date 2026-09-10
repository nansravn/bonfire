# Phase 0 — Terraform, Valheim adapter, A2S, backup: design

**Date:** 2026-09-09
**Status:** Approved in brainstorming; awaiting written review
**Inputs:** [prd.md](../../prd.md) section 14 (Phase 0), [architecture.md](../../architecture.md), [contracts/adapter-interface.md](../../contracts/adapter-interface.md), [contracts/configuration.md](../../contracts/configuration.md), [tests/features/adapter-valheim.feature](../../../tests/features/adapter-valheim.feature)

## 1. Purpose and scope

Phase 0 makes the game VM real: Terraform provisions it from an empty subscription, the Valheim adapter runs on it and passes its conformance scenarios, the player count comes from A2S, and saves can be staged for backup. Start and stop are manual until Phase 1.

**In scope:** state-backend bootstrap; Terraform modules `network`, `vm`, `iam`, `secrets`, `backup`; cloud-init; `games/valheim/`; pytest-bdd contract tests; a CI workflow for validation and contract tests; one new ADR; small amendments to existing docs.

**Out of scope (Phase 1 and later):** the Function, the agent, Table Storage, Cosmos, Discord, scheduled Blob upload, `terraform apply` from CI, cost alerts, Packer images.

## 2. Decisions taken in brainstorming

| Topic | Decision |
|---|---|
| Azure auth | `az login` as the owner; Terraform uses the CLI session. No service principal until CI applies (Phase 1, with an OIDC federated credential). |
| Tooling | Azure CLI, Terraform and Docker Engine installed in the owner's WSL2 (Ubuntu 26.04); `sudo` needs a password, so the owner runs the install commands. |
| Backup scope | `adapter.sh backup` plus the Blob container and lifecycle rule. Scheduled upload arrives with the agent. |
| Terraform state | Remote `azurerm` backend in a bootstrap storage account. |
| Test runner | pytest-bdd, chosen one phase early (ADR 0007). |
| IAM de-risk | The VM's self-deallocate role assignment ships now to prove the owner can create role assignments. |
| VM provisioning | Cloud-init from the public repository at a pinned ref. Packer rejected until ignite-to-ready misses its target. |
| VM image | Ubuntu 24.04 LTS Gen2. The game's own requirements (kernel 5+, glibc, crossplay libraries) are satisfied inside the container image. |
| Public ports | Only 2456/udp is opened. The A2S query port 2457 stays loopback-only, per architecture.md; players join by IP. |
| Server visibility | The server runs with `-public 1` so A2S answers on 2457. Phase 0 measures whether `-public 0` also answers locally. |
| CI | Phase 0: validation and contract tests on GitHub-hosted runners. Phase 1: plan on PR, apply on main, via OIDC. |

## 3. Repository layout after Phase 0

```
.github/workflows/ci.yml
infra/
  bootstrap/create-state-backend.sh
  envs/pilot/{main.tf, variables.tf, outputs.tf, backend.hcl, terraform.tfvars.example}
  modules/network/   modules/vm/   modules/iam/   modules/secrets/   modules/backup/
games/valheim/{adapter.json, adapter.sh, docker-compose.yml, README.md}
tests/steps/{conftest.py, test_adapter_valheim.py}
tests/requirements.txt
docs/adr/0007-test-runner-pytest-bdd.md
```

`terraform.tfvars`, `.terraform/`, and `*.tfstate*` are gitignored. `backend.hcl` is committed: it names the state account, which is not a secret.

## 4. Terraform

### 4.1 Naming and location

Resource group `rg-bonfire-pilot` in `brazilsouth`. Resource names: `vnet-bonfire`, `snet-game`, `nsg-bonfire-game`, `pip-bonfire`, `nic-bonfire`, `vm-bonfire`, `disk-bonfire-data`, `kv-bonfire-<suffix>`, `stbonfirebak<suffix>`. `<suffix>` is a six-character lowercase `random_string` kept in state. The state account `stbonfiretf<suffix>` gets its own suffix from the bootstrap script.

### 4.2 Bootstrap

`infra/bootstrap/create-state-backend.sh` runs once with the owner's CLI session: creates `rg-bonfire-tfstate`, a Standard_LRS storage account with a random suffix, a `tfstate` container, and writes `infra/envs/pilot/backend.hcl` with `resource_group_name`, `storage_account_name`, `container_name = "tfstate"`, `key = "pilot.tfstate"`. Idempotent: if `backend.hcl` exists it verifies the account and exits.

### 4.3 Root module `infra/envs/pilot`

Provider `azurerm` (4.x) with `subscription_id` from a variable; backend `azurerm` initialised with `terraform init -backend-config=backend.hcl`. Calls the five modules and wires outputs between them.

Variables:

| Variable | Type | Default | Notes |
|---|---|---|---|
| `subscription_id` | string | none | |
| `location` | string | `brazilsouth` | |
| `admin_ssh_public_key` | string | none | contents of the owner's `.pub` |
| `admin_cidr` | string | none | the owner's public IP in CIDR, for SSH |
| `game` | string | `valheim` | selects `games/<game>/adapter.json` |
| `game_env` | map(string) | `{}` | non-secret adapter environment, written to `/etc/bonfire/<game>.env` |
| `game_password` | string, sensitive | none | stored in Key Vault as `<game>-server-password` |
| `bonfire_git_ref` | string | `main` | ref cloned by cloud-init |
| `vm_size` | string | `Standard_D4as_v5` | |
| `data_disk_gb` | number | 64 | |

For Valheim, `game_env` carries `SERVER_NAME`, `WORLD_NAME`, `SERVER_PUBLIC = "true"`, and `SERVER_ARGS = "-crossplay"` when crossplay is wanted.

Outputs: `public_address` (`<ip>:<first port in adapter.json>`), `vm_id`, `vm_name`, `resource_group`, `key_vault_name`, `backup_storage_account`.

### 4.4 Modules

- **network**: VNet `10.20.0.0/24`, subnet `10.20.0.0/26`, static Standard public IP, NSG with one inbound allow rule per entry in `jsondecode(file("${path.root}/../../../games/${var.game}/adapter.json")).ports` from any source, one allow rule for TCP 22 from `admin_cidr`, default deny otherwise.
- **vm**: `azurerm_linux_virtual_machine` Standard_D4as_v5, image `Canonical / ubuntu-24_04-lts / server` (Gen2), admin user `bonfire` with SSH key only, Premium_LRS 30 GB OS disk, a separate `azurerm_managed_disk` (Premium_LRS, `data_disk_gb`) attached at LUN 0 with `lifecycle { prevent_destroy = true }`, system-assigned identity, `custom_data` from a `templatefile` of `cloud-init.yaml.tftpl`.
- **iam**: custom role `Bonfire VM Self-Deallocate` (`Microsoft.Compute/virtualMachines/deallocate/action`, `.../read`, `.../instanceView/read`) assignable only to the VM, assigned to the VM identity. `Key Vault Secrets User` on the vault and `Storage Blob Data Contributor` on the backup container, both to the VM identity.
- **secrets**: Key Vault, RBAC authorization, soft delete on, purge protection off (so `destroy` works during the pilot); `Key Vault Secrets Officer` to the deploying principal; secret `<game>-server-password`.
- **backup**: Standard_LRS storage account, container `backups`, management policy deleting blobs older than 7 days.

### 4.5 Cloud-init

Rendered from a template with the game name, Key Vault name, git ref, `game_env`, public address, and the values from `adapter.json`. It:

1. Installs Docker Engine and Compose plugin from Docker's apt repository, plus `git` and `python3-venv`.
2. Formats the LUN 0 disk with ext4 only if it has no filesystem, mounts it at `/data` via fstab by UUID, creates `/data/<game>` and `/data/backup-staging/<game>`.
3. Clones the repository at `bonfire_git_ref` into `/opt/bonfire`.
4. Creates `/opt/bonfire/venv` and installs `python-a2s`.
5. Writes `/etc/bonfire/bonfire.env` (mode 0600): `BONFIRE_GAME`, `BONFIRE_ADAPTER_DIR`, `BONFIRE_DATA_DIR`, `BONFIRE_BACKUP_DIR`, `BONFIRE_STOP_GRACE_SECONDS` (from `adapter.json`), `BONFIRE_PUBLIC_ADDRESS`.
6. Writes `/etc/bonfire/<game>.env` (mode 0600) from `game_env` plus the password fetched from Key Vault: an instance-metadata token for `https://vault.azure.net`, then `GET https://<kv>.vault.azure.net/secrets/<game>-server-password?api-version=7.4`, parsed with `python3`. The password is written as `SERVER_PASS`.
7. Installs and enables `bonfire-game.service`: a oneshot unit with `RemainAfterExit=yes`, `After=docker.service`, `ExecStart=adapter.sh start`, `ExecStop=adapter.sh stop`, `TimeoutStopSec` = grace + 60. Every boot starts the game; every shutdown, including `az vm deallocate`, stops it cleanly.
8. Runs `adapter.sh install` once, then starts the service.

### 4.6 Operations in Phase 0

`az vm start -g rg-bonfire-pilot -n vm-bonfire` and `az vm deallocate ...`. Every test session ends deallocated. `prevent_destroy` on the data disk makes `terraform destroy` refuse until the disk is removed from state; deleting the resource group deletes the disk regardless. Day-to-day cycling is deallocate and start. Moving the disk to its own resource group is a Phase 1 consideration.

## 5. Valheim adapter

### 5.1 `adapter.json`

```json
{ "ports": [{ "port": 2456, "proto": "udp" }], "stop_grace_seconds": 60, "ready_timeout_minutes": 10 }
```

### 5.2 `docker-compose.yml`

Service `valheim`, image `lloesche/valheim-server` pinned to a tag, `restart: on-failure:3`, `network_mode: host` (UDP 2456 public, 2457 loopback-reachable, no NAT overhead), `env_file: /etc/bonfire/valheim.env`, volume `${BONFIRE_DATA_DIR}:/config`, `stop_grace_period: ${BONFIRE_STOP_GRACE_SECONDS}s`. Image features that the adapter owns are disabled: `BACKUPS=false`, `UPDATE_CRON=""` (updates happen through `install`).

### 5.3 `adapter.sh`

Bash, `set -euo pipefail`, `cd "$BONFIRE_ADAPTER_DIR"`, all diagnostics to stderr.

| Subcommand | Implementation |
|---|---|
| `install` | `docker compose pull`; exit 1 on failure. |
| `start` | `docker compose up -d`; exit 0 when the container is running. |
| `stop` | `docker compose stop --timeout "$BONFIRE_STOP_GRACE_SECONDS"` then `docker compose down`; SIGTERM lets the server save. |
| `is_ready` | A2S `info` on `127.0.0.1:2457` with a 3 s timeout via the venv; 0 on answer, 1 on timeout, 2 on other error. |
| `player_count` | A2S `info().player_count`; on failure, parse `docker compose logs --since 24h` counting `Got connection SteamID` minus `Closing socket`; print `unknown` if both fail. Always exit 0 after printing. |
| `health` | `docker inspect` state: `running` with unchanged `RestartCount` → `ok`; `restarting`, or `running` with a higher `RestartCount` than the value cached in `/run/bonfire/valheim.restarts` → `degraded`; `exited` or no container → `crashed`. |
| `backup` | Copy `<WORLD_NAME>.db` and `<WORLD_NAME>.fwl` from `$BONFIRE_DATA_DIR/worlds_local` into `$BONFIRE_BACKUP_DIR/<timestamp>/`; exit 1 if either file is missing. |

### 5.4 README

Image, how player count is obtained, the `-public` note, crossplay flag, where worlds live, how to restore a backup.

## 6. Tests

### 6.1 Contract (local Docker or CI)

`tests/steps/test_adapter_valheim.py` binds `tests/features/adapter-valheim.feature` with pytest-bdd and implements the 13 `@contract` scenarios; `@e2e` scenarios are skipped by marker. `conftest.py` provides a fixture that sets the six `BONFIRE_*` variables against temporary directories and writes a throwaway `/etc/bonfire`-equivalent env file (a test password). Run with `pytest -m contract tests/`. The first run pulls the image and the game (about 1 GB).

### 6.2 End-to-end (pilot VM, manual)

After `apply`, the owner executes the three `@e2e` scenarios and one probe, recording results in section 10:

1. Start to ready within 3 minutes after a warm boot (image already present).
2. `player_count` reflects a real connection and disconnection.
3. A2S answers with crossplay enabled.
4. Probe: with `SERVER_PUBLIC=false`, does A2S still answer on loopback?

### 6.3 ADR 0007

Test runner pytest-bdd, tests in Python 3.12+, tag selection by pytest marker. Alternatives: behave (no pytest ecosystem), cucumber-js (second language), bash conformance script (throwaway).

## 7. CI

`.github/workflows/ci.yml`, two jobs on `ubuntu-latest`:

- **validate** (every push and PR): `python3 scripts/check_docs.py`; `terraform fmt -check -recursive`; `terraform init -backend=false` and `terraform validate` in `infra/envs/pilot`; `shellcheck games/*/adapter.sh infra/bootstrap/*.sh`; `python3 -m py_compile` over `tests/` and `scripts/`.
- **adapter-contract** (when `games/**`, `tests/**` or the workflow change): install `tests/requirements.txt`, `pytest -m contract tests/`.

No Azure credentials in CI during Phase 0.

## 8. Amendments to existing documents

- **ADR 0006**: add `bootstrap/` and `modules/backup/` to the tree, with one sentence each.
- **ADR 0006**: correct the `adapter.json` path to `${path.root}/../../../games/${var.game}/adapter.json` (the root module is `infra/envs/pilot`, three levels below the repository root).
- **ADR 0007**: new.
- **adapter-interface.md**: the `adapter.json` example lists only 2456/udp, with a sentence that query ports stay loopback-only.
- **prd.md** 7.6 Valheim bullet: "Ports: 2456/udp public; 2457 loopback only."
- **testing.md** Runner section: pytest-bdd, link ADR 0007.
- **architecture.md** repository layout: add `.github/`, `tests/steps/`, `infra/bootstrap/`.
- **README.md** status line and a "Running the pilot" section: bootstrap, apply, start, stop, destroy.

## 9. Inputs from the owner, in order

1. Install Azure CLI, Terraform and Docker Engine in WSL2 (commands supplied by the plan; `sudo` required).
2. `az login` and `az account set --subscription <id>`; confirm the account holds Owner or User Access Administrator on the subscription or on `rg-bonfire-pilot`.
3. `ssh-keygen -t ed25519 -f ~/.ssh/bonfire` (no key exists yet).
4. Values for `terraform.tfvars`: subscription ID, public key contents, `admin_cidr`, Valheim server name, world name, password (at least 5 characters), crossplay yes or no.
5. Acknowledge cost: about US$0.28 per hour while running, about US$18 per month while stopped.

## 10. Acceptance

- `terraform apply` from an empty resource group succeeds; a second `apply` is a no-op.
- `pytest -m contract tests/` passes on the owner's machine and in CI.
- The three `@e2e` scenarios pass on the VM; the `-public 0` probe result is recorded here.
- `az vm deallocate` leaves the world files intact and `az vm start` brings the game back to ready without cloud-init running again.
- Replacing the VM (for example by changing `game_env`, which changes cloud-init) reuses the data disk and the world; `terraform destroy` refuses while the disk is managed.
- `python3 scripts/check_docs.py` prints `OK`; every amendment in section 8 is applied.

## 11. Phase 0 results

Appended after execution: e2e outcomes, boot timings, and the `-public 0` probe result.

### Results so far

- 2026-09-10: the 13 `@contract` scenarios passed on a GitHub-hosted runner in 4 min 31 s (workflow `adapter-contract`, run 34422931559 on commit b9c9389). The only warnings were pytest-bdd's own deprecation notices under pytest 9.
- End-to-end scenarios, boot timings and the `-public 0` probe: pending Task O2 and O3.

### Amendments during execution

- Worlds: the current server writes a per-world directory `config/worlds_local/<WORLD_NAME>/` (`_main.N.db2`, `.fwl2`, `.ok`, `.chunks`, chunk files), not a flat `.db`/`.fwl` pair. `adapter.sh backup` copies the directory (legacy pair still supported); the tests treat every file under it as a world file. Section 5.3's description is superseded.
- Data layout: `$BONFIRE_DATA_DIR/config` is the container's `/config` and `$BONFIRE_DATA_DIR/server` is `/opt/valheim`, so the 2.1 GB game download survives `compose down` (plan decision P1).
- Crash simulation: Docker ignores its restart policy after an API-level `docker kill`, so scenario 9 switches the policy to `always`, stops the container's init from inside, and restores `on-failure:3`. Inside the image, supervisord restarts a crashed game process without the container exiting.
- Image pinned to `lloesche/valheim-server@sha256:bbda47cbbc9fd7b0385803ba0a70ba2084df4cb87ec6170a145aec5df06be07e` on 2026-09-09; tests read the reference from the compose file.
- The full contract suite could not complete on the owner's WSL2 host (SteamCMD download stalls); the GitHub-hosted `adapter-contract` workflow is the gate.
- `/data` is mounted by filesystem label rather than UUID.
