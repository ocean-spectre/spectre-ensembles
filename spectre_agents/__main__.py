"""Entry point for the SPECTRE agent system.

Usage:
    python -m spectre_agents [--config PATH]

Starts the Discord bot and agent runner as concurrent asyncio tasks.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from spectre_agents.config import load_config
from spectre_agents.context import AgentContext
from spectre_agents.discord_bot.bot import run_bot
from spectre_agents.tools.discord_notify import set_agent_context

logger = logging.getLogger("spectre_agents")


def setup_logging() -> None:
    """Configure structured logging to stderr and optional file."""
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    # Suppress noisy discord.py debug logs
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)


async def main(config_path: str | None = None) -> None:
    """Main async entry point."""
    setup_logging()

    config = load_config(config_path)
    logger.info("Loaded config: base_dir=%s, sim_dir=%s", config.base_dir, config.sim_dir)

    # Validate required secrets
    if not config.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY not set. Set it in /etc/spectre-agents/env or environment.")
        sys.exit(1)
    if not config.discord_bot_token:
        logger.error("DISCORD_BOT_TOKEN not set. Set it in /etc/spectre-agents/env or environment.")
        sys.exit(1)

    # Initialize shared context
    ctx = AgentContext(base_dir=config.base_dir)
    ctx.load_state()
    logger.info("Loaded state: status=%s, job=%s", ctx.simulation.status, ctx.simulation.active_job_id)

    # Wire up Discord tools with the context
    set_agent_context(ctx)

    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def signal_handler(sig):
        logger.info("Received signal %s, shutting down...", sig)
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler, sig)

    # Run the Discord bot — it manages the event loop
    logger.info("Starting SPECTRE Agent System...")
    try:
        await run_bot(config, ctx)
    except asyncio.CancelledError:
        pass
    finally:
        ctx.save_state()
        logger.info("SPECTRE Agent System stopped.")


def cli() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="SPECTRE Simulation Agent System with Discord bot"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to spectre_agents_config.yaml",
    )
    args = parser.parse_args()
    asyncio.run(main(args.config))


if __name__ == "__main__":
    cli()
