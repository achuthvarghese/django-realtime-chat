# Changelog

Changes are grouped by rework phase. Each phase lands as its own pull request
into `master`.

## Fixes after phase 5

- Touch screens no longer show Edit and Delete on every one of your messages;
  tap a message to show its actions.

## Phase 5d: presence, typing and unread

### Added
- **Presence**: an inbox socket per page records your connection; people who
  share a room with you see a green dot on your avatar and "Online" in the
  header, and groups show how many members are online. Survives multiple
  processes and crashed processes (90-second window, 30-second ping).
- **Typing indicator**: "Maya Rao is typing…" in the room header, throttled
  on both client and server.
- **Unread counts**: per-room badges, bold unread rooms and the total in the
  browser tab title. Opening a room, reading new messages while the tab is
  visible, or sending a message marks it read.
- Live updates for other rooms: preview, time, order and unread badge.
- `ReadState` and `Connection` models; `read` and `typing` room frames;
  `/inbox/` socket with `presence_snapshot`, `presence` and `room_activity`.

## Phase 5c: message actions and history

### Added
- Edit and delete your own messages: hover or focus actions, inline editing
  (Enter saves, Esc cancels), ↑ in an empty composer to edit your last
  message, a confirmation before deleting. Updates reach everyone live as
  `message_updated` frames; messages show "(edited)" or "Message deleted".
- Infinite scroll: the room opens with the latest 50 messages and loads 50
  more when you scroll to the top, keeping your place.
- `/chat/rooms/<uuid>/messages/` JSON history endpoint.
- `Message.edited_at`, `Message.deleted_at` and a `(room, created_at)` index.

### Changed
- Deleting a message erases its text in the database.
- Room previews skip deleted messages.

## Phase 5b: settings

### Added
- Settings page at `/account/settings/` with Profile (name, email), Appearance
  and Password sections, linked from your name in the chat sidebar.
- `Preference` model: palette, mode and density saved to the account. Pages
  render the saved theme for signed-in users and the theme picker saves each
  change, so the choice follows you across devices.
- The palette picked during signup is saved as the first preference.
- `docs/data-model.md`.

### Changed
- The Show/Hide password control moved into the shared stylesheet so it works
  on light surfaces as well as on the sign-in screens.

## Phase 5a: start chats

### Added
- **New chat** dialog: search people by name or username and open a direct
  chat (reusing an existing one), or name a group and add people as chips.
- `/chat/people/` JSON search, and POST endpoints to start direct chats and
  create groups, with validation (no chats with yourself, group name up to 50
  characters, 1 to 49 other members, active users only).
- Flash notices on the chat screen.

### Fixed
- An empty room no longer shows a bare spine above "No messages yet".

## Phase 4: chat screen

### Added
- Chat screen on the design system: chrome sidebar with your chats, a
  transcript pane and a floating composer. Responsive: full list from 1024px,
  icon rail from 600px, one pane at a time with a back arrow on phones.
- Room list sorted by latest activity with last-message preview and time, and
  "Find a chat" filtering.
- Transcript grouping: one line per message, avatar and name only when the
  sender changes or after a 5-minute gap, day separators, local times, kept
  line breaks.
- Connection status (Connecting…, Live, Reconnecting…), automatic reconnect
  with backoff and a Reload prompt afterwards.
- Composer that grows with the text; Enter sends, Shift+Enter adds a line.
- Clear history now asks for confirmation.
- `name` and `initials` in `save_message` frames.

### Changed
- History shows the latest 200 messages.
- Bootstrap, Bootstrap Icons and the background pattern image are removed
  from the chat page; no page uses Bootstrap any more.
- The room-title template tag is replaced by `chat/presenters.py`.

## Phase 3: home, sign in and create account

### Added
- Public home page at `/` with a sample transcript and a feature spine.
  Signed-in visitors go straight to their chats.
- New sign-in and create-account screens on the design system: a transcript
  panel that ends with a pulsing "now" node for you, inline field errors,
  Show/Hide password, and a Theme menu.
- Create account groups its fields into Account, Name, Password and Theme
  steps on a spine; each node fills in as its step is completed. Choosing a
  palette there applies and saves it on the device.
- `docs/screens.md`: every screen and URL.

### Changed
- The chat moved from `/` to `/chat/`.
- Form inputs carry `autocomplete` values and `aria-invalid` /
  `aria-describedby` for errors. Password help lists the password rules.
- Usernames are validated with Django's username rules; field lengths match
  the user model.
- Bootstrap is no longer used on the account screens. The old account base
  template and stylesheets are removed.

## Phase 2: design system

### Added
- `core` app with the Signal design system: design tokens, base styles and
  components (buttons, fields, notices, avatars, badges, segmented controls,
  transcript spine, composer, app shell).
- Six palettes (Graphite + Coral by default, Midnight + Saffron, Slate +
  Electric, Plum + Rose, Moss + Tangerine, Paper + Red), light, dark or system
  mode, and compact or comfortable density. Choices apply instantly and are
  saved on the device.
- Shared `core/base.html` with a skip link and no theme flash on load.
- Site error pages for 400, 403, CSRF failures, 404 and 500.
- `/styleguide/` component gallery when debugging.
- `docs/design-system.md`.

Existing login, signup and chat screens keep their current look until the
next phases move them onto this base.

## Phase 1: security and bug fixes

### Security
- WebSocket connections now require a signed-in user who is a member of the
  room. Previously anyone, including anonymous visitors, could read and post
  to any room.
- Messages and user names are rendered as text in the browser, closing a
  stored XSS hole. The room title tag no longer marks user names as safe HTML.
- The chat page returns 404 for rooms the user is not a member of instead of
  showing their title and members.
- Logout only accepts POST, so links or images on other sites cannot sign
  users out.
- The login `next` parameter is followed only for same-site URLs.

### Fixed
- Malformed JSON, missing fields and unknown message types no longer crash the
  socket; the sender gets an `error` frame instead of a broadcast.
- Empty and over-long (more than 4000 characters) messages are rejected.
- Clearing a room only notifies the requesting user.
- `wss://` is used on HTTPS pages.
- The chat script no longer fails when the current room is missing from the
  list, or when moment.js cannot load (replaced with `Intl.DateTimeFormat`).
- Room search is case-insensitive and filters as you type; Enter sends a
  message.
- Malformed room ids in the URL return 404 instead of a server error.
- Private rooms without a second member fall back to the room name.
- Signup uses validated form data, saves first and last names, signs the new
  user in and treats usernames case-insensitively when checking for
  duplicates.
- Login authenticates once and shows the same error for unknown users and
  wrong passwords.

## Phase 0: foundation

- Django 5.2 LTS, Channels 4 and Daphne; the project starts on Python 3.12+.
- Settings from environment variables or `.env`; Redis channel layer via
  `REDIS_URL`.
- Chat migrations committed.
- Docker image on Python 3.12; migrations run at start-up.
- pytest suite and CI on Python 3.12 and 3.13.
- README rewritten; setup and testing guides added.
