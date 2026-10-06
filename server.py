"""Mini App «Кофейня»: веб-сервер (страница + API) и Telegram-бот в одном процессе.

Страница (app/) открывается внутри Telegram кнопкой «Меню». Заказ: страница шлёт id товаров + initData →
сервер проверяет подпись Telegram, сам считает сумму, создаёт заказ и ссылку на оплату (Telegram Stars) →
страница открывает оплату → бот получает successful_payment → заказ оплачен, админу уведомление.
"""
import asyncio
import html
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    MenuButtonWebApp,
    Message,
    PreCheckoutQuery,
    WebAppInfo,
)
from aiogram.utils.web_app import safe_parse_webapp_init_data
from aiohttp import web
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import catalog  # noqa: E402
import db  # noqa: E402

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID") or 0)
WEBAPP_URL = (os.getenv("WEBAPP_URL") or "").rstrip("/")  # публичный HTTPS-адрес страницы
PORT = int(os.getenv("PORT") or 8080)
# Демо: оплата символической суммой в звёздах вместо рублей (для рублей — provider_token магазина, как в booking-bot)
STARS_PER_ORDER = int(os.getenv("STARS_PER_ORDER") or 1)
INIT_DATA_MAX_AGE = timedelta(hours=24)  # старые initData не принимаем — защита от повторного использования

APP_DIR = Path(__file__).parent / "app"
BUILD = str(int(time.time()))  # версия статики: Telegram кэширует страницу, ?v= заставляет брать свежую

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)


# ---------- проверка подлинности ----------
class AuthError(Exception):
    pass


def authenticate(init_data: str):
    """initData подписан Telegram ключом бота. Без проверки любой отправит заказ от чужого имени."""
    try:
        data = safe_parse_webapp_init_data(BOT_TOKEN, init_data)
    except ValueError:
        raise AuthError("Подпись Telegram не сходится")
    auth_date = data.auth_date if data.auth_date.tzinfo else data.auth_date.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - auth_date > INIT_DATA_MAX_AGE:
        raise AuthError("Сессия устарела — откройте меню заново")
    if data.user is None:
        raise AuthError("Нет данных пользователя")
    return data.user


# ---------- веб: страница и API ----------
async def index(request: web.Request):
    page = (APP_DIR / "index.html").read_text(encoding="utf-8").replace("{{BUILD}}", BUILD)
    return web.Response(text=page, content_type="text/html", headers={"Cache-Control": "no-store"})


async def api_menu(request: web.Request):
    return web.json_response({"menu": catalog.MENU, "pickup": catalog.PICKUP_OPTIONS})


async def api_order(request: web.Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Неверный запрос"}, status=400)
    try:
        user = authenticate(body.get("initData") or "")
    except AuthError as e:
        return web.json_response({"error": str(e)}, status=401)
    try:
        lines, total = catalog.price_order(body.get("items"))
    except catalog.OrderError as e:
        return web.json_response({"error": str(e)}, status=400)
    pickup = body.get("pickup") if body.get("pickup") in catalog.PICKUP_OPTIONS else catalog.PICKUP_OPTIONS[0]
    comment = str(body.get("comment") or "")[:300]

    order_id = db.create(user.id, user.username or user.first_name, lines, total, pickup, comment, STARS_PER_ORDER)
    link = await bot.create_invoice_link(
        title=f"Заказ №{order_id}",
        description=f"{total} ₽ · самовывоз {pickup} · демо-оплата {STARS_PER_ORDER} ⭐",
        payload=f"order:{order_id}",
        currency="XTR",
        prices=[LabeledPrice(label=f"Заказ на {total} ₽", amount=STARS_PER_ORDER)],
    )
    logging.info("Заказ %s от %s на %s ₽", order_id, user.id, total)
    return web.json_response({"orderId": order_id, "total": total, "invoiceLink": link})


def make_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/api/menu", api_menu)
    app.router.add_post("/api/order", api_order)
    app.router.add_static("/static", APP_DIR)
    return app


# ---------- бот ----------
def menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="☕ Открыть меню", web_app=WebAppInfo(url=WEBAPP_URL))]])


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("Кофейня «Демо» ☕\nЗакажите заранее — заберёте без очереди.", reply_markup=menu_keyboard())


@dp.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    order = db.get(int(q.invoice_payload.split(":")[1]))
    if order is None or order["user_id"] != q.from_user.id or order["status"] != "new":
        await q.answer(ok=False, error_message="Заказ не найден или уже оплачен")
        return
    await q.answer(ok=True)


def order_text(order) -> str:
    items = "\n".join(f"• {html.escape(l['name'])} × {l['qty']} — {l['sum']} ₽" for l in db.lines(order))
    comment = f"\n💬 {html.escape(order['comment'])}" if order["comment"] else ""
    return f"{items}\nИтого: <b>{order['total_rub']} ₽</b>\nСамовывоз {order['pickup']}{comment}"


@dp.message(F.successful_payment)
async def paid(message: Message):
    p = message.successful_payment
    order_id = int(p.invoice_payload.split(":")[1])
    if not db.mark_paid(order_id, p.telegram_payment_charge_id):
        return  # повторное уведомление
    order = db.get(order_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Вернуть звезду (демо)", callback_data=f"refund:{order_id}")]])
    await message.answer(f"✅ Заказ №{order_id} оплачен!\n\n{order_text(order)}", parse_mode="HTML", reply_markup=kb)
    if ADMIN_ID:
        await bot.send_message(ADMIN_ID, f"🆕 Заказ №{order_id} от @{html.escape(order['username'] or '—')}\n\n{order_text(order)}",
                               parse_mode="HTML")


@dp.callback_query(F.data.startswith("refund:"))
async def refund(cb: CallbackQuery):
    order = db.get(int(cb.data.split(":")[1]))
    if order is None or order["user_id"] != cb.from_user.id or order["status"] != "paid":
        await cb.answer("Возврат уже сделан или недоступен", show_alert=True)
        return
    await bot.refund_star_payment(user_id=order["user_id"], telegram_payment_charge_id=order["tg_charge_id"])
    db.mark_refunded(order["id"])
    await cb.message.edit_text(f"↩️ Заказ №{order['id']}: {order['stars']} ⭐ возвращено.")
    await cb.answer()


@dp.message()
async def fallback(message: Message):
    await message.answer("Меню — по кнопке ниже 👇", reply_markup=menu_keyboard())


async def main():
    if not WEBAPP_URL.startswith("https://"):
        raise SystemExit("WEBAPP_URL должен быть публичным https-адресом — Telegram открывает Mini App только по HTTPS")
    db.init_db()
    runner = web.AppRunner(make_web_app())
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logging.info("Страница: http://localhost:%s → %s", PORT, WEBAPP_URL)
    # кнопка «Меню» слева от поля ввода во всех чатах с ботом
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Меню", web_app=WebAppInfo(url=WEBAPP_URL)))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
