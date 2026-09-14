from __future__ import annotations

import unittest

from discord_bot.commands.sync_output import format_sync_results
from discord_bot.course_service import CourseSyncResult
from discord_bot.database import Course


class SyncOutputTests(unittest.TestCase):
    def test_formats_one_course_with_full_details(self) -> None:
        message = format_sync_results([self._result("Machine Learning")], scope="ELTE")

        self.assertIn("No Discord resources were modified.", message)
        self.assertIn("University: ELTE", message)
        self.assertIn("Semester: 2026-fall", message)

    def test_formats_multiple_courses_as_hierarchy_summary(self) -> None:
        message = format_sync_results(
            [self._result("Machine Learning"), self._result("Data Mining")],
            scope="the managed server",
        )

        self.assertIn("2 course(s) in the managed server", message)
        self.assertIn("ELTE → 2026-fall → Machine Learning", message)
        self.assertIn("ELTE → 2026-fall → Data Mining", message)

    @staticmethod
    def _result(name: str) -> CourseSyncResult:
        course = Course(
            id=1,
            guild_id=1,
            university_id=1,
            university_name="ELTE",
            semester_id=1,
            semester_name="2026-fall",
            name=name,
            code=None,
            category_id=100,
            status="active",
        )
        return CourseSyncResult(
            course=course,
            category_name=f"ELTE · 2026-fall · {name}",
            category_issue=None,
            category_rebound=False,
            present_count=3,
            accepted_changes=(),
            rebound=(),
            missing=(),
            ambiguous=(),
            additional=(),
        )
