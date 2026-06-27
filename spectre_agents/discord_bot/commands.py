"""Discord slash command definitions for simulation operations.

All commands are registered under a command tree and synced to the guild.
Agent invocations run in a thread pool to keep the bot responsive.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from spectre_agents.discord_bot.embeds import status_embed, validation_embed

if TYPE_CHECKING:
    from spectre_agents.context import AgentContext
    from spectre_agents.config import Config

logger = logging.getLogger(__name__)

# Thread pool for running synchronous agent code
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agent")


def setup_commands(tree: app_commands.CommandTree, ctx: "AgentContext", config: "Config") -> None:
    """Register all slash commands on the command tree."""

    # --- /run group ---
    run_group = app_commands.Group(name="run", description="Simulation run management")

    @run_group.command(name="start", description="Validate config and submit a new simulation run")
    async def run_start(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            result = await _run_agent(ctx, config, "orchestrator", (
                "Validate the namelists, then submit a new simulation run. "
                "Post status updates to Discord as you go."
            ))
            await interaction.followup.send(f"**Run started**\n{result[:1900]}")
        except Exception as e:
            await interaction.followup.send(f"Failed to start run: {e}")

    @run_group.command(name="status", description="Show current simulation status")
    async def run_status(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        sim = ctx.simulation
        embed = status_embed(
            job_id=sim.active_job_id,
            state=sim.status.upper(),
            model_days=sim.model_days,
            cfl=sim.cfl_max,
        )
        await interaction.followup.send(embed=embed)

    @run_group.command(name="stop", description="Cancel the active SLURM job")
    async def run_stop(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            result = await _run_agent(ctx, config, "workflow_runner", (
                f"Cancel SLURM job {ctx.simulation.active_job_id} and stop all monitoring processes."
            ))
            ctx.simulation.status = "stopped"
            ctx.save_state()
            await interaction.followup.send(f"**Run stopped**\n{result[:1900]}")
        except Exception as e:
            await interaction.followup.send(f"Failed to stop run: {e}")

    @run_group.command(name="resubmit", description="Clear run directory and resubmit from pickup")
    async def run_resubmit(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            result = await _run_agent(ctx, config, "orchestrator", (
                "Clear the run directory and resubmit the simulation from the latest pickup file. "
                "Post status to Discord."
            ))
            await interaction.followup.send(f"**Resubmitted**\n{result[:1900]}")
        except Exception as e:
            await interaction.followup.send(f"Failed to resubmit: {e}")

    tree.add_command(run_group)

    # --- /diagnose ---
    @tree.command(name="diagnose", description="Run STDOUT diagnostics on a job")
    @app_commands.describe(job_id="SLURM job ID (optional, defaults to active job)")
    async def diagnose(interaction: discord.Interaction, job_id: int | None = None):
        await interaction.response.defer(thinking=True)
        jid = job_id or ctx.simulation.active_job_id
        try:
            result = await _run_agent(ctx, config, "stdout_diagnostics", (
                f"Diagnose the failure for SLURM job {jid}. "
                f"The run directory is {ctx.simulation.run_dir}."
            ))
            await interaction.followup.send(f"**Diagnosis**\n```\n{result[:1900]}\n```")
        except Exception as e:
            await interaction.followup.send(f"Diagnosis failed: {e}")

    # --- /review ---
    @tree.command(name="review", description="Assess physical plausibility of model output")
    async def review(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            result = await _run_agent(ctx, config, "model_output_review", (
                f"Review the model output in {ctx.simulation.run_dir}. "
                "Assess SST, salinity, velocity, CFL, and trends."
            ))
            await interaction.followup.send(f"**Model Review**\n```\n{result[:1900]}\n```")
        except Exception as e:
            await interaction.followup.send(f"Review failed: {e}")

    # --- /validate ---
    @tree.command(name="validate", description="Run pre-flight namelist validation")
    async def validate(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            result = await _run_agent(ctx, config, "namelist_validator", (
                f"Validate all namelists in {config.input_dir}."
            ))
            await interaction.followup.send(f"**Validation**\n```\n{result[:1900]}\n```")
        except Exception as e:
            await interaction.followup.send(f"Validation failed: {e}")

    # --- /qc group ---
    qc_group = app_commands.Group(name="qc", description="Forcing data quality control")

    @qc_group.command(name="forcing", description="Validate EXF forcing files")
    async def qc_forcing(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            result = await _run_agent(ctx, config, "forcing_data_qc", (
                f"Run QC on all EXF binary files in {config.input_dir}."
            ))
            await interaction.followup.send(f"**Forcing QC**\n```\n{result[:1900]}\n```")
        except Exception as e:
            await interaction.followup.send(f"QC failed: {e}")

    @qc_group.command(name="obc", description="Validate OBC boundary files")
    async def qc_obc(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            result = await _run_agent(ctx, config, "forcing_data_qc", (
                f"Run QC on all OBC binary files in {config.input_dir}."
            ))
            await interaction.followup.send(f"**OBC QC**\n```\n{result[:1900]}\n```")
        except Exception as e:
            await interaction.followup.send(f"QC failed: {e}")

    tree.add_command(qc_group)

    # --- /dashboard group ---
    dash_group = app_commands.Group(name="dashboard", description="Monitoring dashboard management")

    @dash_group.command(name="start", description="Start the monitoring dashboard stack")
    async def dash_start(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            result = await _run_agent(ctx, config, "dashboard_manager", (
                f"Start the full dashboard stack for run directory {ctx.simulation.run_dir}."
            ))
            await interaction.followup.send(f"**Dashboard**\n{result[:1900]}")
        except Exception as e:
            await interaction.followup.send(f"Dashboard start failed: {e}")

    @dash_group.command(name="status", description="Health-check the dashboard stack")
    async def dash_status(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            result = await _run_agent(ctx, config, "dashboard_manager", (
                "Run a health check on all dashboard components."
            ))
            await interaction.followup.send(f"**Dashboard Health**\n```\n{result[:1900]}\n```")
        except Exception as e:
            await interaction.followup.send(f"Health check failed: {e}")

    @dash_group.command(name="restart", description="Restart dashboard components")
    @app_commands.describe(component="Component to restart: dashboard, converter, plotter, or all")
    async def dash_restart(interaction: discord.Interaction, component: str = "all"):
        await interaction.response.defer(thinking=True)
        try:
            result = await _run_agent(ctx, config, "dashboard_manager", (
                f"Restart the {component} component(s) for run directory {ctx.simulation.run_dir}."
            ))
            await interaction.followup.send(f"**Restart**\n{result[:1900]}")
        except Exception as e:
            await interaction.followup.send(f"Restart failed: {e}")

    tree.add_command(dash_group)

    # --- /ensemble group ---
    ensemble_group = app_commands.Group(name="ensemble", description="Bred vector ensemble operations")

    @ensemble_group.command(name="start", description="Begin bred vector ensemble generation")
    async def ensemble_start(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            result = await _run_agent(ctx, config, "orchestrator", (
                "Begin the bred vector ensemble generation process. "
                "Submit the breed_vectors.sh workflow and monitor progress."
            ))
            await interaction.followup.send(f"**Ensemble**\n{result[:1900]}")
        except Exception as e:
            await interaction.followup.send(f"Ensemble start failed: {e}")

    @ensemble_group.command(name="status", description="Show ensemble member progress")
    async def ensemble_status(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        try:
            result = await _run_agent(ctx, config, "orchestrator", (
                "Check the status of all ensemble members and report convergence metrics."
            ))
            await interaction.followup.send(f"**Ensemble Status**\n{result[:1900]}")
        except Exception as e:
            await interaction.followup.send(f"Status check failed: {e}")

    tree.add_command(ensemble_group)

    # --- /config ---
    @tree.command(name="config", description="Show simulation configuration")
    @app_commands.describe(param="Specific parameter to show (optional)")
    async def show_config(interaction: discord.Interaction, param: str | None = None):
        await interaction.response.defer(thinking=True)
        try:
            result = await _run_agent(ctx, config, "workflow_runner", (
                f"Read and display the simulation configuration from etc/config.yaml"
                + (f", focusing on the '{param}' parameter." if param else ".")
            ))
            await interaction.followup.send(f"**Config**\n```yaml\n{result[:1900]}\n```")
        except Exception as e:
            await interaction.followup.send(f"Config read failed: {e}")


async def _run_agent(ctx: "AgentContext", config: "Config", agent_name: str, task: str) -> str:
    """Run a specialist agent in the thread pool and return its text result."""
    from spectre_agents.agents import AGENT_REGISTRY

    agent_cls = AGENT_REGISTRY.get(agent_name)
    if agent_cls is None:
        # Try orchestrator for unknown agent names
        from spectre_agents.agents.orchestrator import SimulationOrchestrator
        agent = SimulationOrchestrator(config)
    else:
        agent = agent_cls(config)

    # Agent.run() is async but involves sync SDK calls — run in executor
    loop = asyncio.get_event_loop()
    result = await agent.run(task)
    return result
