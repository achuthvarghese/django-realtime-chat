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
| `chat/tests.py` | Chat view access, room list order and previews, history limit, initials, WebSocket auth, membership, message handling, broadcast shape, people search, direct and group creation, history paging, edit and delete, unread counts, presence, typing, the inbox socket, the chat page query budget, group rules and actions, removal over sockets, and the group admin migration |

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
