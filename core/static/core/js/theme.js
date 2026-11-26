// Theme controls: palette, mode and density.
//
// The <html> element carries data-palette, data-mode and data-density.
// An inline script in core/base.html applies the device's saved choice
// before first paint; this file wires up the pickers and saves changes.

(() => {
    "use strict";

    const root = document.documentElement;
    const AXES = ["palette", "mode", "density"];
    const STORAGE_PREFIX = "relay.";

    function save(axis, value) {
        try {
            localStorage.setItem(STORAGE_PREFIX + axis, value);
        } catch (error) {
            // Storage can be unavailable (private mode); the choice still
            // applies for this page view.
        }
    }

    // Signed-in users: also save to the account so every device follows.
    async function saveToAccount(axis, value) {
        const url = root.dataset.themeSaveUrl;
        if (!url) return;
        const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
        try {
            const response = await fetch(url, {
                method: "POST",
                credentials: "same-origin",
                headers: { "X-CSRFToken": token, Accept: "application/json" },
                body: new URLSearchParams({ [axis]: value }),
            });
            if (!response.ok) throw new Error(String(response.status));
        } catch (error) {
            document.dispatchEvent(new CustomEvent("relay:theme-save-failed", { detail: { axis, value } }));
        }
    }

    function apply(axis, value) {
        root.dataset[axis] = value;
        save(axis, value);
        saveToAccount(axis, value);
        document.dispatchEvent(new CustomEvent("relay:theme", { detail: { axis, value } }));
    }

    // A control's axis comes from data-axis, else its name. data-axis lets a
    // picker inside a form use its own radio group name.
    const axisOf = (input) => input.dataset.axis || input.name;

    function syncControls(scope = document) {
        for (const input of scope.querySelectorAll("[data-theme-control] input[type=radio]")) {
            const axis = axisOf(input);
            if (AXES.includes(axis)) input.checked = input.value === root.dataset[axis];
        }
    }

    document.addEventListener("change", (event) => {
        const input = event.target;
        if (!(input instanceof HTMLInputElement)) return;
        if (!input.closest("[data-theme-control]")) return;
        const axis = axisOf(input);
        if (!AXES.includes(axis)) return;
        apply(axis, input.value);
        syncControls();
    });

    // Close an open popover menu (theme menu, account menu) on Escape or an
    // outside click.
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        for (const menu of document.querySelectorAll("details[data-popover][open]")) {
            menu.open = false;
            menu.querySelector("summary")?.focus();
        }
    });
    document.addEventListener("click", (event) => {
        for (const menu of document.querySelectorAll("details[data-popover][open]")) {
            if (!menu.contains(event.target)) menu.open = false;
        }
    });

    syncControls();
    window.relayTheme = { apply, syncControls };
})();
