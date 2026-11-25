# Screens and URLs

| URL | Name | Who | Screen |
| --- | --- | --- | --- |
| `/` | `core:home` | Signed out | Home page. Signed-in users are redirected to `/chat/` |
| `/account/login/` | `account:login` | Signed out | Sign in. Accepts a same-site `?next=` |
| `/account/signup/` | `account:signup` | Signed out | Create account; signs the new user in |
| `/account/logout/` | `account:logout` | Signed in | POST only; returns to sign in |
| `/chat/` | `chat:chat` | Signed in | Room list; `?room=<uuid>` opens a room |
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

Unchanged in this phase; it moves to the design system in the chat-screen
phase.
