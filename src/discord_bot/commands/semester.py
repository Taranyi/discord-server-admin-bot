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
@app_commands.describe(
    university="Existing managed university",
    name="Semester name, for example 2026-fall",
)
async def create(
    interaction: discord.Interaction,
    university: app_commands.Range[str, 1, 100],
    name: app_commands.Range[str, 1, 100],
) -> None:
    guild = interaction.guild
    if guild is None:
        return
    bot = cast("AdminBot", interaction.client)
    try:
        clean_university = clean_entity_name(university, "University name", 100)
        clean_name = clean_entity_name(name, "Semester name", 100)
    except CourseServiceError as error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)
        return

    parent = bot.database.get_university(guild.id, clean_university)
    if parent is None:
        await interaction.response.send_message(
            f'❌ University "{clean_university}" does not exist.', ephemeral=True
        )
        return
    semester = bot.database.create_semester(guild.id, parent, clean_name)
    if semester is None:
        message = (
            f'❌ Semester "{clean_name}" already exists under '
            f'"{parent.name}".'
        )
    else:
        message = (
            f'✅ Semester created: **{semester.university_name} → {semester.name}**'
        )
    await interaction.response.send_message(message, ephemeral=True)


@semester_group.command(name="list", description="List managed semesters.")
@app_commands.describe(university="Optional university filter")
async def list_semesters(
    interaction: discord.Interaction,
    university: app_commands.Range[str, 1, 100] | None = None,
) -> None:
    guild = interaction.guild
    if guild is None:
        return
    bot = cast("AdminBot", interaction.client)
    semesters = bot.database.list_semesters(guild.id, university)
    if not semesters:
        message = "No managed semesters yet."
    else:
        lines = [
            f"- {semester.university_name} → {semester.name}"
            for semester in semesters[:50]
        ]
        if len(semesters) > 50:
            lines.append(f"- … and {len(semesters) - 50} more")
        message = "**Managed semesters**\n" + "\n".join(lines)
    await interaction.response.send_message(message, ephemeral=True)


@semester_group.command(name="delete", description="Delete an empty managed semester.")
@app_commands.describe(
    name="Managed semester name",
    university="University containing the semester; optional if unambiguous",
    confirm="Set true after reviewing the deletion preview",
)
async def delete(
    interaction: discord.Interaction,
    name: app_commands.Range[str, 1, 100],
    university: app_commands.Range[str, 1, 100] | None = None,
    confirm: bool = False,
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

    semesters = bot.database.find_semesters(guild.id, clean_name, university)
    if not semesters:
        await interaction.response.send_message(
            f'❌ Semester "{clean_name}" is not managed. Nothing was deleted.',
            ephemeral=True,
        )
        return
    if len(semesters) > 1:
        await interaction.response.send_message(
            f'❌ Semester "{clean_name}" exists under multiple universities. '
            "Specify `university`.",
            ephemeral=True,
        )
        return
    semester = semesters[0]
    course_count = bot.database.count_courses_in_semester(semester.id)
    if course_count:
        await interaction.response.send_message(
            f'❌ Semester "{semester.name}" still contains {course_count} managed '
            "course(s). Delete those courses explicitly first.",
            ephemeral=True,
        )
        return
    if not confirm:
        await interaction.response.send_message(
            f'**Deletion preview**\nSemester: **{semester.university_name} → '
            f'{semester.name}**\n'
            "Discord resources: none\n\nNothing was deleted. Run the same command "
            "with `confirm:true` to delete the local semester record.",
            ephemeral=True,
        )
        return

    if bot.database.delete_semester(semester.id):
        message = f'✅ Semester deleted: **{semester.name}**'
    else:
        message = "❌ The semester changed before deletion. Nothing was deleted."
    await interaction.response.send_message(message, ephemeral=True)


@semester_group.command(
    name="move", description="Move a managed semester to another university."
)
@app_commands.describe(
    name="Managed semester name",
    from_university="Current university",
    to_university="Destination university",
    confirm="Set true after reviewing the move preview",
)
async def move(
    interaction: discord.Interaction,
    name: app_commands.Range[str, 1, 100],
    from_university: app_commands.Range[str, 1, 100],
    to_university: app_commands.Range[str, 1, 100],
    confirm: bool = False,
) -> None:
    guild = interaction.guild
    if guild is None:
        return
    bot = cast("AdminBot", interaction.client)
    try:
        clean_name = clean_entity_name(name, "Semester name", 100)
        clean_from = clean_entity_name(from_university, "University name", 100)
        clean_to = clean_entity_name(to_university, "University name", 100)
    except CourseServiceError as error:
        await interaction.response.send_message(f"❌ {error}", ephemeral=True)
        return

    semester = bot.database.get_semester(guild.id, clean_name, clean_from)
    destination = bot.database.get_university(guild.id, clean_to)
    if semester is None:
        message = f'❌ Semester "{clean_name}" was not found under "{clean_from}".'
    elif destination is None:
        message = f'❌ University "{clean_to}" does not exist.'
    elif semester.university_id == destination.id:
        message = f'❌ Semester "{semester.name}" is already under "{destination.name}".'
    elif bot.database.get_semester(guild.id, semester.name, destination.name):
        message = (
            f'❌ Semester "{semester.name}" already exists under '
            f'"{destination.name}".'
        )
    elif not confirm:
        message = (
            f'**Move preview**\nSemester: **{semester.name}**\n'
            f"From: **{semester.university_name}**\nTo: **{destination.name}**\n"
            "Discord resources: unchanged\n\nNothing was moved. Run the same command "
            "with `confirm:true`. Existing course categories will not be renamed."
        )
    elif bot.database.move_semester(semester.id, destination):
        message = (
            f'✅ Semester moved: **{destination.name} → {semester.name}**\n'
            "Existing Discord category names were not changed."
        )
    else:
        message = "❌ The semester changed before the move. Nothing was moved."
    await interaction.response.send_message(message, ephemeral=True)
