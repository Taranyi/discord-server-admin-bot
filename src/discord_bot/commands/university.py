from __future__ import annotations

from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands

from ..course_service import CourseServiceError, clean_entity_name

if TYPE_CHECKING:
    from ..app import AdminBot


university_group = app_commands.Group(
    name="university",
    description="Manage universities above semesters and courses.",
    guild_only=True,
    default_permissions=discord.Permissions(administrator=True),
)


@university_group.command(name="create", description="Create a managed university.")
@app_commands.describe(name="University name or short name, for example ELTE")
async def create(
    interaction: discord.Interaction, name: app_commands.Range[str, 1, 100]
) -> None:
    guild = interaction.guild
    if guild is None:
        return
    bot = cast("AdminBot", interaction.client)
    try:
        clean_name = clean_entity_name(name, "University name", 100)
    except CourseServiceError as error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)
        return

    university = bot.database.create_university(guild.id, clean_name)
    message = (
        f"✅ University created: **{university.name}**"
        if university is not None
        else f'❌ University "{clean_name}" already exists.'
    )
    await interaction.response.send_message(message, ephemeral=True)


@university_group.command(name="list", description="List managed universities.")
async def list_universities(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if guild is None:
        return
    bot = cast("AdminBot", interaction.client)
    universities = bot.database.list_universities(guild.id)
    if not universities:
        message = "No managed universities yet."
    else:
        lines = []
        for university in universities[:50]:
            semester_count = bot.database.count_semesters_in_university(university.id)
            lines.append(f"- {university.name} — {semester_count} semester(s)")
        if len(universities) > 50:
            lines.append(f"- … and {len(universities) - 50} more")
        message = "**Managed universities**\n" + "\n".join(lines)
    await interaction.response.send_message(message, ephemeral=True)


@university_group.command(
    name="delete", description="Delete an empty managed university."
)
@app_commands.describe(
    name="Managed university name",
    confirm="Set true after reviewing the deletion preview",
)
async def delete(
    interaction: discord.Interaction,
    name: app_commands.Range[str, 1, 100],
    confirm: bool = False,
) -> None:
    guild = interaction.guild
    if guild is None:
        return
    bot = cast("AdminBot", interaction.client)
    try:
        clean_name = clean_entity_name(name, "University name", 100)
    except CourseServiceError as error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)
        return

    university = bot.database.get_university(guild.id, clean_name)
    if university is None:
        await interaction.response.send_message(
            f'❌ University "{clean_name}" is not managed. Nothing was deleted.',
            ephemeral=True,
        )
        return
    semester_count = bot.database.count_semesters_in_university(university.id)
    if semester_count:
        await interaction.response.send_message(
            f'❌ University "{university.name}" still contains {semester_count} '
            "managed semester(s). Delete or move those semesters first.",
            ephemeral=True,
        )
        return
    if not confirm:
        await interaction.response.send_message(
            f'**Deletion preview**\nUniversity: **{university.name}**\n'
            "Discord resources: none\n\nNothing was deleted. Run the same command "
            "with `confirm:true` to delete the local university record.",
            ephemeral=True,
        )
        return

    message = (
        f"✅ University deleted: **{university.name}**"
        if bot.database.delete_university(university.id)
        else "❌ The university changed before deletion. Nothing was deleted."
    )
    await interaction.response.send_message(message, ephemeral=True)
