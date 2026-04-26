# -*- coding: utf-8 -*-
"""
PASHA STORE BOT - clean stable build
Features:
- VIP channel sales with Telegram Stars
- Channel cards with photo
- 2 resend-link limit per subscription
- Automatic expiry removal every 30 min
- Admin channel editing including name
- Ad balance + direct channel ad orders
- Admin can add ad balance from user detail
- Auto video transfer: depot channel -> main channel, caption stripped
"""

import os
import re
import io
import csv
import json
import asyncio
import logging
from datetime import datetime, timedelta

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters,
)
from supabase import create_client

# AI sistemi kald\u0131r\u0131ld\u0131. Harici AI paketi gerekmez.

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OWNER_ID = int(os.getenv("OWNER_ID", "957422314"))


DEFAULT_DURATION_DAYS = 30
INVITE_LINK_EXPIRE_MINUTES = 30
MAX_LINK_RESENDS = 2
AD_MIN_TOPUP = 1
BROADCAST_DELAY = 0.05

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pasha-v23")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN yok")
if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL yok")
if not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_KEY yok")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# MENUS
# =========================
MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["\U0001f680 H\u0131zl\u0131 Ba\u015fla", "\U0001f4cc Durumum"],
        ["\U0001f4e2 VIP Kanallar"],
        ["\U0001f4b0 Bakiye", "\U0001f4e3 Reklam Ver"],
        ["\U0001f4c5 \xdcyeli\u011fim", "\U0001f4dc Ge\xe7mi\u015fim"],
        ["\U0001f381 Referans"],
        ["\u2753 SSS"],
        ["\U0001f198 Destek", "\u2139\ufe0f Yard\u0131m"],
    ],
    resize_keyboard=True,
)

ADMIN_MENU = ReplyKeyboardMarkup(
    [
        ["\U0001f451 Admin Panel"],
        ["\U0001f680 H\u0131zl\u0131 Ba\u015fla", "\U0001f4cc Durumum"],
        ["\U0001f4e2 VIP Kanallar"],
        ["\U0001f4b0 Bakiye", "\U0001f4e3 Reklam Ver"],
        ["\U0001f4c5 \xdcyeli\u011fim", "\U0001f4dc Ge\xe7mi\u015fim"],
        ["\U0001f381 Referans"],
        ["\u2753 SSS"],
        ["\U0001f198 Destek", "\u2139\ufe0f Yard\u0131m"],
    ],
    resize_keyboard=True,
)

CANCEL_WORDS = {"iptal", "vazge\xe7", "vazgec", "geri", "cancel", "men\xfc", "menu"}

# =========================
# HELPERS
# =========================
def now_utc() -> datetime:
    return datetime.utcnow()


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def username_of(user):
    return user.username if user and user.username else None


def is_owner(user_id: int) -> bool:
    return int(user_id) == OWNER_ID


def repair_mojibake(text: str) -> str:
    """Best-effort fix for texts like 'ho\xc5\u0178 geldin' -> 'ho\u015f geldin'."""
    if not text:
        return ""
    text = str(text)
    candidates = [text]
    for enc in ("latin1", "cp1252"):
        try:
            candidates.append(text.encode(enc, errors="ignore").decode("utf-8", errors="ignore"))
        except Exception:
            pass
    good_chars = ["\u011f", "\u011e", "\xfc", "\xdc", "\u015f", "\u015e", "\u0131", "\u0130", "\xf6", "\xd6", "\xe7", "\xc7",
                  "\U0001f680", "\U0001f451", "\U0001f4e2", "\U0001f4b0", "\U0001f4e3", "\U0001f4c5", "\U0001f4dc", "\U0001f381", "\u2753", "\U0001f198", "\u2139\ufe0f"]
    for c in candidates:
        if any(ch in c for ch in good_chars):
            return c
    return candidates[-1] if candidates else text


def normalize(text: str) -> str:
    raw = (text or "").strip()
    variants = [raw, repair_mojibake(raw)]
    for t in variants:
        if not t:
            continue
        if "Admin Panel" in t:
            return "admin"
        if "H\u0131zl\u0131" in t or "Hizli" in t:
            return "quick"
        if "Durumum" in t:
            return "status"
        if "VIP Kanallar" in t:
            return "vip"
        if "Bakiye" in t and "Y\xfckle" not in t and "Yukle" not in t:
            return "balance"
        if "Reklam Ver" in t:
            return "ad"
        if "\xdcyeli\u011fim" in t or "Uyeligim" in t:
            return "subs"
        if "Ge\xe7mi\u015fim" in t or "Gecmisim" in t:
            return "history"
        if "Referans" in t:
            return "ref"
        if "SSS" in t:
            return "faq"
        if "Destek" in t:
            return "support"
        if "Yard\u0131m" in t or "Yardim" in t:
            return "help"
    return repair_mojibake(raw)


def is_menu_text(text: str) -> bool:
    return normalize(text) in {"admin", "quick", "status", "vip", "balance", "ad", "subs", "history", "ref", "faq", "support", "help"}


def get_setting(key, default=None):
    try:
        res = supabase.table("settings").select("*").eq("key", key).execute().data or []
        return res[0].get("value") if res else default
    except Exception:
        return default


def set_setting(key, value):
    try:
        rows = supabase.table("settings").select("*").eq("key", key).execute().data or []
        if rows:
            supabase.table("settings").update({"value": str(value)}).eq("key", key).execute()
        else:
            supabase.table("settings").insert({"key": key, "value": str(value)}).execute()
    except Exception as e:
        logger.error("setting error: %s", e)


def maintenance_on():
    return get_setting("maintenance", "off") == "on"


def test_mode_on():
    return get_setting("test_mode", "off") == "on"


async def log_event(action, actor_id=None, target_user_id=None, channel_id=None, details=None):
    try:
        supabase.table("logs").insert({
            "action": action,
            "actor_id": actor_id,
            "target_user_id": target_user_id,
            "channel_id": channel_id,
            "details": details,
        }).execute()
    except Exception:
        pass


def get_admin_role(user_id):
    if is_owner(user_id):
        return "owner"
    try:
        rows = supabase.table("admins").select("*").eq("user_id", int(user_id)).eq("active", True).execute().data or []
        if rows:
            return rows[0].get("role") or "manager"
    except Exception:
        pass
    return None


def is_admin(user_id) -> bool:
    return get_admin_role(user_id) is not None


def can_manage(user_id) -> bool:
    return get_admin_role(user_id) in {"owner", "manager"}


async def save_user(user, referrer_id=None):
    if not user:
        return
    try:
        rows = supabase.table("users").select("*").eq("user_id", user.id).execute().data or []
        payload = {"username": username_of(user)}
        if rows:
            supabase.table("users").update(payload).eq("user_id", user.id).execute()
        else:
            payload.update({
                "user_id": user.id,
                "accepted_terms": True,
                "referrer_id": referrer_id if referrer_id and referrer_id != user.id else None,
                "created_at": now_utc().isoformat(),
            })
            supabase.table("users").insert(payload).execute()
    except Exception as e:
        logger.error("save_user error: %s", e)


async def is_blacklisted(user_id):
    try:
        rows = supabase.table("blacklist").select("*").eq("user_id", int(user_id)).eq("active", True).execute().data or []
        return bool(rows)
    except Exception:
        return False


async def get_channel(channel_id):
    try:
        rows = supabase.table("channels").select("*").eq("id", int(channel_id)).execute().data or []
        return rows[0] if rows else None
    except Exception:
        return None


async def get_subscription(sub_id):
    try:
        rows = supabase.table("subscriptions").select("*").eq("id", int(sub_id)).execute().data or []
        return rows[0] if rows else None
    except Exception:
        return None


def private_channel_link(chat_id, message_id):
    s = str(chat_id)
    if s.startswith("-100"):
        return f"https://t.me/c/{s[4:]}/{message_id}"
    return None


def normalize_link(link):
    link = (link or "").strip()
    if link.startswith("@"):
        return "https://t.me/" + link[1:]
    if link.startswith("t.me/"):
        return "https://" + link
    if link.startswith("http://") or link.startswith("https://"):
        return link
    return None


def risk_words(text):
    risky = ["if\u015fa", "ifsa", "leak", "s\u0131zd\u0131r", "sizdir", "\xe7ocuk", "cocuk", "minor", "re\u015fit", "resit"]
    low = (text or "").lower()
    return [w for w in risky if w in low]

# =========================
# BALANCE
# =========================
def get_balance(user_id):
    try:
        rows = supabase.table("ad_balances").select("*").eq("user_id", int(user_id)).execute().data or []
        if rows:
            return safe_int(rows[0].get("balance"), 0), safe_int(rows[0].get("spent"), 0)
    except Exception:
        pass
    return 0, 0


def ensure_balance_row(user_id):
    balance, _ = get_balance(user_id)
    try:
        rows = supabase.table("ad_balances").select("*").eq("user_id", int(user_id)).execute().data or []
        if not rows:
            supabase.table("ad_balances").insert({"user_id": int(user_id), "balance": 0, "spent": 0}).execute()
    except Exception:
        pass
    return balance


def add_balance(user_id, amount, desc="Bakiye eklendi", order_id=None):
    amount = safe_int(amount, 0)
    if amount <= 0:
        return False
    ensure_balance_row(user_id)
    bal, spent = get_balance(user_id)
    new_bal = bal + amount
    supabase.table("ad_balances").update({"balance": new_bal, "updated_at": now_utc().isoformat()}).eq("user_id", int(user_id)).execute()
    supabase.table("ad_transactions").insert({"user_id": int(user_id), "amount": amount, "type": "credit", "description": desc, "order_id": order_id}).execute()
    return True


def spend_balance(user_id, amount, desc="Bakiye harcand\u0131", order_id=None):
    amount = safe_int(amount, 0)
    ensure_balance_row(user_id)
    bal, spent = get_balance(user_id)
    if amount <= 0 or bal < amount:
        return False
    supabase.table("ad_balances").update({"balance": bal - amount, "spent": spent + amount, "updated_at": now_utc().isoformat()}).eq("user_id", int(user_id)).execute()
    supabase.table("ad_transactions").insert({"user_id": int(user_id), "amount": -amount, "type": "debit", "description": desc, "order_id": order_id}).execute()
    return True


def subtract_balance(user_id, amount, desc="Admin bakiye \xe7\u0131kard\u0131"):
    amount = safe_int(amount, 0)
    if amount <= 0:
        return 0
    ensure_balance_row(user_id)
    bal, spent = get_balance(user_id)
    removed = min(bal, amount)
    new_bal = max(0, bal - amount)
    supabase.table("ad_balances").update({"balance": new_bal, "updated_at": now_utc().isoformat()}).eq("user_id", int(user_id)).execute()
    supabase.table("ad_transactions").insert({"user_id": int(user_id), "amount": -removed, "type": "admin_debit", "description": desc}).execute()
    return removed

# =========================
# START / MENUS
# =========================
def extract_ref(args):
    if not args:
        return None
    raw = args[0]
    if raw.startswith("ref_"):
        raw = raw[4:]
    elif raw.startswith("ref"):
        raw = raw[3:]
    return safe_int(raw, None) if str(raw).isdigit() else None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user, extract_ref(context.args))
    if context.args and context.args[0].startswith("ad_"):
        if await handle_ad_click_start(update, context, context.args[0]):
            return
    if await is_blacklisted(user.id) and not is_admin(user.id):
        await update.message.reply_text("\U0001f6ab Bu botu kullanma yetkin k\u0131s\u0131tland\u0131.")
        return
    await update.message.reply_text(
        "\U0001f44b Pasha VIP admin sistemine ho\u015f geldin." if is_admin(user.id) else "\U0001f44b Pasha VIP sistemine ho\u015f geldin.",
        reply_markup=ADMIN_MENU if is_admin(user.id) else MAIN_MENU,
    )
    await quick_start_message(update.message, is_admin(user.id))


async def quick_start_message(message, admin=False):
    kb = [
        [InlineKeyboardButton("\u2b50 VIP Sat\u0131n Al", callback_data="quick_vip")],
        [InlineKeyboardButton("\U0001f4e3 Reklam Ver", callback_data="quick_ad")],
        [InlineKeyboardButton("\U0001f4cc Durumum", callback_data="quick_status")],
        [InlineKeyboardButton("\U0001f198 Destek", callback_data="quick_support")],
    ]
    await message.reply_text(
        "\U0001f680 H\u0131zl\u0131 Ba\u015fla\n\nNe yapmak istiyorsun?",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user)
    raw = (update.message.text or "").strip()
    key = normalize(raw)

    # Mode cancel/menu fix
    if context.user_data.get("mode") and (raw.lower() in CANCEL_WORDS or is_menu_text(raw)):
        context.user_data.clear()
        if raw.lower() in CANCEL_WORDS:
            await update.message.reply_text("\u2705 \u0130\u015flem iptal edildi.", reply_markup=ADMIN_MENU if is_admin(user.id) else MAIN_MENU)
            return
        # continue selected menu

    if context.user_data.get("mode"):
        await handle_text_mode(update, context)
        return

    if await is_blacklisted(user.id) and not is_admin(user.id):
        await update.message.reply_text("\U0001f6ab Bu botu kullanma yetkin k\u0131s\u0131tland\u0131.")
        return
    if maintenance_on() and not is_admin(user.id):
        await update.message.reply_text("\U0001f527 Bot bak\u0131m modunda. L\xfctfen daha sonra tekrar dene.")
        return

    if key == "admin" and is_admin(user.id):
        await open_admin_panel(update.message)
    elif key == "quick":
        await quick_start_message(update.message, is_admin(user.id))
    elif key == "status":
        await user_status_message(update.message, user.id)
    elif key == "vip":
        await show_vip_channels(update.message, user.id)
    elif key == "balance":
        await show_balance_center(update.message, user.id)
    elif key == "ad":
        await show_ad_channel_choices(update.message, user.id)
    elif key == "subs":
        await show_my_subscriptions(update.message, user.id)
    elif key == "history":
        await my_history(update.message, user.id)
    elif key == "ref":
        await referral_user_message(update.message, context, user.id)
    elif key == "faq":
        await faq_user_message(update.message)
    elif key == "support":
        await support_menu(update.message)
    elif key == "help":
        await help_message(update.message)
    else:
        await update.message.reply_text("Men\xfcden bir se\xe7enek se\xe7ebilirsin.")


async def help_message(message):
    await message.reply_text(
        "\u2139\ufe0f Yard\u0131m\n\n"
        "\U0001f4e2 VIP Kanallar: Sat\u0131n al\u0131nabilir kanallar\u0131 g\xf6sterir.\n"
        "\U0001f4c5 \xdcyeli\u011fim: Aktif abonelik, link g\xf6nderme ve iptal talebi burada.\n"
        "\U0001f4b0 Bakiye: Reklam bakiyeni y\xfckler ve g\xf6sterir.\n"
        "\U0001f4e3 Reklam Ver: Kanal se\xe7ip reklam talebi olu\u015fturur.\n"
        "\U0001f3ac Otomatik Video: Admin panelden depo kanal\u0131n\u0131 ana kanala ba\u011flar.\n"
        "\U0001f198 Destek: Mesaj\u0131n admin paneline d\xfc\u015fer."
    )

# =========================
# VIP SALES
# =========================
async def show_vip_channels(message, user_id):
    try:
        rows = supabase.table("channels").select("*").eq("active", True).order("id").execute().data or []
    except Exception as e:
        logger.error("channels fetch error: %s", e)
        await message.reply_text("\u274c Kanallar y\xfcklenemedi. Admin veritaban\u0131n\u0131 kontrol etmeli.")
        return

    if not rows:
        await message.reply_text("\U0001f4e2 Hen\xfcz aktif VIP kanal yok.")
        return

    await message.reply_text(
        "\U0001f4e2 VIP Kanallar\n\n"
        "Sat\u0131n almak istedi\u011fin kanal kart\u0131ndaki butona bas. \xd6deme tamamlan\u0131nca tek kullan\u0131ml\u0131k giri\u015f linkin otomatik gelir."
    )
    sent_count = 0
    for ch in rows:
        try:
            price = safe_int(ch.get("price"), 0)
            if price < 1 or not ch.get("chat_id") or not ch.get("name"):
                continue
            text = (
                f"\U0001f4e2 {ch.get('name')}\n"
                f"\u2b50 Fiyat: {price} Stars\n"
                f"\u23f3 S\xfcre: {safe_int(ch.get('duration_days'), DEFAULT_DURATION_DAYS)} g\xfcn"
            )
            if ch.get("description"):
                text += f"\n\n\U0001f4dd {ch.get('description')}"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001f441\ufe0f \xd6nizleme", callback_data=f"chprev_{ch['id']}")],
                [InlineKeyboardButton(f"\u2b50 {price} Stars ile Sat\u0131n Al", callback_data=f"buych_{ch['id']}")],
            ])
            if ch.get("photo_url"):
                try:
                    await message.reply_photo(photo=ch.get("photo_url"), caption=text, reply_markup=kb)
                    sent_count += 1
                    continue
                except Exception as e:
                    logger.warning("photo fallback: %s", e)
            await message.reply_text(text, reply_markup=kb)
            sent_count += 1
        except Exception as e:
            logger.error("channel card error: %s", e)

    if sent_count == 0:
        await message.reply_text(
            "\u274c Aktif kanal bulundu ama kart olu\u015fturulamad\u0131.\n"
            "Admin: Kanal ad\u0131, fiyat ve Chat ID alanlar\u0131n\u0131 kontrol et."
        )


async def show_channel_preview(message, channel_id, user_id):
    ch = await get_channel(channel_id)
    if not ch:
        await message.reply_text("\u274c Kanal bulunamad\u0131.")
        return
    price = safe_int(ch.get("price"), 0)
    text = (
        f"\U0001f441\ufe0f Kanal \xd6nizleme\n\n"
        f"\U0001f4e2 {ch.get('name')}\n"
        f"\u2b50 Fiyat: {price} Stars\n"
        f"\u23f3 S\xfcre: {safe_int(ch.get('duration_days'), DEFAULT_DURATION_DAYS)} g\xfcn\n\n"
        f"\U0001f4dd {ch.get('description') or 'A\xe7\u0131klama yok.'}"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"\u2b50 {price} Stars ile Sat\u0131n Al", callback_data=f"buych_{channel_id}")]])
    if ch.get("photo_url"):
        try:
            await message.reply_photo(photo=ch.get("photo_url"), caption=text, reply_markup=kb)
            return
        except Exception:
            pass
    await message.reply_text(text, reply_markup=kb)


async def buy_channel(query, context):
    channel_id = safe_int(query.data.split("_")[1])
    ch = await get_channel(channel_id)
    if not ch or not ch.get("active"):
        await query.message.reply_text("\u274c Kanal aktif de\u011fil.")
        return
    price = safe_int(ch.get("price"), 0)
    if price < 1:
        await query.message.reply_text("\u274c Kanal fiyat\u0131 hatal\u0131.")
        return
    payload = f"vip_{channel_id}_{price}"
    try:
        supabase.table("checkout_intents").insert({
            "user_id": query.from_user.id,
            "username": username_of(query.from_user),
            "item_type": "vip",
            "item_id": channel_id,
            "price": price,
            "payload": payload,
            "status": "started",
        }).execute()
    except Exception:
        pass
    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=f"{ch.get('name')} VIP \xdcyelik",
        description=f"{safe_int(ch.get('duration_days'), DEFAULT_DURATION_DAYS)} g\xfcnl\xfck VIP \xfcyelik.",
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=ch.get("name") or "VIP", amount=price)],
    )


async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = update.message.successful_payment.invoice_payload
    user = update.effective_user
    if payload.startswith("adtopup_"):
        amount = safe_int(payload.split("_")[1])
        add_balance(user.id, amount, "Telegram Stars bakiye y\xfckleme")
        bal, _ = get_balance(user.id)
        await update.message.reply_text(f"\u2705 Bakiye y\xfcklendi: {amount} Stars\nG\xfcncel bakiye: {bal} Stars")
        return

    if payload.startswith("vip_"):
        parts = payload.split("_")
        channel_id = safe_int(parts[1])
        price = safe_int(parts[2])
        ch = await get_channel(channel_id)
        if not ch:
            await update.message.reply_text("\u2705 \xd6deme al\u0131nd\u0131 ama kanal bulunamad\u0131. Admin ile ileti\u015fime ge\xe7.")
            return
        start_date, end_date = await upsert_subscription(user.id, channel_id, safe_int(ch.get("duration_days"), DEFAULT_DURATION_DAYS), price)
        link = await create_and_store_invite(context, user.id, channel_id, ch)
        try:
            supabase.table("sales").insert({
                "user_id": user.id,
                "username": username_of(user),
                "channel_id": channel_id,
                "price": price,
                "payment_payload": payload,
            }).execute()
            supabase.table("checkout_intents").update({"status": "paid"}).eq("payload", payload).execute()
        except Exception:
            pass
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("\u2b50 \xdcyeli\u011fini Uzat", callback_data=f"buych_{channel_id}")]])
        if link:
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    f"\u2705 \xd6deme ba\u015far\u0131l\u0131!\n\n"
                    f"\U0001f4e2 Kanal: {ch.get('name')}\n"
                    f"\U0001f4c5 Ba\u015flang\u0131\xe7: {start_date}\n"
                    f"\U0001f4c5 Biti\u015f: {end_date}\n\n"
                    f"\U0001f517 Tek kullan\u0131ml\u0131k giri\u015f linkin:\n{link}"
                ),
                reply_markup=kb,
            )
        else:
            await context.bot.send_message(
                chat_id=user.id,
                text=(
                    f"\u2705 \xd6deme al\u0131nd\u0131.\n\n"
                    f"\U0001f4e2 Kanal: {ch.get('name')}\n"
                    f"\U0001f4c5 Ba\u015flang\u0131\xe7: {start_date}\n"
                    f"\U0001f4c5 Biti\u015f: {end_date}\n\n"
                    "\u26a0\ufe0f Link \xfcretilemedi. Admin ile ileti\u015fime ge\xe7."
                ),
                reply_markup=kb,
            )
        try:
            await context.bot.send_message(OWNER_ID, f"\u2705 Yeni VIP sat\u0131\u015f\nKullan\u0131c\u0131: {user.id}\nKanal: {ch.get('name')}\nFiyat: {price} Stars")
        except Exception:
            pass


async def upsert_subscription(user_id, channel_id, days, price):
    now = now_utc()
    rows = supabase.table("subscriptions").select("*").eq("user_id", int(user_id)).eq("channel_id", int(channel_id)).eq("status", "active").execute().data or []
    if rows:
        sub = rows[0]
        old_end = parse_dt(sub.get("end_date")) or now
        base = old_end if old_end > now else now
        new_end = base + timedelta(days=days)
        supabase.table("subscriptions").update({
            "end_date": new_end.isoformat(),
            "price": price,
            "link_resend_count": 0,
            "warn_3d_sent": False,
            "warn_1d_sent": False,
        }).eq("id", sub["id"]).execute()
        return sub.get("start_date"), new_end.isoformat()
    end = now + timedelta(days=days)
    supabase.table("subscriptions").insert({
        "user_id": int(user_id),
        "channel_id": int(channel_id),
        "start_date": now.isoformat(),
        "end_date": end.isoformat(),
        "status": "active",
        "price": price,
        "link_resend_count": 0,
    }).execute()
    return now.isoformat(), end.isoformat()


async def create_and_store_invite(context, user_id, channel_id, ch):
    try:
        if not ch.get("chat_id"):
            return None
        expire = int((now_utc() + timedelta(minutes=INVITE_LINK_EXPIRE_MINUTES)).timestamp())
        invite = await context.bot.create_chat_invite_link(
            chat_id=int(ch.get("chat_id")),
            name=f"{ch.get('name')} - {user_id}",
            expire_date=expire,
            member_limit=1,
        )
        link = invite.invite_link
        supabase.table("subscriptions").update({"generated_invite_link": link}).eq("user_id", int(user_id)).eq("channel_id", int(channel_id)).eq("status", "active").execute()
        return link
    except Exception as e:
        logger.error("invite error: %s", e)
        return None


async def show_my_subscriptions(message, user_id):
    rows = supabase.table("subscriptions").select("*").eq("user_id", int(user_id)).eq("status", "active").execute().data or []
    if not rows:
        await message.reply_text("\U0001f4c5 Aktif \xfcyeli\u011fin yok.")
        return
    for sub in rows:
        ch = await get_channel(sub.get("channel_id"))
        name = ch.get("name") if ch else f"Kanal ID {sub.get('channel_id')}"
        used = safe_int(sub.get("link_resend_count"), 0)
        left = max(0, MAX_LINK_RESENDS - used)
        kb = []
        row = []
        if left > 0:
            row.append(InlineKeyboardButton(f"\U0001f517 Link G\xf6nder ({left}/2)", callback_data=f"resend_{sub['id']}"))
        if row:
            kb.append(row)
        kb.append([InlineKeyboardButton("\u2b50 \xdcyeli\u011fi Uzat", callback_data=f"buych_{sub['channel_id']}")])
        await message.reply_text(
            f"\U0001f4c5 Aktif \xdcyelik\n\n\U0001f4e2 {name}\nDurum: {sub.get('status')}\nBiti\u015f: {sub.get('end_date')}\nYeni link hakk\u0131: {left}/2",
            reply_markup=InlineKeyboardMarkup(kb),
        )


async def resend_link(query, context):
    sub_id = safe_int(query.data.split("_")[1])
    sub = await get_subscription(sub_id)
    if not sub or int(sub.get("user_id")) != int(query.from_user.id) or sub.get("status") != "active":
        await query.message.reply_text("\u274c Aktif \xfcyelik bulunamad\u0131.")
        return
    used = safe_int(sub.get("link_resend_count"), 0)
    if used >= MAX_LINK_RESENDS:
        await query.message.reply_text("\u274c Yeni link hakk\u0131n bitti. Admin ile ileti\u015fime ge\xe7ebilirsin.")
        return
    ch = await get_channel(sub.get("channel_id"))
    link = await create_and_store_invite(context, sub.get("user_id"), sub.get("channel_id"), ch)
    if not link:
        await query.message.reply_text("\u274c Link \xfcretilemedi. Botun kanalda admin oldu\u011fundan emin ol.")
        return
    supabase.table("subscriptions").update({"link_resend_count": used + 1}).eq("id", sub_id).execute()
    await query.message.reply_text(f"\U0001f517 Yeni tek kullan\u0131ml\u0131k linkin:\n{link}\n\nKalan hakk\u0131n: {MAX_LINK_RESENDS - used - 1}/2")


async def remove_user_from_channel(context, ch, user_id):
    try:
        if not ch or not ch.get("chat_id"):
            return False
        await context.bot.ban_chat_member(chat_id=int(ch.get("chat_id")), user_id=int(user_id))
        await context.bot.unban_chat_member(chat_id=int(ch.get("chat_id")), user_id=int(user_id), only_if_banned=True)
        return True
    except Exception as e:
        logger.error("remove user error: %s", e)
        return False


async def expire_subscriptions_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        rows = supabase.table("subscriptions").select("*").eq("status", "active").execute().data or []
    except Exception as e:
        logger.error("expire fetch error: %s", e)
        return
    now = now_utc()
    for sub in rows:
        end = parse_dt(sub.get("end_date"))
        if not end or end > now:
            continue
        ch = await get_channel(sub.get("channel_id"))
        removed = await remove_user_from_channel(context, ch, sub.get("user_id"))
        try:
            supabase.table("subscriptions").update({"status": "expired"}).eq("id", sub.get("id")).execute()
        except Exception:
            pass
        try:
            await context.bot.send_message(sub.get("user_id"), "\u26d4 VIP \xfcyelik s\xfcren bitti. Yenilemek i\xe7in VIP Kanallar b\xf6l\xfcm\xfcn\xfc kullanabilirsin.")
        except Exception:
            pass
        await log_event("subscription_expired", None, sub.get("user_id"), sub.get("channel_id"), f"removed={removed}")

# =========================
# USER STATUS / HISTORY / REF
# =========================
async def user_status_message(message, user_id):
    bal, spent = get_balance(user_id)
    active_subs = supabase.table("subscriptions").select("*").eq("user_id", int(user_id)).eq("status", "active").execute().data or []
    pending_ads = supabase.table("ad_orders").select("*").eq("user_id", int(user_id)).eq("status", "pending").execute().data or []
    await message.reply_text(
        f"\U0001f4cc Durumum\n\n"
        f"\U0001f4c5 Aktif \xfcyelik: {len(active_subs)}\n"
        f"\U0001f4b0 Reklam bakiyesi: {bal} Stars\n"
        f"\U0001f4b8 Harcanan reklam bakiyesi: {spent} Stars\n"
        f"\U0001f4e3 Bekleyen reklam: {len(pending_ads)}"
    )


async def my_history(message, user_id):
    sales = supabase.table("sales").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute().data or []
    ads = supabase.table("ad_orders").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute().data or []
    text = "\U0001f4dc Ge\xe7mi\u015fim\n\n"
    text += "\u2b50 VIP Sat\u0131\u015flar\u0131:\n"
    if sales:
        for s in sales:
            ch = await get_channel(s.get("channel_id"))
            text += f"- {ch.get('name') if ch else s.get('channel_id')} | {s.get('price')} Stars | {s.get('created_at')}\n"
    else:
        text += "- Yok\n"
    text += "\n\U0001f4e3 Reklamlar:\n"
    if ads:
        for a in ads:
            text += f"- {a.get('title')} | {a.get('status')} | {a.get('price')} Stars | G\xf6r\xfcnt\xfclenme: {a.get('views_count') or 0} | T\u0131k: {a.get('clicks_count') or 0}\n"
    else:
        text += "- Yok"
    await message.reply_text(text[:3900])


async def referral_user_message(message, context, user_id):
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    rows = supabase.table("users").select("*").eq("user_id", int(user_id)).execute().data or []
    pts = safe_int(rows[0].get("referral_points"), 0) if rows else 0
    await message.reply_text(f"\U0001f381 Referans\n\nSenin linkin:\n{link}\n\nMevcut puan: {pts}")

# =========================
# BALANCE + ADS
# =========================
async def show_balance_center(message, user_id):
    bal, spent = get_balance(user_id)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("\u2b50 Bakiye Ekle", callback_data="bal_topup")],
        [InlineKeyboardButton("\U0001f4e3 Kanallara Reklam Ver", callback_data="bal_ad")],
        [InlineKeyboardButton("\U0001f4c4 Reklamlar\u0131m", callback_data="bal_myads")],
        [InlineKeyboardButton("\U0001f9fe Bakiye Hareketleri", callback_data="bal_tx")],
    ])
    await message.reply_text(f"\U0001f4b0 Reklam Bakiyen\n\nBakiye: {bal} Stars\nHarcanan: {spent} Stars", reply_markup=kb)


async def ask_topup_amount(message, context):
    context.user_data["mode"] = "topup_amount"
    await message.reply_text("\u2b50 Y\xfcklemek istedi\u011fin Stars tutar\u0131n\u0131 yaz.\n\n\xd6rnek: 2500")


async def create_topup_invoice(message, context, amount):
    amount = safe_int(amount)
    if amount < AD_MIN_TOPUP:
        await message.reply_text("\u274c Tutar en az 1 Stars olmal\u0131.")
        return
    await context.bot.send_invoice(
        chat_id=message.chat_id,
        title="Reklam Bakiyesi",
        description=f"{amount} Stars reklam bakiyesi y\xfckleme.",
        payload=f"adtopup_{amount}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Reklam Bakiyesi", amount=amount)],
    )


async def show_ad_channel_choices(message, user_id):
    rows = supabase.table("channels").select("*").eq("active", True).order("id").execute().data or []
    if not rows:
        await message.reply_text("\U0001f4e3 Reklam verilecek aktif kanal yok.")
        return
    bal, _ = get_balance(user_id)
    await message.reply_text(f"\U0001f4e3 Reklam verilecek kanal\u0131 se\xe7.\n\nBakiyen: {bal} Stars")
    for ch in rows:
        price = safe_int(ch.get("ad_price"), 1000)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"\U0001f4e3 Bu kanalda reklam ver - {price} Stars", callback_data=f"adch_{ch['id']}")]])
        await message.reply_text(f"\U0001f4e2 {ch.get('name')}\nReklam fiyat\u0131: {price} Stars", reply_markup=kb)


async def start_ad_for_channel(query, context):
    channel_id = safe_int(query.data.split("_")[1])
    ch = await get_channel(channel_id)
    if not ch or not ch.get("active"):
        await query.message.reply_text("\u274c Kanal aktif de\u011fil.")
        return
    price = safe_int(ch.get("ad_price"), 1000)
    bal, _ = get_balance(query.from_user.id)
    if bal < price and not (is_admin(query.from_user.id) and test_mode_on()):
        await query.message.reply_text(f"\u274c Bakiyen yetersiz.\nGerekli: {price} Stars\nBakiyen: {bal} Stars\n\n\U0001f4b0 Bakiye b\xf6l\xfcm\xfcnden y\xfckleme yapabilirsin.")
        return
    context.user_data["ad_channel_id"] = channel_id
    context.user_data["ad_price"] = price
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("\u26a1 Tek Mesajla Reklam", callback_data="ad_one")],
        [InlineKeyboardButton("\u2728 Haz\u0131r Reklam Olu\u015ftur", callback_data="ad_template")],
        [InlineKeyboardButton("\u274c \u0130ptal", callback_data="flow_cancel")],
    ])
    await query.message.reply_text(
        f"\U0001f4e3 {ch.get('name')} kanal\u0131na reklam ver\nFiyat: {price} Stars\n\nNas\u0131l reklam olu\u015fturmak istiyorsun?",
        reply_markup=kb,
    )


async def ask_ad_one(message, context):
    context.user_data["mode"] = "ad_one"
    await message.reply_text("\u26a1 Reklam\u0131n\u0131 tek mesajla g\xf6nder:\n\nBa\u015fl\u0131k | Metin | Link\n\n\xd6rnek:\nYeni Kanal | G\xfcncel payla\u015f\u0131mlar i\xe7in hemen incele | https://t.me/kanal")


async def ask_ad_template(message, context):
    context.user_data["mode"] = "ad_template"
    await message.reply_text("\u2728 Haz\u0131r reklam i\xe7in \u015funu yaz:\n\nBa\u015fl\u0131k | K\u0131sa a\xe7\u0131klama | Link")


def parse_ad_pipe(text):
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 3:
        return None
    return parts[0], parts[1], parts[2]


async def create_ad_order(message, context, title, body, link):
    user = message.from_user
    channel_id = context.user_data.get("ad_channel_id")
    price = safe_int(context.user_data.get("ad_price"), 0)
    ch = await get_channel(channel_id)
    if not ch:
        await message.reply_text("\u274c Kanal bulunamad\u0131.")
        return
    clean_link = normalize_link(link)
    if not clean_link:
        await message.reply_text("\u274c Link hatal\u0131. https://t.me/... \u015feklinde g\xf6nder.")
        return
    if risk_words(f"{title} {body} {clean_link}"):
        await message.reply_text("\u274c Reklam metni riskli g\xf6r\xfcn\xfcyor. L\xfctfen yasal ve n\xf6tr bir metinle tekrar dene.")
        return
    if not (is_admin(user.id) and test_mode_on()):
        if not spend_balance(user.id, price, f"Reklam talebi: {ch.get('name')}"):
            await message.reply_text("\u274c Bakiyen yetersiz.")
            return
    row = supabase.table("ad_orders").insert({
        "user_id": user.id,
        "username": username_of(user),
        "channel_id": channel_id,
        "target_type": "single",
        "title": title[:80],
        "ad_text": body[:800],
        "link": clean_link,
        "status": "pending",
        "price": price,
    }).execute().data[0]
    context.user_data.clear()
    await message.reply_text("\u2705 Reklam talebin admin onay\u0131na g\xf6nderildi.")
    try:
        await context.bot.send_message(OWNER_ID, f"\U0001f4e3 Yeni reklam talebi\nID: {row['id']}\nKullan\u0131c\u0131: {user.id}\nKanal: {ch.get('name')}\nFiyat: {price} Stars")
    except Exception:
        pass


async def my_ad_orders(message, user_id):
    rows = supabase.table("ad_orders").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute().data or []
    if not rows:
        await message.reply_text("\U0001f4c4 Hen\xfcz reklam talebin yok.")
        return
    text = "\U0001f4c4 Reklamlar\u0131m\n\n"
    for o in rows:
        text += f"ID: {o.get('id')}\nBa\u015fl\u0131k: {o.get('title')}\nDurum: {o.get('status')}\nFiyat: {o.get('price')} Stars\nG\xf6r\xfcnt\xfclenme: {o.get('views_count') or 0}\nT\u0131klama: {o.get('clicks_count') or 0}\nLink: {o.get('published_links') or '-'}\n\n"
    await message.reply_text(text[:3900])


async def handle_ad_click_start(update, context, arg):
    order_id = safe_int(arg.replace("ad_", ""), 0)
    if not order_id:
        return False
    rows = supabase.table("ad_orders").select("*").eq("id", order_id).execute().data or []
    if not rows:
        return False
    order = rows[0]
    try:
        supabase.table("ad_clicks").insert({"order_id": order_id, "user_id": update.effective_user.id}).execute()
        supabase.table("ad_orders").update({"clicks_count": safe_int(order.get("clicks_count"), 0) + 1}).eq("id", order_id).execute()
    except Exception:
        pass
    await update.message.reply_text(f"\U0001f517 Reklam ba\u011flant\u0131s\u0131:\n{order.get('link')}")
    return True

# =========================
# SUPPORT / FAQ
# =========================
async def support_menu(message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001f464 Admin'e Yaz", callback_data="support_admin")],
    ])
    await message.reply_text(
        "\U0001f198 Destek\n\nSorununu tek mesaj olarak yaz. Destek talebin admin paneline d\xfc\u015fer.",
        reply_markup=kb,
    )


async def faq_user_message(message):
    faqs = [
        ("Botu VIP gruba/kanala nas\u0131l ba\u011flar\u0131m?", "Botu ilgili kanal veya gruba admin yap. Mesaj g\xf6nder, kullan\u0131c\u0131 davet et ve kullan\u0131c\u0131 yasakla yetkilerini a\xe7. Sonra kanala id yaz."),
        ("Yeni link hakk\u0131m ka\xe7?", "Her aktif abonelikte en fazla 2 kez yeni link isteyebilirsin."),
        ("\xd6deme yapt\u0131m link gelmedi", "\xdcyeli\u011fim ekran\u0131ndan Link G\xf6nder butonunu dene. Olmazsa destek a\xe7."),
        ("Reklam bakiyesi nedir?", "Kanallara reklam vermek i\xe7in kullan\u0131lan Stars bakiyesidir."),
        ("Otomatik video nas\u0131l \xe7al\u0131\u015f\u0131r?", "Depo kanal\u0131na video at\u0131l\u0131r, bot ana kanala sadece videoyu g\xf6nderir. Caption gitmez."),
    ]
    kb = [[InlineKeyboardButton(q, callback_data=f"faq_{i}")] for i, (q, _) in enumerate(faqs)]
    await message.reply_text("\u2753 S\u0131k Sorulan Sorular", reply_markup=InlineKeyboardMarkup(kb))


async def answer_faq(message, idx):
    faqs = [
        ("Botu VIP gruba/kanala nas\u0131l ba\u011flar\u0131m?", "Botu ilgili kanal veya gruba admin yap. Mesaj g\xf6nder, kullan\u0131c\u0131 davet et ve kullan\u0131c\u0131 yasakla yetkilerini a\xe7. Sonra kanala id yaz."),
        ("Yeni link hakk\u0131m ka\xe7?", "Her aktif abonelikte en fazla 2 kez yeni link isteyebilirsin."),
        ("\xd6deme yapt\u0131m link gelmedi", "\xdcyeli\u011fim ekran\u0131ndan Link G\xf6nder butonunu dene. Olmazsa destek a\xe7."),
        ("Reklam bakiyesi nedir?", "Kanallara reklam vermek i\xe7in kullan\u0131lan Stars bakiyesidir."),
        ("Otomatik video nas\u0131l \xe7al\u0131\u015f\u0131r?", "Depo kanal\u0131na video at\u0131l\u0131r, bot ana kanala sadece videoyu g\xf6nderir. Caption gitmez."),
    ]
    if 0 <= idx < len(faqs):
        q, a = faqs[idx]
        await message.reply_text(f"\u2753 {q}\n\n{a}")

# =========================
# ADMIN
# =========================
async def admin_dashboard_text():
    today = now_utc().date().isoformat()
    sales = supabase.table("sales").select("*").execute().data or []
    active_subs = supabase.table("subscriptions").select("*").eq("status", "active").execute().data or []
    pending_ads = supabase.table("ad_orders").select("*").eq("status", "pending").execute().data or []
    support = supabase.table("support_requests").select("*").eq("status", "open").execute().data or []
    today_sales = [s for s in sales if str(s.get("created_at") or "").startswith(today)]
    return (
        "\U0001f451 Admin Panel\n\n"
        f"Bug\xfcnk\xfc sat\u0131\u015f: {len(today_sales)}\n"
        f"Aktif \xfcyelik: {len(active_subs)}\n"
        f"Bekleyen reklam: {len(pending_ads)}\n"
        f"A\xe7\u0131k destek: {len(support)}\n"
        f"Bak\u0131m modu: {'A\xc7IK' if maintenance_on() else 'KAPALI'}"
    )


async def open_admin_panel(message):
    kb = [
        [InlineKeyboardButton("\U0001f4cc Bekleyen \u0130\u015fler", callback_data="admin_pending")],
        [InlineKeyboardButton("\U0001f4e2 Kanal Ekle", callback_data="admin_add_channel")],
        [InlineKeyboardButton("\U0001f4e2 Kanallar\u0131 Y\xf6net", callback_data="admin_channels")],
        [InlineKeyboardButton("\U0001f50e Kullan\u0131c\u0131 Ara", callback_data="admin_user_search")],
        [InlineKeyboardButton("\U0001f4e3 Reklam Talepleri", callback_data="admin_ads")],
        [InlineKeyboardButton("\U0001f4c4 Reklam Ge\xe7mi\u015fi", callback_data="admin_ad_history")],
        [InlineKeyboardButton("\U0001f198 Destek Talepleri", callback_data="admin_support")],
        [InlineKeyboardButton("\U0001f3ac Otomatik Video", callback_data="admin_video")],
        [InlineKeyboardButton("\U0001f9ea Sistem Testi", callback_data="admin_system_test")],
        [InlineKeyboardButton("\U0001f527 Bak\u0131m A\xe7/Kapat", callback_data="admin_maintenance")],
    ]
    await message.reply_text(await admin_dashboard_text(), reply_markup=InlineKeyboardMarkup(kb))


async def admin_pending(message):
    ads = supabase.table("ad_orders").select("*").eq("status", "pending").execute().data or []
    support = supabase.table("support_requests").select("*").eq("status", "open").execute().data or []
    failed = supabase.table("ad_orders").select("*").eq("status", "failed").execute().data or []
    await message.reply_text(f"\U0001f4cc Bekleyen \u0130\u015fler\n\n\U0001f4e3 Reklam: {len(ads)}\n\U0001f198 Destek: {len(support)}\n\u26a0\ufe0f Ba\u015far\u0131s\u0131z reklam: {len(failed)}")


async def admin_system_test(message, context):
    lines = ["\U0001f9ea Sistem Testi"]
    try:
        supabase.table("users").select("id").limit(1).execute()
        lines.append("\u2705 Supabase ba\u011flant\u0131s\u0131")
    except Exception as e:
        lines.append(f"\u274c Supabase: {e}")
    lines.append("\u2705 Bot \xe7al\u0131\u015f\u0131yor")
    await message.reply_text("\n".join(lines))


async def admin_add_channel_prompt(message, context):
    context.user_data["mode"] = "add_channel"
    await message.reply_text(
        "\U0001f4e2 Kanal ekle\n\nFormat:\nAd | VIP Fiyat | ChatID | S\xfcreG\xfcn | A\xe7\u0131klama | G\xf6rselURL | ReklamFiyat\u0131\n\n\xd6rnek:\nNUDE PLUS+ | 1000 | -1003921378538 | 30 | VIP kanal | https://site.com/a.jpg | 1000"
    )


async def admin_channels(message):
    rows = supabase.table("channels").select("*").order("id").execute().data or []
    if not rows:
        await message.reply_text("\U0001f4e2 Kanal yok.")
        return
    for ch in rows:
        status = "Aktif" if ch.get("active") else "Pasif"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("\u270f\ufe0f Ad", callback_data=f"ched_name_{ch['id']}"), InlineKeyboardButton("\U0001f4b0 VIP Fiyat", callback_data=f"ched_price_{ch['id']}")],
            [InlineKeyboardButton("\U0001f194 Chat ID", callback_data=f"ched_chat_{ch['id']}"), InlineKeyboardButton("\u23f3 S\xfcre", callback_data=f"ched_days_{ch['id']}")],
            [InlineKeyboardButton("\U0001f5bc\ufe0f G\xf6rsel", callback_data=f"ched_photo_{ch['id']}"), InlineKeyboardButton("\U0001f4e3 Reklam Fiyat\u0131", callback_data=f"ched_adprice_{ch['id']}")],
            [InlineKeyboardButton("A\xe7/Kapat", callback_data=f"chtoggle_{ch['id']}"), InlineKeyboardButton("\U0001f5d1\ufe0f Sil", callback_data=f"chdel_{ch['id']}")],
        ])
        await message.reply_text(
            f"\U0001f4e2 Kanal ID: {ch.get('id')}\nAd: {ch.get('name')}\nVIP fiyat: {ch.get('price')}\nReklam fiyat\u0131: {ch.get('ad_price') or 1000}\nChat ID: {ch.get('chat_id')}\nS\xfcre: {ch.get('duration_days')} g\xfcn\nDurum: {status}",
            reply_markup=kb,
        )



async def admin_user_search_prompt(message, context):
    context.user_data["mode"] = "admin_search_user"
    await message.reply_text("\U0001f50e Kullan\u0131c\u0131 ara\n\nUsername veya User ID yaz.\n\n\xd6rnek:\n@SXpasha\n957422314")


async def find_user_by_term(term):
    term = (term or "").strip()
    if not term:
        return None
    clean = term.replace("@", "").strip()
    try:
        if clean.isdigit():
            rows = supabase.table("users").select("*").eq("user_id", int(clean)).execute().data or []
            if rows:
                return rows[0]
        rows = supabase.table("users").select("*").eq("username", clean).execute().data or []
        if rows:
            return rows[0]
        rows = supabase.table("users").select("*").ilike("username", f"%{clean}%").limit(1).execute().data or []
        if rows:
            return rows[0]
    except Exception as e:
        logger.error("find user error: %s", e)
    return None


async def show_admin_user_detail(message, target_user_id):
    rows = supabase.table("users").select("*").eq("user_id", int(target_user_id)).execute().data or []
    user_row = rows[0] if rows else {"user_id": int(target_user_id), "username": None, "created_at": "-"}
    bal, spent = get_balance(target_user_id)
    active_subs = supabase.table("subscriptions").select("*").eq("user_id", int(target_user_id)).eq("status", "active").execute().data or []
    banned = await is_blacklisted(target_user_id)

    kb = [
        [InlineKeyboardButton("\U0001f4b0 Bakiye Ekle", callback_data=f"userbal_{target_user_id}"),
         InlineKeyboardButton("\u2796 Bakiye \xc7\u0131kart", callback_data=f"userbalminus_{target_user_id}")],
        [InlineKeyboardButton("\U0001f4dc Kullan\u0131c\u0131 Ge\xe7mi\u015fi", callback_data=f"userhist_{target_user_id}")],
    ]

    for sub in active_subs:
        ch = await get_channel(sub.get("channel_id"))
        ch_name = ch.get("name") if ch else f"Kanal {sub.get('channel_id')}"
        kb.append([InlineKeyboardButton(f"\u26d4 {ch_name} aboneli\u011fini pasife al", callback_data=f"userdeact_{sub.get('id')}")])

    kb.append([InlineKeyboardButton("\u2705 Ban Kald\u0131r" if banned else "\U0001f6ab Banla", callback_data=f"userban_{target_user_id}")])

    await message.reply_text(
        f"\U0001f464 Kullan\u0131c\u0131 Detay\u0131\n\n"
        f"User ID: {target_user_id}\n"
        f"Username: @{user_row.get('username') or '-'}\n"
        f"Bot ba\u015flatma tarihi: {user_row.get('created_at') or '-'}\n"
        f"Bakiye: {bal} Stars\n"
        f"Harcanan: {spent} Stars\n"
        f"Aktif abonelik: {len(active_subs)}\n"
        f"Ban durumu: {'Banl\u0131' if banned else 'Temiz'}",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def admin_user_history(message, target_user_id):
    urows = supabase.table("users").select("*").eq("user_id", int(target_user_id)).execute().data or []
    u = urows[0] if urows else {}
    sales = supabase.table("sales").select("*").eq("user_id", int(target_user_id)).order("id", desc=True).limit(10).execute().data or []
    txs = supabase.table("ad_transactions").select("*").eq("user_id", int(target_user_id)).order("id", desc=True).limit(15).execute().data or []
    subs = supabase.table("subscriptions").select("*").eq("user_id", int(target_user_id)).order("id", desc=True).limit(10).execute().data or []
    ads = supabase.table("ad_orders").select("*").eq("user_id", int(target_user_id)).order("id", desc=True).limit(10).execute().data or []

    text = f"\U0001f4dc Kullan\u0131c\u0131 Ge\xe7mi\u015fi\n\nUser ID: {target_user_id}\nUsername: @{u.get('username') or '-'}\nBot ba\u015flatma: {u.get('created_at') or '-'}\n\n"

    text += "\u2b50 VIP Sat\u0131n Al\u0131mlar\u0131:\n"
    if sales:
        for s in sales:
            ch = await get_channel(s.get("channel_id"))
            text += f"- {ch.get('name') if ch else s.get('channel_id')} | {s.get('price')} Stars | {s.get('created_at')}\n"
    else:
        text += "- Yok\n"

    text += "\n\U0001f4c5 Abonelikler:\n"
    if subs:
        for sub in subs:
            ch = await get_channel(sub.get("channel_id"))
            text += f"- {ch.get('name') if ch else sub.get('channel_id')} | {sub.get('status')} | {sub.get('start_date')} -> {sub.get('end_date')}\n"
    else:
        text += "- Yok\n"

    text += "\n\U0001f4b0 Bakiye Hareketleri:\n"
    if txs:
        for t in txs:
            text += f"- {t.get('amount')} Stars | {t.get('description')} | {t.get('created_at')}\n"
    else:
        text += "- Yok\n"

    text += "\n\U0001f4e3 Reklamlar:\n"
    if ads:
        for a in ads:
            text += f"- {a.get('title')} | {a.get('status')} | {a.get('price')} Stars | {a.get('created_at')}\n"
    else:
        text += "- Yok\n"

    await message.reply_text(text[:3900])


async def deactivate_user_subscription(query, context, sub_id):
    sub = await get_subscription(sub_id)
    if not sub:
        await query.message.reply_text("\u274c Abonelik bulunamad\u0131.")
        return
    ch = await get_channel(sub.get("channel_id"))
    ok = await remove_user_from_channel(context, ch, sub.get("user_id"))
    supabase.table("subscriptions").update({"status": "inactive"}).eq("id", int(sub_id)).execute()
    await query.message.reply_text("\u2705 Abonelik pasife al\u0131nd\u0131 ve kullan\u0131c\u0131 kanaldan \xe7\u0131kar\u0131ld\u0131." if ok else "\u26a0\ufe0f Abonelik pasife al\u0131nd\u0131 ama kullan\u0131c\u0131 kanaldan \xe7\u0131kar\u0131lamad\u0131. Bot yetkilerini kontrol et.")
    try:
        await context.bot.send_message(sub.get("user_id"), f"\u26d4 {ch.get('name') if ch else 'VIP'} aboneli\u011fin pasife al\u0131nd\u0131.")
    except Exception:
        pass


async def toggle_user_ban(query, target_user_id):
    rows = supabase.table("blacklist").select("*").eq("user_id", int(target_user_id)).execute().data or []
    if rows and rows[0].get("active"):
        supabase.table("blacklist").update({"active": False}).eq("user_id", int(target_user_id)).execute()
        await query.message.reply_text("\u2705 Kullan\u0131c\u0131n\u0131n ban\u0131 kald\u0131r\u0131ld\u0131.")
    elif rows:
        supabase.table("blacklist").update({"active": True, "reason": "Admin ban"}).eq("user_id", int(target_user_id)).execute()
        await query.message.reply_text("\U0001f6ab Kullan\u0131c\u0131 banland\u0131.")
    else:
        supabase.table("blacklist").insert({"user_id": int(target_user_id), "reason": "Admin ban", "active": True}).execute()
        await query.message.reply_text("\U0001f6ab Kullan\u0131c\u0131 banland\u0131.")


async def admin_support_requests(message):
    rows = supabase.table("support_requests").select("*").eq("status", "open").order("id", desc=True).limit(20).execute().data or []
    if not rows:
        await message.reply_text("\U0001f198 A\xe7\u0131k destek talebi yok.")
        return
    for r in rows:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("\u2705 Kapat", callback_data=f"supportclose_{r.get('id')}")]])
        await message.reply_text(
            f"\U0001f198 Destek Talebi\n\nID: {r.get('id')}\nUser ID: {r.get('user_id')}\nUsername: @{r.get('username') or '-'}\nTarih: {r.get('created_at')}\n\nMesaj:\n{r.get('message')}",
            reply_markup=kb,
        )


async def admin_ad_history(message):
    rows = supabase.table("ad_orders").select("*").order("id", desc=True).limit(20).execute().data or []
    if not rows:
        await message.reply_text("\U0001f4c4 Reklam ge\xe7mi\u015fi yok.")
        return
    text = "\U0001f4c4 Reklam Ge\xe7mi\u015fi\n\n"
    for o in rows:
        ch = await get_channel(o.get("channel_id"))
        text += f"ID {o.get('id')} | {ch.get('name') if ch else o.get('channel_id')} | {o.get('status')} | {o.get('price')} Stars | \U0001f441 {o.get('views_count') or 0} | \U0001f446 {o.get('clicks_count') or 0}\n"
    await message.reply_text(text[:3900])


async def admin_ads(message):
    rows = supabase.table("ad_orders").select("*").eq("status", "pending").order("id", desc=True).execute().data or []
    if not rows:
        await message.reply_text("\U0001f4e3 Bekleyen reklam yok.")
        return
    for o in rows:
        ch = await get_channel(o.get("channel_id"))
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("\u2705 Onayla ve Yay\u0131nla", callback_data=f"adapprove_{o['id']}")],
            [InlineKeyboardButton("\u274c Reddet ve \u0130ade Et", callback_data=f"adreject_{o['id']}")],
        ])
        await message.reply_text(
            f"\U0001f4e3 Reklam Talebi\n\nID: {o.get('id')}\nKullan\u0131c\u0131: {o.get('user_id')}\nKanal: {ch.get('name') if ch else o.get('channel_id')}\nFiyat: {o.get('price')} Stars\n\nBa\u015fl\u0131k:\n{o.get('title')}\n\nMetin:\n{o.get('ad_text')}\n\nLink:\n{o.get('link')}",
            reply_markup=kb,
        )


async def publish_ad_order(query, context, order_id):
    rows = supabase.table("ad_orders").select("*").eq("id", int(order_id)).execute().data or []
    if not rows:
        await query.message.reply_text("\u274c Reklam bulunamad\u0131.")
        return
    o = rows[0]
    ch = await get_channel(o.get("channel_id"))
    if not ch or not ch.get("chat_id"):
        await query.message.reply_text("\u274c Kanal Chat ID yok.")
        return
    try:
        bot_username = (await context.bot.get_me()).username
        track_url = f"https://t.me/{bot_username}?start=ad_{order_id}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("\U0001f517 \u0130ncele", url=track_url)]])
        text = f"\U0001f4e3 Sponsorlu Reklam\n\n\U0001f525 {o.get('title')}\n{o.get('ad_text')}"
        sent = await context.bot.send_message(chat_id=int(ch.get("chat_id")), text=text, reply_markup=kb)
        link = private_channel_link(ch.get("chat_id"), sent.message_id)
        supabase.table("ad_orders").update({
            "status": "published",
            "published_at": now_utc().isoformat(),
            "published_links": link,
            "published_chat_count": 1,
        }).eq("id", int(order_id)).execute()
        await query.message.reply_text("\u2705 Reklam yay\u0131nland\u0131.")
        try:
            await context.bot.send_message(o.get("user_id"), f"\u2705 Reklam\u0131n yay\u0131nland\u0131.\nLink: {link or 'Kanal i\xe7inde yay\u0131nland\u0131.'}")
        except Exception:
            pass
    except Exception as e:
        logger.error("publish ad error: %s", e)
        add_balance(o.get("user_id"), safe_int(o.get("price"), 0), "Reklam yay\u0131nlanamad\u0131 iade", order_id)
        supabase.table("ad_orders").update({"status": "failed"}).eq("id", int(order_id)).execute()
        await query.message.reply_text("\u274c Reklam yay\u0131nlanamad\u0131. Bakiye iade edildi. Botun kanalda mesaj g\xf6nderme yetkisini kontrol et.")


async def reject_ad_order(query, context, order_id):
    rows = supabase.table("ad_orders").select("*").eq("id", int(order_id)).execute().data or []
    if not rows:
        await query.message.reply_text("\u274c Reklam bulunamad\u0131.")
        return
    o = rows[0]
    add_balance(o.get("user_id"), safe_int(o.get("price"), 0), "Reklam reddi iadesi", order_id)
    supabase.table("ad_orders").update({"status": "rejected_refunded"}).eq("id", int(order_id)).execute()
    await query.message.reply_text("\u2705 Reklam reddedildi ve bakiye iade edildi.")
    try:
        await context.bot.send_message(o.get("user_id"), "\u274c Reklam talebin reddedildi. Bakiye hesab\u0131na iade edildi.")
    except Exception:
        pass

# =========================
# AUTO VIDEO
# =========================
def save_detected_chat(chat):
    try:
        chat_id = str(chat.id)
        title = getattr(chat, "title", None) or getattr(chat, "username", None) or chat_id
        rows = supabase.table("auto_video_detected_chats").select("*").eq("chat_id", chat_id).execute().data or []
        payload = {"chat_id": chat_id, "title": title, "chat_type": str(getattr(chat, "type", "channel")), "updated_at": now_utc().isoformat()}
        if rows:
            supabase.table("auto_video_detected_chats").update(payload).eq("chat_id", chat_id).execute()
        else:
            supabase.table("auto_video_detected_chats").insert(payload).execute()
    except Exception as e:
        logger.error("save detected chat error: %s", e)


async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post = update.channel_post
    if not post:
        return
    text = (post.text or post.caption or "").strip().lower()
    if post.text and text in {"id", "chat id", "kanal id", "grup id"}:
        save_detected_chat(post.chat)
        await context.bot.send_message(post.chat_id, f"Chat ID:\n{post.chat_id}\n\nKanal kaydedildi. Admin Panel > Otomatik Video b\xf6l\xfcm\xfcnden butonla se\xe7ebilirsin.")
        return
    if post.video:
        await handle_auto_video(post, context)


async def handle_auto_video(post, context):
    src = str(post.chat_id)
    routes = supabase.table("auto_video_routes").select("*").eq("source_chat_id", src).eq("active", True).execute().data or []
    for r in routes:
        exists = supabase.table("auto_video_sent").select("*").eq("route_id", r.get("id")).eq("source_message_id", post.message_id).execute().data or []
        if exists:
            continue
        try:
            sent = await context.bot.send_video(chat_id=int(r.get("target_chat_id")), video=post.video.file_id, caption=None)
            supabase.table("auto_video_sent").insert({
                "route_id": r.get("id"),
                "source_chat_id": src,
                "source_message_id": post.message_id,
                "target_chat_id": str(r.get("target_chat_id")),
                "target_message_id": sent.message_id,
                "video_file_id": post.video.file_id,
            }).execute()
        except Exception as e:
            logger.error("auto video send error: %s", e)


async def auto_video_panel(message):
    routes = supabase.table("auto_video_routes").select("*").order("id", desc=True).execute().data or []
    kb = [[InlineKeyboardButton("\U0001f9ed Butonlu Kurulum", callback_data="av_setup")]]
    await message.reply_text(
        "\U0001f3ac Otomatik Video\n\nDepo kanal\u0131na video att\u0131\u011f\u0131nda ana kanala sadece video gider. Yaz\u0131/caption g\xf6nderilmez.",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    if not routes:
        await message.reply_text("Hen\xfcz rota yok. \xd6nce iki kanala da id yaz, sonra Butonlu Kurulum kullan.")
        return
    for r in routes:
        status = "Aktif" if r.get("active") else "Pasif"
        ikb = InlineKeyboardMarkup([[InlineKeyboardButton("A\xe7/Kapat", callback_data=f"avtoggle_{r['id']}"), InlineKeyboardButton("Sil", callback_data=f"avdel_{r['id']}")]])
        await message.reply_text(f"Rota ID: {r.get('id')}\n{r.get('name') or '-'}\nKaynak: {r.get('source_chat_id')}\nHedef: {r.get('target_chat_id')}\nDurum: {status}", reply_markup=ikb)


async def auto_video_setup_source(message):
    chats = supabase.table("auto_video_detected_chats").select("*").order("updated_at", desc=True).limit(20).execute().data or []
    if not chats:
        await message.reply_text("Kay\u0131tl\u0131 kanal yok. Depo ve ana kanala d\xfcz mesaj olarak id yaz.")
        return
    kb = [[InlineKeyboardButton(f"{c.get('title')} ({c.get('chat_id')})", callback_data=f"avsrc_{c.get('chat_id')}")] for c in chats]
    await message.reply_text("\xd6nce depo/kaynak kanal\u0131n\u0131 se\xe7:", reply_markup=InlineKeyboardMarkup(kb))

# =========================
# TEXT MODES
# =========================
async def handle_text_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    text = (update.message.text or "").strip()
    user = update.effective_user

    try:
        if mode == "topup_amount":
            context.user_data.clear()
            await create_topup_invoice(update.message, context, safe_int(text))

        elif mode == "ad_one":
            parsed = parse_ad_pipe(text)
            if not parsed:
                await update.message.reply_text("\u274c Format: Ba\u015fl\u0131k | Metin | Link")
                return
            await create_ad_order(update.message, context, *parsed)

        elif mode == "ad_template":
            parsed = parse_ad_pipe(text)
            if not parsed:
                await update.message.reply_text("\u274c Format: Ba\u015fl\u0131k | K\u0131sa a\xe7\u0131klama | Link")
                return
            title, short, link = parsed
            body = f"{short}\n\nDetaylar i\xe7in butona bas."
            await create_ad_order(update.message, context, title, body, link)


        elif mode == "support_admin_text":
            context.user_data.clear()
            supabase.table("support_requests").insert({"user_id": user.id, "username": username_of(user), "message": text, "status": "open"}).execute()
            await update.message.reply_text("\u2705 Destek talebin admin\u2019e g\xf6nderildi.")
            try:
                await context.bot.send_message(OWNER_ID, f"\U0001f198 Yeni destek\nUser ID: {user.id}\nMesaj:\n{text}")
            except Exception:
                pass

        elif mode == "add_channel":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 4:
                await update.message.reply_text("\u274c Format: Ad | VIP Fiyat | ChatID | S\xfcreG\xfcn | A\xe7\u0131klama | G\xf6rselURL | ReklamFiyat\u0131")
                return
            payload = {
                "name": parts[0],
                "price": safe_int(parts[1], 0),
                "chat_id": parts[2],
                "duration_days": safe_int(parts[3], DEFAULT_DURATION_DAYS),
                "description": parts[4] if len(parts) > 4 else None,
                "photo_url": parts[5] if len(parts) > 5 and parts[5] != "-" else None,
                "ad_price": safe_int(parts[6], 1000) if len(parts) > 6 else 1000,
                "active": True,
            }
            supabase.table("channels").insert(payload).execute()
            context.user_data.clear()
            await update.message.reply_text("\u2705 Kanal eklendi.")

        elif mode and mode.startswith("edit_channel_"):
            channel_id = context.user_data.get("channel_id")
            field = mode.replace("edit_channel_", "")
            mapping = {
                "name": ("name", text),
                "price": ("price", safe_int(text)),
                "chat": ("chat_id", text),
                "days": ("duration_days", safe_int(text, DEFAULT_DURATION_DAYS)),
                "photo": ("photo_url", None if text == "-" else text),
                "adprice": ("ad_price", safe_int(text, 1000)),
            }
            col, val = mapping[field]
            supabase.table("channels").update({col: val}).eq("id", int(channel_id)).execute()
            context.user_data.clear()
            await update.message.reply_text("\u2705 Kanal bilgisi g\xfcncellendi.")

        elif mode == "admin_search_user":
            found = await find_user_by_term(text)
            context.user_data.clear()
            if not found:
                await update.message.reply_text("\u274c Kullan\u0131c\u0131 bulunamad\u0131. Username veya User ID ile tekrar ara.")
                return
            await show_admin_user_detail(update.message, found.get("user_id"))

        elif mode == "admin_sub_balance":
            target = context.user_data.get("target_user_id")
            amount = safe_int(text)
            if amount <= 0:
                await update.message.reply_text("\u274c Sadece \xe7\u0131kar\u0131lacak tutar\u0131 yaz. \xd6rnek: 1000")
                return
            removed = subtract_balance(target, amount, f"Admin bakiye \xe7\u0131kard\u0131: {user.id}")
            context.user_data.clear()
            await update.message.reply_text(f"\u2705 {target} kullan\u0131c\u0131s\u0131ndan {removed} Stars bakiye \xe7\u0131kar\u0131ld\u0131.")
            try:
                await context.bot.send_message(target, f"\u2796 Admin hesab\u0131ndan {removed} Stars reklam bakiyesi \xe7\u0131kard\u0131.")
            except Exception:
                pass

        elif mode == "admin_add_balance":
            target = context.user_data.get("target_user_id")
            amount = safe_int(text)
            if amount <= 0:
                await update.message.reply_text("\u274c Sadece tutar\u0131 yaz. \xd6rnek: 2500")
                return
            add_balance(target, amount, f"Admin manuel bakiye y\xfckledi: {user.id}")
            context.user_data.clear()
            await update.message.reply_text(f"\u2705 {target} kullan\u0131c\u0131s\u0131na {amount} Stars bakiye eklendi.")
            try:
                await context.bot.send_message(target, f"\u2705 Admin hesab\u0131na {amount} Stars reklam bakiyesi ekledi.")
            except Exception:
                pass

        else:
            context.user_data.clear()
            await update.message.reply_text("\u0130\u015flem anla\u015f\u0131lamad\u0131. Men\xfcden tekrar se\xe7.")
    except Exception as e:
        logger.error("mode error: %s", e)
        context.user_data.clear()
        await update.message.reply_text("\u274c \u0130\u015flem s\u0131ras\u0131nda hata oldu. L\xfctfen tekrar dene.")

# =========================
# CALLBACKS
# =========================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "flow_cancel":
        context.user_data.clear()
        await query.message.reply_text("\u2705 \u0130\u015flem iptal edildi.")
        return
    if data == "quick_vip":
        await show_vip_channels(query.message, user_id); return
    if data == "quick_ad":
        await show_ad_channel_choices(query.message, user_id); return
    if data == "quick_status":
        await user_status_message(query.message, user_id); return
    if data == "quick_support":
        await support_menu(query.message); return
    if data.startswith("faq_"):
        await answer_faq(query.message, safe_int(data.split("_")[1])); return
    if data.startswith("chprev_"):
        await show_channel_preview(query.message, safe_int(data.split("_")[1]), user_id); return
    if data.startswith("buych_"):
        await buy_channel(query, context); return
    if data.startswith("resend_"):
        await resend_link(query, context); return
    # balance / ads user
    if data == "bal_topup":
        await ask_topup_amount(query.message, context); return
    if data == "bal_ad":
        await show_ad_channel_choices(query.message, user_id); return
    if data == "bal_myads":
        await my_ad_orders(query.message, user_id); return
    if data == "bal_tx":
        await balance_transactions(query.message, user_id); return
    if data.startswith("adch_"):
        await start_ad_for_channel(query, context); return
    if data == "ad_one":
        await ask_ad_one(query.message, context); return
    if data == "ad_template":
        await ask_ad_template(query.message, context); return

    # support
    if data == "support_admin":
        context.user_data["mode"] = "support_admin_text"
        await query.message.reply_text("Admin\u2019e iletilecek mesaj\u0131n\u0131 yaz:")
        return

    # admin only from here
    if not is_admin(user_id):
        await query.message.reply_text("\u274c Yetkin yok.")
        return

    if data == "admin_pending": await admin_pending(query.message); return
    if data == "admin_add_channel": await admin_add_channel_prompt(query.message, context); return
    if data == "admin_channels": await admin_channels(query.message); return
    if data == "admin_user_search": await admin_user_search_prompt(query.message, context); return
    if data == "admin_ads": await admin_ads(query.message); return
    if data == "admin_ad_history": await admin_ad_history(query.message); return
    if data == "admin_support": await admin_support_requests(query.message); return
    if data == "admin_video": await auto_video_panel(query.message); return
    if data == "admin_system_test": await admin_system_test(query.message, context); return
    if data == "admin_maintenance":
        set_setting("maintenance", "off" if maintenance_on() else "on")
        await query.message.reply_text("\u2705 Bak\u0131m modu de\u011fi\u015ftirildi."); return

    if data.startswith("ched_"):
        parts = data.split("_")
        field = parts[1]
        ch_id = safe_int(parts[2])
        context.user_data["mode"] = f"edit_channel_{field}"
        context.user_data["channel_id"] = ch_id
        prompts = {
            "name": "Yeni kanal ad\u0131n\u0131 yaz:",
            "price": "Yeni VIP fiyat\u0131n\u0131 yaz:",
            "chat": "Yeni Chat ID yaz:",
            "days": "Yeni s\xfcreyi g\xfcn olarak yaz:",
            "photo": "G\xf6rsel URL yaz. Kald\u0131rmak i\xe7in - yaz:",
            "adprice": "Yeni reklam fiyat\u0131n\u0131 yaz:",
        }
        await query.message.reply_text(prompts.get(field, "Yeni de\u011feri yaz:")); return
    if data.startswith("chtoggle_"):
        ch_id = safe_int(data.split("_")[1])
        ch = await get_channel(ch_id)
        if ch:
            supabase.table("channels").update({"active": not bool(ch.get("active"))}).eq("id", ch_id).execute()
        await query.message.reply_text("\u2705 Kanal durumu de\u011fi\u015ftirildi."); return
    if data.startswith("chdel_"):
        ch_id = safe_int(data.split("_")[1])
        supabase.table("channels").delete().eq("id", ch_id).execute()
        await query.message.reply_text("\u2705 Kanal silindi."); return
    if data.startswith("userbal_"):
        target = safe_int(data.split("_")[1])
        context.user_data["mode"] = "admin_add_balance"
        context.user_data["target_user_id"] = target
        await query.message.reply_text(f"\U0001f4b0 {target} kullan\u0131c\u0131s\u0131na eklenecek bakiyeyi yaz.\n\n\xd6rnek: 2500"); return
    if data.startswith("userbalminus_"):
        target = safe_int(data.split("_")[1])
        context.user_data["mode"] = "admin_sub_balance"
        context.user_data["target_user_id"] = target
        await query.message.reply_text(f"\u2796 {target} kullan\u0131c\u0131s\u0131ndan \xe7\u0131kar\u0131lacak bakiyeyi yaz.\n\n\xd6rnek: 1000"); return
    if data.startswith("userhist_"):
        target = safe_int(data.split("_")[1])
        await admin_user_history(query.message, target); return
    if data.startswith("userdeact_"):
        await deactivate_user_subscription(query, context, safe_int(data.split("_")[1])); return
    if data.startswith("userban_"):
        target = safe_int(data.split("_")[1])
        await toggle_user_ban(query, target); return
    if data.startswith("supportclose_"):
        sid = safe_int(data.split("_")[1])
        supabase.table("support_requests").update({"status": "closed"}).eq("id", sid).execute()
        await query.message.reply_text("\u2705 Destek talebi kapat\u0131ld\u0131."); return
    if data.startswith("adapprove_"):
        await publish_ad_order(query, context, safe_int(data.split("_")[1])); return
    if data.startswith("adreject_"):
        await reject_ad_order(query, context, safe_int(data.split("_")[1])); return
    if data == "av_setup":
        await auto_video_setup_source(query.message); return
    if data.startswith("avsrc_"):
        src = data.replace("avsrc_", "")
        context.user_data["av_source"] = src
        chats = supabase.table("auto_video_detected_chats").select("*").order("updated_at", desc=True).limit(20).execute().data or []
        kb = [[InlineKeyboardButton(f"{c.get('title')} ({c.get('chat_id')})", callback_data=f"avtgt_{c.get('chat_id')}")] for c in chats if str(c.get("chat_id")) != str(src)]
        await query.message.reply_text("\u015eimdi ana/hedef kanal\u0131 se\xe7:", reply_markup=InlineKeyboardMarkup(kb)); return
    if data.startswith("avtgt_"):
        tgt = data.replace("avtgt_", "")
        src = context.user_data.get("av_source")
        if not src:
            await query.message.reply_text("\u274c Kaynak se\xe7imi kayboldu. Tekrar ba\u015flat."); return
        supabase.table("auto_video_routes").insert({"source_chat_id": src, "target_chat_id": tgt, "name": f"{src} -> {tgt}", "active": True, "strip_caption": True}).execute()
        context.user_data.pop("av_source", None)
        await query.message.reply_text("\u2705 Otomatik video aktarma kuruldu. Depo kanal\u0131ndaki videolar ana kanala sadece video olarak gider."); return
    if data.startswith("avtoggle_"):
        rid = safe_int(data.split("_")[1])
        rows = supabase.table("auto_video_routes").select("*").eq("id", rid).execute().data or []
        if rows:
            supabase.table("auto_video_routes").update({"active": not bool(rows[0].get("active"))}).eq("id", rid).execute()
        await query.message.reply_text("\u2705 Rota durumu de\u011fi\u015ftirildi."); return
    if data.startswith("avdel_"):
        rid = safe_int(data.split("_")[1])
        supabase.table("auto_video_routes").delete().eq("id", rid).execute()
        await query.message.reply_text("\u2705 Rota silindi."); return


async def balance_transactions(message, user_id):
    rows = supabase.table("ad_transactions").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute().data or []
    if not rows:
        await message.reply_text("\U0001f9fe Bakiye hareketi yok.")
        return
    text = "\U0001f9fe Bakiye Hareketleri\n\n"
    for r in rows:
        text += f"{r.get('amount')} Stars | {r.get('description')} | {r.get('created_at')}\n"
    await message.reply_text(text[:3900])

# =========================
# APP
# =========================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.ChatType.CHANNEL, channel_post_handler))
app.add_handler(CallbackQueryHandler(callbacks))
app.add_handler(PreCheckoutQueryHandler(precheckout))
app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))

app.job_queue.run_repeating(expire_subscriptions_job, interval=1800, first=60)

print("Pasha Store bot \xe7al\u0131\u015f\u0131yor...")
app.run_polling()
