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

## Contract changes
(append: date, agent, change, who must adapt)

## Questions for the user
(append; the orchestrator asks)

## Done
(append: agent, commit hash, item ids)

- backend-dev, b15c3b1, B6 (visibility filter for room events)
- backend-dev, 087ad64, B1 B2 B3 B4 B5 B7 B8 + tests (B6 tests included)
