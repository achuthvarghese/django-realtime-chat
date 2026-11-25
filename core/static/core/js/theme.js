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

    function apply(axis, value) {
        root.dataset[axis] = value;
        save(axis, value);
        document.dispatchEvent(new CustomEvent("relay:theme", { detail: { axis, value } }));
    }

    function syncControls(scope = document) {
        for (const axis of AXES) {
            for (const input of scope.querySelectorAll(`[data-theme-control] input[name="${axis}"]`)) {
                input.checked = input.value === root.dataset[axis];
            }
        }
    }

    document.addEventListener("change", (event) => {
        const input = event.target;
        if (!(input instanceof HTMLInputElement)) return;
        if (!input.closest("[data-theme-control]")) return;
        if (!AXES.includes(input.name)) return;
        apply(input.name, input.value);
        syncControls();
    });

    // Close an open theme menu on Escape or an outside click.
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        for (const menu of document.querySelectorAll("details.theme-menu[open]")) {
            menu.open = false;
            menu.querySelector("summary")?.focus();
        }
    });
    document.addEventListener("click", (event) => {
        for (const menu of document.querySelectorAll("details.theme-menu[open]")) {
            if (!menu.contains(event.target)) menu.open = false;
        }
    });

    syncControls();
    window.relayTheme = { apply, syncControls };
})();
