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
        category = MagicMock(spec=discord.CategoryChannel)
        category.id = 100
        category.name = "Machine Learning"
        category.channels = []

        text_channels = []
        for channel_id, name in ((101, "course-chat"), (102, "materials")):
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
        self.assertEqual(len(self.database.get_course_channels(result.course.id)), 4)
        forum_tags = guild.create_forum.await_args.kwargs["available_tags"]
        self.assertEqual(forum_tags[0].name, "Question")
        self.assertEqual(forum_tags[-1].name, "Other")

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
            ("materials", 102, "text"),
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

        replacement_materials = MagicMock(spec=discord.TextChannel)
        replacement_materials.id = 202
        replacement_materials.name = "materials"
        replacement_materials.category_id = 100

        forum = MagicMock(spec=discord.ForumChannel)
        forum.id = 103
        forum.name = "discussions"
        forum.category_id = 100

        voice = MagicMock(spec=discord.VoiceChannel)
        voice.id = 104
        voice.name = "study-room"
        voice.category_id = 100

        extra = MagicMock(spec=discord.TextChannel)
        extra.id = 205
        extra.name = "exam-help"
        extra.category_id = 100
        category.channels = [replacement_materials, forum, voice, extra]

        channels = {
            100: category,
            101: moved_chat,
            102: None,
            103: forum,
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
        self.assertEqual(result.rebound, ("materials → #materials",))
        self.assertEqual(result.additional, ("#exam-help (text)",))
        self.assertFalse(result.missing)
        self.assertEqual(result.present_count, 5)

        managed = {
            channel.template_key: channel
            for channel in self.database.get_course_channels(course.id)
        }
        self.assertEqual(managed["materials"].discord_channel_id, 202)
        observed = self.database.get_course_sync_channels(course.id)
        self.assertEqual(len(observed), 5)

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

        materials = MagicMock(spec=discord.TextChannel)
        materials.id = 102
        materials.name = "materials"
        materials.category_id = 100
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
                create_text_channel=AsyncMock(return_value=materials),
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
        self.assertEqual(len(self.database.get_course_channels(course.id)), 4)
