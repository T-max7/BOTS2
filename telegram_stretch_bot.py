import json
import logging
import os
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes

# ===== Settings =====
BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_BOT_TOKEN_HERE")
TZ_NAME = os.getenv("TZ", "Europe/Tallinn")
MESSAGE_TEXT = "Встаем, пора размяться!"
JOB_NAME_PREFIX = "weekday_reminder_"

# File where registered chat IDs are stored.
# In Timeweb this file will be created automatically near this .py file.
CHAT_IDS_FILE = Path(os.getenv("CHAT_IDS_FILE", "chat_ids.json"))

# Optional backward compatibility: if you already have CHAT_ID in Timeweb env,
# the bot can auto-import it into chat_ids.json on first launch.
LEGACY_CHAT_ID = int(os.getenv("CHAT_ID", "0"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def load_chat_ids() -> set[int]:
    """Load registered chat IDs from JSON file."""
    if not CHAT_IDS_FILE.exists():
        return set()

    try:
        data = json.loads(CHAT_IDS_FILE.read_text(encoding="utf-8"))
        return {int(chat_id) for chat_id in data}
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.exception("Could not read %s", CHAT_IDS_FILE, exc_info=exc)
        return set()


def save_chat_ids(chat_ids: set[int]) -> None:
    """Save registered chat IDs to JSON file."""
    CHAT_IDS_FILE.write_text(
        json.dumps(sorted(chat_ids), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def register_chat_id(chat_id: int) -> bool:
    """
    Register chat_id.
    Returns True if it was newly added, False if it already existed.
    """
    chat_ids = load_chat_ids()
    was_new = chat_id not in chat_ids
    chat_ids.add(chat_id)
    save_chat_ids(chat_ids)
    return was_new


def unregister_chat_id(chat_id: int) -> bool:
    """
    Remove chat_id from registration.
    Returns True if it was removed, False if it was not registered.
    """
    chat_ids = load_chat_ids()
    if chat_id not in chat_ids:
        return False

    chat_ids.remove(chat_id)
    save_chat_ids(chat_ids)
    return True


async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the scheduled reminder to all registered chats."""
    chat_ids = load_chat_ids()

    if not chat_ids:
        logger.warning("No registered chats. Skipping reminder.")
        return

    logger.info("Sending scheduled reminder to %s chat(s)", len(chat_ids))

    failed_chat_ids: list[int] = []
    for chat_id in sorted(chat_ids):
        try:
            await context.bot.send_message(chat_id=chat_id, text=MESSAGE_TEXT)
            logger.info("Reminder sent to chat_id=%s", chat_id)
        except (Forbidden, BadRequest) as exc:
            # Forbidden: bot was removed/blocked.
            # BadRequest: chat not found or bot has no access.
            logger.warning("Cannot send reminder to chat_id=%s: %s", chat_id, exc)
            failed_chat_ids.append(chat_id)
        except TelegramError as exc:
            logger.warning("Telegram error for chat_id=%s: %s", chat_id, exc)

    # Remove chats where the bot definitely cannot send messages anymore.
    if failed_chat_ids:
        current_chat_ids = load_chat_ids()
        for chat_id in failed_chat_ids:
            current_chat_ids.discard(chat_id)
        save_chat_ids(current_chat_ids)
        logger.info("Removed unavailable chat IDs: %s", failed_chat_ids)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        register_chat_id(update.effective_chat.id)

    await update.message.reply_text(
        "Бот активен. Этот чат зарегистрирован для напоминаний.\n\n"
        "Команды:\n"
        "/register — зарегистрировать этот чат\n"
        "/unregister — отключить этот чат\n"
        "/chatid — показать chat_id\n"
        "/chats — показать количество зарегистрированных чатов\n"
        "/testmsg — отправить тест во все зарегистрированные чаты\n"
        "/pause — поставить напоминания на паузу\n"
        "/resume — возобновить напоминания\n"
        "/status — показать статус"
    )


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat:
        return

    was_new = register_chat_id(update.effective_chat.id)
    if was_new:
        await update.message.reply_text("Этот чат добавлен в список напоминаний.")
    else:
        await update.message.reply_text("Этот чат уже был в списке напоминаний.")


async def unregister(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat:
        return

    was_removed = unregister_chat_id(update.effective_chat.id)
    if was_removed:
        await update.message.reply_text("Этот чат отключен от напоминаний.")
    else:
        await update.message.reply_text("Этот чат не был зарегистрирован.")


async def chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat:
        await update.message.reply_text(f"chat_id этого чата: {update.effective_chat.id}")


async def chats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_ids = load_chat_ids()
    await update.message.reply_text(f"Зарегистрированных чатов: {len(chat_ids)}")


def get_reminder_jobs(application: Application):
    """Return only reminder jobs managed by this bot."""
    return [
        job
        for job in application.job_queue.jobs()
        if job.name and job.name.startswith(JOB_NAME_PREFIX)
    ]


async def testmsg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_ids = load_chat_ids()

    if not chat_ids:
        await update.message.reply_text(
            "Нет зарегистрированных чатов. Сначала отправь /register в нужном чате."
        )
        return

    logger.info("Manual test message requested for %s chat(s)", len(chat_ids))

    sent = 0
    failed = 0
    for chat_id in sorted(chat_ids):
        try:
            await context.bot.send_message(chat_id=chat_id, text="Тест: бот работает.")
            sent += 1
        except TelegramError as exc:
            failed += 1
            logger.warning("Could not send test message to chat_id=%s: %s", chat_id, exc)

    await update.message.reply_text(
        f"Тестовая рассылка завершена. Отправлено: {sent}. Ошибок: {failed}."
    )


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
    chat_ids = load_chat_ids()

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
    text = (
        f"Статус: {status_text}.\n"
        f"Зарегистрированных чатов: {len(chat_ids)}.\n"
        f"Активных задач: {len(enabled_jobs)} из {len(jobs)}."
    )

    if next_run:
        text += f"\nБлижайшая отправка: {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}"

    await update.message.reply_text(text)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception while processing update", exc_info=context.error)


def schedule_weekday_reminders(application: Application) -> None:
    tz = ZoneInfo(TZ_NAME)

    # Current schedule: every 60 minutes from 10:30 through 19:30 inclusive.
    # If you want every 45 minutes instead, change the last argument from 60 to 45.
    minutes_of_day = list(range(10 * 60 + 30, 19 * 60 + 31, 60))

    for total_minutes in minutes_of_day:
        hour = total_minutes // 60
        minute = total_minutes % 60
        application.job_queue.run_daily(
            callback=send_reminder,
            time=time(hour=hour, minute=minute, tzinfo=tz),
            days=(1, 2, 3, 4, 5),  # Monday-Friday in python-telegram-bot v20+
            name=f"{JOB_NAME_PREFIX}{hour:02d}_{minute:02d}",
        )
        logger.info("Scheduled reminder for %02d:%02d (%s)", hour, minute, TZ_NAME)


def import_legacy_chat_id_if_needed() -> None:
    if LEGACY_CHAT_ID == 0:
        return

    chat_ids = load_chat_ids()
    if LEGACY_CHAT_ID not in chat_ids:
        chat_ids.add(LEGACY_CHAT_ID)
        save_chat_ids(chat_ids)
        logger.info("Imported legacy CHAT_ID=%s into %s", LEGACY_CHAT_ID, CHAT_IDS_FILE)


def validate_config() -> None:
    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        raise ValueError("Укажи BOT_TOKEN через переменную окружения или прямо в коде.")


def main() -> None:
    validate_config()
    import_legacy_chat_id_if_needed()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("unregister", unregister))
    application.add_handler(CommandHandler("chatid", chatid))
    application.add_handler(CommandHandler("chats", chats))
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
