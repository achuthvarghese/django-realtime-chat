# Session log

## Standing rules (from the user)

- Plan in phases and steps, get confirmation, then develop. Ask questions
  when something is unclear.
- Code review, test, debug, repeat.
- Report only the main actions and results unless asked for more.
- No co-author lines in commits or PR descriptions.
- One descriptive branch off `dev` and one PR into `master` per case;
  fast-forward `dev` after each merge. Update all docs, create new ones.
- Git identity: the repository owner, the same author as the project's
  existing commits (read it from `git log`; resets on session restart,
  check before committing). No email address in any file.
- This `claude-memory` branch keeps session records; never merge it.
  **Update it after every merged PR** with the phase's notes, reports,
  screenshots and mockups, and this log.

## Pull request history

| PR | Branch | Phase |
| --- | --- | --- |
| #5 | master | Initial import |
| #6 | dev-p0 | Phase 0: foundation |
| #7 | dev-p1 | Phase 1: security and bug fixes |
| #8 | dev-design-system | Phase 2: Signal design system |
| #9 | dev-auth-screens | Phase 3: home, sign in, create account |
| #10 | dev-chat-screen | Phase 4: chat screen |
| #11 | dev-start-chats | Phase 5a: start chats |
| #12 | dev-settings | Phase 5b: settings |
| #13 | dev-message-actions | Phase 5c: message actions and history |
| #14 | dev-live-presence | Phase 5d: presence, typing, unread |
| #15 | dev-touch-actions | Fixes after phase 5 |
| #16 | dev-docs-overhaul | Phase 6: documentation |
| #17 | dev-demo-data | Demo data |
| #18 | dev-account-ux | Account UX and username rules |
| #19 | dev-group-admins | Phase 9a: group admins |
| #20 | dev-live-rooms | Phase 9b: live rooms |
| #21 | dev-agents | Claude Code agents (11), CLAUDE.md orchestrator playbook |
| #22 | dev-live-rooms-fixes | Phase 9c: live-room fixes (first agent-team phase) |
| #23 | dev-agent-sessions | Builders run as sub sessions; git author read from history |
| #24 | dev-replies | Phase 10a: replies (first phase with builder sub sessions) |
| #25 | dev-reactions | Phase 10b: reactions |
| #26 | dev-mentions | Phase 10c: mentions |

## Key decisions

- **Design:** Signal design system; palettes as a theme setting; compact
  threads; responsive (desktop, tablet rail, phone). Theme only in Settings
  (signed-out pages keep a theme menu).
- **Usernames:** 3–30 chars, lowercase letters, digits and `_`, start with a
  letter, no trailing or double `_`, unique; existing ones renamed by
  migration.
- **Account menu:** the whole footer row is the menu button with a chevron
  (Option A); Settings has sections added as features land.
- **Groups (P9a):** any member adds people; only admins rename, remove,
  delete and change admins; multiple admins; creator is admin; the only
  admin can't step down; when the last admin leaves, the longest-standing
  member becomes admin; the last member leaving deletes the group; existing
  groups got their earliest member as admin. Error messages come from a
  fixed code table (CodeQL finding).
- **Muting:** no "unmute all"; unmute selected chats only.
- **Live rooms (P9b):** the room list updates over the inbox socket
  (`room_added`, `room_changed`, `room_removed`); the "Refresh" prompt was
  removed.
- **Sub agent vs sub session:** builders (backend, frontend, devops) run
  as sub sessions with their own container and `send_message`; reviewers,
  planner, database designer and docs writer stay sub agents.
- **Agents:** 11 agents in `.claude/agents/` (7 read-only reviewers, 4
  builders). The main session is the orchestrator; builders work in
  worktrees on `dev-<phase>-<role>` branches, and one PR per phase.
  Builders have no SendMessage tool, so the orchestrator relays messages
  between them.
- **Phase 9c (live-room fixes):** per-socket visibility (`visible_to`),
  join-then-check room sockets, group events after commit, one
  `room_changed` frame (also on add/remove/leave), grouped-query
  summaries, `room_refresh` inbox frame, `/chat/rooms/summaries/` with a
  resync on every inbox connect, `/chat/?room=` redirect with a notice,
  SQLite `timeout` 20 + `IMMEDIATE` transactions, redesigned gone pane and
  new-row animation. Details in `phases/live-rooms-fixes/`.
- **Phase 10a (replies):** live, privacy-safe quotes (`Message.reply_to`
  SET_NULL, one check constraint), per-viewer `reply_to` objects and split
  sends, fixed reply error, error frames carry `for`, history 1 query/page,
  `before=` rejects hidden ids; action bar with roving keyboard navigation
  (transcript = one Tab stop), reply bar joined to the composer, jump to the
  original (≤10×100 pages). Details in `phases/replies/`.
- **Phase 10b (reactions):** fixed set of 6 emoji (keys, not characters),
  several per person, names shown to viewers, kept after leave/clear;
  `Reaction` model + 0006; `react` / `reactions_updated` frames, per-user rate
  limit 10/5 s in the cache (Redis cache when REDIS_URL is set), 503 on a busy
  DB; chips with tooltips and a names line on touch, picker, grouped action
  bar; 32px phone chips with a 44px tap area. Details in `phases/reactions/`.
- **Phase 10c (mentions):** P10c split from notifications: mentions now,
  P10d notifications and mute next (command palette → P10e). No bell, no
  @everyone. Server-matched @username (casefold, boundaries, longest wins,
  ≤200 @), `Mention` + 0007 (state-only M2M), "@" badge = unread mentions +
  replies to you that you can see, counts capped at 100 (99+). **Rule:**
  Mention rows record the text (kept on clear history); every "for you"
  reader must filter visible_for — P10d notifications must too. Details in
  `phases/mentions/`.

## Roadmap

- P10d `dev-notifications-mute` (mute in Details + Settings list with Unmute selected, Settings → Notifications, browser notifications with 'Show message text', reaction notifications on by default, notification rate limit); P10e command palette. (Old P10c line follows:) (+ mute,
  Settings → Notifications; notifications need HTTPS); P10d
  `dev-command-palette` (⌘K, search, `/clear` `/invite` `/leave` `/me`).
- P11a `dev-reading-aids` (new-messages line, jump to latest, drafts);
  P11b `dev-seen-by` (+ Settings → Privacy); P11c `dev-shortcuts-help`;
  P11d `dev-group-colours` (8 preset colours).
- Kept in mind: hide direct chats, rate limits, password reset, browser
  tests in CI, production deploy, hardening.
- Deferred from 9c: editing/deleting your own messages after clearing
  history (user: decide later); day dividers at midnight in an open chat;
  room-check timing edge cases (re-review items 3, 4, 7); live-region
  "Added to X"; 44 px phone back button; per-user unread counter at very
  large volumes; retake README screenshots (times now "9:41", no gone
  pane shot).
- Deferred from 10a: four-action bar grouping/wrap (P10b), `?around=<id>`
  history for one-request jumps, per-user variant sends for split replies,
  lighter quote on touch, retake README screenshots with replies.
- Deferred from 10b: smaller reactions_updated frames (delta / people map),
  near-bottom stick-to-newest snap on reactions, channels_redis 4.3 +
  redis-py 8.2 TimeoutError with REDIS_URL (pre-existing; check before
  production Redis), README screenshots with reactions.
- Deferred from 10c: autocomplete in the inline edit box, clearing counts
  across tabs, .badge contrast in Slate/Paper, README screenshots.

## Open questions for the user

- (none open) The typing/room_updated question was settled by the
  security audit: room_updated goes to current members; typing is covered
  by the join-then-check order and after-commit revokes.
