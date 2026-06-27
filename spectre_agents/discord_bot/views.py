"""Interactive Discord views (buttons) for decision approval flows.

DecisionView presents numbered option buttons. When the user clicks one,
the corresponding asyncio.Future is resolved, unblocking the orchestrator.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import discord


class DecisionButton(discord.ui.Button):
    """A button representing one decision option."""

    def __init__(self, label: str, index: int, future: asyncio.Future):
        style = discord.ButtonStyle.primary if index == 0 else discord.ButtonStyle.secondary
        super().__init__(label=label, style=style, custom_id=f"decision_{index}")
        self.option_label = label
        self.future = future

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.future.done():
            await interaction.response.send_message(
                "This decision has already been made.", ephemeral=True
            )
            return

        self.future.set_result(self.option_label)
        await interaction.response.send_message(
            f"Selected: **{self.option_label}**\nResuming orchestrator...",
        )
        # Disable all buttons in the view
        if self.view:
            for item in self.view.children:
                item.disabled = True
            await interaction.message.edit(view=self.view)


class DecisionView(discord.ui.View):
    """Interactive view with numbered option buttons for agent decisions."""

    def __init__(self, options: list[str], future: asyncio.Future, timeout: float = 3600):
        super().__init__(timeout=timeout)
        self.future = future
        for i, option in enumerate(options[:5]):  # Discord max 5 buttons per row
            self.add_item(DecisionButton(option, i, future))

    async def on_timeout(self) -> None:
        if not self.future.done():
            self.future.set_exception(asyncio.TimeoutError("Decision timed out (1 hour)"))


class ConfirmView(discord.ui.View):
    """Simple Yes/No confirmation view for destructive actions."""

    def __init__(self, future: asyncio.Future, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.future = future

    @discord.ui.button(label="Yes, proceed", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.future.done():
            self.future.set_result(True)
        await interaction.response.send_message("Confirmed. Proceeding...")
        self._disable_all()
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.future.done():
            self.future.set_result(False)
        await interaction.response.send_message("Cancelled.")
        self._disable_all()
        await interaction.message.edit(view=self)

    def _disable_all(self) -> None:
        for item in self.children:
            item.disabled = True

    async def on_timeout(self) -> None:
        if not self.future.done():
            self.future.set_result(False)
