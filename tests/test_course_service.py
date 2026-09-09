from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import discord

from discord_bot.course_service import CourseService, CourseServiceError
from discord_bot.database import Database
from discord_bot.template import load_course_template


class CourseServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.database = Database(Path(self.temporary_directory.name) / "bot.db")
        self.database.initialize()
        self.semester = self.database.create_semester(1, "2026-fall")
        assert self.semester is not None
        self.service = CourseService(
            self.database, load_course_template(Path("config.yaml"))
        )

    async def test_creates_and_persists_complete_course_structure(self) -> None:
        bulk_definition = self.database.create_bulk_channel_definition(
            1, "announcements", "text", "Shared announcements"
        )
        assert bulk_definition is not None
        category = MagicMock(spec=discord.CategoryChannel)
        category.id = 100
        category.name = "Machine Learning"
        category.channels = []

        text_channels = []
        for channel_id, name in ((101, "course-chat"),):
            channel = MagicMock(spec=discord.TextChannel)
            channel.id = channel_id
            channel.name = name
            channel.category_id = category.id
            text_channels.append(channel)

        forum = MagicMock(spec=discord.ForumChannel)
        forum.id = 103
        forum.name = "discussions"
        forum.category_id = category.id
        voice = MagicMock(spec=discord.VoiceChannel)
        voice.id = 104
        voice.name = "study-room"
        voice.category_id = category.id
        announcements = MagicMock(spec=discord.TextChannel)
        announcements.id = 105
        announcements.name = "announcements"
        announcements.category_id = category.id
        text_channels.append(announcements)

        guild = cast(
            discord.Guild,
            SimpleNamespace(
                id=1,
                me=SimpleNamespace(
                    guild_permissions=discord.Permissions(manage_channels=True)
                ),
                features=["COMMUNITY"],
                categories=[],
                create_category=AsyncMock(return_value=category),
                create_text_channel=AsyncMock(side_effect=text_channels),
                create_forum=AsyncMock(return_value=forum),
                create_voice_channel=AsyncMock(return_value=voice),
                get_channel=MagicMock(return_value=None),
            ),
        )

        result = await self.service.create_course(
            guild,
            name="Machine Learning",
            semester_name="2026-fall",
            code="ML01",
            requested_by=42,
        )

        self.assertEqual(result.course.status, "active")
        self.assertEqual(result.course.category_id, 100)
        self.assertEqual(
            guild.create_category.await_args.args[0],
            "2026-fall · Machine Learning",
        )
        self.assertEqual(len(self.database.get_course_channels(result.course.id)), 3)
        binding = self.database.get_bulk_channel_binding(
            bulk_definition.id, result.course.id
        )
        self.assertIsNotNone(binding)
        assert binding is not None
        self.assertEqual(binding.discord_channel_id, 105)
        forum_tags = guild.create_forum.await_args.kwargs["available_tags"]
        self.assertEqual(forum_tags[0].name, "Question")
        self.assertEqual(forum_tags[-1].name, "Other")
        self.assertIn("Resource", [tag.name for tag in forum_tags])
        self.assertIn("Code", [tag.name for tag in forum_tags])
        self.assertIn("Idea", [tag.name for tag in forum_tags])

    async def test_requires_manage_channels_before_mutating(self) -> None:
        guild = cast(
            discord.Guild,
            SimpleNamespace(
                id=1,
                me=SimpleNamespace(guild_permissions=discord.Permissions.none()),
                features=["COMMUNITY"],
            ),
        )

        with self.assertRaisesRegex(CourseServiceError, "Manage Channels"):
            await self.service.create_course(
                guild,
                name="Machine Learning",
                semester_name="2026-fall",
                code=None,
                requested_by=42,
            )

        self.assertIsNone(self.database.get_course(1, "Machine Learning"))

    async def test_requires_community_before_mutating(self) -> None:
        guild = cast(
            discord.Guild,
            SimpleNamespace(
                id=1,
                me=SimpleNamespace(
                    guild_permissions=discord.Permissions(manage_channels=True)
                ),
                features=[],
            ),
        )

        with self.assertRaisesRegex(CourseServiceError, "Community"):
            await self.service.create_course(
                guild,
                name="Machine Learning",
                semester_name="2026-fall",
                code=None,
                requested_by=42,
            )

        self.assertIsNone(self.database.get_course(1, "Machine Learning"))

    async def test_sync_accepts_manual_changes_and_rebinds_unique_replacement(
        self,
    ) -> None:
        course = self.database.begin_course(
            1, self.semester, "Machine Learning", "ML01"
        )
        assert course is not None
        self.database.set_course_category(course.id, 100)
        for key, channel_id, channel_type in (
            ("course_chat", 101, "text"),
            ("discussions", 103, "forum"),
            ("study_room", 104, "voice"),
        ):
            self.database.add_course_channel(
                course.id, key, channel_id, channel_type
            )
        self.database.mark_course_active(course.id)

        category = MagicMock(spec=discord.CategoryChannel)
        category.id = 100
        category.name = "ML manually renamed"

        moved_chat = MagicMock(spec=discord.TextChannel)
        moved_chat.id = 101
        moved_chat.name = "general-chat"
        moved_chat.category_id = 999

        replacement_forum = MagicMock(spec=discord.ForumChannel)
        replacement_forum.id = 203
        replacement_forum.name = "discussions"
        replacement_forum.category_id = 100

        voice = MagicMock(spec=discord.VoiceChannel)
        voice.id = 104
        voice.name = "study-room"
        voice.category_id = 100

        extra = MagicMock(spec=discord.TextChannel)
        extra.id = 205
        extra.name = "exam-help"
        extra.category_id = 100
        category.channels = [replacement_forum, voice, extra]

        channels = {
            100: category,
            101: moved_chat,
            103: None,
            104: voice,
        }
        guild = cast(
            discord.Guild,
            SimpleNamespace(
                id=1,
                categories=[category],
                get_channel=MagicMock(side_effect=channels.get),
            ),
        )

        result = self.service.sync_courses(guild, name="Machine Learning")[0]

        self.assertEqual(result.category_name, "ML manually renamed")
        self.assertIn('category renamed to "ML manually renamed"', result.accepted_changes)
        self.assertIn('course_chat renamed to "general-chat"', result.accepted_changes)
        self.assertIn("course_chat moved outside the category", result.accepted_changes)
        self.assertEqual(result.rebound, ("discussions → #discussions",))
        self.assertEqual(result.additional, ("#exam-help (text)",))
        self.assertFalse(result.missing)
        self.assertEqual(result.present_count, 4)

        managed = {
            channel.template_key: channel
            for channel in self.database.get_course_channels(course.id)
        }
        self.assertEqual(managed["discussions"].discord_channel_id, 203)
        observed = self.database.get_course_sync_channels(course.id)
        self.assertEqual(len(observed), 4)

    async def test_resuming_creation_keeps_a_manually_moved_channel(self) -> None:
        course = self.database.begin_course(
            1, self.semester, "Machine Learning", "ML01"
        )
        assert course is not None
        self.database.set_course_category(course.id, 100)
        self.database.add_course_channel(course.id, "course_chat", 101, "text")

        category = MagicMock(spec=discord.CategoryChannel)
        category.id = 100
        category.name = "Machine Learning"
        category.channels = []

        moved_chat = MagicMock(spec=discord.TextChannel)
        moved_chat.id = 101
        moved_chat.name = "course-chat"
        moved_chat.category_id = 999

        forum = MagicMock(spec=discord.ForumChannel)
        forum.id = 103
        forum.name = "discussions"
        forum.category_id = 100
        voice = MagicMock(spec=discord.VoiceChannel)
        voice.id = 104
        voice.name = "study-room"
        voice.category_id = 100

        guild = cast(
            discord.Guild,
            SimpleNamespace(
                id=1,
                me=SimpleNamespace(
                    guild_permissions=discord.Permissions(manage_channels=True)
                ),
                features=["COMMUNITY"],
                categories=[category],
                get_channel=MagicMock(
                    side_effect=lambda channel_id: {
                        100: category,
                        101: moved_chat,
                    }.get(channel_id)
                ),
                create_forum=AsyncMock(return_value=forum),
                create_voice_channel=AsyncMock(return_value=voice),
            ),
        )

        result = await self.service.create_course(
            guild,
            name="Machine Learning",
            semester_name="2026-fall",
            code="ML01",
            requested_by=42,
        )

        self.assertTrue(result.resumed)
        self.assertEqual(result.course.status, "active")
        self.assertEqual(len(self.database.get_course_channels(course.id)), 3)

    async def test_bulk_add_previews_then_creates_and_tracks_channel(self) -> None:
        course = self.database.begin_course(1, self.semester, "Databases", None)
        assert course is not None
        self.database.set_course_category(course.id, 100)
        self.database.mark_course_active(course.id)

        category = MagicMock(spec=discord.CategoryChannel)
        category.id = 100
        category.name = "Databases"
        category.channels = []
        shared = MagicMock(spec=discord.TextChannel)
        shared.id = 201
        shared.name = "announcements"
        shared.category_id = 100
        create_text = AsyncMock(return_value=shared)
        guild = cast(
            discord.Guild,
            SimpleNamespace(
                id=1,
                me=SimpleNamespace(
                    guild_permissions=discord.Permissions(manage_channels=True)
                ),
                features=["COMMUNITY"],
                get_channel=MagicMock(
                    side_effect=lambda channel_id: category
                    if channel_id == 100
                    else None
                ),
                create_text_channel=create_text,
            ),
        )

        preview = await self.service.add_bulk_channel(
            guild,
            name="announcements",
            channel_type="text",
            topic="Shared announcements",
            confirm=False,
            requested_by=42,
        )
        self.assertEqual(preview.create, ("Databases",))
        create_text.assert_not_awaited()

        applied = await self.service.add_bulk_channel(
            guild,
            name="announcements",
            channel_type="text",
            topic="Shared announcements",
            confirm=True,
            requested_by=42,
        )
        self.assertEqual(applied.created, ("Databases",))
        definition = self.database.get_bulk_channel_definition(1, "announcements")
        assert definition is not None
        binding = self.database.get_bulk_channel_binding(definition.id, course.id)
        assert binding is not None
        self.assertEqual(binding.discord_channel_id, 201)

    async def test_bulk_add_rejects_a_base_template_channel_name(self) -> None:
        course = self.database.begin_course(1, self.semester, "Databases", None)
        assert course is not None
        self.database.set_course_category(course.id, 100)
        guild = cast(discord.Guild, SimpleNamespace(id=1))

        with self.assertRaisesRegex(CourseServiceError, "course template"):
            await self.service.add_bulk_channel(
                guild,
                name="course-chat",
                channel_type="text",
                topic=None,
                confirm=True,
                requested_by=42,
            )

        self.assertIsNone(self.database.get_bulk_channel_definition(1, "course-chat"))

    async def test_course_delete_keeps_untracked_channels_and_category(self) -> None:
        course = self.database.begin_course(1, self.semester, "Databases", None)
        assert course is not None
        self.database.set_course_category(course.id, 100)
        self.database.add_course_channel(course.id, "course_chat", 101, "text")
        self.database.mark_course_active(course.id)

        category = MagicMock(spec=discord.CategoryChannel)
        category.id = 100
        category.name = "Databases"
        category.delete = AsyncMock()
        managed = MagicMock(spec=discord.TextChannel)
        managed.id = 101
        managed.name = "course-chat"
        managed.category_id = 100
        managed.delete = AsyncMock()
        manual = MagicMock(spec=discord.TextChannel)
        manual.id = 199
        manual.name = "manual-project"
        manual.category_id = 100
        manual.delete = AsyncMock()
        category.channels = [managed, manual]
        guild = cast(
            discord.Guild,
            SimpleNamespace(
                id=1,
                me=SimpleNamespace(
                    guild_permissions=discord.Permissions(manage_channels=True)
                ),
                get_channel=MagicMock(
                    side_effect=lambda channel_id: {
                        100: category,
                        101: managed,
                    }.get(channel_id)
                ),
            ),
        )

        preview = await self.service.delete_course(
            guild, name="Databases", confirm=False, requested_by=42
        )
        self.assertEqual(len(preview.manual_kept), 1)
        managed.delete.assert_not_awaited()

        deleted = await self.service.delete_course(
            guild, name="Databases", confirm=True, requested_by=42
        )
        self.assertTrue(deleted.record_removed)
        managed.delete.assert_awaited_once()
        manual.delete.assert_not_awaited()
        category.delete.assert_not_awaited()
        self.assertIsNone(self.database.get_course(1, "Databases"))

    async def test_course_delete_removes_an_empty_managed_category(self) -> None:
        course = self.database.begin_course(1, self.semester, "Databases", None)
        assert course is not None
        self.database.set_course_category(course.id, 100)
        category = MagicMock(spec=discord.CategoryChannel)
        category.id = 100
        category.name = "Databases"
        category.channels = []
        category.delete = AsyncMock()
        guild = cast(
            discord.Guild,
            SimpleNamespace(
                id=1,
                me=SimpleNamespace(
                    guild_permissions=discord.Permissions(manage_channels=True)
                ),
                get_channel=MagicMock(
                    side_effect=lambda channel_id: category
                    if channel_id == 100
                    else None
                ),
            ),
        )

        result = await self.service.delete_course(
            guild, name="Databases", confirm=True, requested_by=42
        )

        self.assertTrue(result.record_removed)
        category.delete.assert_awaited_once()

    async def test_bulk_delete_targets_only_the_stored_discord_id(self) -> None:
        course = self.database.begin_course(1, self.semester, "Databases", None)
        assert course is not None
        definition = self.database.create_bulk_channel_definition(
            1, "announcements", "text", None
        )
        assert definition is not None
        self.database.add_bulk_channel_binding(definition.id, course.id, 201)

        tracked = MagicMock(spec=discord.TextChannel)
        tracked.id = 201
        tracked.name = "manually-renamed-announcements"
        tracked.delete = AsyncMock()
        same_name_manual = MagicMock(spec=discord.TextChannel)
        same_name_manual.id = 299
        same_name_manual.name = "announcements"
        same_name_manual.delete = AsyncMock()
        guild = cast(
            discord.Guild,
            SimpleNamespace(
                id=1,
                me=SimpleNamespace(
                    guild_permissions=discord.Permissions(manage_channels=True)
                ),
                get_channel=MagicMock(
                    side_effect=lambda channel_id: tracked
                    if channel_id == 201
                    else None
                ),
            ),
        )

        preview = await self.service.delete_bulk_channel(
            guild, name="announcements", confirm=False, requested_by=42
        )
        self.assertEqual(preview.live, ("Databases",))
        tracked.delete.assert_not_awaited()

        result = await self.service.delete_bulk_channel(
            guild, name="announcements", confirm=True, requested_by=42
        )
        self.assertTrue(result.definition_removed)
        tracked.delete.assert_awaited_once()
        same_name_manual.delete.assert_not_awaited()
        self.assertIsNone(
            self.database.get_bulk_channel_definition(1, "announcements")
        )

    async def test_sync_accepts_a_moved_and_renamed_shared_channel(self) -> None:
        course = self.database.begin_course(1, self.semester, "Databases", None)
        assert course is not None
        self.database.set_course_category(course.id, 100)
        definition = self.database.create_bulk_channel_definition(
            1, "announcements", "text", None
        )
        assert definition is not None
        self.database.add_bulk_channel_binding(definition.id, course.id, 201)

        category = MagicMock(spec=discord.CategoryChannel)
        category.id = 100
        category.name = "Databases"
        category.channels = []
        shared = MagicMock(spec=discord.TextChannel)
        shared.id = 201
        shared.name = "news"
        shared.category_id = 999
        guild = cast(
            discord.Guild,
            SimpleNamespace(
                id=1,
                categories=[category],
                get_channel=MagicMock(
                    side_effect=lambda channel_id: {
                        100: category,
                        201: shared,
                    }.get(channel_id)
                ),
            ),
        )

        result = self.service.sync_courses(guild, name="Databases")[0]

        self.assertIn(
            'shared:announcements renamed to "news"', result.accepted_changes
        )
        self.assertIn(
            "shared:announcements moved outside the category",
            result.accepted_changes,
        )
        observed = self.database.get_course_sync_channels(course.id)
        self.assertTrue(
            any(channel.template_key == "shared:announcements" for channel in observed)
        )
