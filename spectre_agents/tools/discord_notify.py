"""Discord notification tools for agent-to-user communication.

These tools reference the shared AgentContext to post messages, images,
and interactive decision requests to Discord channels.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from claude_agent_sdk import tool

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Module-level reference set by the bot at startup
_context = None


def set_agent_context(ctx) -> None:
    """Set the shared AgentContext for Discord tools to use."""
    global _context
    _context = ctx


@tool(
    "send_discord_message",
    "Send a message to a Discord channel. Use channel names: "
    "simulation-status, decisions, alerts, plots, logs.",
    {"channel_name": str, "content": str},
)
async def send_discord_message(args: dict) -> dict:
    channel_name: str = args["channel_name"]
    content: str = args["content"]

    if _context is None or _context.bot is None:
        return {"content": [{"type": "text", "text": "Discord bot not connected"}]}

    try:
        channel = await _context.get_channel(channel_name)
        if channel is None:
            return {"content": [{"type": "text", "text": f"Channel #{channel_name} not found"}]}

        # Discord message limit is 2000 chars
        if len(content) > 1900:
            content = content[:1900] + "\n... (truncated)"

        await channel.send(content)
        return {"content": [{"type": "text", "text": f"Message sent to #{channel_name}"}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Failed to send message: {e}"}]}


@tool(
    "send_discord_image",
    "Upload an image file to a Discord channel with an optional caption.",
    {"channel_name": str, "image_path": str, "caption": str},
)
async def send_discord_image(args: dict) -> dict:
    import discord

    channel_name: str = args["channel_name"]
    image_path: str = args["image_path"]
    caption: str = args.get("caption", "")

    if _context is None or _context.bot is None:
        return {"content": [{"type": "text", "text": "Discord bot not connected"}]}

    try:
        channel = await _context.get_channel(channel_name)
        if channel is None:
            return {"content": [{"type": "text", "text": f"Channel #{channel_name} not found"}]}

        file = discord.File(image_path)
        await channel.send(content=caption or None, file=file)
        return {"content": [{"type": "text", "text": f"Image sent to #{channel_name}"}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Failed to send image: {e}"}]}


@tool(
    "request_user_decision",
    "Post an interactive decision request to Discord with numbered options. "
    "Blocks until the user selects an option. Returns the selected option text.",
    {"question": str, "options": list},
)
async def request_user_decision(args: dict) -> dict:
    question: str = args["question"]
    options: list = args["options"]

    if _context is None or _context.bot is None:
        return {"content": [{"type": "text", "text": "Discord bot not connected — cannot request decision"}]}

    try:
        selected = await _context.request_decision(question, options, "decisions")
        return {"content": [{"type": "text", "text": f"User selected: {selected}"}]}
    except asyncio.TimeoutError:
        return {"content": [{"type": "text", "text": "Decision request timed out — no user response"}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Decision request failed: {e}"}]}
