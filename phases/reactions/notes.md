# Phase P10b: reactions (branch `dev-reactions`)

React to a text message with one of 6 emoji. The message shows chips (emoji + count); clicking a chip toggles your reaction; changes appear live for everyone who can see the message. Base: master d5a8158. One PR. CHANGELOG heading: `## Phase 10b: reactions`.

## Decided by the user
- Fixed set of 6: thumbs_up 👍 "Thumbs up", heart ❤️ "Heart", laugh 😂 "Laughing", wow 😮 "Surprised", sad 😢 "Sad", party 🎉 "Party" (this order everywhere).
- Several reactions per person per message, one of each emoji.
- Names shown to everyone who can see the message. Reactions stay when the reactor leaves/is removed or clears history (you then can't un-react on a message you cleared).
- Defaults: anyone who can see a text message can react (own messages too); no reactions on system or deleted messages; deleting a message removes its reactions; rate limit 10 react frames per 5 s per socket; no effect on room list, previews, unread or inbox; notifications later (P10c); React button first in the action bar opens a small picker; phones: tap-select, picker below, 44px chips; screen readers hear only your own toggles; action bar grouped React · Reply | Edit · Delete with a separator, wrapping on phones.

## Owners
| Builder (sub session) | Branch | Files |
| --- | --- | --- |
| backend-dev | `dev-reactions-backend` | `chat/models.py`, `chat/migrations/0006_reaction.py`, `chat/admin.py`, `chat/presenters.py`, `chat/views.py`, `chat/channels/consumers.py`, `chat/realtime.py`, `core/demo_data.py` (+ seed command), `chat/tests.py`, `core/tests.py` |
| frontend-dev | `dev-reactions-frontend` | `chat/static/chat/js/*.js`, `chat/static/chat/css/chat.css`, `chat/templates/chat/*.html` |
| docs-writer (sub agent, later) | `dev-reactions-docs` | docs, README, CHANGELOG |

## Schema (database-designer)
- Module-level `ReactionEmoji(models.TextChoices)` with the 6 keys above (key = stored value, label = the emoji character). Store keys, never characters.
- `Reaction(message FK Message CASCADE related_name="reactions" db_index=False, user FK User CASCADE related_name="reactions", emoji CharField(max_length=16, choices=ReactionEmoji.choices), created_at auto_now_add)`; Meta ordering ["created_at", "id"]; `UniqueConstraint(fields=["message","user","emoji"], name="unique_reaction")`; `CheckConstraint(condition=Q(emoji__in=ReactionEmoji.values), name="reaction_emoji_valid")`.
- Migration `chat/0006_reaction` (create table only; reversible).

## Data shape: `reactions` in every message object (`message_data`)
`"reactions": [{"emoji": "thumbs_up", "count": 2, "users": [{"user": "maya", "name": "Maya Rao"}, {"user": "lee", "name": "Lee Chen"}]}, ...]`
- Only emoji with count ≥ 1; ordered by the fixed emoji order; users within an emoji ordered by reaction time.
- Clients compute "mine" from the page's own username. The emoji character and label come from a client-side table keyed by the same 6 keys (frontend owns it; backend may also expose `REACTION_EMOJI` in a json_script if convenient — agree via message).
- Deleted, system and brand-new messages: `"reactions": []`. Inbox `room_activity` messages: `"reactions": []`.
- Present in the initial page JSON, `GET /chat/rooms/<id>/messages/`, `save_message` and `message_updated` frames (so an edit doesn't wipe chips).
- History: exactly +1 query per page (one rows query over the page's message ids, folded in Python); add a CaptureQueriesContext test that the count is the same at 0 and many reactions.

## Socket: client → server
`{"type": "react", "id": "<message uuid>", "emoji": "thumbs_up", "on": true}` (`on: false` removes). Idempotent: on when already on / off when already off = success, no error.
Target must be: in this room, kind=text, not deleted, in the sender's visible_for; emoji must be one of the 6 keys; `on` must be a boolean. Otherwise error `{"type": "error", "code": 400, "message": "You can't react to that message", "for": "react"}` (same text for every reason). Check and write in one `transaction.atomic()`; IntegrityError on add = already on.
Rate limit: more than 10 `react` frames within 5 s on one socket → `{"type":"error","code":429,"message":"Slow down","for":"react"}`, nothing saved.

## Socket: server → client
`{"type": "reactions_updated", "id": "<message uuid>", "reactions": [...]}` after each successful change (also after an idempotent no-op is fine to skip), sent once via `visible_to` = message.visible_for ∩ current room members. Never via `message_updated`. No inbox / room_refresh / unread changes.
Deleting a message deletes its reactions in the same transaction; the existing `message_updated` (deleted) carries `"reactions": []`.

## Front end (frontend-dev)
- Chips row `.msg__reactions` under the message text (with `aria-live="off"` — the transcript is an aria-live log); each chip `button.reaction[data-reaction="<key>"][aria-pressed]`, `.reaction--mine` when you reacted; text = emoji + count; accessible name e.g. "Thumbs up, 3 reactions, including you"; `title` lists names ("Maya Rao, Lee Chen and you"). Click toggles (sends `on` = !mine). Optimistic update allowed only if reconciled by `reactions_updated`.
- `reactions_updated` updates only that row's chips via a dedicated `updateReactions(row)` — never rebuild the row, never close an open inline edit, keep focus on a chip (extend focusKey with `reaction:<key>`).
- `message_updated` keeps working (carries reactions too).
- Action bar: `data-action="react"` button first: React · Reply | Edit · Delete, with a 1px `--line` separator before Edit/Delete; flex-wrap on phones. React opens a picker popover (use `details[data-popover]` pattern or extend the overlay check so the Escape order stays: popover/dialog → reply bar → Details panel) with the 6 emoji as buttons named in words; ←/→ move, Enter picks, Esc closes and returns focus to React; picking an emoji you already reacted with removes it.
- Roving keyboard: chips are part of the focused row's Tab stops.
- Touch: chips tappable directly (44px on coarse pointers) and a chip tap must not select/deselect the row; React in the selected row's bar opens the picker on the line below.
- Screen readers: announce only your own toggles ("Reacted with Thumbs up" / "Removed Thumbs up") via the existing polite status region; others' reactions are silent.
- Errors: show the server message for `for: "react"` errors as a toast; revert any optimistic change.
- Desktop, tablet rail, phone; light/dark; both densities; Signal tokens only; console.warn with "%s" args only.

## Demo data (backend-dev)
A REACTIONS list (room, exact message text, emoji key, [usernames]): one message with several people and 2+ emoji in Design team, one on the reactor's own message, one in a DM, one in Book club on the message Priya cleared (she must not get it). Seeding tests pass.

## Tests (backend-dev)
Constraints; payload shape/order; history +1 query flat; react on/off idempotent; rejects other room, hidden, deleted, system, bad emoji, non-boolean `on`, malformed id with the fixed error; 429 after 10 in 5 s; delete clears reactions; audience: cleared history / joined later / removed member get no `reactions_updated`; message_updated carries reactions; inbox frames have reactions []; demo seed.

## Decisions log
## Contract changes
- 2026-11-27, backend-dev: an idempotent no-op (already on/off) is not broadcast, but the sender's socket alone gets a reactions_updated with the current state (to reconcile optimistic chips).
- 2026-11-27, backend-dev: every react frame counts toward the rate limit, including refused ones.
- 2026-11-27, backend-dev: template context `reaction_emoji` = [{"key","char","label"}] in display order; frontend adds `{{ reaction_emoji|json_script:"reaction-emoji" }}`.

## Review round 1: security-auditor (backend 231cc79)
Risk low; no reactions/names reach anyone who can't see the message (page, history, frames, errors, timing); allowlist strict; audience correct. PoC: security/poc/test_reactions_attack.py.
- **RX1 (low):** rate limit is per socket → bypass with several sockets or reconnects (5 sockets × 10 = 50 broadcasts, no 429). Make it per user (cache key react:<user_pk>, 10 per 5 s); optionally check visibility before opening the IMMEDIATE transaction.
- RX2 (info, frontend): a late reactions_updated can arrive after the delete's message_updated → updateReactions must ignore deleted rows. Optional: a monotonic version in the frame (backend) so clients drop older snapshots.
- RX3 (info): re-added members see reactions added while they were out on messages they could already see — follows the existing visibility rule; no change unless the user decides otherwise.


## Review round 1: code-reviewer (76d02d6)
Backend solid (no must-fix): validation before queries, visibility check inside IMMEDIATE tx, savepoint no-op, on_commit broadcast, delete+reactions in one tx, rate window exact, history 2 queries at 0 and 15,000 reactions, set_reaction 8/6 queries, ~10 KB frame worst case. Throwaway: review/test_rx_queries.py.
- **CRX1 (must, frontend):** picker stays open after Shift+Tab to React then moving on → aria-expanded stuck, option tabIndex 0 on a non-stop row, and overlayOpen() blocks Escape everywhere (reply cancel, Details close). Close when focus leaves the opener too; Escape on the opener closes it. Playwright: open, Shift+Tab, ArrowUp → picker gone, composer Esc cancels reply.
- CRX2 (frontend): message_updated can overwrite newer reactions → keep existing reactions in updateMessage unless deleted (reactions_updated is the authority).
- CRX3: revert on socket close may show off for a saved reaction; consider refetching visible reactions on reconnect (or accept).
- CRX4 (frontend): picker options' aria-pressed not refreshed by reactions_updated while open.
- CRX5 (frontend): own toggle announced before server confirms → announce on confirm, or announce the undo.
- CRX6 (backend): handle_react doesn't catch OperationalError (db locked → socket drops; same as save_message); likely-dead IntegrityError branch (drop or reword).


## Review round 1: ui-ux-designer (76d02d6)
Keyboard, picker placement, Escape, roving stops, chip-tap not selecting, reduced motion, screen-reader names all fine. Shots/mockups in design/shots, design/mock.
Must:
- **DX1:** on touch, a tapped chip takes focus → :focus-within shows the floating hover bar over the text (two bars if another row is selected). In @media (hover: none) show the bar only on selected rows (or when focus-visible is inside the bar).
- **DX2:** "mine" state fails 3:1 in light mode (accent edge 1.9–2.9) and looks like the focus ring → Option B: --mine-edge = color-mix(accent 70%, fg), border + inset 1px ring, count weight 800; focus-visible stacks the focus ring; non-mine border color-mix(muted 35%, surface). Same for picker options [aria-pressed=true].
- **DX3:** aria-haspopup="true" announces a menu but the popup is a toolbar → drop it; keep aria-expanded, add aria-controls.
Later / needs user:
- DX4: who reacted only visible on desktop hover (title) — touch and sighted keyboard users can't see names; contract says names shown to everyone → when a row is selected on touch, a muted line under the chips "👍 Lee Chen and you · 🎉 …" (mockup P2); later a CSS tooltip on hover/focus.
- DX5 (user decided 44px): 32px visible chips with a 44px tap area (::before), 12px wrap gap — mockup compare-phone-chips.png.
- DX6: chips per density; "add reaction" chip; sticky :hover tint on touch.


## Review round 1: performance-profiler (backend 231cc79)
Normal/light use: +1 query, +1.4 ms per page. Heavy (300 reactions per message on a full page): history 4.7 → 268 ms / 668 KB (limit=100: 475 ms / 1.34 MB); 85% is building model objects. Frame 13 KB at 300 entries; one react e2e 64 ms vs 27 ms bare; burst of 10 = 716 ms. Migration 0006: 1.26 s on 100k msgs (Django's whole-DB FK check; note for deploys). Scripts perf/.
- **PQ1 (do now):** reactions_for_messages → values_list(message_id, emoji, user__username, first, last) + name cache (prototype perf/proto.py: 230 → 57 ms, identical output).
- PQ2 (later, contract): payload users repeated per emoji → usernames + one people map per response, or cap names.
- PQ3 (later, contract): send delta frames {id, emoji, user, name, on, count} instead of full state (13 KB → ~150 B).

## Review round 1: user-tester (76d02d6)
~60 checks, 55 pass; privacy clean (priya/later-joined/removed), crafted frames all fixed 400, rate limit, edits survive, phones/tablet/zoom OK. Scripts qa/scripts, shots qa/shots.
- T-1 (major) = CRX1 picker stuck open after Shift+Tab, blocks Escape everywhere.
- **T-2 (minor):** chips flicker under latency with more than one change in flight (applyReactions replaces state that lacks your other unconfirmed changes and clears pending) → keep your still-pending changes applied on top of server state until confirmed.
- T-3 = CRX5 refused reaction still announced.
- **T-4 (minor):** a reaction above the viewport shifts the rows you're reading → keep scroll anchored (not only at bottom).
- T-5 (emoji table twice) — fixed in 0d84c12.

## Questions for the user

- 2026-11-27, user: phone chips 32px visible with a 44px tap area; names of who reacted shown on touch (line under chips when selected) and on keyboard focus (tooltip) in this PR.
## Done
- backend-dev round 2: 55d2600 per-user rate limit in the Django cache (react:<pk>; LocMemCache is per process — with several Daphne processes use a shared cache such as Redis: docs/setup note), reads-before-IMMEDIATE, 503 "Try again" on a locked DB; 15c6fa0 values_list folding; d06fe10 tests. 328 passed.
- backend-dev: 5 commits on dev-reactions-backend (models + 0006, presenters, history +1 query, chat/reactions.py service, consumer react/429/delete, demo REACTIONS, 16 tests + seed test; fixed TestReplyMigration leaving DB at 0005); 324 passed.
