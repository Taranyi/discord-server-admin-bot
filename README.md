# Discord Bot

An on-demand Discord server administration tool for an MSc student community.
It is intended to be started locally when an administrator needs it and stopped
after the work is complete. Discord resources created later by the bot remain in
the server while it is offline.

The current foundation provides:

- environment-based configuration;
- minimal, non-privileged Gateway intents;
- controlled guild or global application-command synchronization;
- safe local logging;
- centralized administrator-only authorization for every command;
- an ephemeral `/server status` command.

Course, semester, role, synchronization, and database features have not been
implemented yet.

Hungarian documentation: [README.hu.md](README.hu.md)

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- a Discord application with a bot user
- a separate test server for development is strongly recommended

## Discord application setup

1. Create an application in the Discord Developer Portal.
2. On the **Installation** page, enable **Guild Install**.
3. Add the `applications.commands` and `bot` install scopes.
4. No privileged Gateway intents are required by the current version.
5. Install the app in a test server. The current status command does not require
   broad bot permissions.
6. Bot commands can currently be used only by members with Discord's
   **Administrator** permission. This restriction is declared on the command
   group and is also enforced centrally at runtime.

Do not grant `Administrator` to the bot by default. Future management features
will document their exact required permissions when they are added.

The user restriction and the bot's own permissions are separate: administrators
may run commands, while the bot still receives only the permissions its current
features actually require.

## Installation

Create the project-local `.venv` and install the locked dependencies into it:

```bash
uv sync
cp .env.example .env
```

Edit `.env` and set your bot token and test server ID:

```dotenv
DISCORD_TOKEN=your_real_bot_token
DISCORD_GUILD_ID=123456789012345678
DISCORD_COMMAND_SYNC=guild
LOG_LEVEL=INFO
```

Never commit `.env` or expose the bot token. Rotate the token immediately if it
is leaked.

## Running

```bash
./run.sh
```

Use `/server status` in the configured Discord server. Stop the bot with
`Ctrl+C` when the administration session is over.

## Command synchronization

`DISCORD_COMMAND_SYNC` makes synchronization deliberate:

- `guild`: copy and synchronize commands to `DISCORD_GUILD_ID`; use this during
  development because guild commands update quickly;
- `global`: synchronize global commands for installed servers;
- `off`: connect without modifying registered commands.

After the commands are registered, setting the value to `off` avoids an
unnecessary synchronization on every local start.

## Tests

```bash
uv run python -m unittest discover -s tests
```

## Project context

Long-term product and engineering context lives in
[docs/project-context.md](docs/project-context.md). It provides direction, not a
fixed feature checklist.
