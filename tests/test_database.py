from __future__ import annotations

import sqlite3
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

    def test_only_empty_semesters_can_be_deleted(self) -> None:
        semester = self.database.create_semester(1, "2026-fall")
        assert semester is not None
        course = self.database.begin_course(1, semester, "Databases", None)
        assert course is not None

        self.assertFalse(self.database.delete_semester(semester.id))
        self.assertTrue(self.database.delete_course(course.id))
        self.assertTrue(self.database.delete_semester(semester.id))

    def test_upgrades_existing_database_without_losing_semesters(self) -> None:
        path = Path(self.temporary_directory.name) / "old.db"
        old = sqlite3.connect(path)
        old.executescript(
            """
            CREATE TABLE schema_metadata (version INTEGER NOT NULL);
            INSERT INTO schema_metadata (version) VALUES (2);
            CREATE TABLE semesters (
                id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (guild_id, normalized_name)
            );
            INSERT INTO semesters (guild_id, name, normalized_name)
            VALUES (1, '2026-fall', '2026-fall');
            """
        )
        old.commit()
        old.close()

        database = Database(path)
        database.initialize()

        self.assertIsNotNone(database.get_semester(1, "2026-fall"))
        upgraded = sqlite3.connect(path)
        version = upgraded.execute(
            "SELECT version FROM schema_metadata"
        ).fetchone()[0]
        tables = {
            row[0]
            for row in upgraded.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        upgraded.close()
        self.assertEqual(version, 3)
        self.assertIn("bulk_channel_definitions", tables)
