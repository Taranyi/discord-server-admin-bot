# Project instructions for coding agents

Before making architectural decisions or implementing changes, read
`docs/project-context.md` completely.

Treat that document as long-term product context, not as a fixed implementation
plan. Implement only what the current user request explicitly asks for.

When user-visible behavior changes, keep the English and Hungarian
documentation meaningfully equivalent.

Treat `README.md` and `README.hu.md` as the canonical user manuals. In the same
change that introduces or modifies user-visible behavior, update both manuals
with all relevant commands, prerequisites and Discord permissions,
configuration, examples, side effects, safety properties, testing steps, and
troubleshooting information.

Maintain a meaningfully equivalent "Roadmap and future candidates" section in
both manuals as durable project memory. Record worthwhile future ideas there so
they are not lost, but do not treat them as approved work or a fixed plan. Do
not silently remove an idea: when it is implemented, move it into the current
feature documentation and update its roadmap status; when it is rejected or
superseded, record that decision unless the user explicitly requests removal.

The bot is an on-demand administration tool, not an always-on service. Never
design correctness around the process having observed every Discord event.
Administrators may change the server while the bot is running or offline, so
each management operation must resolve stable IDs against current Discord state
and handle drift conservatively. Offline manual changes must result in safe
adoption, a clear warning, or a non-destructive refusal after the next sync—never
blind overwrite, duplicate creation, or deletion of surprising resources.

Unless the user explicitly requests an exception, every Discord application
command must be restricted to server administrators. Keep the centralized
runtime authorization check, and declare administrator-only default permissions
on each top-level command or command group.
