from __future__ import annotations

import logging

import discord
from discord import app_commands

from .commands.server import server_group
from .config import Settings

logger = logging.getLogger(__name__)


class AdminCommandTree(app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.permissions.administrator:
            raise app_commands.MissingPermissions(["administrator"])
        return True

    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "You need the Discord Administrator permission to use this command."
        else:
            message = "The command failed unexpectedly. Check the local bot log."
            command_name = (
                interaction.command.qualified_name
                if interaction.command is not None
                else "unknown"
            )
            logger.error(
                "Application command failed: %s",
                command_name,
                exc_info=(type(error), error, error.__traceback__),
            )

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


class AdminBot(discord.Client):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        super().__init__(
            intents=intents,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.settings = settings
        self.tree = AdminCommandTree(self)

    async def setup_hook(self) -> None:
        self.tree.add_command(server_group)
        await self._sync_commands()

    async def _sync_commands(self) -> None:
        mode = self.settings.command_sync
        if mode == "off":
            logger.info("Application command synchronization is disabled")
            return

        if mode == "global":
            synced = await self.tree.sync()
            logger.info("Synchronized %d global application command(s)", len(synced))
            return

        if self.settings.discord_guild_id is None:
            raise RuntimeError("Guild command sync requires a configured guild ID")
        guild = discord.Object(id=self.settings.discord_guild_id)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        logger.info(
            "Synchronized %d application command(s) to guild %d",
            len(synced),
            guild.id,
        )

    async def on_ready(self) -> None:
        if self.user is None:
            return
        logger.info(
            "Connected as %s (ID: %d); visible guilds: %d",
            self.user,
            self.user.id,
            len(self.guilds),
        )
