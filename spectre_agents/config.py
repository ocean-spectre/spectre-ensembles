"""Configuration loader for the SPECTRE agent system.

Priority: environment variables > spectre_agents_config.yaml > defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class GridConfig:
    Nx: int = 768
    Ny: int = 424
    Nr: int = 50
    nPx: int = 8
    nPy: int = 8


@dataclass
class DiscordChannels:
    status: str = "simulation-status"
    decisions: str = "decisions"
    alerts: str = "alerts"
    plots: str = "plots"
    logs: str = "logs"
    knowledge: str = "ask-mitgcm"


@dataclass
class AgentModelConfig:
    model: str = ""
    max_tokens: int = 8192


@dataclass
class AgentsConfig:
    orchestrator: AgentModelConfig = field(
        default_factory=lambda: AgentModelConfig("claude-opus-4-6", 16384)
    )
    workflow_runner: AgentModelConfig = field(
        default_factory=lambda: AgentModelConfig("claude-haiku-4-5", 4096)
    )
    stdout_diagnostics: AgentModelConfig = field(
        default_factory=lambda: AgentModelConfig("claude-sonnet-4-6", 8192)
    )
    model_output_review: AgentModelConfig = field(
        default_factory=lambda: AgentModelConfig("claude-sonnet-4-6", 8192)
    )
    namelist_validator: AgentModelConfig = field(
        default_factory=lambda: AgentModelConfig("claude-sonnet-4-6", 8192)
    )
    forcing_data_qc: AgentModelConfig = field(
        default_factory=lambda: AgentModelConfig("claude-sonnet-4-6", 8192)
    )
    dashboard_manager: AgentModelConfig = field(
        default_factory=lambda: AgentModelConfig("claude-haiku-4-5", 4096)
    )
    notify: AgentModelConfig = field(
        default_factory=lambda: AgentModelConfig("claude-haiku-4-5", 4096)
    )
    web_research: AgentModelConfig = field(
        default_factory=lambda: AgentModelConfig("claude-sonnet-4-6", 8192)
    )


@dataclass
class Config:
    # Paths
    base_dir: Path = Path("/mnt/beegfs/spectre-150-ensembles")
    sim_dir: str = "simulations/glorysv12-curvilinear"
    run_dir_prefix: str = "test-run"

    # Grid
    grid: GridConfig = field(default_factory=GridConfig)

    # Discord
    discord_bot_token: str = ""
    discord_guild_id: int = 0
    discord_channels: DiscordChannels = field(default_factory=DiscordChannels)

    # Anthropic
    anthropic_api_key: str = ""

    # Agents
    agents: AgentsConfig = field(default_factory=AgentsConfig)

    # Monitoring
    poll_interval_seconds: int = 60
    dashboard_port: int = 8050

    @property
    def simulation_dir(self) -> Path:
        return self.base_dir / self.sim_dir

    @property
    def input_dir(self) -> Path:
        return self.simulation_dir / "input"

    @property
    def workflows_dir(self) -> Path:
        return self.simulation_dir / "workflows"


def _apply_agent_config(agents_cfg: AgentsConfig, raw: dict) -> None:
    """Apply raw YAML agent config to the AgentsConfig dataclass."""
    for name, values in raw.items():
        if hasattr(agents_cfg, name) and isinstance(values, dict):
            agent = getattr(agents_cfg, name)
            if "model" in values:
                agent.model = values["model"]
            if "max_tokens" in values:
                agent.max_tokens = values["max_tokens"]


def load_config(config_path: str | Path | None = None) -> Config:
    """Load configuration from YAML file and environment variables."""
    cfg = Config()

    # Load YAML config if it exists
    if config_path is None:
        # Look in the repo root
        candidates = [
            Path("spectre_agents_config.yaml"),
            Path(__file__).parent.parent / "spectre_agents_config.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                config_path = candidate
                break

    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}

        sim = raw.get("simulation", {})
        if "base_dir" in sim:
            cfg.base_dir = Path(sim["base_dir"])
        if "sim_dir" in sim:
            cfg.sim_dir = sim["sim_dir"]
        if "run_dir_prefix" in sim:
            cfg.run_dir_prefix = sim["run_dir_prefix"]

        grid = raw.get("grid", {})
        for attr in ("Nx", "Ny", "Nr", "nPx", "nPy"):
            if attr in grid:
                setattr(cfg.grid, attr, grid[attr])

        discord = raw.get("discord", {})
        channels = discord.get("channels", {})
        for attr in ("status", "decisions", "alerts", "plots", "logs", "knowledge"):
            if attr in channels:
                setattr(cfg.discord_channels, attr, channels[attr])

        if "agents" in raw:
            _apply_agent_config(cfg.agents, raw["agents"])

        monitoring = raw.get("monitoring", {})
        if "poll_interval_seconds" in monitoring:
            cfg.poll_interval_seconds = monitoring["poll_interval_seconds"]
        if "dashboard_port" in monitoring:
            cfg.dashboard_port = monitoring["dashboard_port"]

    # Environment variables override YAML
    cfg.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", cfg.anthropic_api_key)
    cfg.discord_bot_token = os.environ.get("DISCORD_BOT_TOKEN", cfg.discord_bot_token)
    guild_id = os.environ.get("DISCORD_GUILD_ID", "")
    if guild_id:
        cfg.discord_guild_id = int(guild_id)

    if os.environ.get("SPECTRE_BASE_DIR"):
        cfg.base_dir = Path(os.environ["SPECTRE_BASE_DIR"])

    return cfg
