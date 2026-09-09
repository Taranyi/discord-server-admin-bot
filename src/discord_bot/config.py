from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

CommandSyncMode = Literal["off", "guild", "global"]
_COMMAND_SYNC_MODES = {"off", "guild", "global"}


class ConfigError(ValueError):
    """Raised when required application configuration is invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str
    discord_guild_id: int | None
    command_sync: CommandSyncMode
    log_level: int
    course_template_path: Path
    database_path: Path


def load_settings(environment: Mapping[str, str] | None = None) -> Settings:
    values = os.environ if environment is None else environment

    token = values.get("DISCORD_TOKEN", "").strip()
    if not token or token == "your_bot_token_here":
        raise ConfigError("DISCORD_TOKEN is required.")

    guild_id = _parse_optional_snowflake(values.get("DISCORD_GUILD_ID"))

    raw_sync_mode = values.get("DISCORD_COMMAND_SYNC", "off").strip().lower()
    if raw_sync_mode not in _COMMAND_SYNC_MODES:
        allowed = ", ".join(sorted(_COMMAND_SYNC_MODES))
        raise ConfigError(f"DISCORD_COMMAND_SYNC must be one of: {allowed}.")
    command_sync = cast(CommandSyncMode, raw_sync_mode)

    if command_sync == "guild" and guild_id is None:
        raise ConfigError(
            "DISCORD_GUILD_ID is required when DISCORD_COMMAND_SYNC is guild."
        )

    raw_log_level = values.get("LOG_LEVEL", "INFO").strip().upper()
    log_level = logging.getLevelNamesMapping().get(raw_log_level)
    if not isinstance(log_level, int):
        raise ConfigError(f"Unsupported LOG_LEVEL: {raw_log_level!r}.")

    return Settings(
        discord_token=token,
        discord_guild_id=guild_id,
        command_sync=command_sync,
        log_level=log_level,
        course_template_path=Path(
            values.get("DISCORD_CONFIG_PATH", "config.yaml").strip()
            or "config.yaml"
        ),
        database_path=Path(
            values.get("DISCORD_DATABASE_PATH", "data/bot.db").strip()
            or "data/bot.db"
        ),
    )


def _parse_optional_snowflake(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None

    cleaned = value.strip()
    if not cleaned.isdecimal():
        raise ConfigError("DISCORD_GUILD_ID must contain digits only.")

    parsed = int(cleaned)
    if parsed <= 0:
        raise ConfigError("DISCORD_GUILD_ID must be greater than zero.")
    return parsed
