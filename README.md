# Telegram Reminder Bot 🤖⏰

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-gpl-greeen)
![Architecture](https://img.shields.io/badge/architecture-async-orange)

Простой бот для управления напоминаниями с поддержкой естественного языка ввода времени. Проект является основой для каких-либо учебных проектов или самостоятельного изучения кодинга телеграм ботов.

## 🌟 Ключевые особенности

### 🕒 Гибкий ввод времени
- Поддержка относительного времени ("через 30 минут")
- Поддержка абсолютного времени ("завтра в 15:00")
- Распознавание различных форматов дат

### 🔄 Надежное хранение
- Автоматическое восстановление напоминаний после перезапуска
- Поддержка SQLite (по умолчанию) и PostgreSQL
- Резервное копирование состояния планировщика

### ⚡ Производительность
- Полностью асинхронная архитектура
- Оптимизированные запросы к базе данных
- Минимальные задержки при обработке команд

## 🛠 Технологический стек

| Компонент       | Версия  | Назначение                          |
|-----------------|---------|-------------------------------------|
| Python          | 3.10+   | Основной язык программирования      |
| AsyncTeleBot    | 3.0+    | Работа с Telegram Bot API           |
| SQLAlchemy      | 2.0+    | ORM для работы с базой данных       |
| APScheduler     | 3.9+    | Планирование и выполнение задач     |
| Pydantic        | 2.0+    | Валидация и парсинг данных          |
| Loguru          | 0.7+    | Профессиональное логирование        |
| Docker          | 20.10+  | Контейнеризация приложения          |

## 🚀 Быстрый старт

### Предварительные требования
- Python 3.10 или новее
- Аккаунт Telegram
- Токен бота от [@BotFather](https://t.me/BotFather)

### Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/telegram-reminder-bot.git
cd telegram-reminder-bot 
```

2. Настройте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # Linux/MacOS
.\venv\Scripts\activate  # Windows
```

3. Установите зависимости
```bash
pip install -r requirements.txt
```

4. Настройте окружение
```bash
cp .env.example .env
nano .env  # Отредактируйте файл
```

## ⚙️ Конфигурация
Основные параметры в `.env`:
```ini
# Обязательные параметры
BOT_TOKEN=your_telegram_bot_token

# Настройки базы данных
DATABASE_URL=sqlite+aiosqlite:///reminders.db

# Настройки времени
TIMEZONE=Europe/Moscow

# Настройки логирования
LOG_LEVEL=INFO
LOG_FILE=bot.log
LOG_ROTATION=10 MB
```

## 🏃 Запуск приложения
### Локальный запуск
```bash
python bot.py
```
### Запуск в production
```bash
nohup python bot.py > bot.log 2>&1 &
```

## 🐳 Docker развертывание
1. Соберите Docker образ:
```bash
docker build -t reminder-bot .
```
2. Запустите контейнер:
```bash
docker run -d \
  --env-file .env \
  --name reminder-bot \
  -v ./data:/app/data \
  -p 5000:5000 \
  reminder-bot
```

## 📖 Руководство пользователя
| Команда               | Описание                     |
|-----------------------|------------------------------|
| `/start`              | Главное меню бота            |
| "Создать напоминание" | Установка нового напоминания |
| "Мои напоминания"     | Просмотр активных напоминаний|
| "Отмена"              | Прервать текущую операцию    |
### Примеры использования
1. Создание напоминания:
```chat
Пользователь: через 2 часа позвонить маме
Бот: Напоминание "позвонить маме" создано на 15:30
```
2. Просмотр напоминаний:
```chat 
Пользователь: Мои напоминания
Бот: Ваши активные напоминания:
1. Позвонить маме - сегодня в 15:30
2. Совещание - завтра в 09:00
```

## 📊 Мониторинг и логирование
### Логи доступны:
- В файле bot.log (ротация по 10 МБ)
- В stdout при запуске через Docker
### Пример лога:
```log
2023-05-24 12:00:00 - INFO - Bot started
2023-05-24 12:05:00 - INFO - Reminder created for user 12345
2023-05-24 12:10:00 - INFO - Sent reminder to user 12345
```
## 🔧 Устранение неисправностей
### 1. Бот не отвечает:
- Проверьте статус контейнера: docker ps -a
- Просмотрите логи: docker logs reminder-bot
### Проблемы с базой данных:
- Проверьте подключение к БД
- Убедитесь в наличии прав на запись
### Ошибки валидации:
- Проверьте формат вводимых данных
- Убедитесь в правильности временной зоны

## 🤝 Если у вас есть интересные идеи на основе этого бота и вам хочется поделиться ими, то:
1. Форкните репозиторий
2. Создайте ветку для своей фичи (`git checkout -b feature/amazing-feature`)
3. Сделайте коммит изменений (`git commit -m 'Add some amazing feature'`)
4. Запушьте ветку (`git push origin feature/amazing-feature`)
5. Откройте Pull Request

## Примечание
Для production-окружения рекомендуется:

- Использовать PostgreSQL вместо SQLite
- Настроить регулярное резервное копирование базы данных
- Реализовать мониторинг состояния бота

## 📜 Лицензия  
Распространяется под лицензией [GNU GENERAL PUBLIC LICENSE](LICENSE).  
Подробности см. в файле [LICENSE](LICENSE).
