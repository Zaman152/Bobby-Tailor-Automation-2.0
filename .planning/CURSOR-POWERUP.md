# Cursor Power-Up — 2026-05-26

| Step | Status |
|------|--------|
| CodeGraph | done |
| GitNexus | done |
| Cursor rules | 3 rules in .cursor/rules/ |
| .gitignore | updated |

## Agent instructions

- Prefer CodeGraph/GitNexus MCP tools over blind grep when exploring structure.
- Use global skills from ~/.cursor/skills/ (security, performance, clean-code).
- Persist decisions via agentmemory MCP when the server is running.
- Follow .cursor/rules/ for style on matching files.
- GSD artifacts live in .planning/ — read PROJECT.md and STATE.md before large changes.

## User reminders

- Global: `agentmemory` running, `GITHUB_PERSONAL_ACCESS_TOKEN` for GitHub MCP
- Re-index after major refactors: automatic on `/gsd-execute-phase`; manual: `bash ~/.cursor/get-shit-done/scripts/cursor-powerup-reindex.sh`
