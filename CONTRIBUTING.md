# Contributing

Thanks for helping with Relay. This guide covers how work is organised, the
checks every change must pass, and what to update alongside code.

## Getting set up

Follow [docs/setup.md](./docs/setup.md), then:

```sh
pip install -r requirements-dev.txt
pytest
```

## Branches and pull requests

- `master` is the released branch and is protected: it needs the
  `check_format_and_imports` check (and the test jobs) to pass.
- `dev` collects finished work. Start each piece of work from `dev` on its
  own branch with a **descriptive name**: `dev-<what-it-does>`, for example
  `dev-start-chats`, `dev-touch-actions`, `dev-docs-overhaul`.
- **One pull request per feature or fix**, opened against `master`. If a branch
  depends on another open branch, say so at the top of the description
  ("Stacked on #12") and merge them in order.
- After a pull request merges, bring `master` back into `dev`.

## Commits

Use short, imperative subjects with a type and optional scope:

```
feat(chat): people search and endpoints to start direct and group chats
fix(chat-ui): show message actions on tap on touch screens
docs: architecture guide and contributing guide
test(chat): history paging, edit and delete permissions
```

Types used here: `feat`, `fix`, `test`, `docs`, `ci`, `chore`. Explain the
*why* in the body when it isn't obvious. Keep each commit focused so it
reads well on its own.

## Before you push

```sh
black .
isort .
pytest
python manage.py makemigrations --check --dry-run --settings=realtime_chat.settings_test
```

CI runs the same checks on Python 3.12 and 3.13.

For changes to screens, also open the page in a browser at desktop and phone
widths, in light and dark mode, and check the browser console for errors.
The style guide at `/styleguide/` (debug only) shows every component.

## What to update with your change

| If you change… | Also update |
| --- | --- |
| A screen, URL or user-facing behaviour | [docs/screens.md](./docs/screens.md) |
| A WebSocket frame or close code | [docs/websocket-protocol.md](./docs/websocket-protocol.md) |
| A model or migration | [docs/data-model.md](./docs/data-model.md) |
| Tokens, components or the theme | [docs/design-system.md](./docs/design-system.md) |
| Settings or environment variables | [docs/setup.md](./docs/setup.md) and `.env.example` |
| How the pieces fit together | [docs/architecture.md](./docs/architecture.md) |
| Anything users will notice | [CHANGELOG.md](./CHANGELOG.md) |

Add or update tests for every behaviour change; [docs/testing.md](./docs/testing.md)
lists where they live.

## Code guidelines

- **Security first.** Look rooms up through the user's own rooms, check
  ownership before changing a message, and never insert user text as HTML.
  See the security table in [docs/architecture.md](./docs/architecture.md#security-model).
- **No build step.** Plain CSS and JavaScript. Use design tokens, never
  literal colours, so every palette and mode keeps working.
- **Accessibility.** Real buttons and labels, visible focus, `aria-invalid` on
  bad fields, and respect for `prefers-reduced-motion`.
- **Keep queries flat.** List pages should not run a query per row; there is a
  test guarding the chat page.
