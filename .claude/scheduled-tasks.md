# Scheduled Tasks Setup

This file contains the prompts and configuration for the 3 Claude Desktop scheduled tasks
that power the autonomous development pipeline.

## Setup Instructions

1. Run `.github/scripts/setup-labels.sh` to create all required GitHub labels
2. Open **Claude Desktop → Settings → Scheduled Tasks → New Task**
3. Create each task below with the specified schedule and prompt
4. Keep your Mac awake (tasks run locally)

See `.claude/rules/pipeline.md` for how the label state machine works.

---

## Task 1: Langrove Pipeline

**Name:** `Langrove Pipeline`  
**Schedule:** `0 */2 * * *` (every 2 hours)  
**Working directory:** _(path to this repo)_

> Picks up the next open issue and drives it from `triage` → `planned` → `in-progress` → `review` → `done`.

**Prompt:**
```
You are the Langrove autonomous development pipeline. Run the following steps:

1. GUARD: Check if any GitHub issue has the label 'in-progress':
   gh issue list --label "in-progress" --state open --repo devangpadhiyar/langrove
   If yes, check its linked PR:
   - PR merged → remove 'in-progress', add 'done'
   - PR open + has review REQUEST_CHANGES → remove 'in-progress' is already done; address the comments, push fixes to the existing branch
   - PR open + approved → it will merge on its own; stop
   - No PR exists and issue has been 'in-progress' >1 hour → remove 'in-progress', reset to 'triage'
   Then stop.

2. TRIAGE: Find open issues with both 'claude' and 'triage' labels:
   gh issue list --label "claude,triage" --state open --repo devangpadhiyar/langrove --json number,title,labels
   - Skip any labeled 'complexity:large' unless also labeled 'force-auto'
   - Pick highest priority: bugs before features, complexity:small before medium
   - If none found, stop.

3. PLAN (Architect role):
   - Read .claude/rules/ files relevant to the issue topic
   - Read CLAUDE.md for project principles
   - Read the issue description and acceptance criteria
   - Identify and read ALL files that need to change
   - Estimate complexity and diff size
   - Post a structured Implementation Plan as an issue comment (see format in .claude/agents/architect.md)
   - Change labels: remove 'triage', add 'planned' + appropriate complexity:* label
   - Append any new learnings to the most relevant .claude/rules/ file

4. IMPLEMENT (Implementer role):
   - Change labels: remove 'planned', add 'in-progress'
   - Read relevant .claude/rules/ files
   - Read the Implementation Plan comment posted in step 3
   - NEVER push directly to main. Create a new branch off main:
     git checkout main && git pull && git checkout -b claude/{issue-number}-{short-slug}
   - Implement changes following the plan exactly
   - Write tests for all new/changed functionality
   - Run: uv run ruff check . && uv run ruff format . && uv run pytest
   - Fix any failures (up to 3 retry cycles)
   - If diff exceeds 500 lines: remove 'in-progress', add 'blocked' + 'human-review-required', post a comment explaining why, stop
   - Append any new learnings to the most relevant .claude/rules/ file
   - Commit all changes (including rules/ updates) on the feature branch
   - Push the branch and open a PR targeting main with "Closes #{issue-number}" in the description
   - Change labels: remove 'in-progress', add 'review'

5. REVIEW (Reviewer role):
   - Read relevant .claude/rules/ files
   - Review the PR diff using the checklist in .claude/agents/reviewer.md
   - If issues found: post inline comments, submit REQUEST_CHANGES review, remove 'review', add 'in-progress'
   - If acceptable: submit APPROVE review, remove 'review', add 'done'
   - After 2 review cycles with unresolved issues: remove 'review', add 'human-review-required', stop
   - Append any new learnings to the most relevant .claude/rules/ file

6. Push all .claude/rules/ updates if any were modified.

Use gh CLI with --repo devangpadhiyar/langrove for all GitHub operations.
```

---

## Task 2: Langrove Maintenance

**Name:** `Langrove Maintenance`  
**Schedule:** `0 6 * * 0` (Sunday 6am)  
**Working directory:** _(path to this repo)_

> Keeps the repo healthy: consolidates `.claude/rules/` knowledge, checks for stale PRs/branches, and verifies docs are up to date.

**Prompt:**
```
Perform weekly maintenance on the Langrove project:

1. Review all .claude/rules/ files:
   - Remove duplicate entries
   - Consolidate related learnings into cleaner statements
   - Remove entries that no longer match the current code
   - Keep each entry concise (1-2 sentences)

2. Check for outdated dependencies:
   uv pip list --outdated

3. Verify CLAUDE.md project structure section matches the actual src/langrove/ layout.
   Update if anything has changed.

4. Find and close stale claude/* branches (open PRs older than 7 days with no activity):
   gh pr list --state open --repo devangpadhiyar/langrove --json number,headRefName,updatedAt
   For stale ones: gh pr close {number} --comment "Closing stale automated PR. Issue reset to triage." --repo devangpadhiyar/langrove
   Reset the linked issue label back to 'triage'.

5. For any file changes: create a branch `claude/maintenance-{date}` off main, commit, push,
   and open a PR targeting main. Never push directly to main.

Use gh CLI with --repo devangpadhiyar/langrove for all GitHub operations.
```

---

## Task 3: Langrove Issue Creator

**Name:** `Langrove Issue Creator`  
**Schedule:** `0 8 * * 1` (Monday 8am)  
**Working directory:** _(path to this repo)_

> Scans the codebase for TODOs, feature gaps, and missing test coverage, then files up to 3 well-scoped GitHub issues ready for the pipeline to pick up.

**Prompt:**
```
Analyze the Langrove codebase and create GitHub issues for gaps found:

1. Read .claude/rules/ files and CLAUDE.md for context on the project

2. Scan the codebase for:
   - TODO / FIXME / HACK comments in src/
   - Features mentioned in README.md that are not yet implemented
   - Missing test coverage in tests/ for important code paths

3. Check existing open issues to avoid duplicates:
   gh issue list --state open --repo devangpadhiyar/langrove --json number,title

4. For each gap found (up to 3 total), estimate complexity first:
   - complexity:small  — single file, <100 lines
   - complexity:medium — multiple files, same module, 100-300 lines
   - complexity:large  — cross-module, >300 lines (pipeline will skip unless force-auto)

   Then create the issue:
   gh issue create \
     --repo devangpadhiyar/langrove \
     --title "..." \
     --body "## Description\n...\n\n## Acceptance Criteria\n- ...\n\n## Relevant Files\n- ..." \
     --label "claude,triage,{complexity:small|complexity:medium|complexity:large}"

   Only create issues for clear, actionable, well-scoped tasks.

5. For any file changes (including rules/pipeline.md updates): create a branch
   `claude/issue-creator-{date}` off main, commit, push, and open a PR targeting main.
   Never push directly to main.

Use gh CLI with --repo devangpadhiyar/langrove for all GitHub operations.
```

---

## Label Reference

| Label | Color | Meaning |
|-------|-------|---------|
| `triage` | `#d4c5f9` | Awaiting pipeline pickup |
| `planned` | `#0e8a16` | Architect posted implementation plan |
| `in-progress` | `#fbca04` | Implementer agent working |
| `review` | `#1d76db` | PR open, reviewer checking |
| `done` | `#0e8a16` | Merged and closed |
| `blocked` | `#b60205` | Requires human intervention |
| `human-review-required` | `#e11d48` | Must not auto-merge |
| `force-auto` | `#5319e7` | Override complexity:large gate |
| `complexity:small` | `#c5def5` | <100 lines, single file |
| `complexity:medium` | `#bfd4f2` | Multi-file, same module |
| `complexity:large` | `#0075ca` | Cross-module, >300 lines |

## Adjusting for a Different GitHub Account

Replace all occurrences of `devangpadhiyar/langrove` with your `{username}/{repo}`.
Ensure `gh auth status` shows your account as active before running any tasks.
