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
            // A room created by someone else since this page loaded.
            if (event.message.user !== me) showNewRoomNote();
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

    let noteShown = false;
    function showNewRoomNote() {
        if (noteShown) return;
        noteShown = true;
        const list = document.getElementById("room-list");
        const li = document.createElement("li");
        li.className = "room-list__new";
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn--ghost btn--sm";
        button.textContent = "New conversation · Refresh";
        button.addEventListener("click", () => window.location.reload());
        li.append(button);
        list.prepend(li);
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
    renderTitle();
    connect();
})();
