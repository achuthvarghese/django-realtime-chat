# Claude Code agents

The repository ships eleven [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
in [`.claude/agents/`](../.claude/agents/). Claude Code loads them when a
session starts in this repository. Each one knows the project's docs,
conventions and demo data.

- **Reviewers** (seven) never edit project files. They read, run checks,
  tests and the app, and **report back**. The designer and the tester write
  mockups, scripts and screenshots only to a scratchpad folder, as do the
  security auditor and performance profiler for their scripts.
- **Builders** (four) edit code and commit on their own branch. They work in
  parallel on one phase and their work lands in **one pull request** (see
  [Team workflow](#team-workflow)).

## Reviewers

| Agent | Use it for | Tools |
| --- | --- | --- |
| `ui-ux-designer` | Reviewing screens and flows for usability, accessibility (WCAG 2.2 AA), hierarchy, motion and responsive layout; suggesting improvements grounded in classic and current design styles; HTML mockups and screenshots of options | Read, search, shell, write (scratchpad only) |
| `code-reviewer` | Reviewing changes for data structures, logic and loops, error handling, logging, concurrency (async consumers, transactions, races), security and performance; runs black, isort, the migrations check and pytest | Read, search, shell |
| `user-tester` | Testing like real users in real browsers: several users at once, phone and keyboard use, offline and reconnects, double submits, odd input, permission edge cases, crafted socket frames | Read, search, shell, write (scratchpad only) |
| `security-auditor` | Auth, sessions, CSRF and Origin, permissions on every view and socket frame, data exposure (`visible_for`), XSS, open redirects, abuse limits, deploy settings, dependency audit; proof-of-concept for each finding | Read, search, shell, write (scratchpad only) |
| `performance-profiler` | Query counts and time per view, socket handler and broadcast; payload sizes; front-end long tasks with many rooms and messages; load with many sockets; numbers before suggestions | Read, search, shell, write (scratchpad only) |
| `database-designer` | Schema design for new features: fields, relations, `on_delete`, constraints, indexes for real queries, growth, migration plans (data migrations, reversibility, deploy order), SQLite vs PostgreSQL; returns model code for `backend-dev` | Read, search, shell |
| `idea-planner` | Before building: restating an idea, listing questions with options, cross-checking against the code and earlier decisions, feasibility, effort, risks, alternatives and a phased plan | Read, search, shell |

## Builders

| Agent | Area | Tools |
| --- | --- | --- |
| `backend-dev` | Models and migrations, services and group rules, presenters, views and JSON endpoints, Channels consumers and socket frames, demo data, pytest tests | Read, search, shell, edit, write |
| `frontend-dev` | Django templates, vanilla JavaScript (no jQuery, no build step), plain CSS on the Signal tokens, accessibility, responsive layouts; checks its work in Playwright | Read, search, shell, edit, write |
| `docs-writer` | Compares a phase's diff with `docs/`, README, CHANGELOG and CONTRIBUTING; updates what's stale or missing and writes the CHANGELOG entry. Edits Markdown docs only, and reports code/doc contradictions as possible bugs | Read, search, shell, edit, write |
| `devops-dev` | Dockerfile, docker-compose, GitHub Actions (e.g. browser tests in CI), production and security settings, HTTPS, Redis, setup docs. Never deploys or handles real secrets | Read, search, shell, edit, write |

Builders commit as `achuthvarghese`, with no `Co-Authored-By` lines, only on
their own branch. They never push to `master` or `dev` and never open, merge
or approve pull requests.

All eleven use the same model as the session that calls them.

## Team workflow

One phase (for example P10a replies) is built by several agents in parallel
and still lands as **one pull request**:

1. **Plan.** `idea-planner` drafts questions and a plan; you answer and
   confirm. The lead (the main session) writes the **contract** into a shared
   notes file in the scratchpad (`team/<phase>/notes.md`): model fields,
   URLs, JSON and socket frame shapes, CSS classes and `data-` hooks, error
   codes, and who owns which files. If the phase changes models,
   `database-designer` designs the schema and migrations first.
2. **Branches.** The lead creates the phase branch off `dev` (e.g.
   `dev-replies`). Each builder gets its own branch off it
   (`dev-replies-backend`, `dev-replies-frontend`, `dev-replies-devops`)
   in its own git worktree, so parallel edits never collide.
3. **Build in parallel.** Builders work only in their own area, follow the
   contract, message each other (SendMessage) when they need something, and
   log decisions, contract changes and open questions in the notes file.
   Questions for you come back through the lead.
4. **Merge.** The lead merges the builder branches into the phase branch,
   resolves any conflicts and runs the full checks.
5. **Review.** `code-reviewer`, `user-tester` and (for visible changes)
   `ui-ux-designer` review the phase branch; `security-auditor` too when the
   phase touches auth, permissions, sockets or data exposure, and
   `performance-profiler` when it adds lists, broadcasts or heavier pages.
   Fixes go back to the owning builder.
6. **One PR.** `docs-writer` updates the docs and CHANGELOG on its own
   branch; the lead merges it, pushes the phase branch and opens a single
   PR into `master`. You review and merge it; the
   lead then fast-forwards `dev`.

Small changes don't need the team: the lead builds them directly.

## Using them

Ask for one by name in a Claude Code session, for example:

- "Use the idea-planner agent to plan message replies."
- "Have the code-reviewer agent review the changes on this branch."
- "Ask the user-tester agent to try group admin flows with three users."
- "Get the ui-ux-designer agent to review the Details panel on phone and
  suggest options with mockups."

Agents can't ask you questions directly. The planner returns its questions
to the main session, which asks you and passes your answers back.

## Changing an agent

Each agent is a Markdown file: YAML front matter (`name`, `description`,
`tools`) followed by its instructions. Edit the file and start a new
session to pick up the change. Keep the reviewers' "never edit project
files" rule unless you mean to give one write access. The three builders
share the same "Working as a team" section; keep it identical in all three.
