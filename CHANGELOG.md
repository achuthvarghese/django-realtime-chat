# Changelog

Changes are grouped by rework phase. Each phase lands as its own pull request
into `master`.

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
