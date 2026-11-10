const copyInvitationButton = document.getElementById("copy-invitation-link");

if (copyInvitationButton) {
    copyInvitationButton.addEventListener("click", async () => {
        const input = document.getElementById("enrollment-url");
        const status = document.getElementById("copy-invitation-status");
        try {
            await navigator.clipboard.writeText(input.value);
            status.textContent = "Link copied. Paste it into your email or text message.";
        } catch {
            input.focus();
            input.select();
            status.textContent = "Select and copy the link above using your keyboard or copy menu.";
        }
    });
}
