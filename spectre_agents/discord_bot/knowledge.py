"""Knowledge bot: answers MITgcm, ERA5, oceanography, and codebase questions.

Listens in #ask-mitgcm for messages, runs a Claude agent with the full
CLAUDE.md context + WebSearch/WebFetch, and replies in-channel or in a thread.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from spectre_agents.config import Config
    from spectre_agents.context import AgentContext

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="knowledge")

# The knowledge agent's system prompt, combining CLAUDE.md domain knowledge
# with instructions for being a helpful Q&A assistant.
KNOWLEDGE_SYSTEM_PROMPT = """\
You are the SPECTRE knowledge assistant — an expert on MITgcm ocean modeling, \
ERA5/GLORYS reanalysis data, and the SPECTRE simulation system. You answer \
questions from researchers and engineers working on North Atlantic ocean \
simulations.

## Your expertise

- **MITgcm**: namelist parameters, packages (EXF, OBCS, DIAGNOSTICS, KPP, MNC), \
  Fortran source code, numerical methods, grid configuration, debugging
- **ERA5 / Copernicus**: variable definitions, accumulation conventions, units, \
  CDS API, temporal/spatial resolution
- **GLORYS v12**: ocean reanalysis fields, CMEMS access, variable naming
- **Oceanography**: North Atlantic circulation, Gulf Stream dynamics, \
  air-sea fluxes, boundary conditions, ensemble methods
- **HPC / SLURM**: job scheduling, container workflows (enroot/pyxis), \
  parallel I/O, memory management
- **This codebase**: spectre_utils Python package, workflow scripts, \
  configuration files, bred vector ensembles

## SPECTRE simulation context

This project runs a realistic MITgcm simulation of the North Atlantic (26-54N):
- Grid: Native NEMO curvilinear, 768 x 424 x 50 levels, MPI 8x8 = 64 ranks
- Ocean data: GLORYS v12 daily fields (T, S, U, V, SSH) for IC and OBC
- Atmospheric forcing: ERA5 3-hourly single-level fields via EXF package
- Simulation period: 2002-07-01 to 2017-06-30
- Key directory: simulations/glorysv12-curvilinear/

### Critical technical details

- **EXF latitude orientation**: ERA5 stores latitude north-to-south. MITgcm EXF \
  expects south-to-north (lat0=20.0, lat_inc=+0.25). The mk_exf_conditions.py \
  script flips the axis. Getting this wrong causes ~20C air-sea temperature error.

- **EXF range thresholds** (hardcoded in exf_check_range.F): \
  hflux: [-500, +1600] W/m2; ustress/vstress: +/-2.0 N/m2

- **Bulk formula**: ALLOW_BULK_LARGEYEAGER04 — Large & Yeager (2009) \
  stability-corrected with wind-speed-dependent drag coefficients.

- **MNC tile numbering**: mnc_*_0001/ contains PID 0, which writes tile t004.

- **ERA5 scale factors**: 3-hourly accumulations to W/m2 or m/s use \
  1/10800 = 9.2593e-5 (not 1/3600).

- **EXF does not support negative lat_inc** — exf_interp.F assumes \
  monotonically increasing latitude.

- **OBC period = 86400.0s (daily), EXF period = 10800.0s (3-hourly)**

- **MNC memory leak**: diag_mnc=.FALSE. with a post-processor converter \
  is the workaround for long runs.

## How to respond

- Be direct and technical. Lead with the answer, then explain.
- Include MITgcm parameter names, file paths, and Fortran source references.
- When uncertain, say so and suggest where to look (readthedocs, source code).
- For questions about this specific simulation, reference the config and namelists.
- Use code blocks for parameter examples, file snippets, and commands.
- If a question requires web lookup (latest docs, specific source code), \
  use WebSearch/WebFetch to find the answer.
"""


async def _run_knowledge_query(config: Config, question: str, context_hint: str = "") -> str:
    """Run the knowledge agent and return its text response."""
    from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage, AssistantMessage, TextBlock

    prompt = question
    if context_hint:
        prompt = f"{context_hint}\n\nQuestion: {question}"

    result_text = ""
    try:
        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                cwd=str(config.simulation_dir),
                allowed_tools=["Read", "Glob", "Grep", "WebSearch", "WebFetch"],
                system_prompt=KNOWLEDGE_SYSTEM_PROMPT,
                model=config.agents.web_research.model,  # Sonnet for Q&A
                permission_mode="default",
                max_turns=10,
            ),
        ):
            if isinstance(message, ResultMessage):
                result_text = message.result or ""
            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text = block.text
    except Exception as e:
        logger.exception("Knowledge agent failed")
        result_text = f"Sorry, I encountered an error: {e}"

    return result_text


def setup_knowledge_handler(bot: discord.Client, config: Config, ctx: AgentContext) -> None:
    """Register the on_message handler for #ask-mitgcm Q&A."""

    channel_name = config.discord_channels.knowledge

    @bot.event
    async def on_message(message: discord.Message) -> None:
        # Ignore own messages
        if message.author == bot.user:
            return

        # Ignore DMs
        if not message.guild:
            return

        # Only respond in the knowledge channel
        if message.channel.name != channel_name:
            return

        # Ignore messages that are just bot mentions with no content
        content = message.content.strip()
        if not content:
            return

        # Strip bot mention if present
        if bot.user and bot.user.mentioned_in(message):
            content = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()

        if not content:
            return

        logger.info("Knowledge query from %s: %s", message.author, content[:100])

        # Show typing indicator while processing
        async with message.channel.typing():
            # Build context from recent thread/conversation
            context_hint = ""
            if isinstance(message.channel, discord.Thread):
                context_hint = f"(This question is in a thread titled: {message.channel.name})"

            result = await _run_knowledge_query(config, content, context_hint)

        # Reply in thread if message is in a thread, otherwise create one for long answers
        if not result:
            result = "I wasn't able to find an answer. Could you rephrase or provide more context?"

        # Discord 2000 char limit — split long responses
        if len(result) <= 2000:
            await message.reply(result, mention_author=False)
        else:
            # Create a thread for long answers
            if not isinstance(message.channel, discord.Thread):
                thread = await message.create_thread(
                    name=content[:90] + "..." if len(content) > 90 else content,
                    auto_archive_duration=60,
                )
                target = thread
            else:
                target = message.channel

            # Send in chunks
            chunks = _split_message(result)
            for chunk in chunks:
                await target.send(chunk)


def _split_message(text: str, limit: int = 1900) -> list[str]:
    """Split a long message into chunks, preferring line boundaries."""
    if len(text) <= limit:
        return [text]

    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break

        # Try to split at a newline
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1 or split_at < limit // 2:
            # Try space
            split_at = text.rfind(" ", 0, limit)
        if split_at == -1:
            split_at = limit

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    return chunks
