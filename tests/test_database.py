from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from discord_bot.database import Database, ObservedChannel


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.database = Database(Path(self.temporary_directory.name) / "bot.db")
        self.database.initialize()

    def test_semester_names_are_unique_per_guild(self) -> None:
        first = self.database.create_semester(1, "2026-fall")
        duplicate = self.database.create_semester(1, "  2026-FALL ")
        other_guild = self.database.create_semester(2, "2026-fall")

        self.assertIsNotNone(first)
        self.assertIsNone(duplicate)
        self.assertIsNotNone(other_guild)

    def test_persists_course_resource_ids(self) -> None:
        semester = self.database.create_semester(1, "2026-fall")
        self.assertIsNotNone(semester)
        assert semester is not None

        course = self.database.begin_course(
            1, semester, "Machine Learning", "ML01"
        )
        self.assertIsNotNone(course)
        assert course is not None
        self.database.set_course_category(course.id, 100)
        self.database.add_course_channel(course.id, "course_chat", 101, "text")
        self.database.mark_course_active(course.id)

        loaded = self.database.get_course(1, "machine learning")
        channels = self.database.get_course_channels(course.id)
        counts = self.database.counts(1)

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.category_id, 100)
        self.assertEqual(loaded.status, "active")
        self.assertEqual(channels[0].discord_channel_id, 101)
        self.assertEqual(counts, (1, 1))

    def test_saves_latest_discord_observation(self) -> None:
        semester = self.database.create_semester(1, "2026-fall")
        assert semester is not None
        course = self.database.begin_course(1, semester, "Databases", None)
        assert course is not None

        self.database.save_course_sync_snapshot(
            course.id,
            category_present=True,
            category_name="Databases and SQL",
            channels=[
                ObservedChannel(201, "sql-chat", "text", 200, "course_chat"),
                ObservedChannel(202, "exam-room", "voice", 200, None),
            ],
        )

        observed = self.database.get_course_sync_channels(course.id)
        self.assertEqual([channel.discord_channel_id for channel in observed], [202, 201])
        self.assertEqual(observed[0].template_key, None)
        self.assertEqual(observed[1].name, "sql-chat")
