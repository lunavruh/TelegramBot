import logging
import os
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from database import Database

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database("loks.db")


def get_lok_word(count: int) -> str:
    if 11 <= count % 100 <= 14:
        return "локов"
    last = count % 10
    if last == 1:
        return "лок"
    elif 2 <= last <= 4:
        return "лока"
    else:
        return "локов"


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    member = await context.bot.get_chat_member(chat_id, user_id)
    return member.status in ("administrator", "creator")


async def plus_lok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if message.chat.type == "private":
        await message.reply_text("❌ Эта команда работает только в группах!")
        return

    if not await is_admin(update, context):
        await message.reply_text("❌ Только администраторы могут давать локи!")
        return

    target_user = None
    mention_text = None

    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                username = message.text[entity.offset + 1: entity.offset + entity.length]
                mention_text = f"@{username}"
                target_user = db.get_or_create_user_by_username(username)
                break
            elif entity.type == "text_mention" and entity.user:
                u = entity.user
                db.ensure_user(u.id, u.username, u.first_name, u.last_name)
                mention_text = u.first_name or f"@{u.username}"
                target_user = {
                    "user_id": u.id,
                    "username": u.username,
                    "first_name": u.first_name,
                    "last_name": u.last_name,
                }
                break

    if not target_user:
        await message.reply_text("❌ Укажи пользователя: /pluslok @username [причина]")
        return

    if target_user["user_id"] == message.from_user.id:
        await message.reply_text("❌ Нельзя давать лок самому себе!")
        return

    full_text = message.text or ""
    parts = full_text.split(maxsplit=2)
    reason = parts[2].strip() if len(parts) >= 3 else None

    db.ensure_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name,
    )

    db.add_lok(
        receiver_id=target_user["user_id"],
        giver_id=message.from_user.id,
        chat_id=message.chat_id,
        reason=reason,
    )

    total = db.get_total_loks(target_user["user_id"])

    try:
        await message.delete()
    except Exception:
        pass

    if reason:
        text = f"{mention_text} 🔒 {reason}\n💎 Локов: {total}"
    else:
        text = f"{mention_text} получает лок!\n💎 Локов: {total}"

    await context.bot.send_message(
        chat_id=message.chat_id,
        message_thread_id=message.message_thread_id,
        text=text
    )


async def minus_lok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if message.chat.type == "private":
        await message.reply_text("❌ Эта команда работает только в группах!")
        return

    if not await is_admin(update, context):
        await message.reply_text("❌ Только администраторы могут забирать локи!")
        return

    target_user = None
    mention_text = None

    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                username = message.text[entity.offset + 1: entity.offset + entity.length]
                mention_text = f"@{username}"
                target_user = db.get_or_create_user_by_username(username)
                break
            elif entity.type == "text_mention" and entity.user:
                u = entity.user
                db.ensure_user(u.id, u.username, u.first_name, u.last_name)
                mention_text = u.first_name or f"@{u.username}"
                target_user = {
                    "user_id": u.id,
                    "username": u.username,
                    "first_name": u.first_name,
                    "last_name": u.last_name,
                }
                break

    if not target_user:
        await message.reply_text("❌ Укажи пользователя: /minuslok @username [причина]")
        return

    if target_user["user_id"] == message.from_user.id:
        await message.reply_text("❌ Нельзя забирать лок у самого себя!")
        return

    total = db.get_total_loks(target_user["user_id"])
    if total <= 0:
        await message.reply_text("❌ У пользователя нет локов!")
        return

    full_text = message.text or ""
    parts = full_text.split(maxsplit=2)
    reason = parts[2].strip() if len(parts) >= 3 else None

    db.ensure_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name,
    )

    db.remove_lok(receiver_id=target_user["user_id"], reason=reason)
    total = db.get_total_loks(target_user["user_id"])

    try:
        await message.delete()
    except Exception:
        pass

    if reason:
        text = f"{mention_text} 🔓 -{reason}\n💎 Локов: {total}"
    else:
        text = f"{mention_text} теряет лок!\n💎 Локов: {total}"

    await context.bot.send_message(
        chat_id=message.chat_id,
        message_thread_id=message.message_thread_id,
        text=text
    )


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    target_user = None
    mention_text = None

    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                username = message.text[entity.offset + 1: entity.offset + entity.length]
                mention_text = f"@{username}"
                target_user = db.get_or_create_user_by_username(username)
                break
            elif entity.type == "text_mention" and entity.user:
                u = entity.user
                mention_text = u.first_name or f"@{u.username}"
                target_user = {
                    "user_id": u.id,
                    "username": u.username,
                    "first_name": u.first_name,
                    "last_name": u.last_name,
                }
                break

    if not target_user:
        user = message.from_user
        db.ensure_user(user.id, user.username, user.first_name, user.last_name)
        target_user = {
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }
        mention_text = user.first_name or f"@{user.username}"

    records = db.get_history(target_user["user_id"])

    if not records:
        await message.reply_text(f"📋 У {mention_text} пока нет истории локов.")
        return

    lines = [f"📋 <b>История локов — {mention_text}:</b>\n"]
    for r in records:
        date = r["given_at"][:10]
        if r["type"] == "plus":
            reason_str = f" — {r['reason']}" if r.get("reason") else ""
            lines.append(f"🔒 +1{reason_str} <i>({date})</i>")
        else:
            reason_str = f" — {r['reason']}" if r.get("reason") else ""
            lines.append(f"🔓 -1{reason_str} <i>({date})</i>")

    total = db.get_total_loks(target_user["user_id"])
    lines.append(f"\n💎 Итого: <b>{total}</b> {get_lok_word(total)}")

    await message.reply_text("\n".join(lines), parse_mode="HTML")


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    days = None
    if context.args:
        try:
            days = int(context.args[0])
            if days <= 0:
                raise ValueError
        except ValueError:
            await message.reply_text("❌ Укажи корректное количество дней: /top 30")
            return

    top_users = db.get_top(days=days, limit=10)

    if not top_users:
        period = f"за {days} {_day_word(days)}" if days else "за всё время"
        await message.reply_text(f"😔 Пока нет локов {period}.")
        return

    period_str = f"за {days} {_day_word(days)}" if days else "за всё время"
    lines = [f"🏆 <b>Топ по локам {period_str}:</b>\n"]

    medals = ["🥇", "🥈", "🥉"]
    for i, row in enumerate(top_users):
        medal = medals[i] if i < 3 else f"{i + 1}."
        name = row["first_name"] or row["username"] or f"id{row['user_id']}"
        username_str = f" (@{row['username']})" if row["username"] else ""
        count = row["lok_count"]
        lines.append(f"{medal} {name}{username_str} — <b>{count}</b> {get_lok_word(count)}")

    await message.reply_text("\n".join(lines), parse_mode="HTML")


def _day_word(days: int) -> str:
    if 11 <= days % 100 <= 14:
        return "дней"
    last = days % 10
    if last == 1:
        return "день"
    elif 2 <= last <= 4:
        return "дня"
    else:
        return "дней"


async def my_loks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    user = message.from_user
    db.ensure_user(user.id, user.username, user.first_name, user.last_name)
    total = db.get_total_loks(user.id)
    name = user.first_name or user.username or "Ты"

    await message.reply_text(
        f"💎 {name}, у тебя {total} {get_lok_word(total)}!"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 <b>Бот-менеджер локов</b>\n\n"
        "📌 <b>Команды:</b>\n"
        "/pluslok @username [предмет] — дать лок (только админы)\n"
        "/minuslok @username [причина] — забрать лок (только админы)\n"
        "/history @username — история локов пользователя\n"
        "/top — топ по локам за всё время\n"
        "/top 30 — топ за 30 дней\n"
        "/mylok — сколько локов у тебя\n"
        "/help — это сообщение\n\n"
        "💎 <i>Лок — это знак уважения в чате!</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise ValueError("Укажи BOT_TOKEN в переменных окружения или в .env файле")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler(["pluslok", "lok"], plus_lok))
    app.add_handler(CommandHandler(["minuslok", "unlok"], minus_lok))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler(["mylok", "myloks"], my_loks))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("start", help_cmd))

    logger.info("Бот запущен!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
