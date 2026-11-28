# Phase P10c: mentions (branch `dev-mentions`)

`@username` mentions: matched on the server, shown as highlighted names, autocomplete in the composer, an "@" badge on chat rows for mentions and replies to you, and the tab title counting them. Base: master 3fc699c. One PR. CHANGELOG heading: `## Phase 10c: mentions`. (P10d notifications and mute comes after, separately.)

## Decided by the user
- Two PRs: this one is mentions only. No notifications list/bell. No @everyone/@here.
- Matching: `@` + a member's exact username, case-insensitive, not directly after a letter/digit/underscore (so `a@maya.com` is not a mention), only **current members other than the sender**, and only those in the message's `visible_for`. Anything else stays plain text, with no hint to the sender.
- Edits recompute mentions (added/removed). (P10d: new mentions from edits won't trigger browser notifications.)
- "For you" in groups = mentions of you + replies to your messages → "@" badge. Direct chats: no "@" badge (every message is for you).
- The "@" count clears when you open/read the chat (existing ReadState), no new read state.

## Owners
| Builder (sub session) | Branch | Files |
| --- | --- | --- |
| backend-dev | `dev-mentions-backend` | `chat/models.py`, `chat/migrations/0007_mention.py`, `chat/admin.py`, new `chat/mentions.py`, `chat/presenters.py`, `chat/presence.py`, `chat/views.py`, `chat/channels/consumers.py`, `chat/live_rooms.py`, `core/demo_data.py` (+ seed), `chat/tests.py`, `core/tests.py` |
| frontend-dev | `dev-mentions-frontend` | `chat/static/chat/js/*.js`, `chat/static/chat/css/chat.css`, `chat/templates/chat/*.html` |
| docs-writer (sub agent, later) | `dev-mentions-docs` | docs, README, CHANGELOG |

## Schema (database-designer + planner)
- `Mention(message FK Message CASCADE related_name="mention_rows" db_index=False, user FK User CASCADE related_name="mention_rows")`, `UniqueConstraint(fields=["message","user"], name="unique_mention")`; `Message.mentions = ManyToManyField(User, through="Mention", related_name="mentioned_in", blank=True)`.
- Migration `chat/0007_mention` (create + M2M; reversible; no backfill — old messages don't light up).
- Mentions are written in the same transaction as the message (save), diffed on edit, deleted with the message on soft delete (like reactions).

## Data shapes
- Message objects (`message_data`): `"mentions": [{"user": "lee", "name": "Lee Chen"}, ...]` in the order they appear; `[]` for none, deleted and system messages. In the initial page JSON, history pages, `save_message` and `message_updated` frames. History: +1 query per page (flat; test it).
- Room objects (room list / summaries / `room_added` / `room_changed`?): add `"mentions": <int>` = unread messages in that room that mention you or reply to one of your messages (0 for direct chats). Computed in the **same grouped query** as `unread_counts` (no extra query in `rooms_for` or `room_summaries_for_users`; test the count).
- Inbox `room_activity`: add `"mentions": <int>` (the per-recipient count for that room) and `"for_you": "mention" | "reply" | null` (this message relative to the recipient; always null in direct chats). Fix while there (planner G2): `inbox_message` must not fetch the Room per socket per message — pass what's needed in the event and compute unread + mentions in one query.
- Members for autocomplete: the chat page context gets `room_members` = [{"username", "name", "initials"}] for the open room (current members, sorted by name); frontend renders `{{ room_members|json_script:"room-member-list" }}`. Keep the existing `room-members` (usernames) if still used.

## Front end (frontend-dev)
- Rendering: split message text into text nodes and `<span class="mention" data-user="…">@name-or-username</span>` only for entries in `mentions` (match `@username` case-insensitively at word boundaries as the server did); `.mention--me` for you; a row that mentions you or replies to you gets a subtle `.msg--for-you` emphasis. textContent only; never innerHTML.
- Autocomplete in the composer: typing `@` + letters (not after a letter/digit) opens a listbox (combobox ARIA: textarea `aria-autocomplete="list"`, `aria-controls`, `aria-activedescendant`; options with avatar initials, name, @username) filtered by username and name prefix, excluding you, max 8. ↑/↓ move, Enter or Tab inserts `@username ` (replacing the typed token), Esc closes it; while open these keys don't send / edit-last / cancel the reply; the listbox joins the overlay check so Escape order stays: listbox → dialog/picker → reply bar → Details. Click/tap picks. Works with the reply bar open.
- Room list: `.room-link__mentions` "@" badge (accessible text "Mentions and replies: N. Unread: M") when `mentions > 0`, next to the unread count; updated live from `room_activity.mentions`, cleared when you open the chat (and from summaries/resync). Not for direct chats.
- Tab title: count unread as today; muted rooms come in P10d (keep a separate mentions sum ready, e.g. `data-mentions`).
- Desktop, tablet rail, phone; light/dark; both densities; Signal tokens only; console.warn with "%s" args only.

## Demo data (backend-dev)
About six mentions (Design team, Ops, using existing lines or new ones), one reply to a Maya message left unread for her so "@" shows when signing in as maya, a mention of Priya in Book club after her clear point (she sees it) and one before it (she doesn't). Seeding tests pass.

## Tests (backend-dev)
Parser table: email-like, after letter/digit/underscore, case, punctuation after the name (`@lee,` `@lee.`), unknown, non-member, self, removed member, member who can't see the message; save/edit add-remove/delete; mentions in history/page/frames (+1 query flat); mentions count in rooms_for and summaries in the same query (no extra query), reply-to-you counted, direct chats 0, cleared on read; room_activity per-recipient mentions/for_you; inbox_message query budget (no Room fetch); demo seed.

## Decisions log
## Contract changes

## Review round 1: security-auditor (backend 725c909)
Risk low; no mention/"@" signal reaches anyone who can't see the message; server-only event fields stay server-side; no emails. PoCs security/src/secpoc.
- **MS1 (low):** edits use visible_for ∩ members as candidates → the author learns which members cleared history (their mention is silently dropped). Fix: on edit, candidates = current members minus the author, same as new messages (counts/frames already filter visible_for).
- **MS2 (low/medium):** history re-parses every message (find_mentions O(#@ × candidates)); 100 crafted 4,000-char messages → history limit=50 1.13 s, limit=100 2.22 s. Fix: order rows without a full re-parse (e.g. position via lower().find, or store position on Mention); bucket candidates by first char / length in find_mentions; stop when all found.
- MS3 (info): Mention rows survive clear_room (and the seed) — harmless now (all readers filter visible_for) but a trap for P10d: delete the user's Mention rows for cleared messages, or document that readers must filter visible_for.
- MS4 (info): Unicode case folding (Kelvin sign) — consistent client/server, harmless.


## Review round 1: code-reviewer (3797b79)
Backend solid; counts consistent across rooms_for/room_counts/summaries; query budgets flat; rendering text-only; Esc order correct. Probes review/test_probe.py, test_counts_probe.py.
- **MC1 (must, frontend):** Ctrl/Cmd/Alt+Enter with the list open sends and leaves a stale list over an empty composer (↑, Esc, Enter/Tab then act on the stale list). Close the list in the submit path (and when a refused reply's text is restored) or on any modified Enter.
- MC2 (backend, later→do now, cheap): edit vs delete race — conditional update filter(pk, deleted_at__isnull=True) inside the atomic block; stop if 0 rows.
- MC3 (frontend): autocomplete compares lowercased query with non-lowercased usernames; token regex closes on . + - @ → lowercase both; use the server's username character set.
- MC4 (backend): find_mentions length bug with characters whose lowercase is longer (İ) → slice by original length, compare lower()/casefold on both sides.
- **MC5 (decision: orchestrator):** server counts a reply to your message as "for you" even if you can't see the original; client only highlights when reply_to.available → add visible_for=user to the reply Exists (server) so "@" and highlight agree.
- MC6 (frontend): isDirect depends on other_username → render data-room-type and test it (inbox.js setMentions too).
- MC7 (backend): rename `mentions` parameter shadowing the chat.mentions module (send_message_frame, broadcast_update).
- MC8 (backend): seed EDITED rows don't re-sync mentions (comment or sync); script order nit.


## Review round 1: performance-profiler (backend 725c909)
Query budgets kept (0 to +1 per path). Scripts/prototypes in perf/.
- **MP1 (regression):** presence.room_counts per socket per message: 1 query but slower (10k-unread room, 50 sockets: 1.0 → 1.8 s of DB work per message) — the OR with ~Exists(ReadState) defeats the (room_id, created_at) range and 2 correlated EXISTS per row. (a) read ReadState first, filter created_at__gt=when, use uncorrelated pk__in=Mention(user) / reply_to__in=Message(room, user): 35 → 25 ms (2 queries). (b) cap counts at ~100 (badge shows 99+): 35 → 4 ms per socket — needs a product decision (tab title sum).
- **MP2 (pre-existing, cheap, big):** unread_and_mentions builds one OR clause per read room (25 KB SQL at 300 rooms) → annotate the room's last_read_at via correlated Subquery and filter lr null or created_at > lr: 205 → 72 ms at 300 rooms, 1 query instead of 2 (prototype perf/proto_unread.py, identical results).
- **MP3:** migration 0007 AddField of the M2M rebuilds chat_message on SQLite (908 ms + 21 MB at 100k msgs) → SeparateDatabaseAndState(state_operations=[AddField]) (and unique_mention inside CreateModel): 488 ms, no rebuild; makemigrations --check stays clean.
- **MP4 (= MS2):** find_mentions: lowercase text once, candidates bucketed {length: {name: user}} → 4,000-char worst case 28 ms → ~1 ms (perf/proto2.py); optionally cap @ positions per message.
- Fine/later: history +1 query, heavy payload +58% (people map later); inbox event size with many mentions (watch with Redis); edit queries 5 → 10 when mentions change.


## Review round 1: ui-ux-designer (3797b79)
Works and fits Signal; text-only rendering, Esc order, 44px touch rows fine. Mockups design/mockups (chat-snapshot.html + proposed.css), sheets in design/shots.
Must: MD1 .mention--me weaker than others → 20% fill + inset 1px color-mix(accent 70%, fg) (like .reaction--mine). MD2 .msg--for-you edge <3:1 in 4 light palettes, tint drops gutter time <4.5 → 3px edge color-mix(accent 70%, fg), 3% tint, time color-mix(muted 88%, fg), focus shadow matches. MD3 autocomplete silent for screen readers → polite #mention-status ("3 people match. Up and down to choose, Enter to insert."), cleared on close. MD4 hint wrong while open → "↑↓ choose · ↵ insert · Esc close". MD5 active option bar → color-mix(accent 70%, fg) (3px).
Later/cheap: MD6 tablet rail badges crowd the avatar → option D (outlined "@" + filled count in list; rail shows "@" alone, count in accessible name); MD7 label "Mentions and replies: N. Unread: M"; MD8 phone list max-height min(4.5 rows, 45dvh) on coarse pointers; MD9 forced colours (box-shadow edge; outline on .mention--me); MD10 option handle max-width 45% + ellipsis; MD12 .badge contrast in Slate/Paper (tokens, separate).

## Review round 1: user-tester (3797b79)
~60 checks, 56 pass; 0 tracebacks; privacy clean; crafted frames fine; autocomplete keys correct; layouts OK.
- T1 highlight inside @arjun-ops / @arjun.chen and T3 dotted usernames not highlighted — fixed by 9825741 (after the tested build).
- T2 = MC5 (reply you can't see counted).
- T4 = MD6 (rail badges crowd).
- Friction: autocomplete token ASCII-only (can't search non-Latin or hyphenated display names); no autocomplete in the inline edit box; other tabs don't clear counts (existing); "@" has no visible number; inactive members can be mentioned (matches Details); docs stale (demo counts).

## Questions for the user
- 2026-11-28, user: cap unread and mention counts at 100 per chat (badges show 99+; tab title shows (99+) when any chat is capped).
## Done
- backend round 2: 485c8b2 (MS1, MS3 forget_cleared, parser casefold+buckets+200 @ cap, room_counts read-first + COUNT_CAP 100, unread_and_mentions 1 query, 0007 state-only M2M, MC5 reply visible, MC2, MC4, MC7, MC8). 392 passed. Demo: maya Design 5/2, Ops 6/1, Book club 0/0, Maya-Anika 1/0; priya Book club 1 @; 6 Mention rows.
- backend-dev: 582648c, 725c909 (Mention + 0007, chat/mentions.py, payloads, counts in the unread query via presence.room_counts, inbox_message without Room fetch, demo 7 mentions + reply to Maya). 382 passed. History now 3 queries/page. room_members includes the viewer (frontend filters me). Longer username wins at the same @; @lee.chen does not name lee. docs: demo-data counts changed (Design 5, Ops 6 unread for maya).
