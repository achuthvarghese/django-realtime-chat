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
    let openRoom = readJSON("room-id"); // null once its gone pane shows
    let roomMembers = readJSON("room-members") || [];
    let baseTitle = document.title;
    const online = new Set();

    // Times and previews, the same way the server renders a row

    const timeFormat = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });
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

    function setUnread(link, n, { retitle = true } = {}) {
        link.dataset.unread = String(n);
        link.classList.toggle("room-link--unread", n > 0);
        const badge = link.querySelector(".room-link__unread");
        if (badge) {
            badge.hidden = n === 0;
            badge.querySelector("[data-unread-count]").textContent = n > 99 ? "99+" : String(n);
        }
        if (retitle) renderTitle();
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

    // Every live change gets a sequence number. A fetch remembers the number
    // when it started, so its (older) answer can't undo a later change:
    // a room removed or added since, or a row whose preview a live frame
    // updated since. Timestamps can't decide this, because a row's last
    // message can legitimately get older (deleted, history cleared).
    let seq = 0;
    const removedAt = new Map(); // room id -> seq of its latest removal
    const addedAt = new Map(); // room id -> seq of its latest room_added
    const touchedAt = new Map(); // room id -> seq of its latest live preview update
    const touch = (roomId) => {
        seq += 1;
        touchedAt.set(roomId, seq);
    };

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
        if (room.id === openRoom) link.setAttribute("aria-current", "page");

        const wrap = el("span", "room-link__avatar-wrap");
        const avatar = el("span", "avatar room-link__avatar" + (room.type === "group" ? " room-link__avatar--group" : ""));
        avatar.setAttribute("aria-hidden", "true");
        wrap.append(avatar);
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
        if (room.id === openRoom && Array.isArray(room.member_usernames)) {
            roomMembers = room.member_usernames;
        }
    }

    // Preview, time and unread from a full room object. `startedAt` is the
    // sequence number when a fetch began (null for a live frame): a row that
    // a live frame updated after that keeps what it shows.
    function applyActivity(link, room, startedAt) {
        if (startedAt !== null && (touchedAt.get(room.id) ?? -1) > startedAt) return false;
        link.querySelector(".room-link__preview").textContent = room.last_content
            ? previewText(room.last_content, room.last_is_mine)
            : "No messages yet";
        setTime(link.querySelector(".room-link__time"), room.last_at);
        if (room.id !== openRoom) setUnread(link, room.unread || 0, { retitle: false });
        return true;
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

    function render() {
        renderPresence();
        renderTitle();
        listChanged();
    }

    // Add or refresh a row from a full room object.
    function upsertRoom(room, { moveToTop, startedAt = null, rerender = true }) {
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
        applyActivity(link, room, startedAt);
        if (rerender) render();
        return link;
    }

    function removeRoom(roomId, { rerender = true } = {}) {
        const link = findLink(roomId);
        if (link) link.parentElement.remove();
        if (!list.querySelector(".room-link") && !list.querySelector(".room-list__empty")) {
            list.append(el("li", "room-list__empty", "No chats yet. Use New chat to message someone or start a group."));
        }
        if (rerender) {
            renderTitle();
            listChanged();
        }
    }

    // The open room is no longer in your list (room_removed frame, or missing
    // from a resync). Only the room socket knows whether you were removed or
    // the room was deleted, so chat.js checks it and shows the right pane.
    function openRoomMissing() {
        document.dispatchEvent(new CustomEvent("relay:room-check", { detail: { room: openRoom } }));
    }

    // A new message (room_activity frame, or chat.js for the open room).
    function showMessage(roomId, message, { unread = null, moveToTop = true } = {}) {
        const link = findLink(roomId);
        if (!link) return false;
        touch(roomId);
        link.querySelector(".room-link__preview").textContent = previewText(message.message, message.user === me);
        if (moveToTop) {
            setTime(link.querySelector(".room-link__time"), message.created_at);
            list.prepend(link.parentElement);
        }
        if (unread !== null && roomId !== openRoom) setUnread(link, unread);
        listChanged();
        return true;
    }

    function onActivity(event) {
        if (event.room === openRoom && findLink(event.room)) return; // the room socket handles it
        if (!showMessage(event.room, event.message, { unread: event.unread })) {
            // Missed the room_added frame (e.g. while reconnecting): fetch the row.
            fetchRoom(event.room, { activity: event });
        }
    }

    // Fetched rows: ignored if the room was removed after the fetch started.
    function acceptFetched(roomId, startedAt) {
        const removed = removedAt.get(roomId);
        if (removed !== undefined && removed > startedAt) return false;
        removedAt.delete(roomId);
        return true;
    }

    // One fetch per room at a time. A request while one is in flight is
    // remembered: the latest room_activity frame is applied once the row
    // exists, and a refresh request fetches once more afterwards (the
    // running fetch may predate the change).
    const pending = new Map(); // room id -> { activity, again }
    async function fetchRoom(roomId, { activity = null, moveToTop = true } = {}) {
        if (pending.has(roomId)) {
            const queued = pending.get(roomId);
            if (activity) queued.activity = activity;
            else queued.again = true;
            return;
        }
        pending.set(roomId, { activity: null, again: false });
        const startedAt = seq;
        try {
            const response = await fetch(`/chat/rooms/${encodeURIComponent(roomId)}/summary/`, {
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const room = await response.json();
            if (acceptFetched(room.id, startedAt)) {
                upsertRoom(room, { moveToTop: moveToTop || !findLink(room.id), startedAt });
                const later = pending.get(roomId).activity;
                if (later) showMessage(roomId, later.message, { unread: later.unread });
            }
        } catch (error) {
            console.warn(`Relay: couldn't load the room list row for ${roomId}.`, error);
        } finally {
            const again = pending.get(roomId).again;
            pending.delete(roomId);
            if (again) refreshRoom(roomId);
        }
    }

    // Refetch a row in place, e.g. after an edit, delete or cleared history
    // changed its preview (room_refresh frame, or chat.js for the open room).
    function refreshRoom(roomId) {
        if (!roomId || (removedAt.has(roomId) && !findLink(roomId))) return;
        fetchRoom(roomId, { moveToTop: false });
    }

    // Frames may have been missed while the inbox socket was down: fetch the
    // whole list and make the page match it. A call while one is running
    // queues one more run (the running fetch may predate what was missed).
    let resyncing = false;
    let resyncAgain = false;
    async function resync() {
        if (resyncing) {
            resyncAgain = true;
            return;
        }
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
            if (resyncAgain) {
                resyncAgain = false;
                resync();
            }
        }
    }

    function reconcile(rooms, startedAt) {
        const listed = new Set(rooms.map((room) => room.id));

        // Rooms you've left (unless added again since the fetch started).
        let openMissing = false;
        for (const link of [...list.querySelectorAll(".room-link")]) {
            const id = link.dataset.roomId;
            if (listed.has(id) || (addedAt.get(id) ?? -1) > startedAt) continue;
            removeRoom(id, { rerender: false });
            if (id === openRoom) openMissing = true;
        }

        // Add and refresh the rest, then order them like the server does.
        // Rows a live frame moved since the fetch started stay on top, in
        // their current order, as do rows added since (not in the list).
        const kept = rooms.filter((room) => acceptFetched(room.id, startedAt));
        const items = kept.map((room) => {
            const link = upsertRoom(room, { moveToTop: false, startedAt, rerender: false });
            return { item: link.parentElement, live: (touchedAt.get(room.id) ?? -1) > startedAt };
        });
        const fetched = new Set(items.filter((x) => !x.live).map((x) => x.item));
        const top = [...list.children].filter((li) => li.querySelector(".room-link") && !fetched.has(li));
        const focused = list.contains(document.activeElement) ? document.activeElement : null;
        list.append(...top, ...items.filter((x) => !x.live).map((x) => x.item));
        if (focused && focused.isConnected && document.activeElement !== focused) focused.focus();
        render();
        if (openMissing) openRoomMissing();
    }

    // Connection with reconnect and a 30-second keepalive

    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const RESYNC_GRACE_MS = 3000; // a first connect this soon after load has missed nothing
    let attempts = 0;
    let pingTimer = null;
    let reconnectTimer = null;
    let everConnected = false;
    let socket = null;

    const ping = () => {
        if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ping" }));
    };

    function connect() {
        socket = new WebSocket(`${scheme}://${window.location.host}/inbox/`);
        const current = socket;
        current.addEventListener("open", () => {
            // Resync on every open, except a first one right after the page
            // rendered (then the server-rendered list is current).
            if (everConnected || performance.now() > RESYNC_GRACE_MS) resync();
            everConnected = true;
            attempts = 0;
            clearInterval(pingTimer);
            pingTimer = setInterval(ping, 30000);
        });
        current.addEventListener("message", (event) => {
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
                touch(data.room.id);
                upsertRoom(data.room, { moveToTop: true });
                // New room-mates: ask for a fresh presence snapshot.
                ping();
            } else if (data.type === "room_changed") {
                const link = findLink(data.room.id);
                if (link) {
                    applyIdentity(link, data.room);
                    listChanged();
                    // Members joined or left: refresh presence (and "· N online").
                    if (Array.isArray(data.room.member_usernames)) {
                        renderPresence();
                        ping();
                    }
                } else if (!removedAt.has(data.room.id)) {
                    fetchRoom(data.room.id);
                }
            } else if (data.type === "room_refresh") {
                refreshRoom(typeof data.room === "string" ? data.room : data.room?.id);
            } else if (data.type === "room_removed") {
                seq += 1;
                removedAt.set(data.room, seq);
                addedAt.delete(data.room);
                removeRoom(data.room);
                if (data.room === openRoom) openRoomMissing();
            }
        });
        current.addEventListener("close", (event) => {
            clearInterval(pingTimer);
            if (event.code === 4401) return;
            attempts += 1;
            clearTimeout(reconnectTimer);
            reconnectTimer = setTimeout(connect, Math.min(30000, 1000 * 2 ** Math.min(attempts - 1, 5)));
        });
    }

    // Events from other modules

    document.addEventListener("relay:details-loaded", renderPresence);
    // chat.js: the open room went away (gone pane shown). It is no longer
    // the open room: if you're added back, its row behaves like any other.
    document.addEventListener("relay:room-removed", (event) => {
        const roomId = event.detail.room;
        seq += 1;
        removedAt.set(roomId, seq);
        removeRoom(roomId);
        if (roomId === openRoom) openRoom = null;
    });
    // chat.js: the room socket reconnected fine, so you're still a member.
    document.addEventListener("relay:room-still-here", (event) => {
        if (event.detail.room === openRoom && !findLink(openRoom)) fetchRoom(openRoom);
    });
    // chat.js: the open room's row needs the server's view (edit, delete, clear).
    document.addEventListener("relay:room-refresh", (event) => refreshRoom(event.detail.room));
    // chat.js: a message in, or an edit to the last message of, the open room.
    document.addEventListener("relay:room-message", (event) => {
        const { room, message, moveToTop } = event.detail;
        showMessage(room, message, { moveToTop });
    });
    // chat.js: the open room was renamed (room socket).
    document.addEventListener("relay:room-updated", (event) => {
        const link = openRoom && findLink(openRoom);
        if (link && event.detail.name && !link.dataset.username) {
            applyIdentity(link, { id: openRoom, title: event.detail.name, initials: event.detail.initials });
            listChanged();
        }
    });
    // chat.js: the page now shows something else (e.g. the gone pane).
    document.addEventListener("relay:base-title", (event) => {
        baseTitle = event.detail.title;
        renderTitle();
    });

    // Row times are relative to today: redo them at local midnight and when
    // the tab comes back (it may have slept past midnight).
    function refreshTimes() {
        for (const time of list.querySelectorAll(".room-link__time[datetime]")) {
            setTime(time, time.getAttribute("datetime"));
        }
    }
    let midnightTimer = null;
    function scheduleMidnight() {
        clearTimeout(midnightTimer);
        const now = new Date();
        const next = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 1);
        midnightTimer = setTimeout(() => {
            refreshTimes();
            scheduleMidnight();
        }, next - now);
    }
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState !== "visible") return;
        refreshTimes();
        scheduleMidnight();
    });

    refreshTimes();
    scheduleMidnight();
    renderTitle();
    connect();
})();
