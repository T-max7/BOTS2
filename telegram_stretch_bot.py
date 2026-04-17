import logging
import os
from datetime import time
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ===== Settings =====
BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
TZ_NAME = os.getenv("TZ", "Europe/Tallinn")
MESSAGE_TEXT = "Встаем, пора размяться!"
JOB_NAME_PREFIX = "weekday_reminder_"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the scheduled reminder to the configured chat."""
    logger.info("Sending scheduled reminder to chat_id=%s", CHAT_ID)
    await context.bot.send_message(chat_id=CHAT_ID, text=MESSAGE_TEXT)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Бот активен. Команды:\n"
        "/chatid — показать chat_id\n"
        "/testmsg — отправить тестовое сообщение\n"
        "/pause — поставить напоминания на паузу\n"
        "/resume — возобновить напоминания\n"
        "/status — показать статус"
    )


async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        await update.message.reply_text(f"chat_id этого чата: {update.effective_chat.id}")


def get_reminder_jobs(application: Application):
    """Return only reminder jobs managed by this bot."""
    return [
        job
        for job in application.job_queue.jobs()
        if job.name and job.name.startswith(JOB_NAME_PREFIX)
    ]


async def testmsg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("Manual test message requested")
    await context.bot.send_message(chat_id=CHAT_ID, text="Тест: бот работает.")
    await update.message.reply_text("Тестовое сообщение отправлено.")


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    jobs = get_reminder_jobs(context.application)
    changed = 0
    for job in jobs:
        if job.enabled:
            job.enabled = False
            changed += 1

    logger.info("Pause requested. Disabled jobs: %s", changed)
    if changed:
        await update.message.reply_text("Напоминания поставлены на паузу.")
    else:
        await update.message.reply_text("Напоминания уже были на паузе.")


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    jobs = get_reminder_jobs(context.application)
    changed = 0
    for job in jobs:
        if not job.enabled:
            job.enabled = True
            changed += 1

    logger.info("Resume requested. Enabled jobs: %s", changed)
    if changed:
        await update.message.reply_text("Напоминания снова включены.")
    else:
        await update.message.reply_text("Напоминания уже были активны.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    jobs = get_reminder_jobs(context.application)
    if not jobs:
        await update.message.reply_text("Задачи напоминаний не найдены.")
        return

    enabled_jobs = [job for job in jobs if job.enabled]
    paused = len(enabled_jobs) == 0
    next_run = None

    if enabled_jobs:
        next_values = [job.next_t for job in enabled_jobs if job.next_t is not None]
        if next_values:
            next_run = min(next_values)

    status_text = "на паузе" if paused else "активны"
    if next_run:
        await update.message.reply_text(
            f"Статус: {status_text}.\n"
            f"Активных задач: {len(enabled_jobs)} из {len(jobs)}.\n"
            f"Ближайшая отправка: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )
    else:
        await update.message.reply_text(
            f"Статус: {status_text}.\n"
            f"Активных задач: {len(enabled_jobs)} из {len(jobs)}."
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception while processing update", exc_info=context.error)


def schedule_weekday_reminders(application: Application) -> None:
    tz = ZoneInfo(TZ_NAME)
    minutes_of_day = list(range(10 * 60 + 30, 19 * 60 + 31, 45))

    for total_minutes in minutes_of_day:
        hour = total_minutes // 60
        minute = total_minutes % 60
        application.job_queue.run_daily(
            callback=send_reminder,
            time=time(hour=hour, minute=minute, tzinfo=tz),
            days=(0, 1, 2, 3, 4),
            name=f"{JOB_NAME_PREFIX}{hour:02d}_{minute:02d}",
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
    application.add_handler(CommandHandler("testmsg", testmsg))
    application.add_handler(CommandHandler("pause", pause))
    application.add_handler(CommandHandler("resume", resume))
    application.add_handler(CommandHandler("status", status))
    application.add_error_handler(error_handler)

    schedule_weekday_reminders(application)

    logger.info("Bot started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
