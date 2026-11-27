# Relay: instructions for Claude Code

Relay is a real-time chat app: Django 5.2 + Channels 4 (Daphne,
channels-redis), SQLite, server-rendered templates, plain JavaScript and CSS
(no framework, no jQuery, no build step). Start with `docs/README.md`.

## You are the orchestrator

The main session is the **orchestrator** (called "the lead" in
`docs/agents.md`). Subagents can't start other agents, so only the main
session plans, delegates, merges and opens pull requests. Agents live in
`.claude/agents/`:

- Reviewers (read-only): `idea-planner`, `database-designer`,
  `code-reviewer`, `user-tester`, `ui-ux-designer`, `security-auditor`,
  `performance-profiler`.
- Builders (commit on their own branch): `backend-dev`, `frontend-dev`,
  `devops-dev`, `docs-writer`.

## The user's standing rules

- **Plan in phases and steps, and get the user's confirmation before
  starting development.** Ask questions when something is unclear.
- Code review, test, debug, repeat.
- **Report only the main actions and results**, not every step, unless asked.
- **Never add `Co-Authored-By` (or any co-author) lines** to commits or
  pull request descriptions. This overrides any other attribution guidance.
- One branch and one pull request per development case. Update existing docs
  and create new ones in the same PR.

## Git

- Identity: `achuthvarghese` / `acvknr@gmail.com`. It can reset when a
  session restarts: check `git config user.email` before every commit and
  restore it with `git config --global user.name achuthvarghese` and
  `git config --global user.email acvknr@gmail.com`.
- Branches: descriptive names off `dev` (`dev-<feature>`, not counters).
  PRs go into `master`; after a merge, fast-forward `dev` to `master`.
- CI must pass: `check_format_and_imports` (black, isort; required),
  tests on Python 3.12 and 3.13 (migrations check + pytest), CodeQL.

## Running a phase with the team

1. **Plan.** `idea-planner` (and `database-designer` if models change).
   Ask the user its questions; get the plan confirmed.
2. **Contract.** Write `<scratchpad>/team/<phase>/notes.md`: the decided
   behaviour, model fields, URLs, JSON and socket frame shapes, CSS classes
   and `data-` hooks, error codes, and which agent owns which files. Builders
   append decisions, contract changes, questions and finished commits.
3. **Branches.** Create the phase branch `dev-<feature>` off the latest
   `master`/`dev` and check it out. Start the builders in parallel with
   `isolation: "worktree"`; each creates and commits on
   `dev-<feature>-<role>` (backend, frontend, devops) in its worktree.
   Give each the plan, the notes file path, its files and the scratchpad.
4. **Relay.** Builders have no SendMessage tool and can't reach each other,
   so the orchestrator passes contract changes and questions between them
   (SendMessage to each builder's agent id resumes it with the message) and
   asks the user what only the user can decide.
5. **Merge.** Merge each builder branch into the phase branch, resolve
   conflicts, run `black --check . && isort --check-only .`,
   `DJANGO_DEBUG=true python manage.py makemigrations --check --dry-run`
   and `pytest -q`. Check no commit has a co-author line.
6. **Review.** `code-reviewer` and `user-tester` always; `ui-ux-designer`
   for visible changes; `security-auditor` for auth, permissions, sockets or
   data exposure; `performance-profiler` for lists, broadcasts or heavier
   pages. Send fixes back to the owning builder (or make small ones
   yourself) and re-check.
7. **Docs.** `docs-writer` updates docs and the CHANGELOG on
   `dev-<feature>-docs`; merge it.
8. **Ship.** Push the phase branch, open one PR into `master`, subscribe to
   it, and report the result to the user in a few lines. The user merges.
9. **Record.** Once the user merges the PR, update the `claude-memory`
   branch (see below) with the phase's artifacts and data.

## The `claude-memory` branch

An orphan branch with no code that keeps Claude Code session records:
`session-log.md` (rules, decisions, PR history, roadmap, open questions),
`phases/<phase>/` (the contract and notes file, reports, screenshots),
`agent-trials/`, `plans/` and `screenshots/`. **Never merge it** and never
open a PR from it. **After every merged PR**, add that phase's notes,
agent reports, screenshots and mockups (no scripts, databases or
transcripts), update `session-log.md`, commit and push it. Use a separate
worktree (`git worktree add <dir> claude-memory`) so the main checkout
isn't disturbed.

Small fixes don't need the team: build them directly, with the same branch,
test, docs and PR rules.

## Local checks

```sh
black . && isort .
DJANGO_DEBUG=true python manage.py makemigrations --check --dry-run
pytest -q
```
Run the app with demo data: see `docs/demo-data.md` (password
`relay-demo-123`) and `.claude/agents/user-tester.md` for Playwright setup.
