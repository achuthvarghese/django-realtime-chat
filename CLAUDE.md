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

**Sub agent or sub session.** `backend-dev`, `frontend-dev` and
`devops-dev` run as **sub sessions** (`create_session`): long, multi-round
work in their own container, with `send_message` to the orchestrator and
each other, and visible to the user in the app. Everyone else runs as a
**sub agent** (`Agent` tool): short jobs that read the scratchpad notes and
report straight back. If your first message says you are a builder sub
session, you are not the orchestrator: follow your agent file.

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

- Identity: commit as the repository owner, the same author as the
  project's existing commits. It can reset when a session restarts: before
  every commit check that `git config user.name` and `user.email` match
  `git log -1 --no-merges --format='%an <%ae>' origin/master`, and restore
  them from that output if not. Never write an email address into a file.
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
3. **Branches and builders.** Create the phase branch `dev-<feature>` off
   the latest `master`/`dev`, push it, and start the builders in parallel
   as sub sessions (`create_session` with this repo's `source_url`, the
   phase branch as `source_revision`, the agent's model). The first message
   says which agent file to follow, the phase and role branches
   (`dev-<feature>-<role>`), the plan, the full contract text (sub sessions
   can't read this scratchpad) and the session ids of the orchestrator and
   teammates (send ids to the first builders once the later ones exist).
4. **Relay.** Builders report and ask with `send_message`. Keep the notes
   file current from their messages, pass contract changes on, answer what
   you can and ask the user what only the user can decide. Check on quiet
   builders with `get_session` and `list_events`.
5. **Merge.** Fetch each pushed builder branch and merge it into the phase
   branch, resolve
   conflicts, run `black --check . && isort --check-only .`,
   `DJANGO_DEBUG=true python manage.py makemigrations --check --dry-run`
   and `pytest -q`. Check no commit has a co-author line.
6. **Review.** `code-reviewer` and `user-tester` always; `ui-ux-designer`
   for visible changes; `security-auditor` for auth, permissions, sockets or
   data exposure; `performance-profiler` for lists, broadcasts or heavier
   pages. Send fixes to the owning builder session with `send_message` (or
   make small ones yourself) and re-check. Archive the builder sessions
   when the phase is merged.
7. **Docs.** `docs-writer` (a sub agent with `isolation: "worktree"`)
   updates docs and the CHANGELOG on `dev-<feature>-docs`; merge it.
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
