import logging
import os
from datetime import time
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ===== Настройки =====
# 1) BOT_TOKEN: токен от BotFather
# 2) CHAT_ID: ID чата, куда бот будет слать уведомления
# 3) TZ: таймзона, например Europe/Moscow или Europe/Tallinn
BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
TZ_NAME = os.getenv("TZ", "Europe/Moscow")
MESSAGE_TEXT = "Встаем, пора размяться!"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет напоминание в заданный чат."""
    await context.bot.send_message(chat_id=CHAT_ID, text=MESSAGE_TEXT)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает, что бот запущен."""
    await update.message.reply_text(
        "Бот активен. Я буду присылать напоминания по будням каждые 45 минут с 10:30 до 19:30."
    )


async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Помогает узнать chat_id текущего чата."""
    if update.effective_chat:
        await update.message.reply_text(f"chat_id этого чата: {update.effective_chat.id}")


def schedule_weekday_reminders(application: Application) -> None:
    """
    Добавляет задачи на точные слоты по будням:
    10:30, 11:15, 12:00, ..., 19:30.
    """
    tz = ZoneInfo(TZ_NAME)
    minutes_of_day = list(range(10 * 60 + 30, 19 * 60 + 31, 45))

    for total_minutes in minutes_of_day:
        hour = total_minutes // 60
        minute = total_minutes % 60
        application.job_queue.run_daily(
            callback=send_reminder,
            time=time(hour=hour, minute=minute, tzinfo=tz),
            days=(0, 1, 2, 3, 4),  # понедельник-пятница
            name=f"weekday_reminder_{hour:02d}_{minute:02d}",
        )
        logger.info("Scheduled reminder for %02d:%02d (%s)", hour, minute, TZ_NAME)


def validate_config() -> None:
    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        raise ValueError("Укажи BOT_TOKEN через переменную окружения или прямо в коде.")
    if CHAT_ID == 0:
        raise ValueError("Укажи CHAT_ID через переменную окружения. Сначала напиши боту /chatid в нужном чате.")


def main() -> None:
    validate_config()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("chatid", chatid))

    schedule_weekday_reminders(application)

    logger.info("Bot started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
