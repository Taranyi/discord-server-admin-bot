from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from discord_bot.config import ConfigError
from discord_bot.template import load_course_template


class CourseTemplateTests(unittest.TestCase):
    def test_loads_default_template(self) -> None:
        template = load_course_template(Path("config.yaml"))

        self.assertEqual(template.category_name, "{course_name}")
        self.assertEqual(
            [channel.key for channel in template.channels],
            ["course_chat", "materials", "discussions", "study_room"],
        )
        self.assertTrue(template.requires_community)

    def test_rejects_unknown_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(
                """
schema_version: 1
course_template:
  category:
    name: "{unknown}"
  channels:
    chat:
      type: text
      name: chat
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "Unsupported placeholder"):
                load_course_template(path)

    def test_rejects_duplicate_yaml_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(
                """
schema_version: 1
schema_version: 1
course_template: {}
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "Duplicate configuration key"):
                load_course_template(path)
