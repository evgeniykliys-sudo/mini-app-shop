// Mini App «Кофейня». Сумма здесь — только для показа: сервер пересчитывает её сам по id товаров.
const tg = window.Telegram?.WebApp;
const inTelegram = Boolean(tg && tg.initData); // в обычном браузере initData пустой
const fallbackBtn = document.getElementById("fallback-button");

let MENU = [];
let PICKUP = [];
const cart = {}; // id -> количество
let activeCat = null;
let view = "menu";
let mainHandler = null;

const $ = (id) => document.getElementById(id);
const fmt = (n) => n.toLocaleString("ru-RU") + " ₽";

function total() {
  return Object.entries(cart).reduce((s, [id, q]) => s + MENU.find((m) => m.id === id).price * q, 0);
}

function haptic(kind = "light") {
  tg?.HapticFeedback?.impactOccurred?.(kind);
}

// ---------- основная кнопка: Telegram MainButton или своя в браузере ----------
function setMainButton(text, handler) {
  mainHandler = handler;
  if (inTelegram) {
    if (!text) return tg.MainButton.hide();
    tg.MainButton.setText(text);
    tg.MainButton.show();
  } else {
    fallbackBtn.textContent = text || "";
    fallbackBtn.classList.toggle("hidden", !text);
  }
}
function onMain() { if (mainHandler) mainHandler(); }

function setBack(visible) {
  if (!inTelegram) return;
  visible ? tg.BackButton.show() : tg.BackButton.hide();
}

// ---------- меню ----------
function renderTabs() {
  const cats = [...new Set(MENU.map((m) => m.cat))];
  activeCat = activeCat || cats[0];
  $("tabs").innerHTML = "";
  for (const c of cats) {
    const b = document.createElement("button");
    b.textContent = c;
    b.className = c === activeCat ? "active" : "";
    b.onclick = () => { activeCat = c; haptic(); renderTabs(); renderItems(); };
    $("tabs").appendChild(b);
  }
}

function renderItems() {
  const box = $("items");
  box.innerHTML = "";
  for (const m of MENU.filter((x) => x.cat === activeCat)) {
    const q = cart[m.id] || 0;
    const el = document.createElement("div");
    el.className = "item";
    el.innerHTML = `
      <div class="emoji">${m.emoji}</div>
      <div class="info"><div class="name"></div><div class="desc"></div><div class="price">${fmt(m.price)}</div></div>
      <div class="ctrl"></div>`;
    el.querySelector(".name").textContent = m.name;
    el.querySelector(".desc").textContent = m.desc;
    const ctrl = el.querySelector(".ctrl");
    if (!q) {
      const add = document.createElement("button");
      add.className = "add";
      add.textContent = "Добавить";
      add.onclick = () => change(m.id, +1);
      ctrl.appendChild(add);
    } else {
      ctrl.innerHTML = `<div class="qty"><button data-d="-1">−</button><span class="n">${q}</span><button data-d="1">+</button></div>`;
      ctrl.querySelectorAll("button").forEach((b) => (b.onclick = () => change(m.id, Number(b.dataset.d))));
    }
    box.appendChild(el);
  }
}

function change(id, d) {
  cart[id] = Math.max(0, Math.min(20, (cart[id] || 0) + d));
  if (!cart[id]) delete cart[id];
  haptic();
  renderItems();
  updateMain();
}

function updateMain() {
  if (view === "menu") {
    const t = total();
    setMainButton(t ? `Оформить · ${fmt(t)}` : "", showCheckout);
  } else if (view === "checkout") {
    setMainButton(inTelegram ? `Оплатить · ${fmt(total())}` : "Оплата доступна в Telegram", inTelegram ? pay : null);
  } else {
    setMainButton(inTelegram ? "Закрыть" : "", () => tg.close());
  }
}

// ---------- оформление ----------
function show(v) {
  view = v;
  $("menu-view").classList.toggle("hidden", v !== "menu");
  $("checkout-view").classList.toggle("hidden", v !== "checkout");
  $("done-view").classList.toggle("hidden", v !== "done");
  setBack(v === "checkout");
  updateMain();
  window.scrollTo(0, 0);
}

function showCheckout() {
  const rows = Object.entries(cart).map(([id, q]) => {
    const m = MENU.find((x) => x.id === id);
    return `<div class="row"><span>${m.emoji} ${escapeHtml(m.name)} × ${q}</span><span>${fmt(m.price * q)}</span></div>`;
  });
  $("summary").innerHTML = rows.join("") + `<div class="row total"><span>Итого</span><span>${fmt(total())}</span></div>`;
  show("checkout");
}

async function pay() {
  if (inTelegram) tg.MainButton.showProgress();
  try {
    const res = await fetch("/api/order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ initData: tg.initData, items: cart, pickup: $("pickup").value, comment: $("comment").value }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Ошибка сервера");
    tg.openInvoice(data.invoiceLink, (status) => {
      if (status === "paid") {
        tg.HapticFeedback?.notificationOccurred?.("success");
        for (const k of Object.keys(cart)) delete cart[k];
        show("done");
      } else if (status === "failed") {
        tg.showAlert("Оплата не прошла. Попробуйте ещё раз.");
      }
    });
  } catch (e) {
    tg.showAlert(e.message);
  } finally {
    tg.MainButton.hideProgress();
  }
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------- старт ----------
async function init() {
  if (inTelegram) {
    tg.ready();
    tg.expand();
    tg.MainButton.onClick(onMain);
    tg.BackButton.onClick(() => show("menu"));
  } else {
    fallbackBtn.onclick = onMain;
    $("notice").textContent = "Это меню открыто в браузере. Заказать и оплатить можно, открыв его в Telegram через бота.";
    $("notice").classList.remove("hidden");
  }
  const data = await (await fetch("/api/menu")).json();
  MENU = data.menu;
  PICKUP = data.pickup;
  $("pickup").innerHTML = PICKUP.map((p) => `<option>${p}</option>`).join("");
  renderTabs();
  renderItems();
  show("menu");
}
init();
