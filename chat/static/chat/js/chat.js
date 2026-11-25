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

    function actionsFor(data) {
        const bar = document.createElement("span");
        bar.className = "msg__actions";
        for (const [action, label] of [["edit", "Edit"], ["delete", "Delete"]]) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "msg__action";
            button.dataset.action = action;
            button.textContent = label;
            button.setAttribute("aria-label", `${label} message`);
            bar.append(button);
        }
        return bar;
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
        const continues = prev && prev.user === data.user && date - prevDate < GROUP_GAP_MS;

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
        const text = document.createElement("span");
        text.className = "msg__text";
        fillText(text, data);
        body.append(text);
        if (mine && !data.deleted) body.append(actionsFor(data));

        row.append(time, node, body);
        nodes.push(row);
        return nodes;
    }

    function renderAll() {
        const nodes = [];
        messages.forEach((data, i) => nodes.push(...buildRow(data, messages[i - 1] || null)));
        transcript.replaceChildren(...nodes);
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
        fillText(row.querySelector(".msg__text"), data);
        row.querySelector(".msg__actions")?.remove();
        row.querySelector(".msg__edit")?.remove();
        if (data.user === me && !data.deleted) row.querySelector(".msg__body").append(actionsFor(data));
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

    async function loadOlder() {
        if (loadingOlder || !hasMore || !messages.length) return;
        loadingOlder = true;
        updateHistoryStatus();
        const before = messages[0].id;
        try {
            const url = `/chat/rooms/${encodeURIComponent(roomId)}/messages/?before=${encodeURIComponent(before)}&limit=${historyMeta.page_size}`;
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
        } catch (error) {
            loadingOlder = false;
            updateHistoryStatus();
            showToast("Couldn't load earlier messages. Scroll up to try again.");
        }
    }

    scroller.addEventListener("scroll", () => {
        if (scroller.scrollTop < 80) loadOlder();
    });

    renderAll();
    scrollToEnd();
    // If the first page doesn't fill the pane there is nothing to scroll; load more.
    (async () => {
        while (hasMore && scroller.scrollHeight <= scroller.clientHeight) {
            await loadOlder();
            if (loadingOlder) break;
        }
        scrollToEnd();
    })();

    function updatePreview(data, moveToTop = true) {
        const link = document.querySelector(`.room-link[data-room-id="${CSS.escape(roomId)}"]`);
        if (!link) return;
        const preview = link.querySelector(".room-link__preview");
        if (preview) preview.textContent = (data.user === me ? "You: " : "") + data.message;
        const time = link.querySelector(".room-link__time");
        if (time && moveToTop) time.textContent = timeFormat.format(new Date(data.created_at));
        if (!moveToTop) return;
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
                appendMessage(data);
                updatePreview(data);
                if (stick) scrollToEnd();
            } else if (data.type === "message_updated") {
                updateMessage(data);
                if (messages.length && messages[messages.length - 1].id === data.id) {
                    updatePreview({ ...data, message: data.deleted ? "Message deleted" : data.message }, false);
                }
            } else if (data.type === "clear_room" && data.for === me) {
                messages.length = 0;
                hasMore = false;
                renderAll();
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
    transcript.addEventListener("click", (event) => {
        const button = event.target.closest(".msg__action");
        if (!button) return;
        const row = button.closest(".msg");
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
        const lastMine = [...messages].reverse().find((m) => m.user === me && !m.deleted);
        if (!lastMine) return;
        const row = transcript.querySelector(`.msg[data-id="${CSS.escape(lastMine.id)}"]`);
        if (!row) return;
        event.preventDefault();
        row.scrollIntoView({ block: "nearest" });
        startEdit(row);
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
