from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Semester:
    id: int
    guild_id: int
    name: str


@dataclass(frozen=True, slots=True)
class Course:
    id: int
    guild_id: int
    semester_id: int
    semester_name: str
    name: str
    code: str | None
    category_id: int | None
    status: str


@dataclass(frozen=True, slots=True)
class ManagedChannel:
    template_key: str
    discord_channel_id: int
    channel_type: str


@dataclass(frozen=True, slots=True)
class ObservedChannel:
    discord_channel_id: int
    name: str
    channel_type: str
    category_id: int | None
    template_key: str | None


@dataclass(frozen=True, slots=True)
class BulkChannelDefinition:
    id: int
    guild_id: int
    name: str
    channel_type: str
    topic: str | None


@dataclass(frozen=True, slots=True)
class BulkChannelBinding:
    definition_id: int
    course_id: int
    discord_channel_id: int


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        database = self._connect()
        try:
            database.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_metadata (
                    version INTEGER NOT NULL
                );

                INSERT INTO schema_metadata (version)
                SELECT 3
                WHERE NOT EXISTS (SELECT 1 FROM schema_metadata);

                CREATE TABLE IF NOT EXISTS semesters (
                    id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (guild_id, normalized_name)
                );

                CREATE TABLE IF NOT EXISTS courses (
                    id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    semester_id INTEGER NOT NULL REFERENCES semesters(id),
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    code TEXT,
                    discord_category_id INTEGER UNIQUE,
                    status TEXT NOT NULL DEFAULT 'creating'
                        CHECK (status IN ('creating', 'active')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (guild_id, normalized_name)
                );

                CREATE TABLE IF NOT EXISTS course_channels (
                    id INTEGER PRIMARY KEY,
                    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    discord_channel_id INTEGER NOT NULL UNIQUE,
                    template_key TEXT NOT NULL,
                    channel_type TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (course_id, template_key)
                );

                CREATE TABLE IF NOT EXISTS course_sync_snapshots (
                    course_id INTEGER PRIMARY KEY
                        REFERENCES courses(id) ON DELETE CASCADE,
                    category_present INTEGER NOT NULL,
                    category_name TEXT,
                    synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS course_sync_channels (
                    course_id INTEGER NOT NULL
                        REFERENCES courses(id) ON DELETE CASCADE,
                    discord_channel_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    channel_type TEXT NOT NULL,
                    category_id INTEGER,
                    template_key TEXT,
                    observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (course_id, discord_channel_id)
                );

                CREATE TABLE IF NOT EXISTS bulk_channel_definitions (
                    id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    channel_type TEXT NOT NULL
                        CHECK (channel_type IN ('text', 'forum', 'voice')),
                    topic TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (guild_id, normalized_name)
                );

                CREATE TABLE IF NOT EXISTS bulk_course_channels (
                    definition_id INTEGER NOT NULL
                        REFERENCES bulk_channel_definitions(id) ON DELETE CASCADE,
                    course_id INTEGER NOT NULL
                        REFERENCES courses(id) ON DELETE CASCADE,
                    discord_channel_id INTEGER NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (definition_id, course_id)
                );

                UPDATE schema_metadata SET version = 3 WHERE version < 3;
                """
            )
            database.commit()
        finally:
            database.close()

    def create_semester(self, guild_id: int, name: str) -> Semester | None:
        database = self._connect()
        try:
            try:
                cursor = database.execute(
                    """
                    INSERT INTO semesters (guild_id, name, normalized_name)
                    VALUES (?, ?, ?)
                    """,
                    (guild_id, name, normalize_name(name)),
                )
            except sqlite3.IntegrityError:
                return None
            database.commit()
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return the new semester ID")
            return Semester(id=cursor.lastrowid, guild_id=guild_id, name=name)
        finally:
            database.close()

    def get_semester(self, guild_id: int, name: str) -> Semester | None:
        database = self._connect()
        try:
            row = database.execute(
                """
                SELECT id, guild_id, name FROM semesters
                WHERE guild_id = ? AND normalized_name = ?
                """,
                (guild_id, normalize_name(name)),
            ).fetchone()
            return Semester(**dict(row)) if row is not None else None
        finally:
            database.close()

    def list_semesters(self, guild_id: int) -> list[Semester]:
        database = self._connect()
        try:
            rows = database.execute(
                """
                SELECT id, guild_id, name FROM semesters
                WHERE guild_id = ? ORDER BY name COLLATE NOCASE
                """,
                (guild_id,),
            ).fetchall()
            return [Semester(**dict(row)) for row in rows]
        finally:
            database.close()

    def begin_course(
        self, guild_id: int, semester: Semester, name: str, code: str | None
    ) -> Course | None:
        database = self._connect()
        try:
            try:
                cursor = database.execute(
                    """
                    INSERT INTO courses (
                        guild_id, semester_id, name, normalized_name, code
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (guild_id, semester.id, name, normalize_name(name), code),
                )
            except sqlite3.IntegrityError:
                return None
            database.commit()
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return the new course ID")
            return Course(
                id=cursor.lastrowid,
                guild_id=guild_id,
                semester_id=semester.id,
                semester_name=semester.name,
                name=name,
                code=code,
                category_id=None,
                status="creating",
            )
        finally:
            database.close()

    def get_course(self, guild_id: int, name: str) -> Course | None:
        database = self._connect()
        try:
            row = database.execute(
                """
                SELECT c.id, c.guild_id, c.semester_id, s.name AS semester_name,
                       c.name, c.code, c.discord_category_id AS category_id, c.status
                FROM courses AS c
                JOIN semesters AS s ON s.id = c.semester_id
                WHERE c.guild_id = ? AND c.normalized_name = ?
                """,
                (guild_id, normalize_name(name)),
            ).fetchone()
            return Course(**dict(row)) if row is not None else None
        finally:
            database.close()

    def list_courses(
        self, guild_id: int, semester_name: str | None = None
    ) -> list[Course]:
        database = self._connect()
        try:
            parameters: list[object] = [guild_id]
            filter_sql = ""
            if semester_name is not None:
                filter_sql = " AND s.normalized_name = ?"
                parameters.append(normalize_name(semester_name))
            rows = database.execute(
                f"""
                SELECT c.id, c.guild_id, c.semester_id, s.name AS semester_name,
                       c.name, c.code, c.discord_category_id AS category_id, c.status
                FROM courses AS c
                JOIN semesters AS s ON s.id = c.semester_id
                WHERE c.guild_id = ?{filter_sql}
                ORDER BY s.name COLLATE NOCASE, c.name COLLATE NOCASE
                """,
                parameters,
            ).fetchall()
            return [Course(**dict(row)) for row in rows]
        finally:
            database.close()

    def set_course_category(self, course_id: int, category_id: int) -> None:
        self._execute_write(
            """
            UPDATE courses SET discord_category_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (category_id, course_id),
        )

    def add_course_channel(
        self, course_id: int, template_key: str, channel_id: int, channel_type: str
    ) -> None:
        self._execute_write(
            """
            INSERT INTO course_channels (
                course_id, discord_channel_id, template_key, channel_type
            ) VALUES (?, ?, ?, ?)
            """,
            (course_id, channel_id, template_key, channel_type),
        )

    def rebind_course_channel(
        self, course_id: int, template_key: str, channel_id: int, channel_type: str
    ) -> None:
        self._execute_write(
            """
            UPDATE course_channels
            SET discord_channel_id = ?, channel_type = ?
            WHERE course_id = ? AND template_key = ?
            """,
            (channel_id, channel_type, course_id, template_key),
        )

    def get_course_channels(self, course_id: int) -> list[ManagedChannel]:
        database = self._connect()
        try:
            rows = database.execute(
                """
                SELECT template_key, discord_channel_id, channel_type
                FROM course_channels WHERE course_id = ? ORDER BY id
                """,
                (course_id,),
            ).fetchall()
            return [ManagedChannel(**dict(row)) for row in rows]
        finally:
            database.close()

    def mark_course_active(self, course_id: int) -> None:
        self._execute_write(
            """
            UPDATE courses SET status = 'active', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (course_id,),
        )

    def save_course_sync_snapshot(
        self,
        course_id: int,
        *,
        category_present: bool,
        category_name: str | None,
        channels: list[ObservedChannel],
    ) -> None:
        database = self._connect()
        try:
            database.execute(
                """
                INSERT INTO course_sync_snapshots (
                    course_id, category_present, category_name, synced_at
                ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(course_id) DO UPDATE SET
                    category_present = excluded.category_present,
                    category_name = excluded.category_name,
                    synced_at = CURRENT_TIMESTAMP
                """,
                (course_id, int(category_present), category_name),
            )
            database.execute(
                "DELETE FROM course_sync_channels WHERE course_id = ?", (course_id,)
            )
            database.executemany(
                """
                INSERT INTO course_sync_channels (
                    course_id, discord_channel_id, name, channel_type,
                    category_id, template_key
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        course_id,
                        channel.discord_channel_id,
                        channel.name,
                        channel.channel_type,
                        channel.category_id,
                        channel.template_key,
                    )
                    for channel in channels
                ],
            )
            database.commit()
        finally:
            database.close()

    def get_course_sync_channels(self, course_id: int) -> list[ObservedChannel]:
        database = self._connect()
        try:
            rows = database.execute(
                """
                SELECT discord_channel_id, name, channel_type, category_id,
                       template_key
                FROM course_sync_channels
                WHERE course_id = ? ORDER BY name COLLATE NOCASE
                """,
                (course_id,),
            ).fetchall()
            return [ObservedChannel(**dict(row)) for row in rows]
        finally:
            database.close()

    def create_bulk_channel_definition(
        self, guild_id: int, name: str, channel_type: str, topic: str | None
    ) -> BulkChannelDefinition | None:
        database = self._connect()
        try:
            try:
                cursor = database.execute(
                    """
                    INSERT INTO bulk_channel_definitions (
                        guild_id, name, normalized_name, channel_type, topic
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (guild_id, name, normalize_name(name), channel_type, topic),
                )
            except sqlite3.IntegrityError:
                return None
            database.commit()
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return the channel definition ID")
            return BulkChannelDefinition(
                id=cursor.lastrowid,
                guild_id=guild_id,
                name=name,
                channel_type=channel_type,
                topic=topic,
            )
        finally:
            database.close()

    def get_bulk_channel_definition(
        self, guild_id: int, name: str
    ) -> BulkChannelDefinition | None:
        database = self._connect()
        try:
            row = database.execute(
                """
                SELECT id, guild_id, name, channel_type, topic
                FROM bulk_channel_definitions
                WHERE guild_id = ? AND normalized_name = ?
                """,
                (guild_id, normalize_name(name)),
            ).fetchone()
            return BulkChannelDefinition(**dict(row)) if row is not None else None
        finally:
            database.close()

    def list_bulk_channel_definitions(
        self, guild_id: int
    ) -> list[BulkChannelDefinition]:
        database = self._connect()
        try:
            rows = database.execute(
                """
                SELECT id, guild_id, name, channel_type, topic
                FROM bulk_channel_definitions
                WHERE guild_id = ? ORDER BY name COLLATE NOCASE
                """,
                (guild_id,),
            ).fetchall()
            return [BulkChannelDefinition(**dict(row)) for row in rows]
        finally:
            database.close()

    def add_bulk_channel_binding(
        self, definition_id: int, course_id: int, channel_id: int
    ) -> None:
        self._execute_write(
            """
            INSERT INTO bulk_course_channels (
                definition_id, course_id, discord_channel_id
            ) VALUES (?, ?, ?)
            """,
            (definition_id, course_id, channel_id),
        )

    def rebind_bulk_channel(
        self, definition_id: int, course_id: int, channel_id: int
    ) -> None:
        self._execute_write(
            """
            UPDATE bulk_course_channels SET discord_channel_id = ?
            WHERE definition_id = ? AND course_id = ?
            """,
            (channel_id, definition_id, course_id),
        )

    def get_bulk_channel_binding(
        self, definition_id: int, course_id: int
    ) -> BulkChannelBinding | None:
        database = self._connect()
        try:
            row = database.execute(
                """
                SELECT definition_id, course_id, discord_channel_id
                FROM bulk_course_channels
                WHERE definition_id = ? AND course_id = ?
                """,
                (definition_id, course_id),
            ).fetchone()
            return BulkChannelBinding(**dict(row)) if row is not None else None
        finally:
            database.close()

    def list_bulk_channel_bindings_for_course(
        self, course_id: int
    ) -> list[BulkChannelBinding]:
        database = self._connect()
        try:
            rows = database.execute(
                """
                SELECT definition_id, course_id, discord_channel_id
                FROM bulk_course_channels WHERE course_id = ?
                """,
                (course_id,),
            ).fetchall()
            return [BulkChannelBinding(**dict(row)) for row in rows]
        finally:
            database.close()

    def list_bulk_channel_bindings(
        self, definition_id: int
    ) -> list[BulkChannelBinding]:
        database = self._connect()
        try:
            rows = database.execute(
                """
                SELECT definition_id, course_id, discord_channel_id
                FROM bulk_course_channels WHERE definition_id = ?
                """,
                (definition_id,),
            ).fetchall()
            return [BulkChannelBinding(**dict(row)) for row in rows]
        finally:
            database.close()

    def remove_bulk_channel_binding(self, definition_id: int, course_id: int) -> None:
        self._execute_write(
            """
            DELETE FROM bulk_course_channels
            WHERE definition_id = ? AND course_id = ?
            """,
            (definition_id, course_id),
        )

    def delete_bulk_channel_definition(self, definition_id: int) -> bool:
        database = self._connect()
        try:
            cursor = database.execute(
                """
                DELETE FROM bulk_channel_definitions
                WHERE id = ? AND NOT EXISTS (
                    SELECT 1 FROM bulk_course_channels WHERE definition_id = ?
                )
                """,
                (definition_id, definition_id),
            )
            database.commit()
            return cursor.rowcount == 1
        finally:
            database.close()

    def count_courses_in_semester(self, semester_id: int) -> int:
        database = self._connect()
        try:
            row = database.execute(
                "SELECT COUNT(*) FROM courses WHERE semester_id = ?", (semester_id,)
            ).fetchone()
            return int(row[0])
        finally:
            database.close()

    def delete_course(self, course_id: int) -> bool:
        database = self._connect()
        try:
            cursor = database.execute("DELETE FROM courses WHERE id = ?", (course_id,))
            database.commit()
            return cursor.rowcount == 1
        finally:
            database.close()

    def delete_semester(self, semester_id: int) -> bool:
        database = self._connect()
        try:
            cursor = database.execute(
                """
                DELETE FROM semesters
                WHERE id = ? AND NOT EXISTS (
                    SELECT 1 FROM courses WHERE semester_id = ?
                )
                """,
                (semester_id, semester_id),
            )
            database.commit()
            return cursor.rowcount == 1
        finally:
            database.close()

    def counts(self, guild_id: int) -> tuple[int, int]:
        database = self._connect()
        try:
            semester_count = database.execute(
                "SELECT COUNT(*) FROM semesters WHERE guild_id = ?", (guild_id,)
            ).fetchone()[0]
            course_count = database.execute(
                "SELECT COUNT(*) FROM courses WHERE guild_id = ?", (guild_id,)
            ).fetchone()[0]
            return int(semester_count), int(course_count)
        finally:
            database.close()

    def _execute_write(self, sql: str, parameters: tuple[object, ...]) -> None:
        database = self._connect()
        try:
            database.execute(sql, parameters)
            database.commit()
        finally:
            database.close()

    def _connect(self) -> sqlite3.Connection:
        database = sqlite3.connect(self.path)
        database.row_factory = sqlite3.Row
        database.execute("PRAGMA foreign_keys = ON")
        return database


def normalize_name(value: str) -> str:
    return " ".join(value.split()).casefold()
