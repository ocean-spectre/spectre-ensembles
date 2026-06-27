"""Base agent class for all SPECTRE agents.

Provides common configuration, tool registration, and the run() method
that invokes a Claude Agent SDK session.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
)

from spectre_agents.config import Config

logger = logging.getLogger(__name__)


class BaseSpectreAgent:
    """Base class for all SPECTRE simulation agents."""

    name: str = "base"
    description: str = ""
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 8192
    system_prompt: str = ""

    # Subclasses override to list their tool functions
    tool_functions: list = []

    def __init__(self, config: Config):
        self.config = config
        self.sim_dir = config.simulation_dir
        self.base_dir = config.base_dir

        # Apply model config from YAML if available
        agent_cfg = getattr(config.agents, self.name.replace("-", "_"), None)
        if agent_cfg:
            self.model = agent_cfg.model
            self.max_tokens = agent_cfg.max_tokens

    def _build_options(self) -> tuple[Any, ClaudeAgentOptions]:
        """Build the MCP server and ClaudeAgentOptions for this agent."""
        server = create_sdk_mcp_server(
            f"spectre-{self.name}-tools",
            tools=self.tool_functions,
        )
        options = ClaudeAgentOptions(
            cwd=str(self.sim_dir),
            mcp_servers={f"{self.name}-tools": server},
            system_prompt=self.system_prompt,
            model=self.model,
            permission_mode="bypassPermissions",
            max_turns=30,
        )
        return server, options

    async def run(self, task: str) -> str:
        """Run the agent with a task prompt and return the final text response."""
        _, options = self._build_options()

        result_text = ""
        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(task)
                async for message in client.receive_response():
                    if isinstance(message, ResultMessage):
                        result_text = message.result or ""
                    elif isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                # Capture last text output
                                result_text = block.text
        except Exception as e:
            logger.exception("Agent %s failed: %s", self.name, e)
            result_text = f"Agent {self.name} error: {e}"

        return result_text
