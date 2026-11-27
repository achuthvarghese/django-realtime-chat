// Inbox socket: presence for people you share rooms with, and the live room
// list (new activity, rooms added, renamed and removed). This module owns the
// room list and the tab title; other modules talk to it with relay:* events.

(() => {
    "use strict";

    const readJSON = (id) => {
        const element = document.getElementById(id);
        return element ? JSON.parse(element.textContent) : null;
    };
    const me = readJSON("me");
    const currentRoom = readJSON("room-id");
    let roomMembers = readJSON("room-members") || [];
    let baseTitle = document.title;
    const online = new Set();

    // Times and previews, the same way the server renders a row

    const timeFormat = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });
    const fullFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "full", timeStyle: "short" });
    const shortDateFormat = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
    const PREVIEW_LENGTH = 60;

    function daysAgo(date) {
        const start = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
        return Math.round((start(new Date()) - start(date)) / 86400000);
    }

    // Today: clock time; yesterday: "Yesterday"; older: short date. The full
    // date is in the tooltip.
    function setTime(time, iso) {
        const date = iso ? new Date(iso) : null;
        if (!date || Number.isNaN(date.getTime())) {
            time.textContent = "";
            time.removeAttribute("datetime");
            time.removeAttribute("title");
            delete time.dataset.relative;
            return;
        }
        const ago = daysAgo(date);
        time.dateTime = iso;
        time.dataset.relative = "";
        time.textContent = ago === 0 ? timeFormat.format(date) : ago === 1 ? "Yesterday" : shortDateFormat.format(date);
        time.title = fullFormat.format(date);
    }

    // Django's truncatechars: 59 characters and an ellipsis (counts code points).
    function truncate(text) {
        const chars = Array.from(text || "");
        return chars.length > PREVIEW_LENGTH ? chars.slice(0, PREVIEW_LENGTH - 1).join("") + "…" : chars.join("");
    }

    const previewText = (content, mine) => (mine ? "You: " : "") + truncate(content);

    // When the row last changed, from its <time datetime>.
    function lastAt(link) {
        const value = link.querySelector(".room-link__time")?.getAttribute("datetime");
        const time = value ? Date.parse(value) : NaN;
        return Number.isNaN(time) ? null : time;
    }

    // Presence

    function renderPresence() {
        // Room list rows and member rows in the Details panel.
        for (const row of document.querySelectorAll(".room-link[data-username], .member[data-username]")) {
            row.classList.toggle("is-online", online.has(row.dataset.username));
        }
        for (const label of document.querySelectorAll("[data-presence-for]")) {
            const isOnline = online.has(label.dataset.presenceFor);
            label.textContent = isOnline ? "Online" : "Offline";
            label.classList.toggle("is-online", isOnline);
        }
        const count = document.querySelector("[data-presence-count]");
        if (count) {
            const n = roomMembers.filter((u) => u !== me && online.has(u)).length + 1;
            count.textContent = ` · ${n} online`;
            count.hidden = false;
        }
    }

    // Unread badges and the tab title

    function setUnread(link, n) {
        link.dataset.unread = String(n);
        link.classList.toggle("room-link--unread", n > 0);
        const badge = link.querySelector(".room-link__unread");
        if (badge) {
            badge.hidden = n === 0;
            badge.querySelector("[data-unread-count]").textContent = n > 99 ? "99+" : String(n);
        }
        renderTitle();
    }

    function renderTitle() {
        const total = [...document.querySelectorAll(".room-link")].reduce(
            (sum, link) => sum + Number(link.dataset.unread || 0),
            0
        );
        document.title = total > 0 ? `(${total}) ${baseTitle}` : baseTitle;
    }

    // Live room list: rooms appear, change and disappear without a reload.

    const list = document.getElementById("room-list");
    const findLink = (roomId) => list.querySelector(`.room-link[data-room-id="${CSS.escape(roomId)}"]`);

    // Every list change gets a sequence number, so a fetch that started
    // before a room was removed (or added) can't undo that change.
    let seq = 0;
    const removedAt = new Map(); // room id -> seq of its room_removed
    const addedAt = new Map(); // room id -> seq of its latest room_added

    // Tell chat.js (search filter) that rows were added, removed or changed.
    let changedQueued = false;
    function listChanged() {
        if (changedQueued) return;
        changedQueued = true;
        queueMicrotask(() => {
            changedQueued = false;
            document.dispatchEvent(new CustomEvent("relay:rooms-changed"));
        });
    }

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    // Mirrors the room row in chat/templates/chat/chat.html.
    function buildRoomItem(room) {
        const link = el("a", "room-link");
        link.href = `/chat/?room=${encodeURIComponent(room.id)}`;
        link.dataset.roomId = room.id;
        if (room.other_username) link.dataset.username = room.other_username;
        link.dataset.unread = "0";

        const wrap = el("span", "room-link__avatar-wrap");
        wrap.append(el("span", "avatar room-link__avatar" + (room.type === "group" ? " room-link__avatar--group" : "")));
        if (room.other_username) {
            const dot = el("span", "presence-dot");
            dot.setAttribute("aria-hidden", "true");
            wrap.append(dot);
        }
        const text = el("span", "room-link__text");
        text.append(el("span", "room-link__title"), el("span", "room-link__preview"));
        const meta = el("span", "room-link__meta");
        const badge = el("span", "badge room-link__unread");
        badge.hidden = true;
        badge.append(el("span", "visually-hidden", "Unread: "));
        const count = el("span", null, "0");
        count.dataset.unreadCount = "";
        badge.append(count);
        meta.append(el("time", "room-link__time"), badge);
        link.append(wrap, text, meta);

        const item = el("li");
        item.append(link);
        return item;
    }

    // Only the keys present are applied: room_changed frames are partial.
    function applyIdentity(link, room) {
        if (typeof room.title === "string") {
            link.dataset.title = room.title.toLowerCase();
            link.title = room.title;
            link.querySelector(".room-link__title").textContent = room.title;
        }
        if (typeof room.initials === "string") {
            link.querySelector(".room-link__avatar").textContent = room.initials;
        }
        if (room.id === currentRoom && Array.isArray(room.member_usernames)) {
            roomMembers = room.member_usernames;
            renderPresence();
        }
    }

    // Preview, time and unread from a full room object, unless the row
    // already shows something newer.
    function applyActivity(link, room) {
        const shown = lastAt(link);
        const incoming = room.last_at ? Date.parse(room.last_at) : null;
        if (shown !== null && (incoming === null || incoming < shown)) return;
        link.querySelector(".room-link__preview").textContent = room.last_content
            ? previewText(room.last_content, room.last_is_mine)
            : "No messages yet";
        setTime(link.querySelector(".room-link__time"), room.last_at);
        if (room.id !== currentRoom) setUnread(link, room.unread || 0);
    }

    // A new row grows into place, then its tint fades (see .room-list__new).
    function animateIn(item) {
        item.classList.add("room-list__new");
        const link = item.querySelector(".room-link");
        let timer = null;
        const done = (event) => {
            if (event && event.animationName !== "room-flash") return;
            item.classList.remove("room-list__new");
            link.removeEventListener("animationend", done);
            clearTimeout(timer);
        };
        link.addEventListener("animationend", done);
        timer = setTimeout(done, 2500);
    }

    // Add or refresh a row from a full room object.
    function upsertRoom(room, { moveToTop }) {
        let link = findLink(room.id);
        if (!link) {
            list.querySelector(".room-list__empty")?.remove();
            const item = buildRoomItem(room);
            list.prepend(item);
            animateIn(item);
            link = item.querySelector(".room-link");
        } else if (moveToTop) {
            list.prepend(link.parentElement);
        }
        applyIdentity(link, room);
        applyActivity(link, room);
        renderPresence();
        renderTitle();
        listChanged();
        return link;
    }

    function removeRoom(roomId) {
        const link = findLink(roomId);
        if (link) link.parentElement.remove();
        if (!list.querySelector(".room-link") && !list.querySelector(".room-list__empty")) {
            list.append(el("li", "room-list__empty", "No chats yet. Use New chat to message someone or start a group."));
        }
        renderTitle();
        listChanged();
    }

    // A new message (room_activity frame, or chat.js for the open room).
    function showMessage(roomId, message, { unread = null, moveToTop = true } = {}) {
        const link = findLink(roomId);
        if (!link) return false;
        link.querySelector(".room-link__preview").textContent = previewText(message.message, message.user === me);
        if (moveToTop) {
            setTime(link.querySelector(".room-link__time"), message.created_at);
            list.prepend(link.parentElement);
        }
        if (unread !== null && roomId !== currentRoom) setUnread(link, unread);
        listChanged();
        return true;
    }

    function onActivity(event) {
        if (event.room === currentRoom && findLink(event.room)) return; // the room socket handles it
        if (!showMessage(event.room, event.message, { unread: event.unread })) {
            // Missed the room_added frame (e.g. while reconnecting): fetch the row.
            fetchRoom(event.room);
        }
    }

    // Fetched rows: ignored if the room was removed after the fetch started.
    function acceptFetched(roomId, startedAt) {
        const removed = removedAt.get(roomId);
        if (removed !== undefined && removed > startedAt) return false;
        removedAt.delete(roomId);
        return true;
    }

    const pending = new Set();
    async function fetchRoom(roomId) {
        if (pending.has(roomId)) return;
        pending.add(roomId);
        const startedAt = seq;
        try {
            const response = await fetch(`/chat/rooms/${encodeURIComponent(roomId)}/summary/`, {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const room = await response.json();
            if (acceptFetched(room.id, startedAt)) upsertRoom(room, { moveToTop: true });
        } catch (error) {
            console.warn(`Relay: couldn't load the room list row for ${roomId}.`, error);
        } finally {
            pending.delete(roomId);
        }
    }

    // After a reconnect, frames may have been missed: fetch the whole list
    // and make the page match it.
    let resyncing = false;
    async function resync() {
        if (resyncing) return;
        resyncing = true;
        const startedAt = seq;
        try {
            const response = await fetch("/chat/rooms/summaries/", {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const { rooms } = await response.json();
            reconcile(rooms, startedAt);
        } catch (error) {
            console.warn("Relay: couldn't refresh the room list after reconnecting.", error);
        } finally {
            resyncing = false;
        }
    }

    function reconcile(rooms, startedAt) {
        const listed = new Set(rooms.map((room) => room.id));

        // Rooms you've left (unless added again since the fetch started).
        for (const link of [...list.querySelectorAll(".room-link")]) {
            const id = link.dataset.roomId;
            if (listed.has(id) || (addedAt.get(id) ?? -1) > startedAt) continue;
            removeRoom(id);
            if (id === currentRoom) {
                document.dispatchEvent(new CustomEvent("relay:room-gone", { detail: { room: id, deleted: false } }));
            }
        }

        // Add and refresh the rest, then order them like the server does.
        // A row that has had newer activity than the fetched list stays on top.
        const kept = rooms.filter((room) => acceptFetched(room.id, startedAt));
        const items = kept.map((room) => {
            const link = upsertRoom(room, { moveToTop: false });
            return { item: link.parentElement, fresher: (lastAt(link) ?? 0) > (Date.parse(room.last_at) || 0) };
        });
        const ordered = [
            ...items.filter((x) => x.fresher).sort((a, b) => lastAt(b.item.firstElementChild) - lastAt(a.item.firstElementChild)),
            ...items.filter((x) => !x.fresher),
        ];
        // Rows not in the fetched list (added since) stay above, in their order.
        const fetched = new Set(ordered.map((x) => x.item));
        const extras = [...list.children].filter((li) => li.querySelector(".room-link") && !fetched.has(li));
        const focused = list.contains(document.activeElement) ? document.activeElement : null;
        list.append(...extras, ...ordered.map((x) => x.item));
        if (focused && focused.isConnected && document.activeElement !== focused) focused.focus();
        listChanged();
    }

    // Connection with reconnect and a 30-second keepalive

    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    let attempts = 0;
    let pingTimer = null;
    let everConnected = false;

    function connect() {
        const socket = new WebSocket(`${scheme}://${window.location.host}/inbox/`);
        const ping = () => {
            if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ping" }));
        };
        socket.addEventListener("open", () => {
            if (everConnected) resync();
            everConnected = true;
            attempts = 0;
            clearInterval(pingTimer);
            pingTimer = setInterval(ping, 30000);
        });
        socket.addEventListener("message", (event) => {
            let data;
            try {
                data = JSON.parse(event.data);
            } catch (error) {
                console.warn("Relay: ignored an inbox frame that wasn't JSON.", error);
                return;
            }
            if (data.type === "presence_snapshot") {
                online.clear();
                data.online.forEach((u) => online.add(u));
                renderPresence();
            } else if (data.type === "presence") {
                if (data.online) online.add(data.user);
                else online.delete(data.user);
                renderPresence();
            } else if (data.type === "room_activity") {
                onActivity(data);
            } else if (data.type === "room_added") {
                seq += 1;
                addedAt.set(data.room.id, seq);
                removedAt.delete(data.room.id);
                upsertRoom(data.room, { moveToTop: true });
                // New room-mates: ask for a fresh presence snapshot.
                ping();
            } else if (data.type === "room_changed") {
                const link = findLink(data.room.id);
                if (link) {
                    applyIdentity(link, data.room);
                    listChanged();
                } else if (!removedAt.has(data.room.id)) {
                    fetchRoom(data.room.id);
                }
            } else if (data.type === "room_removed") {
                seq += 1;
                removedAt.set(data.room, seq);
                addedAt.delete(data.room);
                removeRoom(data.room);
            }
        });
        socket.addEventListener("close", (event) => {
            clearInterval(pingTimer);
            if (event.code === 4401) return;
            attempts += 1;
            setTimeout(connect, Math.min(30000, 1000 * 2 ** Math.min(attempts - 1, 5)));
        });
    }

    // Events from other modules

    document.addEventListener("relay:details-loaded", renderPresence);
    document.addEventListener("relay:room-removed", (event) => {
        seq += 1;
        removedAt.set(event.detail.room, seq);
        removeRoom(event.detail.room);
    });
    // chat.js: a message in, or an edit to the last message of, the open room.
    document.addEventListener("relay:room-message", (event) => {
        const { room, message, moveToTop } = event.detail;
        showMessage(room, message, { moveToTop });
    });
    // chat.js: the open room was renamed (room socket).
    document.addEventListener("relay:room-updated", (event) => {
        const link = currentRoom && findLink(currentRoom);
        if (link && event.detail.name && !link.dataset.username) {
            applyIdentity(link, { id: currentRoom, title: event.detail.name, initials: event.detail.initials });
            listChanged();
        }
    });
    // chat.js: the page now shows something else (e.g. the gone pane).
    document.addEventListener("relay:base-title", (event) => {
        baseTitle = event.detail.title;
        renderTitle();
    });

    for (const time of list.querySelectorAll(".room-link__time[datetime]")) {
        setTime(time, time.getAttribute("datetime"));
    }
    renderTitle();
    connect();
})();
