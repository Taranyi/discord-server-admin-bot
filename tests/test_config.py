from __future__ import annotations

import logging
import unittest

from discord_bot.config import ConfigError, load_settings


class LoadSettingsTests(unittest.TestCase):
    def test_loads_valid_guild_development_settings(self) -> None:
        settings = load_settings(
            {
                "DISCORD_TOKEN": "secret",
                "DISCORD_GUILD_ID": "123456789012345678",
                "DISCORD_COMMAND_SYNC": "guild",
                "LOG_LEVEL": "debug",
            }
        )

        self.assertEqual(settings.discord_token, "secret")
        self.assertEqual(settings.discord_guild_id, 123456789012345678)
        self.assertEqual(settings.command_sync, "guild")
        self.assertEqual(settings.log_level, logging.DEBUG)

    def test_requires_token(self) -> None:
        with self.assertRaisesRegex(ConfigError, "DISCORD_TOKEN"):
            load_settings({})

    def test_guild_sync_requires_guild_id(self) -> None:
        with self.assertRaisesRegex(ConfigError, "DISCORD_GUILD_ID"):
            load_settings(
                {"DISCORD_TOKEN": "secret", "DISCORD_COMMAND_SYNC": "guild"}
            )

    def test_rejects_non_numeric_guild_id(self) -> None:
        with self.assertRaisesRegex(ConfigError, "digits only"):
            load_settings(
                {"DISCORD_TOKEN": "secret", "DISCORD_GUILD_ID": "not-a-number"}
            )

    def test_rejects_unknown_sync_mode(self) -> None:
        with self.assertRaisesRegex(ConfigError, "DISCORD_COMMAND_SYNC"):
            load_settings(
                {"DISCORD_TOKEN": "secret", "DISCORD_COMMAND_SYNC": "sometimes"}
            )


if __name__ == "__main__":
    unittest.main()
