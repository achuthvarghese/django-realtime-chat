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
| Design team | Group, created by maya | **maya**, **arjun**, anika, lee | 135 messages over ten days, enough for **infinite scroll** (the room opens with 50); grouping and day separators; one **edited** message; two group events; two **replies**; **reactions** |
| Ops | Group, created by lee | **lee**, omar, sofia, maya | Deploy chatter; one **deleted** message ("Message deleted"); a group event; two **replies**, one quoting the deleted message |
| Book club | Group, created by anika | **anika**, sofia, priya, omar, maya | A week-old thread plus recent replies; Priya has cleared her older history; one **reply** whose original Priya can't see; **reactions** Priya can't see |
| Maya ↔ Arjun | Direct | maya, arjun | Short recent exchange, all read; one **reply**; a **reaction** |
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
7. **Phone layout**: open the site with your browser's device toolbar; tap a
   message to show its actions (React and Reply, plus Edit and Delete on
   yours) and the names of who reacted.
8. **Group admin**: as `maya`, open Design team → Details (ⓘ). Make `anika` an
   admin, rename the group, or remove `lee` while `lee` has it open in another
   window: their tab says "You're no longer in this chat." As `lee` (Ops'
   only admin) try stepping down: the panel asks you to make someone else
   admin first.
9. **Replies**: as `maya`, use Reply on any message and send. Click a quote
   to jump to its original. See the seeded replies below for each kind of
   quote.
10. **Reactions**: as `maya` and `arjun` side by side, open Design team and
    find "Palette cards are in, six of them". Click a chip to add or remove
    your reaction and watch the count change in the other window; hover a
    chip (or Tab to it) to see who reacted. Use React to add a new emoji.
    As `priya`, open Book club: the reactions on the message she cleared
    never show.

### Seeded replies

| Room | Reply | Quotes | What it shows |
| --- | --- | --- | --- |
| Design team | maya: "Yes, default stays. Everyone can switch in Settings → Appearance" | lee: "Can we keep Graphite + Coral as the default?" | A quote of a nearby message |
| Design team | arjun: "Try opening Ops in another tab" | arjun: "Pushed the new spine layout to staging" | An original about two days back; jumping to it may load older messages |
| Ops | lee: "Rolling out relay v1.0 now" | sofia's deleted message | A "Message deleted" quote that still jumps |
| Ops | lee: "Smoke tests passed" | omar: "Deploy finished: relay v1.0 is live" | A quote of the message just above |
| Book club | maya: "Halfway through, no spoilers please!" | anika: "Next pick: The Left Hand of Darkness?" | Everyone else sees the quote; `priya` cleared the original, so she sees "Original message unavailable" |
| Maya ↔ Arjun | maya: "Sure, sending notes in a bit" | arjun: "Got a minute to look at the PR?" | A reply in a direct chat |

### Seeded reactions

| Room | Message | Reactions (in the order people reacted) | What it shows |
| --- | --- | --- | --- |
| Design team | anika: "Palette cards are in, six of them" | 👍 maya, lee · ❤️ anika · 🎉 arjun, maya, lee | Several people and emoji; Maya's own reactions are highlighted; Anika reacted to her own message |
| Design team | arjun: "Typing indicator and unread badges are live too" | 😮 lee | One reaction from someone else |
| Maya ↔ Arjun | maya: "Sure, sending notes in a bit" | ❤️ arjun | A reaction in a direct chat, on a reply |
| Book club | anika: "Next pick: The Left Hand of Darkness?" | ❤️ sofia, omar · 😂 maya | Priya cleared this message, so she never sees it or its reactions. Maya can reach it from the quote in her reply |

## Changing the data

The dataset lives in `core/demo_data.py` (users, rooms, scripted messages,
edits, deletes, reactions, read state, cleared history); the loader is
`core/management/commands/seed_demo.py`. Times are relative to when you seed,
so "Today" and "Yesterday" always look right.

Each `SCRIPT` line is `(room, sender, text, minutes before now)`. A reply adds
a fifth item: the exact text of an earlier line in the same room. The loader
links it to the latest message with that text so far, and stops with an error
if no earlier line in that room matches.

Each `REACTIONS` line is `(room, exact text of a text message, emoji key,
[usernames])`, the people in the order they reacted. It matches the
message's final text (after edits). The loader stops with an error if the
text doesn't match exactly one text message in the room that isn't
deleted, or if someone listed can't see the message. Reactions are seeded
before cleared history is applied, 20 seconds apart, starting 20 seconds
after the message.

If you change the data, update
this page; `core/tests.py` checks the unread counts, the seeded reactions and
the scenarios listed here, and `chat/tests.py` checks the seeded replies.
