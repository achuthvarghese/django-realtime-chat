# WebSocket protocol

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

The client redirects to the login page on `4401` and to the room list on
`4403` or `4404`.

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
  "deleted": false
}
```

`user` is the username; `name` is the full name, or the username when no name
is set; `initials` is derived from `name`. The chat page renders its initial
history from the same shape (`chat/presenters.py: message_data`).

`message`, `user` and `name` are plain text. Clients must insert them as text
(`textContent`), never as HTML.

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
