# Session log

## Standing rules (from the user)

- Plan in phases and steps, get confirmation, then develop. Ask questions
  when something is unclear.
- Code review, test, debug, repeat.
- Report only the main actions and results unless asked for more.
- No co-author lines in commits or PR descriptions.
- One descriptive branch off `dev` and one PR into `master` per case;
  fast-forward `dev` after each merge. Update all docs, create new ones.
- Git identity `achuthvarghese` / `acvknr@gmail.com` (resets on session
  restart; check before committing).
- This `claude-memory` branch keeps session records; never merge it.

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
| #21 | dev-agents | Claude Code agents, CLAUDE.md orchestrator playbook |
| (open) | dev-live-rooms-fixes | Phase 9c: live-room fixes (team phase) |

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
- **Agents:** 11 agents in `.claude/agents/` (7 read-only reviewers, 4
  builders). The main session is the orchestrator; builders work in
  worktrees on `dev-<phase>-<role>` branches, and one PR per phase.
  Builders have no SendMessage tool, so the orchestrator relays messages
  between them.

## Roadmap

- Phase 9c `dev-live-rooms-fixes` (in progress, team phase).
- P10a `dev-replies` (plan drafted by idea-planner; see
  `agent-trials/reports.md`).
- P10b `dev-reactions`; P10c `dev-mentions-notifications` (+ mute,
  Settings → Notifications; notifications need HTTPS); P10d
  `dev-command-palette` (⌘K, search, `/clear` `/invite` `/leave` `/me`).
- P11a `dev-reading-aids` (new-messages line, jump to latest, drafts);
  P11b `dev-seen-by` (+ Settings → Privacy); P11c `dev-shortcuts-help`;
  P11d `dev-group-colours` (8 preset colours).
- Kept in mind: hide direct chats, rate limits, password reset, browser
  tests in CI, production deploy, hardening.

## Open questions for the user

- Should `typing` and `room_updated` frames also skip a just-removed
  member's socket? (security-auditor asked for a verdict.)
