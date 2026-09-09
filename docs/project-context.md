# Discord Bot
## Project Context, Product Direction, and Engineering Notes

> **Purpose of this file**
>
> This document is intended to be given to a coding agent such as Codex CLI as long-lived project context.
> It describes the product direction, important Discord-specific constraints, preferred engineering principles, and ideas that may become useful later.
>
> **It is NOT a fixed implementation plan.**
>
> The project may evolve significantly. The coding agent should use this document to understand the intent of the project, but should only implement the features explicitly requested in the current task.
>
> Before implementing Discord-specific behavior that may have changed over time, verify it against the current official Discord Developer documentation and the current stable `discord.py` documentation.

---

# 1. Project Vision

The goal is to build a clean, extensible Discord administration tool for an MSc student community.

The most useful mental model is:

> **A local Discord Server Management Tool with a Discord slash-command interface**

It is not primarily a chat bot.

It is not expected to run continuously.

Its main purpose is to help administrators create, maintain, synchronize, and archive structured parts of the Discord server without repeatedly doing the same manual work in the Discord UI.

Typical things the tool may eventually manage:

- global server structure
- semesters
- courses
- course channel templates
- forum channels and tags
- roles
- category/channel permissions
- archiving
- safe synchronization
- server health/status reports
- configuration validation
- managed-resource metadata
- administrative audit information

The bot should remain understandable and modifiable by a single developer.

---

# 2. Operating Model

The bot is intentionally designed for **on-demand local execution**.

Typical workflow:

```text
Git repository
      |
      | git pull
      v
Local working copy
      |
      | start bot
      v
Bot connects to Discord
      |
      | administrator runs slash commands
      v
Discord server is modified
      |
      | stop bot
      v
Bot is offline
```

Example:

```bash
python bot.py
```

Use the Discord commands that are needed, then stop the bot:

```text
Ctrl+C
```

The bot does not need to stay online after it creates or modifies:

- categories
- channels
- forum channels
- roles
- permissions
- channel positions
- topics
- other persistent Discord server resources

Those Discord-side resources remain after the bot disconnects.

This operating model should influence architectural choices:

- do not require a permanent background worker
- do not require cloud hosting
- do not introduce a task queue unless a future feature actually needs one
- do not assume the process survives between administration sessions
- persist management metadata locally where useful
- startup and shutdown should be simple and predictable

Slash commands may remain registered in Discord while the bot is offline. In that situation they cannot be successfully handled until the bot is running again. That is acceptable for this project.

---

# 3. Non-Goals

Do not turn the initial project into a general-purpose Discord mega-bot.

The following are not goals unless explicitly requested later:

- music playback
- XP / leveling
- economy systems
- games
- AI chat
- welcome-message automation
- 24/7 moderation listeners
- reaction-role systems
- large web dashboard
- public multi-server SaaS platform
- Kubernetes
- Redis
- PostgreSQL
- distributed workers
- background queues
- always-on cloud infrastructure

Use Discord's native functionality whenever Discord already solves a problem well.

Examples:

- Discord roles
- category permissions
- Forum Channels
- AutoMod
- audit logs
- application command permissions
- server onboarding

The custom bot should focus on community-specific administration.

---

# 4. Language Conventions

The Discord server itself currently uses **English naming**.

Therefore visible resources created by the bot should generally use English names, for example:

```text
course-chat
materials
discussions
study-room
announcements
general
```

Code conventions should also be English:

- file names
- Python identifiers
- classes
- function names
- configuration keys
- database column names
- code comments

Documentation is different: the project should eventually provide **both English and Hungarian documentation**.

See the dedicated documentation section later in this file.

---

# 5. Preferred Initial Technology

Current preference:

- Python
- `discord.py`
- Discord application/slash commands
- YAML configuration
- SQLite
- environment variables for secrets
- Git / GitHub for version control

Potential lightweight dependencies:

```text
discord.py
python-dotenv
PyYAML
aiosqlite
```

Do not add dependencies automatically just because they are popular.

Prefer the Python standard library when it is sufficient.

Pin or constrain dependencies in a deliberate way once the project becomes stable enough to benefit from reproducible environments.

---

# 6. Important Discord Platform Facts

The following are architectural facts that should be kept in mind.

These were re-checked against official Discord documentation in September 2026, but current documentation should still be consulted when implementing relevant features.

## 6.1 Slash commands are Application Commands

The intended user interface is primarily Discord slash commands.

Example:

```text
/course create
/course sync
/semester create
/server status
```

Prefer structured command groups instead of a flat collection of unrelated commands when this produces a cleaner UX.

Example:

```text
/course
    create
    info
    list
    sync
    archive
```

rather than:

```text
/create-course
/info-course
/list-courses
/sync-course
/archive-course
```

The exact command tree is not fixed yet.

---

## 6.2 Command registration must be synchronized

With `discord.py`, adding commands locally to the application command tree is not enough; commands must be synced with Discord.

During active development, guild-scoped commands may be useful for fast iteration.

A configurable development guild ID may therefore be useful.

Do not hardcode a personal guild ID throughout the codebase.

Possible environment variable:

```dotenv
DISCORD_GUILD_ID=123456789012345678
```

The project may later choose between:

- development guild commands
- global commands
- a controlled sync strategy

Do not blindly synchronize commands on every reconnect if a more deliberate workflow later becomes preferable.

---

## 6.3 Minimal Gateway intents

This project is slash-command driven.

Do **not** enable privileged Gateway intents just because many beginner Discord bot tutorials do.

In particular:

```text
MESSAGE_CONTENT
GUILD_MEMBERS
GUILD_PRESENCES
```

should only be enabled if a real feature requires them.

A slash-command-focused administration tool generally does not need message-content access merely to process slash commands.

Use the minimum required intents.

This reduces permissions, complexity, and unnecessary access.

---

## 6.4 Installation scopes

For a server-installed Discord app with a bot user, installation should use the appropriate Discord application installation configuration.

Typical relevant scopes include:

```text
applications.commands
bot
```

Required bot permissions should be deliberately selected rather than simply requesting `Administrator`.

Document the installation process clearly.

---

## 6.5 Interaction response deadline

Discord interactions require a quick initial acknowledgement.

If an operation may take longer than a short moment, the command handler should defer the interaction response and then send/edit a follow-up.

This matters especially for commands such as:

```text
/server sync
/semester archive
/course sync
```

which may perform several API operations.

Administrative results should often be ephemeral where appropriate to avoid filling public channels with management output.

---

## 6.6 Channel creation permissions

Creating guild channels requires suitable channel-management permissions.

Changing channel permission overwrites may require role-management permissions.

The application should detect missing permissions and report them clearly instead of failing with a raw exception.

---

## 6.7 Role hierarchy matters

The bot is not a root user.

A bot with `Manage Roles` is still constrained by Discord role hierarchy.

It cannot freely manage roles at or above its own highest role.

The setup documentation should explain bot role placement.

Example conceptual hierarchy:

```text
Owner
Admin
Discord Bot
Moderator
Student
@everyone
```

Exact roles may differ.

---

## 6.8 Avoid Administrator permission by default

The bot should follow least privilege.

Possible permissions may include:

```text
Manage Channels
Manage Roles
View Channels
Send Messages
```

Additional permissions should only be requested when a feature actually requires them.

`Administrator` should not be the default answer to permission problems.

---

## 6.9 Category permissions and synced channel permissions

Discord supports category-level permission overwrites and channels whose permissions are synchronized with their parent category.

This is valuable for course structures.

Prefer category-level permission policy when all channels in the course should share access rules.

Avoid duplicating the same permission overwrites on every channel unless there is a reason.

---

## 6.10 Discord categories do not nest

A Discord category cannot be placed inside another category.

Therefore this conceptual hierarchy is impossible:

```text
ARCHIVE
└── 2026 FALL
    └── MACHINE LEARNING
        └── #course-chat
```

because categories cannot contain categories.

Archive design must respect Discord's real hierarchy.

Possible alternatives:

- rename archived course categories
- move archived categories toward the bottom
- apply a naming prefix
- make archived categories read-only
- maintain semester/archive relationships internally in SQLite
- optionally flatten archived channels differently if explicitly desired

Do not model impossible nested categories.

---

## 6.11 Deleting a category does not delete its child channels

This is extremely important for destructive commands.

Deleting a Discord category removes the parent relationship; its child channels are not automatically deleted with it.

Therefore a command such as:

```text
/course delete
```

must explicitly define what "delete course" means.

If permanent deletion is implemented, it should enumerate and deliberately delete managed child resources, with confirmation and careful error handling.

Never assume deleting the category automatically deletes the whole course.

---

## 6.12 Channel deletion is irreversible

Deleting a guild channel cannot be undone.

Archiving should therefore normally be preferred over deletion.

Destructive commands should use confirmation.

---

## 6.13 Forum Channels

Forum Channels are a core part of the intended course structure.

A forum channel can provide:

- organized post-based discussions
- available tags
- list/gallery layout
- default reaction
- auto archive settings
- post-level threads

For this project, forum channels are useful because a single `discussions` forum can replace many narrowly scoped text channels.

According to current Discord support documentation, Forum Channels require the server to have Community enabled.

Do not silently assume this prerequisite is satisfied.

If the bot is asked to create a forum and Community is not enabled:

- report the prerequisite clearly
- do not unexpectedly reconfigure the entire server
- only automate Community configuration if that becomes an explicit project feature

Enabling/disabling Community itself has stronger permission implications and should not be treated as a trivial side effect.

---

## 6.14 Discord resource limits exist

The tool should not hardcode assumptions that a guild can have unlimited resources.

Current Discord documentation includes limits such as:

- a finite number of channels per guild
- a finite number of categories
- a finite number of channels per category

This MSc use case is unlikely to approach the limits, but bulk operations should still validate obvious capacity problems when practical.

Do not overengineer capacity management in the MVP.

---

## 6.15 Rate limits

Discord APIs are rate-limited.

Use `discord.py`'s normal API methods and let the library handle the protocol-level rate-limit behavior.

Do not build synchronization code around arbitrary hardcoded sleeps such as:

```python
await asyncio.sleep(1)
```

between every API call unless there is a specific reason.

Do not fire uncontrolled hundreds of redundant requests.

Sync should first calculate what actually needs changing, then apply only required operations.

---

## 6.16 Audit log reasons

Discord supports audit-log reasons for many administrative API operations.

Where supported by `discord.py`, administrative changes may include a useful reason, for example:

```text
Discord Bot: course create requested by <user>
```

This improves traceability.

A separate optional `#bot-log` channel may also be useful later, but Discord's native audit log should not be ignored.

---

# 7. Core Domain Concepts

The important conceptual objects are:

```text
Guild / Server
Semester
Course
Course Template
Managed Channel
Managed Role
Archive State
Configuration
Managed State
Sync Plan
```

Not all need formal classes immediately.

The design should, however, avoid treating the Discord server as an unstructured pile of channel names.

---

# 8. Global Server Structure

Some categories are course-independent.

Possible example:

```text
📌 INFORMATION
├── #announcements
├── #important-links
└── #calendar

💬 COMMUNITY
├── #general
├── #introductions
└── #off-topic

🎓 ACADEMIC
├── #administration
├── #thesis
└── #opportunities

🔊 COMMON ROOMS
├── General
└── Study Room
```

This is an example only.

The actual structure should evolve based on how the MSc community uses the server.

The bot may eventually support something like:

```text
/server setup
```

to create global structures from configuration.

This should not be mandatory in the first implementation.

---

# 9. Course Structure

Each subject/course should normally be represented by a dedicated Discord category.

Minimal preferred template:

```text
MACHINE LEARNING
├── #course-chat
├── #materials
├── discussions
└── 🔊 study-room
```

This compact structure is intentional.

Avoid creating six to ten channels for every course unless real usage demonstrates the need.

---

# 10. Course Channel Responsibilities

## 10.1 `#course-chat`

Purpose:

- everyday course discussion
- quick questions
- lecture/class coordination
- course-specific announcements from students
- short-lived discussion

Example topic:

```text
General discussion for Machine Learning.
```

---

## 10.2 `#materials`

Purpose:

- lecture notes
- slides
- links
- references
- files
- useful learning material

Example topic:

```text
Notes, slides, links, references and learning materials for Machine Learning.
```

---

## 10.3 `discussions` Forum Channel

Purpose:

Structured topics that deserve their own thread/post.

Possible tags:

```text
Question
Assignment
Exam
Notes
Project
Important
Other
```

Example posts:

```text
[Assignment] Homework 1
[Question] Lecture 3 — eigenvalues
[Exam] January exam preparation
[Notes] Week 4 lecture notes
[Project] Final project ideas
```

The forum should reduce the need for channels such as:

```text
#assignments
#exams
#questions
#projects
```

Forum tag policy should eventually be configurable.

Avoid destructive synchronization of user-created forum tags.

---

## 10.4 `study-room` Voice Channel

Purpose:

- group study
- pair work
- project discussion
- exam preparation
- quick course voice conversations

---

# 11. Declarative Course Templates

The desired course structure should eventually be configuration-driven.

Example concept:

```yaml
course_template:
  category:
    name: "{course_name}"

  channels:
    course_chat:
      type: text
      name: course-chat
      topic: "General discussion for {course_name}."

    materials:
      type: text
      name: materials
      topic: "Notes, slides, links and learning materials for {course_name}."

    discussions:
      type: forum
      name: discussions
      topic: "Structured discussions for {course_name}."
      tags:
        - Question
        - Assignment
        - Exam
        - Notes
        - Project
        - Important
        - Other

    study_room:
      type: voice
      name: study-room
```

This is an example schema, not a mandatory final format.

Important distinction:

```text
internal template key
visible Discord name
Discord resource ID
```

are different concepts.

Example:

```text
template key       = materials
visible name       = materials
Discord channel ID = 123456789012345678
```

This makes synchronization more robust.

---

# 12. Semester Concept

Semesters should eventually be first-class entities inside the bot's domain model.

Possible names:

```text
2026-fall
2027-spring
```

or:

```text
2026-27-1
2026-27-2
```

Do not prematurely lock the project into one naming scheme unless explicitly requested.

A course can belong to a semester internally even though Discord cannot represent semester -> course category nesting.

Example internal relationship:

```text
Semester: 2026-fall

Courses:
- Machine Learning
- Data Mining
- Statistics
```

Possible future commands:

```text
/semester create
/semester list
/semester info
/semester current
/semester archive
/semester restore
```

The first MVP may only need `create` and `list`.

---

# 13. Archiving

Archiving is preferred over deleting.

Possible archive behavior for a course:

1. mark it archived in managed state
2. make student interaction read-only
3. retain message history
4. move the category lower in the server
5. optionally rename it with a consistent archive marker
6. retain semester association
7. allow restoration

Example:

```text
[ARCHIVED] MACHINE LEARNING
```

or another naming convention later.

Do not overcommit to a visual archive scheme before testing how it feels in the actual server.

Potential commands:

```text
/course archive
/course restore
/semester archive
```

Semester archive could apply archive behavior to all managed courses belonging to the semester.

---

# 14. Safe Synchronization

Safe synchronization is likely to become the most valuable long-term feature.

Concept:

```text
Desired configuration
        vs
Actual Discord state
        vs
Known managed metadata
```

The bot computes drift.

Possible statuses:

```text
OK
MISSING
RENAMED
MOVED
EXTRA
TYPE_MISMATCH
PERMISSION_MISMATCH
UNKNOWN
UNMANAGED
```

Not all need to exist initially.

---

# 15. Idempotency

Administrative operations should be idempotent wherever practical.

Running:

```text
/course sync
/course sync
/course sync
```

should not create:

```text
#materials
#materials-2
#materials-3
```

Similarly:

```text
/semester create 2026-fall
```

should not silently create duplicate semesters.

The system should recognize an already-satisfied desired state.

---

# 16. Conservative Sync Policy

The default philosophy should be:

> **Create or repair what the bot knows it owns; report unknown things; do not destroy surprises.**

Safe default behavior:

- create missing managed resources
- detect renamed managed resources
- repair managed settings when explicitly part of sync policy
- report manually-created extra resources
- do not delete unknown resources
- do not delete user-created forum tags
- do not aggressively overwrite manual changes without a clear rule

Example:

```text
Machine Learning

✓ course-chat
✓ materials
+ create missing forum: discussions
! unknown channel: project-team-alpha
```

The unknown channel should normally remain untouched.

---

# 17. Preview / Dry-Run Before Broad Changes

A future sync engine should support preview.

Example:

```text
/server sync
```

Result:

```text
Synchronization preview

Machine Learning
+ Create #announcements

Data Mining
+ Create #announcements

Statistics
~ Rename #resources -> #materials

Unmanaged resources:
! #project-team-alpha

No resources will be deleted.

[Apply changes]
[Cancel]
```

The first MVP does not need a sophisticated interactive planner, but code should not be structured in a way that makes a later `plan -> apply` workflow impossible.

A useful architecture is:

```text
inspect
   ↓
build change plan
   ↓
present/log plan
   ↓
apply plan
```

rather than directly mutating Discord while discovering differences.

---

# 18. Destructive Operations

Examples:

```text
/course delete
/server reset
/semester delete
```

should be treated as dangerous.

Preferred behavior:

- confirmation required
- clearly state affected resources
- archive offered as safer alternative
- do not perform hidden cascading deletion
- use audit-log reasons
- log partial failures

Example:

```text
⚠️ Permanently delete course?

Course: Machine Learning
Managed channels: 4

This operation cannot be undone.

[Delete permanently]
[Cancel]
```

Remember: deleting the category itself does not delete its children.

A permanent-delete implementation must explicitly determine and delete the intended child resources.

---

# 19. Permissions Model

Start simple.

Possible server roles:

```text
Admin
Moderator
Student
@everyone
```

The bot's own role is separate.

Course categories could initially be visible to the general student role.

Prefer a dedicated `Student` role eventually instead of relying on `@everyone` for every permission.

Future possibilities:

- elective-course role
- private project group
- teaching staff role
- course admin role

Do not implement these prematurely.

---

# 20. Command Authorization

Administrative commands should not be available to everyone.

Possible approaches:

- default member permissions on application commands
- Discord's server integration command permissions
- runtime permission checks
- optional configured admin role

Use Discord-native permission concepts where possible.

Examples of sensitive commands:

```text
/server setup
/server sync
/course create
/course archive
/course delete
/role sync
```

The bot should fail safely if an unauthorized member somehow invokes an administrative handler.

---

# 21. Candidate Command Tree

This is a collection of ideas, not a required implementation plan.

```text
/server
    status
    setup
    preview
    sync

/course
    create
    list
    info
    edit
    sync
    archive
    restore
    delete

/semester
    create
    list
    info
    current
    archive
    restore

/template
    show
    validate
    reload

/role
    list
    create
    sync

/state
    status
    export
    reconcile
```

The project can grow toward this gradually.

Prefer adding commands only when they solve a real workflow.

---

# 22. Potential `/course create` UX

Possible fields:

```text
name
code
semester
private
```

Example:

```text
/course create
name: Machine Learning
code: ML01
semester: 2026-fall
```

Potential behavior:

1. validate request
2. resolve current guild
3. check authorization
4. validate semester if required
5. check for existing managed course
6. check Discord-side conflicts
7. create category
8. create configured child channels
9. apply category permissions
10. create forum tags
11. save resulting IDs
12. send a concise result

Example response:

```text
✅ Course created

Machine Learning
Semester: 2026-fall

Created:
- #course-chat
- #materials
- discussions
- study-room
```

If creation fails halfway through, clearly report what succeeded and what failed.

Do not pretend the operation was atomic if Discord API operations were partially applied.

---

# 23. Partial Failure Handling

Discord modifications are multiple remote API calls.

Example:

```text
create category          success
create course-chat       success
create materials         success
create discussions       failure
create study-room        not attempted
```

The application should not simply return:

```text
Something went wrong.
```

It should retain enough information to recover.

Possible strategies:

- save successful created IDs incrementally
- report partial result
- allow `/course sync` to finish missing pieces later
- avoid blindly rolling back unless rollback is known to be safe
- make retries idempotent

This is a very useful reason for having a sync system.

---

# 24. Configuration vs Managed State

These are separate concepts.

## Configuration answers:

> What should the server/course look like?

Examples:

```yaml
course_template:
  ...
```

## Managed state answers:

> Which real Discord object corresponds to this logical object?

Examples:

```text
Machine Learning category -> Discord ID 123...
materials template key -> Discord ID 456...
```

Do not mix these responsibilities unnecessarily.

---

# 25. SQLite State Model

SQLite is a good local database for this project.

Conceptual tables could include:

```text
guilds
semesters
courses
course_channels
managed_roles
schema_metadata
```

Example course:

```text
courses
-------
id
guild_id
discord_category_id
name
code
semester_id
archived
created_at
updated_at
```

Example managed course channel:

```text
course_channels
---------------
id
course_id
discord_channel_id
template_key
channel_type
created_at
updated_at
```

Example semester:

```text
semesters
---------
id
guild_id
name
is_current
archived
created_at
updated_at
```

The exact schema should be designed when implementation actually begins.

---

# 26. Do Not Trust Names as Identity

Avoid logic like:

```python
if category.name == "Machine Learning":
    ...
```

as the primary identity mechanism.

Names are editable by humans.

Discord Snowflake IDs are stable identifiers for existing resources.

Store IDs when the bot creates or adopts resources.

Example:

```text
logical course ID
      ↓
Discord category ID
      ↓
managed channel IDs
```

Names are display metadata, not durable identity.

---

# 27. Database Portability and Reconciliation

Because the bot runs locally and the source code lives in Git, the local SQLite database introduces an important practical issue:

> What happens if the repository is cloned on a new machine, the database is lost, or an administrator manually changes the server?

The design should not assume that the SQLite file is an eternal, perfect source of truth.

For the initial project, local SQLite is fine.

Longer term, consider one or more of:

```text
/state export
/state import
/state reconcile
```

or:

```text
/diagnose
/adopt
```

Possible reconciliation flow:

1. inspect existing Discord categories/channels
2. compare expected type/name/structure
3. propose candidate matches
4. require confirmation for ambiguous matches
5. rebuild managed ID mappings

Never silently "adopt" arbitrary similarly named resources if that could cause destructive sync behavior.

The raw SQLite database probably should not be committed to Git by default.

If portability becomes important, a deliberately designed export/manifest format is preferable to casually version-controlling a mutable SQLite binary.

Discord IDs themselves are not secrets, but state files may still contain environment-specific information and create merge/conflict problems.

---

# 28. Configuration Validation

Configuration should fail early.

Bad configuration should ideally be caught at startup or via a validation command before Discord changes occur.

Examples:

- duplicate template keys
- unsupported channel type
- duplicate forum tags
- invalid placeholder
- missing required field
- impossible permission configuration

Possible command later:

```text
/template validate
```

The bot should not discover a malformed template halfway through creating ten courses.

---

# 29. Configuration Versioning

A future configuration format may evolve.

It may eventually be useful to include:

```yaml
schema_version: 1
```

This is not necessary on day one, but avoiding an unversionable ad-hoc format will make future changes easier.

---

# 30. Migration Philosophy

Database migrations should be simple and explicit.

For a small local tool, do not introduce heavyweight migration infrastructure immediately unless needed.

But do not rely on deleting `bot.db` every time the schema changes once the tool starts managing real state.

Possible lightweight approach later:

```text
schema_metadata
---------------
version
```

with sequential migration functions.

---

# 31. Suggested Repository Organization

A possible long-term structure:

```text
discord-bot/
│
├── bot.py
├── config.yaml
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── README.hu.md
├── CHANGELOG.md
│
├── cogs/
│   ├── courses.py
│   ├── semesters.py
│   ├── server.py
│   ├── roles.py
│   └── templates.py
│
├── services/
│   ├── course_service.py
│   ├── semester_service.py
│   ├── sync_service.py
│   ├── permission_service.py
│   └── template_service.py
│
├── database/
│   ├── database.py
│   ├── models.py
│   └── migrations.py
│
├── docs/
│   ├── en/
│   │   ├── installation.md
│   │   ├── configuration.md
│   │   ├── commands.md
│   │   ├── administration.md
│   │   └── troubleshooting.md
│   │
│   └── hu/
│       ├── telepites.md
│       ├── konfiguracio.md
│       ├── parancsok.md
│       ├── adminisztracio.md
│       └── hibakereses.md
│
├── tests/
│   └── ...
│
└── data/
    └── bot.db
```

This is illustrative, not mandatory.

For an early version, a smaller layout is acceptable.

Do not create empty architecture layers merely to match this diagram.

Split code when real responsibilities emerge.

---

# 32. Bilingual Documentation Requirement

The finished bot should have useful documentation in **both English and Hungarian**.

This is a project requirement, not an optional afterthought.

The exact documentation layout can evolve, but a good direction is:

```text
README.md       -> English overview
README.hu.md    -> Hungarian overview

docs/en/
docs/hu/
```

At minimum, both languages should eventually cover:

## Installation

- creating the Discord application
- installation/guild setup
- required scopes
- required bot permissions
- bot role placement
- environment variables
- Python environment
- running the bot
- stopping the bot

## Configuration

- configuration file structure
- course template
- forum tags
- naming
- permission-related settings

## Commands

- command reference
- parameters
- examples
- destructive-command warnings

## Administration

- how to create courses
- how semesters work
- how synchronization works
- how archiving works
- what happens while the bot is offline

## Troubleshooting

Examples:

```text
Command does not appear
Bot is offline
Missing Manage Channels
Bot cannot edit a role
Forum creation fails
Community is not enabled
Database state is missing
Sync detects unknown channels
```

---

# 33. Documentation Maintenance Rule

When user-visible behavior changes, the relevant documentation should change in the same development task/commit when practical.

Do not allow:

```text
code behavior = version 4
English docs  = version 2
Hungarian docs = version 1
```

The two languages should remain meaningfully equivalent.

They do not need to be literal word-for-word translations.

Prioritize clarity in each language.

Code and technical identifiers remain English.

---

# 34. Optional Internal Developer Documentation

Useful future files may include:

```text
docs/architecture.md
docs/data-model.md
docs/sync-model.md
docs/decisions/
```

or Architecture Decision Records (ADRs) if the project becomes complex enough.

Do not create bureaucracy for a tiny bot.

A short architecture document explaining:

```text
Discord
   ↕
commands
   ↓
services
   ↓
config + state
```

may be enough for a long time.

---

# 35. Changelog

A lightweight `CHANGELOG.md` may become useful once the bot is actively used.

Possible categories:

```text
Added
Changed
Fixed
Removed
```

This is helpful when changes to sync or permissions may affect the real Discord server.

Not mandatory for the first tiny prototype.

---

# 36. Testing Philosophy

Discord API calls should not make all meaningful logic impossible to test.

Where practical, separate:

```text
decision/planning logic
```

from:

```text
Discord mutation calls
```

For example, a sync planner can be tested with plain Python objects/data structures.

Potential future test targets:

- template validation
- course name normalization
- duplicate detection
- sync diff calculation
- archive-state transitions
- permission-plan generation
- database repository methods

Do not over-mock the entire Discord library in the first prototype.

Test the logic where tests provide real value.

---

# 37. Dry-Run Mode

A future CLI or command-level dry-run mode could be valuable.

Examples:

```text
/course sync dry_run:true
/server sync dry_run:true
```

or a preview button workflow.

The key idea:

> The bot should be able to explain what it intends to modify before performing broad changes.

This is especially useful once the server contains real student data.

---

# 38. Logging

Use normal application logging instead of uncontrolled `print()` statements once the project grows beyond the initial prototype.

Useful categories:

```text
startup
command
discord_api
database
sync
error
```

Do not log secrets.

Never log:

```text
DISCORD_TOKEN
```

Avoid logging unnecessary sensitive user information.

---

# 39. Secrets

Never commit the Discord bot token.

Use `.env` locally.

Example:

```dotenv
DISCORD_TOKEN=actual-secret-token
DISCORD_GUILD_ID=123456789012345678
```

Repository:

```text
.env.example
```

Example:

```dotenv
DISCORD_TOKEN=your_token_here
DISCORD_GUILD_ID=your_development_guild_id_here
```

`.gitignore` should normally include:

```gitignore
.env
.venv/
__pycache__/
*.pyc
data/*.db
```

Adjust database handling intentionally if a future state-management strategy changes.

If a token is ever accidentally committed, treat it as compromised and rotate it.

---

# 40. Startup Experience

Since the bot is manually started when needed, startup should be pleasant and diagnostic.

Example conceptual output:

```text
Discord Bot

Configuration: OK
Database: OK
Schema version: 1
Loaded commands: 8
Discord connection: OK
Guild: Example MSc Server

Ready.
```

Potential startup checks:

- environment variables
- config file parses
- database opens
- migrations succeed
- expected guild can be resolved
- bot has basic required permissions
- Community/forum prerequisite if forum features are about to be used

Do not necessarily fail startup because an optional permission for an unused feature is absent.

---

# 41. Graceful Shutdown

Stopping via `Ctrl+C` should not corrupt local state.

Database connections should close cleanly.

No complex shutdown system is needed unless future functionality introduces background tasks.

---

# 42. Development Server

Development and risky testing should ideally happen on a separate Discord test server before touching the real MSc community server.

This is especially important for:

- bulk sync
- permissions
- archive
- delete
- role management

The official Discord quick-start guidance also recommends testing server-installed apps in a server that is not actively used by others.

---

# 43. Status / Diagnostic Command

A useful early command may be:

```text
/server status
```

Possible information:

```text
Bot permissions
Managed courses
Managed semesters
Missing Discord resources
Unknown/missing database mappings
Community enabled: yes/no
Template valid: yes/no
```

This can become the safe entry point after starting the bot.

It is often more valuable than immediately implementing many mutation commands.

---

# 44. Potential State Health Categories

Possible diagnostic statuses:

```text
HEALTHY
DRIFT
MISSING
UNMANAGED
AMBIGUOUS
PERMISSION_ERROR
CONFIG_ERROR
```

These names are ideas only.

A human-readable report is more important than elaborate enums in the first version.

---

# 45. Concurrency Safety

The bot will probably have very few administrators, but broad management operations should not accidentally run on top of each other.

Example:

```text
Admin A: /server sync
Admin B: /semester archive
```

Potential future safeguard:

- per-guild operation lock
- reject conflicting management operations
- clearly report "another server-management operation is active"

This is not a priority for the earliest prototype but is worth remembering.

---

# 46. Human Manual Changes Are Expected

Administrators may manually edit the Discord server.

Examples:

- rename a category
- move a channel
- create a temporary project channel
- adjust permissions
- add a forum tag

The bot should not treat every manual change as corruption.

The long-term philosophy should support coexistence between:

```text
managed structure
```

and:

```text
human-created additions
```

Sync should be conservative.

---

# 47. Managed vs Unmanaged Resources

A useful conceptual distinction:

```text
Managed resource
```

The bot knows it created/adopted this resource and tracks its identity.

```text
Unmanaged resource
```

The bot sees it in Discord but has no ownership relationship with it.

Unknown resources should usually be preserved.

Future adoption could be explicit:

```text
/state adopt
```

rather than automatic.

---

# 48. Possible Managed Resource Metadata

SQLite may track:

```text
resource_type
discord_id
logical_key
course_id
created_by_tool
last_known_name
last_synced_at
```

Do not implement all fields without a real need.

The important concept is durable identity and ownership.

---

# 49. Name Normalization

Course names may contain characters that are awkward for text channel names but fine for categories.

Example:

```text
Advanced C++ / GPU Programming
```

Category:

```text
ADVANCED C++ / GPU PROGRAMMING
```

A generated text channel or role may require a separate normalization policy.

Do not use a destructive one-size-fits-all normalization function for every Discord resource type.

Preserve the human course display name separately from Discord-safe derived names.

---

# 50. Course Codes

Course code can be useful as metadata:

```text
name: Machine Learning
code: ML01
```

Do not require course codes unless the real MSc program uses them consistently.

Possible display choices later:

```text
ML01 — MACHINE LEARNING
```

or simply:

```text
MACHINE LEARNING
```

Keep storage separate from visual formatting.

---

# 51. Course Template Evolution

Template changes should not automatically imply that all historical courses must be rewritten.

Potential future concepts:

```text
template_version
```

or:

```text
course template snapshot
```

This becomes relevant if archived courses should preserve historical structure while current courses use a new template.

Do not implement versioned templates prematurely.

Just avoid assumptions that make future evolution impossible.

---

# 52. Forum Tag Evolution

If template tags become:

```text
Question
Assignment
Exam
Notes
Project
Important
Other
```

and users later manually add:

```text
Cheat Sheet
```

sync should not automatically remove `Cheat Sheet`.

Similarly, renaming tags should be deliberate.

Forum tags may already be attached to posts, so destructive tag synchronization should be treated carefully.

---

# 53. Permission Sync Philosophy

Permission synchronization can become dangerous quickly.

Start with:

- permission setup at creation time
- diagnostics
- optional repair of known category permissions

Only later introduce aggressive permission sync.

Always distinguish:

```text
expected
actual
difference
proposed change
```

before applying bulk permission changes.

---

# 54. `/server setup`

Potential future purpose:

Create global server scaffolding.

Example:

```text
/server setup
```

could create missing global structures only.

It should be idempotent.

It should not reset an existing server.

A command called `setup` should mean:

> create missing managed baseline

not:

> wipe and recreate everything

If destructive reset behavior is ever added, give it a very explicit separate command and confirmation flow.

---

# 55. `/course sync`

Likely one of the first genuinely useful synchronization commands.

Possible behavior:

1. resolve managed course
2. load desired template
3. fetch/inspect current Discord objects
4. identify missing managed channels
5. identify known renamed/moved channels
6. report unknown resources
7. produce plan
8. apply safe changes
9. update managed metadata
10. report result

For an early version, `sync` can be simpler.

The design principle is more important than feature completeness.

---

# 56. `/server sync`

Do not build this by simply looping over `/course sync` logic with no planning.

Eventually it may be useful to create a whole-server plan first so the administrator can understand the total impact.

Potential summary:

```text
12 courses checked
3 missing channels
1 renamed managed channel
2 unmanaged channels
0 destructive actions
```

---

# 57. `/semester archive`

Potential behavior:

```text
/semester archive 2026-fall
```

could:

- mark semester archived
- archive all managed courses in that semester
- produce preview first
- preserve all content

Because the operation may touch many resources, interaction deferral and progress/result handling matter.

Do not spam a public channel with dozens of status messages.

---

# 58. Interaction UX

Admin commands should have concise, readable Discord responses.

Prefer structured embeds/components where they materially help, but do not make every command visually elaborate.

Useful interaction patterns:

- ephemeral acknowledgement
- confirmation buttons
- compact summary
- error explanation
- preview/apply
- autocomplete for known courses/semesters

Autocomplete may become useful for:

```text
/course info
/course archive
/semester archive
```

because users should not need to type exact names repeatedly.

---

# 59. Command Names and Localization

Discord application commands support localization.

This project may eventually expose localized Hungarian command descriptions/names.

However, the initial command surface may remain English for consistency with the server.

Do not introduce command localization unless requested.

Documentation must still exist in English and Hungarian.

---

# 60. Error Handling

Normal users/admins should receive understandable errors.

Examples:

```text
❌ Course already exists.
```

```text
❌ Semester "2026-fall" does not exist.
```

```text
❌ Missing permission: Manage Channels.
```

```text
❌ Forum Channels require Community to be enabled on this server.
```

```text
⚠️ Managed database state references a channel that no longer exists.
Run /course sync or reconciliation.
```

Technical stack traces belong in local logs, not Discord responses.

---

# 61. Discord API Exceptions

Handle common classes of failures separately when useful:

- forbidden / missing permissions
- not found
- rate limited indirectly through library handling
- invalid request
- network/API failure

Do not catch `Exception` everywhere and discard useful error context.

At command boundaries, convert internal failures into safe user-facing messages and log technical detail.

---

# 62. Avoid Raw Discord REST Calls Unless Needed

Prefer high-level `discord.py` methods.

Examples include:

- create category
- create text channel
- create forum
- create voice channel
- modify channel
- edit permissions

Raw REST calls should only be introduced when the library genuinely lacks necessary functionality.

This allows the library to handle Discord-specific behavior such as rate limiting more reliably.

---

# 63. Bot Architecture

A useful conceptual flow:

```text
Discord slash command
        ↓
command handler
        ↓
service / use-case logic
        ↓
configuration + repository/state
        ↓
discord.py API
```

Command handlers should not eventually contain hundreds of lines of business logic.

Example:

```text
/course create
      ↓
CourseService.create_course(...)
```

The exact architecture can stay small initially.

---

# 64. Do Not Create Architecture for Architecture's Sake

A five-file prototype does not need:

```text
controllers/
repositories/
domain/
use_cases/
adapters/
ports/
entities/
factories/
```

unless real complexity justifies it.

Prefer clear modules over ceremonial enterprise layering.

The coding agent should refactor when responsibilities become clear.

---

# 65. Possible MVP

This is only a suggestion.

A strong first useful version might contain:

## Infrastructure

- startup
- environment loading
- basic config loading
- SQLite initialization
- logging
- slash command registration
- clear error handling

## Commands

```text
/server status
/semester create
/semester list
/course create
/course list
/course info
```

Potentially:

```text
/course sync
```

if it can be implemented safely without exploding scope.

## Course creation

- category
- `course-chat`
- `materials`
- `discussions` forum
- `study-room`
- forum tags
- persisted Discord IDs

This would already solve a real problem.

---

# 66. Possible Phase 2

Ideas:

```text
/course sync
/course archive
/course restore
/semester current
/semester archive
/server setup
/template validate
```

Also:

- preview/apply
- archive permissions
- better diagnostics
- audit reasons
- documentation expansion

---

# 67. Possible Phase 3

Ideas:

- server-wide sync
- state reconciliation
- import/export
- private/elective courses
- role templates
- template versions
- permission synchronization
- bulk course import from YAML/CSV
- semester rollover
- richer admin log
- interactive setup wizard
- command autocomplete
- localized command descriptions

These are future possibilities, not commitments.

---

# 68. Example End-to-End Workflow

Start the tool:

```bash
python bot.py
```

Discord:

```text
/semester create
name: 2026-fall
```

Result:

```text
✅ Semester created: 2026-fall
```

Then:

```text
/course create
name: Machine Learning
code: ML01
semester: 2026-fall
```

Created:

```text
MACHINE LEARNING
├── #course-chat
├── #materials
├── discussions
└── 🔊 study-room
```

Later:

```text
/course create
name: Data Mining
code: DM01
semester: 2026-fall
```

Months later the template changes.

Start bot again.

Run:

```text
/course sync
course: Machine Learning
```

The bot inspects and safely repairs managed differences.

Then stop the bot.

The Discord server continues functioning normally.

---

# 69. Example Config Direction

A future configuration might look roughly like:

```yaml
schema_version: 1

server:
  language: en

course_template:
  category:
    format: "{course_name}"

  channels:
    course_chat:
      type: text
      name: course-chat
      topic: "General discussion for {course_name}."

    materials:
      type: text
      name: materials
      topic: "Notes, slides, links and learning materials for {course_name}."

    discussions:
      type: forum
      name: discussions
      topic: "Structured discussions for {course_name}."
      tags:
        - Question
        - Assignment
        - Exam
        - Notes
        - Project
        - Important
        - Other

    study_room:
      type: voice
      name: study-room
```

Do not copy this schema blindly if a cleaner design emerges during implementation.

---

# 70. Documentation Deliverables

As the project becomes usable, the coding agent should help maintain:

```text
README.md
README.hu.md
docs/en/...
docs/hu/...
```

A useful English README should quickly answer:

```text
What is this?
Why does it exist?
Does it need to run 24/7?
How do I install it?
How do I configure Discord?
How do I start it?
What commands are available?
Where is the Hungarian documentation?
```

The Hungarian README should answer the same practical questions naturally in Hungarian.

---

# 71. Documentation Tone

Documentation should be practical.

Prefer:

```text
1. Open Discord Developer Portal.
2. Create an application.
3. Configure Guild Install.
4. Add the required scopes.
5. Grant the documented minimum permissions.
6. Copy `.env.example` to `.env`.
7. Add the token.
8. Run the bot.
```

over vague descriptions.

Include warnings where actions may be destructive.

---

# 72. Configuration Documentation

The docs should explain each meaningful config field.

Example:

```yaml
course_template:
```

should not become an undocumented magic blob.

When configuration changes, update both English and Hungarian documentation.

---

# 73. Command Documentation

Each command should eventually document:

- purpose
- required permission
- arguments
- example
- side effects
- whether it is destructive
- whether confirmation is required

Example:

```text
/course archive
```

Purpose:

```text
Makes a managed course inactive/read-only while preserving its content.
```

---

# 74. Troubleshooting Documentation

Important because the bot is started only occasionally.

Potential issues:

## Slash command is visible but does nothing

Likely bot is offline.

## Slash command does not appear

Potential command synchronization/install issue.

## Bot cannot create channels

Check `Manage Channels`.

## Bot cannot manage a role

Check `Manage Roles` and role hierarchy.

## Forum creation fails

Check Community server prerequisite and permissions.

## Bot database is missing

Use diagnostic/reconciliation workflow once implemented.

This documentation will greatly reduce future frustration.

---

# 75. Source-of-Truth Philosophy

There are multiple realities:

```text
Configuration
Managed local state
Actual Discord state
Human intention
```

No single one should be blindly trusted in every situation.

Configuration defines desired structure.

SQLite tracks resource identity.

Discord is the actual live server.

Human/admin confirmation resolves ambiguous or destructive differences.

This is why a conservative sync/reconcile design matters.

---

# 76. Security Principles

- least privilege
- never commit token
- avoid privileged intents unless required
- restrict admin commands
- prefer ephemeral admin responses
- validate inputs
- do not mention `@everyone` or roles accidentally from user-provided strings
- use safe mention handling in generated messages
- do not expose internal errors to normal users
- do not silently broaden permissions
- do not automatically grant the bot `Administrator`

---

# 77. Input Safety

Course names, codes, and other administrator-provided values may contain unusual characters.

Treat them as untrusted strings for:

- Discord messages
- logs
- filenames
- SQL parameters
- config interpolation

Use parameterized database queries.

Avoid accidental Discord mentions in generated output.

Do not build SQL by string concatenation.

---

# 78. Data Backups

The bot manages Discord resources, but the local database also becomes useful metadata.

A future `/state export` or manual backup mechanism may be useful before major changes.

Do not pretend a state export is a backup of Discord messages.

Discord content backup/export is a separate problem and is not currently a project goal.

---

# 79. GitHub Workflow

The source lives in Git/GitHub.

Typical development:

```bash
git pull
# edit
# test
git add .
git commit
git push
```

The Discord token remains outside Git.

The bot may be run from any working copy that has:

- valid environment variables
- compatible config
- usable state/reconciliation path

---

# 80. Optional Developer Tooling

Potentially useful later:

```text
pytest
ruff
mypy or pyright
pre-commit
```

Do not add all of them automatically.

If introduced:

- keep configuration simple
- document commands
- avoid making contribution painful

A small project benefits most from consistency and readable code.

---

# 81. Version Compatibility

Avoid writing this project around undocumented behavior.

When selecting Python and `discord.py` versions:

- use supported versions
- document them
- keep `requirements.txt` or project metadata clear
- verify APIs against the installed/current stable library

If a Discord API or `discord.py` feature differs from this document, current official documentation wins.

---

# 82. Reference Documentation

When implementing Discord-specific functionality, prefer first-party sources.

Useful current references include:

- Discord Developer Documentation — Application Commands
  https://docs.discord.com/developers/interactions/application-commands

- Discord Developer Documentation — Receiving and Responding to Interactions
  https://docs.discord.com/developers/interactions/receiving-and-responding

- Discord Developer Documentation — Gateway / Intents
  https://docs.discord.com/developers/events/gateway

- Discord Developer Documentation — Guild Resource
  https://docs.discord.com/developers/resources/guild

- Discord Developer Documentation — Channel Resource
  https://docs.discord.com/developers/resources/channel

- Discord Developer Documentation — Rate Limits
  https://docs.discord.com/developers/topics/rate-limits

- Discord Developer Documentation — OAuth2 and Permissions
  https://docs.discord.com/developers/platform/oauth2-and-permissions

- Discord Developer Documentation — Audit Logs
  https://docs.discord.com/developers/resources/audit-log

- Discord Support — Forum Channels FAQ
  https://support.discord.com/hc/en-us/articles/6208479917079-Forum-Channels-FAQ

- Discord Support — Roles and Permissions
  https://support.discord.com/hc/en-us/articles/214836687-Discord-Roles-and-Permissions

- discord.py stable documentation
  https://discordpy.readthedocs.io/en/stable/

Do not rely on old blog posts or random tutorials when official documentation disagrees.

---

# 83. Instructions to a Coding Agent

When this file is supplied to Codex or another coding agent:

1. Read the entire file before making architectural decisions.
2. Treat it as project context, not as a checklist that must all be implemented now.
3. Implement only the current requested scope.
4. Keep the project small until complexity is real.
5. Prefer slash commands for the Discord UI.
6. Keep visible server naming English unless explicitly changed.
7. Keep code identifiers and configuration keys English.
8. Maintain English and Hungarian user/admin documentation as the project becomes usable.
9. Do not enable privileged intents without a feature-level reason.
10. Do not request `Administrator` by default.
11. Use stable Discord IDs for managed resource identity.
12. Separate desired configuration from actual managed state.
13. Make creation/sync operations idempotent when practical.
14. Never delete unknown resources during normal synchronization.
15. Prefer archive over permanent delete.
16. Add confirmation before destructive operations.
17. Respect the fact that Discord categories cannot be nested.
18. Remember that deleting a category does not delete its child channels.
19. Treat Forum/Community requirements as explicit prerequisites.
20. Handle interaction deadlines correctly; defer longer operations.
21. Use current `discord.py` APIs instead of hand-written HTTP unless necessary.
22. Let the Discord library handle rate limiting rather than hardcoding delays.
23. Preserve partial operation state so retries can recover safely.
24. Do not make SQLite the only recoverable representation of server identity forever.
25. Design future reconciliation/adoption conservatively.
26. Keep secrets out of Git.
27. Keep error messages useful and human-readable.
28. Use logs for technical details.
29. Update documentation when user-visible behavior changes.
30. Verify time-sensitive Discord platform details against official docs before implementation.
31. Do not implement speculative infrastructure merely because it appears in this document.
32. When there are several reasonable designs, prefer the simplest one that leaves room to evolve.

---

# 84. What Matters Most

If only a few principles from this document are remembered, they should be these:

## 1. The bot is an on-demand local administration tool

It does not need continuous hosting.

## 2. Courses are the central managed object

Each course should have a compact reusable structure.

## 3. Semesters are metadata/domain objects

Do not force impossible nested Discord category structures.

## 4. Templates describe desired structure

Avoid repeating manual channel creation.

## 5. Discord IDs identify managed resources

Names can change.

## 6. Synchronization must be conservative and idempotent

Do not destroy manual additions.

## 7. Archive is safer than delete

Student history and materials should normally be preserved.

## 8. Minimum permissions and minimum intents

The bot should not receive broad access without a reason.

## 9. Local state must be recoverable

SQLite is useful, but future reconciliation/export should remain possible.

## 10. Documentation is part of the product

Maintain useful documentation in both English and Hungarian.

---

# 85. Current Product Direction in One Diagram

```text
                  Git / GitHub
                       |
                       v
                Local Python Tool
                       |
               started when needed
                       |
                       v
                 Discord App
                       |
              Slash Admin Commands
                       |
          +------------+------------+
          |                         |
          v                         v
      Configuration             SQLite State
   desired structure          managed identities
          |                         |
          +------------+------------+
                       |
                       v
                Safe Sync Logic
                       |
                       v
                Discord Server
                       |
        +--------------+--------------+
        |              |              |
        v              v              v
    Semesters        Courses       Global Areas
                       |
                       v
              Course Template
                       |
         +-------------+-------------+
         |             |             |
         v             v             v
   course-chat      materials    discussions
                                      |
                                      v
                                  forum posts
                       +
                  study-room
```

---

# 86. Final Context Note

This project is expected to evolve.

The purpose of this document is not to freeze that evolution.

It exists so that a coding agent understands:

- why the project exists
- how it will actually be operated
- what the most valuable domain concepts are
- which Discord limitations matter
- which safety properties should not be accidentally lost
- why synchronization and persistent identity matter
- why the project should remain easy to modify
- why English + Hungarian documentation should be maintained

When future requirements conflict with an idea in this document, evaluate the new requirement carefully and update this document if the project's direction genuinely changes.

The application should grow from real needs rather than from speculative complexity.
