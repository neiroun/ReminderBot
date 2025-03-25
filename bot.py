#!/usr/bin/env python3
"""
Telegram бот для управления напоминаниями с использованием:
- AsyncTeleBot для асинхронного взаимодействия с Telegram API
- SQLAlchemy для работы с базой данных
- APScheduler для планирования задач
- Pydantic для валидации данных
- Loguru для логирования
"""

import asyncio
import sync_tasks
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import AsyncGenerator, Dict, List, Optional

import pytz
from loguru import logger
from pydantic import BaseModel, validator
from sqlalchemy import Column, DateTime, Integer, String, select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from telebot import asyncio_filters
from telebot.async_telebot import AsyncTeleBot
from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.date import DateTrigger


## Конфигурация приложения
class AppConfig:
    class Database:
        URL = "sqlite+aiosqlite:///reminders.db"
        ECHO = False

    class Bot:
        TOKEN = "YOUR_TOKEN"
        TIMEOUT = 30
        STATE_TTL = 3600  # 1 hour in seconds

    class Scheduler:
        JOBSTORES = {
            'default': SQLAlchemyJobStore(
                url='sqlite:///jobs.db',
                engine_options={'connect_args': {'check_same_thread': False}}
            )
        }
        TIMEZONE = pytz.timezone("Europe/Moscow")


## Модели данных
Base = declarative_base()


class ReminderModel(Base):
    """SQLAlchemy модель для хранения напоминаний"""
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    chat_id = Column(Integer, nullable=False)
    text = Column(String(500), nullable=False)
    remind_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    job_id = Column(String(100), nullable=False, unique=True)


class ReminderCreate(BaseModel):
    """Pydantic модель для создания напоминаний"""
    user_id: int
    chat_id: int
    text: str
    remind_time: datetime

    @validator('text')
    def validate_text(cls, v):
        if len(v) > 500:
            raise ValueError("Text must be less than 500 characters")
        return v.strip()

    @validator('remind_time')
    def validate_remind_time(cls, v):
        if v <= datetime.now(AppConfig.Scheduler.TIMEZONE):
            raise ValueError("Remind time must be in the future")
        return v


## Состояния бота
class BotState(Enum):
    MAIN_MENU = auto()
    SET_TEXT = auto()
    SET_TIME = auto()


class UserContext(BaseModel):
    """Контекст пользовательской сессии"""
    state: BotState
    data: Dict = {}
    created_at: datetime = datetime.now()


## Инициализация компонентов
class BotComponents:
    def __init__(self):
        # Инициализация базы данных
        self.engine = create_async_engine(
            AppConfig.Database.URL,
            echo=AppConfig.Database.ECHO
        )
        self.async_session = sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

        # Инициализация бота
        self.bot = AsyncTeleBot(AppConfig.Bot.TOKEN)
        self.scheduler = AsyncIOScheduler(
            jobstores=AppConfig.Scheduler.JOBSTORES,
            timezone=AppConfig.Scheduler.TIMEZONE
        )

        # Хранилище состояний
        self.user_contexts: Dict[int, UserContext] = {}

    async def init_db(self):
        """Инициализация таблиц базы данных"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def cleanup(self):
        """Очистка ресурсов"""
        await self.engine.dispose()


## Сервисный слой
class ReminderService:
    def __init__(self, components: BotComponents):
        self.components = components

    async def create_reminder(self, reminder: ReminderCreate) -> ReminderModel:
        """Создание нового напоминания"""
        job_id = f"reminder_{reminder.user_id}_{int(datetime.now().timestamp())}"

        try:
            # Проверяем существование задания
            if self.components.scheduler.get_job(job_id):
                self.components.scheduler.remove_job(job_id)
        except:
            pass

        async with self.components.async_session() as session:
            reminder_model = ReminderModel(
                user_id=reminder.user_id,
                chat_id=reminder.chat_id,
                text=reminder.text,
                remind_time=reminder.remind_time,
                job_id=job_id
            )
            session.add(reminder_model)
            await session.commit()

            self.components.scheduler.add_job(
                sync_tasks.send_reminder,
                trigger=DateTrigger(reminder.remind_time),
                args=(reminder.chat_id, reminder.text),
                id=job_id,
                replace_existing=True
            )

            return reminder_model

    async def get_user_reminders(self, user_id: int) -> List[ReminderModel]:
        """Получение активных напоминаний пользователя"""
        async with self.components.async_session() as session:
            result = await session.execute(
                select(ReminderModel)
                .where(ReminderModel.user_id == user_id)
                .where(ReminderModel.remind_time > datetime.now(AppConfig.Scheduler.TIMEZONE))
                .order_by(ReminderModel.remind_time)
            )
            return result.scalars().all()

    async def delete_reminder(self, reminder_id: int) -> bool:
        """Удаление напоминания"""
        async with self.components.async_session() as session:
            result = await session.execute(
                select(ReminderModel.job_id)
                .where(ReminderModel.id == reminder_id)
            )
            job_id = result.scalar_one_or_none()

            if job_id:
                await session.execute(
                    delete(ReminderModel)
                    .where(ReminderModel.id == reminder_id)
                )
                await session.commit()

                try:
                    self.components.scheduler.remove_job(job_id)
                except Exception as e:
                    logger.error(f"Failed to remove job {job_id}: {e}")

                return True
            return False

    async def send_reminder(self, chat_id: int, text: str):
        """Отправка напоминания пользователю"""
        try:
            await self.components.bot.send_message(chat_id, f"⏰ Напоминание: {text}")
        except Exception as e:
            logger.error(f"Failed to send reminder to {chat_id}: {e}")

    async def restore_reminders(self):
        """Восстановление напоминаний при старте"""
        # Очищаем все существующие задания
        self.components.scheduler.remove_all_jobs()

        async with self.components.async_session() as session:
            result = await session.execute(
                select(ReminderModel)
                .where(ReminderModel.remind_time > datetime.now(AppConfig.Scheduler.TIMEZONE))
            )
            reminders = result.scalars().all()

            for reminder in reminders:
                try:
                    self.components.scheduler.add_job(
                        sync_tasks.send_reminder,
                        trigger=DateTrigger(reminder.remind_time),
                        args=(reminder.chat_id, reminder.text),
                        id=reminder.job_id,
                        replace_existing=True  # Добавлено для перезаписи
                    )
                    logger.info(f"Восстановлено напоминание: {reminder.id}")
                except Exception as e:
                    logger.error(f"Ошибка восстановления {reminder.id}: {e}")


## Парсер времени
class TimeInputParser:
    @staticmethod
    def parse(input_str: str) -> Optional[datetime]:
        """Парсинг пользовательского ввода времени"""
        input_str = input_str.lower().strip()
        now = datetime.now(AppConfig.Scheduler.TIMEZONE)

        try:
            if input_str.startswith("через"):
                return TimeInputParser._parse_relative(input_str, now)
            elif "в " in input_str:
                return TimeInputParser._parse_absolute(input_str, now)
            return TimeInputParser._parse_datetime(input_str, now)
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _parse_relative(text: str, now: datetime) -> datetime:
        parts = text.split()
        num = int(parts[1])
        unit = parts[2]

        if any(x in unit for x in ["мин", "min"]):
            delta = timedelta(minutes=num)
        elif any(x in unit for x in ["час", "hour"]):
            delta = timedelta(hours=num)
        elif any(x in unit for x in ["день", "ден", "day"]):
            delta = timedelta(days=num)
        else:
            raise ValueError("Unknown time unit")

        return now + delta

    @staticmethod
    def _parse_absolute(text: str, now: datetime) -> datetime:
        if "завтра" in text:
            date = now.date() + timedelta(days=1)
            time_part = text.split("в ")[1]
        else:
            date = now.date()
            time_part = text.split("в ")[1] if "в " in text else text

        if ":" in time_part:
            hours, minutes = map(int, time_part.split(":"))
        else:
            hours, minutes = int(time_part), 0

        return datetime.combine(date, datetime.min.time()).replace(
            hour=hours, minute=minutes, tzinfo=AppConfig.Scheduler.TIMEZONE)

    @staticmethod
    def _parse_datetime(text: str, now: datetime) -> datetime:
        for fmt in ("%d.%m.%Y %H:%M", "%d.%m %H:%M", "%H:%M"):
            try:
                dt = datetime.strptime(text, fmt)
                if fmt == "%H:%M":
                    return datetime.combine(now.date(), dt.time()).replace(
                        tzinfo=AppConfig.Scheduler.TIMEZONE)
                return dt.replace(tzinfo=AppConfig.Scheduler.TIMEZONE)
            except ValueError:
                continue
        raise ValueError("Invalid datetime format")


## Пользовательский интерфейс
class BotUI:
    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        """Главное меню бота"""
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("Создать напоминание", callback_data="create_reminder"),
            InlineKeyboardButton("Мои напоминания", callback_data="list_reminders")
        )
        return markup

    @staticmethod
    def reminders_list(reminders: List[ReminderModel]) -> InlineKeyboardMarkup:
        """Список напоминаний с кнопками удаления"""
        markup = InlineKeyboardMarkup()
        for reminder in reminders:
            btn_text = f"{reminder.text[:15]}... - {reminder.remind_time.strftime('%d.%m %H:%M')}"
            markup.add(InlineKeyboardButton(
                btn_text, callback_data=f"delete_{reminder.id}"
            ))
        return markup

    @staticmethod
    def cancel_button() -> InlineKeyboardMarkup:
        """Кнопка отмены"""
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Отмена", callback_data="cancel"))
        return markup


## Обработчики команд
class BotHandlers:
    def __init__(self, components: BotComponents, service: ReminderService):
        self.components = components
        self.service = service
        self.bot = components.bot

        # Регистрация обработчиков
        self.register_handlers()

    def register_handlers(self):
        """Регистрация всех обработчиков команд"""
        self.bot.register_message_handler(
            self.handle_start, commands=["start"], pass_bot=True
        )
        self.bot.register_callback_query_handler(
            self.handle_create_reminder,
            func=lambda call: call.data == "create_reminder",
            pass_bot=True
        )
        self.bot.register_callback_query_handler(
            self.handle_list_reminders,
            func=lambda call: call.data == "list_reminders",
            pass_bot=True
        )
        self.bot.register_callback_query_handler(
            self.handle_delete_reminder,
            func=lambda call: call.data.startswith("delete_"),
            pass_bot=True
        )
        self.bot.register_callback_query_handler(
            self.handle_cancel,
            func=lambda call: call.data == "cancel",
            pass_bot=True
        )
        self.bot.register_message_handler(
            self.handle_text_input,
            content_types=["text"],
            pass_bot=True
        )

    async def handle_start(self, message: Message, bot: AsyncTeleBot):
        """Обработчик команды /start"""
        self.components.user_contexts[message.from_user.id] = UserContext(
            state=BotState.MAIN_MENU
        )
        await bot.send_message(
            message.chat.id,
            "Привет! Я бот для управления напоминаниями.",
            reply_markup=BotUI.main_menu()
        )

    async def handle_create_reminder(self, call: CallbackQuery, bot: AsyncTeleBot):
        """Обработчик создания напоминания"""
        self.components.user_contexts[call.from_user.id] = UserContext(
            state=BotState.SET_TEXT,
            data={"chat_id": call.message.chat.id}
        )
        await bot.edit_message_text(
            "Введите текст напоминания:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=BotUI.cancel_button()
        )

    async def handle_text_input(self, message: Message, bot: AsyncTeleBot):
        """Обработчик текстового ввода"""
        user_id = message.from_user.id
        if user_id not in self.components.user_contexts:
            return

        context = self.components.user_contexts[user_id]

        if context.state == BotState.SET_TEXT:
            context.state = BotState.SET_TIME
            context.data["text"] = message.text
            await bot.send_message(
                message.chat.id,
                "Введите время напоминания (например: 'через 30 минут' или 'завтра в 15:00')",
                reply_markup=BotUI.cancel_button()
            )

        elif context.state == BotState.SET_TIME:
            remind_time = TimeInputParser.parse(message.text)

            if not remind_time:
                await bot.send_message(
                    message.chat.id,
                    "Неверный формат времени. Попробуйте снова.",
                    reply_markup=BotUI.cancel_button()
                )
                return

            try:
                reminder = ReminderCreate(
                    user_id=user_id,
                    chat_id=context.data["chat_id"],
                    text=context.data["text"],
                    remind_time=remind_time
                )

                await self.service.create_reminder(reminder)
                await bot.send_message(
                    message.chat.id,
                    f"✅ Напоминание создано на {remind_time.strftime('%d.%m.%Y %H:%M')}",
                    reply_markup=BotUI.main_menu()
                )

                # Возвращаем в главное меню
                context.state = BotState.MAIN_MENU

            except ValueError as e:
                await bot.send_message(
                    message.chat.id,
                    f"Ошибка: {str(e)}",
                    reply_markup=BotUI.cancel_button()
                )

    async def handle_list_reminders(self, call: CallbackQuery, bot: AsyncTeleBot):
        """Обработчик списка напоминаний"""
        reminders = await self.service.get_user_reminders(call.from_user.id)

        if not reminders:
            await bot.edit_message_text(
                "У вас нет активных напоминаний.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=BotUI.main_menu()
            )
            return

        text = "📋 Ваши активные напоминания:\n\n"
        for reminder in reminders:
            text += f"• {reminder.text} - {reminder.remind_time.strftime('%d.%m.%Y %H:%M')}\n"

        await bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=BotUI.reminders_list(reminders)
        )

    async def handle_delete_reminder(self, call: CallbackQuery, bot: AsyncTeleBot):
        """Обработчик удаления напоминания"""
        reminder_id = int(call.data.split("_")[1])
        success = await self.service.delete_reminder(reminder_id)

        if success:
            await bot.answer_callback_query(call.id, "Напоминание удалено!")
            await bot.edit_message_text(
                "Напоминание успешно удалено.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=BotUI.main_menu()
            )
        else:
            await bot.answer_callback_query(call.id, "Ошибка удаления напоминания!")

    async def handle_cancel(self, call: CallbackQuery, bot: AsyncTeleBot):
        """Обработчик отмены действия"""
        self.components.user_contexts[call.from_user.id] = UserContext(
            state=BotState.MAIN_MENU
        )
        await bot.edit_message_text(
            "Действие отменено.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=BotUI.main_menu()
        )


## Основной цикл приложения
async def main():
    # Инициализация компонентов
    components = BotComponents()
    await components.init_db()

    # Инициализация сервисов
    service = ReminderService(components)
    await service.restore_reminders()

    # Запуск планировщика
    components.scheduler.start()

    # Инициализация обработчиков
    BotHandlers(components, service)

    # Запуск бота
    logger.info("Starting bot...")
    try:
        await components.bot.polling(none_stop=True, timeout=AppConfig.Bot.TIMEOUT)
    finally:
        await components.cleanup()
        components.scheduler.shutdown()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
