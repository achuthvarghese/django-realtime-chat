# Testing

The suite uses pytest with pytest-django and pytest-asyncio.

```sh
pip install -r requirements-dev.txt
pytest
```

Tests run with `realtime_chat.settings_test`, which fills in a test secret key,
turns debug off, forces the in-memory channel layer and uses a fast password
hasher. No `.env` or Redis is needed.

## Layout

| File | Covers |
| --- | --- |
| `account/tests.py` | Login, signup, logout, `next` redirects, validation, the auth screens, settings sections, saved appearance, username rules and the rename migration, case-insensitive sign-in, account menu |
| `core/tests.py` | Theme options, palette keys in sync across Python/CSS/JS, base template, error pages, home page, demo data seeding (including the seeded reactions, mentions and "@" counts) |
| `chat/tests.py` | Chat view access, room list order and previews, history limit, initials, WebSocket auth, membership, message handling, broadcast shape, people search, direct and group creation, history paging, edit and delete, unread counts, presence, typing, the inbox socket, the chat page query budget, group rules and actions, removal over sockets, the group admin migration, room summaries, live room-list frames (added, renamed, removed, left, deleted), the live-room fixes, replies, reactions and mentions listed below |

New in `chat/tests.py` for the live-room fixes:

| Class | Covers |
| --- | --- |
| `TestRoomSummariesForUsers`, `TestRoomSummariesForUsersRich` | Grouped `room_added` summaries equal `room_summary` for every viewer, with history, read state, cleared and deleted messages, system messages and direct chats; same-time messages; query count doesn't grow with history |
| `TestLiveRoomQueries` | Query counts don't grow with members for create group, add members and rename (`CaptureQueriesContext`) |
| `TestRoomChangedFrame` | One partial `room_changed` frame for every member; none for direct chats |
| `TestRoomChangedOnMembership` | `room_changed` on add (existing members only), remove and leave; none when the last member leaves |
| `TestLiveRoomFailures`, `TestLiveRoomLogging` | A failed inbox send is logged and skipped, the view still succeeds, nothing is sent on rollback; one warning per action, tracebacks for build failures |
| `TestRoomSummariesEndpoint` | `GET /chat/rooms/summaries/`: login, order, empty list, POST refused, query count doesn't grow with rooms |
| `TestUpdateVisibility` | Edits and deletes only reach people who can see the message; new messages reach every member; you can't edit your own message after clearing it; a removed member doesn't get the removal group event |
| `TestPingRefreshesContacts` | A `ping` returns a snapshot that includes new room-mates |
| `TestRefusedSocketFrames`, `TestStaleRoomSocket` | A refused room socket ignores frames; a socket whose membership ended without the revoke reaching it gets no message text or room updates; a removal between joining the group and the membership check is caught |
| `TestRoomEventsAfterCommit` | Group room events go out after commit, in order, never on rollback; failures logged; `room_updated` only to current members |
| `TestRoomRefresh` | `room_refresh` inbox frames after edits and deletes, only to people who can see the message |
| `TestChatPageRace` | Removed between the chat page's two queries: redirect with the notice |
| `TestBusyDatabase` | SQLite waits for locks; a locked database while marking read doesn't close the socket |
| `TestLeaveNotice` | "You left <group>." is queued on the JSON and redirect leave paths, and no other JSON action queues a notice |

New in `chat/tests.py` for replies:

| Class | Covers |
| --- | --- |
| `TestReplyMigration` | `chat/0005_message_reply_to` applies and reverses |
| `TestReplyConstraints`, `TestReplyReviewFixes.test_one_reply_constraint` | System messages can't reply, a message can't reply to itself, one `message_reply_valid` constraint; removing the original from the database makes the reply plain (`SET_NULL`) |
| `TestReplyPresenter` | The `reply_to` shapes: null, visible, deleted original, unavailable (and unavailable by default without the annotation), no quote on a deleted reply |
| `TestReplyHistory` | History and the initial page carry per-viewer quotes; query count doesn't grow with replies (`CaptureQueriesContext`) |
| `TestReplySockets` | A reply is saved and quoted; plain messages have `"reply_to": null`; other-room, system, deleted, hidden, malformed, unknown, non-string and empty-string targets are refused with the fixed error and nothing is saved; a target removed mid-save is refused; new replies and reply edits are split by who can see the original (a member who joined later gets `available: false` and never the excerpt); edits keep the target; inbox `room_activity` has `"reply_to": null` |
| `TestReplyReviewFixes` | `?before=` must be a message you can see; a cross-room `reply_to` never quotes; history loads only the user fields it shows |
| `TestReplyReviewSockets` | Error frames carry `for` with the client frame type, and no `for` for an unknown type; `message_updated` for an original keeps its shape |
| `TestReplyDemoData`, `TestReplyDemoDeleted` | Seeded replies are in groups and a direct chat, same room, after their original; Priya sees the Book club quote as unavailable; the Ops reply quotes the deleted message |

New in `chat/tests.py` for reactions (an autouse fixture clears the cache
before and after each test, since rate-limit windows are keyed by user id):

| Class | Covers |
| --- | --- |
| `TestReactionModel` | `unique_reaction` (one of each emoji per person) and `reaction_emoji_valid`; reactions go with the message and stay when the reactor leaves; the emoji table |
| `TestReactionPayload` | The `reactions` list: emoji in the fixed order, people by reaction time; none on deleted, system and new messages; the grouped query matches building from model objects; a no-op writes nothing; history and the initial page carry reactions; history takes one extra query however many reactions (`CaptureQueriesContext`) |
| `TestReactionSockets` | On and off reach everyone and are idempotent (a no-op answers only the sender); other-room, hidden, deleted, system, unknown and malformed ids, unknown emoji (including the emoji character instead of its key), a non-boolean `on` and missing keys all get the one fixed error and save nothing; `429` after 10 frames in 5 seconds, shared by a user's sockets and reconnects but not by other users; a locked database gets `503` and keeps the socket; `reactions_updated` skips people who cleared the message, joined later or were removed; edits carry reactions and deletes clear them; new messages and inbox `room_activity` carry `"reactions": []` and reacting sends nothing to the inbox |
| `TestReactRateLimitWindow` | The 5-second window slides and is kept per user |

New in `chat/tests.py` for mentions:

| Class | Covers |
| --- | --- |
| `TestFindMentions` | The parser table: start and middle of text, case, punctuation after the name (`@lee,`, `@lee.`, `@lee...`), email-like and after a letter, digit or underscore, longer words and handles (`@mayabee`, `@lee.chenx`), the longer username winning (`@lee.chen`), usernames with `+` and `-`, `@@maya`, unknown names, each person once in order; only candidates match |
| `TestFindMentionsFolding` | Case folding that changes length (`İlker`, `straße`); crafted 4,000-character texts stay under 20 ms; only the first 200 `@` signs are scanned |
| `TestMentionsOnSave` | Saving stores mentions and sends them in order; yourself, unknown names, non-members and emails stay plain; a removed member isn't mentioned; superuser-style usernames; direct chats store mentions |
| `TestMentionsOnEditDelete` | Edits add and remove mentions; edit mentions don't reveal who cleared their history; an unchanged edit keeps them; deleting removes them; removing the row cascades |
| `TestMentionsInHistory` | History and the initial page carry `mentions`; none on deleted messages; history takes three queries per page however many mentions (`CaptureQueriesContext`); the page's `room-member-list` is sorted by name |
| `TestMentionCounts` | Mentions and replies to you count, a reply that mentions you counts once; your own and hidden messages don't; direct chats are always 0; reading clears the count; the summaries endpoint and `room_summaries_for_users` agree; no extra query, and query counts stay flat for `rooms_for` and `room_summaries_for_users` |
| `TestMentionCountsRound2` | Unread and mention counts stop at 100 everywhere; the grouped counts match `room_counts` room by room in a mixed scenario; a reply counts only while you can see your original |
| `TestMentionInboxFrames` | `room_activity` `for_you` and `mentions` per recipient (`"mention"`, `"reply"`, `null` for the sender); direct chats are never for you; `inbox_message` takes three queries and never reads the room |
| `TestMentionSocketsRound2` | A reply to an original you cleared isn't for you; **Clear history** forgets your mentions; an edit racing a delete changes nothing |
| `TestMentionMigration` | `chat/0007_mention` applies and reverses |

`TestReplyMigration` now migrates back to the latest schema when it's done,
so later tests see every table.

The `?room=` redirect tests (non-member, malformed id, unknown, removed,
deleted, other endpoints keep their 404s) sit with the chat view tests.

WebSocket tests use `channels.testing.WebsocketCommunicator` against the full
ASGI application, so routing and origin validation are exercised too. Mark
them `@pytest.mark.django_db(transaction=True)` because the consumer reads the
database from another thread.

## Lint

```sh
black .
isort .
```

## Continuous integration

`.github/workflows/python_code_checks.yml` runs on pushes and pull requests to
`master` and `dev`:

- **check_format_and_imports** (required on `master`): `black --check` and `isort --check`
- **test**: on Python 3.12 and 3.13, checks for missing migrations, runs
  `manage.py check`, then `pytest`
