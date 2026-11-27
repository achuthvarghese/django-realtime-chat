# Screens and URLs

| URL | Name | Who | Screen |
| --- | --- | --- | --- |
| `/` | `core:home` | Signed out | Home page. Signed-in users are redirected to `/chat/` |
| `/account/login/` | `account:login` | Signed out | Sign in. Accepts a same-site `?next=` |
| `/account/signup/` | `account:signup` | Signed out | Create account; signs the new user in |
| `/account/logout/` | `account:logout` | Signed in | POST only; returns to sign in |
| `/chat/` | `chat:chat` | Signed in | Room list; `?room=<uuid>` opens a room. A room you can't open (not a member, deleted, unknown or a bad id) redirects to `/chat/` with the notice "That chat isn’t available. You may have been removed, or it was deleted." |
| `/chat/people/?q=` | `chat:people` | Signed in | JSON people search for New chat |
| `/chat/rooms/<uuid>/messages/` | `chat:history` | Room members | JSON page of older messages: `?before=<message id>&limit=1..100`. `before` must be a message in this room that you can see; otherwise 400 `{"error": "Unknown message"}` |
| `/chat/rooms/summaries/` | `chat:summaries` | Signed in | JSON `{"rooms": [...]}`: every room-list row, most recent first. The list resyncs with it when the inbox socket reconnects |
| `/chat/rooms/<uuid>/summary/` | `chat:summary` | Room members | JSON room-list row (the `room` object of the inbox `room_added` frame) |
| `/chat/rooms/<uuid>/details/` | `chat:details` | Room members | HTML for the Details panel |
| `/chat/rooms/<uuid>/group/<action>/` | `chat:group_action` | Room members | POST; `action` is `add` (`members`), `rename` (`name`), `make-admin`, `remove-admin`, `remove` (`username`), `leave` or `delete`. JSON with `Accept: application/json`, otherwise a redirect with a notice |
| `/chat/new/direct/` | `chat:start_direct` | Signed in | POST `username`; opens or creates the direct chat |
| `/chat/new/group/` | `chat:start_group` | Signed in | POST `name` and `members`; creates a group |
| `/account/settings/` | `account:settings` | Signed in | Redirects to the Profile section |
| `/account/settings/profile/` | `account:settings_profile` | Signed in | Name and email |
| `/account/settings/appearance/` | `account:appearance` | Signed in | GET shows the section; POST any of `palette`, `mode`, `density` (JSON when `Accept: application/json`) |
| `/account/settings/password/` | `account:settings_password` | Signed in | Change password |
| `/styleguide/` | `core:styleguide` | Debug only | Component gallery |
| `/admin/` | | Staff | Django admin |
| `ws(s)://<host>/chat/<uuid>` | | Room members | Live room socket, see [websocket-protocol.md](./websocket-protocol.md) |

## Home

Chrome-coloured page in the active palette.

- **Nav**: wordmark, Theme menu, Sign in, Create account. On phones Sign in
  moves out of the nav and stays in the hero.
- **Hero**: headline, one-line pitch, the two calls to action, and a sample
  conversation drawn with the real transcript components.
- **Features**: four items hanging off a horizontal spine that turns vertical
  below 860px.

Template `core/templates/core/home.html`, styles `core/static/core/css/home.css`.

## Sign in and create account

Both use `account/templates/account/auth_base.html`:

- **Left panel** (hidden below 820px): wordmark, tagline and a short transcript
  that ends with a pulsing "now" node for you ("signing in…", "joining
  relay…"). On phones only that "now" line is shown above the form.
- **Right panel**: Theme menu, notices, the form.

Form behaviour:

- Each field is rendered by `account/partials/field.html`: label, input, then
  either its errors (`id="<field>-error"`, linked with `aria-describedby`) or
  its help text. Inputs with errors get `aria-invalid="true"`.
- Password fields have a Show/Hide toggle.
- Correct `autocomplete` values (`username`, `current-password`,
  `new-password`, `email`, `given-name`, `family-name`) let password managers
  work.
- Sign-in errors are the same for an unknown user and a wrong password.

Create account lays its fields on a spine of four steps: **Account**
(username, email), **Name**, **Password** (with the password rules as help
text) and **Theme**. A step's node fills in once its fields are complete and
valid, and turns red when the server reported an error in it. Picking a palette
in the Theme step applies it immediately and saves it on the device; it is not
sent with the form.

Styles `account/static/account/css/auth.css`, script
`account/static/account/js/auth.js`.

## Chat

`/chat/` lists your chats; `/chat/?room=<uuid>` opens one. Template
`chat/templates/chat/chat.html`, styles `chat/static/chat/css/chat.css`, script
`chat/static/chat/js/chat.js`.

### Layout by width

| Width | Room list | Open room |
| --- | --- | --- |
| 1024px and up | Names, last-message preview and time | Beside the list |
| 600 to 1023px | Icon rail of initials; name on hover. Screen readers still hear each room's name, preview and unread count, and the New chat button's name | Beside the rail |
| Under 600px | Full screen when no room is open | Full screen with a back arrow |

### Room list

- Most recently active first. Each row shows the other person's name (private
  rooms) or the room name (groups), the last message you can still see
  (prefixed "You:" when it was yours) and its time: clock time today,
  "Yesterday", or a short date. Previews are cut to 60 characters. Times
  update at local midnight and when you come back to the tab.
- Group rooms have round avatars; private rooms square, with a dot that turns
  green while the other person is online.
- Rooms with unread messages show a count badge and bold text; the browser
  tab title shows the total, for example "(3) Chats · Relay". New messages in
  other rooms update the preview and move the room to the top live.
- The list changes live, without a reload: a chat or group someone starts
  with you grows into place at the top and briefly flashes the accent colour,
  a renamed group updates its title, and a group you're removed from (or
  that's deleted) disappears. Edits, deletes and clearing your history update
  the row's preview. If you have that room open, it shows the
  [gone pane](#when-the-open-room-goes-away).
- If the connection drops, the list fetches every row again when it
  reconnects, so it catches up on anything it missed.
- "Find a chat" filters the list as you type, and keeps filtering as rows
  arrive, change or go. It's hidden while you have no chats.
- The footer row (your avatar, name and @username, with a chevron) is the
  **account menu** button: it opens Settings and Sign out above it, and the
  chevron flips while it's open. Escape or a click elsewhere closes it. On the
  tablet rail the avatar alone is the button. The theme is changed in
  Settings → Appearance; the chat screen has no Theme button.

### Open room

- **Header**: avatar, title, connection status (Connecting…, Live,
  Reconnecting…), then "Online"/"Offline" for a private chat or "N members ·
  N online" for a group, a "… is typing…" indicator, and a **Details** button
  (ⓘ) that opens the [Details panel](#group-details). Opening a room marks it
  read.
- **Transcript**: the latest 50 messages you can see; scrolling to the top
  loads 50 more at a time ("Loading earlier messages…") until "Start of the
  conversation". Messages are grouped one line per
  message. A new sender, a gap of more than 5 minutes or a new day starts a new
  group with the avatar and name; day separators read Today, Yesterday or the
  date. Times are shown in your local time zone; follow-up times appear on
  hover. Line breaks are kept. New messages keep the view pinned to the bottom
  unless you have scrolled up to read. A reply always starts a new group.
- **Action bar**: every text message (not group events, not deleted ones)
  has a small bar of actions at its top right, shown on hover or when you
  Tab into it. **Reply** is on everyone's messages, including your own; **Edit**
  and **Delete** only on yours. Each button is named for its message ("Reply
  to Maya Rao", "Edit your message") and described by the message's time. On
  touch screens, tap any text message to select it and show its bar on a line
  below; tap it again or another message to hide it.
- **Edit and delete**: Edit opens an inline box: Enter saves, Esc
  cancels. Delete asks for confirmation and leaves "Message deleted" for
  everyone. Edited messages show "(edited)". Changes reach everyone live, and
  the sidebar preview follows edits and deletes of the latest message.
- **Keyboard in the transcript**: the transcript is one Tab stop. Tab lands on
  the newest message (or the one you last moved to); ↑ and ↓ move between
  messages, Home and End go to the first and last loaded. ↑ on the oldest
  loaded message loads the page before it. From a focused message, Tab moves
  into its quote and action buttons, then on out of the transcript.
- **Composer**: grows with the text up to about six lines. Enter sends,
  Shift+Enter adds a line, ↑ in an empty composer edits your last message. Send is disabled while disconnected; the text stays
  in the box.
- **Group events** ("Maya added Lee", "Arjun is now an admin") appear as muted
  one-line rows with a small diamond on the spine. They never join a sender's
  group of messages, can't be edited, and don't count as unread or show as the
  room preview.
- **Clear history** (in the Details panel) asks for confirmation (Cancel is the
  default) and hides the room's messages for you only.
- **Connection**: if the socket drops, the page retries after 1, 2, 4, 8 and
  then every 15 seconds. After reconnecting it offers a Reload, since
  messages sent in between are not replayed. Being signed out sends you to
  sign in. If you're removed from a group, or it's deleted, while it's open,
  the page shows the gone pane below and stays on it.

#### Replies

- **Reply** (in the action bar) opens a "Replying to <name>" bar on top of
  the composer, joined to it as one unit, with a one-line excerpt of the
  message and a × button ("Cancel reply"). Replying to your own message reads
  "Replying to yourself". Focus moves to the composer; screen readers hear
  "Replying to <name>". While replying, the placeholder reads "Reply to
  <name>" and the hint "Esc cancel reply · Shift ↵ new line". If you were at
  the bottom of the transcript, it stays there as the bar opens and closes.
- **Sending** sends the reply and closes the bar. Esc in the composer or the
  bar, or ×, cancels the reply ("Reply cancelled"). Escape closes the
  innermost thing first: an open dialog or menu, then the reply, then the
  Details panel. If the message you're replying to is deleted, the bar closes
  with "The message you were replying to was deleted."
- If the server refuses the reply (the message was deleted or hidden
  meanwhile), the toast says "You can't reply to that message" and your text
  comes back, with the bar if the message can still be replied to. It doesn't
  come back over something new you've started typing.
- **Quotes**: a reply shows a one-line quote of its original above its text,
  with an accent rule on the left: the original's author ("You" for yours)
  and the start of its text. The quote is live: it follows edits of the
  original, and reads "Message deleted" (in italics) once the original is
  deleted. If you can't see the original (you cleared your history, or joined
  after it), the quote reads "Original message unavailable", isn't a button,
  and its tooltip says "Sent before you joined, or not visible to you". A
  deleted reply shows no quote; if the original is removed from the database,
  the reply shows as a plain message.
- **Jump to the original**: click a quote (or Enter on it) to scroll the
  original to the middle of the view, tint it in the accent colour for about
  1.6 seconds and focus it. With reduced motion it doesn't animate the scroll
  and shows a still tint. If the original isn't loaded yet, the page loads
  older messages 100 at a time, up to 10 pages, then jumps. If it still isn't
  found, a toast says "That message is too far back." ("Couldn't find that
  message." when the start of the conversation was reached). Deleted
  originals can still be jumped to.
- The room list's preview of a reply is the reply's own text, never the quote.

#### When the open room goes away

When you're removed from the open group, leave it in another tab, or it's
deleted, the room is replaced by a pane that names the chat:

| | Removed or left | Deleted |
| --- | --- | --- |
| Header | Muted avatar and title, "Not a member" instead of the member count | Muted avatar and title, "Deleted" |
| Heading | "You’re no longer in <name>" | "<name> was deleted" |
| Text | "You were removed or left, so you can’t read or send messages here any more. Ask a member to add you back." | "An admin deleted it, so its messages are gone for everyone." |
| Tab title | "No longer in <name> · Relay" | "<name> was deleted · Relay" |

- The Details button goes and the Details panel closes; on phones the back
  arrow stays. A **Back to chats** button returns to `/chat/` (at least 44px
  tall on touch screens and phones).
- Focus moves to the heading, which is the page's only `h1`. The room title
  in the header becomes a plain paragraph.
- The unread count prefix in the tab title, for example "(2)", still works.
- Which copy you see comes from the room socket: the page reconnects it and
  the server's close code (`4403` or `4404`) picks the text. If there's no
  answer within 3 seconds (for example, you're offline), it shows the
  "no longer in" copy. See
  [websocket-protocol.md](./websocket-protocol.md#when-the-open-room-goes-away).

#### With no room open

The pane shows a short welcome with a New chat button: "Pick a chat" and
"Choose a conversation from the list, or start a new one." when you have
chats, or "Welcome, <your name>" and "You’re not in any chats yet. Message
someone or start a group." when you don't. The text switches as the first
room arrives or the last one goes.

Notices, such as "That chat isn’t available…" or "You left <group>.", show
above the welcome on desktop and tablet. On phones, where that pane is
hidden, they show at the top of the room list instead.

### Group details

The **Details** button in the room header opens a panel: a third column on
desktop and tablet, full screen on phones. Escape closes the innermost open
thing first (a menu or dialog, then a reply you're writing when focus is in
the composer, then the panel). Escape in an inline message edit cancels the
edit and leaves the panel open.

| Part | Who sees it | What it does |
| --- | --- | --- |
| Name, member count, "Created by" | Everyone | Direct chats show the other person's @username instead |
| Rename group | Admins | Inline form; the new name reaches everyone's header and sidebar live |
| Members | Everyone | You first, then admins, then others; Admin badge and online dot |
| + Add people | Any member | Search by name or username, pick people as chips, **Add to group** |
| Member menu (⋯) | Admins | **Make admin** / **Remove admin**, **Remove from group** (asks first) |
| Your own menu (⋯) | Admins | **Step down as admin** when other admins exist; otherwise a note says to make someone else admin first |
| Clear history (for you) | Everyone | Same as before, now here instead of the header |
| Leave group | Everyone in a group | Asks first; warns the only admin that the longest-standing member will become admin. Returns to the list with "You left <group>." |
| Delete group | Admins | Asks first; deletes the group and its messages for everyone |

#### Group permissions

| Action | Admins | Members |
| --- | --- | --- |
| Add people | ✅ | ✅ |
| Rename, remove members, delete the group | ✅ | ❌ |
| Make someone admin, remove admin | ✅ | ❌ |
| Leave | ✅ | ✅ |

- The person who creates a group is its first admin; a group can have several.
- The only admin can't remove their own admin role: they make someone else
  admin, then step down.
- When the last admin leaves, the member who joined earliest becomes admin.
- When the last member leaves, the group is deleted.
- Groups hold up to 50 members. Direct chats have no admins or members to
  manage.

Every change is announced in the chat as a group event. The rules live in
`chat/groups.py`. When a change isn't allowed, the panel shows a fixed
sentence from `GROUP_ERROR_MESSAGES` there (for example "Only admins can do
that."); error responses never include exception text.

### New chat

The **New chat** button (top of the sidebar, and on the welcome pane) opens a
dialog with two tabs:

- **Direct**: search by name or username (`@` optional). Picking a person
  opens your existing private chat with them, or creates one. You can't start
  a chat with yourself.
- **Group**: give the group a name (up to 50 characters), search and add
  people as chips (click again or × to remove), then **Create group**. You are
  added automatically. Groups hold up to 50 members.

Search matches usernames, first names, last names and "first last", ignores
inactive accounts and returns up to 20 people. Errors (unknown people, missing
name) appear as a notice above the chat.

## Settings

Reached from the account menu in the chat sidebar. A chrome
side menu (a scrolling tab strip on phones) lists the sections; each has its
own URL, and `/account/settings/` opens Profile.

| Section | URL | Contents |
| --- | --- | --- |
| **Profile** | `/account/settings/profile/` | Your initials avatar, name and read-only @username ("usernames can't be changed"); first name, last name and email (required, validated). Saving shows "Profile saved." |
| **Appearance** | `/account/settings/appearance/` | The full theme picker. Each change applies at once and is saved to your account, so every device you sign in on uses it. "Saved." confirms; if saving fails the choice still applies on this device. Without JavaScript, a Save button posts the form |
| **Password** | `/account/settings/password/` | Current password plus the new one twice, checked against the password rules. You stay signed in after changing it |

More sections (Notifications, Privacy) are added with the features that need
them. The palette picked during signup is saved as your first preference.

## Username rules

Usernames are chosen at signup and can't be changed.

| Rule | Valid | Rejected |
| --- | --- | --- |
| 3 to 30 characters | `lee`, `maya_rao2` | `al` |
| Lowercase letters, numbers and `_` only | `lee2` | `Lee`, `lee.chen`, `lee-chen` |
| Starts with a letter | `lee` | `2fast`, `_sam` |
| No `_` at the end or twice in a row | `a_b_c`, `sam_2` | `sam_`, `a__b` |
| Unique | | an existing name, in any letter case |

While you type, the signup field formats for you: capitals become lowercase
and spaces become a single `_` ("Maya Rao" → `maya_rao`). Other characters stay
so the error under the field can say what's wrong. Sign-in applies the same
formatting, so `MAYA` or `Maya Rao` find `maya` and `maya_rao`.

Rules live in `account/usernames.py`. Accounts created before these rules were
renamed by migration `account/0002_conform_usernames` (see
[setup.md](./setup.md#upgrading)).
