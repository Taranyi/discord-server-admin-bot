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
course_channel_group = app_commands.Group(
    name="channel",
    description="Manage channels shared by every managed course.",
    parent=course_group,
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


@course_group.command(name="delete", description="Safely delete a managed course.")
@app_commands.describe(
    name="Managed course name",
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
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        result = await bot.course_service.delete_course(
            guild,
            name=name,
            confirm=confirm,
            requested_by=interaction.user.id,
        )
    except CourseServiceError as error:
        await interaction.edit_original_response(content=f"❌ {error}")
        return

    if not result.confirmed:
        lines = [
            "**Course deletion preview**",
            f"Course: **{result.course.name}**",
            f"Managed channels to delete: {len(result.managed_live)}",
            f"Already missing managed channels: {len(result.managed_missing)}",
            "Category: "
            + ("will be deleted" if result.category_will_delete else "will be kept"),
        ]
        _append_sync_section(lines, "Managed resources", result.managed_live)
        _append_sync_section(
            lines, "Manual/untracked channels that will be kept", result.manual_kept
        )
        lines.extend(
            (
                "",
                "Nothing was deleted. Run the same command with `confirm:true` "
                "to apply this exact safety policy.",
            )
        )
    else:
        icon = "✅" if result.record_removed else "⚠️"
        lines = [
            f"{icon} Course deletion {'completed' if result.record_removed else 'incomplete'}",
            f"Course: **{result.course.name}**",
        ]
        _append_sync_section(lines, "Deleted", result.deleted)
        _append_sync_section(lines, "Manual channels kept", result.manual_kept)
        _append_sync_section(lines, "Failures; retry safely", result.failures, warning=True)
        if not result.record_removed:
            lines.extend(("", "The course record was kept so the command can be retried."))
    await interaction.edit_original_response(
        content=_fit_discord_message("\n".join(lines))
    )


@course_channel_group.command(
    name="add-all", description="Add a managed channel to every course."
)
@app_commands.describe(
    name="Shared channel name",
    channel_type="Discord channel type",
    topic="Optional text or forum topic",
    confirm="Set true after reviewing the preview",
)
@app_commands.choices(
    channel_type=[
        app_commands.Choice(name="Text", value="text"),
        app_commands.Choice(name="Forum", value="forum"),
        app_commands.Choice(name="Voice", value="voice"),
    ]
)
async def add_all_channel(
    interaction: discord.Interaction,
    name: app_commands.Range[str, 1, 100],
    channel_type: app_commands.Choice[str],
    topic: app_commands.Range[str, 1, 1024] | None = None,
    confirm: bool = False,
) -> None:
    guild = interaction.guild
    if guild is None:
        return
    bot = cast("AdminBot", interaction.client)
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        result = await bot.course_service.add_bulk_channel(
            guild,
            name=name,
            channel_type=channel_type.value,
            topic=topic,
            confirm=confirm,
            requested_by=interaction.user.id,
        )
    except CourseServiceError as error:
        await interaction.edit_original_response(content=f"❌ {error}")
        return

    heading = (
        "✅ Bulk channel operation completed"
        if result.confirmed
        else "**Bulk channel addition preview**"
    )
    lines = [
        heading,
        f"Channel: **{result.name}** ({result.channel_type})",
        f"Managed courses: {result.course_count}",
    ]
    if result.confirmed:
        lines.append(f"Created now: {len(result.created)}")
    else:
        lines.append(f"Would create: {len(result.create)}")
    _append_sync_section(lines, "Courses to create in", result.create)
    _append_sync_section(lines, "Courses to reconnect", result.reconnect)
    _append_sync_section(lines, "Already present", result.already_present)
    _append_sync_section(lines, "Created", result.created)
    _append_sync_section(lines, "Skipped conflicts", result.conflicts, warning=True)
    if not result.confirmed:
        lines.extend(
            (
                "",
                "Nothing was changed. Run the same command with `confirm:true` "
                "to create and remember this channel for current and future courses.",
            )
        )
    await interaction.edit_original_response(
        content=_fit_discord_message("\n".join(lines))
    )


@course_channel_group.command(
    name="delete-all", description="Delete one tracked shared channel from every course."
)
@app_commands.describe(
    name="Previously added shared channel name",
    confirm="Set true after reviewing the deletion preview",
)
async def delete_all_channel(
    interaction: discord.Interaction,
    name: app_commands.Range[str, 1, 100],
    confirm: bool = False,
) -> None:
    guild = interaction.guild
    if guild is None:
        return
    bot = cast("AdminBot", interaction.client)
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        result = await bot.course_service.delete_bulk_channel(
            guild,
            name=name,
            confirm=confirm,
            requested_by=interaction.user.id,
        )
    except CourseServiceError as error:
        await interaction.edit_original_response(content=f"❌ {error}")
        return

    if not result.confirmed:
        lines = [
            "**Bulk channel deletion preview**",
            f"Channel: **{result.definition.name}** ({result.definition.channel_type})",
            f"Tracked live channels to delete: {len(result.live)}",
            f"Already missing tracked channels: {len(result.missing)}",
        ]
        _append_sync_section(lines, "Courses affected", result.live)
        lines.extend(
            (
                "",
                "Nothing was deleted. Run the same command with `confirm:true`. "
                "Only stable IDs previously tracked by `add-all` will be deleted.",
            )
        )
    else:
        icon = "✅" if result.definition_removed else "⚠️"
        lines = [
            f"{icon} Bulk channel deletion "
            f"{'completed' if result.definition_removed else 'incomplete'}",
            f"Channel: **{result.definition.name}**",
        ]
        _append_sync_section(lines, "Deleted from courses", result.deleted)
        _append_sync_section(lines, "Already missing", result.missing)
        _append_sync_section(lines, "Failures; retry safely", result.failures, warning=True)
    await interaction.edit_original_response(
        content=_fit_discord_message("\n".join(lines))
    )


@course_channel_group.command(
    name="list", description="List channels shared across managed courses."
)
async def list_shared_channels(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if guild is None:
        return
    bot = cast("AdminBot", interaction.client)
    definitions = bot.database.list_bulk_channel_definitions(guild.id)
    if not definitions:
        message = "No shared course channels are managed."
    else:
        lines = ["**Shared course channels**"]
        for definition in definitions[:50]:
            tracked = len(bot.database.list_bulk_channel_bindings(definition.id))
            topic = f" — {definition.topic}" if definition.topic else ""
            lines.append(
                f"- **{definition.name}** ({definition.channel_type}), "
                f"tracked in {tracked} course(s){topic}"
            )
        if len(definitions) > 50:
            lines.append(f"- … and {len(definitions) - 50} more")
        message = "\n".join(lines)
    await interaction.response.send_message(
        _fit_discord_message(message), ephemeral=True
    )


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
