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

The consumer joins the room's group **before** it checks membership. If you
are removed between the two steps, the revoke event still reaches the socket;
checking first would leave a window where it is missed. When the check fails,
the socket leaves the group again and is refused. A refused socket ignores any
frames the client sends before it sees the close, and any room frames queued
for it before it left the group.

Membership is also checked on **every frame**, and when a member is removed,
leaves, or the group is deleted, their open sockets get an `error` (`403` or
`404`) and close with `4403` or `4404`.

The client redirects to the login page on `4401`. On `4403` it shows the
"You’re no longer in <name>" pane, and on `4404` the "<name> was deleted"
pane (see [screens.md](./screens.md#when-the-open-room-goes-away)). The page stays on that pane;
it doesn't return to the list by itself.

## Client to server

Every frame is a JSON object with a `type`.

### `save_message`

```json
{"type": "save_message", "message": "Hello"}
```

`message` is trimmed and must be 1 to 4000 characters. The message is saved
and made visible to every current member of the room.

To reply to a message, add its id as `reply_to`:

```json
{"type": "save_message", "message": "Sounds good", "reply_to": "3b1d…"}
```

`reply_to` is optional; `null` or no key sends a plain message. Otherwise it
must be a string holding the UUID of a message that is:

- in the same room,
- a text message (not a group event),
- not deleted, and
- visible to you (not hidden by your **Clear history**, not sent before you
  joined).

Anything else, including an empty string, a number or an object, is refused
with one fixed error and nothing is saved:

```json
{"type": "error", "code": 400, "message": "You can't reply to that message", "ts": "…", "for": "save_message"}
```

The text is the same for every reason, so the error doesn't reveal whether a
message you can't see exists. The same error is sent if the original is
removed from the database while the reply is being saved.

### `edit_message`

```json
{"type": "edit_message", "id": "8f5c…", "message": "Fixed text"}
```

Changes the text of one of your own messages in this room. The same rules as
`save_message` apply to `message`. Deleted messages can't be edited. An edit
never changes what a reply replies to; a `reply_to` key is ignored.

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

### Who gets room frames

Frames about messages go only to sockets whose user may see them. The server
attaches a list of user ids to the channel layer event (`visible_to`); each
socket drops the frame if its user isn't in the list. The list is never sent
to the client.

| Frame | Goes to |
| --- | --- |
| `save_message` (yours) | People who were members when it was sent; a reply is split by who can see the original (see [Replies](#replies-and-the-reply_to-object)) |
| `save_message` (group event) | People who were members when it happened, so a removed member doesn't see "Maya removed Lee" |
| `message_updated` | Current members who can still see the message: not people who cleared their history or joined after it. Edits and deletes of a reply are split the same way as new replies |
| `room_updated` | Current members |
| `typing` | Every socket in the room |
| `clear_room`, `error` | The requesting socket only |

Group changes (`chat/groups.py`) send their room events only after the
database change commits, in the order they were queued, and never if it rolls
back. Removing someone sends the group event, then closes their sockets, then
sends `room_updated`. A failed send is logged and skipped.

### `save_message` (to members, see above)

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
  "kind": "text",
  "reply_to": null
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

#### Replies and the `reply_to` object

Every message object (the page's initial JSON, `GET /chat/rooms/<uuid>/messages/`,
`save_message` and `message_updated`) has a `reply_to` key. It takes one of
four forms, built for each viewer when the message is sent or loaded:

| Case | `reply_to` |
| --- | --- |
| Plain message, a deleted reply, or the original was removed from the database | `null` |
| You can't see the original (you cleared it, or joined after it) | `{"id": "<uuid>", "available": false}` |
| The original is deleted | `{"id": "<uuid>", "available": true, "deleted": true, "user": "maya", "name": "Maya Rao"}` |
| Otherwise | `{"id": "<uuid>", "available": true, "deleted": false, "user": "maya", "name": "Maya Rao", "excerpt": "Can we keep Graphite + Coral as the default?"}` |

A viewer who can't see the original gets only its id: never its author or
text. `excerpt` is the original's current text with every run of whitespace
collapsed to one space, trimmed, and cut to the first 200 characters (no
ellipsis). `user`, `name` and `excerpt` are plain text.

For a new reply, and for an edit or delete of a reply, the server splits the
recipients in two: people who can see the original get the full quote, the
rest get `{"id": "<uuid>", "available": false}`. Each group gets its own
frame (one extra query to find who can see the original).

When an original is edited or deleted, its `message_updated` frame is the
usual one. Clients update every loaded quote whose `reply_to.id` matches it:
the new excerpt (computed from `message` with the same rule) or the deleted
state. Quotes shown as unavailable stay unavailable.

### `typing` (to every socket in the room, including yours)

```json
{"type": "typing", "user": "maya", "name": "Maya Rao"}
```

Clients ignore their own and show "Maya Rao is typing…" for 4 seconds or
until that person's message arrives.

### `room_updated` (to current members)

```json
{"type": "room_updated", "room": "<room uuid>", "name": "Design crew", "member_count": 4}
```

Sent after any group change (members added or removed, admins changed,
renamed). Clients update the header and sidebar and reload the Details panel
if it's open.

### `message_updated` (to people who can see the message)

Sent after an edit or delete, with the same fields as `save_message`. A deleted
message has `"deleted": true`, an empty `message` and `"reply_to": null`; an
edited one has `"edited": true`. The same people also get a `room_refresh` frame on their
inbox socket (see below).

You can only edit or delete your own messages that you can still see. After
you clear your history, your older messages can't be edited or deleted by
you (the server answers `403`).

### `clear_room` (to the requesting socket only)

```json
{"type": "clear_room", "cleared": true, "for": "maya"}
```

### `error` (to the requesting socket only)

```json
{"type": "error", "code": 400, "message": "Message cannot be empty", "ts": "…", "for": "save_message"}
```

Sent for invalid JSON, a non-object payload, an unknown `type`, an empty or
over-long message, a refused reply, editing or deleting a message you can't
change, and when a connection is refused (`403`, `404`).

`for` is the `type` of the client frame the error answers (`save_message`,
`edit_message`, `delete_message`, …), so the page can tell which request
failed: it puts a refused reply's text and target back only for
`"for": "save_message"`. `for` is absent when the error doesn't answer a
known frame type: invalid JSON, a non-object payload, an unknown `type`, and
refusals (on connect, or when membership is checked on a frame).


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
room already open. The embedded message always has `"reply_to": null`: the
room list shows a reply's own text, never its quote.

```json
{
  "type": "room_activity",
  "room": "<room uuid>",
  "unread": 3,
  "message": {"id": "…", "message": "standup in 5", "user": "anika", "…": "…", "reply_to": null}
}
```

**`room_added`**, **`room_changed`**, **`room_removed`**, **`room_refresh`**:
keep the room list live. All four are sent only after the database change
commits, and none if it rolls back.

| Frame | Sent to | When |
| --- | --- | --- |
| `room_added` | People who gain a room | A direct chat or group is created with them in it, or they're added to a group |
| `room_changed` | Members at commit time, except people just added | A group is renamed, or people are added, removed or leave |
| `room_removed` | People who lose a room | They're removed or leave (their other tabs), or the group is deleted |
| `room_refresh` | Current members who can see the message | A message is edited or deleted |

`room_added` carries that person's own view of the room (a direct chat is
titled with the other person's name):

```json
{
  "type": "room_added",
  "room": {
    "id": "<room uuid>", "title": "Launch prep", "initials": "LP", "type": "group",
    "member_count": 3, "last_content": "", "last_at": null, "last_is_mine": false,
    "unread": 0, "other_username": "", "member_usernames": ["arjun", "maya", "sam"]
  }
}
```

`room_changed` is one partial room object, the same for every member, and is
only sent for groups. It has only these keys; the page applies them and never
touches the preview, time or unread count from it. When the member list
changes, the page asks for a fresh `presence_snapshot` (a `ping`).

```json
{
  "type": "room_changed",
  "room": {
    "id": "<room uuid>", "title": "Launch prep", "initials": "LP",
    "member_count": 3, "member_usernames": ["arjun", "maya", "sam"]
  }
}
```

People who are added get `room_added`, not `room_changed`. The person who is
removed or leaves gets only `room_removed`. When the last member leaves, the
group is deleted and no `room_changed` is sent.

```json
{"type": "room_removed", "room": "<room uuid>"}
```

`room_refresh` means the room's preview may have changed (for example, its
last message was deleted). The page refetches that row from
`GET /chat/rooms/<uuid>/summary/`.

```json
{"type": "room_refresh", "room": "<room uuid>"}
```

After a `room_added` frame the page sends a `ping`, so the next
`presence_snapshot` includes the new room's members.

### When the open room goes away

If `room_removed` names the room you have open, or a resync no longer lists
it, the page reconnects that room's socket instead of guessing why:

1. A refusal with `4403` shows the "You’re no longer in <name>" pane; `4404`
   shows "<name> was deleted".
2. If the socket stays open for 1 second, you're still a member (for example,
   you were added back), and the page fetches the room's row again.
3. If neither happens within 3 seconds (for example, you're offline), the page
   shows the "no longer in" pane.

### Missed frames and resync

If a `room_activity` or `room_changed` frame names a room the page doesn't
list (a `room_added` frame was missed), the page fetches the row from
`GET /chat/rooms/<uuid>/summary/`, which returns the same `room` object as
`room_added`.

Every time the inbox socket opens, the page fetches the whole list from
`GET /chat/rooms/summaries/` and makes the page match it: missing rooms are
added, rooms not in the list are removed, and titles, previews and unread
counts are updated. This includes the first connect after page load: frames
sent between the server rendering the page and the socket joining its group
would otherwise be lost.

```json
{"rooms": [{"id": "<room uuid>", "title": "Launch prep", "…": "…"}]}
```

The rooms are the same objects as `room_added`, most recent first. A row that
a live frame changed after the fetch started keeps the live version, and a
room removed after the fetch started isn't added back.

Presence and activity use the database and the channel layer, so they work
across server processes when `REDIS_URL` is set. Connections left behind by
a crashed process stop counting after 90 seconds and are deleted after an
hour.
