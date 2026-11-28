# P10c mentions, notifications, mute: agent reports, condensed

## database-designer
- `Mention(message FK CASCADE db_index=False, user FK CASCADE)` unique_mention; `Message.mentions` M2M through Mention (related_name mentioned_in).
- `Notification(recipient, kind mention|reply|reaction, room (denormalised), message CASCADE, actor CASCADE, created_at, read_at)`; partial index notif_unread (recipient, room) where read_at null; notif_list (recipient, -created_at, -id); checks notif_kind_valid, notif_not_self; unique notif_one_per_message (recipient, message) for non-reaction (mention wins over reply); unique notif_reaction_collapse (recipient, message, actor) for reactions.
- `Membership.muted_at` (nullable; resets on leave/rejoin). Preference: notify_browser False, notify_mentions True, notify_replies True, notify_reactions False.
- Rules: resolve @username in Python against room members (case-insensitive), only visible_for members; write in the save transaction; edits diff mentions; soft delete removes mentions+notifications; reaction add get_or_create, remove when reactor has no emoji left; clear history / remove / leave delete the user's notifications for that room; list query also checks visible_for; mark_read also sets read_at; sending a message marks the room read.
- Reads: mention_counts grouped query (+1 in rooms_for, +1 grouped in room_summaries_for_users); muted flag via subquery (no extra query); list keyset paging 30; unmute selected = update.
- Migrations: chat 0007_mention, 0008_notification, 0009_membership_muted_at; account 0003_preference_notifications; no backfill (old messages don't light up).
- Growth ~400k notifications/year at 200 users; optional cleanup of read >90 days.
- Alternatives: per-message reaction collapse; ReadState-based badge; Membership.notify_level (all/mentions/none) instead of muted_at; seen_at for a bell; @everyone as Message.mentions_all with notifications only.

## idea-planner
Split: P10c mentions (`dev-mentions`, "Phase 10c: mentions") then P10d notifications and mute (`dev-notifications-mute`, "Phase 10d: notifications and mute"); command palette moves to P10e.
Questions (★): 1 split two PRs ★; 2 no @everyone/@here ★; 3 server parses @token not after a letter/digit, case-insensitive, current members other than sender ★; 4 edits recompute mentions, new ones badge but no browser notification ★; 5 groups: mentions + replies to you drive "@" badge (reactions only browser notifications), DMs: every message notifies, no "@" ★; 6 muted room: no count badge, dimmed + bell-off, excluded from tab title, mentions/replies still "@" + notify, sort unchanged ★; 7 mute until unmuted ★; 8 Mute/Unmute toggle in Details + Settings list with checkboxes + Unmute selected ★ (confirm vs earlier decision); 9 mentioning non-member/self = plain text, no feedback ★; 10 notification shows sender, chat, 100-char excerpt with "Show message text" setting default on ★; 11 no notifications list/bell now (derived counts from Mention + ReadState) ★ vs Notification model + bell drawer (L); 12 ask browser permission only from a Turn on button in Settings ★; 13 event checkboxes per account, browser switch per device ★; 14 reaction browser notifications default on, same tag replaces ★; 15 demo data ★.
Cross-check: unread_counts grouped query gets a mention/reply-to-you count (no extra query); ReadState clears it; inbox_message per-recipient frame gets mentions/for_you; G2 inbox_message does a Room fetch + count per socket per message (fix in P10c); G3 no message rate limit (notification throttle in P10d); G4 clear_room loads all messages (separate); G5 superuser usernames may break the pattern — match exactly against members; G1 inbox socket only on the chat page (document).
Model (planner): Mention only in P10c; Membership.muted_at + Preference fields in P10d; no Notification table unless a bell is wanted. (database-designer proposed a Notification table — only needed for a list/bell or persistent read state.)

## User decisions, batch 1 (2026-11-28)
Two PRs (P10c mentions, then P10d notifications and mute; command palette → P10e); no notifications list/bell now (no Notification table; '@' badge from Mention + ReadState); mute = quiet but mentions/replies still show '@' and notify, unchanged order, until unmuted; Mute/Unmute toggle in Details + Settings list with checkboxes and 'Unmute selected' (no unmute all).

## User decisions, batch 2 (2026-11-28)
No @everyone/@here now; browser notifications show sender, chat and 100-char excerpt with a 'Show message text' setting (default on); reaction notifications on by default (same tag replaces; never for own); all other planner defaults accepted (Q3, Q4, Q5, Q9, Q12, Q13, Q15).

## Reviews (round 1) — summary
- security-auditor: risk low; MS1 edit candidates leaked who cleared (fixed); MS2 history parse cost (fixed: casefold + buckets + 200 cap, history only parses mentioned users); MS3 Mention rows after clear (see final decision below).
- performance-profiler: MP1 per-socket counts regression (fixed: read-first + uncorrelated + cap 100 per user decision); MP2 unread query 205 → ~72 ms (one grouped query); MP3 0007 state-only M2M (no table rebuild); MP4 parser 28 ms → ~1 ms.
- code-reviewer: MC1 Ctrl/Cmd/Alt+Enter stale list (fixed), MC2 edit/delete race (fixed), MC3 autocomplete case/charset (fixed), MC4 casefold (fixed), MC5 reply-you-can't-see (fixed), MC6 data-room-type (fixed), MC7/MC8 tidy (fixed).
- ui-ux-designer: MD1–MD5 must (fixed), MD6–MD10 (fixed); MD12 .badge contrast in Slate/Paper (tokens, later).
- user-tester round 1: ~60 checks, 56 pass (all fixed). Re-test at 4e7d136: ~75 checks, 74 pass; history of @-heavy messages 1.13 s → 29 ms.

## Final decision (orchestrator)
Tester round 2 found edits recreating Mention rows for people who cleared. Removing/skipping rows would itself leak (the author's highlights change after reload), so forget_cleared was dropped: Mention rows record the text; every "for you" reader (counts, for_you, and P10d notifications) MUST filter by visible_for. Documented in chat/mentions.py and docs/data-model.md. Test test_clear_room_keeps_mentions_but_not_counts. 7 Mention rows in the seed.

## Process notes
- Builder sub sessions; both containers reset git identity; backend caught it; frontend's wrong-author merge commit was skipped by cherry-picking its two real commits.
- User decisions mid-phase: count cap at 100.
