# bonfire

🔥 On-demand game server. Anyone in the Discord group lights the bonfire; it burns out by itself when nobody is playing.

Bonfire starts and stops one dedicated game server VM on Azure from Discord slash commands, warns the channel as the idle timer runs down, and extinguishes the server after a configurable time with no players. Games are adapters; Valheim is the first.

## Documents

| Read | For |
|---|---|
| [docs/prd.md](docs/prd.md) | What Bonfire is for, requirements, metrics, roadmap |
| [docs/architecture.md](docs/architecture.md) | Components, state machine, sequences, glossary |
| [docs/adr/](docs/adr/README.md) | Why each architecture decision was made |
| [docs/contracts/](docs/contracts/adapter-interface.md) | The adapter CLI, configuration, data schema and Discord contracts code is written against |
| [docs/testing.md](docs/testing.md) | Test levels and fakes |
| [tests/features/](tests/features/idle-shutdown.feature) | Gherkin scenarios for every behaviour |
| [docs/prior-art.md](docs/prior-art.md) | Similar tools and the patterns borrowed from them |

## Running the pilot

Prerequisites: Azure CLI, Terraform ≥ 1.9, Docker, an `az login` session with Owner on the subscription.

```bash
infra/bootstrap/create-state-backend.sh                    # once: state storage + infra/envs/pilot/backend.hcl
cp infra/envs/pilot/terraform.tfvars.example infra/envs/pilot/terraform.tfvars   # fill in your values
terraform -chdir=infra/envs/pilot init -backend-config=backend.hcl
terraform -chdir=infra/envs/pilot apply
az vm deallocate -g rg-bonfire-pilot -n vm-bonfire         # stop
az vm start -g rg-bonfire-pilot -n vm-bonfire              # start; the game comes up by itself
```

`terraform destroy` keeps the data disk (`prevent_destroy`); to delete the world as well, remove the `prevent_destroy` line in `infra/modules/vm/main.tf` first. Adapter tests: `pip install -r tests/requirements.txt && pytest -m contract tests/`.

Status: Phase 0 in progress (Terraform and the Valheim adapter).
