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

Discord setup: create an application and bot in the [Discord developer portal](https://discord.com/developers/applications), invite the bot to the guild with the `applications.commands` scope, create a channel webhook, and put the application ID, public key, bot token and webhook URL in `terraform.tfvars`.

```bash
infra/bootstrap/create-state-backend.sh                    # once: state storage + infra/envs/pilot/backend.hcl
cp infra/envs/pilot/terraform.tfvars.example infra/envs/pilot/terraform.tfvars   # fill in your values
terraform -chdir=infra/envs/pilot init -backend-config=backend.hcl
scripts/build-function.sh                                    # stage the Function before every plan/apply
terraform -chdir=infra/envs/pilot apply
terraform -chdir=infra/envs/pilot output -raw function_url     # paste into the Discord portal as the Interactions Endpoint URL
DISCORD_BOT_TOKEN=$(az keyvault secret show --vault-name "$(terraform -chdir=infra/envs/pilot output -raw key_vault_name)" -n discord-bot-token --query value -o tsv) \
  DISCORD_APPLICATION_ID=... DISCORD_GUILD_ID=... python3 scripts/register-commands.py
```

Day to day: `/bonfire ignite`, `/bonfire check`, `/bonfire extinguish`, `/bonfire cost` in Discord.

Two cost backstops are provisioned: an Azure budget of US$120/month with an alert at 80%, and a nightly auto-deallocate at 04:00 São Paulo time (`shutdown_time` in the vm module).

`terraform destroy` refuses to run while the data disk is under Terraform management (`prevent_destroy`); to tear everything down, run `terraform state rm module.vm.azurerm_managed_disk.data` first, and note that deleting the resource group deletes the world with it. For day-to-day use, cycle the VM with `az vm deallocate` and `az vm start`, which keep the disk and the world. Unit level: `pip install -e ".[test]" && pytest -m unit tests/`. Adapter contract: `pytest -m contract tests/`.

Status: Phase 1 in progress: agent, Function and Discord commands implemented; e2e pending.
