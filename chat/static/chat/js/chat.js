// Chat script

(() => {
    "use strict";

    const user = JSON.parse(document.getElementById("user").textContent);
    const roomId = new URL(window.location.href).searchParams.get("room") || "";

    const left = document.getElementById("left");
    const right = document.getElementById("right");
    const chatRoom = document.getElementById("chat-room");
    const commonCard = document.getElementById("common-card");
    const messagesBox = document.getElementById("messages");

    const dateFormatter = new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
    });
    const formatDate = (value) => {
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? "" : dateFormatter.format(date);
    };

    setupRoomSearch();

    if (roomId === "") {
        left.classList.add("d-lg-block");
        right.classList.add("d-lg-block", "d-none");
        chatRoom.classList.add("d-none");
        commonCard.classList.add("d-flex");
        return;
    }

    left.classList.add("d-none", "d-lg-block");
    right.classList.add("d-block");
    commonCard.classList.add("d-none");

    // Mark the current room in the list, if it is there.
    const activeRoomLink = document.getElementById(`room_${roomId}`);
    if (activeRoomLink) {
        activeRoomLink.classList.add("active");
        activeRoomLink.setAttribute("aria-current", "true");
    }

    // Convert server datetimes to the viewer's locale.
    for (const element of document.querySelectorAll(".date[data-date]")) {
        element.textContent = formatDate(element.dataset.date);
    }
    scrollToLatest();

    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${scheme}://${window.location.host}/chat/${encodeURIComponent(roomId)}`);

    function sendMessage(data) {
        if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(data));
        }
    }

    ws.onclose = (event) => {
        // 4401 unauthenticated, 4403 not a member, 4404 unknown room
        if (event.code === 4401) {
            window.location.assign("/account/login/");
        } else if (event.code === 4403 || event.code === 4404) {
            window.location.assign("/chat/");
        }
    };

    ws.onmessage = (event) => {
        let data;
        try {
            data = JSON.parse(event.data);
        } catch (error) {
            return;
        }

        switch (data.type) {
            case "save_message":
                appendMessage(data);
                break;
            case "clear_room":
                clearMessages(data);
                break;
            case "error":
                console.warn("Chat error:", data.message);
                break;
            default:
                break;
        }
        scrollToLatest();
    };

    // Send message
    const messageInput = document.getElementById("message");
    const sendButton = document.getElementById("send-message-btn");

    function submitMessage() {
        const text = messageInput.value.trim();
        if (text === "") {
            messageInput.classList.add("border-danger");
            return;
        }
        messageInput.classList.remove("border-danger");
        sendMessage({ type: "save_message", message: text, ts: new Date().toISOString() });
        messageInput.value = "";
    }

    sendButton.addEventListener("click", submitMessage);
    messageInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            submitMessage();
        }
    });

    // Clear chat history (for this user only)
    const clearButton = document.getElementById("clear-room");
    if (clearButton) {
        clearButton.addEventListener("click", () => {
            sendMessage({ type: "clear_room", ts: new Date().toISOString() });
        });
    }

    function scrollToLatest() {
        messagesBox.scrollTop = messagesBox.scrollHeight;
    }

    // Build a message node with text only; never inject HTML from the server.
    function appendMessage(data) {
        const side = user === data.user ? "right" : "left";
        const node = document.createElement("div");
        node.className = `message message-${side} border rounded mb-1 p-1`;

        node.append(document.createTextNode(data.message), document.createElement("br"));
        const meta = document.createElement("span");
        meta.className = "text-muted fw-lighter";
        meta.textContent = `by ${data.user} on ${formatDate(data.created_at)}`;
        node.append(meta);

        messagesBox.appendChild(node);
    }

    function clearMessages(data) {
        if (user === data.for) {
            messagesBox.replaceChildren();
        }
    }

    // Filter the room list by name (case-insensitive).
    function setupRoomSearch() {
        const searchInput = document.getElementById("search-room-input");
        const searchButton = document.getElementById("search-room-btn");
        if (!searchInput || !searchButton) {
            return;
        }

        const filterRooms = () => {
            const query = searchInput.value.trim().toLowerCase();
            for (const element of document.getElementsByClassName("room")) {
                const name = element.children[0].textContent.trim().toLowerCase();
                element.style.display = name.includes(query) ? "" : "none";
            }
        };
        searchInput.addEventListener("input", filterRooms);
        searchButton.addEventListener("click", filterRooms);
    }
})();
