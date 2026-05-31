# Telegram Hashtag Parser

Бот для парсинга постов из Telegram по хэштегам. 

## Запуск локально

1. Создаем окружение:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Настраиваем `.env`:
```bash
cp .env.example .env
nano .env
```
Впиши свой `BOT_TOKEN` и `ADMIN_IDS` (через запятую). Все остальные настройки (прокси, аккаунты, слова, фильтры) делаются прямо в меню бота.

3. Создаем базу и запускаем бота:
```bash
python -m app.db.init_db
python -m app.main
```

## Деплой на сервер

Бот деплоится атомарно через `deploy.sh`. На сервере создается `systemd` сервис.

1. Зайди на сервер и установи python-venv:
```bash
apt update && apt install -y python3-venv python3-pip
```

2. Создай папку для базы и конфиг на сервере:
```bash
mkdir -p /opt/telegram-hashtag-parser/shared/data
nano /opt/telegram-hashtag-parser/shared/.env
```
Впиши туда `BOT_TOKEN` и `ADMIN_IDS`.

3. Со своего компьютера запусти деплой:
```bash
cp deploy.example.env deploy.env
nano deploy.env # Укажи IP сервера
./deploy.sh
```

## Восстановление из бэкапа

Бот каждый день делает бэкапы базы (если настроено). Чтобы восстановить базу:
1. Зайди на сервер и останови бота:
   `systemctl stop telegram-hashtag-parser`
2. Скопируй бэкап в папку с активной БД:
   `cp /opt/telegram-hashtag-parser/shared/data/backups/bot_backup_XXX.db /opt/telegram-hashtag-parser/shared/data/bot.db`
3. Запусти бота:
   `systemctl start telegram-hashtag-parser`
