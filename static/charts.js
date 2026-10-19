// Hover readouts for the dashboard charts and the year's squares. Listeners sit on the
// document, so they keep working after hx-boost swaps the page.
(() => {
    const tip = document.createElement("div");
    tip.className = "hover-tip";
    tip.setAttribute("aria-hidden", "true");
    tip.hidden = true;
    const rowsByChart = new WeakMap();
    let activeChart = null;

    function rows(wrap) {
        if (!rowsByChart.has(wrap)) rowsByChart.set(wrap, JSON.parse(wrap.dataset.hover || "[]"));
        return rowsByChart.get(wrap);
    }

    function show(event, lines) {
        tip.replaceChildren(
            ...lines.filter(Boolean).map((text, index) => {
                const line = document.createElement(index ? "span" : "strong");
                line.textContent = text;
                return line;
            }),
        );
        // hx-boost replaces the body's contents, so put the tip back if it was swapped out
        if (!tip.isConnected) document.body.append(tip);
        tip.hidden = false;
        const gap = 14;
        const { width, height } = tip.getBoundingClientRect();
        const left = event.clientX + gap + width > window.innerWidth ? event.clientX - gap - width : event.clientX + gap;
        tip.style.left = `${Math.max(4, left)}px`;
        tip.style.top = `${Math.max(4, event.clientY - height - gap)}px`;
    }

    function hideChart() {
        if (activeChart) activeChart.classList.remove("hovering");
        activeChart = null;
    }

    function showChart(wrap, event) {
        const data = rows(wrap);
        const svg = wrap.querySelector("svg");
        if (!data.length || !svg) return false;
        const box = svg.viewBox.baseVal;
        const rect = svg.getBoundingClientRect();
        const x = ((event.clientX - rect.left) / rect.width) * box.width;
        // Rows are in day order, so the nearest one is the first that's closer than the next
        let index = 0;
        while (index < data.length - 1 && Math.abs(data[index + 1][0] - x) <= Math.abs(data[index][0] - x)) index++;
        const [rowX, rowY, day, value, note] = data[index];

        if (activeChart !== wrap) hideChart();
        activeChart = wrap;
        wrap.classList.add("hovering");
        wrap.style.setProperty("--hover-x", `${(rowX / box.width) * 100}%`);
        wrap.style.setProperty("--hover-y", `${(rowY / box.height) * 100}%`);
        show(event, [day, value, note]);
        return true;
    }

    function track(event) {
        const target = event.target instanceof Element ? event.target : null;
        const wrap = target?.closest(".chart-wrap[data-hover]");
        if (wrap && showChart(wrap, event)) return;
        hideChart();
        const cell = target?.closest("[data-tip]");
        if (cell) {
            show(event, [cell.dataset.tip, cell.dataset.tipValue]);
        } else {
            tip.hidden = true;
        }
    }

    document.addEventListener("pointermove", track);
    // A tap on a touch screen shows the same readout
    document.addEventListener("pointerdown", track);
    document.documentElement.addEventListener("pointerleave", () => {
        hideChart();
        tip.hidden = true;
    });
})();
