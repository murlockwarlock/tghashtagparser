# Telegram Hashtag Parser

Telegram-бот, который ищет посты по хэштегам, сохраняет результаты и позволяет управлять фильтрами из меню.

## Запуск

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

В `.env` укажите `BOT_TOKEN` и `ADMIN_IDS`, затем выполните:

```bash
python -m app.db.init_db
python -m app.main
```

## Сервер

Для развёртывания используйте `deploy.sh`. Параметры подключения берутся из локального `deploy.env`, который не добавляется в Git.
