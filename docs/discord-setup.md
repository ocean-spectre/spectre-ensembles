# SPECTRE Agent System — Complete Setup Guide

This guide covers setting up the autonomous Python agent system with Discord bot integration on the Spectre (Franklin) cluster.

## Prerequisites

- Python 3.11+ on the cluster login/utility node
- `uv` package manager installed
- Access to SLURM commands (`sbatch`, `sacct`, `squeue`)
- BeeGFS mounted at `/mnt/beegfs/`
- An Anthropic API key with access to Claude Opus 4.6, Sonnet 4.6, and Haiku 4.5
- A Discord account with permission to create bots

---

## Step 1: Create a Discord Bot

1. Go to https://discord.com/developers/applications
2. Click **New Application** and name it `SPECTRE Bot`
3. Go to the **Bot** tab:
   - Click **Add Bot** (if not already created)
   - Copy the **Token** — save it securely, you'll need it later
   - Enable **Message Content Intent** (required for reading messages)
   - Enable **Server Members Intent**
4. Go to the **OAuth2 → URL Generator** tab:
   - **Scopes**: select `bot` and `applications.commands`
   - **Bot Permissions**: select:
     - Send Messages
     - Embed Links
     - Attach Files
     - Use Slash Commands
     - Read Message History
     - Create Public Threads
   - Copy the generated URL
5. Open the URL in your browser and add the bot to your Discord server

## Step 2: Set Up Discord Server Channels

Create these channels in your Discord server:

| Channel | Purpose |
|---------|---------|
| `#simulation-status` | Automated status updates, milestones |
| `#decisions` | Interactive decision requests with buttons |
| `#alerts` | Failure alerts and critical warnings |
| `#plots` | Surface field PNGs, convergence plots |
| `#logs` | Verbose agent activity (optional) |
| `#ask-mitgcm` | Knowledge Q&A — ask about MITgcm, ERA5, oceanography, or the codebase |

**Get your Guild (Server) ID:**
- Enable Developer Mode in Discord (Settings → Advanced → Developer Mode)
- Right-click your server name → Copy Server ID

## Step 3: Configure Secrets

Create the secrets file on the cluster:

```bash
sudo mkdir -p /etc/spectre-agents
sudo tee /etc/spectre-agents/env << 'EOF'
ANTHROPIC_API_KEY=sk-ant-your-key-here
DISCORD_BOT_TOKEN=your-bot-token-here
DISCORD_GUILD_ID=your-guild-id-here
EOF
sudo chmod 600 /etc/spectre-agents/env
sudo chown joe:joe /etc/spectre-agents/env
```

## Step 4: Install the Agent System

```bash
cd /mnt/beegfs/spectre-150-ensembles

# Create virtual environment
uv venv .venv

# Install dependencies (includes spectre_agents package)
uv sync

# Verify the package loads
.venv/bin/python -c "from spectre_agents.config import load_config; print('OK')"
```

## Step 5: Test the Bot Locally

Before installing as a service, test interactively:

```bash
cd /mnt/beegfs/spectre-150-ensembles

# Source the secrets
source /etc/spectre-agents/env
export ANTHROPIC_API_KEY DISCORD_BOT_TOKEN DISCORD_GUILD_ID

# Run the agent system
.venv/bin/python -m spectre_agents --config spectre_agents_config.yaml
```

You should see:
```
SPECTRE Agent System starting...
Bot connected as SPECTRE Bot#1234 (ID: ...)
Synced commands to guild ...
```

In Discord, the bot should post "SPECTRE Agent System online" in `#simulation-status`.

Test slash commands:
- `/run status` — should show current (idle) status
- `/validate` — should run namelist validation
- `/dashboard status` — should check dashboard health

Press `Ctrl+C` to stop.

## Step 6: Install as a Systemd Service

```bash
# Copy the service file
sudo cp systemd/spectre-agents.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start the service
sudo systemctl enable spectre-agents
sudo systemctl start spectre-agents

# Check status
sudo systemctl status spectre-agents

# View logs
journalctl -u spectre-agents -f
```

## Step 7: Verify Everything Works

1. In Discord, run `/run status` — bot should respond with a status embed
2. Run `/validate` — should trigger namelist validation and return results
3. Run `/dashboard status` — should report dashboard component health
4. Run `/run start` — should validate, submit a SLURM job, and start monitoring

---

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│           Spectre Cluster Node              │
│                                             │
│  systemd: spectre-agents.service            │
│  ┌───────────────────────────────────────┐  │
│  │  python -m spectre_agents             │  │
│  │                                       │  │
│  │  Discord Bot (asyncio event loop)     │  │
│  │    ├── Slash commands → Agent runner  │  │
│  │    ├── Decision queue ← Orchestrator  │  │
│  │    └── Status embeds → Discord        │  │
│  │                                       │  │
│  │  Agent Runner (ThreadPoolExecutor)    │  │
│  │    ├── Orchestrator (Opus)            │  │
│  │    │   delegates to:                  │  │
│  │    ├── WorkflowRunner (Haiku)         │  │
│  │    ├── StdoutDiagnostics (Sonnet)     │  │
│  │    ├── ModelOutputReview (Sonnet)     │  │
│  │    ├── NamelistValidator (Sonnet)     │  │
│  │    ├── ForcingDataQC (Sonnet)         │  │
│  │    ├── DashboardManager (Haiku)       │  │
│  │    ├── DiscordNotifier (Haiku)        │  │
│  │    └── WebResearch (Sonnet)           │  │
│  └───────────────────────────────────────┘  │
│                                             │
│  SLURM ←→ sbatch/sacct/squeue              │
│  BeeGFS ←→ /mnt/beegfs/spectre-*           │
│  Tailscale ←→ Dashboard proxy               │
└─────────────────────────────────────────────┘
```

## Discord Commands Reference

### Slash commands (simulation ops)

| Command | Description |
|---------|-------------|
| `/run start` | Validate config, submit simulation, start monitoring |
| `/run status` | Show job state, model days, CFL, throughput |
| `/run stop` | Cancel SLURM job, stop monitoring |
| `/run resubmit` | Clear run dir, resubmit from pickup |
| `/diagnose [job_id]` | Run STDOUT failure diagnostics |
| `/review` | Model output physical plausibility check |
| `/validate` | Pre-flight namelist validation |
| `/qc forcing` | EXF forcing data QC |
| `/qc obc` | OBC boundary data QC |
| `/dashboard start` | Start monitoring stack |
| `/dashboard status` | Health-check all components |
| `/dashboard restart [component]` | Restart dashboard/converter/plotter |
| `/ensemble start` | Begin bred vector generation |
| `/ensemble status` | Show ensemble convergence |
| `/config [param]` | Show simulation configuration |

### Knowledge Q&A (`#ask-mitgcm`)

Just type a question in the `#ask-mitgcm` channel — no slash command needed.
The bot answers using Claude with full context about:

- **MITgcm**: parameters, packages, Fortran source, debugging
- **ERA5 / GLORYS**: variable definitions, units, accumulation conventions
- **This simulation**: grid, forcing, namelists, workflows, known gotchas
- **Oceanography**: North Atlantic circulation, air-sea fluxes, ensemble methods
- **HPC / SLURM**: job scheduling, containers, parallel I/O

Long answers automatically create a thread to keep the channel clean.
The bot can also search the web and read files in the repo for up-to-date answers.

## Agent Autonomy Levels

The system operates with **high autonomy**:

**Autonomous actions (no Discord approval needed):**
- Resubmit after SLURM walltime exceeded
- Restart dead dashboard/plotter/converter processes
- Clear run directory before resubmit
- Rebuild container image if not found

**Requires Discord approval (posts interactive buttons):**
- Timestep changes (CFL approaching 0.45)
- Ambiguous failure with multiple fix options
- Physics parameter changes (viscosity, diffusion)
- First-time configuration submission
- Bred vector cycle completion review

## Troubleshooting

### Bot doesn't respond to commands
- Check `journalctl -u spectre-agents -f` for errors
- Verify `DISCORD_BOT_TOKEN` and `DISCORD_GUILD_ID` are correct
- Ensure the bot has the required permissions in your server
- Commands may take up to 1 hour to sync globally; guild sync is instant

### "Claude Agent SDK not found" error
- Ensure `claude-agent-sdk` is installed: `.venv/bin/pip list | grep claude`
- The Claude Code CLI must be installed on the system: `which claude`

### Agent times out
- Check `ANTHROPIC_API_KEY` is valid and has quota
- Increase `max_turns` in `spectre_agents_config.yaml` if agents need more steps
- Check network connectivity from the cluster node

### SLURM commands fail
- Verify the service runs as the correct user (joe)
- Check that SLURM is accessible from the node running the service
- Ensure the working directory exists: `/mnt/beegfs/spectre-150-ensembles`

## Cost Estimates

| Agent | Model | Approx. cost per invocation |
|-------|-------|---------------------------|
| Orchestrator | Opus 4.6 | $0.10 – $0.50 |
| Diagnostics/Review/Validator/QC | Sonnet 4.6 | $0.02 – $0.10 |
| WorkflowRunner/Dashboard/Notify | Haiku 4.5 | $0.005 – $0.02 |

A typical run-diagnose-fix-restart cycle costs approximately $0.50 – $1.00.
