// Drag-and-drop for the Arrange page: goals move within and between groups, groups move among
// themselves. The form posts its hidden inputs in document order, so moving an element is all it
// takes. Pointer events cover mouse and touch; the arrow buttons do the same from the keyboard,
// and post the move to the server instead when this script isn't running.
// The Arrange page loads this from its body, so hx-boost runs it on every visit; the listeners sit on
// the document, so they only need adding once.
(() => {
    if (window.arrangeReady) return;
    window.arrangeReady = true;
    const EDGE = 60;
    let drag = null;

    function markUnsaved(item) {
        const form = item.closest("form");
        const note = form?.querySelector(".unsaved");
        if (note) note.hidden = false;
    }

    function placeNear(item, other, y) {
        const box = other.getBoundingClientRect();
        if (y < box.top + box.height / 2) {
            if (other.previousElementSibling !== item) other.before(item);
        } else if (other.nextElementSibling !== item) {
            other.after(item);
        }
    }

    function moveTo(x, y) {
        const { item, kind } = drag;
        const target = document.elementFromPoint(x, y);
        if (!target || item.contains(target)) return;
        const other = target.closest(`[data-sortable-item="${kind}"]`);
        if (other && other.parentElement === item.parentElement) {
            placeNear(item, other, y);
        } else if (kind === "goal") {
            // Over another group: next to the goal under the pointer, or at the end of an empty list
            const list = target.closest(".arrange-group")?.querySelector(".arrange-list");
            if (other?.dataset.sortableItem === "goal") placeNear(item, other, y);
            else if (list && item.parentElement !== list) list.append(item);
        }
    }

    function step(item, direction) {
        const sibling = direction < 0 ? item.previousElementSibling : item.nextElementSibling;
        if (sibling) {
            if (direction < 0) sibling.before(item);
            else sibling.after(item);
        } else if (item.dataset.sortableItem === "goal") {
            // Past the end of a group: into the neighbouring one
            const lists = [...document.querySelectorAll(".arrange-list")];
            const next = lists[lists.indexOf(item.parentElement) + direction];
            if (!next) return;
            if (direction < 0) next.append(item);
            else next.prepend(item);
        } else {
            return;
        }
        markUnsaved(item);
        item.querySelector(`[data-move="${direction < 0 ? "up" : "down"}"]`)?.focus();
    }

    document.addEventListener("pointerdown", (event) => {
        const handle = event.target instanceof Element ? event.target.closest(".drag-handle") : null;
        if (!handle || event.button > 0) return;
        const item = handle.closest("[data-sortable-item]");
        if (!item) return;
        event.preventDefault();
        handle.setPointerCapture(event.pointerId);
        drag = { item, kind: item.dataset.sortableItem, handle, moved: false };
        item.classList.add("dragging");
    });

    document.addEventListener("pointermove", (event) => {
        if (!drag) return;
        drag.moved = true;
        moveTo(event.clientX, event.clientY);
        if (event.clientY < EDGE) window.scrollBy(0, -12);
        else if (event.clientY > window.innerHeight - EDGE) window.scrollBy(0, 12);
    });

    function drop() {
        if (!drag) return;
        drag.item.classList.remove("dragging");
        if (drag.moved) markUnsaved(drag.item);
        drag = null;
    }

    document.addEventListener("pointerup", drop);
    document.addEventListener("pointercancel", drop);

    document.addEventListener("click", (event) => {
        const button = event.target instanceof Element ? event.target.closest("[data-move]") : null;
        const item = button?.closest("[data-sortable-item]");
        if (!item) return;
        // Move it here instead of submitting the form
        event.preventDefault();
        step(item, button.dataset.move === "up" ? -1 : 1);
    });

    document.addEventListener("input", (event) => {
        if (event.target instanceof Element && event.target.closest("#arrange-form")) markUnsaved(event.target);
    });
})();
