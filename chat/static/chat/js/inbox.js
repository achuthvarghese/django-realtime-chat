// Inbox socket: presence for people you share rooms with, and new activity
// in rooms other than the one you have open (preview, order, unread badge).

(() => {
    "use strict";

    const readJSON = (id) => {
        const element = document.getElementById(id);
        return element ? JSON.parse(element.textContent) : null;
    };
    const me = readJSON("me");
    const currentRoom = readJSON("room-id");
    const roomMembers = readJSON("room-members") || [];
    const baseTitle = document.title;
    const online = new Set();
    const timeFormat = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });

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

    function onActivity(event) {
        const link = document.querySelector(`.room-link[data-room-id="${CSS.escape(event.room)}"]`);
        if (!link) {
            // Missed the room_added frame (e.g. while reconnecting): fetch the row.
            fetchRoom(event.room);
            return;
        }
        if (event.room === currentRoom) return; // the room socket handles it
        const message = event.message;
        const preview = link.querySelector(".room-link__preview");
        if (preview) preview.textContent = (message.user === me ? "You: " : "") + message.message;
        const time = link.querySelector(".room-link__time");
        if (time) time.textContent = timeFormat.format(new Date(message.created_at));
        setUnread(link, event.unread);
        const item = link.parentElement;
        item.parentElement.prepend(item);
    }

    // Live room list: rooms appear, change and disappear without a reload.

    const list = document.getElementById("room-list");

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

    function fillRoomItem(link, room) {
        link.dataset.title = room.title.toLowerCase();
        link.title = room.title;
        link.querySelector(".room-link__avatar").textContent = room.initials;
        link.querySelector(".room-link__title").textContent = room.title;
        link.querySelector(".room-link__preview").textContent = room.last_content
            ? (room.last_is_mine ? "You: " : "") + room.last_content
            : "No messages yet";
        const time = link.querySelector(".room-link__time");
        time.textContent = room.last_at ? timeFormat.format(new Date(room.last_at)) : "";
        if (room.id !== currentRoom) setUnread(link, room.unread);
    }

    function upsertRoom(room, { moveToTop }) {
        let link = list.querySelector(`.room-link[data-room-id="${CSS.escape(room.id)}"]`);
        if (!link) {
            list.querySelector(".room-list__empty")?.remove();
            const item = buildRoomItem(room);
            item.classList.add("room-list__new");
            list.prepend(item);
            link = item.querySelector(".room-link");
        } else if (moveToTop) {
            list.prepend(link.parentElement);
        }
        fillRoomItem(link, room);
        renderPresence();
        renderTitle();
    }

    function removeRoom(roomId) {
        list.querySelector(`.room-link[data-room-id="${CSS.escape(roomId)}"]`)?.parentElement.remove();
        if (!list.querySelector(".room-link") && !list.querySelector(".room-list__empty")) {
            list.append(el("li", "room-list__empty", "No chats yet. Use New chat to message someone or start a group."));
        }
        renderTitle();
    }

    const pending = new Set();
    async function fetchRoom(roomId) {
        if (pending.has(roomId)) return;
        pending.add(roomId);
        try {
            const response = await fetch(`/chat/rooms/${encodeURIComponent(roomId)}/summary/`, { credentials: "same-origin" });
            if (response.ok) upsertRoom(await response.json(), { moveToTop: true });
        } finally {
            pending.delete(roomId);
        }
    }

    // Connection with reconnect and a 30-second keepalive

    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    let attempts = 0;
    let pingTimer = null;

    function connect() {
        const socket = new WebSocket(`${scheme}://${window.location.host}/inbox/`);
        socket.addEventListener("open", () => {
            attempts = 0;
            clearInterval(pingTimer);
            pingTimer = setInterval(() => {
                if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ping" }));
            }, 30000);
        });
        socket.addEventListener("message", (event) => {
            let data;
            try {
                data = JSON.parse(event.data);
            } catch (error) {
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
                upsertRoom(data.room, { moveToTop: true });
            } else if (data.type === "room_changed") {
                upsertRoom(data.room, { moveToTop: false });
            } else if (data.type === "room_removed") {
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

    document.addEventListener("relay:details-loaded", renderPresence);
    document.addEventListener("relay:room-removed", (event) => removeRoom(event.detail.room));
    renderTitle();
    connect();
})();
