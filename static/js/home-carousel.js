document.addEventListener("DOMContentLoaded", () => {
    const carousels = document.querySelectorAll("[data-carousel]");

    carousels.forEach((carousel) => {
        const slides = Array.from(carousel.querySelectorAll("[data-carousel-slide]"));
        const indicators = Array.from(carousel.querySelectorAll("[data-carousel-indicator]"));
        const intervalMs = Number(carousel.dataset.carouselInterval || 5000);
        let currentIndex = slides.findIndex((slide) => slide.classList.contains("is-active"));
        let timerId = null;

        if (slides.length === 0) {
            return;
        }

        if (currentIndex < 0) {
            currentIndex = 0;
        }

        const render = (index) => {
            currentIndex = (index + slides.length) % slides.length;

            slides.forEach((slide, slideIndex) => {
                const isActive = slideIndex === currentIndex;
                slide.classList.toggle("is-active", isActive);
                slide.hidden = !isActive;
                slide.setAttribute("aria-hidden", String(!isActive));
            });

            indicators.forEach((indicator, indicatorIndex) => {
                const isActive = indicatorIndex === currentIndex;
                indicator.classList.toggle("is-active", isActive);
                indicator.setAttribute("aria-current", String(isActive));
            });
        };

        const stop = () => {
            if (timerId !== null) {
                window.clearInterval(timerId);
                timerId = null;
            }
        };

        const start = () => {
            stop();
            if (slides.length < 2) return;
            timerId = window.setInterval(() => render(currentIndex + 1), intervalMs);
        };

        indicators.forEach((indicator) => {
            indicator.addEventListener("click", () => {
                render(Number(indicator.dataset.slideTo));
                start();
            });
        });

        carousel.addEventListener("mouseenter", stop);
        carousel.addEventListener("mouseleave", start);
        carousel.addEventListener("focusin", stop);
        carousel.addEventListener("focusout", start);
        carousel.addEventListener("keydown", (event) => {
            if (event.key === "ArrowLeft") {
                render(currentIndex - 1);
                start();
            }
            if (event.key === "ArrowRight") {
                render(currentIndex + 1);
                start();
            }
        });

        render(currentIndex);
        start();
    });
});
