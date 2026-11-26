# Data model

```mermaid
erDiagram
    User ||--o| Preference : "has"
    User }o--o{ Room : "member of"
    Room ||--o{ Message : "contains"
    User ||--o{ Message : "sends"
    User }o--o{ Message : "can see (visible_for)"
    User ||--o{ ReadState : "has"
    Room ||--o{ ReadState : "tracked by"
    User ||--o{ Connection : "has open"
```

## `auth.User`

Django's built-in user model. `username` follows the
[username rules](./screens.md#username-rules) (enforced by the signup form and
applied to older accounts by migration `account/0002_conform_usernames`).
`first_name`, `last_name` and `email` are edited in Settings → Profile.

## `chat.Room`

| Field | Notes |
| --- | --- |
| `id` | UUID primary key; used in URLs and the WebSocket path |
| `name` | Up to 50 characters. Groups show it as the title; private rooms show the other person's name instead |
| `type` | `private` (exactly two members, one per pair of people) or `group` |
| `members` | Many-to-many to `User` (`user.rooms`) |
| `created_at` | Set on creation |

Rooms are created by `chat/services.py`: `get_or_create_direct_room` and
`create_group_room`.

## `chat.Message`

| Field | Notes |
| --- | --- |
| `id` | UUID primary key |
| `content` | Text, 1 to 4000 characters after trimming (enforced by the consumer) |
| `room`, `user` | Where and by whom |
| `created_at` | Set on creation; messages are ordered by it (indexed with `room`) |
| `edited_at` | Set when the author edits the text |
| `deleted_at` | Set when the author deletes it; `content` is emptied at the same time |
| `visible_for` | Members who can still see the message. Set to all room members on send; **Clear history** removes the requesting user |

`chat/presenters.py: message_data` turns a message into the JSON shape used by
the page and the socket.

## `chat.ReadState`

| Field | Notes |
| --- | --- |
| `user`, `room` | Unique together |
| `last_read_at` | Messages from others after this are unread. No row means everything from others is unread |

Updated when the user opens the room, sends a `read` frame, or sends a
message. `chat/presence.py: unread_counts` counts unread messages for many rooms
in one query (visible, not deleted, not your own).

## `chat.Connection`

| Field | Notes |
| --- | --- |
| `channel_name` | The inbox socket's channel; unique |
| `user` | Whose socket it is |
| `created_at`, `last_seen` | `last_seen` is refreshed by the 30-second ping |

A user is online while any connection has `last_seen` within 90 seconds.
Rows older than an hour are removed when anyone connects.

## `account.Preference`

| Field | Values | Default |
| --- | --- | --- |
| `user` | One-to-one (`user.preference`) | |
| `palette` | `graphite`, `midnight`, `slate`, `plum`, `moss`, `paper` | `graphite` |
| `mode` | `light`, `dark`, `system` | `system` |
| `density` | `compact`, `comfortable` | `compact` |
| `updated_at` | Set on save | |

A row is created the first time a user saves an appearance choice (or picks a
palette during signup). `Preference.for_user(user)` returns the saved row or an
unsaved one holding the defaults.
