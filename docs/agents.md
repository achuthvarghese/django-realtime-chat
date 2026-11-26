# Claude Code agents

The repository ships four [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
in [`.claude/agents/`](../.claude/agents/). Claude Code loads them when a
session starts in this repository. Each one knows the project's docs,
conventions and demo data.

None of them edit project files. They read, run checks, tests and the app, and
**report back**. Changes are made afterwards, once you've confirmed them. The
designer and the tester write mockups, scripts and screenshots only to a
scratchpad folder (or `/tmp/relay-design/` and `/tmp/relay-qa/`).

| Agent | Use it for | Tools |
| --- | --- | --- |
| `ui-ux-designer` | Reviewing screens and flows for usability, accessibility (WCAG 2.2 AA), hierarchy, motion and responsive layout; suggesting improvements grounded in classic and current design styles; HTML mockups and screenshots of options | Read, search, shell, write (scratchpad only) |
| `code-reviewer` | Reviewing changes for data structures, logic and loops, error handling, logging, concurrency (async consumers, transactions, races), security and performance; runs black, isort, the migrations check and pytest | Read, search, shell |
| `user-tester` | Testing like real users in real browsers: several users at once, phone and keyboard use, offline and reconnects, double submits, odd input, permission edge cases, crafted socket frames | Read, search, shell, write (scratchpad only) |
| `idea-planner` | Before building: restating an idea, listing questions with options, cross-checking against the code and earlier decisions, feasibility, effort, risks, alternatives and a phased plan | Read, search, shell |

All four use the same model as the session that calls them.

## Using them

Ask for one by name in a Claude Code session, for example:

- "Use the idea-planner agent to plan message replies."
- "Have the code-reviewer agent review the changes on this branch."
- "Ask the user-tester agent to try group admin flows with three users."
- "Get the ui-ux-designer agent to review the Details panel on phone and
  suggest options with mockups."

Agents can't ask you questions directly. The planner returns its questions
to the main session, which asks you and passes your answers back.

## Typical flow for a phase

1. **idea-planner**: questions, then a phased plan. You confirm it.
2. Build the phase.
3. **code-reviewer** and **user-tester** on the branch; **ui-ux-designer**
   for anything visible.
4. Fix what you agree with, then open the pull request.

## Changing an agent

Each agent is a Markdown file: YAML front matter (`name`, `description`,
`tools`) followed by its instructions. Edit the file and start a new
session to pick up the change. Keep the "never edit project files" rule
unless you mean to give an agent write access.
