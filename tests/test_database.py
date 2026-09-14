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
        self.university = self.database.create_university(1, "ELTE")
        assert self.university is not None

    def test_university_names_are_unique_per_guild(self) -> None:
        duplicate = self.database.create_university(1, "  elte ")
        other_guild = self.database.create_university(2, "ELTE")

        self.assertIsNone(duplicate)
        self.assertIsNotNone(other_guild)

    def test_semester_names_are_unique_per_university(self) -> None:
        other_university = self.database.create_university(1, "BME")
        assert other_university is not None
        first = self.database.create_semester(1, self.university, "2026-fall")
        duplicate = self.database.create_semester(
            1, self.university, "  2026-FALL "
        )
        other_parent = self.database.create_semester(
            1, other_university, "2026-fall"
        )

        self.assertIsNotNone(first)
        self.assertIsNone(duplicate)
        self.assertIsNotNone(other_parent)

    def test_course_names_are_scoped_to_semester_and_can_be_ambiguous(self) -> None:
        fall = self.database.create_semester(1, self.university, "2026-fall")
        spring = self.database.create_semester(1, self.university, "2027-spring")
        assert fall is not None and spring is not None

        first = self.database.begin_course(1, fall, "Machine Learning", None)
        duplicate = self.database.begin_course(1, fall, "machine learning", None)
        later = self.database.begin_course(1, spring, "Machine Learning", None)

        self.assertIsNotNone(first)
        self.assertIsNone(duplicate)
        self.assertIsNotNone(later)
        self.assertIsNone(self.database.get_course(1, "Machine Learning"))
        matches = self.database.find_courses(1, "Machine Learning")
        self.assertEqual(len(matches), 2)
        resolved = self.database.get_course(
            1, "Machine Learning", "ELTE", "2027-spring"
        )
        self.assertIsNotNone(resolved)

    def test_moves_semester_and_only_deletes_empty_university(self) -> None:
        destination = self.database.create_university(1, "BME")
        semester = self.database.create_semester(
            1, self.university, "2026-fall"
        )
        assert destination is not None and semester is not None

        self.assertFalse(self.database.delete_university(self.university.id))
        self.assertTrue(self.database.move_semester(semester.id, destination))
        moved = self.database.get_semester(1, "2026-fall", "BME")
        self.assertIsNotNone(moved)
        self.assertTrue(self.database.delete_university(self.university.id))

    def test_persists_course_resource_ids(self) -> None:
        semester = self.database.create_semester(1, self.university, "2026-fall")
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
        self.assertEqual(counts, (1, 1, 1))

    def test_saves_latest_discord_observation(self) -> None:
        semester = self.database.create_semester(1, self.university, "2026-fall")
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
        semester = self.database.create_semester(1, self.university, "2026-fall")
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

        semester = database.get_semester(1, "2026-fall", "Unassigned")
        self.assertIsNotNone(semester)
        assert semester is not None
        self.assertEqual(semester.university_name, "Unassigned")
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
        self.assertEqual(version, 4)
        self.assertIn("bulk_channel_definitions", tables)
        self.assertIn("universities", tables)

    def test_v3_migration_preserves_courses_and_discord_ids(self) -> None:
        path = Path(self.temporary_directory.name) / "v3.db"
        old = sqlite3.connect(path)
        old.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE schema_metadata (version INTEGER NOT NULL);
            INSERT INTO schema_metadata (version) VALUES (3);
            CREATE TABLE semesters (
                id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (guild_id, normalized_name)
            );
            CREATE TABLE courses (
                id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                semester_id INTEGER NOT NULL REFERENCES semesters(id),
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                code TEXT,
                discord_category_id INTEGER UNIQUE,
                status TEXT NOT NULL DEFAULT 'creating',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (guild_id, normalized_name)
            );
            CREATE TABLE course_channels (
                id INTEGER PRIMARY KEY,
                course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                discord_channel_id INTEGER NOT NULL UNIQUE,
                template_key TEXT NOT NULL,
                channel_type TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (course_id, template_key)
            );
            INSERT INTO semesters (id, guild_id, name, normalized_name)
            VALUES (10, 1, '2026-fall', '2026-fall');
            INSERT INTO courses (
                id, guild_id, semester_id, name, normalized_name, code,
                discord_category_id, status
            ) VALUES (20, 1, 10, 'Machine Learning', 'machine learning',
                      'ML01', 100, 'active');
            INSERT INTO course_channels (
                course_id, discord_channel_id, template_key, channel_type
            ) VALUES (20, 101, 'course_chat', 'text');
            """
        )
        old.commit()
        old.close()

        migrated = Database(path)
        migrated.initialize()

        course = migrated.get_course(
            1, "Machine Learning", "Unassigned", "2026-fall"
        )
        self.assertIsNotNone(course)
        assert course is not None
        self.assertEqual(course.category_id, 100)
        self.assertEqual(course.university_name, "Unassigned")
        channels = migrated.get_course_channels(course.id)
        self.assertEqual(channels[0].discord_channel_id, 101)
