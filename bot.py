import logging
import os
from datetime import datetime
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

OWNER_ID: int | None = None
_raw_owner = os.environ.get("OWNER_ID", "").strip()
if _raw_owner.isdigit():
    OWNER_ID = int(_raw_owner)

# Состояние создания конкурса: {user_id: {step, data}}
contest_creation: dict = {}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_owner(update: Update) -> bool:
    if OWNER_ID is None:
        return False
    return update.message.from_user.id == OWNER_ID


def is_private(update: Update) -> bool:
    return update.message.chat.type == "private"


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    member = await context.bot.get_chat_member(chat_id, user_id)
    return member.status in ("administrator", "creator")


async def check_private_access(update: Update) -> bool:
    if not is_private(update):
        return True
    user_id = update.message.from_user.id
    if OWNER_ID and user_id == OWNER_ID:
        return True
    if db.whitelist_check(user_id):
        return True
    await update.message.reply_text(
        "🔒 Доступ в ЛС ограничен. Обратитесь к владельцу бота."
    )
    return False


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


def parse_date(s: str) -> datetime | None:
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(s.strip(), fmt)
            if fmt == "%d.%m.%Y":
                dt = dt.replace(hour=0, minute=0, second=0)
            return dt
        except ValueError:
            continue
    return None


def medals(i: int) -> str:
    return ["🥇", "🥈", "🥉"][i] if i < 3 else f"{i + 1}."


# ─── Loks ─────────────────────────────────────────────────────────────────────

async def plus_lok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if not await check_private_access(update):
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

    try:
        await message.delete()
    except Exception:
        pass

    text = f"{mention_text} lock {reason}🔒" if reason else f"{mention_text} получает лок!"
    await context.bot.send_message(
        chat_id=message.chat_id,
        message_thread_id=message.message_thread_id,
        text=text,
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

    try:
        await message.delete()
    except Exception:
        pass

    text = f"{mention_text} теряет лок по причине: {reason}🔓" if reason else f"{mention_text} теряет лок!"
    await context.bot.send_message(
        chat_id=message.chat_id,
        message_thread_id=message.message_thread_id,
        text=text,
    )


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if not await check_private_access(update):
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
        reason_str = f" — {r['reason']}" if r.get("reason") else ""
        icon = "🔒" if r["type"] == "plus" else "🔓"
        sign = "+1" if r["type"] == "plus" else "-1"
        lines.append(f"{icon} {sign}{reason_str} <i>({date})</i>")

    total = db.get_total_loks(target_user["user_id"])
    lines.append(f"\n💎 Итого: <b>{total}</b> {get_lok_word(total)}")

    await message.reply_text("\n".join(lines), parse_mode="HTML")


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if not await check_private_access(update):
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

    for i, row in enumerate(top_users):
        medal = medals(i)
        name = row["first_name"] or row["username"] or f"id{row['user_id']}"
        username_str = f" (@{row['username']})" if row["username"] else ""
        count = row["lok_count"]
        lines.append(f"{medal} {name}{username_str} — <b>{count}</b> {get_lok_word(count)}")

    await message.reply_text("\n".join(lines), parse_mode="HTML")


async def my_loks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if not await check_private_access(update):
        return

    user = message.from_user
    db.ensure_user(user.id, user.username, user.first_name, user.last_name)
    total = db.get_total_loks(user.id)
    name = user.first_name or user.username or "Ты"

    await message.reply_text(f"💎 {name}, у тебя {total} {get_lok_word(total)}!")


# ─── Whitelist ────────────────────────────────────────────────────────────────

async def whitelist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if not is_owner(update):
        await message.reply_text("🔒 Только владелец бота может управлять whitelist.")
        return

    if not context.args:
        await message.reply_text(
            "📋 <b>Whitelist</b>\n\n"
            "/whitelist add 123456789 — добавить по Telegram ID\n"
            "/whitelist remove 123456789 — убрать по Telegram ID\n"
            "/whitelist list — список",
            parse_mode="HTML",
        )
        return

    sub = context.args[0].lower()

    if sub == "list":
        users = db.whitelist_get_all()
        if not users:
            await message.reply_text("📋 Whitelist пуст.")
            return
        lines = ["📋 <b>Whitelist:</b>\n"]
        for u in users:
            uname = f"@{u['username']}" if u["username"] else f"id{u['user_id']}"
            lines.append(f"• {uname} ({u['user_id']})")
        await message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    if sub not in ("add", "remove"):
        await message.reply_text("❌ Используй: add, remove, list")
        return

    if len(context.args) < 2:
        await message.reply_text(f"❌ Укажи Telegram ID: /whitelist {sub} 123456789")
        return

    raw = context.args[1].lstrip("@")

    if raw.lstrip("-").isdigit():
        target_id = int(raw)
        target_username = None
        known = db.get_user_by_id(target_id)
        if known:
            target_username = known.get("username")
    else:
        known = db.get_or_create_user_by_username(raw)
        if not known:
            await message.reply_text("❌ Пользователь не найден. Передай Telegram ID числом.")
            return
        target_id = known["user_id"]
        target_username = known.get("username")

    mention = f"@{target_username}" if target_username else f"id{target_id}"

    if sub == "add":
        newly = db.whitelist_add(target_id, target_username)
        if newly:
            await message.reply_text(f"✅ {mention} ({target_id}) добавлен в whitelist.")
        else:
            await message.reply_text(f"ℹ️ {mention} ({target_id}) уже в whitelist.")
    elif sub == "remove":
        removed = db.whitelist_remove(target_id)
        if removed:
            await message.reply_text(f"✅ {mention} ({target_id}) удалён из whitelist.")
        else:
            await message.reply_text(f"ℹ️ {mention} ({target_id}) не найден в whitelist.")


# ─── Contest ──────────────────────────────────────────────────────────────────

async def finish_contest(context: ContextTypes.DEFAULT_TYPE, contest: dict):
    """Завершает конкурс и объявляет победителей."""
    contest_id = contest["id"]
    chat_id = contest["chat_id"]

    top_users = db.contest_get_top(contest_id, limit=20)
    prizes = db.contest_get_prizes(contest_id)
    prizes_map = {p["place"]: p["prize"] for p in prizes}

    results = []
    for i, user in enumerate(top_users):
        place = i + 1
        results.append({
            "user_id": user["user_id"],
            "place": place,
            "lok_count": user["lok_count"],
            "prize": prizes_map.get(place),
        })

    db.contest_save_results(contest_id, results)
    db.contest_set_status(contest_id, "finished")

    if not results:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🏁 Конкурс <b>{contest['title']}</b> завершён!\n\n😔 Никто не набрал локов за период конкурса.",
            parse_mode="HTML",
        )
        return

    lines = [f"🏁 <b>Конкурс «{contest['title']}» завершён!</b>\n\n🏆 <b>Результаты:</b>\n"]
    for r in results:
        if not r.get("prize"):
            break
        name = db.get_user_by_id(r["user_id"])
        display = f"@{name['username']}" if name and name.get("username") else f"id{r['user_id']}"
        count = r["lok_count"]
        prize = r["prize"]
        medal = medals(r["place"] - 1)
        lines.append(f"{medal} {display} — <b>{count}</b> {get_lok_word(count)} — 🎁 {prize}")

    await context.bot.send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        parse_mode="HTML",
    )


async def contest_job(context: ContextTypes.DEFAULT_TYPE):
    """Джоб — проверяет статусы конкурсов каждую минуту."""
    now = datetime.utcnow()
    contests = db.contest_get_all_pending_and_active()

    for contest in contests:
        start = datetime.fromisoformat(contest["start_at"])
        end = datetime.fromisoformat(contest["end_at"])

        if contest["status"] == "pending" and now >= start:
            db.contest_set_status(contest["id"], "active")
            prizes = db.contest_get_prizes(contest["id"])
            prize_lines = "\n".join(
                f"  {medals(p['place'] - 1)} {p['place']} место — {p['prize']}"
                for p in prizes
            )
            await context.bot.send_message(
                chat_id=contest["chat_id"],
                text=(
                    f"🎉 <b>Конкурс «{contest['title']}» начался!</b>\n\n"
                    f"📅 Конец: <b>{end.strftime('%d.%m.%Y %H:%M')}</b> UTC\n\n"
                    f"🎁 <b>Призы:</b>\n{prize_lines}\n\n"
                    f"Кто наберёт больше локов — тот побеждает! 🔒"
                ),
                parse_mode="HTML",
            )

        elif contest["status"] == "active" and now >= end:
            await finish_contest(context, contest)


async def konkurs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    if message.chat.type == "private":
        await message.reply_text("❌ Конкурсы создаются только в группах!")
        return

    if not context.args:
        # Показать текущий конкурс
        active = db.contest_get_active(message.chat_id)
        if active:
            prizes = db.contest_get_prizes(active["id"])
            prize_lines = "\n".join(
                f"  {medals(p['place'] - 1)} {p['place']} место — {p['prize']}"
                for p in prizes
            )
            end = datetime.fromisoformat(active["end_at"])
            await message.reply_text(
                f"🎯 <b>Активный конкурс: «{active['title']}»</b>\n\n"
                f"📅 Конец: <b>{end.strftime('%d.%m.%Y %H:%M')}</b> UTC\n\n"
                f"🎁 <b>Призы:</b>\n{prize_lines}\n\n"
                f"Используй /konkurs top чтобы увидеть текущий топ.",
                parse_mode="HTML",
            )
        else:
            pending = db.contest_get_pending(message.chat_id)
            if pending:
                start = datetime.fromisoformat(pending["start_at"])
                await message.reply_text(
                    f"⏳ Скоро начнётся конкурс «{pending['title']}»\n"
                    f"📅 Старт: <b>{start.strftime('%d.%m.%Y %H:%M')}</b> UTC",
                    parse_mode="HTML",
                )
            else:
                await message.reply_text(
                    "ℹ️ Активных конкурсов нет.\n\n"
                    "Команды для администраторов:\n"
                    "/konkurs create — создать конкурс\n"
                    "/konkurs top — топ текущего конкурса\n"
                    "/konkurs results — результаты последнего конкурса"
                )
        return

    sub = context.args[0].lower()

    # --- TOP ---
    if sub == "top":
        active = db.contest_get_active(message.chat_id)
        if not active:
            await message.reply_text("❌ Нет активного конкурса.")
            return

        top_users = db.contest_get_top(active["id"], limit=10)
        if not top_users:
            await message.reply_text(f"😔 Пока никто не набрал локов в конкурсе «{active['title']}».")
            return

        prizes = db.contest_get_prizes(active["id"])
        prizes_map = {p["place"]: p["prize"] for p in prizes}

        lines = [f"🏆 <b>Топ конкурса «{active['title']}»:</b>\n"]
        for i, row in enumerate(top_users):
            place = i + 1
            medal = medals(i)
            name = row["first_name"] or row["username"] or f"id{row['user_id']}"
            username_str = f" (@{row['username']})" if row["username"] else ""
            count = row["lok_count"]
            prize_str = f" — 🎁 {prizes_map[place]}" if place in prizes_map else ""
            lines.append(f"{medal} {name}{username_str} — <b>{count}</b> {get_lok_word(count)}{prize_str}")

        await message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    # --- RESULTS ---
    if sub == "results":
        last = db.contest_get_last_finished(message.chat_id)
        if not last:
            await message.reply_text("❌Завершённых конкурсов нет.")
            return

        results = db.contest_get_results(last["id"])
        if not results:
            await message.reply_text(f"😔 В конкурсе «{last['title']}» не было участников.")
            return

        lines = [f"🏁 <b>Результаты конкурса «{last['title']}»:</b>\n"]
        for r in results:
            display = f"@{r['username']}" if r.get("username") else f"id{r['user_id']}"
            count = r["lok_count"]
            prize_str = f" — 🎁 {r['prize']}" if r.get("prize") else ""
            medal = medals(r["place"] - 1)
            lines.append(f"{medal} {display} — <b>{count}</b> {get_lok_word(count)}{prize_str}")

        await message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    # --- CREATE ---
    if sub == "create":
        if not await is_admin(update, context):
            await message.reply_text("❌ Только администраторы могут создавать конкурсы!")
            return

        active = db.contest_get_active(message.chat_id)
        pending = db.contest_get_pending(message.chat_id)
        if active or pending:
            await message.reply_text("❌ Уже есть активный или запланированный конкурс. Дождись его завершения.")
            return

        user_id = message.from_user.id
        contest_creation[user_id] = {
            "step": "title",
            "chat_id": message.chat_id,
            "data": {}
        }

        await message.reply_text(
            "🎯 <b>Создание конкурса</b>\n\n"
            "Шаг 1/4: Введи название конкурса:",
            parse_mode="HTML",
        )
        return

    await message.reply_text("❌ Неизвестная подкоманда. Используй: create, top, results")


async def handle_contest_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает пошаговое создание конкурса через обычные сообщения."""
    message = update.message
    if not message or not message.text:
        return

    user_id = message.from_user.id
    state = contest_creation.get(user_id)
    if not state:
        return

    text = message.text.strip()
    step = state["step"]

    if step == "title":
        state["data"]["title"] = text
        state["step"] = "start_date"
        await message.reply_text(
            "📅 Шаг 2/4: Введи дату и время начала конкурса:\n"
            "Формат: <b>ДД.ММ.ГГГГ ЧЧ:ММ</b> (UTC)\n"
            "Например: <code>01.06.2025 10:00</code>",
            parse_mode="HTML",
        )

    elif step == "start_date":
        dt = parse_date(text)
        if not dt:
            await message.reply_text("❌ Неверный формат. Используй ДД.ММ.ГГГГ ЧЧ:ММ\nНапример: 01.06.2025 10:00")
            return
        state["data"]["start_at"] = dt.isoformat()
        state["step"] = "end_date"
        await message.reply_text(
            "📅 Шаг 3/4: Введи дату и время конца конкурса:\n"
            "Формат: <b>ДД.ММ.ГГГГ ЧЧ:ММ</b> (UTC)\n"
            "Например: <code>30.06.2025 23:59</code>",
            parse_mode="HTML",
        )

    elif step == "end_date":
        dt = parse_date(text)
        if not dt:
            await message.reply_text("❌ Неверный формат. Используй ДД.ММ.ГГГГ ЧЧ:ММ\nНапример: 30.06.2025 23:59")
            return
        start = datetime.fromisoformat(state["data"]["start_at"])
        if dt <= start:
            await message.reply_text("❌ Дата конца должна быть позже даты начала!")
            return
        state["data"]["end_at"] = dt.isoformat()
        state["step"] = "prizes"
        state["data"]["prizes"] = {}
        state["data"]["prize_count"] = None
        await message.reply_text(
            "🎁 Шаг 4/4: Сколько призовых мест?\n"
            "Введи число (например: <code>3</code>)",
            parse_mode="HTML",
        )

    elif step == "prizes":
        if state["data"]["prize_count"] is None:
            try:
                n = int(text)
                if n < 1 or n > 10:
                    raise ValueError
            except ValueError:
                await message.reply_text("❌ Введи число от 1 до 10.")
                return
            state["data"]["prize_count"] = n
            state["data"]["prizes"] = {}
            state["step"] = "prize_entry"
            state["data"]["current_prize_place"] = 1
            await message.reply_text(
                f"🥇 Введи приз для <b>1 места</b>:\n"
                f"Например: <code>30$</code>",
                parse_mode="HTML",
            )

    elif step == "prize_entry":
        place = state["data"]["current_prize_place"]
        state["data"]["prizes"][place] = text
        next_place = place + 1
        total = state["data"]["prize_count"]

        if next_place <= total:
            state["data"]["current_prize_place"] = next_place
            medal = medals(next_place - 1)
            await message.reply_text(
                f"{medal} Введи приз для <b>{next_place} места</b>:",
                parse_mode="HTML",
            )
        else:
            # Всё введено — создаём конкурс
            d = state["data"]
            contest_id = db.contest_create(
                chat_id=state["chat_id"],
                title=d["title"],
                start_at=d["start_at"],
                end_at=d["end_at"],
                created_by=user_id,
            )
            for p, prize in d["prizes"].items():
                db.contest_add_prize(contest_id, p, prize)

            del contest_creation[user_id]

            start = datetime.fromisoformat(d["start_at"])
            end = datetime.fromisoformat(d["end_at"])
            prize_lines = "\n".join(
                f"  {medals(p - 1)} {p} место — {prize}"
                for p, prize in d["prizes"].items()
            )

            await message.reply_text(
                f"✅ <b>Конкурс создан!</b>\n\n"
                f"📌 Название: <b>{d['title']}</b>\n"
                f"📅 Начало: <b>{start.strftime('%d.%m.%Y %H:%M')}</b> UTC\n"
                f"📅 Конец: <b>{end.strftime('%d.%m.%Y %H:%M')}</b> UTC\n\n"
                f"🎁 Призы:\n{prize_lines}",
                parse_mode="HTML",
            )


# ─── Help ─────────────────────────────────────────────────────────────────────

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_access(update):
        return

    text = (
        "🤖 <b>Бот-менеджер локов</b>\n\n"
        "📌 <b>Основные команды:</b>\n"
        "/pluslok @username [причина] — дать лок (только админы)\n"
        "/minuslok @username [причина] — забрать лок (только админы)\n"
        "/history [@username] — история локов\n"
        "/top [дней] — топ по локам\n"
        "/mylok — сколько локов у тебя\n\n"
        "🎯 <b>Конкурсы:</b>\n"
        "/konkurs — инфо об активном конкурсе\n"
        "/konkurs create — создать конкурс (только админы)\n"
        "/konkurs top — топ текущего конкурса\n"
        "/konkurs results — результаты последнего конкурса\n\n"
        "🔒 <b>Доступ в ЛС:</b> только whitelist.\n"
        "/whitelist add/remove/list — управление (только владелец)\n\n"
        "💎 <i>Лок — это знак уважения в чате!</i>"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise ValueError("Укажи BOT_TOKEN в переменных окружения")

    if OWNER_ID is None:
        logger.warning("OWNER_ID не задан! /whitelist будет недоступен.")
    else:
        logger.info(f"Владелец бота: {OWNER_ID}")

    app = Application.builder().token(token).build()

    # Loks
    app.add_handler(CommandHandler(["pluslok", "lok"], plus_lok))
    app.add_handler(CommandHandler(["minuslok", "unlok"], minus_lok))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler(["mylok", "myloks"], my_loks))

    # Whitelist
    app.add_handler(CommandHandler("whitelist", whitelist_cmd))

    # Contest
    app.add_handler(CommandHandler("konkurs", konkurs_cmd))

    # Help
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("start", help_cmd))

    # Обработчик пошагового создания конкурса (текстовые сообщения)
    from telegram.ext import MessageHandler, filters
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_contest_creation))

    # Джоб — проверка конкурсов каждую минуту
    app.job_queue.run_repeating(contest_job, interval=60, first=10)

    logger.info("Бот запущен!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
