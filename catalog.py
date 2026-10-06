"""Меню кофейни и расчёт заказа. Цены считает ТОЛЬКО сервер: страница присылает id товаров и количество,
сумма берётся отсюда — иначе покупатель поправит цену в браузере и оплатит кофе за 1 ₽."""

MENU = [
    {"id": "espresso", "cat": "Кофе", "name": "Эспрессо", "price": 150, "emoji": "☕", "desc": "30 мл, плотный вкус"},
    {"id": "cappuccino", "cat": "Кофе", "name": "Капучино", "price": 220, "emoji": "☕", "desc": "250 мл, классика"},
    {"id": "latte", "cat": "Кофе", "name": "Латте", "price": 240, "emoji": "🥛", "desc": "300 мл, мягкий"},
    {"id": "raf", "cat": "Кофе", "name": "Раф ванильный", "price": 280, "emoji": "🍦", "desc": "300 мл, со сливками"},
    {"id": "tea", "cat": "Чай", "name": "Облепиховый чай", "price": 200, "emoji": "🍵", "desc": "400 мл, с мёдом"},
    {"id": "matcha", "cat": "Чай", "name": "Матча латте", "price": 290, "emoji": "🍵", "desc": "300 мл, на овсяном"},
    {"id": "croissant", "cat": "Выпечка", "name": "Круассан", "price": 180, "emoji": "🥐", "desc": "сливочный, тёплый"},
    {"id": "cheesecake", "cat": "Выпечка", "name": "Чизкейк", "price": 260, "emoji": "🍰", "desc": "нью-йорк"},
    {"id": "sandwich", "cat": "Выпечка", "name": "Сэндвич с индейкой", "price": 320, "emoji": "🥪", "desc": "на чиабатте"},
]
BY_ID = {item["id"]: item for item in MENU}
MAX_QTY = 20
PICKUP_OPTIONS = ("через 10 минут", "через 20 минут", "через 30 минут")


class OrderError(ValueError):
    pass


def price_order(items: dict) -> tuple[list[dict], int]:
    """{"latte": 2, "croissant": 1} → строки заказа и сумма в рублях. Всё, что пришло со страницы, — недоверенное."""
    if not isinstance(items, dict) or not items:
        raise OrderError("Корзина пуста")
    lines, total = [], 0
    for item_id, qty in items.items():
        item = BY_ID.get(item_id)
        if item is None:
            raise OrderError(f"Нет такой позиции: {item_id}")
        if not isinstance(qty, int) or isinstance(qty, bool) or not 1 <= qty <= MAX_QTY:
            raise OrderError(f"Неверное количество для «{item['name']}»")
        lines.append({"id": item_id, "name": item["name"], "qty": qty, "price": item["price"], "sum": item["price"] * qty})
        total += item["price"] * qty
    return lines, total
