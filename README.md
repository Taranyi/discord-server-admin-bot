# Discord Bot

An on-demand Discord server administration tool for an MSc student community.
It is intended to be started locally when an administrator needs it and stopped
after the work is complete. Discord resources created later by the bot remain in
the server while it is offline.

Continuous operation is not required for correctness. Administrators may edit
Discord while the bot is running or offline; after the next start,
synchronization uses the server's current state instead of relying on events the
process might have observed earlier.

The current MVP provides:

- environment-based configuration;
- minimal, non-privileged Gateway intents;
- controlled guild or global application-command synchronization;
- safe local logging;
- centralized administrator-only authorization for every command;
- YAML-based course templates;
- local SQLite managed state;
- semester creation and listing;
- course creation, listing, inspection, and Discord-authoritative synchronization;
- previewed deletion of managed courses and empty semesters;
- tracked shared-channel creation and deletion across every managed course;
- an ephemeral diagnostic `/server status` command.

Role management, archive/restore, bulk course import, and server-wide structure
management have not been implemented yet.

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
5. Give the bot **View Channels** and **Manage Channels**, then install it in a
   test server. Do not grant `Administrator` or `Manage Roles`.
6. Bot commands can currently be used only by members with Discord's
   **Administrator** permission. This restriction is declared on the command
   group and is also enforced centrally at runtime.
7. Enable Discord **Community** on the server before creating courses. The
   default course template includes a Forum Channel, which requires Community.

Do not grant `Administrator` to the bot. Future management features will
document additional permissions only when they are actually required.

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
DISCORD_CONFIG_PATH=config.yaml
DISCORD_DATABASE_PATH=data/bot.db
```

Never commit `.env` or expose the bot token. Rotate the token immediately if it
is leaked.

## Running

```bash
./run.sh
```

Stop the bot with `Ctrl+C` when the administration session is over. The SQLite
database is stored locally under `data/` and is intentionally ignored by Git.
On the first `0.4.0` start, an existing database is upgraded in place with the
new shared-channel tracking tables; existing semesters, courses, resource IDs,
and sync snapshots are retained. A backup of `data/bot.db` before the first
production start is still recommended.

## First-use workflow

1. Set `DISCORD_COMMAND_SYNC=guild` and start the bot once so Discord receives
   the commands.
2. Run `/server status` and verify that Community and Manage Channels both show
   `yes`.
3. Create a semester, for example `/semester create name:2026-fall`.
4. Create a course, for example `/course create name:Machine Learning
   semester:2026-fall code:ML01`.
5. Inspect it with `/course info name:Machine Learning`.
6. After making manual Discord changes, run `/course sync name:Machine Learning`,
   or omit `name` to synchronize all managed courses.
7. Preview destructive and bulk operations without confirmation first. Repeat
   with `confirm:true` only after reviewing the private result.

Course creation produces one category containing:

```text
Machine Learning
├── #course-chat
├── #materials
├── discussions (forum)
└── study-room (voice)
```

The forum tags, channel names, topics, and category format come from
`config.yaml`.

## Commands

All responses are ephemeral and all commands require the invoking member to
have Discord's `Administrator` permission.

- `/server status` — show connectivity, prerequisites, permissions, and managed
  object counts.
- `/semester create name:<name>` — create a local managed semester. This does not
  create a Discord category.
- `/semester list` — list the server's managed semesters.
- `/semester delete name:<name> [confirm:true]` — preview, then delete an empty
  local semester record. It refuses while the semester contains courses.
- `/course create name:<name> semester:<semester> [code:<code>]` — create and
  persist the configured Discord course structure.
- `/course list [semester:<semester>]` — list all managed courses or filter them
  by semester.
- `/course info name:<name>` — show stored Discord resource IDs and provisioning
  state.
- `/course sync [name:<name>]` — accept the current Discord state for one course,
  or all managed courses when `name` is omitted, and save a local observation
  without changing Discord.
- `/course delete name:<name> [confirm:true]` — preview, then delete the course's
  stable-ID-tracked resources and local record while preserving manual channels.
- `/course channel add-all name:<name> channel_type:<Text|Forum|Voice>
  [topic:<topic>] [confirm:true]` — preview, then create and track one shared
  channel in every managed course.
- `/course channel delete-all name:<name> [confirm:true]` — preview, then delete
  only the stable IDs previously tracked for that shared channel.
- `/course channel list` — list shared definitions and how many course channels
  are currently tracked for each.

Course and semester names are matched case-insensitively. Repeating a completed
create operation does not create a duplicate. If Discord fails partway through,
successful resource IDs remain stored and retrying the same command continues
the incomplete course. Unknown categories and channels are reported as
conflicts and are never deleted or silently adopted.

### What course synchronization does

Discord is authoritative for `/course sync`. The command works even when the
manual changes were made while the bot was offline: start the bot afterward and
run the command. It then:

- follows stable Discord IDs, so manual renames and moves of known categories
  and channels are accepted automatically;
- saves the names, types, category placement, and additional channels currently
  observed in each managed course;
- keeps additional manually created channels and records them in the snapshot,
  without assigning them a template role;
- reconnects a deleted-and-recreated category or template channel only when its
  expected name and type produce exactly one unambiguous match;
- reports missing, wrong-type, or ambiguous resources for administrator review;
- never creates, renames, moves, or deletes a Discord resource.

With no `name`, `/course sync` covers every course already managed by the bot.
It deliberately does not claim or inventory unrelated parts of the server.
An additional channel can safely coexist inside a managed course category, but
it does not automatically become one of the template's required channels.
The logical course name used in slash-command parameters remains unchanged when
its Discord category is manually renamed.

This guarantees safe coexistence, not automatic interpretation of every
possible manual edit. While the bot is offline no immediate synchronization
occurs. After it starts, `/course sync` either accepts a known-ID change,
reconnects one unique replacement, or reports the unresolved difference without
changing Discord. Run it after manual changes and before future lifecycle
operations.

The bot cannot automatically recover if its local database is lost, it is
removed from the server, its token is reset without updating `.env`, or its
visibility and required permissions are revoked. It also cannot safely guess
between multiple similar replacements. These cases produce a missing or
ambiguous result, or require manual setup; they do not authorize destructive
repair.

There are currently no archive, restore, or Discord-modifying synchronization
commands. Deletion exists only through the narrow, previewed commands below.

## Shared channels across all courses

Use this when every current and future managed course needs the same additional
channel. First request a preview:

```text
/course channel add-all name:announcements channel_type:Text topic:Shared announcements
```

The preview lists courses where the bot would create, reconnect, skip, or report
a conflict. Nothing changes yet. If it is correct, repeat with confirmation:

```text
/course channel add-all name:announcements channel_type:Text topic:Shared announcements confirm:true
```

The definition is stored in SQLite. Existing managed courses receive the
channel where their category is available, and later `/course create` operations
also include it. Repeating the command is safe: tracked live channels are not
duplicated. A same-name untracked or ambiguous channel is reported instead of
being silently adopted. A name reserved by the base course template is rejected.
Forum channels require Community; voice channels cannot have a topic.

Use `/course channel list` at any time to see the stored shared definitions.

To remove that tracked shared channel, preview and then confirm:

```text
/course channel delete-all name:announcements
/course channel delete-all name:announcements confirm:true
```

Deletion targets only Discord IDs stored for this shared definition, even if a
tracked channel was manually renamed or moved. A manually created same-name
channel is not selected. Successful mappings are removed as the operation
progresses; after a partial Discord error, repeating the command continues only
the remaining tracked work. Once complete, future courses no longer receive the
definition.

## Safe deletion

Course deletion is always a two-step operation:

```text
/course delete name:Machine Learning
/course delete name:Machine Learning confirm:true
```

The private preview lists tracked live resources, already missing resources,
manual/untracked channels that will be kept, and whether the category will be
deleted. All template and shared channels tracked by stable ID belong to the
confirmed deletion target, including tracked channels manually renamed or moved
elsewhere. Unknown channels are never deleted. If a manual channel remains in
the course category, the category is kept and becomes unmanaged; an empty
category is deleted. The local course record is removed only after all required
Discord deletions succeed. On partial failure it remains available for a safe
retry.

A semester can be deleted only after its managed courses are gone:

```text
/semester delete name:2026-fall
/semester delete name:2026-fall confirm:true
```

Semester deletion removes only the local empty semester record and never deletes
Discord resources or cascades into courses.

## Course template configuration

`config.yaml` has schema version `1`. The `course_template.category.name` value
controls the category name, while each item under `course_template.channels` has
a stable internal key and defines its visible `name` and `type` (`text`, `forum`,
or `voice`). Text and forum channels may have a `topic`; forum channels may also
have up to 20 unique `tags`.

Names and topics may use these placeholders:

- `{course_name}`
- `{course_code}`
- `{semester}`

Configuration is validated before the bot connects. Duplicate YAML keys,
unsupported types, invalid placeholders, duplicate tags, and malformed required
fields stop startup before Discord is modified.

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

The test suite is offline: it validates configuration, command registration,
administrator authorization, template parsing, SQLite persistence, and the
course creation, synchronization, bulk-channel, and safe-deletion workflows
without connecting to Discord. A final test on a separate Discord server is
still recommended after behavior changes.

## Safety and local state

- The bot does not need Discord's `Administrator` permission. Its current
  mutating operation only needs `View Channels` and `Manage Channels`.
- Every command also checks that the invoking member is a server administrator.
  Discord's default command permission is set accordingly, and a centralized
  runtime check provides a second enforcement layer.
- Commands and errors are returned ephemerally, so normal command output is
  visible only to the administrator who invoked it.
- The bot does not read message contents and does not request privileged Gateway
  intents.
- Destructive commands require a no-change preview followed by `confirm:true`.
  They target only stable IDs owned by the bot and never delete or silently
  adopt an unknown Discord category or channel because of a name match.
- `data/bot.db` is the bot's local managed-state database. It stores semesters,
  courses, provisioning states, and stable Discord resource IDs. It is not a
  backup of Discord messages or server content.
- The database and its SQLite sidecar files are ignored by Git. Back up
  `data/bot.db` before future large-scale administration or lifecycle changes.
  Do not casually delete it on a real server: the current version has no
  reconciliation/adoption tool for rebuilding ownership from existing Discord
  channels.
- If course creation stops after creating only some resources, their IDs are
  saved whenever possible. The response lists what was created, and retrying the
  identical `/course create` command attempts to continue the incomplete course.
- If a channel created during an incomplete course is manually moved, retrying
  course creation recognizes it by stable ID and leaves it in its chosen
  location while completing the remaining resources.
- Shared-channel and course deletion save progress. After a Discord error, read
  the result and repeat the confirmed command; already removed IDs are skipped
  and the retained database record protects the remaining work.
- After manually changing managed channels, run `/course sync`. Moves and renames
  are accepted, unique replacements are reconnected, and unresolved drift is
  reported without modifying Discord.
- The bot can be stopped with `Ctrl+C` after use. Previously created Discord
  resources and the local SQLite state remain in place.

## Troubleshooting

### The bot does not start

- Run `uv sync` first and start it with `./run.sh`; this guarantees use of the
  project-local `.venv`, not the system Python installation.
- Confirm that `.env` contains a bot token, not the Application ID. Create or
  reset the token on the Discord Developer Portal's **Bot** page.
- Configuration errors are reported before the bot connects. Check the paths in
  `DISCORD_CONFIG_PATH` and `DISCORD_DATABASE_PATH`, and validate edits to
  `config.yaml` against the documented schema and placeholders.
- Never paste the real token into an issue, commit, screenshot, or chat. If it
  has been exposed, reset it in the Developer Portal and update `.env`.

### Slash commands are missing

- For development, set `DISCORD_COMMAND_SYNC=guild` and make sure
  `DISCORD_GUILD_ID` is the ID of the server where the bot is installed, then
  restart the bot once.
- Confirm that the installation includes both `bot` and
  `applications.commands` scopes.
- Keep the process running until the log reports a successful connection and
  synchronization. After registration, `DISCORD_COMMAND_SYNC=off` is suitable
  for ordinary starts.

### A command is unavailable or denied

- The person invoking it must have Discord's `Administrator` permission. This
  does not mean the bot itself should receive `Administrator`.
- The bot needs `View Channels` and `Manage Channels` in the target server.
  Channel/category permission overwrites and the bot role's position can still
  affect what it can see or modify.
- Run `/server status` for the currently detected prerequisites and managed
  object counts.

### Course creation fails

- Create the semester first with `/semester create`.
- Enable Discord Community because the default template contains a Forum
  Channel.
- Check for an existing unmanaged category or channel with the same expected
  name. The bot reports this as a conflict rather than changing it.
- If the response reports partial creation, do not manually recreate the same
  items immediately. Correct the permission or configuration problem and retry
  the same command so the bot can continue from stored IDs.
- If managed channels were manually deleted or rearranged, retain the database
  and run `/course sync name:<course>`. Review its missing or ambiguous warnings;
  deleting the database may remove the only local ownership record.

### A bulk or deletion operation reports conflicts or partial failure

- Run the command without `confirm:true` again to obtain a fresh preview after
  manual changes.
- Same-name untracked channels are deliberately conflicts. Rename them or choose
  a different shared-channel name rather than expecting automatic adoption.
- If Discord denied only some deletions or creations, correct permissions and
  repeat the confirmed command. Stored IDs prevent successfully completed work
  from being targeted by name or blindly duplicated.
- A course category containing manual channels is intentionally kept after
  course deletion. Those channels and the remaining category are then unmanaged.

## Documentation policy

`README.md` and `README.hu.md` are the user manuals for the project. Every
future user-visible change must update both in the same change, including usage,
permissions, configuration, examples, side effects, safety notes, tests, and
troubleshooting. The two versions must remain meaningfully equivalent.

The roadmap below is durable memory for ideas worth revisiting. It is not an
implementation commitment: only an explicit current user request authorizes new
work. Ideas are not silently discarded; implemented items move into the current
feature documentation, while rejected or superseded items retain a short note
unless removal is explicitly requested.

## Roadmap and future candidates

Current status: version `0.4.0` has administrator-only semester management,
template-driven course creation and inspection, local stable-ID persistence,
safe conflict handling, server diagnostics, and non-mutating,
Discord-authoritative course synchronization. It also has previewed course and
empty-semester deletion plus tracked shared channels for every current and
future course. The following work remains optional and requires a separate
explicit request.

### Priority 1 — extend the safe synchronization foundation

- Completed in `0.3.0`: `/course sync` accepts the current Discord course state,
  stores observations, reconnects only unique matches, and reports drift without
  changing Discord.
- Add a separate dry-run plan before any future option is allowed to apply the
  template back to Discord.
- Add guided resolution for ambiguous matches and richer history between sync
  snapshots.

### Priority 2 — extend semester and course lifecycle

- Completed in `0.4.0`: narrow, previewed deletion of managed courses and empty
  semesters, preserving unknown/manual resources.
- Add course archive and restore without immediate permanent deletion.
- Add semester information, current-semester selection, archive, and restore.
- Define clearly what archive changes on Discord and what remains in SQLite.

### Priority 3 — usability, recovery, and portability

- Add autocomplete for semester and course parameters.
- Extend deliberate reconciliation to missing-database recovery; the current
  sync can reconnect unique replacements only when the course record still
  exists.
- Add managed-state export/import and a documented backup/restore procedure.

### Priority 4 — permissions and bulk administration

- Completed in `0.4.0`: previewed shared-channel addition/removal across every
  course, persisted for future courses and deleted only by tracked stable ID.
- Add student roles and configurable permission templates.
- Add cautious permission synchronization with inspection and dry-run first.
- Add validated bulk semester/course import from a reviewed CSV or YAML plan.
- Add optional global server-structure setup after its ownership boundaries are
  defined.

### Priority 5 — operational hardening

- Add per-server operation locks to prevent overlapping mutations.
- Add sequential SQLite schema migrations and template version/snapshot tracking.
- Expand audit logging while continuing to redact tokens and other secrets.
- Keep any future broader reset or cascade deletion separate from the current
  narrow deletion commands, with preview, explicit confirmation, and clear
  recovery limitations.

## Project context

Long-term product and engineering context lives in
[docs/project-context.md](docs/project-context.md). It provides direction, not a
fixed feature checklist.
