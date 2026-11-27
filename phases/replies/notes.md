# Phase P10a: replies (branch `dev-replies`)

Reply to a specific message: the reply shows a live quote of the original
above it; clicking the quote jumps to the original. Base: master 5180f6c.
One PR. CHANGELOG heading: `## Phase 10a: replies`.

## Decided by the user
- Live, privacy-safe quotes (no copied text).
- Jump loads older pages (100 at a time) up to 10 pages, then "That message is too far back".
- Reply button in the per-message action bar + "Replying to" bar above the composer; Esc cancels. No swipe.
- Defaults: reply to text messages only (own too), not system or deleted ones; editing a reply changes text only; after a jump, no extra control (P11a adds jump-to-latest); deleted original → "Message deleted", still jumps; original removed from the DB → reply becomes a plain message; room-list preview = the reply's own text; excerpt ≤ 200 chars on one line; server rejects replies to messages the sender can't see.

## Owners
| Builder (sub session) | Branch | Files |
| --- | --- | --- |
| backend-dev | `dev-replies-backend` | `chat/models.py`, `chat/migrations/0005_*`, `chat/presenters.py`, `chat/channels/consumers.py`, `chat/views.py`, `chat/realtime.py`, `chat/live_rooms.py`, `core/demo_data.py` (+ seed command), `chat/tests.py`, `core/tests.py` |
| frontend-dev | `dev-replies-frontend` | `chat/static/chat/js/*.js`, `chat/static/chat/css/chat.css`, `chat/templates/chat/*.html`, `core/static/core/css/*` if needed |
| docs-writer (sub agent, later) | `dev-replies-docs` | docs, README, CHANGELOG |

## Schema (database-designer)
- `Message.reply_to = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies")` (default FK index kept).
- Meta constraints: `CheckConstraint(condition=Q(reply_to__isnull=True) | Q(kind="text"), name="message_reply_only_text")`, `CheckConstraint(condition=~Q(reply_to=F("id")), name="message_reply_not_self")`.
- Migration `chat/0005_message_reply_to` via makemigrations (AddField + 2 AddConstraint), reversible, no data migration.
- History query stays 1 query/page: `.select_related("user", "reply_to__user").annotate(reply_visible=Exists(Message.visible_for.through.objects.filter(message_id=OuterRef("reply_to_id"), user_id=user.pk)))`. Add a CaptureQueriesContext test that query count doesn't grow with replies.

## Data shape: `reply_to` in every message object (`message_data`)
Present in the page's initial JSON, `GET /chat/rooms/<id>/messages/`, `save_message` and `message_updated` frames:
- plain message: `"reply_to": null`
- viewer can't see the original: `"reply_to": {"id": "<uuid>", "available": false}` (no name, no text)
- original deleted: `"reply_to": {"id": "<uuid>", "available": true, "deleted": true, "user": "<username>", "name": "<display name>"}`
- otherwise: `"reply_to": {"id": "<uuid>", "available": true, "deleted": false, "user": "<username>", "name": "<display name>", "excerpt": "<≤200 chars>"}`
- excerpt = original content with every whitespace run collapsed to one space, stripped, first 200 characters (no ellipsis; CSS clamps to one line).
- Inbox `room_activity` frames: the embedded message has `"reply_to": null` (no quote over the inbox).
- `message_data(message, viewer=...)` (or an explicit flag) decides `available`; never leak name/excerpt to viewers outside the original's `visible_for`.

## Socket: client → server
`{"type": "save_message", "message": "...", "reply_to": "<uuid>"}` (`reply_to` optional, null or absent = plain message).
Target must be: a valid uuid, in the same room, `kind=text`, not deleted, and in the sender's `visible_for`. Otherwise error frame `{"type": "error", "code": 400, "message": "You can't reply to that message"}` (fixed text; same for every reason) and nothing is saved. An IntegrityError from the original being hard-deleted at the same moment → same error.
`edit_message` never changes `reply_to`.

## Socket: server → client (per viewer)
- New reply: split recipients by whether they can see the original (one query on the original's visible_for ∩ current members), two group sends via `visible_to`: one with the full quote, one with `{"id", "available": false}`.
- `message_updated` for a **reply** (edit/delete of the reply): same split, so the quote stays per-viewer.
- `message_updated` for an **original**: unchanged frame; clients update every loaded quote whose `reply_to.id` equals it: new excerpt (client computes the same excerpt rule from `message`) or deleted state.

## Front end (frontend-dev)
- **Action bar** `.msg__actions` on every text message (not system, not deleted): Reply for everyone; Edit and Delete only on your own. Built so P10b can add React. Hover/focus on desktop; on touch, tapping any text message selects it (`.is-selected`) and shows the bar (today only `.msg--mine`).
- **Composer reply bar** above `#composer`: "Replying to <name>" + one-line excerpt + × button (aria-label "Cancel reply"). Hidden when not replying. `aria-live` polite announcement "Replying to <name>". Reply moves focus to the composer input. Esc in the composer cancels the reply first; the innermost-first Escape order is dialog/popover → reply bar → Details panel (update details.js's check). Sending clears it. Leaving the room drops it. Up-arrow-to-edit keeps working.
- **Quote** inside a reply, above its text: `button.msg__quote` (name + excerpt, one line, accent left rule). Unavailable: non-interactive `div.msg__quote.msg__quote--unavailable` "Original message unavailable". Deleted: "Message deleted" italic, still a button. Text via textContent only.
- **Jump**: click/Enter on a quote → if the original is loaded, scroll it into view (centre), add `.msg--target` highlight ~1.6 s (reduced motion: no scroll animation, tint only) and focus it (`tabindex=-1`). If not loaded, page back with `?before=<oldest id>&limit=100` up to 10 pages (reuse the history loader; keep scroll position stable; guard against double runs), then jump; if still not found, toast "That message is too far back". Errors → friendly toast + console.warn with `%s` args (no values in the format string: CodeQL).
- Live quote updates on `message_updated` for originals (see above).
- Composer hint stays; works on desktop, tablet rail, phone; light/dark; both densities.

## Demo data (backend-dev)
Add a few replies to the seeded chats (e.g. in a group and a DM), via a way for SCRIPT entries to reply to an earlier line. Seeding tests still pass.

## Tests (backend-dev)
Migration applies/reverses; presenter shapes (null, visible, deleted, unavailable); save_message reply ok; rejects other-room, system, deleted, hidden, malformed, nonexistent ids with the fixed error; per-viewer split for new replies and reply edits (a member who joined later gets available:false and never the excerpt); inbox frame has reply_to null; history and initial page carry reply_to per viewer with flat queries; SET_NULL on original user delete; demo seed.

## Decisions log
## Contract changes
- 2026-11-27, backend-dev: a deleted reply has "reply_to": null (no quote on a tombstone).

## Review round 1: security-auditor (backend 1052fe5)
Risk low; no leak of a hidden original's name/text on any path (page, history, all frames, inbox, errors, timing). PoC: security/poc/test_reply_leaks.py.
- **RS1 (low):** views.room_history `before=` lookup lacks visible_for=request.user; P10a now hands out hidden ids (reply_to.id). Add the filter (same 400 "Unknown message" as other-room/nonexistent).
- RS2 (info): reply_target lookup outside the atomic block → race with soft delete / clear. Move it inside.
- RS3 (info): same-room not enforced by DB; add reply_to__room_id=F("room_id") to the reply_visible Exists (and the socket split) + a test.


## Review round 1: code-reviewer (bf2db2b)
Backend sound (split, shapes, seed format; deferred-FK race really caught on commit: review/test_fk_race.py). Verdict: fix 1–3 before merge, 4 before P10b.
Frontend (chat.js):
- **CR1 (must):** pendingReply restored on ANY error frame and never cleared on socket close → wrong restore / duplicate send. Clear on close; restore only for the reply error (backend adds `"for": "save_message"` to error frames — see CR-B1); don't re-open the bar if the input holds other text; a quick plain send after a reply mustn't lose the reply's text.
- **CR2 (must):** clear_room leaves the reply bar up → cancelReply + pendingReply = null.
- **CR3 (must):** updateMessage never rebuilds the quote from data.reply_to (SET_NULL → stale quote) → replace/remove .msg__quote like buildRow.
- **CR4 (important a11y, caused by this phase):** action bars + quotes in the tab order → hundreds/thousands of Tab stops. Roving tabindex: transcript is one tab stop, Up/Down between rows, Tab within a row reaches its quote/actions (or actions tabindex=-1, opened from a focused row).
- CR5: smooth scroll after a jump cut off by auto-load (hold `jumping` until scrollend / ~600 ms, or skip auto-load while .msg--target exists).
- CR6: composer Esc ignores open popover/dialog (add the same check details.js uses).
- CR7: details.js Escape also skips when focus is in .msg__edit.
- CR8: renderAll loses an open edit and moves focus from the action button → block quote jumps while editing (or keep edit text); restore focus to the same [data-action] button/quote.
- CR9: clear_room during an older-page load re-adds old messages → clearGen counter.
- CR10: jump re-renders all rows per page → prepend only new rows (fix the boundary row).
Backend:
- **CR-B1:** error frames carry `"for": "<client frame type>"` (e.g. "save_message", "edit_message") so the client can match them. Contract change.
- CR-B2 tests: message_updated for an original keeps its shape; empty-string reply_to is refused (document it).
- Nice: one demo reply to the DELETED ops line ("Message deleted" quote).


## Review round 1: ui-ux-designer (bf2db2b)
Solid and on-system; Esc order, live region, jump/focus, reduced motion, 44px all verified. Mockup: design/mockup-replies.html, shots design/shots/.
Must (this PR):
- **DZ1:** reply bar pushes the newest message out of view (and cancel the reverse): read nearBottom() before toggling #reply-bar, scrollToEnd() after if it was.
- **DZ2:** quote excerpt 4.47:1 in light (WCAG 1.4.3): .msg__quote no fill (hover fill only), excerpt color color-mix(in srgb, var(--fg) 72%, var(--bg)).
- **DZ3:** a reply inside a same-author continuation reads as part of the message above: continues = … && !data.reply_to.
Also cheap, do now:
- DZ5 = CR4 (roving tabindex).
- DZ6: action buttons' names identical on every row → aria-describedby to the row's name/text (or "Reply to <name>").
- DZ8: reply bar attached to the composer as one unit; while replying placeholder "Reply to <name>" and hint "Esc cancel reply · Shift ↵ new line".
- DZ9: title on the unavailable quote ("Sent before you joined, or not visible to you").
Later: DZ4 four-action bar grouping/wrap (P10b), DZ7 lighter quote on touch with 44px hit area, back-to-reply after jump (P11a).


## Review round 1: performance-profiler (backend 1052fe5)
Nothing grows with N or history; query counts flat at 0/50/100% replies; all lookups indexed. Payload +~265 B per reply (bounded).
- **PF1:** history_page hydrates 4 full models per row (incl. auth_user.password, full original content): add .only(...) for the fields message_data reads (prototype perf/proto_only.py: −23% at limit=100, identical output).
- **PF4:** migration 0005 rebuilds the table twice (≈1.3 s per 100k msgs): merge the two CheckConstraints into one (`Q(reply_to__isnull=True) | (Q(kind="text") & ~Q(reply_to=F("id")))`, name e.g. message_reply_valid) — 0005 isn't released yet, so regenerate it.
Later: PF2 `?around=<id>` endpoint to make far jumps one request; PF3 split replies double room deliveries (fine at 50 cap).


## Review round 1: user-tester (bf2db2b)
52 checks, 47 pass; privacy clean (no hidden original text anywhere for priya / cleared / later-joined); all crafted reply_to values refused; jump paging 4/10 pages and "too far back" OK; phone/tablet/zoom OK. Scripts qa/scripts (s8 bugs 1–2, s2/s9 bug 3, s5 bug 4); DB with Longroom (1,305 msgs).
- Bugs 1–2 = CR1 (lost text when a plain send follows; stale bar on unrelated error). Bug 3 = RS1 (fixed 7f4f56b). Bug 4 = CR7.
- Sent to frontend r2: T1 jump-failure toast; T2 visible busy state for slow jumps; T3 refused-reply toast hint; T4 zoom overlap of hover bar; T5 phone action bar reachable on long messages.
- Noted: Esc with focus outside composer doesn't cancel the reply (by design: innermost-first from the composer); "Attempt to send on a closed protocol" tracebacks on inbox connect when browsers close (dev-server noise; watch).

## Questions for the user
## Done
- backend-dev: 734820d schema, 433ae43 quotes/socket/history, 1052fe5 demo data; 301 tests.
