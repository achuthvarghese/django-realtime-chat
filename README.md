# claude-memory (not code, never merge)

This branch holds Claude Code session records for Relay: decisions, plans,
the team's working notes, agent reports, design mockups and screenshots.

- **No application code lives here.** It shares no history with `master`.
- **Never merge this branch** into `master`, `dev` or any feature branch,
  and never open a pull request from it.
- The orchestrator session (see `CLAUDE.md` on `master`) adds to it at the
  end of each phase: a phase folder, an entry in `session-log.md`, and any
  agent reports or screenshots worth keeping.

## Layout

| Path | What's in it |
| --- | --- |
| `session-log.md` | Standing rules, decisions, roadmap, open questions, PR history |
| `phases/<phase>/` | The team contract and notes file, and screenshots from that phase |
| `agent-trials/` | First trial runs of the agents: reports, design mockups, test screenshots |
| `plans/` | HTML plan pages shown to the user (rework plan, P9–P11 UI plan) |
| `screenshots/` | Screenshots taken while building phases 3–9 |

Raw session transcripts are not stored here: they contain account details.

## Phases recorded

| Phase | Folder | PR |
| --- | --- | --- |
| 9c live-room fixes | `phases/live-rooms-fixes/` (contract and notes, condensed agent reports, builder/designer/tester screenshots, design mockups) | #22 |
