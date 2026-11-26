# Demo data

A ready-made set of people, chats and messages for trying Relay locally.
It loads **only in debug mode**. Every account and message is fictional.

> **Never use these accounts outside local development.** They all share a
> published password. `seed_demo` refuses to run when `DJANGO_DEBUG` is off.

## Loading it

**Docker** (automatic): `docker compose up --build` runs
`python manage.py seed_demo --if-debug` before starting the server. The first
start seeds the data. Later starts see it is already there and leave it, and
anything you added, alone.

**Without Docker:**

```sh
python manage.py migrate
python manage.py seed_demo            # seed once; skips if already seeded
python manage.py seed_demo --reset    # delete the demo data and seed again
```

| Situation | Result |
| --- | --- |
| `DJANGO_DEBUG=true`, first run | Seeds everything below |
| Already seeded | "Demo data already present; skipping." |
| `--reset` | Deletes demo users and rooms made only of demo users, then seeds again. Other accounts and their rooms are kept |
| `DJANGO_DEBUG` off | `seed_demo` fails with "Refusing to seed demo data"; with `--if-debug` it prints "skipped" and exits normally |
| `DJANGO_SEED_DEMO=false` | Same as debug off: lets you keep debug on with an empty database |

To start over in Docker: `docker compose down -v` removes the database
volume, and the next `up` seeds a fresh copy.

## Sign-in details

**Password for every account: `relay-demo-123`**

| Username | Name | Theme saved on the account | Good for testing |
| --- | --- | --- | --- |
| `maya` | Maya Rao | Default (Graphite + Coral, system, compact) | **Start here.** In every group plus two direct chats, with unread messages in Design team (3), Ops (4) and her chat with Anika (1) |
| `arjun` | Arjun Kumar | Slate + Electric, dark | Second window next to Maya: live messages, typing, presence; dark mode |
| `anika` | Anika Shah | Plum + Rose, light, comfortable | Comfortable density; the edited message is hers |
| `lee` | Lee Chen | Midnight + Saffron, system | Theme following the operating system |
| `sofia` | Sofia Martins | Moss + Tangerine, dark, comfortable | Ops and Book club member; direct chat with Priya |
| `omar` | Omar Haddad | Paper + Red, light | The light Paper palette |
| `priya` | Priya Nair | Default | Has cleared older Book club history, so she sees only the recent messages |
| `sam` | Sam Taylor | Default | **No chats yet**: empty states and starting a first chat with New chat |
| `noah` | Noah Kim | n/a | **Inactive account**: sign-in is refused and he never appears in people search |

All demo usernames follow the [username rules](./screens.md#username-rules); sign-in ignores letter case, so `Maya` works too.
Emails are `<username>@example.com`. There is no admin account; create one
with `python manage.py createsuperuser` if you need `/admin/`.

## Rooms

| Room | Type | Members (admins in bold) | What's in it |
| --- | --- | --- | --- |
| Design team | Group, created by maya | **maya**, **arjun**, anika, lee | 135 messages over ten days, enough for **infinite scroll** (the room opens with 50); grouping and day separators; one **edited** message; two group events |
| Ops | Group, created by lee | **lee**, omar, sofia, maya | Deploy chatter; one **deleted** message ("Message deleted"); a group event |
| Book club | Group, created by anika | **anika**, sofia, priya, omar, maya | A week-old thread plus recent replies; Priya has cleared her older history |
| Maya ↔ Arjun | Direct | maya, arjun | Short recent exchange, all read |
| Maya ↔ Anika | Direct | maya, anika | One unread message for Maya |
| Arjun ↔ Lee | Direct | arjun, lee | Code review chat |
| Sofia ↔ Priya | Direct | sofia, priya | Book chat |

## Things to try

1. **Live chat**: sign in as `maya` in one browser and `arjun` in a private
   window. Open Design team in both and type: you'll see "… is typing…", the
   message appear instantly and Online in the Maya ↔ Arjun header.
2. **Unread**: as `maya`, the tab title reads "(8) Chats · Relay". Open Ops
   and the badge and count clear.
3. **Infinite scroll**: open Design team and scroll to the top until "Start of
   the conversation".
4. **Edit and delete**: as `maya`, press ↑ in an empty composer to edit your
   last message, or use Delete on one of yours.
5. **Themes**: sign in as `arjun`, `anika`, `omar` or `sofia` to see their saved
   palettes, or change yours in Settings → Appearance.
6. **New chat**: as `sam`, use New chat to message `maya`, or create a group.
7. **Phone layout**: open the site with your browser's device toolbar; tap one
   of your messages to show Edit and Delete.
8. **Group admin**: as `maya`, open Design team → Details (ⓘ). Make `anika` an
   admin, rename the group, or remove `lee` while `lee` has it open in another
   window: their tab says "You're no longer in this chat." As `lee` (Ops'
   only admin) try stepping down: the panel asks you to make someone else
   admin first.

## Changing the data

The dataset lives in `core/demo_data.py` (users, rooms, scripted messages,
edits, deletes, read state, cleared history); the loader is
`core/management/commands/seed_demo.py`. Times are relative to when you seed,
so "Today" and "Yesterday" always look right. If you change the data, update
this page; `core/tests.py` checks the unread counts and scenarios listed here.
