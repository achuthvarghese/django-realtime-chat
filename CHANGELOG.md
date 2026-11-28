# Changelog

Changes are grouped by rework phase. Each phase lands as its own pull request
into `master`.

## Phase 10c: mentions

Mention a member with `@username`. The name is highlighted in the message,
the composer suggests people as you type, and group chats with unread
mentions of you or replies to you show an "@" next to the unread count.
Notifications and muting chats come next, in their own phase (10d); this
phase has no notification list, and no `@everyone` or `@here`.

### Added
- `chat.Mention`: one member named in one text message (`message`, `user`),
  with the constraint `unique_mention`, and `Message.mentions`, a
  many-to-many to `User` through it. Migration `chat/0007_mention` adds the
  field to the model state only, so SQLite doesn't rebuild the message
  table. Mentions are in the Django admin.
- `chat/mentions.py`: finds mentions in message text and keeps the `Mention`
  rows in step. A mention is `@` and the exact username (any case, compared
  with `casefold()`) of a current member other than the author, not right
  after a letter, digit or underscore and not running on into a longer
  handle; the longest username wins at one `@`; at most 200 `@` signs are
  looked at. Anything else stays plain text and nobody is told.
- Every message object has a `mentions` list (`user`, `name`) in the order
  the text names them; deleted and system messages have `"mentions": []`.
- Room objects (the page, summaries, `room_added`) have `mentions`: unread
  messages that mention you or reply to one of your messages you can still
  see. Always 0 for direct chats.
- Inbox `room_activity` frames have `mentions` (your count for the room) and
  `for_you` (`"mention"`, `"reply"` or `null`).
- Highlighted mentions in messages, stronger for mentions of you, and a
  subtle "for you" edge and tint on group messages that mention or reply to
  you (`.mention`, `.mention--me`, `.msg--for-you`).
- Mention autocomplete in the composer: `@` opens a list of up to 8 members,
  searched by username or name (any word, any part of a hyphenated word,
  any script). ↑ and ↓ move, Enter or Tab inserts `@username `, Escape
  closes it first, before dialogs, the reply and the Details panel. A polite
  status tells screen readers how many people match, and the composer hint
  changes while the list is open.
- An outlined "@" chip on group rows in the room list, before the unread
  count ("Mentions and replies: N. Unread: M" for screen readers). On the
  tablet rail it shows alone. Room rows carry `data-room-type` and
  `data-mentions`.
- Demo mentions in Design team, Ops and Book club (seven in the script, six
  stored: Priya's cleared history drops one) and a reply to Maya, so `maya`
  sees "@" on Design team and Ops and `priya` on Book club.

### Changed
- Unread and mention counts stop at 100 per chat. Badges show "99+", and the
  tab title shows "(99+)" once the total reaches 100 or any chat is capped.
- Unread and mention counts for the room list come from one grouped query,
  with each room's last read time as a subquery, instead of one condition
  per room.
- An inbox socket no longer loads the room for each new message: the event
  says whether it's a group, and the socket reads its read state first and
  counts at most 100 rows (up to three small queries).
- History pages take three queries: messages, reactions and mentions.
- Edits recompute mentions; `message_updated` carries the new list, and a
  deleted message has `"mentions": []`.
- **Clear history** also removes your mentions in the messages you cleared.
- Demo counts for `maya`: Design team 5 unread (2 "@"), Ops 6 (1 "@"); the
  tab title reads "(12) Chats · Relay".

### Fixed
- An edit racing a delete of the same message (from another tab) could
  write the text back onto the deleted message; it now changes nothing.

## Phase 10b: reactions

React to a text message with one of six emoji. The message shows a chip per
emoji with its count; clicking a chip adds or removes your reaction, and
changes appear live for everyone who can see the message.

### Added
- `chat.Reaction`: one person's emoji on one text message (`message`,
  `user`, `emoji`, `created_at`), with the fixed set `ReactionEmoji`
  (`thumbs_up`, `heart`, `laugh`, `wow`, `sad`, `party`). Constraints
  `unique_reaction` (one of each emoji per person) and
  `reaction_emoji_valid`. Migration `chat/0006_reaction`. Reactions are in
  the Django admin.
- `react` socket frame (`id`, `emoji`, `on`). It is idempotent: a no-op
  changes nothing and sends the current state to the sender's socket only.
  A refused frame gets the fixed error "You can't react to that message"
  (`400`); more than 10 `react` frames per user in 5 seconds get "Slow down"
  (`429`); a busy database gets "Try again" (`503`). All carry
  `"for": "react"`.
- `reactions_updated` frame with the message's whole `reactions` list, sent
  after each change to current members who can still see the message.
- Every message object has a `reactions` list (emoji, count and the people
  who reacted, in reaction order). Deleted, system and new messages, and
  inbox `room_activity` frames, carry `"reactions": []`.
- `chat/reactions.py`: checks and saves reactions, the per-user rate limit
  (kept in the Django cache) and who gets `reactions_updated`.
- Reaction chips under the text, highlighted when they're yours, with a
  tooltip of who reacted on hover and keyboard focus. On touch screens a
  selected row shows the names on a line under the chips.
- **React** in the action bar opens a picker with the six emoji (← and →
  move, Enter picks, Escape closes and returns to React). Picking one you
  already have removes it.
- Screen readers hear your own changes once the server confirms them
  ("Reacted with Thumbs up", "Removed Thumbs up", or "Couldn’t react with
  Thumbs up"); other people's reactions are silent.
- Eleven demo reactions on four messages in Design team, Maya ↔ Arjun and
  Book club (the Book club ones are on the message Priya cleared, so she
  never sees them). `REACTIONS` in `core/demo_data.py`.

### Changed
- The action bar is grouped React · Reply | Edit · Delete, with a separator
  before your own message's Edit and Delete. It wraps on phones.
- History pages take two queries: one for the messages, one for all their
  reactions.
- `message_updated` carries the message's reactions; a deleted message has
  `"reactions": []`.
- Deleting a message removes its reactions in the same transaction.
- On touch screens only the selected row shows its action bar, and hover
  tints no longer stick after a tap.
- Escape closes an open reaction picker or a keyboard-focused chip tooltip
  before the reply and the Details panel; a hover-only tooltip doesn't hold
  Escape back.

### Fixed
- `TestReplyMigration` left the test database at `chat/0005`; it now
  migrates back to the latest schema.

## Phase 10a: replies

Reply to a specific message. The reply shows a live quote of the original,
and clicking the quote jumps to it. This is the first phase whose builders
(`backend-dev`, `frontend-dev`) ran as Claude Code sub sessions, each in its
own container on its own branch.

### Added
- `Message.reply_to`: a nullable foreign key to the message being answered
  (`on_delete=SET_NULL`, `message.replies`), with one check constraint,
  `message_reply_valid` (only text messages reply, never to themselves).
  Migration `chat/0005_message_reply_to`.
- `save_message` takes an optional `reply_to` (the original's id). The
  original must be in the same room, a text message, not deleted and
  visible to the sender; otherwise the server answers with the fixed error
  "You can't reply to that message" and saves nothing.
- Every message object has a `reply_to` key: `null`, `{"id", "available":
  false}` for people who can't see the original, or the original's author
  and an excerpt (up to 200 characters on one line), or `"deleted": true`.
  Quotes are built for each viewer, so the original's author and text never
  reach someone who can't see it. Inbox `room_activity` frames carry
  `"reply_to": null`.
- `error` frames carry `for`, the type of the client frame they answer, when
  there is one.
- Reply in a new action bar on every text message, and a "Replying to"
  bar joined to the composer, with a matching placeholder and hint. Esc or ×
  cancels; Escape closes a dialog or menu first, then the reply, then the
  Details panel.
- Quotes above replies: the original's author and text, "Message deleted",
  or "Original message unavailable". They follow edits and deletes of the
  original live.
- Jump to the original: scroll, focus and a brief accent tint (a still tint
  with reduced motion). Older messages load 100 at a time, up to 10 pages,
  then "That message is too far back."
- Six demo replies (Design team, Ops, Book club and Maya ↔ Arjun), including
  one quoting a deleted message and one Priya sees as unavailable. `SCRIPT`
  lines take an optional fifth item: the text of the line they reply to.

### Changed
- Keyboard: the transcript is one Tab stop (roving tabindex). ↑ and ↓ move
  between messages, Home and End go to the first and last loaded, and Tab
  from a message reaches its quote and actions. The scroll area itself is no
  longer a Tab stop.
- On touch screens, tapping any text message (not only your own) shows its
  actions, on a line below the text.
- Action buttons are named for their message ("Reply to Maya Rao", "Edit
  your message") and described by its time.
- A reply always starts a new group of messages, even from the same sender.
- Loading older history adds the new rows above the old ones instead of
  redrawing the whole transcript, keeping focus and any open edit.
- History pages load only the columns they show (no password hashes) and
  stay at one query per page with replies.
- Builders check their git identity before every commit; a commit under the
  wrong author is re-authored by the orchestrator when merging, never
  force-pushed.

### Fixed
- The message action bar is reachable by keyboard: it was hidden with
  `display: none`, so Tab skipped Edit and Delete.
- `GET /chat/rooms/<uuid>/messages/?before=` refuses a message you can't see
  (400 "Unknown message"), since hidden message ids now reach the page as
  `reply_to.id`.
- Escape in an inline message edit no longer closes the Details panel.
- Clearing your history while older messages are loading no longer brings
  them back.

## Agent sessions

### Changed
- Builders (`backend-dev`, `frontend-dev`, `devops-dev`) run as Claude Code
  sub sessions: own container, `send_message` to the orchestrator and each
  other, and they push their own branch. Reviewers, `idea-planner`,
  `database-designer` and `docs-writer` stay sub agents. See
  docs/agents.md and CLAUDE.md.
- Agents and the orchestrator take the git author from the project's
  existing commits instead of a value written in the files.

## Phase 9c: live-room fixes

Fixes to the live room list from Phase 9b, plus one privacy fix. This is the
first phase built by the agent team: `backend-dev`, `frontend-dev` and
`docs-writer` worked in parallel on their own branches against a shared
contract, and `security-auditor`, `performance-profiler`, `ui-ux-designer`,
`code-reviewer` and `user-tester` reviewed the result.

### Added
- `GET /chat/rooms/summaries/` (`chat:summaries`): every room-list row as
  JSON, most recent first. The list resyncs with it each time the inbox
  socket reconnects, so frames missed while offline are caught up.
- Inbox frame `room_refresh`: after an edit or delete, the room-list rows of
  people who can see the message refetch their preview.
- The gone pane names the chat ("You’re no longer in <name>" / "<name> was
  deleted"), keeps a muted header with "Not a member" or "Deleted", focuses
  the heading and sets the tab title.
- Room-list times update at local midnight and when you return to the tab.
- On phones, notices with no room open show at the top of the room list.

### Changed
- `room_changed` is one partial room object (`id`, `title`, `initials`,
  `member_count`, `member_usernames`) for every member, and is also sent to
  the remaining members when people are added, removed or leave.
- `room_added` summaries are built with a fixed number of queries however
  many people get them (adding 40 people to a 10,000-message room: 4.7 s to
  0.24 s).
- `/chat/?room=<id>` for a room you can't open redirects to `/chat/` with
  "That chat isn’t available. You may have been removed, or it was deleted."
  instead of a 404. Other endpoints keep their 404s.
- Group room events (group events, revokes, `room_updated`, `room.deleted`)
  are sent only after the change commits, in order.
- When the open room disappears from the list, the page reconnects its room
  socket and the close code (`4403` or `4404`) picks the copy; with no answer
  in 3 seconds it shows the "no longer in" copy.
- New room-list rows grow into place and flash the accent colour; with
  reduced motion only a short tint shows.
- Initials use only letters and digits ("@lee" gives "LE", "!!!" gives "?"),
  the same in Python and JavaScript.
- Leaving a group from the Details panel shows "You left <group>.".
- The tablet rail keeps each room's name, preview and unread count, and the
  New chat label, for screen readers.
- SQLite waits up to 20 seconds for a write lock.

### Fixed
- Edits, deletes and group events no longer reach sockets of people who
  can't see the message: people who cleared their history, joined later, or
  were just removed (`visible_to` on room events). `room_updated` goes only to
  current members.
- A room socket joins the room group before checking membership, so a
  removal at connect time can't leave it receiving events. A refused socket
  ignores frames and queued events.
- You can no longer edit or delete your own message after clearing it from
  your history.
- One failed inbox send no longer breaks the request; failures are logged.
- A room deleted while you were offline no longer says you were removed.
- Room rows built live show times and previews exactly like server rows,
  never bring back a room you were removed from, and keep "Find a chat"
  filtering.
- The preview of the open room follows deletes, edits and cleared history.
- A locked SQLite database while marking a room read no longer closes the
  socket.
- Removed between the chat page's two queries no longer raises an error.

## Claude Code agents

### Added
- Reviewer subagents in `.claude/agents/`: `ui-ux-designer`,
  `code-reviewer`, `user-tester` and `idea-planner`. They report and never
  edit project files.
- Three more reviewers: `security-auditor`, `performance-profiler` and
  `database-designer`.
- Four builder subagents: `backend-dev`, `frontend-dev`, `devops-dev` and
  `docs-writer` (Markdown docs only).
  They commit on their own branches and work in parallel on one phase
  through a shared contract; the lead session merges their work into one
  pull request. See docs/agents.md.
- `CLAUDE.md`: the orchestrator playbook for the main session (standing
  rules, git identity, running a phase with the team).

## Phase 9b: live rooms

### Added
- The room list updates live over the inbox socket: new direct chats and
  groups slide in at the top, renamed groups update, and rooms you're removed
  from, leave or that are deleted disappear (inbox frames `room_added`,
  `room_changed`, `room_removed`; see docs/websocket-protocol.md).
- `GET /chat/rooms/<uuid>/summary/`: one room-list row as JSON, used when the
  page sees activity in a room it doesn't list yet.
- A "You're no longer in this chat" / "This chat was deleted" pane replaces an
  open room when you lose access, with a Back to chats button.

### Removed
- The "New conversation · Refresh" prompt; new rooms now appear by themselves.

## Phase 9a: group admins

### Added
- **Details panel** (ⓘ in the room header): group name and creator, members
  with Admin badges and online dots, Add people, per-member menus, Clear
  history, Leave group and Delete group, with confirmations. Third column on
  desktop and tablet, full screen on phones.
- **Admins**: the creator is the first admin; groups can have several. Admins
  rename, remove members, make or remove admins and delete the group; any
  member can add people. The only admin can't step down until someone else is
  admin; when the last admin leaves, the earliest member becomes admin; the
  last member leaving deletes the group.
- **Group events** as one-line system messages on the spine ("Maya added
  Lee"); not unread, not previews, not editable.
- Live updates: `room_updated` frames refresh the header, sidebar and panel;
  removed members and deleted groups close open sockets with a notice.
- `Membership` model (adopting the existing members table), `Room.created_by`,
  `Message.kind`; migration `chat/0004_group_admins` gives existing groups an
  admin (earliest member).
- Demo data: group creators, admins and group events.

### Changed
- Clear history moved from the room header into the Details panel.
- Socket membership is checked on every frame, not only on connect.

### Fixed
- Escape closes the innermost open menu or dialog before the Details panel.
- Group action errors are looked up by code from a fixed message table
  instead of returning exception text (CodeQL: information exposure through
  an exception).

## Account UX and username rules

### Added
- Username rules: 3–30 lowercase letters, numbers and `_`, starting with a
  letter, no `_` at the end or twice in a row. The signup field formats as you
  type (capitals to lowercase, spaces to `_`) and explains any broken rule.
- Migration `account/0002_conform_usernames` renames older accounts to the
  rules and prints every rename.
- Account menu: the whole footer row in the chat sidebar (avatar, name,
  @username and a chevron) opens Settings and Sign out.
- Settings sections with their own URLs: Profile (with read-only @username),
  Appearance and Password.

### Changed
- Sign-in ignores letter case and spaces in the username.
- The Theme button is gone from the chat sidebar; signed-in users change the
  theme in Settings → Appearance. Signed-out pages keep their Theme menu.

## Demo data

### Added
- `manage.py seed_demo`: nine demo users (one inactive, one with no chats),
  three groups and four direct chats with 153 messages over ten days, unread
  messages, an edited and a deleted message, cleared history and varied saved
  themes. Seeds once, `--reset` rebuilds, and it refuses to run when debug is
  off.
- Docker seeds the demo data on start in debug mode (`DJANGO_SEED_DEMO`
  turns it off).
- `docs/demo-data.md`: sign-in details, what each account and room is for,
  and things to try.

## Phase 6: documentation

### Added
- `docs/architecture.md`: components diagram, apps and modules, request and
  message flow, presence, security model, front-end layout, scaling notes.
- `CONTRIBUTING.md`: branches, one PR per change, commit style, checks, and
  which docs to update for each kind of change.
- `docs/README.md`: documentation index.
- Screenshots in `docs/images/` (home, create account, chat in light and
  dark, New chat, settings, phone list and room) and a rewritten README with a
  feature list.
- A test that keeps the chat page's query count flat as rooms grow, backing
  the claim in the architecture guide.

### Fixed
- `readme/config_static_files.md`: broken `settings.py` link, examples now use
  this project's files, and a section on how static files are organised here.

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
