# Design system: Signal

Relay's UI style is called **Signal**: chrome in a dark (or paper) sidebar, a
light or dark reading pane, and conversations laid out as a transcript, one
line per message on a vertical spine.

The code lives in the `core` app:

| File | Purpose |
| --- | --- |
| `core/theme.py` | Palette, mode and density options and defaults |
| `core/context_processors.py` | Puts the active theme in every template as `ui` |
| `core/static/core/css/tokens.css` | Design tokens for every palette, mode and density |
| `core/static/core/css/relay.css` | Base styles and components |
| `core/static/core/js/theme.js` | Wires theme pickers; saves choices on the device |
| `core/templates/core/base.html` | Base template every page extends |
| `core/templates/core/partials/` | `notices.html`, `theme_picker.html`, `theme_menu.html` |
| `core/templates/{400,403,403_csrf,404,500}.html` | Error pages |

With `DJANGO_DEBUG=true`, every component is shown at
[`/styleguide/`](http://localhost:8000/styleguide/).

## Theme axes

Three independent attributes on `<html>`:

| Attribute | Values | Default | Controls |
| --- | --- | --- | --- |
| `data-palette` | `graphite`, `midnight`, `slate`, `plum`, `moss`, `paper` | `graphite` | Chrome colours, accent, your own messages |
| `data-mode` | `light`, `dark`, `system` | `system` | Reading surface; `system` follows the OS |
| `data-density` | `compact`, `comfortable` | `compact` | Row padding, line height, control height |

| Palette | Chrome | Accent | Your messages |
| --- | --- | --- | --- |
| Graphite + Coral | `#16181d` | `#ff5a36` | `#2ec4a6` |
| Midnight + Saffron | `#121a2b` | `#f5a524` | `#7c9cff` |
| Slate + Electric | `#1c2430` | `#3d7bff` | `#22c3a6` |
| Plum + Rose | `#2a1630` | `#ff4f8b` | `#ffb547` |
| Moss + Tangerine | `#17241e` | `#ff7a2f` | `#7bd88f` |
| Paper + Red | `#eceef2` | `#e5484d` | `#2f6fde` |

Paper switches its chrome to graphite tones in dark mode.

### Where the theme comes from

1. The server renders the defaults from `core/theme.py` on `<html>`.
2. An inline script in `base.html` applies the choice saved on this device
   (`localStorage` keys `relay.palette`, `relay.mode`, `relay.density`) before
   the first paint, so there is no flash.
3. For signed-in users the server renders their saved
   [`Preference`](./data-model.md#accountpreference) with
   `data-theme-source="server"`, so the inline script leaves it alone.
   `theme.js` then also POSTs every change to `data-theme-save-url`
   (`/account/settings/appearance/`) using the CSRF token from
   `<meta name="csrf-token">`, and fires `relay:theme-save-failed` if that
   fails.

Any `<details data-popover>` (the Theme menu, the account menu) closes on Escape or an outside click; `theme.js` handles it.

Any element with `data-theme-control` containing radio inputs named
`palette`, `mode` or `density` (or with `data-axis` set to one of those, so a
picker inside a form can use its own group name) changes the theme instantly; `theme.js` handles
it. Include `core/partials/theme_picker.html` for the full picker or
`core/partials/theme_menu.html` for a compact popover. Signed-out pages use the
menu; signed-in users change the theme in Settings → Appearance.

### Adding a palette

1. Add a `Palette` to `PALETTES` in `core/theme.py`.
2. Add a `:root[data-palette="<key>"]` block to `tokens.css`.
3. Add the key to the `allowed.palette` list in `base.html`.

`core/tests.py` fails if these drift apart.

## Tokens

Use tokens, never literal colours, in components.

| Group | Tokens |
| --- | --- |
| Chrome (palette) | `--chrome`, `--chrome-fg`, `--chrome-strong`, `--chrome-raised`, `--accent`, `--on-accent`, `--mine`, `--on-mine` |
| Surface (mode) | `--bg`, `--surface`, `--fg`, `--muted`, `--line`, `--hover` |
| Semantic | `--danger`, `--success`, `--warning` |
| Type | `--font-display` (Sora), `--font-body` (Manrope), `--font-mono` (JetBrains Mono); `--text-xs` … `--text-2xl` |
| Space and shape | `--space-1` … `--space-7`, `--radius-sm/md/lg`, `--shadow-float`, `--focus-ring` |
| Density | `--row-pad-y`, `--row-line`, `--group-gap`, `--control-h` |

## Components

| Class | Notes |
| --- | --- |
| `.wordmark` | "relay" with an accent dot; `--lg`, `--on-surface` |
| `.btn` | `--primary`, `--ghost`, `--danger`, `--block`, `--icon`, `--sm` |
| `.field`, `.input` | Label, hint, error; set `aria-invalid="true"` on invalid inputs |
| `.notice` | `--error`, `--success`, `--warning`, `--info`; `notices.html` renders Django messages |
| `.card`, `.badge`, `.avatar` | Avatar is an initials square; `--mine`, `--muted`, `--lg` |
| `.segmented`, `.swatch` | Radio-based controls used by the theme picker |
| `.transcript`, `.msg` | Spine layout. See below |
| `.composer` | Floating message bar with an auto-growing textarea |
| `.shell`, `.shell__side`, `.shell__main` | App layout: chrome sidebar plus reading pane |
| `.on-chrome` | Paints an element with chrome colours and adapts buttons and inputs inside |
| `.page-center` | Centred single-column page |
| `.password`, `.password__toggle` | Show/Hide button inside a password input |

Screen-specific components live with their screens:

| Class | File | Notes |
| --- | --- | --- |
| `.auth`, `.auth__aside`, `.auth__panel` | `account/css/auth.css` | Two-column sign-in layout |
| `.form-spine`, `.form-spine__step` | `account/css/auth.css` | Form groups as spine nodes; `is-done`, `has-error` |
| `.palette-chip` | `account/css/auth.css` | Compact palette radio |
| `.home-hero`, `.home-demo`, `.feature-spine` | `core/css/home.css` | Home page |
| `.settings`, `.settings__nav`, `.settings__section`, `.settings__identity` | `account/css/settings.css` | Settings sections; the current section link has `aria-current="page"` |
| `.account-menu`, `.account-menu__panel`, `.account-menu__item` | `chat/css/chat.css` | Account popover above your name in the chat sidebar |
| `.chat`, `.chat-side`, `.room-link`, `.chat-head`, `.status`, `.chat-toast`, `.confirm` | `chat/css/chat.css` | Chat screen; see [screens.md](./screens.md#chat) |
| `.room-list__new` | `chat/css/chat.css` | A room that just arrived: the row grows from zero height (`grid-template-rows` 0fr to 1fr, 200ms, `cubic-bezier(.2, 0, 0, 1)`) so the rows below move down smoothly, its content fades in, then an accent tint (`color-mix(in srgb, var(--accent) 22%, transparent)`) fades out over 1.6s. `inbox.js` removes the class when the tint is done |
| `.chat-head--gone`, `.chat-gone`, `.chat-gone__heading`, `.chat-gone__back` | `chat/css/chat.css` | The open room went away: muted header avatar and title, an icon, the heading (focused, without a focus ring) and Back to chats (44px tall on touch screens and phones) |
| `.chat-notices--side` | `chat/css/chat.css` | Notices in the room list on phones when no room is open; uses the chrome colours (`--chrome-raised`, `--chrome-strong`) |
| `.msg__actions`, `.msg__action`, `.msg__actions-sep` | `chat/css/chat.css` | Action bar at a message's top right, grouped React · Reply \| Edit · Delete: `.msg__actions-sep` is a 1px `--line` rule (`aria-hidden`) before your own message's Edit and Delete; Delete is in `--danger`. Hidden with `opacity: 0` and `pointer-events: none` (not `display: none`) so its buttons stay reachable by keyboard; shown on hover or `:focus-within`, and kept up while its reaction picker is open. Focus on the row itself (`.msg:focus`, from ↑/↓ or a jump) doesn't open it; Tab into its buttons does. On touch screens (`hover: none`) a tapped row gets `.is-selected` and shows the bar on its own line below the text, wrapping when it doesn't fit; rows that aren't selected show no bar unless keyboard focus (`:focus-visible`) is inside it. Hover tints apply only where there is hover. Buttons are 44px tall on coarse pointers |
| `.msg__reactions`, `.msg__chips`, `.reaction` | `chat/css/chat.css` | Reaction chips under a message's text. `.msg__reactions` has `aria-live="off"` (the transcript is a live log) and holds `.msg__chips`, a wrapping row of `button.reaction[data-reaction="<key>"][aria-pressed]` pills: `.reaction__emoji` then `.reaction__count` (tabular numbers), `--surface` fill, a `color-mix(in srgb, var(--muted) 35%, var(--surface))` border, 24px tall (28px in comfortable density). `.reaction--mine` marks yours: border and a 1px inset ring in `--mine-edge` (`color-mix(in srgb, var(--accent) 70%, var(--fg))`, 3:1 against the page in every palette), `--mine-fill` (14% accent) and an 800-weight count; on `:focus-visible` the `--focus-ring` stacks on top, so pressed and focused look different. On coarse pointers chips are 32px tall and at least 44px wide, with a `::before` reaching 6px above and below for a 44px tap area and a 12px gap between wrapped lines |
| `.reaction__tip` | `chat/css/chat.css` | Tooltip inside a chip (`role="tooltip"`, the chip's `aria-describedby`) naming who reacted; shown on mouse hover (`hover: hover`) or keyboard focus, hidden with `[hidden]`. `--surface`, `--line` border, `--radius-sm`, `--shadow-float`, `--text-xs`, up to `min(320px, 70vw)` wide, no pointer events |
| `.msg__reactors` | `chat/css/chat.css` | The names line under the chips ("👍 Lee Chen and you · 🎉 …"), `--muted`, `--text-xs`. Shown only in a selected row on touch screens (`hover: none`) |
| `.reaction-picker`, `.reaction-picker__option` | `chat/css/chat.css` | The React action's popover (`role="toolbar"`, "Pick a reaction"): six 32px emoji buttons (44px on coarse pointers) in a `--surface` box with a `--line` border, `--radius-md` and `--shadow-float`, above the bar or below it with `--below`. The option for a reaction you have has `aria-pressed="true"` and the same `--mine-edge` and `--mine-fill` look as `.reaction--mine`. With hover and no reduced-motion preference, options grow slightly on hover. In a selected row on touch screens it sits on its own line inside the bar, without a shadow |
| `.msg__quote` | `chat/css/chat.css` | A reply's quote above its text: one line, 2px `--accent` left rule, no fill at rest (`--hover` on hover and focus), name (`.msg__quote-name`, bold, `--fg`) then excerpt (`.msg__quote-text`, `color-mix(in srgb, var(--fg) 72%, var(--bg))`, cut with an ellipsis). A `button` that jumps to the original; `--deleted` sets the text in italics; `--unavailable` is a plain `div` with a `--line` rule and italic text. At least 44px tall on coarse pointers |
| `.reply-bar` | `chat/css/chat.css` | "Replying to" bar on top of the composer: `--surface`, `--line` border with no bottom edge, top corners `--radius-lg`; the composer loses its top corners while the bar shows, so the two read as one unit, and the bar's border turns `--accent` while the composer has focus. Parts: `__icon` (accent), `__label`, `__name`, `__excerpt` (one line, ellipsis), `__cancel` (44px on coarse pointers) |
| `.msg--target` | `chat/css/chat.css` | The message you jumped to: an accent tint (`color-mix(in srgb, var(--accent) 22%, transparent)`) that fades out over 1.6s. With reduced motion, a still 16% tint for the same time. `chat.js` removes the class |

### Transcript

```html
<div class="transcript">
  <span class="transcript__day">Today</span>
  <div class="msg">
    <time class="msg__time">09:38</time>
    <span class="msg__node avatar">AK</span>
    <div class="msg__body"><span class="msg__name">Arjun</span><span class="msg__inline-time">09:38</span>Morning</div>
  </div>
  <div class="msg msg--cont">
    <time class="msg__time">09:38</time>
    <span></span>
    <div class="msg__body">Pulled the branch</div>
  </div>
</div>
```

- The time gutter is 52px and never wraps, so 12-hour times fit.
- The first message of a run shows the avatar node and name on the same line as
  the text. Follow-ups (`msg--cont`) show only text; their time appears on
  hover or focus.
- Your own messages use `avatar--mine`.
- A reply puts `.msg__quote` at the top of `.msg__body`, before the text,
  and always starts a new run.
- Reactions put `.msg__reactions` after the text (after an open inline
  edit, if there is one) and before the action bar.
- Rows are focusable (`tabindex="-1"`, one row `0`) and show an inset
  `--focus-ring` on `:focus-visible`.
- `.transcript` is a size container. Below 420px wide the time gutter is hidden
  and `.msg__inline-time` shows next to the name.

## Accessibility

- Every interactive element has a visible focus ring (`--focus-ring`).
- `prefers-reduced-motion` removes movement; short colour fades may stay.
  `relay.css` cuts every transition and animation to almost nothing, and a
  new room-list row skips growing and fading in and only shows the accent
  tint, fading out over 1.2s.
- `base.html` includes a skip link to `#main`; pages put `id="main"` on their
  main landmark.
- Theme controls are real radio inputs inside `fieldset`/`legend`.
- Accent colours carry a matching `--on-accent` text colour chosen for
  contrast in each palette.
