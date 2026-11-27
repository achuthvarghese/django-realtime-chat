// Details panel: room info, members and group actions.
// The panel's HTML comes from /chat/rooms/<id>/details/. Its forms work
// without JavaScript; here they are submitted in place, after a confirmation
// where the form asks for one. Text from the server is inserted as text.

(() => {
    "use strict";

    const panel = document.getElementById("details");
    if (!panel) return;
    const shell = document.querySelector(".chat");
    const opener = document.querySelector("[data-details-open]");
    const confirmDialog = document.getElementById("confirm-dialog");
    const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || "";

    // Open, close, load

    async function load() {
        try {
            const response = await fetch(panel.dataset.detailsUrl, { credentials: "same-origin" });
            if (!response.ok) throw new Error(String(response.status));
            panel.innerHTML = await response.text(); // trusted, escaped server template
            wireAddPeople();
            document.dispatchEvent(new CustomEvent("relay:details-loaded"));
        } catch (error) {
            console.warn("Relay: couldn't load the Details panel.", error);
            const note = document.createElement("p");
            note.className = "details__loading muted";
            note.textContent = "Couldn't load details. Close and try again.";
            panel.replaceChildren(note);
        }
    }

    function open() {
        panel.hidden = false;
        shell.classList.add("chat--details-open");
        opener.setAttribute("aria-expanded", "true");
        load().then(() => panel.querySelector("[data-details-close]")?.focus());
    }

    function close() {
        panel.hidden = true;
        shell.classList.remove("chat--details-open");
        opener.setAttribute("aria-expanded", "false");
        opener.focus();
    }

    opener.addEventListener("click", () => (panel.hidden ? open() : close()));
    panel.addEventListener("click", (event) => {
        if (event.target.closest("[data-details-close]")) close();
    });
    // Escape closes the innermost thing only: an open menu or dialog first,
    // the panel on the next press. Capture phase, so this sees the menu
    // before theme.js closes it.
    document.addEventListener(
        "keydown",
        (event) => {
            if (event.key !== "Escape" || panel.hidden) return;
            if (document.querySelector("dialog[open], details[data-popover][open]")) return;
            close();
        },
        true
    );
    document.addEventListener("relay:room-updated", () => {
        if (!panel.hidden) load();
    });

    // Confirmation for destructive actions

    function confirmAction(form) {
        if (!form.dataset.confirmTitle || typeof confirmDialog.showModal !== "function") {
            return Promise.resolve(true);
        }
        document.getElementById("confirm-title").textContent = form.dataset.confirmTitle;
        document.getElementById("confirm-text").textContent = form.dataset.confirmBody || "";
        document.getElementById("confirm-ok").textContent = form.dataset.confirmButton || "Confirm";
        confirmDialog.returnValue = "";
        confirmDialog.showModal();
        return new Promise((resolve) => {
            confirmDialog.addEventListener("close", () => resolve(confirmDialog.returnValue === "ok"), { once: true });
        });
    }

    // Submit group actions in place

    panel.addEventListener("submit", async (event) => {
        const form = event.target.closest("form[data-group-action]");
        if (!form) return;
        event.preventDefault();
        if (!(await confirmAction(form))) return;
        const button = form.querySelector('button[type="submit"]');
        if (button) button.disabled = true;
        try {
            const response = await fetch(form.action, {
                method: "POST",
                credentials: "same-origin",
                headers: { Accept: "application/json", "X-CSRFToken": csrf() },
                body: new FormData(form),
            });
            let result;
            try {
                result = await response.json();
            } catch (error) {
                throw new Error(`HTTP ${response.status}, not JSON`);
            }
            if (!result.ok) {
                notify(result.error || "That didn't work. Try again.");
                if (button) button.disabled = false;
                return;
            }
            if (result.redirect) {
                window.location.assign(result.redirect);
                return;
            }
            await load();
        } catch (error) {
            console.warn("Relay: a group action failed.", error);
            if (button) button.disabled = false;
            notify("That didn't work. Check your connection and try again.");
        }
    });

    function notify(text) {
        let note = panel.querySelector(".details__error");
        if (!note) {
            note = document.createElement("p");
            note.className = "notice notice--error details__error";
            note.setAttribute("role", "alert");
            panel.querySelector(".details__head")?.after(note);
        }
        note.textContent = text;
    }

    // Add people: search, pick as chips, submit

    function wireAddPeople() {
        const form = panel.querySelector("#add-people");
        const toggle = panel.querySelector("[data-add-toggle]");
        if (!form || !toggle) return;
        const search = form.querySelector("[data-add-search]");
        const results = form.querySelector("[data-add-results]");
        const chips = form.querySelector("[data-add-chips]");
        const submit = form.querySelector("[data-add-submit]");
        const members = new Set([...panel.querySelectorAll(".member[data-username]")].map((m) => m.dataset.username));
        const picked = new Map();

        toggle.addEventListener("click", () => {
            form.hidden = !form.hidden;
            toggle.setAttribute("aria-expanded", String(!form.hidden));
            if (!form.hidden) search.focus();
        });

        function renderChips() {
            chips.replaceChildren(
                ...[...picked.values()].map((person) => {
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
                        picked.delete(person.username);
                        renderChips();
                    });
                    li.append(hidden, label, remove);
                    return li;
                })
            );
            submit.disabled = picked.size === 0;
        }

        let timer = null;
        search.addEventListener("input", () => {
            clearTimeout(timer);
            const query = search.value.trim();
            if (!query) return results.replaceChildren();
            timer = setTimeout(async () => {
                try {
                    const response = await fetch(`/chat/people/?q=${encodeURIComponent(query)}`, {
                        credentials: "same-origin",
                        headers: { Accept: "application/json" },
                    });
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                    const people = (await response.json()).results.filter((p) => !members.has(p.username));
                    if (!people.length) {
                        const li = document.createElement("li");
                        li.className = "people__note";
                        li.textContent = "No one else matches that.";
                        return results.replaceChildren(li);
                    }
                    results.replaceChildren(
                        ...people.map((person) => {
                            const li = document.createElement("li");
                            const button = document.createElement("button");
                            button.type = "button";
                            button.className = "person";
                            const avatar = document.createElement("span");
                            avatar.className = "avatar";
                            avatar.textContent = person.initials;
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
                            action.textContent = picked.has(person.username) ? "Added" : "Add";
                            button.append(avatar, text, action);
                            button.addEventListener("click", () => {
                                if (picked.has(person.username)) picked.delete(person.username);
                                else picked.set(person.username, person);
                                action.textContent = picked.has(person.username) ? "Added" : "Add";
                                renderChips();
                            });
                            li.append(button);
                            return li;
                        })
                    );
                } catch (error) {
                    console.warn("Relay: people search failed (add people).", error);
                    notify("Search isn't available right now.");
                }
            }, 200);
        });
    }
})();
