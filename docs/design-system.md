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

Any element with `data-theme-control` containing radio inputs named
`palette`, `mode` or `density` (or with `data-axis` set to one of those, so a
picker inside a form can use its own group name) changes the theme instantly; `theme.js` handles
it. Include `core/partials/theme_picker.html` for the full picker or
`core/partials/theme_menu.html` for a compact popover.

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
| `.settings`, `.settings__nav`, `.settings__section` | `account/css/settings.css` | Settings page |
| `.chat`, `.chat-side`, `.room-link`, `.chat-head`, `.status`, `.chat-toast`, `.confirm` | `chat/css/chat.css` | Chat screen; see [screens.md](./screens.md#chat) |

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
- `.transcript` is a size container. Below 420px wide the time gutter is hidden
  and `.msg__inline-time` shows next to the name.

## Accessibility

- Every interactive element has a visible focus ring (`--focus-ring`).
- `prefers-reduced-motion` disables transitions and animations.
- `base.html` includes a skip link to `#main`; pages put `id="main"` on their
  main landmark.
- Theme controls are real radio inputs inside `fieldset`/`legend`.
- Accent colours carry a matching `--on-accent` text colour chosen for
  contrast in each palette.
