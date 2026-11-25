# Django Real-Time Chat

A messaging app built with Django and Django Channels: direct and group rooms,
with messages delivered over WebSockets.

## Quick start

```sh
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Open http://localhost:8000, sign up, and create rooms from the Django admin at
`/admin/` (an in-app way to start chats is on the roadmap).

Or with Docker: `docker compose up --build`.

## Stack

| Part | Version |
| --- | --- |
| Python | 3.12, 3.13 |
| Django | 5.2 LTS |
| Channels / Daphne | 4.x |
| Channel layer | In-memory by default, Redis when `REDIS_URL` is set |
| Database | SQLite |

## Documentation

- [Setup and configuration](./docs/setup.md): local, Docker, environment variables, production notes
- [Testing](./docs/testing.md): running the suite, layout, CI
- [WebSocket protocol](./docs/websocket-protocol.md): connection rules and message frames
- [Changelog](./CHANGELOG.md)

### Background notes

- [Channels basic setup][config_channels.md]
- [Channel layers setup][config_channel_layers.md]
- [Django static files][config_static_files.md]

## Project layout

```
account/        login, signup, logout
chat/           rooms, messages, chat view
chat/channels/  WebSocket consumer and routing
realtime_chat/  settings, URLs, ASGI/WSGI entry points
docs/           project documentation
```

## License

See [LICENSE](./LICENSE).

<!-- File links -->
[config_channels.md]: ./readme/config_channels.md
[config_static_files.md]: ./readme/config_static_files.md
[config_channel_layers.md]: ./readme/config_channel_layers.md
