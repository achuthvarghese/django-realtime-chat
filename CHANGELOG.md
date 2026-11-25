# Changelog

Changes are grouped by rework phase. Each phase lands as its own pull request
into `master`.

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
