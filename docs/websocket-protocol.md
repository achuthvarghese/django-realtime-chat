# WebSocket protocol

The chat page opens two sockets:

- a **room socket** for the room you have open (messages, edits, typing,
  read receipts), and
- an **inbox socket** for everything else (presence of people you share rooms
  with, new messages and unread counts in your other rooms).

Both pass through `AllowedHostsOriginValidator` and `AuthMiddlewareStack`.

## Room socket

Each open room uses one WebSocket at:

```
ws[s]://<host>/chat/<room_id>
```

`room_id` is the room's UUID. The page picks `wss` when it was loaded over
HTTPS. Connections pass through `AllowedHostsOriginValidator`, so the page's
host must be in `DJANGO_ALLOWED_HOSTS`, and through `AuthMiddlewareStack`, so
the Django session cookie identifies the user.

## Connecting

| Situation | Result |
| --- | --- |
| Not signed in | Closed before accepting, code `4401` |
| Malformed or unknown room id | Accepted, sends an `error` with `code: 404`, closes with `4404` |
| Signed in but not a member | Accepted, sends an `error` with `code: 403`, closes with `4403` |
| Member | Accepted and joined to the room's group |

Membership is also checked on **every frame**, and when a member is removed,
leaves, or the group is deleted, their open sockets get an `error` (`403` or
`404`) and close with `4403` or `4404`. The client redirects to the login page
on `4401`; on `4403` or `4404` it shows why and returns to the room list.

## Client to server

Every frame is a JSON object with a `type`.

### `save_message`

```json
{"type": "save_message", "message": "Hello"}
```

`message` is trimmed and must be 1 to 4000 characters. The message is saved
and made visible to every current member of the room.

### `edit_message`

```json
{"type": "edit_message", "id": "8f5c…", "message": "Fixed text"}
```

Changes the text of one of your own messages in this room. The same rules as
`save_message` apply to `message`. Deleted messages can't be edited.

### `delete_message`

```json
{"type": "delete_message", "id": "8f5c…"}
```

Deletes one of your own messages for everyone. The text is removed from the
database; the message stays as a "Message deleted" placeholder.

Editing or deleting a message that is not yours, is already deleted, or does
not exist in this room returns an `error` with `code: 403`.

### `read`

```json
{"type": "read"}
```

Marks the room read up to now for you. The page sends it on connect, when a
message from someone else arrives, and when the tab becomes visible again.
Sending a message also marks the room read.

### `typing`

```json
{"type": "typing"}
```

Tells others you are typing. The page sends it at most every 2.5 seconds
while you type; the server forwards at most one per second per socket.

### `clear_room`

```json
{"type": "clear_room"}
```

Hides every message currently in the room for the requesting user only. Other
members keep their history.

## Server to client

### `save_message` (to every member connected to the room)

```json
{
  "type": "save_message",
  "id": "8f5c…",
  "message": "Hello",
  "user": "maya",
  "name": "Maya Rao",
  "initials": "MR",
  "created_at": "2026-11-25T09:41:00.123456+00:00",
  "edited": false,
  "deleted": false,
  "kind": "text"
}
```

`kind` is `text` for messages people write, or `system` for group events
("Maya added Lee"), where `message` is the event text and `user` is who did
it. System messages can't be edited or deleted and never count as unread.

`user` is the username; `name` is the full name, or the username when no name
is set; `initials` is derived from `name`. The chat page renders its initial
history from the same shape (`chat/presenters.py: message_data`).

`message`, `user` and `name` are plain text. Clients must insert them as text
(`textContent`), never as HTML.

### `typing` (to every socket in the room, including yours)

```json
{"type": "typing", "user": "maya", "name": "Maya Rao"}
```

Clients ignore their own and show "Maya Rao is typing…" for 4 seconds or
until that person's message arrives.

### `room_updated` (to every socket in the room)

```json
{"type": "room_updated", "room": "<room uuid>", "name": "Design crew", "member_count": 4}
```

Sent after any group change (members added or removed, admins changed,
renamed). Clients update the header and sidebar and reload the Details panel
if it's open.

### `message_updated` (to every member connected to the room)

Sent after an edit or delete, with the same fields as `save_message`. A deleted
message has `"deleted": true` and an empty `message`; an edited one has
`"edited": true`.

### `clear_room` (to the requesting socket only)

```json
{"type": "clear_room", "cleared": true, "for": "maya"}
```

### `error` (to the requesting socket only)

```json
{"type": "error", "code": 400, "message": "Message cannot be empty", "ts": "…"}
```

Sent for invalid JSON, a non-object payload, an unknown `type`, an empty or
over-long message, and when a connection is refused (`403`, `404`).


## Inbox socket

```
ws[s]://<host>/inbox/
```

Signed-in users only; otherwise the socket closes with `4401`. Each open
inbox socket is recorded as a `Connection`. You are **online** while any of
your connections was seen in the last 90 seconds.

### Client to server

```json
{"type": "ping"}
```

Send every 30 seconds. Refreshes your connection and returns a new
`presence_snapshot`.

### Server to client

**`presence_snapshot`**, on connect and after each ping: the people you share
a room with who are online now.

```json
{"type": "presence_snapshot", "online": ["arjun", "anika"]}
```

**`presence`**, when someone you share a room with comes online (their first
connection) or goes offline (their last connection closes).

```json
{"type": "presence", "user": "arjun", "online": false}
```

**`room_activity`**, to every member when a message is sent in one of their
rooms, with their unread count for that room. The page uses it to update the
preview, move the room to the top and show the unread badge, except for the
room already open.

```json
{
  "type": "room_activity",
  "room": "<room uuid>",
  "unread": 3,
  "message": {"type": "save_message", "id": "…", "message": "standup in 5", "user": "anika", "…": "…"}
}
```

Presence and activity use the database and the channel layer, so they work
across server processes when `REDIS_URL` is set. Connections left behind by
a crashed process stop counting after 90 seconds and are deleted after an
hour.
