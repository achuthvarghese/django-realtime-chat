# Setup

## Requirements

- Python 3.12 or 3.13
- Optional: Redis 7, when running more than one server process
- Optional: Docker with Compose v2

## Local development

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # sets DJANGO_DEBUG=true for local work
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

`daphne` is the first entry in `INSTALLED_APPS`, so `runserver` starts the
ASGI server and serves both HTTP and WebSockets on http://localhost:8000.

## Docker

```sh
docker compose up --build
```

This starts the app with `DJANGO_DEBUG=true` and a Redis channel layer. The
SQLite database lives in the `sqlite-data` volume, and migrations run when the
container starts.

## Environment variables

Settings read their values from the environment. A `.env` file in the project
root is loaded automatically; real environment variables take precedence.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_DEBUG` | `false` | Debug mode. Turns on the debug toolbar when it is installed. |
| `DJANGO_SECRET_KEY` | dev key when debugging | Required when `DJANGO_DEBUG` is off. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` in debug, empty otherwise | Comma-separated host names. Also used to validate WebSocket origins. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | Comma-separated origins, e.g. `https://chat.example.com`. |
| `DJANGO_DEBUG_TOOLBAR` | `true` | Set to `false` to hide the toolbar while debugging. |
| `DJANGO_SECURE_COOKIES` | `true` | Secure session and CSRF cookies when not debugging. |
| `REDIS_URL` | unset | Use the Redis channel layer instead of the in-memory one. |
| `SQLITE_PATH` | `./db.sqlite3` | Location of the SQLite database file. |

## Production notes

- Set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.
- Run `python manage.py collectstatic`; files go to `staticfiles/`. Serve them
  with your web server or a CDN.
- Run the app with Daphne: `daphne -b 0.0.0.0 -p 8000 realtime_chat.asgi:application`.
- Use `REDIS_URL` whenever more than one process serves WebSockets; the
  in-memory layer cannot pass messages between processes. Presence, typing
  and unread updates depend on it in the same way.
- Presence is stored in the database (`chat.Connection`), so all processes
  must share one database.
