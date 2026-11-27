# Agent trial runs (2026-11-26)

Each reviewer ran once on real work; feedback on its own instructions was
folded into the agent files in PR #21.

## idea-planner: P10a replies

Verdict: go with changes. One FK `Message.reply_to` (SET_NULL); quote shows
the original as it is now ("Message deleted" if deleted; "Original message
unavailable" for viewers who can't see it, never leaking cleared or
pre-join history); Reply in a shared per-message action bar (reused by P10b
reactions); composer "Replying to …" bar, Esc cancels (innermost-first
Escape rule); jump to original pages back with `?before=` up to ~10 pages.
13 questions with recommended answers (Q1 text messages only, Q2 edit
changes text only, Q3 live quote, Q4 page back, Q5 nothing new, Q6
unavailable quote, Q7 server rejects hidden targets, Q8 deleted placeholder,
Q9 SET_NULL, Q10 action bar, Q11 composer bar with Esc, Q12 preview
unchanged, Q13 200-char excerpt). Found the edit-broadcast leak (fixed in
Phase 9c, B6).

## code-reviewer: Phase 9b diff

Important: per-member `rooms_for` in live_rooms (210 queries for a
50-member rename); `on_commit` sends not robust (Redis failure after commit
→ 500, retry duplicates the group; no logging). Minor: live rows lost
relative times and truncation; `fetchRoom` without catch; fetch vs
`room_removed` race; no resync on reconnect; new rows ignored the search
filter; presence lag on new direct chats; import inside a function. All
became Phase 9c items B1–B8 / F1–F11.

## ui-ux-designer: gone pane and slide-in

Gone pane loses context (no chat name, header removed), status not
announced (focus jumped to the button), tab title stale, button under 44px
on phones, straight apostrophes. Recommended Option A (muted header kept,
chat named, heading focused). Slide-in: rows below jump; proposed height
growth plus fading accent tint. Mockups in `agent-trials/design/`.

## user-tester: group flows with three users

51 checks passed (create, add, rename, admins, remove while open, last
admin leaves, delete, two tabs, offline then added, double-click create,
`<script>` and `<img onerror>` names shown as text, crafted POSTs). Bugs:
reloading a removed room gave a bare 404 (fixed in 9c, B5); initials of
punctuation-led names (fixed, B7). Friction: groups added while
disconnected stay hidden until a message arrives (fixed, F5). Screenshots
in `agent-trials/qa/`.
