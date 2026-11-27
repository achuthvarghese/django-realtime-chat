# P10a replies: agent reports, condensed

## Planning
- idea-planner (trial run, 2026-11-26): 13 questions; user accepted all recommendations (live privacy-safe quote, page back up to 10 pages, Reply button + composer bar, defaults).
- database-designer: `Message.reply_to` self-FK SET_NULL related_name "replies" (FK index kept); check constraints message_reply_only_text and message_reply_not_self; migration 0005 (AddField + 2 AddConstraint, reversible, SQLite rebuilds the table twice, fine); history stays 1 query/page via select_related("user", "reply_to__user") + Exists on the visible_for through table (covered by its unique index); same-room/visible/not-deleted enforced in the consumer; deferred FK means a racing hard delete raises IntegrityError at commit; broadcasts split per viewer with one query.

## Builders (sub sessions)
- backend-dev: session_01UMRWCCQy49WEP7vKSpLupX, branch dev-replies-backend
- frontend-dev: session_01UMRWCDbph9qxRW4Su6m46f, branch dev-replies-frontend

## Reviews (round 1)
- security-auditor: risk low; no leak of hidden originals on any path. RS1 before= accepted hidden ids (fixed), RS2 lookup outside atomic (fixed), RS3 same-room in queries (fixed).
- performance-profiler: nothing grows with N/history; flat queries; +~265 B per reply. PF1 .only() (−23%, done), PF4 one constraint/one table rebuild (done). Later: ?around= endpoint, per-user variant sends.
- code-reviewer: backend sound; CR1–CR3 must (reply restore, clear_room, quote rebuild) and CR4 roving tabindex — all fixed with CR5–CR10; CR-B1 error "for" field added.
- ui-ux-designer: DZ1 newest message hidden by reply bar, DZ2 quote contrast 4.47:1, DZ3 reply inside a continuation — fixed; DZ6/8/9 done; later DZ4 four-action bar (P10b), DZ7 lighter touch quote.
- user-tester: 52 checks, 47 pass; privacy clean; bugs 1–2 (reply restore), 3 (RS1), 4 (Esc in edit) fixed; add-on T1 jump-failure toast, T2 busy state, T3 refused hint, T5 sticky phone bar done; T4 not reproducible after the joined bar.

## Final re-test (orchestrator, rate limit hit the tester agent)
Tester's own scripts against a7b9972: rejected reply keeps text + hint; unrelated errors don't reopen the bar; Esc in edit keeps Details open; hidden before= → 400; privacy holds (the s3 "LEAK" lines were legitimate: sent before clearing / Arjun already in visible_for; the "unavailable" quote was for a message Arjun never could see); jumps 4/10 pages, too far back, reduced motion, double-click; transcript has 3 real Tab stops at 50 or 1,300 messages; newest message stays visible with the bar; reply rows never continue a group; quote has no fill at rest; "Finding message…" + aria-busy on slow jumps; "Couldn't find that message. Try again." on failure; phone/tablet layouts with long/emoji/RTL/HTML excerpts, no overflow, no alerts; 0 page errors, 0 server tracebacks.

## Process notes
- Builders ran as sub sessions for the first time; they messaged each other directly.
- Both builder containers reset git identity once → two "Claude"-authored commits, re-authored by cherry-pick at merge; identity check before every commit added to builder files.
- Agent rate limit (5-hour) stopped the final re-test agent; the orchestrator ran the tester's scripts itself.
