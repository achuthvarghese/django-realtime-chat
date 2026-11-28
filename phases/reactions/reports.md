# P10b reactions: agent reports, condensed

## database-designer
- `ReactionEmoji` TextChoices (module level), 8 keys: thumbs_up 👍, heart ❤️, laugh 😂, wow 😮, sad 😢, pray 🙏, party 🎉, check ✅ — store keys, not characters.
- `Reaction(message FK CASCADE related_name reactions db_index=False, user FK CASCADE, emoji CharField(16, choices), created_at)`; UniqueConstraint(message,user,emoji) "unique_reaction"; CheckConstraint(emoji__in=values) "reaction_emoji_valid". Unique index covers the read path; user_id index for cascade.
- Migration 0006_reaction: create table only, reversible; changing the allowlist later needs a migration.
- History: +1 query per page (rows over the page's ids folded in Python into reactions [{emoji,count,mine,users:[{username,name}]}] in allowlist order); without names, a grouped query. Deleted/system → [].
- Open: do reactors who later left / cleared count? (matches reply quotes if yes; else filter current members).
- Socket: `react` {id, emoji, on: true|false} (idempotent add/remove, not toggle); target like own_message minus author (room, visible_for, not deleted, text); add in atomic + IntegrityError = success; remove = delete(); broadcast `reactions_updated` to visible_to with usernames so clients compute `mine` (one group_send).
- Soft delete removes reactions in the same save; clear history keeps your reactions for others.
- Growth tiny (15k–75k rows/year at 50 users). Alternatives: A one reaction per person (unique message,user; update_or_create); B free emoji (length check, grapheme + variation-selector normalisation).

## idea-planner (branch dev-reactions, CHANGELOG "## Phase 10b: reactions")
Questions (★ = recommended): 1 fixed set of 6 (👍 ❤️ 😂 😮 😢 🎉) ★ / full picker / set + "More…"; 2 several per person (one of each) ★ / one per person; 3 any member who can see it, own messages too ★; 4 no reactions on system/deleted, delete removes them ★; 5 show names to viewers who can see the message ★ / counts only; 6 keep reactions of removed members and after clear history ★ (clearing stays private; can't un-react on a cleared message) / remove on leave; 7 rate limit 10 frames / 5 s → 429 "Slow down" ★; 8 no room-list/unread/inbox effects ★; 9 notifications in P10c ★; 10 React button first in the bar opens a 6-emoji popover (arrow keys, Enter, Esc) ★; 11 phones: tap-select, picker on the line below, 44px chips ★ / long-press; 12 chips are button[aria-pressed] "Thumbs up, 3 reactions, including you"; only own toggles announced ★; 13 action bar grouping React · Reply | Edit · Delete + flex-wrap now ★; 14 one same-for-everyone frame with user lists, client computes mine ★.
Gaps to fix in this phase: G1 transcript is aria-live polite additions → chips aria-live off; G2 updateMessage rebuilds quote/bar and kills an open edit → separate reactions_updated + updateReactions; G3 message_updated must carry reactions; G4 focus keys for chips; G5 tab stops in the stop row (docs); G6 chip tap mustn't select row; G7 picker as details[data-popover] for Escape order; G8 (minor, existing) edit with unchanged text still broadcasts; G9 delete clears reactions in the same transaction.
Plan: backend model/presenter/history (+1 query/page), socket react/reactions_updated/delete/rate limit, demo data; frontend chips/live updates/fixes, picker + grouped bar; 5 reviewers; docs-writer.

## User decisions (2026-11-27)
Fixed set of 6 (👍 ❤️ 😂 😮 😢 🎉); several per person, one of each; names shown to viewers who can see the message, reactions stay after leave/clear; all other planner defaults accepted.

## Reviews (round 1)
- security-auditor: risk low; no leak of reactions/names; strict allowlist; RX1 per-socket rate limit (fixed: per user via cache; Redis cache when REDIS_URL), RX2 late frames on deleted rows (fixed in client), RX3 re-added members see reactions on messages they could already see (existing rule, kept).
- performance-profiler: light use +1 query/+1.4 ms; heavy page 268 ms → fixed to ~57 ms (values_list); frame up to 13 KB and burst cost (later: delta frames / people map); migration 0006 ~1.26 s per 100k msgs (Django FK check).
- code-reviewer: backend solid; CRX1 picker stuck open blocking Escape (fixed); CRX2–6 fixed.
- ui-ux-designer: DX1 floating bar on chip tap (fixed), DX2 mine contrast (Option B, ≥3.3:1), DX3 aria-haspopup (fixed); user decisions: 32px chips/44px tap, names on touch and keyboard (done).
- user-tester round 1: ~60 checks, 55 pass; picker bug, flicker, early announcement, scroll shift — all fixed.
- user-tester re-test at c74ed55: ~75 checks, all pass; friction: hover tooltip held back composer Escape (fixed 53868aa, verified with t8/t1); near-bottom stick-to-newest snaps on reactions (existing rule, later). Env note: channels_redis 4.3 + redis-py 8.2 TimeoutError drops sockets with REDIS_URL (pre-existing; check before production Redis).

## Process notes
- Builders as sub sessions again; backend identity reset caught by the per-commit check (no wrong-author commits).
- Agent 5-hour limit interrupted the re-test once; resumed after reset.
- Orchestrator fixes: Redis cache when REDIS_URL set (+ settings test), hover tooltip Escape.
