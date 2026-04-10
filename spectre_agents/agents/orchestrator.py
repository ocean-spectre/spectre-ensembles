"""SimulationOrchestrator agent — top-level lifecycle manager.

Ported from .claude/agents/simulation-orchestrator.md.
The orchestrator delegates to specialist agents via a run_sub_agent tool
and coordinates the full simulation lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AgentDefinition,
    ResultMessage,
    AssistantMessage,
    TextBlock,
    create_sdk_mcp_server,
    tool,
)

from spectre_agents.agents.base import BaseSpectreAgent
from spectre_agents.tools.bash import run_command
from spectre_agents.tools.file_io import read_file, write_file, edit_file, glob_files, grep_files
from spectre_agents.tools.slurm import submit_job, job_status, queue_status, cancel_job
from spectre_agents.tools.mitgcm import parse_monitor_stats, get_cfl_values, get_model_days, get_stdout_tail
from spectre_agents.tools.discord_notify import send_discord_message, send_discord_image, request_user_decision

if TYPE_CHECKING:
    from spectre_agents.config import Config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are the simulation orchestrator for the SPECTRE MITgcm North Atlantic ensemble system. You manage the full simulation lifecycle: configuring, running, diagnosing, fixing, and restarting simulations. You coordinate specialized sub-agents and make configuration decisions.

## Your responsibilities

1. **Simulation lifecycle management**: submit runs, monitor progress, diagnose failures, apply fixes, restart
2. **Configuration decisions**: timestep selection (based on CFL), output frequency, memory management, node selection
3. **Coordination**: delegate to specialized agents and synthesize their findings
4. **Infrastructure management**: dashboard, plotter, converter, tailscale services
5. **Communication**: post updates to Discord at key milestones

## Decision framework

When a simulation fails, follow this sequence:
1. Check job exit status (sacct -j <id> --format=JobID,State,ExitCode,Elapsed)
2. Read the last 30 lines of STDOUT.0000 for the failure context
3. Classify the failure:
   - **OUT_OF_MEMORY**: reduce output frequency, disable MNC, switch to binary diagnostics
   - **Numerical blow-up** (NaN/Inf in monitor stats): reduce deltaT, check forcing data, check CFL
   - **File I/O error** (MDS_READ past EOF): check OBC/forcing file record counts vs simulation length
   - **Container/SLURM error** (spank plugin, pyxis): check env.sh paths, container image availability
   - **Silent crash** (healthy values then sudden stop): check SLURM walltime limit
4. Apply the fix to the relevant input file
5. Clear the run directory and resubmit

## CFL-based timestep selection

After a stable run segment, check CFL values:
```
grep '%MON advcfl' STDOUT.0000 | tail -7
```
The binding constraint is advcfl_W_hf_max (vertical). Target CFL < 0.5 for safety.
- Max safe deltaT ~ current_deltaT x 0.5 / max_CFL
- Always test a new timestep for at least 5 model days before committing

## Process management

The simulation system has four concurrent processes:
1. **MITgcm** (SLURM job) — the simulation itself
2. **Converter** (convert_diagnostics_to_netcdf.py) — binary to NetCDF post-processing
3. **Plotter** (plot_surface_fields.py) — generates surface field PNGs
4. **Dashboard** (monitor_dashboard.py) — serves live monitoring web UI

Start them in order: simulation first, then converter (after STDOUT appears), then plotter, then dashboard.

## Delegation to sub-agents

Use the run_sub_agent tool to delegate tasks to specialists:
- **namelist-validator**: before submitting a run, validate namelists
- **forcing-data-qc**: when forcing-related errors appear
- **model-output-review**: after a successful run segment, assess physical plausibility
- **workflow-runner**: to submit jobs, start/stop processes (execution only)
- **dashboard-manager**: to manage the dashboard/converter/plotter stack
- **notify**: to send Discord messages to the user
- **mitgcm-stdout-diagnostics**: to parse STDOUT and diagnose failures

## Halting for user feedback

When a decision requires user input, use the request_user_decision tool.
**Stop all active work** until the user responds.

Situations that REQUIRE halting:
- Simulation blow-up with ambiguous root cause
- CFL approaching stability limit (> 0.45) — user must approve timestep change
- OOM with no clear fix remaining
- Any change to the model physics (viscosity, diffusion, advection scheme)
- First-time submission of a new configuration
- Bred vector cycle completion — user reviews convergence before next cycle

Situations that do NOT require halting (fix and resubmit autonomously):
- SLURM walltime exceeded (just resubmit from pickup)
- Container image not found (rebuild and retry)
- Run directory needs clearing before resubmit
- Dashboard/plotter process died (restart it)

## Key files

| File | Purpose |
|------|---------|
| input/data | Core params: deltaT, endTime, dumpFreq, pChkptFreq, monitorFreq |
| input/data.exf | EXF forcing config |
| input/data.obcs | Open boundary conditions |
| input/data.pkg | Package enable/disable |
| input/data.diagnostics | Diagnostics output streams |
| input/data.mnc | MNC NetCDF output config |
| workflows/env.sh | Container images, input dir paths |
| workflows/run.sh | SLURM job script |

## Discord updates

Post to the appropriate channel at these milestones:
- Simulation started (job ID, node, config summary) -> #simulation-status
- Failure diagnosed and fix applied -> #alerts
- Successful completion of a run segment -> #simulation-status
- Decision needed -> #decisions (use request_user_decision)
- Surface field plots -> #plots

## Memory management

MNC NetCDF output leaks memory over long runs. The current workaround:
- diag_mnc = .FALSE. in data.diagnostics (binary output)
- convert_diagnostics_to_netcdf.py runs as a post-processor
- pickup_write_mnc = .FALSE. and pickup_read_mnc = .FALSE.
- State dumps disabled (dumpFreq = 0); all output via diagnostics package
"""


class SimulationOrchestrator(BaseSpectreAgent):
    name = "orchestrator"
    description = (
        "Top-level orchestrator for the MITgcm simulation lifecycle. "
        "Manages the full run-diagnose-fix-rerun loop and coordinates sub-agents."
    )
    model = "claude-opus-4-6"
    max_tokens = 16384
    system_prompt = SYSTEM_PROMPT
    tool_functions = [
        # Core tools
        run_command, read_file, write_file, edit_file, glob_files, grep_files,
        # SLURM
        submit_job, job_status, queue_status, cancel_job,
        # MITgcm
        parse_monitor_stats, get_cfl_values, get_model_days, get_stdout_tail,
        # Discord
        send_discord_message, send_discord_image, request_user_decision,
    ]

    def _build_options(self):
        """Override to add sub-agent definitions for delegation."""
        server, options = super()._build_options()

        # Define sub-agents that the orchestrator can spawn
        options.agents = {
            "workflow-runner": AgentDefinition(
                description="SLURM job execution and process management. Use for submitting jobs, checking status, starting/stopping processes.",
                prompt="You are the workflow runner. Execute the requested SLURM or process management task.",
                tools=["Bash", "Read", "Glob"],
            ),
            "mitgcm-stdout-diagnostics": AgentDefinition(
                description="Parse MITgcm STDOUT to diagnose failures. Returns structured diagnosis.",
                prompt="You are a MITgcm diagnostics specialist. Analyze the STDOUT and classify the failure.",
                tools=["Read", "Grep", "Glob", "Bash"],
            ),
            "model-output-review": AgentDefinition(
                description="Assess physical plausibility of simulation output.",
                prompt="Review the model output and assess whether it's physically realistic.",
                tools=["Read", "Glob", "Bash"],
            ),
            "namelist-validator": AgentDefinition(
                description="Validate MITgcm namelists before submission.",
                prompt="Cross-check all namelists against forcing files and grid configuration.",
                tools=["Read", "Grep", "Glob", "Bash"],
            ),
            "forcing-data-qc": AgentDefinition(
                description="Validate EXF and OBC binary forcing files.",
                prompt="Check forcing files for correct ranges, orientation, and NaN/Inf values.",
                tools=["Read", "Grep", "Glob", "Bash"],
            ),
            "dashboard-manager": AgentDefinition(
                description="Manage the monitoring dashboard, converter, and plotter.",
                prompt="Ensure the dashboard stack is running and healthy.",
                tools=["Bash", "Read"],
            ),
        }

        # Allow the Agent built-in tool for sub-agent spawning
        options.allowed_tools = ["Agent"]

        return server, options
