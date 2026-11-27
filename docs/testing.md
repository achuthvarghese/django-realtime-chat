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
| `core/tests.py` | Theme options, palette keys in sync across Python/CSS/JS, base template, error pages, home page, demo data seeding |
| `chat/tests.py` | Chat view access, room list order and previews, history limit, initials, WebSocket auth, membership, message handling, broadcast shape, people search, direct and group creation, history paging, edit and delete, unread counts, presence, typing, the inbox socket, the chat page query budget, group rules and actions, removal over sockets, the group admin migration, room summaries, live room-list frames (added, renamed, removed, left, deleted), the live-room fixes and replies listed below |

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
