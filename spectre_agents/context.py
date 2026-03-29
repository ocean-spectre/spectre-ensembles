"""Shared agent context: state, decision queue, and Discord bot reference.

AgentContext is a singleton shared between the Discord bot and the agent runner.
It holds the current simulation state and a decision queue for interactive
approval flows.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from spectre_agents.types import SimulationState

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)

STATE_FILE = ".spectre-agents-state.json"


@dataclass
class PendingDecision:
    """A decision awaiting user input via Discord."""
    question: str
    options: list[str]
    future: asyncio.Future
    channel_name: str = "decisions"


@dataclass
class AgentContext:
    """Shared state between the Discord bot and agent runner."""

    simulation: SimulationState = field(default_factory=SimulationState)
    base_dir: Path = Path(".")
    bot: Optional[Any] = None  # discord.Client — typed as Any to avoid import at module level
    _decision_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    _channel_cache: dict[str, Any] = field(default_factory=dict)

    def save_state(self) -> None:
        """Persist simulation state to disk for daemon restart resilience."""
        state_path = self.base_dir / STATE_FILE
        data = {
            "active_job_id": self.simulation.active_job_id,
            "run_dir": self.simulation.run_dir,
            "model_days": self.simulation.model_days,
            "cfl_max": self.simulation.cfl_max,
            "status": self.simulation.status,
        }
        try:
            state_path.write_text(json.dumps(data, indent=2))
        except OSError as e:
            logger.warning("Failed to save state: %s", e)

    def load_state(self) -> None:
        """Restore simulation state from disk."""
        state_path = self.base_dir / STATE_FILE
        if not state_path.exists():
            return
        try:
            data = json.loads(state_path.read_text())
            self.simulation.active_job_id = data.get("active_job_id")
            self.simulation.run_dir = data.get("run_dir", "")
            self.simulation.model_days = data.get("model_days", 0.0)
            self.simulation.cfl_max = data.get("cfl_max", 0.0)
            self.simulation.status = data.get("status", "idle")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load state: %s", e)

    async def get_channel(self, channel_name: str) -> Optional[Any]:
        """Look up a Discord channel by name in the configured guild."""
        if self.bot is None:
            return None
        if channel_name in self._channel_cache:
            return self._channel_cache[channel_name]
        for guild in self.bot.guilds:
            for channel in guild.text_channels:
                if channel.name == channel_name:
                    self._channel_cache[channel_name] = channel
                    return channel
        return None

    async def request_decision(
        self, question: str, options: list[str], channel_name: str = "decisions"
    ) -> str:
        """Post a decision request to Discord and block until user responds.

        Returns the selected option text.
        """
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        decision = PendingDecision(
            question=question,
            options=options,
            future=future,
            channel_name=channel_name,
        )
        await self._decision_queue.put(decision)
        return await future
