# Phase: live-rooms fixes (branch `dev-live-rooms-fixes`)

Fixes for Phase 9b (live room list) found by the code-reviewer, user-tester
and ui-ux-designer trials, plus one privacy fix. The user confirmed the scope.
Base: `master` at 47f22a7. One PR. CHANGELOG heading: `## Phase 9c: live-room fixes`.

## Owners

| Agent | Branch | Files |
| --- | --- | --- |
| backend-dev | `dev-live-rooms-fixes-backend` | `chat/live_rooms.py`, `chat/presenters.py`, `chat/views.py`, `chat/urls.py`, `chat/channels/consumers.py`, `chat/tests.py` |
| frontend-dev | `dev-live-rooms-fixes-frontend` | `chat/static/chat/js/*.js`, `chat/static/chat/css/chat.css`, `chat/templates/chat/*.html` |
| docs-writer | `dev-live-rooms-fixes-docs` | docs, README, CHANGELOG (after merge) |

## Backend items (B)

- **B1: rename sends one frame.** `room_changed(room)` sends **one** frame
  to all members (no per-member `rooms_for`). Frame (unchanged type, partial
  room object; only these keys):
  `{"type": "room_changed", "room": {"id": "<uuid>", "title": "<name>", "initials": "<XX>", "member_count": 3, "member_usernames": [...]}}`
  Only sent for groups (direct rooms are never renamed).
- **B2: room_added is query-flat.** Building `room_added` summaries for N
  users must use a constant number of queries (not ~4 per user). Same frame
  and full room object as before. Add `CaptureQueriesContext` tests for
  `create_group_room` with 2 vs 50 members, `add_members` with 1 vs 40 new
  people, and `rename` with 3 vs 50 members: the query count must not grow
  with N.
- **B3: one failed send never breaks the request.** Each inbox/room send in
  `live_rooms` is wrapped: catch `Exception`, `logger.warning(...)` with room
  id and user pk (no names or message text), continue with the next
  recipient. The view still returns success. Tests: patch
  `realtime.send_to_inbox` to raise → `create_group_room` returns the room,
  others still get frames, a warning is logged; no frames when the
  transaction rolls back (e.g. a `GroupError` raised after queuing).
- **B4: full list for resync.** New `GET /chat/rooms/summaries/`
  (`chat:summaries`, login required) →
  `{"rooms": [<room object>, ...]}`, same objects as `/summary/`, most
  recent first. Must be query-flat in the number of rooms (test with 3 vs
  30 rooms).
- **B5: removed or unknown room in the URL.** `/chat/?room=<id>` for a room
  the user isn't in (or that doesn't exist, or a bad id) **redirects to
  `/chat/`** with an info notice "That chat isn't available. You may have
  been removed, or it was deleted." (Django messages, level info). Same text
  for unknown and forbidden (no existence leak). Other endpoints keep their
  404s.
- **B6: edit/delete frames respect visibility.** `message_updated` frames
  (edit and delete) must only reach sockets whose user is in the message's
  `visible_for`. Approach is yours (e.g. include allowed user pks in the
  event and filter in `chat_response`, never sending them to the client).
  Tests: a member who cleared history, and a member added after the message,
  get no `message_updated` for it; others do. Check other per-room
  broadcasts for the same leak and report.
- **B7: initials skip punctuation.** `initials()` uses the first letter or
  digit of each word, ignoring other characters; fallback "?".
  `"<img src=x onerror=alert(2)>"` → `"IS"`, `"maya"` → `"MA"`,
  `"Maya Rao"` → `"MR"`, `"@lee"` → `"LE"`, `"!!!"` → `"?"`. frontend-dev
  mirrors it in JS.
- **B8:** move the `room_summary` import in `chat/views.py` to the top.

## Frontend items (F)

- **F1: one time formatter for room rows.** Rows built or updated by
  inbox.js show time exactly like server rows (today → clock, yesterday →
  "Yesterday", older → short date), set `datetime` and `title` (full date),
  and `data-relative`. Previews truncated to 60 characters like the
  template's `truncatechars:60` (59 chars + "…").
- **F2: partial room_changed.** Apply only the keys present in the frame
  (B1). Never touch preview/time/unread from `room_changed`.
- **F3: fetch errors.** Every fetch has `catch` with `console.warn` and
  context; no unhandled rejections.
- **F4: no resurrected or stale rows.** Keep a `removed` set: after
  `room_removed`, ignore later `room_added`/summary results for that id
  unless a newer `room_added` frame arrives (a re-add clears it). A
  fetched summary never overwrites a newer preview (compare `last_at`).
- **F5: resync on reconnect.** On inbox socket `open` **after a reconnect**
  (not the first connect), fetch `GET /chat/rooms/summaries/` (B4) and
  reconcile: add missing rows, remove rows not in the list (if the open room
  is gone, show the gone pane), update titles/previews/unread.
- **F6: search filter.** After any add/remove/update of rows, re-apply
  the "Find a chat" filter and the "No chats match" note. Use a
  `relay:rooms-changed` event that chat.js listens to (inbox.js owns the
  list; chat.js owns search).
- **F7: presence on new rows.** After `room_added`, send `{"type": "ping"}`
  on the inbox socket; the server replies with a fresh `presence_snapshot`
  (contacts are recomputed per ping — backend: confirm).
- **F8: gone pane (designer Option A).** Keep a muted room header (avatar
  at reduced opacity, title, "Not a member" or "Deleted" in place of the
  member count, no Details button, phone back arrow kept). Heading names
  the chat: "You’re no longer in <title>" / "<title> was deleted". Body:
  "You were removed or left, so you can’t read or send messages here any
  more. Ask a member to add you back." (curly apostrophes); deleted copy
  unchanged apart from curly quotes. Focus the heading (`tabindex="-1"`,
  no outline on it) instead of the button. Set `document.title` to
  "No longer in <title> · Relay" / "<title> was deleted · Relay", then
  keep the unread prefix logic working. Button min-height 44px on
  `(pointer: coarse)` or phone width. Only one `h1` on the page (header
  title becomes a `p` or the gone heading is the h1, your call).
- **F9: slide-in (designer proposal).** New row grows its height
  (grid-template-rows 0fr → 1fr, ~200ms, `cubic-bezier(.2,0,0,1)`), content
  fades in, then an accent tint
  (`color-mix(in srgb, var(--accent) 22%, transparent)`) fades out over
  ~1.6s. Respect `prefers-reduced-motion` (no animation, tint only briefly
  or none).
- **F10: notice for unavailable chat.** Make sure the B5 notice is visible
  on `/chat/` with no room open (desktop and phone).
- **F11: initials in JS** match B7.

## Decisions log
(append: date, agent, decision)

- 2026-11-27, backend-dev, F7/B6: confirmed. `InboxConsumer.send_snapshot()` calls `presence.contacts_of(user)` fresh on every ping, so a `ping` after `room_added` returns a snapshot that includes the new room's members. Test: `TestPingRefreshesContacts`.
- 2026-11-27, backend-dev, B7/F11 rule (for the JS mirror): split on whitespace; strip every character that isn't a letter or digit from each word (Python `str.isalnum`, JS `/[\p{L}\p{N}]/u`); drop words left empty. 2+ words: first char of the first two words. 1 word: its first two chars. None: "?". Uppercase. Extra cases: `"--- Lee"` → `"LE"`, `"(Design) team"` → `"DT"`, `"Q3 2026"` → `"Q2"`, `"!!! ???"` → `"?"`.
- 2026-11-27, backend-dev, B1: `room_changed` is only sent for groups; payload built once from a fresh read at commit time; member order is DB order (don't rely on it).
- 2026-11-27, backend-dev, B5: `/chat/?room=` now redirects (302 to `/chat/`) for bad id, unknown, deleted and non-member rooms with `messages.info` "That chat isn't available. You may have been removed, or it was deleted." (`chat.views.ROOM_UNAVAILABLE`). Other endpoints still 404. Updated `core/tests.py` site-404 test to use the details endpoint.
- 2026-11-27, backend-dev, B6 approach: `chat_response` events may carry `visible_to` (list of user pks); `ChatConsumer.chat_response` drops the frame for sockets whose user isn't listed and never forwards the key. Used for `message_updated` (edit/delete, from the message's `visible_for`), user `save_message` and system `save_message` (`realtime.broadcast_frame(..., visible_to=...)`, used in `groups.system_message`). Also `own_message` now requires the sender to still see the message (can't edit/delete a message you cleared; 403 as before).
- 2026-11-27, backend-dev, B6 audit of other per-room broadcasts: `save_message` was already only visible-for-all-members, but a removed member's socket received the "X removed Y" system message before its close; now filtered. `typing` and `room_updated` (name, member count) still go to every socket in the room, including a just-removed member's socket before it closes: no message content, left as is. `clear_room` goes only to the requester. Inbox `room_activity` goes to members only (all in `visible_for`). No other leaks found.

- 2026-11-27, frontend-dev, F4: removals and adds carry a sequence number. A fetched summary (single row or resync list) is ignored only if the room was removed *after* the fetch started; a fetch started after a removal is newer than it, so its result is accepted (the server only returns rooms you're in). Same effect as "ignore until a newer room_added" without losing rows re-added while a frame was missed.
- 2026-11-27, frontend-dev, new page events (all on `document`, inbox.js owns the list and the tab title): `relay:rooms-changed` (inbox.js -> chat.js re-applies search), `relay:room-message` {room, message, moveToTop} (chat.js -> inbox.js, open room's preview), `relay:room-gone` {room, deleted} (inbox.js resync -> chat.js gone pane), `relay:base-title` {title} (chat.js -> inbox.js, gone pane and rename). `relay:room-updated` now carries `initials`. Row-time formatting moved from chat.js to inbox.js.
- 2026-11-27, frontend-dev, F8: the gone heading is the page's h1; the header title is swapped to a `p` with the same class. Pane markup is a `<template id="gone-template">` in chat.html (icons for removed/deleted), text filled with textContent.
- 2026-11-27, frontend-dev, F10: with no room open, notices render twice: in the main pane (desktop/tablet) and in the list pane (`.chat-notices--side`, phones only, since the main pane is hidden there). Only one is ever displayed.
- 2026-11-27, frontend-dev: the "Find a chat" box is now always rendered (hidden when the list is empty), so it appears once a first room arrives live.

- 2026-11-27, backend-dev, S1: ChatConsumer.connect() joins the group first, then checks membership; if the check fails it discards the group, refuses, and ignores any events queued before the discard. message_updated `visible_to` = visible_for and current member; room_updated `visible_to` = current member pks. typing has no per-frame check, as agreed.
- 2026-11-27, backend-dev, S2: new `realtime.send_to_room_after_commit` / `broadcast_frame_after_commit`. They use on_commit, keep queue order and log failures (logger `chat.realtime`, event type and room id only). Used for system messages, membership.revoked, room_updated and also `room.deleted` (it had the same pre-commit problem). Order on remove: system message, revoke, room_updated.
- 2026-11-27, backend-dev, notice: ROOM_UNAVAILABLE uses a curly apostrophe ("isn’t").
- 2026-11-27, backend-dev, P1: room_summaries_for_users is set-based: 7 queries regardless of recipients or history. Bench on perf/after.sqlite3: 40 newcomers / 10k history 243 ms (was 4.7 s), output equal to the prototype. A difference from the prototype: the latest message is picked from each person's own visibility rows, not by created_at alone. The prototype could show a same-timestamp message the person can't see. Ties go to the highest message id, and rooms_for now orders `-created_at, -id` so room_summary agrees. No joined_at bound. P2 untouched.
- 2026-11-27, backend-dev, C9: live_rooms logs one warning per action: frame type, room id, count failed / total, the failed user pks, and the exception class. Build failures log with exc_info.
- 2026-11-27, backend-dev, C10: chat() uses next(..., None) and redirects with ROOM_UNAVAILABLE.
- 2026-11-27, backend-dev, S3 left as is (user decision).

- 2026-11-27, backend-dev, T3: `room_refresh` recipients are the same list as message_updated's `visible_to`: people who can see the message and are still members. Sent through `live_rooms.room_refresh` with on_commit; failed sends are logged once per action. The InboxConsumer handler forwards `{"type": "room_refresh", "room": "<uuid>"}`. Sent once per edit and once per delete.
- 2026-11-27, backend-dev, T8: handle_read catches OperationalError and logs a warning with room id and user pk (no error text); the socket stays open. Settings: sqlite `OPTIONS = {"timeout": 20}`.
- 2026-11-27, backend-dev, UX: the leave JSON response also queues `messages.success("You left <name>.")`, same text as the redirect path. Other JSON actions (including delete) still queue no notice.

- 2026-11-27, frontend-dev, round 2: C1 freshness uses a per-room live-update sequence (touchedAt) compared with the fetch's start; room_added frames are treated as live (always applied). C2: resync on every inbox open except a first one within 3 s of page load. C5/D1: `relay:room-check` (inbox.js -> chat.js) replaces `relay:room-gone`; chat.js reconnects the room socket. The server accepts for a moment before a 4403/4404 refusal, so an open socket counts as "still a member" only after it stays open 1 s (then `relay:room-still-here` -> inbox.js refetches the row). No refusal within 3 s -> removed copy. New events: `relay:room-refresh` {room} (chat.js -> inbox.js after message_updated and clear_room).
- 2026-11-27, frontend-dev, D8: instead of aria-labels, the rail keeps the row text and the New chat label visually hidden (not display:none), so links keep their full name (title, preview, unread). Room avatars are aria-hidden, so names start with the title.
- 2026-11-27, frontend-dev, D5: only row times (inbox.js) use hour "numeric"; transcript times in chat.js unchanged.
- 2026-11-27, frontend-dev, for backend-dev (found in browser checks): `ChatConsumer.receive` raises AttributeError (`self.room` is None) when a client sends a frame on a socket that `reject()` accepted briefly before closing 4404 (seen with `{"type":"read"}` on open). The client no longer sends during a membership check, but a normal reconnect to a deleted room still sends `read` on open. Suggest: ignore frames in receive() when the socket was rejected (`self.room is None` or not a member).

## Contract changes
- 2026-11-27, orchestrator: new inbox frame room_refresh {room} on edit/delete (T3); backend sends, frontend fetches /summary/.
(append: date, agent, change, who must adapt)

- 2026-11-27, backend-dev, C7: `room_changed` is now also sent on add, remove and leave (same partial frame as B1: `id`, `title`, `initials`, `member_count`, `member_usernames`). Recipients are the members at commit time. On add, the newcomers are left out (they get `room_added`). On remove and leave, the person who went gets `room_removed` only. No `room_changed` when the last member leaves (group deleted). frontend-dev: update roomMembers from `member_usernames` and ping for presence. Not messaged directly: I have no SendMessage tool, so the lead needs to pass this on.


## Review round 1: security-auditor (backend a7f2535)

Risk low. B6 works in the normal flow; summaries endpoint, redirect and logging fine.
- **S1 (low, leak confirmed):** a room socket that missed its revoke (connect race, or a dropped group_send) still gets message_updated text for old messages, room_updated and typing. PoC: security/poc/test_poc.py.
- **S2 (low, existed before):** system_message, announce_room_changed and revoke_access send before commit (inside atomic).
- **S3 (info, product):** after clearing history a sender can't edit or delete their own messages that others still see (own_message requires visible_for).
- Verdict on typing/room_updated: room_updated gets visible_to = current members; typing is covered by fixing the connect order and on_commit.


## Review round 1: performance-profiler (backend a7f2535)

B1/B2/B4/B6 targets met (rename 50 members: 210 → 11 queries, 311 → 47 ms; 10k-msg rename 1,634 → 55 ms; summaries endpoint 6 queries at 3/30/300 rooms; visible_to ≈ free).
- **P1 (M):** room_summaries_for_users cost grows with recipients × room history: add 40 people to a 10k-message room = 4.7 s (existed before). Set-based rewrite (~6 flat queries) prototype gives identical output in 0.26 s: perf/proto.py.
- P2 (L, later): unread counts linear in unread messages; per-user counter on ReadState if it matters.


## Review round 1: ui-ux-designer (84fa2f9)

F1, F8, F9, F10 verified as specified (all sizes, light/dark, contrast, focus, reduced motion).
Fix before ship:
- **D1:** inbox.js reconcile() dispatches relay:room-gone deleted:false for the open room missing from the resync, so a room deleted while offline says "removed… ask a member" and the later 4404 is ignored. Fix (a): for the open room only remove the row; let the room socket's close code (4403/4404) choose the copy.
- **D2 (docs-writer):** docs/screens.md (~95-97, ~138-140) old gone flow; docs/design-system.md:146 reduced motion wording ("removes movement; short colour fades may stay").
- **D3:** phone notice (.chat-notices--side) white on dark column: use --chrome-raised / --chrome-strong / border color-mix(--chrome-fg 18%). Mockup design/mockups/side-notice.html.
- **D4:** gone heading aria-describedby → gone text.
- **D5:** timeFormat hour "numeric" not "2-digit".
- **D8 (a11y, WCAG 4.1.2):** tablet rail: New chat button and room links need aria-labels (room title).
Later: D6 midnight refresh of row times; D7 live-region "Added to X"; D9 phone back button 44px.


## Review round 1: code-reviewer (84fa2f9)

Backend correct, flat (room_summaries_for_users equals room_summary in a rich scenario: review/test_summaries_equal.py).
Frontend (inbox.js):
- **C1 (important):** applyActivity skips updates when fetched last_at is older/null, but last_at legitimately goes back (last message deleted, history cleared) → deleted text and stuck unread stay after resync. Decide freshness by a live-activity sequence (touchedAt per room vs fetch start), not timestamps; same in reconcile's fresher check.
- **C2 (important):** resync only after a previous successful connect; if the first connect fails, frames missed since page render are never recovered. Resync on every open except one shortly after load (or always).
- C3: a reconnect during an in-flight resync drops the second resync; queue one more run.
- C4: fetchRoom de-dup throws away a later room_activity; apply the latest queued activity after the fetch (or refetch).
- C5 (= D1): resync/room_removed for the open room: reconnect the room socket and let 4403/4404 pick the copy; fall back to removed after ~3 s.
- C6: after the gone pane, inbox.js still treats the dead room as open (frozen preview/unread if re-added; aria-current missing on rebuilt row). Clear "open room" on relay:room-gone/room-removed.
- C8: reconcile is O(N²) DOM work; batch renderPresence/renderTitle once at the end.
Backend:
- **C7:** existing members get no frame on add/remove/leave → stale member_usernames, "· N online" misses new people, presence not refreshed. Send room_changed (one frame) to remaining members on add, remove and leave too. (frontend: after room_changed for the open room, update roomMembers and ping for presence.)
- C9: live_rooms warnings: exc_info=True on build failures; one warning per action with a failure count instead of per recipient.
- C10: chat() next(...) StopIteration race → next(..., None) and redirect with ROOM_UNAVAILABLE.
- C11: tests: room_added equality test with messages/ReadState/cleared/deleted/system/direct (adapt review/test_summaries_equal.py); test_failed_group_change_sends_nothing can't fail (rename or replace); ruff RUF059 unused "kept" at tests.py ~660.


## Review round 1: user-tester (84fa2f9)

~45 checks, 37 pass; 0 blocker/major. Scripts qa/scripts, shots qa/shots.
- T1 = C5/D1 (deleted-while-offline says "no longer in").
- **T2 (frontend):** open room's row after deleting/editing the latest message shows "Message deleted" / stale text; after message_updated in the open room, refetch /summary/ for its row.
- **T3 (backend + frontend, contract):** edits/deletes never reach other members' list rows. Backend: on edit or delete, send inbox frame {"type": "room_refresh", "room": "<uuid>"} to the inboxes of visible_to members. Frontend: on room_refresh, fetch /summary/ for that row (de-duped, C4 rules).
- **T4 (frontend):** clear history leaves the old preview; after clear_room, refetch the row.
- **T5 (frontend):** .room-list__new[hidden]{display:none}.
- **T6 (frontend):** .chat-gone__heading overflow-wrap:anywhere.
- **T7 (frontend, = D6):** refresh row times at midnight / on visibilitychange.
- **T8 (backend):** handle_read crashes on SQLite "database is locked"; catch OperationalError and log; SQLite OPTIONS timeout 20.
- T9 (frontend): JS initials split must match Python str.split (U+0085 splits, U+FEFF doesn't).
- UX: welcome pane text after first room arrives / last removed (frontend); "You left X." notice on the JSON leave path (backend).
- Docs gaps → docs-writer.

## Questions for the user
(append; the orchestrator asks)

## Done
(append: agent, commit hash, item ids)

- backend-dev, b15c3b1, B6 (visibility filter for room events)
- backend-dev, 087ad64, B1 B2 B3 B4 B5 B7 B8 + tests (B6 tests included)
- frontend-dev, b5a2282, F3 (details.js, new-chat.js)
- frontend-dev, 9cc17c2, F1 F2 F3 F4 F5 F6 F7 F8 F9 F10 F11
- frontend-dev, 84fa2f9, F8 (no focus ring on the gone heading)
- frontend-dev, 0386979, merge of dev-live-rooms-fixes (backend) for real browser checks
- backend-dev, 58b3a75, S1 S2 (connect order, visible_to on updates/room_updated, room events after commit)
- backend-dev, 58bacaa, curly apostrophe in ROOM_UNAVAILABLE
- backend-dev, 97eba7d, P1 (set-based room_summaries_for_users)
- backend-dev, 3684a9d, C7 C9 C10 C11 + tests for P1/C7/C9/C10
- backend-dev, e4d4c14, UX (leave notice on the JSON path)
- backend-dev, 625002f, T3 T8 + tests
- frontend-dev, 9cf58bc, round 2: C1 C2 C3 C4 C5/D1/T1 C6 C7 C8 D3 D4 D5 D8 T2 T3 T4 T5 T6 T7 T9, welcome pane (merged with backend at e240230; 151 browser checks + real T3 pass)
