// 店铺网页：按网址里的 # 切页面，数据都从 /api/shop 取。聊天窗用 CustomerAgent.mount 挂。
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const get = (path) => fetch(path, { credentials: "same-origin" }).then((r) => r.json());
const WHO = { guest: "游客", "member-a": "会员甲", "member-b": "会员乙" };

let products = [];
let floatChat = null;
let pageChat = null;
let lang = localStorage.getItem("shop-lang") || "zh";

function chips(p) {
  return `<span class="chip">${esc(p.delivery)}</span><span class="chip">质保 ${p.warranty_days} 天</span>${p.in_stock ? "" : '<span class="chip out">缺货</span>'}`;
}

function cover(p) {
  return `<div class="cover ${esc(p.style)}"><small>${esc(p.category)}</small><b>${esc(p.cover)}</b></div>`;
}

function renderProducts({ words = "", category = "" } = {}) {
  const query = words.toLowerCase().trim();
  $("grid").innerHTML = products
    .map((p, i) => [p, i])
    .filter(([p]) => (!query || p.name.toLowerCase().includes(query)) && (!category || p.category === category))
    .map(([p, i]) => `<a class="prod" href="#products/${i}">${cover(p)}<div class="body"><b>${esc(p.name)}</b><small>${esc(p.tagline)}</small>
      <div class="chips">${chips(p)}</div><div class="price">${esc(p.price)}</div></div></a>`)
    .join("") || '<p class="muted">没有找到相关商品。</p>';
}

function renderCategories() {
  const counts = {};
  products.forEach((p) => (counts[p.category] = (counts[p.category] || 0) + 1));
  $("catList").innerHTML = Object.keys(counts).map((c) => `<a href="#home" data-cat="${esc(c)}">${esc(c)}<svg class="i s"><use href="#i-right"/></svg></a>`).join("")
    + '<a class="all" href="#products/0">全部商品<svg class="i s"><use href="#i-arrow"/></svg></a>';
}

function renderMe(who) {
  $("meCard").innerHTML = who === "guest"
    ? `<div class="hi"><span class="ava"><svg class="i"><use href="#i-user"/></svg></span><div><b>你好</b><small>不登录也能下单，订单链接发到邮箱</small></div></div>
       <div class="acts"><a class="btn primary" href="#orders">查订单</a><a class="btn" href="#help">帮助</a></div>`
    : `<div class="hi"><span class="ava"><svg class="i"><use href="#i-user"/></svg></span><div><b>你好，${esc(WHO[who])}</b><small>订单、工单都在「我的订单」</small></div></div>
       <div class="acts"><a class="btn primary" href="#orders">我的订单</a><a class="btn" href="#support">客服</a></div>`;
}

function renderDetail(i) {
  const p = products[i] || products[0];
  if (!p) return;
  $("detail").innerHTML = `${cover(p)}<div>
    <h1>${esc(p.name)}</h1>
    <div class="chips">${chips(p)}</div>
    <p class="muted">${esc(p.about)}</p>
    <div class="price" style="margin-top:12px;font-size:26px">${esc(p.price)}</div>
    <a class="btn primary" href="#orders">立即购买</a></div>`;
}

async function renderOrders() {
  const orders = await get("/api/shop/orders");
  $("orderList").innerHTML = orders.length ? orders.map((o) => `
    <div class="order"><b>${esc(o.product)}</b><span class="st">${esc(o.status)}</span>
      <small>${esc(o.order_no)} · ${o.paid ? "已到账" : "还没有收到付款"}${o.warranty_until ? ` · 质保到 ${esc(o.warranty_until)}` : ""}${o.open_ticket ? ` · 工单 ${esc(o.open_ticket)} 在处理` : ""}</small>
      ${o.card_secret ? `<span class="card">卡密：${esc(o.card_secret)}</span>` : ""}</div>`).join("")
    : '<p class="muted">当前浏览器里没有订单。</p>';
}

async function renderHelp(target) {
  if (!$("helpList").dataset.loaded) {
    const articles = await get("/api/shop/help");
    $("helpList").innerHTML = articles.map((a) => `
      <div class="faq" id="help-${esc(a.id)}"><b>${esc(a.title)}</b><small>${esc(a.category)}</small><p>${esc(a.body)}</p></div>`).join("");
    $("helpList").dataset.loaded = "1";
  }
  document.querySelectorAll(".faq.hit").forEach((x) => x.classList.remove("hit"));
  const hit = target && document.getElementById(`help-${target}`);
  if (hit) {
    hit.classList.add("hit");
    hit.scrollIntoView({ block: "start" });
  } else window.scrollTo(0, 0);
}

function mountChat(support) {
  if (support) {
    floatChat?.unmount();
    floatChat = null;
    pageChat ??= CustomerAgent.mount({ mode: "page", target: $("fullHost"), lang });
  } else {
    pageChat?.unmount();
    pageChat = null;
    floatChat ??= CustomerAgent.mount({ mode: "float", lang });
  }
}

function route() {
  const [view, ...rest] = (location.hash.slice(1) || "home").split("/");
  const name = ["home", "products", "orders", "help", "support"].includes(view) ? view : "home";
  document.querySelectorAll(".view").forEach((x) => x.classList.toggle("on", x.id === `v-${name}`));
  document.querySelectorAll("#links a").forEach((x) => x.classList.toggle("on", x.getAttribute("href") === `#${name}`));
  if (name === "products") renderDetail(Number(rest[0] || 0));
  if (name === "orders") renderOrders();
  if (name === "help") renderHelp(rest.join("/"));
  else window.scrollTo(0, 0);
  mountChat(name === "support");
}

$("who").addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  await fetch("/api/shop/identity", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ who: b.dataset.who }) });
  location.reload(); // 换了身份，聊天窗会发现旧会话打不开，自动开新的
});

$("lang").addEventListener("click", () => {
  localStorage.setItem("shop-lang", lang === "en" ? "zh" : "en");
  location.reload();
});

$("search").addEventListener("input", (e) => {
  if (location.hash && location.hash !== "#home") location.hash = "#home";
  renderProducts({ words: e.target.value });
});

$("catList").addEventListener("click", (e) => {
  const a = e.target.closest("[data-cat]");
  if (a) renderProducts({ category: a.dataset.cat });
});

(async () => {
  document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
  document.querySelector("#lang span").textContent = lang === "en" ? "中文" : "English";
  const me = await get("/api/shop/me");
  $("shopName").textContent = me.name;
  $("shopBrand").textContent = me.brand;
  document.title = me.name;
  document.querySelectorAll("#who button").forEach((x) => x.classList.toggle("on", x.dataset.who === me.who));
  renderMe(me.who);
  products = await get("/api/shop/products");
  renderProducts();
  renderCategories();
  window.addEventListener("hashchange", route);
  route();
})();
