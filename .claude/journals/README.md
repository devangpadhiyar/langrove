# Agent Journals

This directory previously contained per-role journal files (planner.md, implementer.md, reviewer.md).

## Migration to `.claude/rules/`

Agent learnings are now stored in **topic-based `.claude/rules/` files** instead of per-role journals.
This follows the industry-standard pattern (Lore Protocol, Letta Context Repositories, Cline Memory Bank)
and uses Claude Code's native path-scoped rules for automatic context loading.

### How it works now

- Knowledge organized by domain: `database.md`, `streaming.md`, `auth.md`, etc.
- Files have `globs:` frontmatter — Claude auto-loads relevant rules when editing matching files
- All agents share all knowledge (no role silos)
- Agents append new learnings to the most relevant rules/ file after completing work
- Weekly maintenance consolidates and deduplicates entries

### Rules files

| File | Scope |
|------|-------|
| `rules/database.md` | asyncpg, JSONB, pools, migrations |
| `rules/streaming.md` | SSE format, pub/sub, event replay |
| `rules/worker-tasks.md` | Redis Streams, consumer groups, recovery |
| `rules/auth.md` | middleware, authorization, AuthUser |
| `rules/api-design.md` | FastAPI patterns, services, error handling |
| `rules/testing.md` | pytest conventions, fixtures, CI |
| `rules/architecture.md` | system design, graph loading, lifecycle |
| `rules/pipeline.md` | automation meta-learnings |
