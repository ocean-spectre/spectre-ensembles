"""Main Discord bot class and event loop integration.

The bot connects to Discord, registers slash commands, and processes
decision queue items from the agent system. It runs on the asyncio
event loop alongside the agent runner.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from spectre_agents.discord_bot.commands import setup_commands
from spectre_agents.discord_bot.embeds import decision_embed
from spectre_agents.discord_bot.knowledge import setup_knowledge_handler
from spectre_agents.discord_bot.views import DecisionView

if TYPE_CHECKING:
    from spectre_agents.config import Config
    from spectre_agents.context import AgentContext

logger = logging.getLogger(__name__)


class SpectreBot(discord.Client):
    """Discord bot for SPECTRE simulation operations."""

    def __init__(self, config: Config, ctx: AgentContext):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True

        super().__init__(intents=intents)
        self.config = config
        self.ctx = ctx
        self.tree = app_commands.CommandTree(self)
        self._decision_task: asyncio.Task | None = None

    async def setup_hook(self) -> None:
        """Called after login, before the bot is fully connected."""
        setup_commands(self.tree, self.ctx, self.config)

        # Sync commands to the guild
        if self.config.discord_guild_id:
            guild = discord.Object(id=self.config.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Synced commands to guild %s", self.config.discord_guild_id)
        else:
            await self.tree.sync()
            logger.info("Synced commands globally")

    async def on_ready(self) -> None:
        logger.info("Bot connected as %s (ID: %s)", self.user, self.user.id)
        logger.info("Guilds: %s", [g.name for g in self.guilds])

        # Store bot reference in context for tools to use
        self.ctx.bot = self

        # Start the decision queue processor
        self._decision_task = asyncio.create_task(self._process_decision_queue())

        # Register the knowledge Q&A handler for #ask-mitgcm
        setup_knowledge_handler(self, self.config, self.ctx)
        logger.info("Knowledge bot listening in #%s", self.config.discord_channels.knowledge)

        # Post startup message
        channel = await self.ctx.get_channel(self.config.discord_channels.status)
        if channel:
            await channel.send(
                "**SPECTRE Agent System** online.\n"
                "Use `/run start` to begin a simulation, `/run status` to check progress.\n"
                f"Ask questions in #**{self.config.discord_channels.knowledge}**."
            )

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        logger.exception("Discord error in %s", event_method)

    async def _process_decision_queue(self) -> None:
        """Continuously process pending decisions from agents.

        When the orchestrator posts a decision to the queue, this task
        picks it up, posts an interactive embed to Discord, and the
        DecisionView callback resolves the future.
        """
        logger.info("Decision queue processor started")
        while True:
            try:
                decision = await self.ctx._decision_queue.get()
                logger.info("Processing decision: %s", decision.question)

                channel = await self.ctx.get_channel(decision.channel_name)
                if channel is None:
                    logger.warning("Channel %s not found for decision", decision.channel_name)
                    if not decision.future.done():
                        decision.future.set_exception(
                            RuntimeError(f"Channel #{decision.channel_name} not found")
                        )
                    continue

                embed = decision_embed(decision.question, decision.options)
                view = DecisionView(decision.options, decision.future)
                await channel.send(embed=embed, view=view)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error processing decision")

    async def close(self) -> None:
        if self._decision_task:
            self._decision_task.cancel()
        await super().close()


async def run_bot(config: Config, ctx: AgentContext) -> None:
    """Start the Discord bot. This coroutine runs until the bot disconnects."""
    if not config.discord_bot_token:
        logger.error("DISCORD_BOT_TOKEN not set — bot will not start")
        return

    bot = SpectreBot(config, ctx)
    try:
        await bot.start(config.discord_bot_token)
    except discord.LoginFailure:
        logger.error("Invalid Discord bot token")
    except Exception:
        logger.exception("Bot crashed")
    finally:
        if not bot.is_closed():
            await bot.close()
