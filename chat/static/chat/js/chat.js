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

    // Dates

    const timeFormat = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" });
    const fullFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "full", timeStyle: "short" });
    const dayFormat = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "short", day: "numeric" });
    const shortDateFormat = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });

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

    // Room list: local times and search

    for (const time of document.querySelectorAll("time[data-relative]")) {
        const date = new Date(time.getAttribute("datetime"));
        if (Number.isNaN(date.getTime())) continue;
        const ago = daysAgo(date);
        time.textContent = ago === 0 ? timeFormat.format(date) : ago === 1 ? "Yesterday" : shortDateFormat.format(date);
        time.title = fullFormat.format(date);
    }

    const search = document.getElementById("room-search");
    if (search) {
        const noMatch = document.getElementById("room-nomatch");
        search.addEventListener("input", () => {
            const query = search.value.trim().toLowerCase();
            let shown = 0;
            for (const link of document.querySelectorAll("#room-list .room-link")) {
                const match = link.dataset.title.includes(query);
                link.parentElement.hidden = !match;
                if (match) shown += 1;
            }
            noMatch.hidden = shown > 0;
        });
    }

    const roomId = readJSON("room-id");
    if (!roomId) return;

    // Transcript

    const transcript = document.getElementById("messages");
    const scroller = document.getElementById("chat-scroll");
    const emptyNote = document.getElementById("chat-empty");
    let last = null; // { user, date } of the last rendered message

    const nearBottom = () => scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 120;
    const scrollToEnd = () => { scroller.scrollTop = scroller.scrollHeight; };

    function renderMessage(data) {
        const date = new Date(data.created_at);
        const mine = data.user === me;

        if (!last || dayKey(last.date) !== dayKey(date)) {
            const day = document.createElement("span");
            day.className = "transcript__day";
            day.textContent = dayLabel(date);
            transcript.append(day);
            last = null;
        }
        const continues = last && last.user === data.user && date - last.date < GROUP_GAP_MS;

        const row = document.createElement("div");
        row.className = "msg" + (continues ? " msg--cont" : "") + (mine ? " msg--mine" : "");
        row.dataset.id = data.id;

        const time = document.createElement("time");
        time.className = "msg__time";
        time.dateTime = data.created_at;
        time.title = fullFormat.format(date);
        time.textContent = timeFormat.format(date);
        row.append(time);

        const node = document.createElement("span");
        if (!continues) {
            node.className = "msg__node avatar" + (mine ? " avatar--mine" : "");
            node.textContent = data.initials || "?";
            node.setAttribute("aria-hidden", "true");
        }
        row.append(node);

        const body = document.createElement("div");
        body.className = "msg__body";
        if (!continues) {
            const name = document.createElement("span");
            name.className = "msg__name";
            name.textContent = mine ? "You" : data.name || data.user;
            const inlineTime = document.createElement("span");
            inlineTime.className = "msg__inline-time";
            inlineTime.textContent = timeFormat.format(date);
            body.append(name, inlineTime);
        } else {
            // Screen readers still hear who spoke.
            const who = document.createElement("span");
            who.className = "visually-hidden";
            who.textContent = (mine ? "You" : data.name || data.user) + ": ";
            body.append(who);
        }
        body.append(document.createTextNode(data.message));
        row.append(body);

        transcript.append(row);
        last = { user: data.user, date };
        emptyNote.hidden = true;
    }

    const initial = readJSON("initial-messages") || [];
    initial.forEach(renderMessage);
    emptyNote.hidden = initial.length > 0;
    scrollToEnd();

    function updatePreview(data) {
        const link = document.querySelector(`.room-link[data-room-id="${CSS.escape(roomId)}"]`);
        if (!link) return;
        const preview = link.querySelector(".room-link__preview");
        if (preview) preview.textContent = (data.user === me ? "You: " : "") + data.message;
        const time = link.querySelector(".room-link__time");
        if (time) time.textContent = timeFormat.format(new Date(data.created_at));
        const item = link.parentElement;
        item.parentElement.prepend(item);
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

    function connect() {
        setStatus(attempts === 0 && !everConnected ? "connecting" : "offline");
        socket = new WebSocket(socketUrl);

        socket.addEventListener("open", () => {
            if (everConnected) {
                showToast("Reconnected. Messages sent while you were away may be missing.", {
                    persist: true,
                    action: { label: "Reload", run: () => window.location.reload() },
                });
            }
            everConnected = true;
            attempts = 0;
            setStatus("live");
        });

        socket.addEventListener("message", (event) => {
            let data;
            try {
                data = JSON.parse(event.data);
            } catch (error) {
                return;
            }
            if (data.type === "save_message") {
                const stick = nearBottom() || data.user === me;
                renderMessage(data);
                updatePreview(data);
                if (stick) scrollToEnd();
            } else if (data.type === "clear_room" && data.for === me) {
                transcript.replaceChildren();
                last = null;
                emptyNote.hidden = false;
                showToast("History cleared for you.");
            } else if (data.type === "error") {
                showToast(data.message);
            }
        });

        socket.addEventListener("close", (event) => {
            // 4401 signed out, 4403 not a member, 4404 unknown room
            if (event.code === 4401) return window.location.assign("/account/login/");
            if (event.code === 4403 || event.code === 4404) return window.location.assign("/chat/");
            setStatus("offline");
            attempts += 1;
            const delay = Math.min(15000, 1000 * 2 ** Math.min(attempts - 1, 4));
            setTimeout(connect, delay);
        });
    }
    connect();

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

    composer.addEventListener("submit", (event) => {
        event.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        if (send({ type: "save_message", message: text })) {
            input.value = "";
            autosize();
        }
        input.focus();
    });

    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            composer.requestSubmit();
        }
    });

    // Clear history, after confirmation

    const clearButton = document.getElementById("clear-room");
    const dialog = document.getElementById("clear-dialog");
    clearButton.addEventListener("click", () => {
        if (typeof dialog.showModal === "function") {
            dialog.returnValue = "";
            dialog.showModal();
        }
    });
    dialog.addEventListener("close", () => {
        if (dialog.returnValue === "clear") send({ type: "clear_room" });
        clearButton.focus();
    });

    if (window.matchMedia("(min-width: 600px)").matches) input.focus();
})();
