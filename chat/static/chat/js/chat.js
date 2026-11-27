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
    // one row; loading older history re-renders so grouping stays right.

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

    function fillText(container, data) {
        container.replaceChildren();
        if (data.deleted) {
            container.classList.add("msg__text--deleted");
            container.textContent = "Message deleted";
            return;
        }
        container.classList.remove("msg__text--deleted");
        container.append(document.createTextNode(data.message));
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
    function actionsFor(data) {
        const items = [["reply", "Reply", "Reply to message"]];
        if (data.user === me) items.push(["edit", "Edit", "Edit message"], ["delete", "Delete", "Delete message"]);
        const bar = document.createElement("span");
        bar.className = "msg__actions";
        for (const [action, label, name] of items) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "msg__action";
            button.dataset.action = action;
            button.textContent = label;
            button.setAttribute("aria-label", name);
            bar.append(button);
        }
        return bar;
    }

    // The quote above a reply: a button that jumps to the original, or a
    // plain note when you can't see the original.
    function buildQuote(reply) {
        if (!reply.available) {
            const note = document.createElement("div");
            note.className = "msg__quote msg__quote--unavailable";
            note.textContent = "Original message unavailable";
            return note;
        }
        const quote = document.createElement("button");
        quote.type = "button";
        quote.className = "msg__quote";
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
            prev && prev.kind !== "system" && prev.user === data.user && date - prevDate < GROUP_GAP_MS;

        const row = document.createElement("div");
        row.className = "msg" + (continues ? " msg--cont" : "") + (mine ? " msg--mine" : "");
        row.dataset.id = data.id;

        const time = document.createElement("time");
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
        if (actionable(data)) body.append(actionsFor(data));

        row.append(time, node, body);
        nodes.push(row);
        return nodes;
    }

    function renderAll() {
        // Keep focus and the jump tint on the same message (e.g. a jump
        // target near the top that makes older history load).
        const focused = transcript.contains(document.activeElement) ? document.activeElement.closest(".msg[data-id]") : null;
        const targetId = transcript.querySelector(".msg--target")?.dataset.id;
        const nodes = [];
        messages.forEach((data, i) => nodes.push(...buildRow(data, messages[i - 1] || null)));
        transcript.replaceChildren(...nodes);
        if (focused) {
            const row = transcript.querySelector(`.msg[data-id="${CSS.escape(focused.dataset.id)}"]`);
            if (row) {
                row.tabIndex = -1;
                row.focus({ preventScroll: true });
            }
        }
        if (targetId) transcript.querySelector(`.msg[data-id="${CSS.escape(targetId)}"]`)?.classList.add("msg--target");
        emptyNote.hidden = messages.length > 0;
        updateHistoryStatus();
    }

    function appendMessage(data) {
        if (messages.some((m) => m.id === data.id)) return;
        transcript.append(...buildRow(data, messages[messages.length - 1] || null));
        messages.push(data);
        emptyNote.hidden = true;
    }

    function updateMessage(data) {
        const index = messages.findIndex((m) => m.id === data.id);
        if (index === -1) return;
        messages[index] = data;
        const row = transcript.querySelector(`.msg[data-id="${CSS.escape(data.id)}"]`);
        if (!row) return;
        const text = row.querySelector(".msg__text");
        fillText(text, data);
        text.hidden = false;
        if (data.deleted) {
            row.querySelector(".msg__quote")?.remove();
            row.classList.remove("is-selected");
        }
        row.querySelector(".msg__actions")?.remove();
        row.querySelector(".msg__edit")?.remove();
        if (actionable(data)) row.querySelector(".msg__body").append(actionsFor(data));
    }

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
    function loadOlder(limit = historyMeta.page_size) {
        if (olderRequest) return olderRequest;
        if (!hasMore || !messages.length) return Promise.resolve(false);
        olderRequest = fetchOlder(limit).finally(() => { olderRequest = null; });
        return olderRequest;
    }

    async function fetchOlder(limit) {
        loadingOlder = true;
        updateHistoryStatus();
        const before = messages[0].id;
        try {
            const url = `/chat/rooms/${encodeURIComponent(roomId)}/messages/?before=${encodeURIComponent(before)}&limit=${encodeURIComponent(limit)}`;
            const response = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
            if (!response.ok) throw new Error(String(response.status));
            const page = await response.json();
            const known = new Set(messages.map((m) => m.id));
            const older = page.messages.filter((m) => !known.has(m.id));
            const fromBottom = scroller.scrollHeight - scroller.scrollTop;
            messages.unshift(...older);
            hasMore = page.has_more;
            loadingOlder = false;
            renderAll();
            scroller.scrollTop = scroller.scrollHeight - fromBottom;
            return true;
        } catch (error) {
            console.warn("Relay: couldn't load earlier messages: %s", String(error));
            loadingOlder = false;
            updateHistoryStatus();
            showToast("Couldn't load earlier messages. Scroll up to try again.");
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

    const rowFor = (id) => transcript.querySelector(`.msg[data-id="${CSS.escape(id)}"]`);

    function showTarget(row) {
        for (const old of transcript.querySelectorAll(".msg--target")) old.classList.remove("msg--target");
        clearTimeout(targetTimer);
        row.scrollIntoView({ block: "center", behavior: reducedMotion.matches ? "auto" : "smooth" });
        row.tabIndex = -1;
        row.focus({ preventScroll: true });
        // Restart the tint if the same message is the target again.
        void row.offsetWidth;
        row.classList.add("msg--target");
        // Query again: loading older history may have rebuilt the row.
        targetTimer = setTimeout(() => {
            for (const tinted of transcript.querySelectorAll(".msg--target")) tinted.classList.remove("msg--target");
        }, TARGET_MS);
    }

    async function jumpTo(id) {
        if (jumping) return;
        let row = rowFor(id);
        if (row) return showTarget(row);
        jumping = true;
        try {
            for (let pages = 0; !row && hasMore && pages < JUMP_MAX_PAGES; pages += 1) {
                if (!(await loadOlder(JUMP_PAGE_SIZE))) {
                    if (hasMore) return; // the request failed and said so
                    break;
                }
                row = rowFor(id);
            }
            if (row) showTarget(row);
            else if (hasMore) showToast("That message is too far back.");
            else showToast("Couldn't find that message.");
        } catch (error) {
            console.warn("Relay: couldn't jump to message %s: %s", id, String(error));
            showToast("Couldn't jump to that message.");
        } finally {
            jumping = false;
        }
    }

    scroller.addEventListener("scroll", () => {
        if (scroller.scrollTop < 80 && !jumping) loadOlder();
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
                if (data.user === me) pendingReply = null;
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
                messages.length = 0;
                hasMore = false;
                renderAll();
                showToast("History cleared for you.");
                refreshRow();
            } else if (data.type === "room_updated") {
                applyRoomUpdate(data);
            } else if (data.type === "error") {
                showToast(data.message);
                // A refused send gives back the reply's text and target.
                if (data.for === "save_message") restorePendingReply();
            }
        });

        socket.addEventListener("close", (event) => {
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
            input.placeholder = `Message ${data.name}`;
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

    // Replying: the bar above the composer says to whom; sending clears it.

    const replyBar = document.getElementById("reply-bar");
    const replyName = replyBar.querySelector("[data-reply-name]");
    const replyExcerpt = replyBar.querySelector("[data-reply-excerpt]");
    const replyStatus = document.getElementById("reply-status");
    let replyTarget = null; // { id, name, excerpt } while replying
    // A reply just sent: if the server refuses it, its text and target come back.
    let pendingReply = null;

    function announce(text) {
        // Clear first so the same words are read again.
        replyStatus.textContent = "";
        setTimeout(() => { replyStatus.textContent = text; }, 50);
    }

    function setReply(data, { announce: say = true, focus = true } = {}) {
        const name = data.user === me ? "yourself" : data.name || data.user;
        replyTarget = { id: data.id, user: data.user, name, excerpt: excerptOf(data.message) };
        replyName.textContent = name;
        replyExcerpt.textContent = replyTarget.excerpt;
        replyBar.hidden = false;
        if (say) announce(`Replying to ${name}`);
        if (focus) input.focus();
    }

    function cancelReply({ announce: say = true, focus = true } = {}) {
        if (!replyTarget) return;
        replyTarget = null;
        replyBar.hidden = true;
        replyName.textContent = "";
        replyExcerpt.textContent = "";
        if (say) announce("Reply cancelled");
        if (focus) input.focus();
    }

    function restorePendingReply() {
        if (!pendingReply) return;
        const { text, target } = pendingReply;
        pendingReply = null;
        if (input.value === "") {
            input.value = text;
            autosize();
        }
        if (!replyTarget) {
            const original = messages.find((m) => m.id === target.id);
            if (original && actionable(original)) setReply(original, { announce: false, focus: false });
        }
    }

    replyBar.querySelector("[data-reply-cancel]").addEventListener("click", () => cancelReply());

    composer.addEventListener("submit", (event) => {
        event.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        const payload = { type: "save_message", message: text };
        if (replyTarget) payload.reply_to = replyTarget.id;
        if (send(payload)) {
            pendingReply = replyTarget ? { text, target: replyTarget } : null;
            input.value = "";
            autosize();
            cancelReply({ announce: false, focus: false });
        }
        input.focus();
    });

    // Escape in the composer cancels a reply (details.js leaves it to us).
    composer.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || !replyTarget || event.isComposing) return;
        event.preventDefault();
        cancelReply();
    });
    replyBar.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || !replyTarget) return;
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
        row.querySelector(".msg__body").append(form);
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
            jumpTo(quote.dataset.replyTo);
            return;
        }
        const button = event.target.closest(".msg__action");
        if (!button) {
            // Touch screens: tap a message to show its actions.
            if (!touchOnly.matches || event.target.closest(".msg__edit")) return;
            const row = event.target.closest(".msg:not(.msg--system)");
            selectRow(row && row.querySelector(".msg__actions") ? row : null);
            return;
        }
        const row = button.closest(".msg");
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
