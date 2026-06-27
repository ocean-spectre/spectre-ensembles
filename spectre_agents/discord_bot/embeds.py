"""Rich embed formatters for Discord messages.

Each function returns a discord.Embed with appropriate colors, fields,
and formatting for different notification types.
"""

from __future__ import annotations

from datetime import datetime, timezone

import discord


# Color palette
COLOR_GREEN = 0x2ECC71   # Healthy / success
COLOR_YELLOW = 0xF1C40F  # Warning
COLOR_RED = 0xE74C3C     # Critical / failure
COLOR_BLUE = 0x3498DB    # Info / status
COLOR_PURPLE = 0x9B59B6  # Decision request


def status_embed(
    job_id: int | None,
    state: str,
    model_days: float,
    cfl: float,
    throughput: str = "",
) -> discord.Embed:
    """Create a simulation status embed with color-coded health."""
    if state == "RUNNING":
        color = COLOR_GREEN if cfl < 0.4 else COLOR_YELLOW
    elif state in ("COMPLETED", "DONE"):
        color = COLOR_GREEN
    else:
        color = COLOR_RED

    embed = discord.Embed(
        title="Simulation Status",
        description=f"`glorysv12-curvilinear`",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    if job_id:
        embed.add_field(name="Job ID", value=str(job_id), inline=True)
    embed.add_field(name="State", value=state, inline=True)
    embed.add_field(name="Model Days", value=f"{model_days:.1f}", inline=True)
    embed.add_field(name="CFL", value=f"{cfl:.3f}", inline=True)
    if throughput:
        embed.add_field(name="Throughput", value=throughput, inline=True)
    return embed


def failure_embed(
    failure_type: str,
    root_cause: str,
    evidence: str,
    suggested_fix: str,
    job_id: int | None = None,
    model_days: float = 0,
) -> discord.Embed:
    """Create a failure diagnosis embed (red sidebar)."""
    embed = discord.Embed(
        title=f"Simulation Failed — {failure_type}",
        description=f"`glorysv12-curvilinear`",
        color=COLOR_RED,
        timestamp=datetime.now(timezone.utc),
    )
    if job_id:
        embed.add_field(name="Job ID", value=str(job_id), inline=True)
    embed.add_field(name="Model Days", value=f"{model_days:.1f}", inline=True)
    embed.add_field(name="Root Cause", value=root_cause[:1024], inline=False)
    if evidence:
        embed.add_field(name="Evidence", value=f"```\n{evidence[:1000]}\n```", inline=False)
    embed.add_field(name="Suggested Fix", value=suggested_fix[:1024], inline=False)
    return embed


def health_embed(
    status: str,
    model_days: float,
    summary: str,
    fields: dict[str, str],
    recommendation: str = "",
) -> discord.Embed:
    """Create a health assessment embed with per-field breakdown."""
    color_map = {"HEALTHY": COLOR_GREEN, "WARNING": COLOR_YELLOW, "CRITICAL": COLOR_RED}
    color = color_map.get(status, COLOR_BLUE)

    embed = discord.Embed(
        title=f"Model Health: {status}",
        description=summary,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(name="Model Days", value=f"{model_days:.1f}", inline=True)

    for name, assessment in fields.items():
        embed.add_field(name=name, value=assessment[:1024], inline=False)

    if recommendation:
        embed.add_field(name="Recommendation", value=recommendation[:1024], inline=False)

    return embed


def validation_embed(checks: list[dict[str, str]]) -> discord.Embed:
    """Create a namelist validation embed with PASS/FAIL per check."""
    pass_count = sum(1 for c in checks if c.get("result") == "PASS")
    fail_count = sum(1 for c in checks if c.get("result") == "FAIL")
    total = len(checks)

    color = COLOR_GREEN if fail_count == 0 else COLOR_RED

    embed = discord.Embed(
        title=f"Namelist Validation: {pass_count}/{total} passed",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )

    # Group checks into a compact format
    lines = []
    for check in checks[:25]:  # Discord embed field limit
        icon = "\u2705" if check.get("result") == "PASS" else "\u274c"
        lines.append(f"{icon} {check.get('name', 'check')}: {check.get('detail', '')}")

    embed.description = "\n".join(lines) if lines else "No checks performed"

    if fail_count > 0:
        embed.set_footer(text=f"{fail_count} check(s) failed — review before submitting")

    return embed


def decision_embed(question: str, options: list[str]) -> discord.Embed:
    """Create a decision request embed (purple sidebar)."""
    embed = discord.Embed(
        title="Decision Needed",
        description=question,
        color=COLOR_PURPLE,
        timestamp=datetime.now(timezone.utc),
    )
    option_text = "\n".join(f"**{i + 1}.** {opt}" for i, opt in enumerate(options))
    embed.add_field(name="Options", value=option_text, inline=False)
    embed.set_footer(text="Select an option below. The orchestrator is waiting for your response.")
    return embed


def milestone_embed(title: str, details: str) -> discord.Embed:
    """Create a milestone achievement embed (green sidebar)."""
    return discord.Embed(
        title=f"Milestone: {title}",
        description=details,
        color=COLOR_GREEN,
        timestamp=datetime.now(timezone.utc),
    )
