from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import discord
from discord import app_commands

from discord_bot.app import AdminBot
from discord_bot.config import Settings
from discord_bot.template import load_course_template


class AdminBotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)

    async def test_registers_status_command_with_minimal_intents(self) -> None:
        bot = self._create_bot()
        self.addAsyncCleanup(bot.close)

        await bot.setup_hook()

        self.assertTrue(bot.intents.guilds)
        self.assertFalse(bot.intents.members)
        self.assertFalse(bot.intents.message_content)
        self.assertFalse(bot.intents.presences)

        commands = bot.tree.get_commands()
        self.assertEqual(
            [command.name for command in commands], ["server", "semester", "course"]
        )
        self.assertEqual(
            [command.name for command in commands[0].commands], ["status"]
        )
        self.assertEqual(
            [command.name for command in commands[1].commands],
            ["create", "list", "delete"],
        )
        self.assertEqual(
            [command.name for command in commands[2].commands],
            ["channel", "create", "list", "info", "sync", "delete"],
        )
        channel_group = commands[2].commands[0]
        self.assertEqual(
            [command.name for command in channel_group.commands],
            ["add-all", "delete-all", "list"],
        )
        self.assertTrue(
            all(command.default_permissions.administrator for command in commands)
        )

    async def test_allows_administrator_interactions(self) -> None:
        bot = self._create_bot()
        self.addAsyncCleanup(bot.close)
        interaction = cast(
            discord.Interaction,
            SimpleNamespace(permissions=discord.Permissions(administrator=True)),
        )

        self.assertTrue(await bot.tree.interaction_check(interaction))

    async def test_rejects_non_administrator_interactions(self) -> None:
        bot = self._create_bot()
        self.addAsyncCleanup(bot.close)
        interaction = cast(
            discord.Interaction,
            SimpleNamespace(permissions=discord.Permissions.none()),
        )

        with self.assertRaises(app_commands.MissingPermissions):
            await bot.tree.interaction_check(interaction)

    def _create_bot(self) -> AdminBot:
        template_path = Path("config.yaml")
        return AdminBot(
            Settings(
                discord_token="not-used",
                discord_guild_id=None,
                command_sync="off",
                log_level=logging.INFO,
                course_template_path=template_path,
                database_path=Path(self.temporary_directory.name) / "bot.db",
            ),
            load_course_template(template_path),
        )
