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

Status: documentation complete; Phase 0 (Terraform and the Valheim adapter) not started.
