document.addEventListener("DOMContentLoaded", () => {
    const details = document.querySelector("[data-calendar-details]");
    const dayButtons = Array.from(document.querySelectorAll("[data-calendar-day]"));

    if (!details || dayButtons.length === 0) {
        return;
    }

    const title = details.querySelector("[data-calendar-details-title]");
    const empty = details.querySelector("[data-calendar-details-empty]");
    const list = details.querySelector("[data-calendar-details-list]");
    const selectedDate = details.querySelector("[data-calendar-selected-date]");
    const reservedFor = details.querySelector("[data-calendar-reserved-for]");
    const requestedBy = details.querySelector("[data-calendar-requested-by]");
    const blockedReason = details.querySelector("[data-calendar-blocked-reason]");
    const blockedBy = details.querySelector("[data-calendar-blocked-by]");
    const blockedReasonRow = details.querySelector("[data-calendar-blocked-reason-row]");
    const blockedByRow = details.querySelector("[data-calendar-blocked-by-row]");
    const dateRange = details.querySelector("[data-calendar-date-range]");
    const nightCount = details.querySelector("[data-calendar-night-count]");

    const selectDay = (dayButton) => {
        const isReservation = dayButton.dataset.detailType === "reservation";

        dayButtons.forEach((button) => {
            const isSelected = button === dayButton;
            button.classList.toggle("is-selected", isSelected);
            button.setAttribute("aria-pressed", String(isSelected));
        });

        title.textContent = isReservation
            ? `${dayButton.dataset.reservedFor} is booked`
            : `Blocked on ${dayButton.dataset.selectedDate}`;
        selectedDate.textContent = dayButton.dataset.selectedDate;
        reservedFor.textContent = dayButton.dataset.reservedFor;
        requestedBy.textContent = dayButton.dataset.requestedBy;
        blockedReason.textContent = dayButton.dataset.blockedReason;
        blockedBy.textContent = dayButton.dataset.blockedBy;
        dateRange.textContent = dayButton.dataset.dateRange;
        nightCount.textContent = dayButton.dataset.nightCount;
        reservedFor.closest("div").hidden = !isReservation;
        requestedBy.closest("div").hidden = !isReservation;
        blockedReasonRow.hidden = isReservation;
        blockedByRow.hidden = isReservation;
        empty.hidden = true;
        list.hidden = false;
    };

    dayButtons.forEach((dayButton) => {
        dayButton.setAttribute("aria-pressed", "false");
        dayButton.addEventListener("click", () => selectDay(dayButton));
        dayButton.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                selectDay(dayButton);
            }
        });
    });
});
