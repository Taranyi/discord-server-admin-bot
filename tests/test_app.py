from __future__ import annotations

import logging
import unittest
from types import SimpleNamespace
from typing import cast

import discord
from discord import app_commands

from discord_bot.app import AdminBot
from discord_bot.config import Settings


class AdminBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_registers_status_command_with_minimal_intents(self) -> None:
        bot = AdminBot(
            Settings(
                discord_token="not-used",
                discord_guild_id=None,
                command_sync="off",
                log_level=logging.INFO,
            )
        )
        self.addAsyncCleanup(bot.close)

        await bot.setup_hook()

        self.assertTrue(bot.intents.guilds)
        self.assertFalse(bot.intents.members)
        self.assertFalse(bot.intents.message_content)
        self.assertFalse(bot.intents.presences)

        commands = bot.tree.get_commands()
        self.assertEqual([command.name for command in commands], ["server"])
        self.assertEqual(
            [command.name for command in commands[0].commands], ["status"]
        )
        self.assertTrue(commands[0].default_permissions.administrator)

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

    @staticmethod
    def _create_bot() -> AdminBot:
        return AdminBot(
            Settings(
                discord_token="not-used",
                discord_guild_id=None,
                command_sync="off",
                log_level=logging.INFO,
            )
        )
