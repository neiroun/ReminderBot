from telebot import TeleBot
from loguru import logger
from bot import AppConfig


def send_reminder(chat_id: int, text: str):
    """Синхронная функция для отправки напоминаний"""
    try:
        bot = TeleBot(AppConfig.Bot.TOKEN)
        bot.send_message(chat_id, f"⏰ Напоминание: {text}")
    except Exception as e:
        logger.error(f"Failed to send reminder: {e}")


def send_reminder_with_retry(chat_id: int, text: str, max_retries=3):
    """Функция с повторными попытками"""
    for attempt in range(max_retries):
        try:
            send_reminder(chat_id, text)
            break
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"Failed after {max_retries} attempts: {e}")

