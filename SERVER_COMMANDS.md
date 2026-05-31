# Мануал по серверу — Telegram Hashtag Parser

Сервер: `YOUR_SERVER_IP`  
Путь проекта: `/opt/telegram-hashtag-parser/`  
Подключение: `ssh root@YOUR_SERVER_IP`

---

## 🤖 Управление ботом (systemd)

```bash
# Статус бота
systemctl status telegram-hashtag-parser

# Перезапустить бота
systemctl restart telegram-hashtag-parser

# Остановить бота
systemctl stop telegram-hashtag-parser

# Запустить бота
systemctl start telegram-hashtag-parser

# Принудительно убить (если завис при остановке)
systemctl kill -s SIGKILL telegram-hashtag-parser

# Посмотреть логи в реальном времени
journalctl -u telegram-hashtag-parser -f

# Посмотреть последние 100 строк логов
journalctl -u telegram-hashtag-parser -n 100 --no-pager

# Посмотреть логи за сегодня
journalctl -u telegram-hashtag-parser --since today --no-pager
```

---

## 🚀 Деплой

Деплой делается **с локальной машины**, не с сервера:

```bash
# Обычный деплой (запускает тесты, загружает, перезапускает)
SSHPASS='YOUR_SSH_PASSWORD' ./deploy.sh
```

Деплой атомарный — если тесты падают, бот не перезапускается.

### Посмотреть список релизов на сервере:
```bash
ls -lt /opt/telegram-hashtag-parser/releases/
```

### Откатиться на предыдущий релиз:
```bash
# Посмотреть какой сейчас текущий
ls -la /opt/telegram-hashtag-parser/current

# Переключиться на конкретный релиз
ln -sfn /opt/telegram-hashtag-parser/releases/<имя_релиза> /opt/telegram-hashtag-parser/current
systemctl restart telegram-hashtag-parser
```

---

## 🗃️ База данных

БД: `/opt/telegram-hashtag-parser/shared/db.sqlite3`  
Запросы запускать через Python (sqlite3 не установлен):

```bash
cd /opt/telegram-hashtag-parser/current
/opt/telegram-hashtag-parser/shared/venv/bin/python3 -c "
from app.db.session import SessionLocal
from app.db.models import Post
with SessionLocal() as db:
    # пример: посмотреть последние 10 кандидатов
    posts = db.query(Post).filter(Post.status=='candidate').order_by(Post.id.desc()).limit(10).all()
    for p in posts:
        print(p.id, p.published_at, p.hashtag, p.priority)
"
```

### Бэкап БД:
```bash
cp /opt/telegram-hashtag-parser/shared/db.sqlite3 ~/db_backup_$(date +%Y%m%d).sqlite3
```

---

## ⚙️ Конфиг

Переменные окружения: `/opt/telegram-hashtag-parser/shared/.env`

```bash
# Посмотреть текущий конфиг (без секретов)
cat /opt/telegram-hashtag-parser/shared/.env | sed -E 's/([^=]+)=.*/\1=***скрыто***/'

# Отредактировать (после — обязательно рестарт)
nano /opt/telegram-hashtag-parser/shared/.env
systemctl restart telegram-hashtag-parser
```

### Важные переменные:
| Переменная | Описание |
|---|---|
| `BOT_TOKEN` | Токен Telegram бота |
| `ADMIN_IDS` | ID администраторов (через запятую) |
| `API_ID` / `API_HASH` | Telegram API для парсера |

---

## 📁 Структура на сервере

```
/opt/telegram-hashtag-parser/
├── current/          → симлинк на текущий релиз
├── releases/         → все релизы (можно откатиться)
│   └── 20260529_HHMMSS_<hash>/
├── shared/
│   ├── .env          → конфиг (токены, ключи)
│   ├── db.sqlite3    → база данных
│   ├── sessions/     → Telegram сессии аккаунтов
│   └── venv/         → Python venv (общий для всех релизов)
```

---

## 🔍 Диагностика

```bash
# Бот не отвечает — смотреть логи
journalctl -u telegram-hashtag-parser -n 50 --no-pager

# Проверить что процесс жив
ps aux | grep python

# Свободное место на диске
df -h

# Использование памяти
free -h

# Проверить сеть / доступ к Telegram
curl -s https://api.telegram.org/bot<TOKEN>/getMe
```

---

## 🔐 Telegram сессии (аккаунты парсера)

Сессии хранятся в `/opt/telegram-hashtag-parser/shared/sessions/`.  
Управление аккаунтами — через бота (`/start` → Аккаунты).

Если аккаунт получил flood wait или ban — бот уведомит в чат автоматически.
