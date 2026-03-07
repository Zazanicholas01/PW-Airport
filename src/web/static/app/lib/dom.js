export const $ = (id, root = document) => root.getElementById(id);

export function setVisible(el, visible) {
  if (!el) return;
  el.classList.toggle("hidden", !visible);
  el.style.display = visible ? "" : "none";
}

export function delegate(root, selector, type, handler) {
  root.addEventListener(type, (event) => {
    const target = event.target.closest(selector);
    if (!target || !root.contains(target)) return;
    handler(event, target);
  });
}
