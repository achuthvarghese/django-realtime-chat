// New chat dialog: search people, start a direct chat, or build a group.
// Results are inserted as text only.

(() => {
    "use strict";

    const dialog = document.getElementById("new-chat");
    if (!dialog) return;

    const peopleUrl = "/chat/people/";
    const directForm = document.getElementById("direct-form");
    const directUsername = document.getElementById("direct-username");
    const groupForm = document.getElementById("group-form");
    const groupCreate = document.getElementById("group-create");
    const groupName = document.getElementById("group-name");
    const chips = document.getElementById("group-members");
    const selected = new Map(); // username -> person

    // Open, close, tabs

    for (const opener of document.querySelectorAll("[data-open-new-chat]")) {
        opener.addEventListener("click", () => {
            dialog.showModal();
            dialog.querySelector("#direct-q").focus();
        });
    }

    for (const tab of dialog.querySelectorAll("input[data-tab]")) {
        tab.addEventListener("change", () => {
            for (const other of dialog.querySelectorAll("input[data-tab]")) {
                document.getElementById(other.dataset.tab).hidden = !other.checked;
            }
            const panel = document.getElementById(tab.dataset.tab);
            panel.querySelector("input:not([type=hidden])")?.focus();
        });
    }

    // Search

    function avatar(person) {
        const span = document.createElement("span");
        span.className = "avatar avatar--lg";
        span.textContent = person.initials;
        span.setAttribute("aria-hidden", "true");
        return span;
    }

    function personButton(person, label) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "person";
        const text = document.createElement("span");
        text.className = "person__text";
        const name = document.createElement("span");
        name.className = "person__name";
        name.textContent = person.name;
        const handle = document.createElement("span");
        handle.className = "person__handle";
        handle.textContent = "@" + person.username;
        text.append(name, handle);
        const action = document.createElement("span");
        action.className = "person__action";
        action.textContent = label;
        button.append(avatar(person), text, action);
        return button;
    }

    function showMessage(list, text) {
        const li = document.createElement("li");
        li.className = "people__note";
        li.textContent = text;
        list.replaceChildren(li);
    }

    async function search(query) {
        const response = await fetch(`${peopleUrl}?q=${encodeURIComponent(query)}`, {
            headers: { Accept: "application/json" },
            credentials: "same-origin",
        });
        if (!response.ok) throw new Error(String(response.status));
        return (await response.json()).results;
    }

    function wireSearch(input, list, onPick, label) {
        let timer = null;
        let latest = 0;
        input.addEventListener("input", () => {
            clearTimeout(timer);
            const query = input.value.trim();
            if (!query) {
                list.replaceChildren();
                return;
            }
            timer = setTimeout(async () => {
                const ticket = ++latest;
                try {
                    const results = await search(query);
                    if (ticket !== latest) return;
                    if (!results.length) return showMessage(list, "No one matches that.");
                    list.replaceChildren(
                        ...results.map((person) => {
                            const li = document.createElement("li");
                            const button = personButton(person, label(person));
                            button.addEventListener("click", () => onPick(person, button));
                            li.append(button);
                            return li;
                        })
                    );
                } catch (error) {
                    console.warn("Relay: people search failed (new chat).", error);
                    showMessage(list, "Search isn't available right now. Try again.");
                }
            }, 200);
        });
    }

    // Direct: pick a person and go

    wireSearch(
        document.getElementById("direct-q"),
        document.getElementById("direct-results"),
        (person) => {
            directUsername.value = person.username;
            directForm.submit();
        },
        () => "Message"
    );

    // Group: collect people as chips

    function refreshGroup() {
        groupCreate.disabled = selected.size === 0 || groupName.value.trim() === "";
    }

    function renderChips() {
        chips.replaceChildren(
            ...[...selected.values()].map((person) => {
                const li = document.createElement("li");
                li.className = "chip";
                const hidden = document.createElement("input");
                hidden.type = "hidden";
                hidden.name = "members";
                hidden.value = person.username;
                const label = document.createElement("span");
                label.textContent = person.name;
                const remove = document.createElement("button");
                remove.type = "button";
                remove.className = "chip__remove";
                remove.setAttribute("aria-label", `Remove ${person.name}`);
                remove.textContent = "×";
                remove.addEventListener("click", () => {
                    selected.delete(person.username);
                    renderChips();
                });
                li.append(hidden, label, remove);
                return li;
            })
        );
        refreshGroup();
    }

    const groupQuery = document.getElementById("group-q");
    wireSearch(
        groupQuery,
        document.getElementById("group-results"),
        (person, button) => {
            if (selected.has(person.username)) {
                selected.delete(person.username);
            } else {
                selected.set(person.username, person);
            }
            button.querySelector(".person__action").textContent = selected.has(person.username) ? "Added" : "Add";
            renderChips();
        },
        (person) => (selected.has(person.username) ? "Added" : "Add")
    );
    groupName.addEventListener("input", refreshGroup);
    groupForm.addEventListener("submit", (event) => {
        if (groupCreate.disabled) event.preventDefault();
    });
})();
