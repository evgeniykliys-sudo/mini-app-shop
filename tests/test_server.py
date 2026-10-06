"""Офлайн-тест: проверка подписи Telegram (initData) и серверного расчёта суммы.
API гоняется через настоящий aiohttp-сервер; создание счёта в Telegram подменено.

    python tests/test_server.py
"""
import asyncio
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode

TOKEN = "123456:TEST-TOKEN-FOR-SIGNING"
os.environ.update(BOT_TOKEN=TOKEN, DB_PATH=str(Path(tempfile.mkdtemp()) / "t.db"), WEBAPP_URL="https://example.test")
sys.path.insert(0, str(Path(__file__).parent.parent))

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

import db  # noqa: E402
import server  # noqa: E402

ok_all = True


def check(name, cond):
    global ok_all
    ok_all &= bool(cond)
    print(("✅" if cond else "❌"), name)


def sign(fields: dict, token: str = TOKEN) -> str:
    """Подпись initData по алгоритму Telegram: secret = HMAC("WebAppData", token), hash = HMAC(secret, строки key=value)."""
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": h})


def fields(user_id=42, age_sec=0):
    return {"auth_date": str(int(time.time()) - age_sec), "query_id": "AAA",
            "user": json.dumps({"id": user_id, "first_name": "Тест", "username": "tester"}, ensure_ascii=False)}


async def main():
    # --- подпись ---
    good = sign(fields())
    check("1. настоящая подпись принимается", server.authenticate(good).id == 42)
    f = fields(); f_bad = dict(f, user=f["user"].replace("42", "777"))
    forged = urlencode({**f_bad, "hash": dict(p.split("=", 1) for p in good.split("&"))["hash"]})
    for name, data in [("2. подменён пользователь (чужой id с той же подписью)", forged),
                       ("3. подписано чужим токеном", sign(fields(), "999:OTHER")),
                       ("4. подписи нет вовсе", urlencode(fields())),
                       ("5. подпись старше 24 часов", sign(fields(age_sec=25 * 3600)))]:
        try:
            server.authenticate(data)
            check(name + " — отклонено", False)
        except server.AuthError:
            check(name + " — отклонено", True)

    # --- расчёт на сервере ---
    import catalog
    lines, total = catalog.price_order({"latte": 2, "croissant": 1})
    check("6. сумма считается по прайсу сервера (2×240 + 180 = 660)", total == 660)
    for name, items in [("7. несуществующий товар", {"free_coffee": 1}), ("8. отрицательное количество", {"latte": -3}),
                        ("9. дробное/строковое количество", {"latte": "2"}), ("10. слишком много", {"latte": 500}),
                        ("11. true вместо числа", {"latte": True}), ("12. пустая корзина", {})]:
        try:
            catalog.price_order(items)
            check(name + " — отклонено", False)
        except catalog.OrderError:
            check(name + " — отклонено", True)

    # --- API целиком ---
    async def fake_invoice(**kw):
        fake_invoice.last = kw
        return "https://t.me/$fake-invoice"
    server.bot.create_invoice_link = fake_invoice
    db.init_db()
    async with TestClient(TestServer(server.make_web_app())) as client:
        r = await client.get("/api/menu")
        check("13. /api/menu отдаёт меню", r.status == 200 and len((await r.json())["menu"]) == len(catalog.MENU))
        r = await client.post("/api/order", json={"initData": sign(fields()),
                                                  "items": {"latte": 2, "croissant": 1}, "price": 1, "total": 1})
        body = await r.json()
        check("14. заказ с подделанной суммой от клиента: сервер считает сам (660 ₽)",
              r.status == 200 and body["total"] == 660 and db.get(body["orderId"])["total_rub"] == 660)
        check("15. счёт создан на сервере: валюта XTR, payload с номером заказа",
              fake_invoice.last["currency"] == "XTR" and fake_invoice.last["payload"] == f"order:{body['orderId']}")
        r = await client.post("/api/order", json={"initData": forged, "items": {"latte": 1}})
        check("16. заказ с поддельной подписью → 401, заказ не создан", r.status == 401)
        r = await client.get("/")
        check("17. страница отдаётся без кэша (Telegram иначе держит старую версию)",
              r.status == 200 and r.headers.get("Cache-Control") == "no-store")

    print("\nИТОГ:", "все проверки пройдены" if ok_all else "ЕСТЬ ОШИБКИ")
    await server.bot.session.close()
    sys.exit(0 if ok_all else 1)


asyncio.run(main())
