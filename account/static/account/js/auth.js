// Login and signup helpers: show/hide password, and fill signup spine nodes
// as each group of fields is completed.

(() => {
    "use strict";

    for (const toggle of document.querySelectorAll("[data-password-toggle]")) {
        const input = document.getElementById(toggle.getAttribute("aria-controls"));
        if (!input) continue;
        toggle.addEventListener("click", () => {
            const show = input.type === "password";
            input.type = show ? "text" : "password";
            toggle.textContent = show ? "Hide" : "Show";
            toggle.setAttribute("aria-pressed", String(show));
            input.focus();
        });
    }

    const steps = document.querySelectorAll(".form-spine [data-step]");
    function refresh(step) {
        const inputs = [...step.querySelectorAll("input")];
        step.classList.toggle("has-error", inputs.some((i) => i.getAttribute("aria-invalid") === "true"));
        step.classList.toggle("is-done", inputs.length > 0 && inputs.every((i) => i.value.trim() !== "" && i.checkValidity()));
    }
    for (const step of steps) {
        refresh(step);
        step.addEventListener("input", (event) => {
            event.target.removeAttribute("aria-invalid");
            refresh(step);
        });
    }
})();
