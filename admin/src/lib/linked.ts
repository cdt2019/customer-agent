/** 两栏联动：同一块在左右两边都带 data-c。长文档有几百块，高亮直接改属性，不走 React 重新渲染。 */
export function markLinked(root: HTMLElement | null, id: string | null) {
  root?.querySelectorAll("[data-c][data-on]").forEach((el) => el.removeAttribute("data-on"));
  if (id) root?.querySelectorAll(`[data-c="${id}"]`).forEach((el) => el.setAttribute("data-on", ""));
}

/** 只滚最近的 data-scroll 那一栏：scrollIntoView 会把整页也带着滚。 */
export function scrollWithin(target: Element) {
  const box = target.closest("[data-scroll]");
  if (box) box.scrollTop += target.getBoundingClientRect().top - box.getBoundingClientRect().top - 48;
}
