from __future__ import annotations

from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands

from ..course_service import CourseServiceError, clean_entity_name

if TYPE_CHECKING:
    from ..app import AdminBot

semester_group = app_commands.Group(
    name="semester",
    description="Manage academic semesters.",
    guild_only=True,
    default_permissions=discord.Permissions(administrator=True),
)


@semester_group.command(name="create", description="Create a managed semester.")
@app_commands.describe(name="Semester name, for example 2026-fall")
async def create(
    interaction: discord.Interaction, name: app_commands.Range[str, 1, 100]
) -> None:
    guild = interaction.guild
    if guild is None:
        return
    bot = cast("AdminBot", interaction.client)
    try:
        clean_name = clean_entity_name(name, "Semester name", 100)
    except CourseServiceError as error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)
        return

    semester = bot.database.create_semester(guild.id, clean_name)
    if semester is None:
        message = f'❌ Semester "{clean_name}" already exists.'
    else:
        message = f'✅ Semester created: **{semester.name}**'
    await interaction.response.send_message(message, ephemeral=True)


@semester_group.command(name="list", description="List managed semesters.")
async def list_semesters(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if guild is None:
        return
    bot = cast("AdminBot", interaction.client)
    semesters = bot.database.list_semesters(guild.id)
    if not semesters:
        message = "No managed semesters yet."
    else:
        lines = [f"- {semester.name}" for semester in semesters[:50]]
        if len(semesters) > 50:
            lines.append(f"- … and {len(semesters) - 50} more")
        message = "**Managed semesters**\n" + "\n".join(lines)
    await interaction.response.send_message(message, ephemeral=True)
