document.addEventListener("DOMContentLoaded", () => {
    const menus = document.querySelectorAll("[data-menu]");

    menus.forEach((menu) => {
        const toggle = menu.querySelector("[data-menu-toggle]");
        const panel = menu.querySelector("[data-menu-panel]");

        if (!toggle || !panel) {
            return;
        }

        const setOpen = (isOpen) => {
            toggle.setAttribute("aria-expanded", String(isOpen));
            toggle.setAttribute(
                "aria-label",
                isOpen ? "Close navigation menu" : "Open navigation menu",
            );
            menu.classList.toggle("is-open", isOpen);
            panel.hidden = !isOpen;
        };

        toggle.addEventListener("click", () => {
            const isOpen = toggle.getAttribute("aria-expanded") === "true";
            setOpen(!isOpen);
        });

        panel.querySelectorAll("a").forEach((link) => {
            link.addEventListener("click", () => setOpen(false));
        });

        menu.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                setOpen(false);
                toggle.focus();
            }
        });

        document.addEventListener("click", (event) => {
            if (!menu.contains(event.target)) {
                setOpen(false);
            }
        });

        setOpen(false);
    });
});
