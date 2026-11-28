// Chat screen: renders the transcript, keeps the room socket alive and
// handles the composer. Messages are always inserted as text, never HTML.

(() => {
    "use strict";

    const readJSON = (id) => {
        const element = document.getElementById(id);
        return element ? JSON.parse(element.textContent) : null;
    };

    const me = readJSON("me");
    const GROUP_GAP_MS = 5 * 60 * 1000;

    // The characters Python's str.split() splits on (JavaScript's \s differs).
    const PY_WHITESPACE = /[\t\n\v\f\r\x1c-\x20\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/u;
    // A reply's quote of its original: the same rule as the server (collapse
    // whitespace runs to one space, strip, first 200 characters).
    const EXCERPT_CHARS = 200;
    const excerptOf = (text) =>
        Array.from((text || "").split(PY_WHITESPACE).filter(Boolean).join(" "))
            .slice(0, EXCERPT_CHARS)
            .join("");

    // Dates

    const timeFormat = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });
    const fullFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "full", timeStyle: "short" });
    const dayFormat = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "short", day: "numeric" });

    const dayKey = (date) => `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
    function daysAgo(date) {
        const start = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
        return Math.round((start(new Date()) - start(date)) / 86400000);
    }
    function dayLabel(date) {
        const ago = daysAgo(date);
        if (ago === 0) return "Today";
        if (ago === 1) return "Yesterday";
        return dayFormat.format(date);
    }

    // Room list search. inbox.js owns the rows and fires relay:rooms-changed
    // whenever it adds, removes or changes one, so the filter is re-applied.

    const search = document.getElementById("room-search");
    if (search) {
        const searchBox = search.closest(".chat-side__search");
        const noMatch = document.getElementById("room-nomatch");
        const applyFilter = () => {
            const query = search.value.trim().toLowerCase();
            const links = document.querySelectorAll("#room-list .room-link");
            let shown = 0;
            for (const link of links) {
                const match = (link.dataset.title || "").includes(query);
                link.parentElement.hidden = !match;
                if (match) shown += 1;
            }
            noMatch.hidden = shown > 0 || links.length === 0;
            // No rooms, nothing to search (the list shows its empty note).
            if (searchBox) searchBox.hidden = links.length === 0 && query === "";
        };
        search.addEventListener("input", applyFilter);
        document.addEventListener("relay:rooms-changed", applyFilter);
        applyFilter();
    }

    // The welcome pane (no room open) says "Pick a chat" or "Welcome" to
    // match the list as rooms arrive or go.
    const welcomeParts = document.querySelectorAll("[data-welcome-title], [data-welcome-text]");
    if (welcomeParts.length) {
        document.addEventListener("relay:rooms-changed", () => {
            const any = !!document.querySelector("#room-list .room-link");
            for (const part of welcomeParts) {
                const text = any ? part.dataset.rooms : part.dataset.empty;
                if (part.textContent !== text) part.textContent = text;
            }
        });
    }

    const roomId = readJSON("room-id");
    if (!roomId) return;
    let gone = false; // the room went away while open (see showGone)

    // Transcript
    //
    // `messages` holds every loaded message, oldest first. Appending renders
    // one row; loading older history prepends its rows and rebuilds the row
    // at the old boundary so grouping and day markers stay right.
    //
    // Keyboard: the transcript is one tab stop (roving tabindex). One row,
    // the newest unless you moved, has tabindex 0 and so do its quote and
    // action buttons; every other row and button has -1. Up and Down move
    // between rows, Home and End go to the first and last loaded.

    const transcript = document.getElementById("messages");
    const scroller = document.getElementById("chat-scroll");
    const emptyNote = document.getElementById("chat-empty");
    const historyStatus = document.getElementById("history-status");
    const historyMeta = readJSON("history-meta") || { has_more: false, page_size: 50 };
    const messages = readJSON("initial-messages") || [];
    let hasMore = historyMeta.has_more;
    let loadingOlder = false;

    const nearBottom = () => scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 120;
    const scrollToEnd = () => { scroller.scrollTop = scroller.scrollHeight; };
    const speaker = (data) => (data.user === me ? "You" : data.name || data.user);

    // Mentions: the server lists who a message mentions (`mentions`:
    // [{user, name}], current members only). Only those `@username`s are
    // highlighted, matched like the server: case-insensitive, not right
    // after a letter, digit or underscore, and the whole username.
    const MENTION = /(?<![\p{L}\p{N}_])@([a-z0-9_]+)/giu;
    const mentionsOf = (data) => (Array.isArray(data.mentions) ? data.mentions : []).filter((m) => m && typeof m.user === "string");

    // Text nodes and <span class="mention"> for `text`; never HTML.
    function mentionNodes(text, mentions) {
        const names = new Map(mentions.map((m) => [m.user.toLowerCase(), m]));
        if (!names.size) return [document.createTextNode(text)];
        const nodes = [];
        let at = 0;
        for (const match of text.matchAll(MENTION)) {
            const who = names.get(match[1].toLowerCase());
            if (!who) continue;
            if (match.index > at) nodes.push(document.createTextNode(text.slice(at, match.index)));
            const span = document.createElement("span");
            span.className = "mention" + (who.user === me ? " mention--me" : "");
            span.dataset.user = who.user;
            span.textContent = match[0];
            if (who.name) span.title = who.user === me ? "You" : who.name;
            nodes.push(span);
            at = match.index + match[0].length;
        }
        if (at < text.length) nodes.push(document.createTextNode(text.slice(at)));
        return nodes;
    }

    // In groups, a message that mentions you or replies to yours (not your
    // own) is "for you" and gets a subtle emphasis. Direct chats are all
    // for you, so they don't.
    const isDirect = !!document.querySelector(".chat-head__title[data-private]");
    const forYou = (data) =>
        !isDirect &&
        data.kind !== "system" &&
        !data.deleted &&
        data.user !== me &&
        (mentionsOf(data).some((m) => m.user === me) || (!!data.reply_to && data.reply_to.available && data.reply_to.user === me));

    function fillText(container, data) {
        container.replaceChildren();
        container.closest(".msg")?.classList.toggle("msg--for-you", forYou(data));
        if (data.deleted) {
            container.classList.add("msg__text--deleted");
            container.textContent = "Message deleted";
            return;
        }
        container.classList.remove("msg__text--deleted");
        container.append(...mentionNodes(data.message, mentionsOf(data)));
        if (data.edited) {
            const edited = document.createElement("span");
            edited.className = "msg__edited";
            edited.textContent = " (edited)";
            container.append(edited);
        }
    }

    // Text messages you can act on: not group events, not deleted.
    const actionable = (data) => data.kind !== "system" && !data.deleted;

    // The per-message action bar. Everyone can reply; only the author can
    // edit or delete. Each entry is [data-action, label, accessible name].
    // Buttons are named for the message ("Reply to Anika Shah"), and
    // described by the row's time so each one is distinct.
    // Grouped React · Reply | Edit · Delete, with a separator before your
    // own message's Edit and Delete.
    function actionsFor(data) {
        const who = data.user === me ? "your message" : data.name || data.user;
        const items = [
            ["react", "React", `React to ${who}`],
            ["reply", "Reply", `Reply to ${who}`],
        ];
        if (data.user === me) items.push(null, ["edit", "Edit", "Edit your message"], ["delete", "Delete", "Delete your message"]);
        const bar = document.createElement("span");
        bar.className = "msg__actions";
        for (const item of items) {
            if (!item) {
                const separator = document.createElement("span");
                separator.className = "msg__actions-sep";
                separator.setAttribute("aria-hidden", "true");
                bar.append(separator);
                continue;
            }
            const [action, label, name] = item;
            const button = document.createElement("button");
            button.type = "button";
            button.className = "msg__action";
            button.dataset.action = action;
            button.tabIndex = -1;
            button.textContent = label;
            button.setAttribute("aria-label", name);
            button.setAttribute("aria-describedby", timeId(data.id));
            if (action === "react") button.setAttribute("aria-expanded", "false");
            bar.append(button);
        }
        return bar;
    }
    const timeId = (id) => `msg-time-${id}`;

    // Reactions: the server's fixed set ("reaction-emoji": [{key, char,
    // label}] in display order). Each message's `reactions` is
    // [{emoji, count, users: [{user, name}]}], the server's state; your
    // toggles not yet confirmed (`pendingToggles`) are shown on top of it.
    const REACTIONS = (readJSON("reaction-emoji") || [])
        .filter((r) => r && typeof r.key === "string" && typeof r.char === "string" && typeof r.label === "string")
        .map((r) => [r.key, r.char, r.label]);
    const REACTION = new Map(REACTIONS.map(([key, char, label]) => [key, { char, label }]));
    const REACTION_ORDER = REACTIONS.map(([key]) => key);
    const reactionsOf = (data) => (Array.isArray(data.reactions) ? data.reactions : []).filter((r) => REACTION.has(r.emoji) && r.count > 0);
    const isMine = (reaction) => (reaction.users || []).some((u) => u.user === me);

    // Sent react frames the server hasn't answered yet, oldest first:
    // { id, emoji, on }. The server answers each in order, with a
    // reactions_updated for that message or an error.
    let pendingToggles = [];

    // What a message's chips show: the server's reactions with your
    // unconfirmed toggles applied, in order.
    function shownReactions(data) {
        let list = reactionsOf(data);
        for (const toggle of pendingToggles) {
            if (toggle.id === data.id) list = withMine(list, toggle.emoji, toggle.on);
        }
        return list;
    }

    // `list` with your reaction `emoji` added or removed, in the fixed order.
    function withMine(list, emoji, on) {
        const next = [];
        let found = false;
        for (const reaction of list) {
            if (reaction.emoji !== emoji) {
                next.push(reaction);
                continue;
            }
            found = true;
            const others = (reaction.users || []).filter((u) => u.user !== me);
            const had = isMine(reaction);
            if (on) {
                next.push({ ...reaction, count: reaction.count + (had ? 0 : 1), users: [...others, { user: me, name: "" }] });
            } else if (reaction.count - (had ? 1 : 0) > 0) {
                next.push({ ...reaction, count: reaction.count - (had ? 1 : 0), users: others });
            }
        }
        if (on && !found) next.push({ emoji, count: 1, users: [{ user: me, name: "" }] });
        return next.sort((a, b) => REACTION_ORDER.indexOf(a.emoji) - REACTION_ORDER.indexOf(b.emoji));
    }

    // "Maya Rao", "Maya Rao and you", "Maya Rao, Lee Chen and you", and
    // "… and 4 others" past ten names.
    const NAMES_SHOWN = 10;
    function reactorNames(reaction) {
        const mine = isMine(reaction);
        const others = (reaction.users || []).filter((u) => u.user !== me).map((u) => u.name || u.user);
        const listed = (reaction.count || 0) - (mine ? 1 : 0);
        const shown = others.slice(0, NAMES_SHOWN);
        const rest = Math.max(0, listed - shown.length);
        const parts = [...shown];
        if (rest) parts.push(`${rest} other${rest === 1 ? "" : "s"}`);
        if (mine) parts.push(parts.length ? "you" : "You");
        if (parts.length <= 1) return parts.join("");
        return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
    }

    // Each chip carries a tooltip naming who reacted (shown on hover and
    // keyboard focus, see the tooltip handlers below) and describes itself
    // with it.
    let tipCount = 0;
    function fillChip(chip, reaction) {
        const { char, label } = REACTION.get(reaction.emoji);
        const mine = isMine(reaction);
        chip.classList.toggle("reaction--mine", mine);
        chip.setAttribute("aria-pressed", String(mine));
        chip.setAttribute(
            "aria-label",
            `${label}, ${reaction.count} reaction${reaction.count === 1 ? "" : "s"}${mine ? ", including you" : ""}`
        );
        const emoji = chip.querySelector(".reaction__emoji");
        if (emoji.textContent !== char) emoji.textContent = char;
        chip.querySelector(".reaction__count").textContent = String(reaction.count);
        chip.querySelector(".reaction__tip").textContent = reactorNames(reaction);
    }

    function buildChip(reaction, tabIndex) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "reaction";
        chip.dataset.reaction = reaction.emoji;
        chip.tabIndex = tabIndex;
        const emoji = document.createElement("span");
        emoji.className = "reaction__emoji";
        emoji.setAttribute("aria-hidden", "true");
        const count = document.createElement("span");
        count.className = "reaction__count";
        count.setAttribute("aria-hidden", "true");
        const tip = document.createElement("span");
        tip.className = "reaction__tip";
        tip.id = `reaction-tip-${++tipCount}`;
        tip.setAttribute("role", "tooltip");
        tip.hidden = true;
        chip.setAttribute("aria-describedby", tip.id);
        chip.append(emoji, count, tip);
        fillChip(chip, reaction);
        return chip;
    }

    // The names line a selected row shows on touch screens (where there is
    // no hover): "👍 Lee Chen and you · 🎉 Arjun Kumar, Lee Chen and you".
    function fillReactors(line, list) {
        line.textContent = list.map((r) => `${REACTION.get(r.emoji).char} ${reactorNames(r)}`).join(" · ");
    }

    function buildReactions(list) {
        const box = document.createElement("div");
        box.className = "msg__reactions";
        // The transcript is a live log; chip changes aren't news.
        box.setAttribute("aria-live", "off");
        const chips = document.createElement("div");
        chips.className = "msg__chips";
        for (const reaction of list) chips.append(buildChip(reaction, -1));
        const line = document.createElement("p");
        line.className = "msg__reactors";
        fillReactors(line, list);
        box.append(chips, line);
        return box;
    }

    // Bring a row's chips in line with what its message shows. Chips are
    // updated in place (never the row), so an inline edit stays open and a
    // focused chip keeps focus; if the focused chip goes, focus moves to its
    // neighbour, else the React button, else the row.
    function updateReactions(row) {
        if (!row) return;
        const data = messages.find((m) => m.id === row.dataset.id);
        const list = data && actionable(data) ? shownReactions(data) : [];
        if (picker && picker.row === row) {
            const mine = new Set(list.filter(isMine).map((r) => r.emoji));
            for (const option of picker.el.children) option.setAttribute("aria-pressed", String(mine.has(option.dataset.pick)));
        }
        let box = row.querySelector(".msg__reactions");
        if (!list.length) {
            if (!box) return;
            const lost = box.contains(document.activeElement);
            box.remove();
            if (lost) (row.querySelector('[data-action="react"]') || row).focus({ preventScroll: true });
            return;
        }
        if (!box) {
            box = buildReactions([]);
            // Below the text, or below an open inline edit.
            (row.querySelector(".msg__edit") || row.querySelector(".msg__text")).after(box);
        }
        const chips = box.querySelector(".msg__chips");
        const tabIndex = row === stopRow ? 0 : -1;
        const keep = new Set(list.map((r) => r.emoji));
        let lostAt = -1;
        [...chips.children].forEach((chip, i) => {
            if (keep.has(chip.dataset.reaction)) return;
            if (chip === document.activeElement) lostAt = i;
            chip.remove();
        });
        let before = chips.firstElementChild;
        for (const reaction of list) {
            let chip = chips.querySelector(`.reaction[data-reaction="${CSS.escape(reaction.emoji)}"]`);
            if (chip) fillChip(chip, reaction);
            else chip = buildChip(reaction, tabIndex);
            if (chip !== before) chips.insertBefore(chip, before);
            before = chip.nextElementSibling;
        }
        fillReactors(box.querySelector(".msg__reactors"), list);
        if (lostAt !== -1) {
            (chips.children[Math.min(lostAt, chips.children.length - 1)] || row).focus({ preventScroll: true });
        }
    }

    // The quote above a reply: a button that jumps to the original, or a
    // plain note when you can't see the original.
    function buildQuote(reply) {
        if (!reply.available) {
            const note = document.createElement("div");
            note.className = "msg__quote msg__quote--unavailable";
            note.textContent = "Original message unavailable";
            note.title = "Sent before you joined, or not visible to you";
            return note;
        }
        const quote = document.createElement("button");
        quote.type = "button";
        quote.className = "msg__quote";
        quote.tabIndex = -1;
        quote.dataset.replyTo = reply.id;
        fillQuote(quote, reply);
        return quote;
    }

    function fillQuote(quote, reply) {
        const hidden = document.createElement("span");
        hidden.className = "visually-hidden";
        hidden.textContent = "In reply to ";
        const name = document.createElement("span");
        name.className = "msg__quote-name";
        name.textContent = reply.user === me ? "You" : reply.name || reply.user;
        const separator = document.createElement("span");
        separator.className = "visually-hidden";
        separator.textContent = ": ";
        const text = document.createElement("span");
        text.className = "msg__quote-text";
        quote.classList.toggle("msg__quote--deleted", !!reply.deleted);
        text.textContent = reply.deleted ? "Message deleted" : reply.excerpt;
        quote.replaceChildren(hidden, name, separator, text);
        quote.title = reply.deleted ? "Message deleted. Jump to it" : "Jump to the original message";
    }

    // Build the nodes for `data`, given the message before it (or null).
    function buildRow(data, prev) {
        const nodes = [];
        const date = new Date(data.created_at);
        const prevDate = prev ? new Date(prev.created_at) : null;
        const mine = data.user === me;

        if (!prev || dayKey(prevDate) !== dayKey(date)) {
            const day = document.createElement("span");
            day.className = "transcript__day";
            day.textContent = dayLabel(date);
            nodes.push(day);
            prev = null;
        }
        if (data.kind === "system") {
            // Group events: a muted line with a diamond node, no avatar.
            const row = document.createElement("div");
            row.className = "msg msg--system";
            row.dataset.id = data.id;
            row.tabIndex = -1;
            const time = document.createElement("time");
            time.className = "msg__time";
            time.dateTime = data.created_at;
            time.title = fullFormat.format(date);
            time.textContent = timeFormat.format(date);
            const node = document.createElement("span");
            node.className = "msg__sysnode";
            node.setAttribute("aria-hidden", "true");
            const body = document.createElement("div");
            body.className = "msg__body";
            const text = document.createElement("span");
            text.className = "msg__text";
            text.textContent = data.message;
            body.append(text);
            row.append(time, node, body);
            nodes.push(row);
            return nodes;
        }

        const continues =
            prev &&
            prev.kind !== "system" &&
            prev.user === data.user &&
            date - prevDate < GROUP_GAP_MS &&
            !data.reply_to; // a reply always starts a new group

        const row = document.createElement("div");
        row.className = "msg" + (continues ? " msg--cont" : "") + (mine ? " msg--mine" : "") + (forYou(data) ? " msg--for-you" : "");
        row.dataset.id = data.id;
        row.tabIndex = -1;

        const time = document.createElement("time");
        time.id = timeId(data.id);
        time.className = "msg__time";
        time.dateTime = data.created_at;
        time.title = fullFormat.format(date);
        time.textContent = timeFormat.format(date);

        const node = document.createElement("span");
        if (!continues) {
            node.className = "msg__node avatar" + (mine ? " avatar--mine" : "");
            node.textContent = data.initials || "?";
            node.setAttribute("aria-hidden", "true");
        }

        const body = document.createElement("div");
        body.className = "msg__body";
        if (!continues) {
            const name = document.createElement("span");
            name.className = "msg__name";
            name.textContent = speaker(data);
            const inlineTime = document.createElement("span");
            inlineTime.className = "msg__inline-time";
            inlineTime.textContent = timeFormat.format(date);
            body.append(name, inlineTime);
        } else {
            const who = document.createElement("span");
            who.className = "visually-hidden";
            who.textContent = speaker(data) + ": ";
            body.append(who);
        }
        if (data.reply_to && !data.deleted) body.append(buildQuote(data.reply_to));
        const text = document.createElement("span");
        text.className = "msg__text";
        fillText(text, data);
        body.append(text);
        if (actionable(data)) {
            const list = shownReactions(data);
            if (list.length) body.append(buildReactions(list));
            body.append(actionsFor(data));
        }

        row.append(time, node, body);
        nodes.push(row);
        return nodes;
    }

    const rowFor = (id) => transcript.querySelector(`.msg[data-id="${CSS.escape(id)}"]`);

    // Roving tabindex. `currentId` is the row you moved to; null means the
    // newest row, so the tab stop follows new messages.
    let currentId = null;
    let stopRow = null;

    // The reaction picker keeps its own roving tab stop.
    function setStop(row, on) {
        row.tabIndex = on ? 0 : -1;
        for (const button of row.querySelectorAll("button")) {
            if (!button.closest(".reaction-picker")) button.tabIndex = on ? 0 : -1;
        }
    }

    function updateStop() {
        const last = transcript.lastElementChild;
        const row = (currentId && rowFor(currentId)) || (last && last.matches(".msg") ? last : null);
        if (stopRow && stopRow !== row && stopRow.isConnected) setStop(stopRow, false);
        if (row) setStop(row, true);
        stopRow = row;
    }

    // Where focus is inside the transcript, so it can come back after a
    // row is rebuilt: the row itself, its quote or one of its actions.
    function focusKey() {
        const el = document.activeElement;
        if (!el || !transcript.contains(el)) return null;
        const row = el.closest(".msg[data-id]");
        if (!row) return null;
        if (el === row) return { id: row.dataset.id, part: "row" };
        if (el.matches(".msg__quote")) return { id: row.dataset.id, part: "quote" };
        if (el.matches(".reaction")) return { id: row.dataset.id, part: `reaction:${el.dataset.reaction}` };
        // In the picker: it closes when the row is rebuilt, so back to React.
        if (el.closest(".reaction-picker")) return { id: row.dataset.id, part: "react" };
        if (el.dataset.action) return { id: row.dataset.id, part: el.dataset.action };
        return null;
    }

    function restoreFocus(key) {
        if (!key) return;
        const active = document.activeElement;
        if (active && active !== document.body && active.isConnected) return; // focus didn't get lost
        const row = rowFor(key.id);
        if (!row) return;
        let el = row;
        if (key.part === "quote") el = row.querySelector("button.msg__quote") || row;
        else if (key.part.startsWith("reaction:")) {
            const emoji = key.part.slice("reaction:".length);
            el = row.querySelector(`.reaction[data-reaction="${CSS.escape(emoji)}"]`) || row.querySelector(".reaction") || row;
        } else if (key.part !== "row") el = row.querySelector(`[data-action="${CSS.escape(key.part)}"]`) || row;
        el.focus({ preventScroll: true });
    }

    function renderAll() {
        const key = focusKey();
        const targetId = transcript.querySelector(".msg--target")?.dataset.id;
        const nodes = [];
        messages.forEach((data, i) => nodes.push(...buildRow(data, messages[i - 1] || null)));
        transcript.replaceChildren(...nodes);
        stopRow = null;
        if (currentId && !rowFor(currentId)) currentId = null;
        updateStop();
        restoreFocus(key);
        if (targetId) rowFor(targetId)?.classList.add("msg--target");
        emptyNote.hidden = messages.length > 0;
        updateHistoryStatus();
    }

    function appendMessage(data) {
        if (messages.some((m) => m.id === data.id)) return;
        transcript.append(...buildRow(data, messages[messages.length - 1] || null));
        messages.push(data);
        emptyNote.hidden = true;
        updateStop();
    }

    // Older messages go above the loaded ones. Only the old first row is
    // rebuilt (its day marker and grouping depend on the row before it),
    // unless you're editing it, when it is left as it is.
    function prependOlder(older) {
        if (!older.length) return;
        const boundary = messages[0] || null;
        const nodes = [];
        older.forEach((data, i) => nodes.push(...buildRow(data, older[i - 1] || null)));
        const oldFirst = boundary ? rowFor(boundary.id) : null;
        if (oldFirst) {
            // Drop the old first row's day marker; the rebuilt row adds one
            // back if the day changes there.
            let marker = oldFirst.previousElementSibling;
            while (marker && marker.classList.contains("transcript__day")) {
                const before = marker.previousElementSibling;
                marker.remove();
                marker = before;
            }
            const last = older[older.length - 1];
            if (oldFirst.querySelector(".msg__edit")) {
                if (dayKey(new Date(last.created_at)) !== dayKey(new Date(boundary.created_at))) {
                    oldFirst.before(buildRow(boundary, null)[0]);
                }
            } else {
                const key = focusKey();
                const tinted = oldFirst.classList.contains("msg--target");
                const selected = oldFirst.classList.contains("is-selected");
                const fresh = buildRow(boundary, last);
                oldFirst.replaceWith(...fresh);
                const row = fresh[fresh.length - 1];
                row.classList.toggle("msg--target", tinted);
                row.classList.toggle("is-selected", selected);
                if (stopRow === oldFirst) stopRow = null;
                restoreFocus(key);
            }
        }
        transcript.prepend(...nodes);
        messages.unshift(...older);
        emptyNote.hidden = messages.length > 0;
        updateStop();
    }

    // message_updated is the authority on text and deletion; reactions_updated
    // on reactions, so the reactions already held are kept unless the
    // message was deleted (a deleted message has none).
    function updateMessage(data) {
        const index = messages.findIndex((m) => m.id === data.id);
        if (index === -1) return;
        if (data.deleted) dropToggles(data.id);
        else data = { ...data, reactions: messages[index].reactions };
        messages[index] = data;
        const row = rowFor(data.id);
        if (!row) return;
        const key = focusKey();
        if (picker && picker.row === row) closePicker({ focus: false });
        const body = row.querySelector(".msg__body");
        const text = row.querySelector(".msg__text");
        fillText(text, data);
        text.hidden = false;
        // The quote follows reply_to, as in buildRow: none on a deleted
        // message or when the original is gone (reply_to null).
        row.querySelector(".msg__quote")?.remove();
        if (data.reply_to && !data.deleted) text.before(buildQuote(data.reply_to));
        if (data.deleted) row.classList.remove("is-selected");
        row.querySelector(".msg__actions")?.remove();
        row.querySelector(".msg__edit")?.remove();
        if (actionable(data)) body.append(actionsFor(data));
        redrawReactions(data.id);
        setStop(row, row === stopRow);
        restoreFocus(key);
    }

    // Reacting. A click shows the change at once and sends the frame; it
    // stays in `pendingToggles` until the server's answer. A refusal (or a
    // lost socket) takes it back off.
    function toggleReaction(id, emoji) {
        const data = messages.find((m) => m.id === id);
        if (!data || !REACTION.has(emoji) || !actionable(data)) return;
        if (!socket || socket.readyState !== WebSocket.OPEN) {
            showToast("Not connected yet. Try again in a moment.");
            return;
        }
        // From what you see, including toggles still on their way.
        const current = shownReactions(data).find((r) => r.emoji === emoji);
        const on = !(current && isMine(current));
        socket.send(JSON.stringify({ type: "react", id, emoji, on }));
        pendingToggles.push({ id, emoji, on });
        redrawReactions(id);
    }

    // The server's state for a message. The oldest unconfirmed toggle of
    // each emoji that this state matches is confirmed (and announced);
    // later ones stay shown on top.
    function applyReactions(id, reactions) {
        const data = messages.find((m) => m.id === id);
        if (!data || !actionable(data)) return;
        data.reactions = Array.isArray(reactions) ? reactions : [];
        const mine = new Set(reactionsOf(data).filter(isMine).map((r) => r.emoji));
        const seen = new Set();
        pendingToggles = pendingToggles.filter((toggle) => {
            if (toggle.id !== id || seen.has(toggle.emoji)) return true;
            seen.add(toggle.emoji);
            if (mine.has(toggle.emoji) !== toggle.on) return true;
            const { label } = REACTION.get(toggle.emoji);
            announce(toggle.on ? `Reacted with ${label}` : `Removed ${label}`);
            return false;
        });
        redrawReactions(id);
    }

    // The server refused the oldest toggle it hadn't answered: take it back.
    function refuseOldestToggle() {
        const toggle = pendingToggles.shift();
        if (!toggle) return;
        const { label } = REACTION.get(toggle.emoji);
        announce(toggle.on ? `Couldn’t react with ${label}` : `Couldn’t remove ${label}`);
        redrawReactions(toggle.id);
    }

    function dropToggles(id = null) {
        const ids = new Set(pendingToggles.filter((t) => id === null || t.id === id).map((t) => t.id));
        pendingToggles = id === null ? [] : pendingToggles.filter((t) => t.id !== id);
        return ids;
    }

    // Chips can add or remove a line. Keep what you're reading where it is:
    // the newest message if you were at the bottom, else the first row in
    // view (browsers without scroll anchoring would let it jump).
    function redrawReactions(id) {
        const row = rowFor(id);
        if (!row) return;
        if (nearBottom()) {
            updateReactions(row);
            scrollToEnd();
            return;
        }
        const top = scroller.getBoundingClientRect().top;
        let anchor = null;
        for (const candidate of transcript.querySelectorAll(".msg[data-id]")) {
            if (candidate.getBoundingClientRect().bottom > top) {
                anchor = candidate;
                break;
            }
        }
        const before = anchor ? anchor.getBoundingClientRect().top : 0;
        updateReactions(row);
        if (anchor && anchor !== row && anchor.isConnected) {
            const shift = anchor.getBoundingClientRect().top - before;
            if (shift) scroller.scrollTop += shift;
        }
    }

    // The reaction picker: a small popover under (or above) the action bar
    // with the six reactions as buttons. Left and Right move, Enter picks,
    // Escape (in it or on React) closes; focus goes back to React. One is
    // open at a time, and it closes when focus leaves it and React.
    let picker = null; // { el, row, opener }
    const PICKER_ID = "reaction-picker";

    function openPicker(opener) {
        const row = opener.closest(".msg[data-id]");
        const data = row && messages.find((m) => m.id === row.dataset.id);
        if (!data || !actionable(data)) return;
        if (picker) {
            const same = picker.opener === opener;
            closePicker({ focus: false });
            if (same) return;
        }
        const mineSet = new Set(shownReactions(data).filter(isMine).map((r) => r.emoji));
        const el = document.createElement("div");
        el.className = "reaction-picker";
        el.id = PICKER_ID;
        el.setAttribute("role", "toolbar");
        el.setAttribute("aria-label", "Pick a reaction");
        REACTIONS.forEach(([key, char, label], i) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "reaction-picker__option";
            button.dataset.pick = key;
            button.tabIndex = i === 0 ? 0 : -1;
            button.textContent = char;
            button.title = label;
            button.setAttribute("aria-label", label);
            button.setAttribute("aria-pressed", String(mineSet.has(key)));
            el.append(button);
        });
        // Open upward unless the bar is near the top of the view.
        const room = opener.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
        if (room < 64) el.classList.add("reaction-picker--below");
        // Right after React in the tab order; Tab moves on to Reply.
        opener.after(el);
        opener.setAttribute("aria-expanded", "true");
        opener.setAttribute("aria-controls", PICKER_ID);
        picker = { el, row, opener };
        el.firstElementChild.focus({ preventScroll: true });
        // On touch the bar is sticky inside a selected row: bring the whole
        // row (text, chips, bar and picker) into view when it fits.
        const selected = row.classList.contains("is-selected") && row.offsetHeight < scroller.clientHeight;
        (selected ? row : el).scrollIntoView({ block: "nearest" });
    }

    function closePicker({ focus = true } = {}) {
        // Also clears a picker whose row was rebuilt or removed meanwhile.
        for (const stray of document.querySelectorAll(".reaction-picker")) {
            if (!picker || stray !== picker.el) stray.remove();
        }
        if (!picker) return;
        const { el, opener } = picker;
        picker = null;
        const hadFocus = el.contains(document.activeElement);
        el.remove();
        opener.setAttribute("aria-expanded", "false");
        opener.removeAttribute("aria-controls");
        if ((focus || hadFocus) && opener.isConnected) opener.focus({ preventScroll: true });
    }

    transcript.addEventListener("keydown", (event) => {
        if (!picker) return;
        if (event.key === "Escape" && event.target === picker.opener) {
            event.preventDefault();
            closePicker();
            return;
        }
        if (!picker.el.contains(event.target)) return;
        const options = [...picker.el.children];
        const at = options.indexOf(event.target);
        let next = -1;
        if (event.key === "ArrowRight") next = (at + 1) % options.length;
        else if (event.key === "ArrowLeft") next = (at - 1 + options.length) % options.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = options.length - 1;
        else if (event.key === "Escape") {
            event.preventDefault();
            closePicker();
            return;
        } else if (event.key === "ArrowUp" || event.key === "ArrowDown") {
            event.preventDefault(); // don't move between rows from here
            return;
        }
        if (next === -1) return;
        event.preventDefault();
        options.forEach((option, i) => { option.tabIndex = i === next ? 0 : -1; });
        options[next].focus();
    });
    // Focus leaving the picker and React (Tab, Shift+Tab, a click, arrows
    // to another row) closes the picker.
    transcript.addEventListener("focusout", (event) => {
        if (!picker) return;
        const inside = (node) => !!node && (picker.el.contains(node) || node === picker.opener);
        if (!inside(event.target) || inside(event.relatedTarget)) return;
        closePicker({ focus: false });
    });
    document.addEventListener("click", (event) => {
        if (!picker) return;
        if (picker.el.contains(event.target) || picker.opener.contains(event.target)) return;
        closePicker({ focus: false });
    });

    // Chip tooltips: who reacted, on mouse hover or keyboard focus. Escape
    // hides one (before anything else closes); it comes back on the next
    // hover or focus.
    const canHover = window.matchMedia("(hover: hover)");
    const showTip = (chip) => {
        for (const open of transcript.querySelectorAll(".reaction__tip:not([hidden])")) {
            if (open.parentElement !== chip) open.hidden = true;
        }
        const tip = chip.querySelector(".reaction__tip");
        if (tip) tip.hidden = false;
    };
    const hideTip = (chip) => {
        const tip = chip.querySelector(".reaction__tip");
        if (tip && !(chip.matches(":hover") && canHover.matches) && document.activeElement !== chip) tip.hidden = true;
    };
    transcript.addEventListener("focusin", (event) => {
        const chip = event.target.closest?.("button.reaction");
        if (chip && chip.matches(":focus-visible")) showTip(chip);
    });
    transcript.addEventListener("focusout", (event) => {
        const chip = event.target.closest?.("button.reaction");
        if (chip) setTimeout(() => hideTip(chip), 0);
    });
    transcript.addEventListener("mouseover", (event) => {
        const chip = event.target.closest("button.reaction");
        if (chip && canHover.matches && !chip.contains(event.relatedTarget)) showTip(chip);
    });
    transcript.addEventListener("mouseout", (event) => {
        const chip = event.target.closest("button.reaction");
        if (chip && !chip.contains(event.relatedTarget)) setTimeout(() => hideTip(chip), 0);
    });
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        for (const tip of transcript.querySelectorAll(".reaction__tip:not([hidden])")) tip.hidden = true;
    });

    // An original was edited or deleted: refresh every loaded quote of it
    // (quotes you can't see stay unavailable) and the reply bar.
    function updateQuotesOf(data) {
        const reply = {
            id: data.id,
            available: true,
            deleted: !!data.deleted,
            user: data.user,
            name: data.name,
        };
        if (!data.deleted) reply.excerpt = excerptOf(data.message);
        for (const m of messages) {
            if (m.reply_to && m.reply_to.id === data.id && m.reply_to.available) m.reply_to = reply;
        }
        for (const quote of transcript.querySelectorAll(`button.msg__quote[data-reply-to="${CSS.escape(data.id)}"]`)) {
            fillQuote(quote, reply);
        }
        if (replyTarget && replyTarget.id === data.id) {
            if (data.deleted) {
                cancelReply({ announce: false, focus: false });
                showToast("The message you were replying to was deleted.");
            } else {
                setReply(data, { announce: false, focus: false });
            }
        }
    }

    function updateHistoryStatus() {
        if (loadingOlder) {
            historyStatus.textContent = "Loading earlier messages…";
            historyStatus.hidden = false;
        } else if (!hasMore && messages.length > 0) {
            historyStatus.textContent = "Start of the conversation";
            historyStatus.hidden = false;
        } else {
            historyStatus.hidden = true;
        }
    }

    // Load the page before the oldest loaded message. Resolves true when a
    // page was added; a call while one is loading shares that request.
    let olderRequest = null;
    // `quiet`: the caller (a jump) says what went wrong itself.
    function loadOlder(limit = historyMeta.page_size, { quiet = false } = {}) {
        if (olderRequest) return olderRequest;
        if (!hasMore || !messages.length) return Promise.resolve(false);
        olderRequest = fetchOlder(limit, quiet).finally(() => { olderRequest = null; });
        return olderRequest;
    }

    // Bumped when history is cleared, so a page that was loading then is dropped.
    let clearGen = 0;

    async function fetchOlder(limit, quiet) {
        loadingOlder = true;
        updateHistoryStatus();
        const before = messages[0].id;
        const gen = clearGen;
        try {
            const url = `/chat/rooms/${encodeURIComponent(roomId)}/messages/?before=${encodeURIComponent(before)}&limit=${encodeURIComponent(limit)}`;
            const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
            if (!response.ok) throw new Error(String(response.status));
            const page = await response.json();
            loadingOlder = false;
            if (gen !== clearGen) {
                updateHistoryStatus();
                return false;
            }
            const known = new Set(messages.map((m) => m.id));
            const older = page.messages.filter((m) => !known.has(m.id));
            const fromBottom = scroller.scrollHeight - scroller.scrollTop;
            hasMore = page.has_more;
            prependOlder(older);
            updateHistoryStatus();
            scroller.scrollTop = scroller.scrollHeight - fromBottom;
            return true;
        } catch (error) {
            console.warn("Relay: couldn't load earlier messages: %s", String(error));
            loadingOlder = false;
            updateHistoryStatus();
            if (!quiet) showToast("Couldn't load earlier messages. Scroll up to try again.");
            return false;
        }
    }

    // Jump to a reply's original: scroll it into view, tint it briefly and
    // focus it. If it isn't loaded, load older pages (100 at a time, up to
    // 10 pages) until it is.
    const JUMP_PAGE_SIZE = 100;
    const JUMP_MAX_PAGES = 10;
    const TARGET_MS = 1600;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let jumping = false;
    let targetTimer = null;
    // True while a jump's smooth scroll runs, so it doesn't load older pages.
    let scrollHold = false;
    let holdTimer = null;

    function showTarget(row) {
        for (const old of transcript.querySelectorAll(".msg--target")) old.classList.remove("msg--target");
        clearTimeout(targetTimer);
        const smooth = !reducedMotion.matches;
        if (smooth) {
            scrollHold = true;
            clearTimeout(holdTimer);
            const release = () => {
                scrollHold = false;
                clearTimeout(holdTimer);
            };
            scroller.addEventListener("scrollend", release, { once: true });
            holdTimer = setTimeout(release, 800);
        }
        row.scrollIntoView({ block: "center", behavior: smooth ? "smooth" : "auto" });
        // Focusing it makes it the transcript's tab stop (see focusin below).
        row.focus({ preventScroll: true });
        // Restart the tint if the same message is the target again.
        void row.offsetWidth;
        row.classList.add("msg--target");
        // Query again: loading older history may have rebuilt the row.
        targetTimer = setTimeout(() => {
            for (const tinted of transcript.querySelectorAll(".msg--target")) tinted.classList.remove("msg--target");
        }, TARGET_MS);
    }

    const FINDING = "Finding message\u2026";
    async function jumpTo(id, quote = null) {
        if (jumping) return;
        let row = rowFor(id);
        if (row) return showTarget(row);
        jumping = true;
        // Paging can take a while and the loading note is at the top, out
        // of view: mark the quote busy and say so near the composer.
        quote?.setAttribute("aria-busy", "true");
        showToast(FINDING, { persist: true });
        let note = "";
        try {
            for (let pages = 0; !row && hasMore && pages < JUMP_MAX_PAGES; pages += 1) {
                if (!(await loadOlder(JUMP_PAGE_SIZE, { quiet: true }))) {
                    if (hasMore) note = "Couldn't find that message. Try again.";
                    break;
                }
                row = rowFor(id);
            }
            if (!row && !note) note = hasMore ? "That message is too far back." : "Couldn't find that message.";
        } catch (error) {
            console.warn("Relay: couldn't jump to message %s: %s", id, String(error));
            note = "Couldn't find that message. Try again.";
        } finally {
            jumping = false;
            // The quote may have been rebuilt meanwhile; clear any busy one.
            for (const busy of transcript.querySelectorAll('.msg__quote[aria-busy="true"]')) busy.removeAttribute("aria-busy");
            quote?.removeAttribute("aria-busy");
        }
        if (note) showToast(note);
        else {
            if (toast.textContent === FINDING) hideToast();
            showTarget(row);
        }
    }

    scroller.addEventListener("scroll", () => {
        if (scroller.scrollTop < 80 && !jumping && !scrollHold) loadOlder();
    });

    // Roving tabindex: whatever row gets focus (Up/Down, a click on its
    // quote, a jump) becomes the tab stop.
    transcript.addEventListener("focusin", (event) => {
        const row = event.target.closest(".msg[data-id]");
        if (!row) return;
        currentId = row === transcript.lastElementChild ? null : row.dataset.id;
        updateStop();
    });

    const isRow = (node) => node && node.matches(".msg[data-id]");
    function siblingRow(row, step) {
        let node = step < 0 ? row.previousElementSibling : row.nextElementSibling;
        while (node && !isRow(node)) node = step < 0 ? node.previousElementSibling : node.nextElementSibling;
        return node;
    }
    function moveTo(row) {
        row.focus({ preventScroll: true });
        row.scrollIntoView({ block: "nearest" });
    }

    transcript.addEventListener("keydown", (event) => {
        if (!["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
        if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
        if (event.target.closest(".msg__edit, .reaction-picker")) return;
        const row = event.target.closest(".msg[data-id]");
        if (!row) return;
        event.preventDefault();
        let next = null;
        if (event.key === "ArrowUp") next = siblingRow(row, -1);
        else if (event.key === "ArrowDown") next = siblingRow(row, 1);
        else if (event.key === "Home") next = transcript.querySelector(".msg[data-id]");
        else next = transcript.lastElementChild;
        if (next && next !== row) return moveTo(next);
        // Up from the oldest loaded row loads the page before it.
        if (event.key === "ArrowUp" && hasMore) {
            const id = row.dataset.id;
            loadOlder().then((added) => {
                const fresh = rowFor(id);
                const above = added && fresh ? siblingRow(fresh, -1) : null;
                if (above) moveTo(above);
            });
        }
    });

    renderAll();
    scrollToEnd();
    // If the first page doesn't fill the pane there is nothing to scroll; load more.
    (async () => {
        while (hasMore && scroller.scrollHeight <= scroller.clientHeight) {
            if (!(await loadOlder())) break;
        }
        scrollToEnd();
    })();

    // The room list row for this room (inbox.js owns the list).
    function refreshRow() {
        document.dispatchEvent(new CustomEvent("relay:room-refresh", { detail: { room: roomId } }));
    }

    function updatePreview(data, moveToTop = true) {
        document.dispatchEvent(
            new CustomEvent("relay:room-message", { detail: { room: roomId, message: data, moveToTop } })
        );
    }

    // Toast for errors and connection notes

    const toast = document.getElementById("chat-toast");
    let toastTimer = null;
    function showToast(text, { persist = false, action = null } = {}) {
        toast.replaceChildren(document.createTextNode(text));
        if (action) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn--ghost btn--sm";
            button.textContent = action.label;
            button.addEventListener("click", action.run);
            toast.append(button);
        }
        toast.hidden = false;
        clearTimeout(toastTimer);
        if (!persist) toastTimer = setTimeout(() => { toast.hidden = true; }, 4000);
    }
    function hideToast() {
        clearTimeout(toastTimer);
        toast.hidden = true;
    }

    // Connection

    const status = document.getElementById("status");
    const statusLabel = status.querySelector(".status__label");
    const sendButton = document.getElementById("send");
    const STATUS_TEXT = { connecting: "Connecting…", live: "Live", offline: "Reconnecting…" };

    function setStatus(state) {
        status.dataset.state = state;
        statusLabel.textContent = STATUS_TEXT[state];
        sendButton.disabled = state !== "live";
    }

    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const socketUrl = `${scheme}://${window.location.host}/chat/${encodeURIComponent(roomId)}`;
    let socket = null;
    let attempts = 0;
    let everConnected = false;
    let reconnectTimer = null;
    let checkTimer = null; // set while checking whether you're still a member
    let rechecking = false; // the socket was closed on purpose to check
    const STILL_HERE_MS = 1000;

    function connect() {
        if (gone) return;
        setStatus(attempts === 0 && !everConnected ? "connecting" : "offline");
        socket = new WebSocket(socketUrl);

        socket.addEventListener("open", () => {
            if (checkTimer) {
                // The server accepts for a moment before refusing (4403 or
                // 4404), so only an open socket that stays open means you're
                // still a member (e.g. added back).
                // Send nothing until then.
                clearTimeout(checkTimer);
                checkTimer = setTimeout(() => {
                    checkTimer = null;
                    if (socket.readyState !== WebSocket.OPEN) return; // closed meanwhile: reconnecting
                    attempts = 0;
                    setStatus("live");
                    markRead();
                    document.dispatchEvent(new CustomEvent("relay:room-still-here", { detail: { room: roomId } }));
                }, STILL_HERE_MS);
                return;
            } else if (everConnected) {
                showToast("Reconnected. Messages sent while you were away may be missing.", {
                    persist: true,
                    action: { label: "Reload", run: () => window.location.reload() },
                });
            }
            everConnected = true;
            attempts = 0;
            setStatus("live");
            markRead();
        });

        socket.addEventListener("message", (event) => {
            let data;
            try {
                data = JSON.parse(event.data);
            } catch (error) {
                console.warn("Relay: ignored a room frame that wasn't JSON.", error);
                return;
            }
            if (data.type === "save_message") {
                // Your reply arrived, so it wasn't refused.
                if (
                    pendingReply &&
                    data.user === me &&
                    data.reply_to &&
                    data.reply_to.id === pendingReply.target.id &&
                    data.message === pendingReply.text
                ) {
                    pendingReply = null;
                }
                const stick = nearBottom() || data.user === me;
                appendMessage(data);
                // Previews show conversation, not group events (matches the server).
                if (data.kind !== "system") updatePreview(data);
                if (stick) scrollToEnd();
                if (data.user !== me) {
                    hideTyping(data.user);
                    markRead();
                }
            } else if (data.type === "typing") {
                if (data.user !== me) showTyping(data);
            } else if (data.type === "message_updated") {
                updateMessage(data);
                updateQuotesOf(data);
                if (messages.length && messages[messages.length - 1].id === data.id) {
                    updatePreview({ ...data, message: data.deleted ? "Message deleted" : data.message }, false);
                }
                // The server's row may differ (e.g. a deleted last message); refetch it.
                refreshRow();
            } else if (data.type === "clear_room" && data.for === me) {
                clearGen += 1;
                messages.length = 0;
                hasMore = false;
                currentId = null;
                cancelReply({ announce: false, focus: false });
                pendingReply = null;
                dropToggles();
                closePicker({ focus: false });
                renderAll();
                showToast("History cleared for you.");
                refreshRow();
            } else if (data.type === "reactions_updated") {
                applyReactions(data.id, data.reactions);
            } else if (data.type === "room_updated") {
                applyRoomUpdate(data);
            } else if (data.type === "error") {
                if (data.for === "react") {
                    showToast(data.message || "Couldn\u2019t change that reaction.");
                    refuseOldestToggle();
                    return;
                }
                // A refused reply: its original was most likely deleted or
                // hidden meanwhile, so say so.
                const refusedReply = data.for === "save_message" && data.code === 400 && pendingReply;
                showToast(refusedReply ? "You can\u2019t reply to that message \u2014 it was deleted or isn\u2019t available." : data.message);
                // A refused send gives back the reply's text and target.
                if (data.for === "save_message") restorePendingReply();
            }
        });

        socket.addEventListener("close", (event) => {
            // Nothing will answer a reply or reaction sent on this socket now.
            pendingReply = null;
            for (const id of dropToggles()) redrawReactions(id);
            if (gone) return;
            // 4401 signed out, 4403 not a member, 4404 unknown room
            if (event.code === 4401) return window.location.assign("/account/login/");
            if (event.code === 4403 || event.code === 4404) return showGone(event.code === 4404);
            clearTimeout(reconnectTimer);
            if (rechecking) {
                rechecking = false;
                connect();
                return;
            }
            setStatus("offline");
            attempts += 1;
            const delay = Math.min(15000, 1000 * 2 ** Math.min(attempts - 1, 4));
            reconnectTimer = setTimeout(connect, delay);
        });
    }
    connect();

    // Read receipts: tell the server while this tab is visible.
    function markRead() {
        if (document.visibilityState !== "visible") return;
        if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "read" }));
    }
    document.addEventListener("visibilitychange", markRead);

    // Typing indicator

    const typingEl = document.getElementById("typing");
    const typers = new Map(); // username -> { name, timer }
    function renderTyping() {
        const names = [...typers.values()].map((t) => t.name);
        typingEl.hidden = names.length === 0;
        if (names.length === 1) typingEl.textContent = `${names[0]} is typing…`;
        else if (names.length === 2) typingEl.textContent = `${names[0]} and ${names[1]} are typing…`;
        else if (names.length > 2) typingEl.textContent = "Several people are typing…";
    }
    function showTyping(data) {
        const existing = typers.get(data.user);
        if (existing) clearTimeout(existing.timer);
        typers.set(data.user, {
            name: data.name || data.user,
            timer: setTimeout(() => hideTyping(data.user), 4000),
        });
        renderTyping();
    }
    function hideTyping(user) {
        const existing = typers.get(user);
        if (!existing) return;
        clearTimeout(existing.timer);
        typers.delete(user);
        renderTyping();
    }

    // The room went away while open: keep a muted header so you know which
    // chat it was, explain in the pane, and offer a way back.
    function showGone(deleted) {
        if (gone) return;
        gone = true;
        clearTimeout(checkTimer);
        clearTimeout(reconnectTimer);
        socket?.close();
        for (const t of typers.values()) clearTimeout(t.timer);
        typers.clear();
        clearTimeout(toastTimer);
        document.querySelectorAll(".chat-main dialog[open]").forEach((d) => d.close());

        const main = document.querySelector(".chat-main");
        const head = main.querySelector(".chat-head");
        const name = head.querySelector(".chat-head__title").textContent.trim();

        // Header: muted, no Details button, "Not a member" or "Deleted".
        // The pane's heading is now the page's h1, so the title becomes a p.
        head.classList.add("chat-head--gone");
        head.querySelector(".chat-head__details")?.remove();
        const oldTitle = head.querySelector(".chat-head__title");
        const title = document.createElement("p");
        title.className = oldTitle.className;
        title.textContent = name;
        oldTitle.replaceWith(title);
        const meta = head.querySelector(".chat-head__meta");
        const state = document.createElement("span");
        state.textContent = deleted ? "Deleted" : "Not a member";
        meta.replaceChildren(state);

        const pane = document.getElementById("gone-template").content.firstElementChild.cloneNode(true);
        pane.querySelector(`[data-gone-icon="${deleted ? "removed" : "deleted"}"]`).remove();
        const heading = pane.querySelector("[data-gone-heading]");
        heading.textContent = deleted ? `${name} was deleted` : `You\u2019re no longer in ${name}`;
        pane.querySelector("[data-gone-text]").textContent = deleted
            ? "An admin deleted it, so its messages are gone for everyone."
            : "You were removed or left, so you can\u2019t read or send messages here any more. Ask a member to add you back.";

        for (const child of [...main.children]) {
            if (child !== head && !child.classList.contains("chat-notices")) child.remove();
        }
        main.append(pane);

        document.getElementById("details")?.setAttribute("hidden", "");
        document.querySelector(".chat")?.classList.remove("chat--details-open");
        // inbox.js owns the room list (and its empty state) and the tab title.
        document.dispatchEvent(new CustomEvent("relay:room-removed", { detail: { room: roomId } }));
        document.dispatchEvent(
            new CustomEvent("relay:base-title", {
                detail: { title: `${deleted ? `${name} was deleted` : `No longer in ${name}`} \u00b7 Relay` },
            })
        );
        heading.focus();
    }
    // inbox.js heard the room left your list (room_removed, or missing after
    // a resync). Reconnect now: the server refuses with 4403 (not a member)
    // or 4404 (deleted), which picks the right copy. If neither answer comes
    // within 3 seconds (e.g. offline), say you're no longer in it.
    const CHECK_TIMEOUT_MS = 3000;
    document.addEventListener("relay:room-check", (event) => {
        if (event.detail.room !== roomId || gone || checkTimer) return;
        checkTimer = setTimeout(() => {
            checkTimer = null;
            showGone(false);
        }, CHECK_TIMEOUT_MS);
        clearTimeout(reconnectTimer);
        attempts = 0;
        if (socket && socket.readyState === WebSocket.CLOSED) {
            connect();
        } else if (socket) {
            rechecking = true;
            socket.close();
        }
    });

    // Group changes: new name or member count in the header. inbox.js
    // updates the room list row.
    // Same rule as initials() in chat/presenters.py: the first letter or
    // digit of the first two words, else the first two letters or digits
    // of the only word, else "?".
    function initialsOf(name) {
        const words = (name || "")
            .split(PY_WHITESPACE)
            .map((word) => Array.from(word.replace(/[^\p{L}\p{N}]/gu, "")))
            .filter((chars) => chars.length);
        if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
        return words.length ? words[0].slice(0, 2).join("").toUpperCase() : "?";
    }

    function applyRoomUpdate(data) {
        if (gone) return;
        const title = document.querySelector(".chat-head__title");
        const isGroup = title && !title.dataset.private;
        const initials = data.name ? initialsOf(data.name) : undefined;
        if (isGroup && data.name) {
            title.textContent = data.name;
            const headAvatar = document.querySelector(".chat-head .avatar");
            if (headAvatar) headAvatar.textContent = initials;
            basePlaceholder = `Message ${data.name}`;
            if (!replyTarget) input.placeholder = basePlaceholder;
            document.querySelector('label[for="message"]').textContent = `Message ${data.name}`;
            document.dispatchEvent(new CustomEvent("relay:base-title", { detail: { title: `${data.name} \u00b7 Relay` } }));
        }
        const count = document.querySelector("[data-member-count]");
        if (count) count.textContent = `${data.member_count} member${data.member_count === 1 ? "" : "s"}`;
        document.dispatchEvent(new CustomEvent("relay:room-updated", { detail: { ...data, initials } }));
    }

    function send(payload) {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify(payload));
            return true;
        }
        showToast("Not connected yet. Your message is still in the box.");
        return false;
    }

    // Composer

    const composer = document.getElementById("composer");
    const input = document.getElementById("message");

    function autosize() {
        input.style.height = "auto";
        input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
    }
    input.addEventListener("input", autosize);

    let lastTypingSent = 0;
    input.addEventListener("input", () => {
        const now = Date.now();
        if (input.value.trim() && now - lastTypingSent > 2500 && socket && socket.readyState === WebSocket.OPEN) {
            lastTypingSent = now;
            socket.send(JSON.stringify({ type: "typing" }));
        }
    });

    // Mention autocomplete. Typing "@" (not right after a letter, digit or
    // underscore) and the start of a username or name opens a listbox of
    // matching members (not you), at most 8. Up and Down move, Enter or Tab
    // inserts "@username ", Escape closes; while it is open those keys do
    // nothing else (no send, no edit-last, no cancelling the reply). A
    // click or tap picks.

    const MENTION_MAX = 8;
    const mentionList = document.getElementById("mention-list");
    // [{username, name, initials}], current members sorted by name.
    let members = (readJSON("room-member-list") || []).filter((m) => m && typeof m.username === "string");
    // Members joined or left (inbox.js, from room_changed): keep who is
    // still here; newcomers have only a username until the next load.
    document.addEventListener("relay:room-members", (event) => {
        if (event.detail.room !== roomId || !Array.isArray(event.detail.usernames)) return;
        const known = new Map(members.map((m) => [m.username, m]));
        members = event.detail.usernames
            .map((u) => known.get(u) || { username: u, name: u, initials: initialsOf(u) })
            .sort((a, b) => a.name.localeCompare(b.name));
        if (mention) refreshMention();
    });

    let mention = null; // { start, end, query, items, active } while open
    let dismissed = null; // "start:query" of a token you closed with Escape

    // The "@token" the caret is in or right after, or null.
    function tokenAtCaret() {
        if (input.selectionStart !== input.selectionEnd) return null;
        const caret = input.selectionStart;
        const before = input.value.slice(0, caret);
        const match = /(?<![\p{L}\p{N}_])@([a-z0-9_]*)$/iu.exec(before);
        if (!match) return null;
        const after = /^[a-z0-9_]*/i.exec(input.value.slice(caret))[0];
        return { start: match.index, end: caret + after.length, query: match[1].toLowerCase() };
    }

    function matchMembers(query) {
        const byUser = [];
        const byName = [];
        for (const m of members) {
            if (m.username === me) continue;
            const words = (m.name || "").toLowerCase().split(PY_WHITESPACE).filter(Boolean);
            if (m.username.startsWith(query)) byUser.push(m);
            else if ((m.name || "").toLowerCase().startsWith(query) || words.some((w) => w.startsWith(query))) byName.push(m);
        }
        return [...byUser, ...byName].slice(0, MENTION_MAX);
    }

    const optionId = (i) => `mention-option-${i}`;

    function renderMention() {
        const options = mention.items.map((m, i) => {
            const option = document.createElement("li");
            option.className = "mention-option";
            option.id = optionId(i);
            option.setAttribute("role", "option");
            option.setAttribute("aria-selected", String(i === mention.active));
            option.dataset.username = m.username;
            const avatar = document.createElement("span");
            avatar.className = "avatar mention-option__avatar";
            avatar.setAttribute("aria-hidden", "true");
            avatar.textContent = m.initials || initialsOf(m.name || m.username);
            const name = document.createElement("span");
            name.className = "mention-option__name";
            name.textContent = m.name || m.username;
            const handle = document.createElement("span");
            handle.className = "mention-option__handle";
            handle.textContent = `@${m.username}`;
            option.append(avatar, name, " ", handle);
            return option;
        });
        mentionList.replaceChildren(...options);
        mentionList.hidden = false;
        input.setAttribute("aria-activedescendant", optionId(mention.active));
        mentionList.children[mention.active]?.scrollIntoView({ block: "nearest" });
    }

    function closeMention() {
        if (!mention) return;
        mention = null;
        mentionList.hidden = true;
        mentionList.replaceChildren();
        input.removeAttribute("aria-activedescendant");
    }

    // Open, update or close the list for where the caret is now.
    function refreshMention() {
        const token = tokenAtCaret();
        if (!token || dismissed === `${token.start}:${token.query}`) return closeMention();
        const items = matchMembers(token.query);
        if (!items.length) return closeMention();
        const keep = mention && mention.start === token.start ? mention.items[mention.active]?.username : null;
        const active = Math.max(0, items.findIndex((m) => m.username === keep));
        mention = { ...token, items, active };
        renderMention();
    }

    function moveMention(step) {
        const count = mention.items.length;
        mention.active = (mention.active + step + count) % count;
        for (const [i, option] of [...mentionList.children].entries()) {
            option.setAttribute("aria-selected", String(i === mention.active));
        }
        input.setAttribute("aria-activedescendant", optionId(mention.active));
        mentionList.children[mention.active].scrollIntoView({ block: "nearest" });
    }

    // Replace the typed token with "@username " (one space, unless one
    // follows already), keeping undo where the browser supports it.
    function pickMention(index) {
        const picked = mention && mention.items[index];
        if (!picked) return;
        const { start, end } = mention;
        closeMention();
        const spaced = /^\s/.test(input.value.slice(end));
        const text = `@${picked.username}${spaced ? "" : " "}`;
        input.focus();
        input.setSelectionRange(start, end);
        let done = false;
        try {
            done = document.execCommand("insertText", false, text);
        } catch (error) {
            console.warn("Relay: insertText failed: %s", String(error));
        }
        if (!done || input.value.slice(start, start + text.length) !== text) {
            input.setRangeText(text, start, end, "end");
        }
        const caret = start + text.length + (spaced ? 1 : 0);
        input.setSelectionRange(caret, caret);
        dismissed = null;
        closeMention();
        autosize();
    }

    // A textarea can't take role="combobox" (so not aria-expanded either);
    // aria-activedescendant makes screen readers read the active option.
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", "mention-list");

    input.addEventListener("input", () => {
        dismissed = null;
        refreshMention();
    });
    // The caret moved without typing (arrows, a click): follow it.
    input.addEventListener("keyup", (event) => {
        if (["ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown"].includes(event.key)) refreshMention();
    });
    input.addEventListener("click", refreshMention);
    input.addEventListener("blur", closeMention);

    // Capture: runs before the composer's own keys (send, edit last,
    // cancel reply), which an open list takes over.
    composer.addEventListener(
        "keydown",
        (event) => {
            if (!mention || event.target !== input || event.isComposing) return;
            if (event.altKey || event.ctrlKey || event.metaKey) return;
            let handled = true;
            if (event.key === "ArrowDown") moveMention(1);
            else if (event.key === "ArrowUp") moveMention(-1);
            else if ((event.key === "Enter" && !event.shiftKey) || (event.key === "Tab" && !event.shiftKey)) pickMention(mention.active);
            else if (event.key === "Escape") {
                dismissed = `${mention.start}:${mention.query}`;
                closeMention();
            } else handled = false;
            if (!handled) return;
            event.preventDefault();
            event.stopPropagation();
        },
        true
    );
    // Keep focus in the textarea; the click picks.
    mentionList.addEventListener("mousedown", (event) => event.preventDefault());
    mentionList.addEventListener("click", (event) => {
        const option = event.target.closest(".mention-option");
        if (!option || !mention) return;
        pickMention([...mentionList.children].indexOf(option));
    });

    // Replying: the bar above the composer says to whom; sending clears it.

    const replyBar = document.getElementById("reply-bar");
    const replyName = replyBar.querySelector("[data-reply-name]");
    const replyExcerpt = replyBar.querySelector("[data-reply-excerpt]");
    const replyStatus = document.getElementById("reply-status");
    const hint = composer.querySelector(".composer__hint");
    let basePlaceholder = input.placeholder;
    const baseHint = hint ? hint.textContent : "";
    let replyTarget = null; // { id, name, excerpt } while replying
    // A reply just sent: if the server refuses it, its text and target come back.
    let pendingReply = null;

    function announce(text) {
        // Clear first so the same words are read again.
        replyStatus.textContent = "";
        setTimeout(() => { replyStatus.textContent = text; }, 50);
    }

    // Showing or hiding the bar shrinks or grows the transcript; keep the
    // newest message in view if you were at the bottom.
    function toggleBar(show) {
        const stick = nearBottom();
        replyBar.hidden = !show;
        if (stick) scrollToEnd();
    }

    function setReply(data, { announce: say = true, focus = true } = {}) {
        const name = data.user === me ? "yourself" : data.name || data.user;
        replyTarget = { id: data.id, user: data.user, name, excerpt: excerptOf(data.message) };
        replyName.textContent = name;
        replyExcerpt.textContent = replyTarget.excerpt;
        input.placeholder = `Reply to ${name}`;
        if (hint) hint.textContent = "Esc cancel reply \u00b7 Shift \u21b5 new line";
        toggleBar(true);
        if (say) announce(`Replying to ${name}`);
        if (focus) input.focus();
    }

    function cancelReply({ announce: say = true, focus = true } = {}) {
        if (!replyTarget) return;
        replyTarget = null;
        toggleBar(false);
        replyName.textContent = "";
        replyExcerpt.textContent = "";
        input.placeholder = basePlaceholder;
        if (hint) hint.textContent = baseHint;
        if (say) announce("Reply cancelled");
        if (focus) input.focus();
    }

    // The server refused the reply you sent: put its text and target back,
    // unless you've started writing something else.
    function restorePendingReply() {
        if (!pendingReply) return;
        const { text, target } = pendingReply;
        pendingReply = null;
        if (input.value.trim() !== "") return;
        input.value = text;
        autosize();
        const original = messages.find((m) => m.id === target.id);
        if (original && actionable(original)) setReply(original, { announce: false, focus: false });
        else cancelReply({ announce: false, focus: false });
    }

    replyBar.querySelector("[data-reply-cancel]").addEventListener("click", () => cancelReply());

    composer.addEventListener("submit", (event) => {
        event.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        const payload = { type: "save_message", message: text };
        if (replyTarget) payload.reply_to = replyTarget.id;
        if (send(payload)) {
            // A plain send keeps an earlier reply's pending state, so if that
            // reply is refused its text still comes back.
            if (replyTarget) pendingReply = { text, target: replyTarget };
            input.value = "";
            autosize();
            cancelReply({ announce: false, focus: false });
        }
        input.focus();
    });

    // Escape in the composer cancels a reply (details.js leaves it to us).
    // The mention list, then an open dialog or menu, take Escape first.
    const overlayOpen = () =>
        !!document.querySelector(
            ".mention-list:not([hidden]), dialog[open], details[data-popover][open], .reaction-picker, button.reaction:focus .reaction__tip:not([hidden])"
        );
    composer.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || !replyTarget || event.isComposing || overlayOpen()) return;
        event.preventDefault();
        cancelReply();
    });
    replyBar.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || !replyTarget || overlayOpen()) return;
        event.preventDefault();
        cancelReply();
    });

    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            composer.requestSubmit();
        }
    });

    // Edit and delete your own messages

    function startEdit(row) {
        const data = messages.find((m) => m.id === row.dataset.id);
        if (!data || data.deleted || row.querySelector(".msg__edit")) return;
        const text = row.querySelector(".msg__text");
        const actions = row.querySelector(".msg__actions");
        text.hidden = true;
        if (actions) actions.hidden = true;

        const form = document.createElement("form");
        form.className = "msg__edit";
        const area = document.createElement("textarea");
        area.className = "input msg__edit-input";
        area.value = data.message;
        area.rows = Math.min(6, data.message.split("\n").length);
        area.maxLength = 4000;
        area.setAttribute("aria-label", "Edit message");
        const save = document.createElement("button");
        save.type = "submit";
        save.className = "btn btn--primary btn--sm";
        save.textContent = "Save";
        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.className = "btn btn--ghost btn--sm";
        cancel.textContent = "Cancel";
        const hint = document.createElement("span");
        hint.className = "msg__edit-hint";
        hint.textContent = "Enter to save · Esc to cancel";
        form.append(area, save, cancel, hint);
        text.after(form);
        form.scrollIntoView({ block: "nearest" });
        area.focus();
        area.setSelectionRange(area.value.length, area.value.length);

        const finish = () => {
            form.remove();
            text.hidden = false;
            if (actions) actions.hidden = false;
        };
        cancel.addEventListener("click", () => { finish(); input.focus(); });
        area.addEventListener("keydown", (event) => {
            if (event.key === "Escape") { event.preventDefault(); finish(); input.focus(); }
            if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); form.requestSubmit(); }
        });
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            const value = area.value.trim();
            if (!value) return showToast("Message cannot be empty. Use Delete to remove it.");
            if (value === data.message || send({ type: "edit_message", id: data.id, message: value })) finish();
            input.focus();
        });
    }

    const deleteDialog = document.getElementById("delete-dialog");
    let pendingDelete = null;
    const touchOnly = window.matchMedia("(hover: none)");
    function selectRow(row) {
        for (const other of transcript.querySelectorAll(".msg.is-selected")) {
            if (other !== row) other.classList.remove("is-selected");
        }
        if (row) row.classList.toggle("is-selected");
    }

    transcript.addEventListener("click", (event) => {
        const quote = event.target.closest("button.msg__quote");
        if (quote) {
            selectRow(null);
            jumpTo(quote.dataset.replyTo, quote);
            return;
        }
        // Reactions: a chip toggles yours; a picker option toggles it and
        // closes the picker. Neither selects or deselects the row.
        const chip = event.target.closest("button.reaction");
        if (chip) {
            toggleReaction(chip.closest(".msg[data-id]").dataset.id, chip.dataset.reaction);
            return;
        }
        const option = event.target.closest(".reaction-picker__option");
        if (option) {
            const id = picker?.row.dataset.id;
            closePicker();
            if (id) toggleReaction(id, option.dataset.pick);
            return;
        }
        if (event.target.closest(".reaction-picker, .msg__reactions")) return;
        const button = event.target.closest(".msg__action");
        if (!button) {
            // Touch screens: tap a message to show its actions.
            if (!touchOnly.matches || event.target.closest(".msg__edit")) return;
            const row = event.target.closest(".msg:not(.msg--system)");
            selectRow(row && row.querySelector(".msg__actions") ? row : null);
            return;
        }
        const row = button.closest(".msg");
        // React keeps a selected row's bar (touch) open; its picker opens there.
        if (button.dataset.action === "react") return openPicker(button);
        row.classList.remove("is-selected");
        if (button.dataset.action === "reply") {
            const data = messages.find((m) => m.id === row.dataset.id);
            if (data && actionable(data)) setReply(data);
        }
        if (button.dataset.action === "edit") startEdit(row);
        if (button.dataset.action === "delete") {
            pendingDelete = row.dataset.id;
            deleteDialog.returnValue = "";
            deleteDialog.showModal();
        }
    });
    deleteDialog.addEventListener("close", () => {
        if (deleteDialog.returnValue === "delete" && pendingDelete) {
            send({ type: "delete_message", id: pendingDelete });
        }
        pendingDelete = null;
        input.focus();
    });

    // Up arrow in an empty composer edits your last message.
    input.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowUp" || input.value !== "") return;
        const lastMine = [...messages].reverse().find((m) => m.user === me && !m.deleted && m.kind !== "system");
        if (!lastMine) return;
        const row = transcript.querySelector(`.msg[data-id="${CSS.escape(lastMine.id)}"]`);
        if (!row) return;
        event.preventDefault();
        row.scrollIntoView({ block: "nearest" });
        startEdit(row);
    });

    // Clear history, after confirmation

    // The button lives in the Details panel, which is loaded later, so
    // listen on the document.
    const dialog = document.getElementById("clear-dialog");
    let clearOpener = null;
    document.addEventListener("click", (event) => {
        const button = event.target.closest("[data-clear-room]");
        if (!button || typeof dialog.showModal !== "function") return;
        clearOpener = button;
        dialog.returnValue = "";
        dialog.showModal();
    });
    dialog.addEventListener("close", () => {
        if (dialog.returnValue === "clear") send({ type: "clear_room" });
        clearOpener?.focus();
    });

    if (window.matchMedia("(min-width: 600px)").matches) input.focus();
})();
