from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands

from ..course_service import (
    CourseProvisionError,
    CourseServiceError,
    CourseSyncResult,
)

if TYPE_CHECKING:
    from ..app import AdminBot

logger = logging.getLogger(__name__)

course_group = app_commands.Group(
    name="course",
    description="Manage course structures.",
    guild_only=True,
    default_permissions=discord.Permissions(administrator=True),
)


@course_group.command(name="create", description="Create a managed course structure.")
@app_commands.describe(
    name="Human-readable course name",
    semester="Existing managed semester",
    code="Optional course code",
)
async def create(
    interaction: discord.Interaction,
    name: app_commands.Range[str, 1, 100],
    semester: app_commands.Range[str, 1, 100],
    code: app_commands.Range[str, 1, 32] | None = None,
) -> None:
    guild = interaction.guild
    if guild is None:
        return
    bot = cast("AdminBot", interaction.client)
    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        result = await bot.course_service.create_course(
            guild,
            name=name,
            semester_name=semester,
            code=code,
            requested_by=interaction.user.id,
        )
    except CourseProvisionError as error:
        logger.exception("Course provisioning failed in guild %d", guild.id)
        created = "\n".join(f"- {item}" for item in error.created)
        suffix = f"\n\nCreated before the failure:\n{created}" if created else ""
        await interaction.edit_original_response(content=f"❌ {error}{suffix}")
        return
    except CourseServiceError as error:
        await interaction.edit_original_response(content=f"❌ {error}")
        return

    heading = "✅ Course completed" if result.resumed else "✅ Course created"
    details = [
        heading,
        "",
        f"**{result.course.name}**",
        f"Semester: {result.course.semester_name}",
    ]
    if result.course.code:
        details.append(f"Code: {result.course.code}")
    if result.created:
        details.extend(("", "Created:", *(f"- {item}" for item in result.created)))
    else:
        details.extend(("", "All managed resources were already present."))
    await interaction.edit_original_response(content="\n".join(details))


@course_group.command(name="list", description="List managed courses.")
@app_commands.describe(semester="Optional semester filter")
async def list_courses(
    interaction: discord.Interaction,
    semester: app_commands.Range[str, 1, 100] | None = None,
) -> None:
    guild = interaction.guild
    if guild is None:
        return
    bot = cast("AdminBot", interaction.client)
    courses = bot.database.list_courses(guild.id, semester)
    if not courses:
        message = "No managed courses found."
    else:
        lines = []
        for course in courses[:50]:
            code = f" [{course.code}]" if course.code else ""
            state = "" if course.status == "active" else " — incomplete"
            lines.append(f"- {course.name}{code} — {course.semester_name}{state}")
        if len(courses) > 50:
            lines.append(f"- … and {len(courses) - 50} more")
        message = "**Managed courses**\n" + "\n".join(lines)
    await interaction.response.send_message(message, ephemeral=True)


@course_group.command(name="info", description="Show a managed course and its resources.")
@app_commands.describe(name="Managed course name")
async def info(
    interaction: discord.Interaction, name: app_commands.Range[str, 1, 100]
) -> None:
    guild = interaction.guild
    if guild is None:
        return
    bot = cast("AdminBot", interaction.client)
    course = bot.database.get_course(guild.id, name)
    if course is None:
        await interaction.response.send_message(
            f'❌ Course "{name}" is not managed.', ephemeral=True
        )
        return

    channels = bot.database.get_course_channels(course.id)
    lines = [
        f"**{course.name}**",
        f"Semester: {course.semester_name}",
        f"Code: {course.code or '—'}",
        f"Status: {course.status}",
        f"Category ID: {course.category_id or 'not created'}",
        "",
        "Managed channels:",
    ]
    if channels:
        lines.extend(
            f"- {channel.template_key} ({channel.channel_type}): "
            f"`{channel.discord_channel_id}`"
            for channel in channels
        )
    else:
        lines.append("- none")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@course_group.command(
    name="sync", description="Accept and record the current Discord course state."
)
@app_commands.describe(name="Optional managed course name; omit to sync every course")
async def sync(
    interaction: discord.Interaction,
    name: app_commands.Range[str, 1, 100] | None = None,
) -> None:
    guild = interaction.guild
    if guild is None:
        return
    bot = cast("AdminBot", interaction.client)
    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        results = bot.course_service.sync_courses(guild, name=name)
    except CourseServiceError as error:
        await interaction.edit_original_response(content=f"❌ {error}")
        return

    if len(results) == 1:
        message = _format_sync_details(results[0])
    else:
        lines = [
            f"✅ Saved the current Discord state for {len(results)} course(s).",
            "No Discord resources were modified.",
            "",
        ]
        for result in results[:40]:
            warning_count = (
                len(result.missing)
                + len(result.ambiguous)
                + int(result.category_issue is not None)
            )
            changes = len(result.accepted_changes) + len(result.rebound)
            lines.append(
                f"- **{result.course.name}**: {result.present_count} channel(s), "
                f"{changes} accepted change(s), {warning_count} warning(s)"
            )
        if len(results) > 40:
            lines.append(f"- … and {len(results) - 40} more")
        lines.extend(("", "Run `/course sync name:<course>` for full details."))
        message = "\n".join(lines)

    await interaction.edit_original_response(content=_fit_discord_message(message))


def _format_sync_details(result: CourseSyncResult) -> str:
    lines = [
        "✅ Current Discord state saved locally",
        "No Discord resources were modified.",
        "",
        f"**{result.course.name}**",
        f"Category: {result.category_name or 'missing'}",
        f"Observed channels: {result.present_count}",
    ]
    if result.category_rebound:
        lines.append("- Reconnected the course to its unique matching category.")
    if result.category_issue:
        lines.append(f"- ⚠️ Category: {result.category_issue}")
    _append_sync_section(lines, "Accepted manual changes", result.accepted_changes)
    _append_sync_section(lines, "Reconnected managed resources", result.rebound)
    _append_sync_section(lines, "Additional channels kept and observed", result.additional)
    _append_sync_section(lines, "Missing managed resources", result.missing, warning=True)
    _append_sync_section(lines, "Ambiguous matches", result.ambiguous, warning=True)
    if not any(
        (
            result.category_rebound,
            result.category_issue,
            result.accepted_changes,
            result.rebound,
            result.additional,
            result.missing,
            result.ambiguous,
        )
    ):
        lines.extend(("", "No manual differences detected."))
    return "\n".join(lines)


def _append_sync_section(
    lines: list[str], heading: str, items: tuple[str, ...], *, warning: bool = False
) -> None:
    if not items:
        return
    marker = "⚠️ " if warning else ""
    lines.extend(("", f"{marker}**{heading}:**", *(f"- {item}" for item in items)))


def _fit_discord_message(message: str, limit: int = 1950) -> str:
    if len(message) <= limit:
        return message
    suffix = "\n\n… Output shortened. Check the local log or sync one course at a time."
    return message[: limit - len(suffix)].rstrip() + suffix
