# Live-room fixes (Phase 9c): agent reports, condensed

First phase built by the agent team. Details of each item are in notes.md.

## Timeline
1. Contract written (B1–B8 backend, F1–F11 frontend); backend-dev and frontend-dev started in parallel in worktrees.
2. backend-dev round 1 (B1–B8, 251 tests) merged; frontend-dev round 1 (F1–F11, 122 browser checks) merged.
3. Reviews: security-auditor (S1–S3), performance-profiler (P1–P2), ui-ux-designer (D1–D9), code-reviewer (C1–C11), user-tester (T1–T9, ~45 checks, 37 pass).
4. backend-dev rounds 2–3 (S1, S2, P1, C7, C9–C11, T3, T8, leave notice; 277 tests). frontend-dev round 2 (C1–C8, D1–D8, T1–T9, welcome pane; 151 browser checks).
5. Orchestrator fixes: refused-socket frames and events (crash on reconnect to a deleted room), resync race and first-connect resync, ping only on member changes, IMMEDIATE SQLite transactions.
6. docs-writer updated 8 docs + CHANGELOG; orchestrator updated CLAUDE.md.
7. Re-review and re-test confirmed fixes; final: 280 pytest, 151 browser checks, lock test 40/40, race 6/6. PR #22.

## Security-auditor (risk low)
S1 stale socket after a missed revoke still got edits/renames/typing (fixed: join-then-check, current-member filtering). S2 group events before commit (fixed: after-commit helpers). S3 can't edit/delete own messages after clearing history: user decided to leave for later.

## Performance-profiler
Rename 50 members 210→11 queries, 311→47 ms; 10k-message rename 1,634→55 ms; create 50 members 207→10 queries; summaries endpoint 6 queries at 3/30/300 rooms; visible_to ~free (edit fan-out 24 ms unchanged, 200 leaked frames → 0). P1 add 40 people to a 10k-message room 4.7 s → 0.24 s after grouped-query rewrite. P2 unread counter (later).

## ui-ux-designer
F1/F8/F9/F10 built as specified. Fixed: D1 wrong copy for deleted-while-offline, D3 phone notice colours, D4 aria-describedby, D5 numeric hours, D8 tablet rail names. Later: D7 live-region "Added to X", D9 44 px phone back button.

## code-reviewer
Backend correct and flat. Frontend C1 freshness by sequence not timestamp, C2 resync after failed first connect, C3–C8 races/perf, C7 room_changed on membership changes, C9 logging, C10 view race, C11 tests: all fixed. Re-review later items: room-check flag (3), still-here toast (4), day dividers at midnight (6), WebsocketCommunicator test for refused frames (7).

## user-tester
Round 1: T1–T9 (deleted-while-offline copy, preview after delete, other members' rows on edit/delete, clear history row, hidden row in search, long heading wrap, midnight refresh, initials whitespace) all fixed. Re-test: 15/16 confirmed + regression sweep 10/10; found DB-lock 500s under concurrent loads (fixed with IMMEDIATE transactions, 40/40) and early-first-connect race (fixed by resync on every connect, 6/6).

## Lessons for the next team phase
- Builders have no SendMessage; the orchestrator relays (now in CLAUDE.md).
- Agent definitions only load from the checked-out branch; merge .claude/agents to the phase branch first.
- Heredoc + stdin redirect pitfalls: write edit scripts to files.
- Start security and performance reviews as soon as the backend merges; they ran in parallel with the frontend.
