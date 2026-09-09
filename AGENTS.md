# Project instructions for coding agents

Before making architectural decisions or implementing changes, read
`docs/project-context.md` completely.

Treat that document as long-term product context, not as a fixed implementation
plan. Implement only what the current user request explicitly asks for.

When user-visible behavior changes, keep the English and Hungarian
documentation meaningfully equivalent.

Unless the user explicitly requests an exception, every Discord application
command must be restricted to server administrators. Keep the centralized
runtime authorization check, and declare administrator-only default permissions
on each top-level command or command group.
