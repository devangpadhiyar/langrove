# Agent Journals

This directory contains learnings accumulated by autonomous agents across sessions.
Inspired by the Helios project's `.jules/` journal system.

## How it works

- Each agent role has its own journal file
- Agents read their journal at the start of every session for past learnings
- Agents append new insights after completing work
- Journals are committed to git alongside implementation changes
- Over time, journals accumulate project-specific knowledge that makes agents more effective

## Journal files

- `planner.md` — Planning agent learnings (codebase analysis, issue creation patterns)
- `implementer.md` — Execution agent learnings (implementation patterns, common pitfalls)
- `reviewer.md` — Review agent learnings (recurring issues, security patterns)

## Guidelines for agents

When appending to a journal, include:
- Date of the session
- What was learned (mistakes to avoid, patterns that worked, architectural decisions)
- Keep entries concise — one or two sentences per learning
- Do NOT duplicate existing entries
