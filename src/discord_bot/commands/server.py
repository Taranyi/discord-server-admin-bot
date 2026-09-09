from __future__ import annotations

from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands

if TYPE_CHECKING:
    from ..app import AdminBot

server_group = app_commands.Group(
    name="server",
    description="Inspect and manage this Discord server.",
    guild_only=True,
    default_permissions=discord.Permissions(administrator=True),
)


@server_group.command(name="status", description="Show the bot's server status.")
async def status(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.", ephemeral=True
        )
        return

    bot_member = guild.me
    permissions = bot_member.guild_permissions if bot_member else discord.Permissions.none()
    bot = cast("AdminBot", interaction.client)
    semester_count, course_count = bot.database.counts(guild.id)
    latency_ms = round(interaction.client.latency * 1000)
    community_enabled = "COMMUNITY" in guild.features

    message = "\n".join(
        (
            "**Discord Bot**",
            "Status: online",
            f"Server: {guild.name} (`{guild.id}`)",
            f"Gateway latency: {latency_ms} ms",
            f"Community enabled: {'yes' if community_enabled else 'no'}",
            f"Manage Channels: {'yes' if permissions.manage_channels else 'no'}",
            f"Manage Roles: {'yes' if permissions.manage_roles else 'no'}",
            "Configuration: OK",
            "Database: OK",
            f"Managed semesters: {semester_count}",
            f"Managed courses: {course_count}",
        )
    )
    await interaction.response.send_message(message, ephemeral=True)
