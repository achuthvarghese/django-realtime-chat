# Screens and URLs

| URL | Name | Who | Screen |
| --- | --- | --- | --- |
| `/` | `core:home` | Signed out | Home page. Signed-in users are redirected to `/chat/` |
| `/account/login/` | `account:login` | Signed out | Sign in. Accepts a same-site `?next=` |
| `/account/signup/` | `account:signup` | Signed out | Create account; signs the new user in |
| `/account/logout/` | `account:logout` | Signed in | POST only; returns to sign in |
| `/chat/` | `chat:chat` | Signed in | Room list; `?room=<uuid>` opens a room |
| `/chat/people/?q=` | `chat:people` | Signed in | JSON people search for New chat |
| `/chat/rooms/<uuid>/messages/` | `chat:history` | Room members | JSON page of older messages: `?before=<message id>&limit=1..100` |
| `/chat/new/direct/` | `chat:start_direct` | Signed in | POST `username`; opens or creates the direct chat |
| `/chat/new/group/` | `chat:start_group` | Signed in | POST `name` and `members`; creates a group |
| `/account/settings/` | `account:settings` | Signed in | Profile, appearance and password |
| `/account/settings/appearance/` | `account:appearance` | Signed in | POST any of `palette`, `mode`, `density`; JSON when `Accept: application/json` |
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
| 600 to 1023px | Icon rail of initials; name on hover | Beside the rail |
| Under 600px | Full screen when no room is open | Full screen with a back arrow |

### Room list

- Most recently active first. Each row shows the other person's name (private
  rooms) or the room name (groups), the last message you can still see
  (prefixed "You:" when it was yours) and its time: clock time today,
  "Yesterday", or a short date.
- Group rooms have round avatars; private rooms square.
- "Find a chat" filters the list as you type.
- The footer shows you, the Theme menu and Sign out.

### Open room

- **Header**: avatar, title, connection status (Connecting…, Live,
  Reconnecting…) and member count, plus **Clear history**.
- **Transcript**: the latest 50 messages you can see; scrolling to the top
  loads 50 more at a time ("Loading earlier messages…") until "Start of the
  conversation". Messages are grouped one line per
  message. A new sender, a gap of more than 5 minutes or a new day starts a new
  group with the avatar and name; day separators read Today, Yesterday or the
  date. Times are shown in your local time zone; follow-up times appear on
  hover. Line breaks are kept. New messages keep the view pinned to the bottom
  unless you have scrolled up to read.
- **Your messages** show Edit and Delete on hover or keyboard focus (always
  visible on touch screens). Edit opens an inline box: Enter saves, Esc
  cancels. Delete asks for confirmation and leaves "Message deleted" for
  everyone. Edited messages show "(edited)". Changes reach everyone live, and
  the sidebar preview follows edits and deletes of the latest message.
- **Composer**: grows with the text up to about six lines. Enter sends,
  Shift+Enter adds a line, ↑ in an empty composer edits your last message. Send is disabled while disconnected; the text stays
  in the box.
- **Clear history** asks for confirmation in a dialog (Cancel is the default)
  and hides the room's messages for you only.
- **Connection**: if the socket drops, the page retries after 1, 2, 4, 8 and
  then every 15 seconds. After reconnecting it offers a Reload, since
  messages sent in between are not replayed. Being signed out sends you to
  sign in; losing access to the room sends you back to the list.

With no room open, the pane shows a short welcome with a New chat button.

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

`/account/settings/`, reached from your name at the bottom of the chat sidebar.
A chrome side menu (a top bar on phones) links to three sections:

- **Profile**: first name, last name and email (required, validated). Saving
  shows "Profile saved."
- **Appearance**: the full theme picker. Each change applies at once and is
  saved to your account, so every device you sign in on uses it. "Saved."
  confirms; if saving fails the choice still applies on this device. Without
  JavaScript, a Save button posts the form.
- **Password**: current password plus the new one twice, checked against the
  password rules. You stay signed in after changing it.

Each form posts its own `section`, so an error in one never clears another.
The palette picked during signup is saved as your first preference.
