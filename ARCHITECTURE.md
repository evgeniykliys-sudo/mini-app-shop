# Архитектура: mini-app-shop

```
Telegram (кнопка «Меню») ──► https://WEBAPP_URL/  (страница: app/index.html + app.js + style.css)
                                   │  GET /api/menu — каталог
                                   │  POST /api/order {initData, items:{id: кол-во}, pickup, comment}
                                   ▼
server.py (aiohttp)  ─ authenticate(initData): подпись HMAC ключом бота + не старше 24 ч
                     ─ catalog.price_order(items): сумма по прайсу сервера
                     ─ db.create(): заказ status=new
                     ─ bot.create_invoice_link(XTR) → ссылка на оплату
                                   │
страница: Telegram.WebApp.openInvoice(ссылка) → оплата внутри Mini App
                                   │
бот (aiogram, тот же процесс): pre_checkout (заказ свой, не оплачен) → successful_payment
                                → заказ paid, подтверждение клиенту, уведомление админу → кнопка возврата (демо)
```

## Модули
| Модуль | Что делает |
|---|---|
| `server.py` | aiohttp: страница и API; aiogram: /start, кнопка «Меню», оплата, возврат. Один процесс — одна база и один токен |
| `catalog.py` | Меню и расчёт заказа (вход со страницы — недоверенный) |
| `db.py` | Заказы SQLite: new → paid → refunded |
| `app/` | Страница без сборщиков: тема Telegram, MainButton/BackButton, HapticFeedback, openInvoice |
| `tests/test_server.py` | Подпись initData (сам подписываю по алгоритму Telegram), расчёт, API через настоящий aiohttp-сервер |

## Решения и почему
- **Проверка initData на сервере** (`aiogram.utils.web_app.safe_parse_webapp_init_data`) + свой контроль возраста
  подписи: без него старую перехваченную initData можно использовать бесконечно.
- **Сервер считает сумму сам** — на странице сумма только для показа.
- **Оплата через `createInvoiceLink` + `openInvoice`**, а не `sendData`: `sendData` работает только при запуске
  с обычной клавиатуры и закрывает приложение, а здесь оплата идёт внутри Mini App и пользователь видит результат.
- **Страница без сборщиков** (чистый HTML/JS): заказчику проще поддерживать, нечего собирать.
- **Цвета — CSS-переменные темы Telegram** (`--tg-theme-*`) с запасными значениями для обычного браузера.
- **`Cache-Control: no-store` и `?v=версия` для статики**: встроенный браузер Telegram держит старую версию страницы.
- **Работа вне Telegram**: в обычном браузере меню открывается (для портфолио и проверки вёрстки), заказ — нет
  (без initData сервер его не примет).

## HTTPS для разработки
Telegram открывает Mini App только по HTTPS. Туннель Cloudflare не подключился: порт 7844 у провайдера закрыт
(в логе `Allow outbound TCP on port 7844`). Заработал SSH-туннель localhost.run через обычный порт 22.
Для постоянной работы — сервер с доменом и сертификатом (Caddy получает Let's Encrypt сам).
