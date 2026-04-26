# -*- coding: utf-8 -*-
import os
import io
import csv
import random
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

# =========================================================
# PASHA VIP BOT - V6 FIXED
# Only /start is used. Everything else is buttons + guided text.
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OWNER_ID = int(os.getenv("OWNER_ID", "957422314"))

DEFAULT_DURATION_DAYS = 30
INVITE_LINK_EXPIRE_MINUTES = 30
BROADCAST_DELAY_SECONDS = 0.05
ABANDONED_REMINDER_HOURS = 2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pasha-v6")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN Railway Variables i\u00e7inde yok.")
if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL Railway Variables i\u00e7inde yok.")
if not SUPABASE_KEY:
    raise ValueError("SUPABASE_KEY Railway Variables i\u00e7inde yok.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["\U0001f680 H\u0131zl\u0131 Ba\u015fla", "\U0001f4cc Durumum"],
        ["\U0001f4e2 VIP Kanallar"],
        ["\U0001f4b0 Bakiye", "\U0001f4e3 Reklam Ver"],
        ["\U0001f4c5 \u00dcyeli\u011fim", "\U0001f4dc Ge\u00e7mi\u015fim"],
        ["\U0001f381 Referans"],
        ["\U0001f39f\ufe0f Kupon Gir"],
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
        ["\U0001f4c5 \u00dcyeli\u011fim", "\U0001f4dc Ge\u00e7mi\u015fim"],
        ["\U0001f381 Referans"],
        ["\U0001f39f\ufe0f Kupon Gir"],
        ["\u2753 SSS"],
        ["\U0001f198 Destek", "\u2139\ufe0f Yard\u0131m"],
    ],
    resize_keyboard=True,
)

LABEL_TO_KEY = {
    "\\U0001f680 H\\u0131zl\\u0131 Ba\\u015fla": "Hizli Basla",
    "\\U0001f680 Hizli Basla": "Hizli Basla",
    "\\U0001f4cc Durumum": "Durumum",
    "\U0001f451 Admin Panel": "Admin Panel",
    "\U0001f4e2 VIP Kanallar": "VIP Kanallar",
    "\U0001f4e6 Paketler": "Paketler",
    "\U0001f4c5 \u00dcyeli\u011fim": "Uyeligim",
    "\U0001f4c5 Uyeligim": "Uyeligim",
    "\U0001f4dc Ge\u00e7mi\u015fim": "Gecmisim",
    "\U0001f4dc Gecmisim": "Gecmisim",
    "\u274c \u0130ptal Talebi": "Iptal Talebi",
    "\u274c Iptal Talebi": "Iptal Talebi",
    "\U0001f381 Referans": "Referans",
    "\U0001f3c6 Liderlik": "Liderlik",
    "\U0001f389 \u00c7ekili\u015f": "Cekilis",
    "\U0001f389 Cekilis": "Cekilis",
    "\U0001f39f\ufe0f Kupon Gir": "Kupon Gir",
    "\U0001f39f Kupon Gir": "Kupon Gir",
    "\U0001f4b0 Bakiye": "Bakiye Merkezi",
    "\U0001f4b0 Bakiyem": "Bakiyem",
    "\u2b50 Bakiye Y\u00fckle": "Bakiye Yukle",
    "\u2b50 Bakiye Yukle": "Bakiye Yukle",
    "\U0001f4e3 Reklam Ver": "Reklam Ver",
    "\U0001f4c4 Reklamlar\u0131m": "Reklamlarim",
    "\U0001f4c4 Reklamlarim": "Reklamlarim",
    "\u2753 SSS": "SSS",
    "\U0001f198 Destek": "Destek",
    "\u2139\ufe0f Yard\u0131m": "Yardim",
    "\u2139 Yard\u0131m": "Yardim",
    "\u2139\ufe0f Yardim": "Yardim",
    "\u2139 Yardim": "Yardim",
    "Admin Panel": "Admin Panel",
    "Hizli Basla": "Hizli Basla",
    "HÄ±zlÄ± BaÅla": "Hizli Basla",
    "Durumum": "Durumum",
    "VIP Kanallar": "VIP Kanallar",
    "Paketler": "Paketler",
    "Uyeligim": "Uyeligim",
    "\u00dcyeli\u011fim": "Uyeligim",
    "Gecmisim": "Gecmisim",
    "Ge\u00e7mi\u015fim": "Gecmisim",
    "Iptal Talebi": "Iptal Talebi",
    "\u0130ptal Talebi": "Iptal Talebi",
    "Referans": "Referans",
    "Liderlik": "Liderlik",
    "Cekilis": "Cekilis",
    "\u00c7ekili\u015f": "Cekilis",
    "Kupon Gir": "Kupon Gir",
    "Bakiye": "Bakiye Merkezi",
    "Bakiye Merkezi": "Bakiye Merkezi",
    "Bakiyem": "Bakiyem",
    "Bakiye Yukle": "Bakiye Yukle",
    "Bakiye Y\u00fckle": "Bakiye Yukle",
    "Reklam Ver": "Reklam Ver",
    "Reklamlarim": "Reklamlarim",
    "Reklamlar\u0131m": "Reklamlarim",
    "SSS": "SSS",
    "Destek": "Destek",
    "Yardim": "Yardim",
    "Yard\u0131m": "Yardim",
}

def normalize_menu_text(text: str) -> str:
    text = (text or "").strip()
    return LABEL_TO_KEY.get(text, text)

MENU_TEXTS = set(LABEL_TO_KEY.values()) | set(LABEL_TO_KEY.keys())
CANCEL_TEXTS = {"iptal", "\u0130ptal", "cancel", "Cancel", "vazge\u00e7", "vazgec", "geri", "men\u00fc", "menu"}
DEFAULT_GROUP_FAQS = [
    (
        "Botu VIP gruba/kanala nas\u0131l ba\u011flar\u0131m?",
        "Botu VIP grup veya kanala y\u00f6netici olarak ekle. Mesaj g\u00f6nder, kullan\u0131c\u0131 davet et ve kullan\u0131c\u0131 yasakla yetkilerini a\u00e7. Sonra grup/kanal i\u00e7ine d\u00fcz mesaj olarak id yaz; bot -100 ile ba\u015flayan Chat ID verir.",
    ),
    (
        "Kanal ID ile grup ID ayn\u0131 m\u0131?",
        "\u0130kisi de Chat ID olarak kullan\u0131l\u0131r. Telegram s\u00fcper gruplar ve kanallar genelde -100 ile ba\u015flayan ID verir. Bot VIP link \u00fcretirken bu ID'yi kullan\u0131r.",
    ),
    (
        "Bot kullan\u0131c\u0131y\u0131 gruba direkt ekleyebilir mi?",
        "Hay\u0131r. Telegram botlar\u0131 kullan\u0131c\u0131y\u0131 zorla gruba/kanala ekleyemez. Bot tek kullan\u0131ml\u0131k davet linki \u00fcretir; kullan\u0131c\u0131 linke bas\u0131p kat\u0131l\u0131r.",
    ),
    (
        "Davet linki \u00e7al\u0131\u015fm\u0131yor, ne yapmal\u0131y\u0131m?",
        "\u00dcyeli\u011fim b\u00f6l\u00fcm\u00fcnden Yeni link g\u00f6nder butonuna bas. Link yine olu\u015fmuyorsa bot VIP grupta/kanalda admin de\u011fildir veya kullan\u0131c\u0131 davet et yetkisi kapal\u0131d\u0131r.",
    ),
    (
        "VIP grup mu kanal m\u0131 kullanmal\u0131y\u0131m?",
        "Sadece i\u00e7erik yay\u0131nlayacaksan kanal daha temizdir. \u00dcyelerin konu\u015fmas\u0131n\u0131 istiyorsan grup kullan. Sat\u0131\u015f ve \u00fcyelik sistemi ikisinde de \u00e7al\u0131\u015f\u0131r.",
    ),
    (
        "Grup gizli mi olmal\u0131?",
        "Evet. VIP eri\u015fim sat\u0131yorsan grup/kanal gizli olmal\u0131. Kullan\u0131c\u0131lar sadece botun \u00fcretti\u011fi tek kullan\u0131ml\u0131k linkle girmeli.",
    ),
]

BAD_TEXT_MARKERS = ("\u00c3", "\u00c4", "\u00c5", "\u00f0", "\ufffd")

def is_bad_text(value) -> bool:
    return any(marker in str(value or "") for marker in BAD_TEXT_MARKERS)

def clean_faq_rows(rows):
    cleaned = []
    seen = set()
    for row in rows or []:
        q = (row.get("question") or "").strip()
        a = (row.get("answer") or "").strip()
        if not q or is_bad_text(q) or is_bad_text(a):
            continue
        key = q.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(row)
    return cleaned

# =========================================================
# BASIC HELPERS
# =========================================================

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


def safe_username(user):
    return user.username if user and user.username else None


def is_owner(user_id) -> bool:
    return int(user_id) == OWNER_ID


def get_setting(key, default=None):
    try:
        res = supabase.table("settings").select("*").eq("key", key).execute()
        if res.data:
            return res.data[0].get("value")
    except Exception as e:
        logger.warning("Setting okunamadi: %s", e)
    return default


def set_setting(key, value):
    value = str(value)
    res = supabase.table("settings").select("*").eq("key", key).execute()
    if res.data:
        supabase.table("settings").update({"value": value}).eq("key", key).execute()
    else:
        supabase.table("settings").insert({"key": key, "value": value}).execute()


def maintenance_on():
    return get_setting("maintenance", "off") == "on"


def campaign_active():
    if get_setting("campaign_enabled", "off") != "on":
        return False
    end = parse_dt(get_setting("campaign_end", ""))
    return bool(end and end > now_utc())


def campaign_percent():
    if not campaign_active():
        return 0
    return max(0, min(95, safe_int(get_setting("campaign_percent", "0"), 0)))


def get_referral_invite_points():
    return safe_int(get_setting("referral_invite_points", "1"), 1)


def get_referral_purchase_points():
    return safe_int(get_setting("referral_purchase_points", "3"), 3)


def get_referral_bonus_days():
    return safe_int(get_setting("referral_bonus_days", "3"), 3)


def get_weekly_winner_prize_days():
    return safe_int(get_setting("weekly_winner_prize_days", "30"), 30)


def get_renewal_bonus_days():
    return safe_int(get_setting("renewal_bonus_days", "3"), 3)


def current_week_key():
    y, w, _ = now_utc().isocalendar()
    return f"{y}-W{w:02d}"


def previous_week_key():
    d = now_utc() - timedelta(days=7)
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def ab_variant(user_id):
    return "A" if int(user_id) % 2 == 0 else "B"


def parse_channel_ids(text):
    if not text:
        return []
    return [int(x.strip()) for x in str(text).split(",") if x.strip().isdigit()]


def admin_role(user_id):
    if is_owner(user_id):
        return "owner"
    try:
        res = (
            supabase.table("admins")
            .select("*")
            .eq("user_id", int(user_id))
            .eq("active", True)
            .execute()
        )
        if res.data:
            return res.data[0].get("role") or "manager"
    except Exception as e:
        logger.warning("Admin rol okunamadi: %s", e)
    return None


def is_admin(user_id):
    return admin_role(user_id) is not None


def can_manage(user_id):
    return admin_role(user_id) in ["owner", "manager"]


def can_view_reports(user_id):
    return admin_role(user_id) in ["owner", "manager", "viewer"]


async def log_event(action, actor_id=None, target_user_id=None, channel_id=None, details=None):
    try:
        supabase.table("logs").insert(
            {
                "action": action,
                "actor_id": actor_id,
                "target_user_id": target_user_id,
                "channel_id": channel_id,
                "details": details,
            }
        ).execute()
    except Exception as e:
        logger.warning("Log yazilamadi: %s", e)


async def ensure_defaults_once(context: ContextTypes.DEFAULT_TYPE = None):
    # DB kurulmussa eksik ayarlari ve grup SSS kayitlarini tamamlar.
    for key, value in {
        "maintenance": "off",
        "campaign_enabled": "off",
        "campaign_percent": "0",
        "campaign_end": "",
        "referral_invite_points": "1",
        "referral_purchase_points": "3",
        "referral_bonus_days": "3",
        "weekly_winner_prize_days": "30",
        "renewal_bonus_days": "3",
    }.items():
        try:
            if get_setting(key) is None:
                set_setting(key, value)
        except Exception:
            pass
    try:
        existing_rows = supabase.table("faq").select("id,question,answer").execute().data or []
        for row in existing_rows:
            if is_bad_text(row.get("question")) or is_bad_text(row.get("answer")):
                supabase.table("faq").update({"active": False}).eq("id", row["id"]).execute()
        for q, a in DEFAULT_GROUP_FAQS:
            existing = supabase.table("faq").select("id").eq("question", q).execute()
            if not existing.data:
                supabase.table("faq").insert({"question": q, "answer": a, "active": True}).execute()
    except Exception as e:
        logger.warning("Varsay\u0131lan SSS eklenemedi: %s", e)

# =========================================================
# DB ACCESS
# =========================================================

async def get_user_row(user_id):
    try:
        res = supabase.table("users").select("*").eq("user_id", int(user_id)).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


async def save_user(user, referrer_id=None):
    if not user:
        return False
    existing = supabase.table("users").select("*").eq("user_id", user.id).execute()
    is_new = not bool(existing.data)
    payload = {"username": safe_username(user)}
    valid_ref = referrer_id and int(referrer_id) != int(user.id)
    if is_new:
        payload.update(
            {
                "user_id": user.id,
                "accepted_terms": False,
                "active_coupon": None,
                "referrer_id": int(referrer_id) if valid_ref else None,
                "referral_join_reward_given": False,
                "referral_purchase_reward_given": False,
                "referral_points": 0,
                "referral_total_points": 0,
            }
        )
        supabase.table("users").insert(payload).execute()
        if valid_ref:
            await add_referral_points(int(referrer_id), user.id, get_referral_invite_points(), "join")
    else:
        # Var olan kullanicinin referrer'ini sonradan degistirme; sahte referansi azaltir.
        supabase.table("users").update(payload).eq("user_id", user.id).execute()
    return is_new


async def user_accepted_terms(user_id):
    row = await get_user_row(user_id)
    return bool(row and row.get("accepted_terms"))


async def is_blacklisted(user_id):
    try:
        res = (
            supabase.table("blacklist")
            .select("*")
            .eq("user_id", int(user_id))
            .eq("active", True)
            .execute()
        )
        return bool(res.data)
    except Exception:
        return False


async def get_channel(channel_id):
    try:
        res = supabase.table("channels").select("*").eq("id", int(channel_id)).single().execute()
        return res.data
    except Exception:
        return None


async def get_first_active_channel():
    try:
        res = supabase.table("channels").select("*").eq("active", True).order("id").limit(1).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


async def get_package(package_id):
    try:
        res = supabase.table("packages").select("*").eq("id", int(package_id)).single().execute()
        return res.data
    except Exception:
        return None


async def get_subscription(sub_id):
    try:
        res = supabase.table("subscriptions").select("*").eq("id", int(sub_id)).single().execute()
        return res.data
    except Exception:
        return None

# =========================================================
# TELEGRAM CHANNEL ACTIONS
# =========================================================

async def create_one_time_invite_link(context, ch, user_id):
    chat_id_raw = ch.get("chat_id") if ch else None
    if not chat_id_raw:
        return None
    expire_timestamp = int((now_utc() + timedelta(minutes=INVITE_LINK_EXPIRE_MINUTES)).timestamp())
    invite = await context.bot.create_chat_invite_link(
        chat_id=int(chat_id_raw),
        name=f"{ch.get('name', 'VIP')} - {user_id}",
        expire_date=expire_timestamp,
        member_limit=1,
    )
    return invite.invite_link


async def safe_create_and_store_link(context, user_id, channel_id, ch):
    try:
        vip_link = await create_one_time_invite_link(context, ch, user_id)
        if vip_link:
            supabase.table("subscriptions").update({"generated_invite_link": vip_link}).eq("user_id", int(user_id)).eq("channel_id", int(channel_id)).eq("status", "active").execute()
        return vip_link
    except Exception as e:
        logger.error("Davet linki uretilemedi: %s", e)
        return None


async def remove_user_from_channel(context, ch, user_id):
    chat_id_raw = ch.get("chat_id") if ch else None
    if not chat_id_raw:
        return False
    try:
        await context.bot.ban_chat_member(chat_id=int(chat_id_raw), user_id=int(user_id))
        await context.bot.unban_chat_member(chat_id=int(chat_id_raw), user_id=int(user_id), only_if_banned=True)
        return True
    except Exception as e:
        logger.error("Kanaldan cikarilamadi: %s", e)
        return False

# =========================================================
# START / TERMS / MENU ROUTING
# =========================================================

async def show_terms(message):
    kb = [[InlineKeyboardButton("\u2705 Kabul Ediyorum", callback_data="accept_terms")]]
    await message.reply_text(
        " Kurallar ve Kullanim Onayi\n\n"
        "Bu bot uzerinden verilen VIP erisimler yalnizca yasal, rizaya dayali ve kurallara uygun icerikler icindir.\n\n"
        "Devam ederek kurallari kabul etmis olursun.",
        reply_markup=InlineKeyboardMarkup(kb),
    )


def extract_referrer(args):
    if not args:
        return None
    raw = args[0].strip()
    if raw.startswith("ref_"):
        raw = raw[4:]
    elif raw.startswith("ref"):
        raw = raw[3:]
    return int(raw) if raw.isdigit() else None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_defaults_once(context)
    user = update.effective_user
    referrer_id = extract_referrer(context.args)
    await save_user(user, referrer_id=referrer_id)
    if context.args and context.args[0].startswith("ad_"):
        handled = await handle_ad_click_start(update, context, context.args[0])
        if handled:
            return
    if await is_blacklisted(user.id) and not is_admin(user.id):
        await update.message.reply_text("\U0001f6ab Bu botu kullanma yetkin k\u0131s\u0131tland\u0131.")
        return
    if not is_admin(user.id) and not await user_accepted_terms(user.id):
        await show_terms(update.message)
        return
    await update.message.reply_text(
        "\U0001f44b Pasha VIP admin sistemine ho\u015f geldin." if is_admin(user.id) else "\U0001f44b Pasha VIP sistemine ho\u015f geldin.",
        reply_markup=ADMIN_MENU if is_admin(user.id) else MAIN_MENU,
    )
    await quick_start_message(update.message, is_admin(user.id))


async def channel_id_reader(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post:
        return
    text = (update.channel_post.text or "").lower().strip()
    if text in ["id", "chat id", "kanal id", "grup id", "group id", "kanalid"]:
        await context.bot.send_message(chat_id=update.channel_post.chat_id, text=f"Chat ID:\n{update.channel_post.chat_id}")


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_defaults_once(context)
    raw_text = update.message.text.strip()
    text = normalize_menu_text(raw_text)
    user = update.effective_user
    user_id = user.id
    await save_user(user)

    # CRITICAL FIX: mode stuck bug. Any menu/cancel text clears the pending flow.
    if context.user_data.get("mode") and (text in MENU_TEXTS or raw_text.lower() in {x.lower() for x in CANCEL_TEXTS}):
        context.user_data.clear()
        if raw_text.lower() in {x.lower() for x in CANCEL_TEXTS}:
            await update.message.reply_text(
                "\u2705 \u0130\u015flem iptal edildi. Men\u00fcden tekrar se\u00e7im yapabilirsin.",
                reply_markup=ADMIN_MENU if is_admin(user_id) else MAIN_MENU,
            )
            return
        # Continue with the selected menu instead of treating it as form input.

    if await is_blacklisted(user_id) and not is_admin(user_id):
        await update.message.reply_text("\U0001f6ab Bu botu kullanma yetkin k\u0131s\u0131tland\u0131.")
        return
    if not is_admin(user_id) and not await user_accepted_terms(user_id):
        await show_terms(update.message)
        return
    if context.user_data.get("mode"):
        await handle_text_mode(update, context)
        return
    if maintenance_on() and not is_admin(user_id):
        await update.message.reply_text("\U0001f527 Bot bak\u0131m modunda. L\u00fctfen daha sonra tekrar dene.")
        return

    if text == "Hizli Basla":
        await quick_start_message(update.message, is_admin(user_id))
    elif text == "Durumum":
        await user_status_message(update.message, user_id)
    elif is_admin(user_id) and text == "Admin Panel":
        await open_admin_panel(update.message)
    elif text == "VIP Kanallar":
        await show_vip_channels(update.message, user_id)
    elif text == "Paketler":
        await update.message.reply_text("\U0001f4e6 Paket sistemi kald\u0131r\u0131ld\u0131. Sat\u0131n almak i\u00e7in VIP Kanallar b\u00f6l\u00fcm\u00fcn\u00fc kullan.")
    elif text == "Uyeligim":
        await show_my_subscriptions(update.message, user_id)
    elif text == "Gecmisim":
        await my_history(update.message, user_id)
    elif text == "Referans":
        await referral_user_message(update.message, context, user_id)
    elif text == "Liderlik":
        await update.message.reply_text("\U0001f3c6 Liderlik kald\u0131r\u0131ld\u0131. Referans linkini yine Referans b\u00f6l\u00fcm\u00fcnden alabilirsin.")
    elif text == "Cekilis":
        await update.message.reply_text("\U0001f389 \u00c7ekili\u015f kald\u0131r\u0131ld\u0131. VIP kazanmak i\u00e7in Referans b\u00f6l\u00fcm\u00fcn\u00fc kullanabilirsin.")
    elif text == "Iptal Talebi":
        await update.message.reply_text("\u274c \u0130ptal talebi art\u0131k sadece \u00dcyeli\u011fim ekran\u0131ndaki aktif aboneli\u011fin alt\u0131ndan olu\u015fturulur.\n\n\U0001f4c5 \u00dcyeli\u011fim > aboneli\u011fin alt\u0131ndaki \u0130ptal talebi butonu")
    elif text == "Kupon Gir":
        context.user_data["mode"] = "user_coupon"
        await update.message.reply_text("\U0001f39f\ufe0f Kupon kodunu yaz:")
    elif text in ["Bakiye Merkezi", "Bakiyem"]:
        await show_balance_center(update.message, user_id)
    elif text == "Bakiye Yukle":
        await ask_custom_topup_amount(update.message, context)
    elif text == "Reklam Ver":
        await show_ad_packages_user(update.message, user_id)
    elif text == "Reklamlarim":
        await my_ad_orders(update.message, user_id)
    elif text == "Destek":
        await support_menu(update.message)
    elif text == "SSS":
        await faq_user_message(update.message)
    elif text == "Yardim":
        await help_message(update.message)
    else:
        await update.message.reply_text("Men\u00fcden bir se\u00e7enek se\u00e7ebilirsin.")


async def help_message(message):
    await message.reply_text(
        "\u2139\ufe0f Yard\u0131m\n\n"
        "\U0001f4e2 VIP Kanallar: Sat\u0131n al\u0131nabilir kanallar\u0131 g\u00f6sterir.\n"

        "\U0001f4c5 \u00dcyeli\u011fim: Aktif \u00fcyeliklerini ve link yenilemeyi g\u00f6sterir.\n"
        "\U0001f381 Referans: Arkada\u015f getirip puan kazan\u0131rs\u0131n.\n"

        "\u274c \u0130ptal: Sadece \u00dcyeli\u011fim ekran\u0131ndaki abonelik kart\u0131ndan yap\u0131l\u0131r.\n"
        "\u2753 SSS: Grup/kanal ve \u00f6deme sorunlar\u0131 i\u00e7in haz\u0131r cevaplar.\n"
        "\U0001f4b0 Bakiyem: Reklam bakiyeni g\u00f6sterir.\n"
        "\U0001f4e3 Reklam Ver: Reklam talebi olu\u015fturur.\n"
        "\U0001f198 Destek: Admin'e destek talebi g\u00f6nderir."
    )

# =========================================================
# ADMIN PANEL
# =========================================================



def test_mode_on():
    return get_setting("test_mode", "off") == "on"


def normalize_ad_link(link):
    link = (link or "").strip()
    if link.startswith("@"):
        return "https://t.me/" + link[1:]
    if link.startswith("t.me/"):
        return "https://" + link
    if link.startswith("https://") or link.startswith("http://"):
        return link
    return None


def validate_ad_fields(title, body, link):
    title = (title or "").strip()
    body = (body or "").strip()
    clean_link = normalize_ad_link(link)
    if len(title) < 3:
        return False, "Baslik cok kisa. En az 3 karakter yaz.", None
    if len(title) > 80:
        return False, "Baslik cok uzun. En fazla 80 karakter yaz.", None
    if len(body) < 10:
        return False, "Metin cok kisa. En az 10 karakter yaz.", None
    if len(body) > 700:
        return False, "Metin cok uzun. En fazla 700 karakter yaz.", None
    if not clean_link:
        return False, "Link gecersiz. https:// veya t.me/ ile baslamali.", None
    return True, "OK", clean_link


async def quick_start_message(message, admin=False):
    kb = [
        [InlineKeyboardButton("\u2b50 VIP Sat\u0131n Al", callback_data="quick_vip")],
        [InlineKeyboardButton("\U0001f4e3 Reklam Ver", callback_data="quick_ads")],
        [InlineKeyboardButton("\U0001f4cc Durumum", callback_data="quick_status")],
        [InlineKeyboardButton("\U0001f198 Destek", callback_data="quick_support")],
    ]
    if admin:
        kb.insert(0, [InlineKeyboardButton("\U0001f451 Admin Panel", callback_data="admin_panel_open")])
    await message.reply_text(
        "\U0001f680 H\u0131zl\u0131 Ba\u015fla\n\n"
        "Ne yapmak istiyorsun?",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def user_status_message(message, user_id):
    balance = await get_ad_balance(user_id)
    active_subs = supabase.table("subscriptions").select("*").eq("user_id", int(user_id)).eq("status", "active").execute().data or []
    ad_orders = supabase.table("ad_orders").select("*").eq("user_id", int(user_id)).execute().data or []
    user_row = await get_user_row(user_id)
    coupon = (user_row or {}).get("active_coupon") or "Yok"
    pending_ads = len([o for o in ad_orders if o.get("status") == "pending"])
    published_ads = len([o for o in ad_orders if o.get("status") == "published"])
    rejected_ads = len([o for o in ad_orders if str(o.get("status") or "").startswith("rejected") or "refunded" in str(o.get("status") or "")])

    lines = ["\U0001f4cc Durumum", ""]
    lines.append(f"\U0001f4b0 Reklam bakiyesi: {balance} Stars")
    lines.append(f"\U0001f39f\ufe0f Aktif kupon: {coupon}")
    lines.append(f"\U0001f4e3 Bekleyen reklam: {pending_ads}")
    lines.append(f"\u2705 Yay\u0131nlanan reklam: {published_ads}")
    lines.append(f"\u274c Reddedilen/iade edilen reklam: {rejected_ads}")
    lines.append("")
    if active_subs:
        lines.append("\U0001f4c5 Aktif VIP \u00fcyelikler:")
        for sub in active_subs[:5]:
            ch = await get_channel(sub.get("channel_id"))
            name = (ch or {}).get("name") or f"Kanal ID {sub.get('channel_id')}"
            lines.append(f"- {name}: {sub.get('end_date')}")
    else:
        lines.append("\U0001f4c5 Aktif VIP \u00fcyelik: Yok")

    kb = [
        [InlineKeyboardButton("\U0001f4e2 VIP Sat\u0131n Al", callback_data="quick_vip")],
        [InlineKeyboardButton("\U0001f4e3 Reklam Ver", callback_data="quick_ads")],
        [InlineKeyboardButton("\U0001f4c4 Reklamlar\u0131m", callback_data="ad_my_orders")],
    ]
    await message.reply_text("\n".join(lines)[:3900], reply_markup=InlineKeyboardMarkup(kb))


async def pending_work_message(message):
    pending_ads = supabase.table("ad_orders").select("*").eq("status", "pending").execute().data or []
    failed_ads = supabase.table("ad_orders").select("*").in_("status", ["failed", "failed_refunded"]).execute().data or []
    supports = supabase.table("support_requests").select("*").eq("status", "open").execute().data or []
    cancels = supabase.table("cancel_requests").select("*").eq("status", "pending").execute().data or []

    kb = [
        [InlineKeyboardButton(f"\U0001f4e3 Reklam Talepleri ({len(pending_ads)})", callback_data="admin_ads")],
        [InlineKeyboardButton(f"\U0001f198 Destek ({len(supports)})", callback_data="admin_support")],
        [InlineKeyboardButton(f"\u274c \u0130ptal Talepleri ({len(cancels)})", callback_data="admin_cancel")],
        [InlineKeyboardButton(f"\u26a0\ufe0f Yay\u0131nlanamayan Reklam ({len(failed_ads)})", callback_data="admin_ad_stats")],
    ]
    await message.reply_text(
        "\U0001f4cc Bekleyen \u0130\u015fler\n\n"
        f"Bekleyen reklam: {len(pending_ads)}\n"
        f"A\u00e7\u0131k destek: {len(supports)}\n"
        f"Bekleyen iptal: {len(cancels)}\n"
        f"Yay\u0131nlanamayan reklam: {len(failed_ads)}",
        reply_markup=InlineKeyboardMarkup(kb),
    )

async def admin_dashboard_text():
    today = now_utc().date().isoformat()
    month = now_utc().strftime("%Y-%m")
    sales = supabase.table("sales").select("*").execute().data or []
    active_subs = supabase.table("subscriptions").select("*").eq("status", "active").execute().data or []
    supports = supabase.table("support_requests").select("*").eq("status", "open").execute().data or []
    abandoned = supabase.table("checkout_intents").select("*").eq("status", "started").execute().data or []
    blacklisted = supabase.table("blacklist").select("*").eq("active", True).execute().data or []
    try:
        pending_ads = supabase.table("ad_orders").select("*").eq("status", "pending").execute().data or []
    except Exception:
        pending_ads = []
    today_count = today_stars = month_count = month_stars = 0
    for s in sales:
        if s.get("refund_status") == "refunded":
            continue
        created = str(s.get("created_at") or "")
        price = safe_int(s.get("price"), 0)
        if created.startswith(today):
            today_count += 1
            today_stars += price
        if created.startswith(month):
            month_count += 1
            month_stars += price
    expiring_today = 0
    for sub in active_subs:
        end = parse_dt(sub.get("end_date"))
        if end and end.date() == now_utc().date():
            expiring_today += 1
    return (
        "\U0001f451 Admin Panel\n\n"
        f"\U0001f4ca Bug\u00fcn: {today_count} sat\u0131\u015f / {today_stars} Stars\n"
        f"\U0001f4c6 Bu ay: {month_count} sat\u0131\u015f / {month_stars} Stars\n"
        f"\U0001f465 Aktif \u00fcye: {len(active_subs)}\n"
        f"\U0001f6d2 Yar\u0131m kalan \u00f6deme: {len(abandoned)}\n"
        f"\u23f3 Bug\u00fcn bitecek \u00fcyelik: {expiring_today}\n"
        f"\U0001f198 A\u00e7\u0131k destek: {len(supports)}\n"
        f"\U0001f4e3 Bekleyen reklam: {len(pending_ads)}\n"
        f"\U0001f6ab Kara liste: {len(blacklisted)}\n"
        f"\U0001f527 Bak\u0131m modu: {'A\u00c7IK' if maintenance_on() else 'KAPALI'}"
    )


async def open_admin_panel(message):
    kb = [
        [InlineKeyboardButton("\u2795 Kanal Ekle", callback_data="admin_add_channel")],
        [InlineKeyboardButton("\U0001f4e2 Kanallar\u0131 Y\u00f6net", callback_data="admin_channels")],
        [InlineKeyboardButton("\U0001f381 Kullan\u0131c\u0131ya VIP Ver", callback_data="admin_grant")],
        [InlineKeyboardButton("\U0001f4ca Son Sat\u0131\u015flar", callback_data="admin_sales"), InlineKeyboardButton("\U0001f4c8 Rapor", callback_data="admin_report")],
        [InlineKeyboardButton("\U0001f4e2 Kanal \u0130statistikleri", callback_data="admin_channel_stats"), InlineKeyboardButton("\U0001f6d2 Yar\u0131m Kalanlar", callback_data="admin_abandoned")],
        [InlineKeyboardButton("\U0001f465 Kullan\u0131c\u0131lar", callback_data="admin_users"), InlineKeyboardButton("\U0001f50d Kullan\u0131c\u0131 Ara", callback_data="admin_search_user")],
        [InlineKeyboardButton("\U0001f39f\ufe0f Kuponlar", callback_data="admin_coupons"), InlineKeyboardButton("\U0001f525 Kampanya", callback_data="admin_campaign")],
        [InlineKeyboardButton("\U0001f381 Referans Paneli", callback_data="admin_referrals")],
        [InlineKeyboardButton("\U0001f4cc Bekleyen \u0130\u015fler", callback_data="admin_pending_work")],
        [InlineKeyboardButton("\U0001f4e3 Reklam Talepleri", callback_data="admin_ads"), InlineKeyboardButton("\U0001f4b8 Reklam Fiyatlari", callback_data="admin_ad_channel_prices")],
        [InlineKeyboardButton("\U0001f4b0 Bakiye \u0130\u015flemleri", callback_data="admin_ad_balances")],
        [InlineKeyboardButton("\U0001f4ca Reklam Istatistikleri", callback_data="admin_ad_stats"), InlineKeyboardButton("\U0001f9ea Sistem Testi", callback_data="admin_system_test")],
        [InlineKeyboardButton("\U0001f9ea Test Modu A\u00e7/Kapat", callback_data="admin_test_mode")],
        [InlineKeyboardButton("\u2753 SSS Y\u00f6net", callback_data="admin_faq"), InlineKeyboardButton("\U0001f198 Destek Talepleri", callback_data="admin_support")],
        [InlineKeyboardButton("\u274c \u0130ptal Talepleri", callback_data="admin_cancel"), InlineKeyboardButton("\U0001f6ab Kara Liste", callback_data="admin_blacklist")],
        [InlineKeyboardButton("\U0001f46e Adminler", callback_data="admin_admins"), InlineKeyboardButton("\U0001f4dc \u0130\u015flem Loglar\u0131", callback_data="admin_logs")],
        [InlineKeyboardButton("\U0001f4c4 Sat\u0131\u015f CSV", callback_data="admin_export_sales"), InlineKeyboardButton("\U0001f194 Grup/Kanal ID Yard\u0131m\u0131", callback_data="admin_channel_id_help")],
        [InlineKeyboardButton("\U0001f527 Bak\u0131m A\u00e7/Kapat", callback_data="admin_maintenance")],
    ]
    await message.reply_text(await admin_dashboard_text(), reply_markup=InlineKeyboardMarkup(kb))

# =========================================================
# DISPLAY CHANNELS / PACKAGES
# =========================================================

async def show_vip_channels(message, user_id):
    rows = supabase.table("channels").select("*").eq("active", True).order("id").execute().data or []
    if not rows:
        await message.reply_text("\U0001f4e2 Hen\u00fcz VIP kanal eklenmedi.")
        return

    await message.reply_text("\U0001f4e2 VIP Kanallar\n\nSat\u0131n almak istedi\u011fin kanal kart\u0131ndaki butona bas. \u00d6deme tamamlan\u0131nca tek kullan\u0131ml\u0131k giri\u015f linkin otomatik gelir.")

    for ch in rows:
        base_price = safe_int(ch.get("price"), 0)
        final_price, coupon_code, discount_text = await calculate_price(user_id, base_price, ch.get("id"))
        variant = ab_variant(user_id)
        title = "\U0001f525 Bug\u00fcne \u00f6zel VIP eri\u015fim" if variant == "B" else "\U0001f4e2 VIP Kanal"
        campaign_line = f"\n\U0001f525 Kampanya indirimi: %{campaign_percent()}" if campaign_percent() else ""
        coupon_line = f"\n\U0001f39f\ufe0f Kupon: {coupon_code} ({discount_text})" if coupon_code else ""
        description_line = f"\n\n\U0001f4dd {ch.get('description')}" if ch.get("description") else ""
        text = (
            f"{title}\n\n"
            f"\U0001f4e2 {ch.get('name')}\n"
            f"\u2b50 Fiyat: {base_price} Stars\n"
            f"\u2705 \u00d6denecek: {final_price} Stars\n"
            f"\u23f3 S\u00fcre: {ch.get('duration_days') or DEFAULT_DURATION_DAYS} g\u00fcn"
            f"{campaign_line}{coupon_line}{description_line}"
        )
        kb = [
            [InlineKeyboardButton("\U0001f441\ufe0f \u00d6nizleme", callback_data=f"preview_channel_{ch['id']}")],
            [InlineKeyboardButton(f"\u2b50 {final_price} Stars ile Sat\u0131n Al", callback_data=f"buyc_{ch['id']}")],
        ]

        photo_url = ch.get("photo_url")
        if photo_url:
            try:
                await message.reply_photo(
                    photo=photo_url,
                    caption=text,
                    reply_markup=InlineKeyboardMarkup(kb),
                )
                continue
            except Exception as e:
                logger.error("Kanal gorseli gonderilemedi, text fallback kullaniliyor: %s", e)

        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def show_channel_preview(message, channel_id, user_id):
    ch = await get_channel(channel_id)
    if not ch:
        await message.reply_text(" Kanal bulunamadi.")
        return
    final_price, coupon_code, discount_text = await calculate_price(user_id, safe_int(ch.get("price"), 0), channel_id)
    coupon_line = f"\n\U0001f39f\ufe0f Kupon: {coupon_code} ({discount_text})" if coupon_code else ""
    text = (
        " Kanal Onizleme\n\n"
        f"\U0001f4e2 {ch.get('name')}\n"
        f" Fiyat: {ch.get('price')} Stars\n"
        f"\u2705 \u00d6denecek: {final_price} Stars\n"
        f" Sure: {ch.get('duration_days') or DEFAULT_DURATION_DAYS} gun\n"
        f" {ch.get('description') or 'Aciklama yok.'}\n\n"
        " Odeme Telegram Stars ile yapilir\n"
        " Link otomatik gonderilir\n"
        " Uyelik tarihi botta gorunur\n"
        " Sorun olursa destek acabilirsin"
        f"{coupon_line}"
    )
    kb = [[InlineKeyboardButton(f"\u2b50 {final_price} Stars ile Sat\u0131n Al", callback_data=f"buyc_{channel_id}")]]
    if ch.get("photo_url"):
        try:
            await message.reply_photo(ch["photo_url"], caption=text, reply_markup=InlineKeyboardMarkup(kb))
            return
        except Exception:
            pass
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def show_packages(message, user_id):
    rows = supabase.table("packages").select("*").eq("active", True).order("id").execute().data or []
    if not rows:
        await message.reply_text(" Henuz paket eklenmedi.")
        return
    for p in rows:
        base_price = safe_int(p.get("price"), 0)
        final_price, coupon_code, discount_text = await calculate_price(user_id, base_price, None)
        coupon_line = f"\n\U0001f39f\ufe0f Kupon: {coupon_code} ({discount_text})" if coupon_code else ""
        text = (
            f" {p.get('name')}\n"
            f"\u2b50 Fiyat: {base_price} Stars\n"
            f"\u2705 \u00d6denecek: {final_price} Stars\n"
            f" Sure: {p.get('duration_days') or DEFAULT_DURATION_DAYS} gun\n"
            f" {p.get('description') or ''}"
            f"{coupon_line}"
        )
        kb = [[InlineKeyboardButton(f" {final_price} Stars ile Paketi Al", callback_data=f"buyp_{p['id']}")]]
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

# =========================================================
# TEXT MODES
# =========================================================

async def handle_text_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    raw_text = update.message.text.strip()
    text = normalize_menu_text(raw_text)
    user = update.effective_user
    user_id = user.id
    try:
        if mode == "add_channel":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 4:
                await update.message.reply_text(" Format: KanalAdi | Fiyat | ChatID | SureGun | Aciklama | GorselURL")
                return
            payload = {
                "name": parts[0],
                "price": int(parts[1]),
                "chat_id": parts[2],
                "duration_days": int(parts[3]),
                "description": parts[4] if len(parts) >= 5 else None,
                "photo_url": parts[5] if len(parts) >= 6 and parts[5] not in ["", "-"] else None,
                "invite_link": "",
                "active": True,
            }
            supabase.table("channels").insert(payload).execute()
            await log_event("channel_added", user_id, details=str(payload))
            context.user_data.clear()
            await update.message.reply_text(f" Kanal eklendi: {payload['name']}")

        elif mode == "add_package":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 4:
                await update.message.reply_text(" Format: PaketAdi | Fiyat | SureGun | KanalIDleri | Aciklama")
                return
            payload = {
                "name": parts[0],
                "price": int(parts[1]),
                "duration_days": int(parts[2]),
                "channel_ids": parts[3],
                "description": parts[4] if len(parts) >= 5 else None,
                "active": True,
            }
            supabase.table("packages").insert(payload).execute()
            await log_event("package_added", user_id, details=str(payload))
            context.user_data.clear()
            await update.message.reply_text(f" Paket eklendi: {payload['name']}")

        elif mode in ["edit_price", "edit_duration", "edit_chat", "edit_description", "edit_photo"]:
            channel_id = context.user_data.get("channel_id")
            if mode == "edit_price":
                field, value, reply = "price", int(text), " Fiyat guncellendi."
            elif mode == "edit_duration":
                field, value, reply = "duration_days", int(text), " Sure guncellendi."
            elif mode == "edit_chat":
                field, value, reply = "chat_id", text, " Chat ID guncellendi."
            elif mode == "edit_description":
                field, value, reply = "description", text, " Aciklama guncellendi."
            else:
                field, value, reply = "photo_url", None if text == "-" else text, " Gorsel URL guncellendi."
            supabase.table("channels").update({field: value}).eq("id", channel_id).execute()
            await log_event("channel_updated", user_id, channel_id=channel_id, details=f"{field}={value}")
            context.user_data.clear()
            await update.message.reply_text(reply)

        elif mode == "add_coupon":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 5:
                await update.message.reply_text(" Format: KOD | YuzdeIndirim | StarsIndirim | MaxKullanim | KanalID/0")
                return
            ch_id = int(parts[4])
            payload = {
                "code": parts[0].upper(),
                "discount_percent": int(parts[1]),
                "discount_stars": int(parts[2]),
                "max_uses": int(parts[3]),
                "channel_id": None if ch_id == 0 else ch_id,
                "used_count": 0,
                "active": True,
            }
            supabase.table("coupons").insert(payload).execute()
            await log_event("coupon_added", user_id, details=str(payload))
            context.user_data.clear()
            await update.message.reply_text(" Kupon olusturuldu.")

        elif mode == "add_faq":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 2:
                await update.message.reply_text(" Format: Soru | Cevap")
                return
            supabase.table("faq").insert({"question": parts[0], "answer": parts[1], "active": True}).execute()
            await log_event("faq_added", user_id, details=text)
            context.user_data.clear()
            await update.message.reply_text(" SSS eklendi.")

        elif mode == "add_admin":
            if not is_owner(user_id):
                context.user_data.clear()
                await update.message.reply_text(" Sadece owner admin ekleyebilir.")
                return
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 2 or parts[1].lower() not in ["manager", "viewer"]:
                await update.message.reply_text(" Format: UserID | role\nRole: manager veya viewer")
                return
            target_id = int(parts[0])
            role = parts[1].lower()
            existing = supabase.table("admins").select("*").eq("user_id", target_id).execute()
            if existing.data:
                supabase.table("admins").update({"role": role, "active": True}).eq("user_id", target_id).execute()
            else:
                supabase.table("admins").insert({"user_id": target_id, "role": role, "active": True}).execute()
            await log_event("admin_added", user_id, target_user_id=target_id, details=role)
            context.user_data.clear()
            await update.message.reply_text(" Admin eklendi.")

        elif mode == "blacklist_reason":
            target_id = context.user_data.get("target_user_id")
            existing = supabase.table("blacklist").select("*").eq("user_id", target_id).execute()
            if existing.data:
                supabase.table("blacklist").update({"reason": text, "active": True}).eq("user_id", target_id).execute()
            else:
                supabase.table("blacklist").insert({"user_id": target_id, "reason": text, "active": True}).execute()
            await log_event("blacklisted", user_id, target_user_id=target_id, details=text)
            context.user_data.clear()
            await update.message.reply_text(" Kullanici kara listeye alindi.")

        elif mode == "custom_grant_days":
            target_user_id = context.user_data.get("target_user_id")
            channel_id = context.user_data.get("channel_id")
            days = int(text)
            context.user_data.clear()
            await grant_vip_to_user(update.message, context, target_user_id, channel_id, custom_days=days)

        elif mode == "campaign_start":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 2:
                await update.message.reply_text(" Format: IndirimYuzde | Saat")
                return
            percent = max(1, min(95, int(parts[0])))
            hours = max(1, int(parts[1]))
            set_setting("campaign_enabled", "on")
            set_setting("campaign_percent", str(percent))
            set_setting("campaign_end", (now_utc() + timedelta(hours=hours)).isoformat())
            await log_event("campaign_started", user_id, details=text)
            context.user_data.clear()
            await update.message.reply_text(f" Kampanya basladi: %{percent} / {hours} saat")

        elif mode == "search_user":
            await search_user(update.message, text)
            context.user_data.clear()

        elif mode == "ad_topup_amount":
            amount_text = raw_text.replace(" ", "").strip()
            if not amount_text.isdigit():
                await update.message.reply_text("Lutfen sadece rakam yaz. Ornek: 2500")
                return
            amount = int(amount_text)
            if amount < 50:
                await update.message.reply_text("Minimum yukleme 50 Stars olmalidir.")
                return
            if amount > 100000:
                await update.message.reply_text("Tek seferde en fazla 100000 Stars yukleyebilirsin.")
                return
            context.user_data.clear()
            await send_custom_topup_invoice(update.message, context, amount)

        elif mode == "edit_channel_ad_price":
            if not can_manage(user_id):
                context.user_data.clear()
                await update.message.reply_text(" Yetkin yok.")
                return
            channel_id = context.user_data.get("channel_id")
            amount_text = raw_text.replace(" ", "").strip()
            if not amount_text.isdigit():
                await update.message.reply_text("Lutfen sadece rakam yaz. Ornek: 1500")
                return
            price = int(amount_text)
            if price < 1:
                await update.message.reply_text("Reklam fiyati en az 1 Stars olmali.")
                return
            supabase.table("channels").update({"ad_price": price}).eq("id", channel_id).execute()
            await log_event("channel_ad_price_updated", user_id, channel_id=channel_id, details=f"ad_price={price}")
            context.user_data.clear()
            await update.message.reply_text(f"Kanal reklam fiyati guncellendi: {price} Stars")

        elif mode == "add_ad_package":
            if not can_manage(user_id):
                context.user_data.clear()
                await update.message.reply_text(" Yetkin yok.")
                return
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 5:
                await update.message.reply_text(" Format: PaketAdi | Fiyat | Hedef | KanalID/0 | Aciklama\nHedef: single veya all")
                return
            target_type = parts[2].lower()
            if target_type not in ["single", "all"]:
                await update.message.reply_text(" Hedef sadece single veya all olabilir.")
                return
            channel_id = None if parts[3] == "0" or target_type == "all" else int(parts[3])
            supabase.table("ad_packages").insert({"name": parts[0], "price": int(parts[1]), "target_type": target_type, "channel_id": channel_id, "description": parts[4], "active": True}).execute()
            await log_event("ad_package_added", user_id, details=text)
            context.user_data.clear()
            await update.message.reply_text(" Reklam paketi eklendi.")

        elif mode == "ad_single_message":
            parts = [p.strip() for p in raw_text.split("|")]
            if len(parts) < 3:
                await update.message.reply_text("Format: Baslik | Metin | Link")
                return
            title, body, link = parts[0], parts[1], parts[2]
            ok, msg, clean_link = validate_ad_fields(title, body, link)
            if not ok:
                await update.message.reply_text(msg)
                return
            context.user_data["ad_title"] = title
            context.user_data["ad_text"] = body
            context.user_data["ad_link"] = clean_link
            context.user_data["mode"] = "ad_image"
            await update.message.reply_text(
                "Reklam hazir. Gorsel eklemek istersen foto gonder. Gorselsiz devam etmek icin butona bas veya skip yaz.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Gorselsiz Devam", callback_data="ad_no_image")]]),
            )

        elif mode == "ad_template_prompt":
            parts = [p.strip() for p in raw_text.split("|")]
            if len(parts) < 3:
                await update.message.reply_text("Format: Baslik | Kisa aciklama | Link")
                return
            title, short_desc, link = parts[0], parts[1], parts[2]
            body = f"{short_desc}\n\nDetaylar icin asagidaki butona bas."
            ok, msg, clean_link = validate_ad_fields(title, body, link)
            if not ok:
                await update.message.reply_text(msg)
                return
            context.user_data["ad_title"] = title
            context.user_data["ad_text"] = body
            context.user_data["ad_link"] = clean_link
            context.user_data["mode"] = "ad_image"
            await update.message.reply_text(
                "Hazir reklam olusturuldu. Gorsel eklemek istersen foto gonder. Gorselsiz devam etmek icin butona bas veya skip yaz.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Gorselsiz Devam", callback_data="ad_no_image")]]),
            )

        elif mode == "ad_title":
            if len(raw_text) < 3:
                await update.message.reply_text("Baslik cok kisa. En az 3 karakter yaz.")
                return
            if len(raw_text) > 80:
                await update.message.reply_text(" Baslik cok uzun. En fazla 80 karakter yaz.")
                return
            context.user_data["ad_title"] = raw_text
            context.user_data["mode"] = "ad_text"
            await update.message.reply_text(" Reklam metnini yaz. En fazla 700 karakter.")

        elif mode == "ad_text":
            if len(raw_text) < 10:
                await update.message.reply_text("Metin cok kisa. En az 10 karakter yaz.")
                return
            if len(raw_text) > 700:
                await update.message.reply_text(" Metin cok uzun. En fazla 700 karakter yaz.")
                return
            context.user_data["ad_text"] = raw_text
            context.user_data["mode"] = "ad_link"
            await update.message.reply_text(" Hedef linki yaz. Ornek: https://t.me/kanal veya https://site.com")

        elif mode == "ad_link":
            clean_link = normalize_ad_link(raw_text.strip())
            if not clean_link:
                await update.message.reply_text(" Link gecersiz. https:// veya t.me/ ile baslayan bir link yaz.")
                return
            context.user_data["ad_link"] = clean_link
            context.user_data["mode"] = "ad_image"
            await update.message.reply_text(
                "Gorsel eklemek istersen simdi foto gonder. Gorselsiz devam etmek icin butona bas veya skip yaz.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Gorselsiz Devam", callback_data="ad_no_image")]]),
            )

        elif mode == "ad_image":
            if raw_text.lower() in ["skip", "gec", "yok", "hayir"]:
                context.user_data["ad_image_file_id"] = None
                await preview_ad_order(update.message, context)
            else:
                await update.message.reply_text("Lutfen foto gonder veya gorselsiz devam etmek icin skip yaz.")

        elif mode == "edit_ad_pkg_price":
            package_id = context.user_data.get("ad_package_id")
            price = int(raw_text.strip())
            if price < 1:
                await update.message.reply_text("Fiyat en az 1 Stars olmali.")
                return
            supabase.table("ad_packages").update({"price": price}).eq("id", package_id).execute()
            await log_event("ad_package_price_updated", user_id, details=f"package_id={package_id}, price={price}")
            context.user_data.clear()
            await update.message.reply_text("Reklam paketi fiyati guncellendi.")

        elif mode == "edit_ad_pkg_desc":
            package_id = context.user_data.get("ad_package_id")
            supabase.table("ad_packages").update({"description": raw_text}).eq("id", package_id).execute()
            await log_event("ad_package_desc_updated", user_id, details=f"package_id={package_id}")
            context.user_data.clear()
            await update.message.reply_text("Reklam paketi aciklamasi guncellendi.")

        elif mode == "edit_ad_pkg_target":
            package_id = context.user_data.get("ad_package_id")
            parts = [x.strip() for x in raw_text.split("|")]
            if len(parts) < 2 or parts[0].lower() not in ["single", "all"]:
                await update.message.reply_text("Format: single | KanalID veya all | 0")
                return
            target_type = parts[0].lower()
            channel_id = None if target_type == "all" or parts[1] == "0" else int(parts[1])
            supabase.table("ad_packages").update({"target_type": target_type, "channel_id": channel_id}).eq("id", package_id).execute()
            await log_event("ad_package_target_updated", user_id, details=f"package_id={package_id}, target={target_type}, channel_id={channel_id}")
            context.user_data.clear()
            await update.message.reply_text("Reklam paketi hedefi guncellendi.")

        elif mode == "ad_update_views":
            order_id = context.user_data.get("ad_order_id")
            views = int(raw_text.strip())
            if views < 0:
                await update.message.reply_text("Goruntulenme negatif olamaz.")
                return
            supabase.table("ad_orders").update({"views_count": views, "views_updated_at": now_utc().isoformat()}).eq("id", order_id).execute()
            await log_event("ad_views_updated", user_id, details=f"order_id={order_id}, views={views}")
            context.user_data.clear()
            await update.message.reply_text("Reklam goruntulenme sayisi guncellendi.")

        elif mode == "user_coupon":
            code = text.upper()
            coupon = await get_coupon(code)
            if not coupon or not coupon.get("active"):
                context.user_data.clear()
                await update.message.reply_text(" Kupon bulunamadi veya aktif degil.")
                return
            if int(coupon.get("max_uses") or 0) > 0 and int(coupon.get("used_count") or 0) >= int(coupon.get("max_uses") or 0):
                context.user_data.clear()
                await update.message.reply_text(" Bu kuponun kullanim limiti dolmus.")
                return
            supabase.table("users").update({"active_coupon": code}).eq("user_id", user_id).execute()
            context.user_data.clear()
            await update.message.reply_text(f" Kupon uygulandi: {code}")

        elif mode == "user_support":
            if await is_blacklisted(user_id):
                context.user_data.clear()
                await update.message.reply_text(" Destek talebi olusturamazsin.")
                return
            supabase.table("support_requests").insert({"user_id": user_id, "username": safe_username(user), "message": text, "status": "open"}).execute()
            await log_event("support_created", user_id, target_user_id=user_id, details=text)
            context.user_data.clear()
            await update.message.reply_text(" Destek talebin admin'e gonderildi.")
            await context.bot.send_message(OWNER_ID, f" Yeni destek talebi!\n\nKullanici: @{safe_username(user) or 'yok'}\nID: {user_id}\n\n{text}")

        elif mode == "broadcast":
            context.user_data.clear()
            await broadcast_message(update.message, context, text)

    except Exception as e:
        logger.error("Text mode hatasi: %s", e)
        context.user_data.clear()
        await update.message.reply_text(" Islem sirasinda hata oldu. Formati kontrol et. Islem modu kapatildi.")

# =========================================================
# CALLBACK ROUTER
# =========================================================

async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "accept_terms":
        supabase.table("users").update({"accepted_terms": True}).eq("user_id", user_id).execute()
        await query.message.reply_text("\u2705 Kurallar\u0131 kabul ettin. Men\u00fcden devam edebilirsin.", reply_markup=MAIN_MENU)
        return

    # public callbacks
    if data.startswith("preview_channel_"):
        await show_channel_preview(query.message, int(data.split("_")[2]), user_id)
        return
    if data.startswith("buyc_"):
        await handle_buy_channel(query, context)
        return
    if data.startswith("buyp_"):
        await handle_buy_package(query, context)
        return
    if data.startswith("resend_"):
        await resend_invite_link(query, context)
        return
    if data.startswith("request_cancel_"):
        await request_cancel_from_button(query, context)
        return
    if data.startswith("faq_view_"):
        await faq_answer(query.message, int(data.split("_")[2]))
        return
    if data.startswith("redeem_"):
        await redeem_referral_reward(query, context)
        return
    if data.startswith("support_auto_"):
        await support_auto_answer(query.message, data.split("_", 2)[2])
        return
    if data == "ad_balance_center":
        await show_balance_center(query.message, user_id)
        return
    if data == "ad_topup_custom":
        await ask_custom_topup_amount(query.message, context)
        return
    if data == "ad_show_packages":
        await show_ad_channels_user(query.message, user_id)
        return
    if data == "ad_my_orders":
        await my_ad_orders(query.message, user_id)
        return
    if data == "ad_transactions":
        await show_ad_transactions(query.message, user_id)
        return
    if data.startswith("topup_"):
        await handle_topup(query, context)
        return
    if data.startswith("adch_") and len(data.split("_")) == 2 and data.split("_")[1].isdigit():
        await start_ad_order_channel(query, context)
        return
    if data.startswith("adpkg_") and len(data.split("_")) == 2 and data.split("_")[1].isdigit():
        await start_ad_order(query, context)
        return
    if data == "ad_submit":
        await submit_ad_order(query, context)
        return
    if data == "ad_cancel":
        context.user_data.clear()
        await query.message.reply_text(" Reklam talebi iptal edildi.")
        return
    if data == "quick_vip":
        await show_vip_channels(query.message, user_id)
        return
    if data == "quick_ads":
        await show_balance_center(query.message, user_id)
        return
    if data == "quick_status":
        await user_status_message(query.message, user_id)
        return
    if data == "quick_support":
        await support_menu(query.message)
        return
    if data == "admin_panel_open":
        if is_admin(user_id):
            await open_admin_panel(query.message)
        else:
            await query.message.reply_text("Yetkin yok.")
        return
    if data == "ad_method_single":
        if not context.user_data.get("ad_channel_id"):
            await query.message.reply_text("Once reklam vermek istedigin kanali sec.")
            return
        context.user_data["mode"] = "ad_single_message"
        await query.message.reply_text(
            "Reklamini tek mesajda gonder:\n\n"
            "Baslik | Metin | Link\n\n"
            "Ornek:\n"
            "Yeni Kanal | Guncel paylasimlar icin hemen incele | https://t.me/kanal"
        )
        return
    if data == "ad_method_template":
        if not context.user_data.get("ad_channel_id"):
            await query.message.reply_text("Once reklam vermek istedigin kanali sec.")
            return
        context.user_data["mode"] = "ad_template_prompt"
        await query.message.reply_text(
            "Hazir reklam olusturmak icin yaz:\n\n"
            "Baslik | Kisa aciklama | Link\n\n"
            "Ornek:\n"
            "Yeni Kanal | Guncel icerikler ve ozel paylasimlar | https://t.me/kanal"
        )
        return
    if data == "ad_method_step":
        if not context.user_data.get("ad_channel_id"):
            await query.message.reply_text("Once reklam vermek istedigin kanali sec.")
            return
        context.user_data["mode"] = "ad_title"
        await query.message.reply_text("Simdi reklam basligini yaz. Ornek: Yeni VIP Kanal")
        return
    if data == "ad_no_image":
        if context.user_data.get("mode") != "ad_image":
            await query.message.reply_text("Aktif gorsel adimi yok.")
            return
        context.user_data["ad_image_file_id"] = None
        await preview_ad_order(query.message, context)
        return

    # protected callbacks
    if not is_admin(user_id):
        await query.message.reply_text(" Yetkin yok.")
        return

    if data.startswith("cancel_"):
        await handle_cancel_admin(query, context)
        return
    if data.startswith("support_close_"):
        if not can_manage(user_id):
            await query.message.reply_text(" Yetkin yok.")
            return
        rid = int(data.split("_")[2])
        supabase.table("support_requests").update({"status": "closed"}).eq("id", rid).execute()
        await log_event("support_closed", user_id, details=f"request_id={rid}")
        await query.message.reply_text(" Destek talebi kapatildi.")
        return
    if data.startswith("ad_reject_reason_"):
        if not can_manage(user_id):
            await query.message.reply_text(" Yetkin yok.")
            return
        parts = data.split("_")
        reason_code = parts[3]
        order_id = int(parts[4])
        reason_map = {
            "content": "Uygunsuz icerik",
            "link": "Link hatali",
            "missing": "Eksik bilgi",
            "rules": "Kurallara aykiri",
        }
        await reject_and_refund_ad(query.message, order_id, user_id, reason_map.get(reason_code, "Admin reddetti"))
        return

    try:
        await admin_callback(query, context, data)
    except Exception as e:
        logger.error("Callback hatasi: %s", e)
        context.user_data.clear()
        await query.message.reply_text(" Islem sirasinda hata oldu. Mod kapatildi.")


async def admin_callback(query, context, data):
    user_id = query.from_user.id
    if data == "admin_add_channel":
        if not can_manage(user_id):
            await query.message.reply_text(" Yetkin yok."); return
        context.user_data["mode"] = "add_channel"
        await query.message.reply_text(" Kanal bilgilerini yaz:\n\nKanalAdi | Fiyat | ChatID | SureGun | Aciklama | GorselURL\n\nOrnek:\nVIP | 2500 | -1001234567890 | 30 | Gunluk VIP kanal | https://site.com/resim.jpg\n\nGorsel yoksa son kismi bos birakabilirsin.")
    elif data == "admin_add_package":
        if not can_manage(user_id):
            await query.message.reply_text(" Yetkin yok."); return
        context.user_data["mode"] = "add_package"
        await query.message.reply_text(" Paket ekle:\n\nPaketAdi | Fiyat | SureGun | KanalIDleri | Aciklama\n\nOrnek:\nTumVIP | 6000 | 30 | 1,2,3 | Tum VIP kanallar")
    elif data == "admin_channels":
        await list_channels_manage(query.message)
    elif data == "admin_packages":
        await list_packages_manage(query.message)
    elif data == "admin_grant":
        await show_users_for_grant(query.message)
    elif data == "admin_sales":
        await sales_message(query.message)
    elif data == "admin_report":
        await report_message(query.message)
    elif data == "admin_channel_stats":
        await channel_stats_message(query.message)
    elif data == "admin_abandoned":
        await abandoned_message(query.message)
    elif data == "admin_users":
        await users_message(query.message)
    elif data == "admin_search_user":
        context.user_data["mode"] = "search_user"
        await query.message.reply_text(" Kullanici ID veya username yaz:")
    elif data == "admin_coupons":
        await coupons_message(query.message)
    elif data == "coupon_add":
        if not can_manage(user_id):
            await query.message.reply_text(" Yetkin yok."); return
        context.user_data["mode"] = "add_coupon"
        await query.message.reply_text(" Kupon olustur:\n\nKOD | YuzdeIndirim | StarsIndirim | MaxKullanim | KanalID/0\n\nOrnek:\nPASHA50 | 50 | 0 | 100 | 0")
    elif data.startswith("coupon_toggle_"):
        cid = int(data.split("_")[2])
        row = supabase.table("coupons").select("*").eq("id", cid).single().execute().data
        if row:
            supabase.table("coupons").update({"active": not bool(row.get("active"))}).eq("id", cid).execute()
        await log_event("coupon_toggled", user_id, details=f"coupon_id={cid}")
        await query.message.reply_text(" Kupon durumu degistirildi.")
    elif data == "admin_campaign":
        await campaign_message(query.message)
    elif data == "campaign_start":
        context.user_data["mode"] = "campaign_start"
        await query.message.reply_text(" Kampanya baslat:\n\nIndirimYuzde | Saat\n\nOrnek:\n30 | 6")
    elif data == "campaign_stop":
        set_setting("campaign_enabled", "off")
        await log_event("campaign_stopped", user_id)
        await query.message.reply_text(" Kampanya kapatildi.")
    elif data == "admin_referrals":
        await referrals_admin_message(query.message)
    elif data == "admin_giveaway":
        await giveaway_admin_message(query.message)
    elif data == "admin_pending_work":
        await pending_work_message(query.message)
    elif data == "admin_test_mode":
        current = test_mode_on()
        set_setting("test_mode", "off" if current else "on")
        await log_event("test_mode_toggled", user_id, details="off" if current else "on")
        await query.message.reply_text("Test modu degistirildi: " + ("KAPALI" if current else "ACIK"))
    elif data == "admin_ads":
        await ad_orders_admin_message(query.message)
    elif data == "admin_ad_channel_prices":
        await ad_channel_prices_admin_message(query.message)
    elif data.startswith("adchprice_"):
        if not can_manage(user_id):
            await query.message.reply_text(" Yetkin yok."); return
        context.user_data["mode"] = "edit_channel_ad_price"
        context.user_data["channel_id"] = int(data.split("_")[1])
        await query.message.reply_text("Bu kanal icin yeni reklam fiyatini Stars olarak yaz. Ornek: 1500")
    elif data == "admin_ad_packages":
        await query.message.reply_text("Reklam paketi sistemi kapatildi. Reklam fiyatlari kanal bazli ayarlaniyor.")
    elif data == "admin_add_ad_package":
        await query.message.reply_text("Reklam paketi sistemi kapatildi. Kullanici direkt kanal seciyor; fiyatlari Reklam Fiyatlari ekranindan kanal bazli ayarla.")
    elif data == "admin_ad_balances":
        await ad_balances_admin_message(query.message)
    elif data == "admin_ad_stats":
        await ad_stats_admin_message(query.message)
    elif data == "admin_system_test":
        await system_test_message(query.message, context)
    elif data.startswith("ad_views_"):
        context.user_data["mode"] = "ad_update_views"
        context.user_data["ad_order_id"] = int(data.split("_")[2])
        await query.message.reply_text("Goruntulenme sayisini yaz. Ornek: 1250")
    elif data.startswith("ad_approve_"):
        await approve_and_publish_ad(query.message, context, int(data.split("_")[2]), user_id)
    elif data.startswith("ad_reject_"):
        await reject_and_refund_ad(query.message, int(data.split("_")[2]), user_id)
    elif data.startswith("adpkg_toggle_"):
        await toggle_ad_package(query.message, int(data.split("_")[2]), user_id)
    elif data.startswith("adpkg_price_"):
        context.user_data["mode"] = "edit_ad_pkg_price"
        context.user_data["ad_package_id"] = int(data.split("_")[2])
        await query.message.reply_text("Yeni reklam paketi fiyatini Stars olarak yaz. Ornek: 1500")
    elif data.startswith("adpkg_desc_"):
        context.user_data["mode"] = "edit_ad_pkg_desc"
        context.user_data["ad_package_id"] = int(data.split("_")[2])
        await query.message.reply_text("Yeni reklam paketi aciklamasini yaz.")
    elif data.startswith("adpkg_target_"):
        context.user_data["mode"] = "edit_ad_pkg_target"
        context.user_data["ad_package_id"] = int(data.split("_")[2])
        await query.message.reply_text("Hedefi yaz:\nsingle | KanalID\nveya\nall | 0")
    elif data.startswith("adpkg_delete_"):
        await delete_ad_package(query.message, int(data.split("_")[2]), user_id)
    elif data == "giveaway_run":
        await run_giveaway(query.message, context, previous_week_key(), manual=True)
    elif data == "admin_faq":
        await faq_admin_message(query.message)
    elif data == "faq_add":
        context.user_data["mode"] = "add_faq"
        await query.message.reply_text("SSS ekle:\n\nSoru | Cevap")
    elif data.startswith("faq_toggle_"):
        fid = int(data.split("_")[2])
        row = supabase.table("faq").select("*").eq("id", fid).single().execute().data
        if row:
            supabase.table("faq").update({"active": not bool(row.get("active"))}).eq("id", fid).execute()
        await query.message.reply_text(" SSS durumu degistirildi.")
    elif data == "admin_broadcast":
        context.user_data["mode"] = "broadcast"
        await query.message.reply_text(" Tum kullanicilara gondermek istedigin duyuruyu yaz:")
    elif data == "admin_channel_id_help":
        await query.message.reply_text(" Grup/Kanal ID alma:\n\n1. Botu VIP grup/kanala yonetici yap.\n2. Mesaj gonder, kullanici davet et ve kullanici yasakla yetkilerini ac.\n3. VIP grup/kanal icine duz mesaj olarak sadece id yaz.\n4. Bot -100 ile baslayan Chat ID verir.")
    elif data == "admin_support":
        await support_requests_message(query.message)
    elif data == "admin_cancel":
        await cancel_requests_message(query.message)
    elif data == "admin_blacklist":
        await blacklist_message(query.message)
    elif data == "admin_admins":
        await admins_message(query.message)
    elif data == "admin_add_admin":
        if not is_owner(user_id):
            await query.message.reply_text(" Sadece owner admin ekleyebilir."); return
        context.user_data["mode"] = "add_admin"
        await query.message.reply_text(" Admin ekle:\n\nUserID | role\n\nRole: manager veya viewer\n\nCikmak icin: iptal")
    elif data.startswith("admin_toggle_"):
        if not is_owner(user_id):
            await query.message.reply_text(" Yetkin yok."); return
        tid = int(data.split("_")[2])
        row = supabase.table("admins").select("*").eq("user_id", tid).single().execute().data
        if row:
            supabase.table("admins").update({"active": not bool(row.get("active"))}).eq("user_id", tid).execute()
        await log_event("admin_toggled", user_id, target_user_id=tid)
        await query.message.reply_text(" Admin durumu degistirildi.")
    elif data == "admin_logs":
        await logs_message(query.message)
    elif data == "admin_export_sales":
        await export_sales_csv(query.message)
    elif data == "admin_maintenance":
        set_setting("maintenance", "off" if maintenance_on() else "on")
        await log_event("maintenance_toggled", user_id)
        await query.message.reply_text(" Bakim modu degistirildi.")
    elif data.startswith("ch_"):
        await handle_channel_admin_button(query, context)
    elif data.startswith("pkg_"):
        await handle_package_admin_button(query, context)
    elif data.startswith("grant_user_"):
        await show_channels_for_grant(query.message, int(data.split("_")[2]))
    elif data.startswith("grant_channel_"):
        parts = data.split("_")
        await show_grant_duration(query.message, int(parts[2]), int(parts[3]))
    elif data.startswith("grant_days_"):
        parts = data.split("_")
        await grant_vip_to_user(query.message, context, int(parts[2]), int(parts[3]), custom_days=int(parts[4]))
    elif data.startswith("grant_custom_"):
        parts = data.split("_")
        context.user_data["mode"] = "custom_grant_days"
        context.user_data["target_user_id"] = int(parts[2])
        context.user_data["channel_id"] = int(parts[3])
        await query.message.reply_text(" Kac gunluk VIP vermek istiyorsun? Ornek: 14")
    elif data.startswith("userdetail_"):
        await show_user_detail_by_id(query.message, int(data.split("_")[1]))
    elif data.startswith("usub_cancel_"):
        await admin_cancel_subscription(query.message, context, int(data.split("_")[2]))
    elif data.startswith("usub_link_"):
        await admin_resend_link_for_subscription(query.message, context, int(data.split("_")[2]))
    elif data.startswith("usub_extend_"):
        parts = data.split("_")
        await admin_extend_subscription(query.message, int(parts[2]), int(parts[3]))
    elif data.startswith("refund_sale_"):
        await mark_refund(query.message, user_id, int(data.split("_")[2]))
    elif data.startswith("blacklist_"):
        tid = int(data.split("_")[1])
        context.user_data["mode"] = "blacklist_reason"
        context.user_data["target_user_id"] = tid
        await query.message.reply_text(" Kara liste sebebini yaz:")
    elif data.startswith("unblacklist_"):
        tid = int(data.split("_")[1])
        supabase.table("blacklist").update({"active": False}).eq("user_id", tid).execute()
        await log_event("unblacklisted", user_id, target_user_id=tid)
        await query.message.reply_text(" Kullanici kara listeden cikarildi.")

# =========================================================
# CHANNEL/PACKAGE ADMIN
# =========================================================

async def handle_channel_admin_button(query, context):
    if not can_manage(query.from_user.id):
        await query.message.reply_text(" Yetkin yok."); return
    data = query.data
    if data.startswith("ch_delete_"):
        cid = int(data.split("_")[2])
        supabase.table("channels").delete().eq("id", cid).execute()
        await log_event("channel_deleted", query.from_user.id, channel_id=cid)
        await query.message.reply_text(" Kanal silindi.")
    elif data.startswith("ch_toggle_"):
        cid = int(data.split("_")[2])
        row = supabase.table("channels").select("*").eq("id", cid).single().execute().data
        if row:
            supabase.table("channels").update({"active": not bool(row.get("active"))}).eq("id", cid).execute()
        await query.message.reply_text(" Kanal aktif/pasif degistirildi.")
    else:
        parts = data.split("_")
        action, cid = parts[1], int(parts[2])
        maps = {
            "price": ("edit_price", " Yeni fiyati yaz. Ornek: 3000"),
            "duration": ("edit_duration", " Yeni sureyi gun olarak yaz. Ornek: 60"),
            "chat": ("edit_chat", " Yeni Chat ID yaz. Ornek: -1001234567890"),
            "description": ("edit_description", " Yeni aciklamayi yaz."),
            "photo": ("edit_photo", " Gorsel URL yaz. Bos birakmak icin - yaz."),
        }
        mode, prompt = maps[action]
        context.user_data["mode"] = mode
        context.user_data["channel_id"] = cid
        await query.message.reply_text(prompt)


async def handle_package_admin_button(query, context):
    if not can_manage(query.from_user.id):
        await query.message.reply_text(" Yetkin yok."); return
    data = query.data
    if data.startswith("pkg_delete_"):
        pid = int(data.split("_")[2])
        supabase.table("packages").delete().eq("id", pid).execute()
        await query.message.reply_text(" Paket silindi.")
    elif data.startswith("pkg_toggle_"):
        pid = int(data.split("_")[2])
        row = supabase.table("packages").select("*").eq("id", pid).single().execute().data
        if row:
            supabase.table("packages").update({"active": not bool(row.get("active"))}).eq("id", pid).execute()
        await query.message.reply_text(" Paket aktif/pasif degistirildi.")


async def list_channels_manage(message):
    rows = supabase.table("channels").select("*").order("id").execute().data or []
    if not rows:
        await message.reply_text(" Henuz kanal yok."); return
    for ch in rows:
        status = "Aktif " if ch.get("active") else "Pasif "
        kb = [
            [InlineKeyboardButton(" Fiyat", callback_data=f"ch_price_{ch['id']}"), InlineKeyboardButton(" Sure", callback_data=f"ch_duration_{ch['id']}")],
            [InlineKeyboardButton(" Chat ID", callback_data=f"ch_chat_{ch['id']}"), InlineKeyboardButton(" Aciklama", callback_data=f"ch_description_{ch['id']}")],
            [InlineKeyboardButton(" Gorsel", callback_data=f"ch_photo_{ch['id']}"), InlineKeyboardButton("Ac/Kapat", callback_data=f"ch_toggle_{ch['id']}")],
            [InlineKeyboardButton(" Sil", callback_data=f"ch_delete_{ch['id']}")],
        ]
        await message.reply_text(
            f" Kanal\n\nID: {ch['id']}\nAd: {ch.get('name')}\nFiyat: {ch.get('price')} \nSure: {ch.get('duration_days')} gun\nChat ID: {ch.get('chat_id')}\nDurum: {status}\nAciklama: {ch.get('description') or '-'}",
            reply_markup=InlineKeyboardMarkup(kb),
        )


async def list_packages_manage(message):
    rows = supabase.table("packages").select("*").order("id").execute().data or []
    if not rows:
        await message.reply_text(" Henuz paket yok."); return
    for p in rows:
        status = "Aktif " if p.get("active") else "Pasif "
        kb = [[InlineKeyboardButton("Ac/Kapat", callback_data=f"pkg_toggle_{p['id']}"), InlineKeyboardButton(" Sil", callback_data=f"pkg_delete_{p['id']}")]]
        await message.reply_text(
            f" Paket\n\nID: {p['id']}\nAd: {p.get('name')}\nFiyat: {p.get('price')} \nSure: {p.get('duration_days')} gun\nKanallar: {p.get('channel_ids')}\nDurum: {status}\nAciklama: {p.get('description') or '-'}",
            reply_markup=InlineKeyboardMarkup(kb),
        )

# =========================================================
# SUBSCRIPTIONS / GRANT / HISTORY
# =========================================================

async def upsert_subscription(user_id, channel_id, duration_days, price):
    current = now_utc()
    existing = (
        supabase.table("subscriptions")
        .select("*")
        .eq("user_id", int(user_id))
        .eq("channel_id", int(channel_id))
        .eq("status", "active")
        .execute()
    )
    if existing.data:
        sub = existing.data[0]
        old_end = parse_dt(sub.get("end_date")) or current
        base = old_end if old_end > current else current
        new_end = base + timedelta(days=int(duration_days))
        supabase.table("subscriptions").update(
            {"end_date": new_end.isoformat(), "price": int(price), "status": "active", "warn_3d_sent": False, "warn_1d_sent": False}
        ).eq("id", sub["id"]).execute()
        return sub.get("start_date"), new_end.isoformat()
    start = current
    end = start + timedelta(days=int(duration_days))
    supabase.table("subscriptions").insert(
        {"user_id": int(user_id), "channel_id": int(channel_id), "start_date": start.isoformat(), "end_date": end.isoformat(), "status": "active", "price": int(price), "warn_3d_sent": False, "warn_1d_sent": False}
    ).execute()
    return start.isoformat(), end.isoformat()


async def grant_vip_to_user(message, context, target_user_id, channel_id, custom_days=None):
    ch = await get_channel(channel_id)
    if not ch:
        await message.reply_text(" Kanal bulunamadi."); return
    days = int(custom_days or ch.get("duration_days") or DEFAULT_DURATION_DAYS)
    start_date, end_date = await upsert_subscription(target_user_id, channel_id, days, 0)
    vip_link = await safe_create_and_store_link(context, target_user_id, channel_id, ch)
    supabase.table("sales").insert({"user_id": target_user_id, "username": "manual_admin", "channel_id": channel_id, "price": 0, "payment_payload": "manual_admin_grant", "coupon_code": None, "refund_status": "none"}).execute()
    await log_event("vip_granted", message.chat_id, target_user_id, channel_id, f"{days} gun")
    if vip_link:
        try:
            await context.bot.send_message(target_user_id, f" Admin sana VIP erisim verdi!\n\n Kanal: {ch.get('name')}\n Tek kullanimlik giris linkin:\n{vip_link}\n\nBaslangic: {start_date}\nBitis: {end_date}")
            await message.reply_text(" VIP yetki verildi ve link kullaniciya gonderildi.")
        except Exception:
            await message.reply_text(f" VIP yetki verildi ama kullaniciya mesaj gonderilemedi. Linki manuel gonder:\n{vip_link}")
    else:
        await message.reply_text(" VIP yetki verildi ama davet linki uretilemedi. Botun grupta/kanalda admin oldugundan emin ol.")


async def show_my_subscriptions(message, user_id):
    rows = supabase.table("subscriptions").select("*").eq("user_id", int(user_id)).eq("status", "active").execute().data or []
    if not rows:
        await message.reply_text("\U0001f4c5 Aktif \u00fcyelik bulunamad\u0131."); return
    await message.reply_text("\U0001f4c5 \u00dcyeli\u011fim\n\nLink yenileme ve iptal talebi sadece a\u015fa\u011f\u0131daki aktif abonelik kartlar\u0131ndan yap\u0131l\u0131r.")
    for sub in rows:
        ch = await get_channel(sub["channel_id"])
        name = ch.get("name") if ch else f"Kanal ID {sub['channel_id']}"
        kb = [
            [InlineKeyboardButton(" Bu uyeligi uzat", callback_data=f"buyc_{sub['channel_id']}")],
            [InlineKeyboardButton(" Yeni link gonder", callback_data=f"resend_{sub['id']}"), InlineKeyboardButton("\u274c Iptal talebi", callback_data=f"request_cancel_{sub['id']}")],
        ]
        await message.reply_text(f" Aktif uyeligin:\n\n Kanal: {name}\nBaslangic: {sub.get('start_date')}\nBitis: {sub.get('end_date')}\nDurum: {sub.get('status')}", reply_markup=InlineKeyboardMarkup(kb))


async def my_history(message, user_id):
    sales = supabase.table("sales").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute().data or []
    subs = supabase.table("subscriptions").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute().data or []
    text = " Gecmisin\n\n"
    text += "Satin almalar:\n" if sales else "Satin alma gecmisi yok.\n"
    for s in sales:
        ch = await get_channel(s.get("channel_id")) if s.get("channel_id") else None
        name = ch.get("name") if ch else f"Kanal ID {s.get('channel_id')}"
        text += f"- {name} | {s.get('price')} Stars | {s.get('created_at')}\n"
    text += "\nUyelikler:\n" if subs else "\nUyelik gecmisi yok."
    for sub in subs:
        ch = await get_channel(sub.get("channel_id"))
        name = ch.get("name") if ch else f"Kanal ID {sub.get('channel_id')}"
        text += f"- {name} | {sub.get('status')} | Bitis: {sub.get('end_date')}\n"
    await message.reply_text(text[:3900])

# =========================================================
# PAYMENTS / COUPONS / CAMPAIGN
# =========================================================

async def get_coupon(code):
    if not code:
        return None
    res = supabase.table("coupons").select("*").eq("code", code.upper()).execute()
    return res.data[0] if res.data else None


async def calculate_price(user_id, base_price, channel_id=None):
    price = max(1, int(base_price))
    camp = campaign_percent()
    if camp:
        price = int(price * (100 - camp) / 100)
    row = await get_user_row(user_id)
    code = row.get("active_coupon") if row else None
    coupon = await get_coupon(code) if code else None
    if not coupon or not coupon.get("active"):
        return max(1, price), None, None
    coupon_channel = coupon.get("channel_id")
    if coupon_channel and channel_id and int(coupon_channel) != int(channel_id):
        return max(1, price), None, None
    max_uses = int(coupon.get("max_uses") or 0)
    used = int(coupon.get("used_count") or 0)
    if max_uses > 0 and used >= max_uses:
        return max(1, price), None, None
    percent = int(coupon.get("discount_percent") or 0)
    stars = int(coupon.get("discount_stars") or 0)
    if percent > 0:
        price = int(price * (100 - percent) / 100)
    if stars > 0:
        price -= stars
    discount_text = f"%{percent} indirim" if percent > 0 else f"{stars} Stars indirim"
    return max(1, price), code.upper(), discount_text


async def create_checkout_intent(user, item_type, item_id, price, payload):
    try:
        supabase.table("checkout_intents").insert({"user_id": user.id, "username": safe_username(user), "item_type": item_type, "item_id": item_id, "price": price, "payload": payload, "status": "started", "reminder_sent": False}).execute()
    except Exception as e:
        logger.warning("Checkout kaydedilemedi: %s", e)


async def handle_buy_channel(query, context):
    if maintenance_on() and not is_admin(query.from_user.id):
        await query.message.reply_text(" Bot bakim modunda. Satin alma gecici olarak kapali."); return
    if await is_blacklisted(query.from_user.id) and not is_admin(query.from_user.id):
        await query.message.reply_text(" Satin alma yetkin kisitlandi."); return
    channel_id = int(query.data.split("_")[1])
    ch = await get_channel(channel_id)
    if not ch or not ch.get("active"):
        await query.message.reply_text(" Kanal bulunamadi veya pasif."); return
    price, coupon_code, _ = await calculate_price(query.from_user.id, int(ch.get("price") or 1), channel_id)
    payload = f"channel_{channel_id}_{price}_{coupon_code or 'NONE'}_{ab_variant(query.from_user.id)}"
    await create_checkout_intent(query.from_user, "channel", channel_id, price, payload)
    await context.bot.send_invoice(chat_id=query.message.chat_id, title=f"{ch.get('name')} VIP Uyelik", description=f"{ch.get('duration_days') or DEFAULT_DURATION_DAYS} gunluk VIP uyelik.", payload=payload, provider_token="", currency="XTR", prices=[LabeledPrice(label=ch.get("name"), amount=price)])


async def handle_buy_package(query, context):
    package_id = int(query.data.split("_")[1])
    p = await get_package(package_id)
    if not p or not p.get("active"):
        await query.message.reply_text(" Paket bulunamadi veya pasif."); return
    price, coupon_code, _ = await calculate_price(query.from_user.id, int(p.get("price") or 1), None)
    payload = f"package_{package_id}_{price}_{coupon_code or 'NONE'}_{ab_variant(query.from_user.id)}"
    await create_checkout_intent(query.from_user, "package", package_id, price, payload)
    await context.bot.send_invoice(chat_id=query.message.chat_id, title=f"{p.get('name')} VIP Paket", description=f"{p.get('duration_days') or DEFAULT_DURATION_DAYS} gunluk paket.", payload=payload, provider_token="", currency="XTR", prices=[LabeledPrice(label=p.get("name"), amount=price)])


async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = update.message.successful_payment.invoice_payload
    user = update.effective_user
    if payload.startswith("topup_"):
        amount = int(payload.split("_", 1)[1])
        await change_ad_balance(user.id, amount, "topup", "Stars bakiye yukleme")
        await log_event("ad_balance_topup", user.id, user.id, details=f"{amount} Stars")
        await update.message.reply_text(f" Bakiye yuklendi: {amount} Stars\n\nGuncel bakiye: {await get_ad_balance(user.id)} Stars")
        await context.bot.send_message(OWNER_ID, f" Yeni reklam bakiyesi yukleme\n\nKullanici: @{safe_username(user) or 'yok'}\nID: {user.id}\nTutar: {amount} Stars")
        return
    parts = payload.split("_", 4)
    item_type, item_id, paid_price = parts[0], int(parts[1]), int(parts[2])
    coupon_code = parts[3] if len(parts) > 3 and parts[3] != "NONE" else None
    variant = parts[4] if len(parts) > 4 else ab_variant(user.id)
    links = []
    sale_channel_id = None
    package_id = None
    item_name = "VIP"
    duration = DEFAULT_DURATION_DAYS
    if item_type == "channel":
        ch = await get_channel(item_id)
        if not ch:
            await update.message.reply_text(" Odeme alindi ama kanal bulunamadi. Admin ile iletisime gec."); return
        sale_channel_id = item_id
        item_name = ch.get("name")
        duration = int(ch.get("duration_days") or DEFAULT_DURATION_DAYS)
        start_date, end_date = await upsert_subscription(user.id, item_id, duration, paid_price)
        link = await safe_create_and_store_link(context, user.id, item_id, ch)
        if link:
            links.append((item_name, link))
    else:
        p = await get_package(item_id)
        if not p:
            await update.message.reply_text(" Odeme alindi ama paket bulunamadi. Admin ile iletisime gec."); return
        package_id = item_id
        item_name = p.get("name")
        duration = int(p.get("duration_days") or DEFAULT_DURATION_DAYS)
        for cid in parse_channel_ids(p.get("channel_ids")):
            ch = await get_channel(cid)
            if not ch:
                continue
            sale_channel_id = cid
            start_date, end_date = await upsert_subscription(user.id, cid, duration, paid_price)
            link = await safe_create_and_store_link(context, user.id, cid, ch)
            if link:
                links.append((ch.get("name"), link))
    supabase.table("sales").insert({"user_id": user.id, "username": safe_username(user), "channel_id": sale_channel_id, "package_id": package_id, "price": paid_price, "payment_payload": payload, "coupon_code": coupon_code, "refund_status": "none", "ab_variant": variant}).execute()
    supabase.table("checkout_intents").update({"status": "paid"}).eq("payload", payload).execute()
    if coupon_code:
        coupon = await get_coupon(coupon_code)
        if coupon:
            supabase.table("coupons").update({"used_count": int(coupon.get("used_count") or 0) + 1}).eq("id", coupon["id"]).execute()
        supabase.table("users").update({"active_coupon": None}).eq("user_id", user.id).execute()
    await handle_referral_purchase_bonus(context, user.id)
    await log_event("payment_success", user.id, user.id, sale_channel_id, f"{paid_price} Stars")
    await context.bot.send_message(OWNER_ID, f" Yeni satis!\n\nKullanici: @{safe_username(user) or 'yok'}\nUser ID: {user.id}\nUrun: {item_name}\nFiyat: {paid_price} Stars\nKupon: {coupon_code or 'Yok'}")
    if links:
        link_text = "\n\n".join([f" {name}\n {link}" for name, link in links])
        await update.message.reply_text(f" Odeme basarili!\n\n{link_text}\n\n Linkler {INVITE_LINK_EXPIRE_MINUTES} dakika gecerlidir ve tek kullanimliktir.")
    else:
        await update.message.reply_text(" Odeme basarili fakat otomatik davet linki uretilemedi. Admin ile iletisime gec.")

# =========================================================
# REFERRALS / GIVEAWAY
# =========================================================


async def add_referral_points(referrer_id, referred_id, points, event_type):
    """Add referral points safely even if an older SQL schema is installed."""
    week = current_week_key()
    pts = int(points or 0)
    if not referrer_id or pts <= 0:
        return

    try:
        supabase.table("referral_events").insert({
            "referrer_id": int(referrer_id),
            "referred_id": int(referred_id) if referred_id else None,
            "points": pts,
            "event_type": event_type,
            "week_key": week,
        }).execute()
    except Exception as e:
        logger.warning("referral_events week_key insert failed, fallback: %s", e)
        try:
            supabase.table("referral_events").insert({
                "referrer_id": int(referrer_id),
                "referred_id": int(referred_id) if referred_id else None,
                "points": pts,
                "event_type": event_type,
            }).execute()
        except Exception as e2:
            logger.warning("referral_events insert failed: %s", e2)

    row = await get_user_row(referrer_id)
    if not row:
        return

    current_points = int(row.get("referral_points") or 0)
    current_total = int(row.get("referral_total_points") or row.get("referral_entries") or current_points or 0)
    current_entries = int(row.get("referral_entries") or 0)

    payload = {"referral_points": current_points + pts}
    if "referral_total_points" in row:
        payload["referral_total_points"] = current_total + pts
    if "referral_entries" in row:
        payload["referral_entries"] = current_entries + pts

    try:
        supabase.table("users").update(payload).eq("user_id", int(referrer_id)).execute()
    except Exception as e:
        logger.warning("referral user update failed, minimal fallback: %s", e)
        try:
            supabase.table("users").update({"referral_points": current_points + pts}).eq("user_id", int(referrer_id)).execute()
        except Exception as e2:
            logger.warning("minimal referral update failed: %s", e2)

async def handle_referral_purchase_bonus(context, buyer_id):
    row = await get_user_row(buyer_id)
    if not row or not row.get("referrer_id") or row.get("referral_purchase_reward_given"):
        return
    referrer_id = int(row["referrer_id"])
    pts = get_referral_purchase_points()
    await add_referral_points(referrer_id, buyer_id, pts, "purchase")
    supabase.table("users").update({"referral_purchase_reward_given": True}).eq("user_id", buyer_id).execute()
    bonus_days = get_referral_bonus_days()
    await extend_first_active_or_default_subscription(context, referrer_id, bonus_days)
    try:
        await context.bot.send_message(referrer_id, f"Referansin ilk satin almayi yapti! +{pts} puan ve +{bonus_days} gun bonus kazandin.")
    except Exception:
        pass


async def extend_first_active_or_default_subscription(context, user_id, days):
    active = supabase.table("subscriptions").select("*").eq("user_id", user_id).eq("status", "active").limit(1).execute().data or []
    if active:
        sub = active[0]
        await admin_extend_subscription_simple(sub["id"], days)
        return sub.get("channel_id")
    ch = await get_first_active_channel()
    if not ch:
        return None
    await upsert_subscription(user_id, ch["id"], days, 0)
    link = await safe_create_and_store_link(context, user_id, ch["id"], ch)
    try:
        await context.bot.send_message(user_id, f" Bonus VIP kazandin!\n\n {ch.get('name')}\n {link or 'Link uretilemedi, admin ile iletisime gec.'}")
    except Exception:
        pass
    return ch["id"]



async def referral_user_message(message, context, user_id):
    try:
        me = await context.bot.get_me()
        row = await get_user_row(user_id) or {}
        points = int(row.get("referral_points") or 0)
        total = int(row.get("referral_total_points") or row.get("referral_entries") or points or 0)
        link = f"https://t.me/{me.username}?start=ref_{user_id}"
        kb = [
            [InlineKeyboardButton("\U0001f381 3 puan = 1 g\u00fcn", callback_data="redeem_3_1")],
            [InlineKeyboardButton("\U0001f525 10 puan = 7 g\u00fcn", callback_data="redeem_10_7")],
            [InlineKeyboardButton("\U0001f451 25 puan = 30 g\u00fcn", callback_data="redeem_25_30")],
        ]
        await message.reply_text(
            "\U0001f381 Davet Et Kazan\n\n"
            f"Senin linkin:\n{link}\n\n"
            f"Mevcut puan: {points}\n"
            f"Toplam puan: {total}\n\n"
            f"1 yeni kullan\u0131c\u0131 = +{get_referral_invite_points()} puan\n"
            f"\u0130lk sat\u0131n alma = +{get_referral_purchase_points()} puan + bonus g\u00fcn",
            reply_markup=InlineKeyboardMarkup(kb),
        )
    except Exception as e:
        logger.error("referral_user_message error: %s", e)
        await message.reply_text("\u274c Referans bilgisi al\u0131namad\u0131. SQL patch \u00e7al\u0131\u015ft\u0131r\u0131ld\u0131 m\u0131 kontrol et.")


async def redeem_referral_reward(query, context):
    try:
        _, cost, days = query.data.split("_")
        cost, days = int(cost), int(days)
        row = await get_user_row(query.from_user.id) or {}
        points = int(row.get("referral_points") or 0)
        if points < cost:
            await query.message.reply_text(f"\u274c Yetersiz puan. Gerekli: {cost}, mevcut: {points}")
            return

        ch = await get_first_active_channel()
        active = supabase.table("subscriptions").select("*").eq("user_id", query.from_user.id).eq("status", "active").limit(1).execute().data or []
        if not ch and not active:
            await query.message.reply_text("\u274c \u00d6d\u00fcl verilecek aktif kanal yok. \u00d6nce admin panelden en az bir VIP kanal ekle.")
            return

        supabase.table("users").update({"referral_points": points - cost}).eq("user_id", query.from_user.id).execute()
        await extend_first_active_or_default_subscription(context, query.from_user.id, days)
        await log_event("referral_reward_redeemed", query.from_user.id, query.from_user.id, details=f"{cost} puan -> {days} gun")
        await query.message.reply_text(f"\u2705 {cost} puan harcand\u0131, {days} g\u00fcn VIP \u00f6d\u00fcl uyguland\u0131.")
    except Exception as e:
        logger.error("redeem_referral_reward error: %s", e)
        await query.message.reply_text("\u274c \u00d6d\u00fcl kullan\u0131lamad\u0131. SQL patch ve aktif kanal kontrol\u00fc yap.")


async def leaderboard_message(message):
    try:
        rows = supabase.table("users").select("*").execute().data or []
    except Exception as e:
        logger.error("leaderboard users query failed: %s", e)
        await message.reply_text("\u274c Liderlik verisi okunamad\u0131. SQL patch'i \u00e7al\u0131\u015ft\u0131rman gerekiyor.")
        return

    scored = []
    for u in rows:
        score = int(u.get("referral_total_points") or u.get("referral_entries") or u.get("referral_points") or 0)
        if score > 0:
            scored.append((score, u))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        await message.reply_text(
            "\U0001f3c6 Liderlik Tablosu\n\n"
            "Hen\u00fcz puanl\u0131 kullan\u0131c\u0131 yok.\n\n"
            "Kullan\u0131c\u0131lar Referans butonundan link payla\u015f\u0131nca burada g\u00f6r\u00fcnecek."
        )
        return

    text = "\U0001f3c6 Liderlik Tablosu\n\n"
    for i, (score, u) in enumerate(scored[:10], start=1):
        name = f"@{u.get('username')}" if u.get("username") else str(u.get("user_id"))
        text += f"{i}. {name} - {score} puan\n"

    await message.reply_text(text)


async def referrals_admin_message(message):
    try:
        events = supabase.table("referral_events").select("*").execute().data or []
    except Exception as e:
        logger.error("referrals_admin_message error: %s", e)
        await message.reply_text("\u274c Referans olaylar\u0131 okunamad\u0131. SQL patch \u00e7al\u0131\u015ft\u0131r.")
        return

    joins = len([e for e in events if e.get("event_type") == "join"])
    purchases = len([e for e in events if e.get("event_type") == "purchase"])
    total_points = sum(int(e.get("points") or e.get("entries") or 0) for e in events)

    await message.reply_text(
        "\U0001f381 Referans Paneli\n\n"
        f"Toplam referans kay\u0131t: {joins}\n"
        f"Sat\u0131n almaya d\u00f6nen: {purchases}\n"
        f"Toplam \u00e7ekili\u015f hakk\u0131/puan: {total_points}"
    )
    await leaderboard_message(message)


def referral_event_points(row):
    return int(row.get("points") or row.get("entries") or 0)


def filter_events_for_week(rows, week):
    with_week = [r for r in rows if r.get("week_key")]
    if with_week:
        return [r for r in with_week if r.get("week_key") == week]
    return rows


async def get_referral_events_safe(week=None):
    try:
        rows = supabase.table("referral_events").select("*").execute().data or []
    except Exception as e:
        logger.error("referral_events query failed: %s", e)
        return []
    if week:
        return filter_events_for_week(rows, week)
    return rows


async def giveaway_user_message(message):
    week = current_week_key()
    rows = await get_referral_events_safe(week)
    total_points = sum(referral_event_points(r) for r in rows)
    participants = len(set(r.get("referrer_id") for r in rows if r.get("referrer_id") and referral_event_points(r) > 0))

    await message.reply_text(
        "\U0001f389 Haftal\u0131k \u00c7ekili\u015f\n\n"
        f"Bu hafta kat\u0131l\u0131mc\u0131: {participants}\n"
        f"Toplam \u00e7ekili\u015f hakk\u0131: {total_points}\n\n"
        "Her referans puan\u0131 \u00e7ekili\u015f hakk\u0131d\u0131r.\n"
        f"Haftan\u0131n kazanan\u0131 {get_weekly_winner_prize_days()} g\u00fcn VIP al\u0131r."
    )

async def giveaway_admin_message(message):
    await giveaway_user_message(message)
    kb = [[InlineKeyboardButton("Cekilisi Simdi Yap", callback_data="giveaway_run")]]
    await message.reply_text("Admin cekilis paneli", reply_markup=InlineKeyboardMarkup(kb))



async def run_giveaway(message, context, week_key, manual=False):
    rows = await get_referral_events_safe(week_key)
    tickets = []

    for r in rows:
        rid = r.get("referrer_id")
        pts = referral_event_points(r)
        if rid and pts > 0:
            tickets.extend([int(rid)] * pts)

    if not tickets:
        await message.reply_text(
            "\u274c Bu hafta \u00e7ekili\u015f hakk\u0131 yok.\n\n"
            "Bir kullan\u0131c\u0131 Referans linkiyle arkada\u015f getirince \u00e7ekili\u015f hakk\u0131 olu\u015fur."
        )
        return

    winner = random.choice(tickets)
    days = get_weekly_winner_prize_days()
    cid = await extend_first_active_or_default_subscription(context, winner, days)

    stored = False
    for table_name in ["giveaway_winners", "raffle_winners"]:
        try:
            payload = {"week_key": week_key, "user_id": winner, "channel_id": cid}
            if table_name == "giveaway_winners":
                payload["prize_days"] = days
            else:
                payload["reward_days"] = days
            supabase.table(table_name).insert(payload).execute()
            stored = True
            break
        except Exception as e:
            logger.warning("winner insert failed for %s: %s", table_name, e)

    await log_event("giveaway_winner", None, winner, cid, f"week={week_key}, days={days}, stored={stored}")

    try:
        await context.bot.send_message(winner, f"\U0001f389 Haftal\u0131k \u00e7ekili\u015fi kazand\u0131n! {days} g\u00fcn VIP \u00f6d\u00fcl uyguland\u0131.")
    except Exception:
        pass

    await message.reply_text(f"\U0001f389 Kazanan: {winner}\n\U0001f381 \u00d6d\u00fcl: {days} g\u00fcn VIP")

async def support_menu(message):
    kb = [
        [InlineKeyboardButton(" Link calismiyor", callback_data="support_auto_link")],
        [InlineKeyboardButton(" Odeme yaptim", callback_data="support_auto_payment")],
        [InlineKeyboardButton(" Uyelik tarihi", callback_data="support_auto_date")],
        [InlineKeyboardButton(" Kupon calismiyor", callback_data="support_auto_coupon")],
        [InlineKeyboardButton(" Admin ile konus", callback_data="support_auto_admin")],
    ]
    await message.reply_text(" Sorunun ne?", reply_markup=InlineKeyboardMarkup(kb))


async def support_auto_answer(message, key):
    answers = {
        "link": "Uyeligim bolumunden Yeni link gonder butonuna bas. Link yine calismazsa destek mesaji yaz.",
        "payment": " Odeme yaptiysan Uyeligim bolumunde aktif uyeligin gorunmeli. Gorunmuyorsa destek mesaji yaz.",
        "date": "Uyeligim bolumunde baslangic ve bitis tarihini gorebilirsin.",
        "coupon": " Kupon kodunu Kupon Gir bolumunden yaz. Bazi kuponlar sadece belirli kanal icin gecerli olabilir.",
        "admin": " Sorununu tek mesaj olarak yaz; admin'e iletilecek.",
    }
    if key == "admin":
        # mode is per user, but we only have message here. A new text will go to menu without mode. Ask user to use Destek menu.
        await message.reply_text(" Admin'e yazmak icin ana menude Destek butonuna basip mesajini yaz.")
    else:
        await message.reply_text(answers.get(key, "Destek icin Destek butonunu kullan."))


async def faq_user_message(message):
    rows = supabase.table("faq").select("*").eq("active", True).order("id").execute().data or []
    rows = clean_faq_rows(rows)
    if not rows:
        await message.reply_text("\u2753 Hen\u00fcz SSS eklenmedi."); return
    kb = [[InlineKeyboardButton(row.get("question") or f"SSS {row['id']}", callback_data=f"faq_view_{row['id']}")] for row in rows[:40]]
    await message.reply_text("\u2753 S\u0131k Sorulan Sorular", reply_markup=InlineKeyboardMarkup(kb))


async def faq_answer(message, faq_id):
    row = supabase.table("faq").select("*").eq("id", faq_id).single().execute().data
    if not row or is_bad_text(row.get("question")) or is_bad_text(row.get("answer")):
        await message.reply_text("\u274c SSS bulunamad\u0131."); return
    await message.reply_text(f"\u2753 {row.get('question')}\n\n{row.get('answer')}")


async def faq_admin_message(message):
    rows = supabase.table("faq").select("*").order("id", desc=True).execute().data or []
    rows = clean_faq_rows(rows)
    await message.reply_text("\u2753 SSS Y\u00f6netimi", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\u2795 SSS Ekle", callback_data="faq_add")]]))
    for row in rows[:30]:
        status = "Aktif \u2705" if row.get("active") else "Pasif \u26d4"
        await message.reply_text(f"ID: {row['id']}\nSoru: {row.get('question')}\nDurum: {status}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("A\u00e7/Kapat", callback_data=f"faq_toggle_{row['id']}")]]))


async def create_cancel_request(update, context):
    rows = supabase.table("subscriptions").select("*").eq("user_id", update.effective_user.id).eq("status", "active").execute().data or []
    if not rows:
        await update.message.reply_text(" Aktif uyeligin olmadigi icin iptal talebi olusturulamaz."); return
    for sub in rows:
        await create_cancel_request_for_sub(update.message, context, sub)


async def request_cancel_from_button(query, context):
    sub_id = int(query.data.split("_")[2])
    sub = await get_subscription(sub_id)
    if not sub or int(sub.get("user_id")) != query.from_user.id or sub.get("status") != "active":
        await query.message.reply_text(" Aktif uyelik bulunamadi."); return
    await create_cancel_request_for_sub(query.message, context, sub)


async def create_cancel_request_for_sub(message, context, sub):
    existing = supabase.table("cancel_requests").select("*").eq("user_id", sub["user_id"]).eq("channel_id", sub["channel_id"]).eq("status", "pending").execute().data or []
    if existing:
        await message.reply_text(" Zaten bekleyen iptal talebin var."); return
    supabase.table("cancel_requests").insert({"user_id": sub["user_id"], "channel_id": sub["channel_id"], "status": "pending"}).execute()
    await log_event("cancel_requested", sub["user_id"], sub["user_id"], sub["channel_id"])
    await message.reply_text("Iptal talebin admin onayina gonderildi.")
    await context.bot.send_message(OWNER_ID, f" Yeni iptal talebi!\n\nKullanici ID: {sub['user_id']}\nKanal ID: {sub['channel_id']}")

# =========================================================
# ADMIN LISTS / REPORTS / USER DETAILS
# =========================================================

async def show_users_for_grant(message):
    rows = supabase.table("users").select("*").order("id", desc=True).limit(20).execute().data or []
    if not rows:
        await message.reply_text(" Henuz kullanici yok."); return
    for u in rows:
        username = f"@{u.get('username')}" if u.get("username") else "username yok"
        kb = [[InlineKeyboardButton(" Detay", callback_data=f"userdetail_{u['user_id']}")], [InlineKeyboardButton(" VIP Ver", callback_data=f"grant_user_{u['user_id']}")]]
        await message.reply_text(f" {username}\nID: {u['user_id']}", reply_markup=InlineKeyboardMarkup(kb))


async def show_channels_for_grant(message, target_user_id):
    rows = supabase.table("channels").select("*").eq("active", True).order("id").execute().data or []
    if not rows:
        await message.reply_text(" Once kanal eklemelisin."); return
    for ch in rows:
        await message.reply_text(f" Kanal sec\n\nAd: {ch.get('name')}\nFiyat: {ch.get('price')} \nSure: {ch.get('duration_days')} gun", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f" {ch.get('name')} sec", callback_data=f"grant_channel_{target_user_id}_{ch['id']}")]]))


async def show_grant_duration(message, target_user_id, channel_id):
    kb = [[InlineKeyboardButton(" 7 Gun", callback_data=f"grant_days_{target_user_id}_{channel_id}_7"), InlineKeyboardButton(" 30 Gun", callback_data=f"grant_days_{target_user_id}_{channel_id}_30")], [InlineKeyboardButton(" 90 Gun", callback_data=f"grant_days_{target_user_id}_{channel_id}_90"), InlineKeyboardButton(" Ozel Sure", callback_data=f"grant_custom_{target_user_id}_{channel_id}")]]
    await message.reply_text(" VIP suresini sec:", reply_markup=InlineKeyboardMarkup(kb))


async def search_user(message, query):
    q = query.replace("@", "").strip()
    if q.isdigit():
        rows = supabase.table("users").select("*").eq("user_id", int(q)).execute().data or []
    else:
        rows = supabase.table("users").select("*").ilike("username", f"%{q}%").execute().data or []
    if not rows:
        await message.reply_text(" Kullanici bulunamadi."); return
    for row in rows[:5]:
        await show_user_detail(message, row)


async def show_user_detail_by_id(message, user_id):
    row = await get_user_row(user_id)
    if not row:
        await message.reply_text(" Kullanici bulunamadi."); return
    await show_user_detail(message, row)


async def show_user_detail(message, user_row):
    user_id = user_row["user_id"]
    username = f"@{user_row.get('username')}" if user_row.get("username") else "username yok"
    blacklisted = await is_blacklisted(user_id)
    kb_top = [[InlineKeyboardButton(" VIP Ver", callback_data=f"grant_user_{user_id}")], [InlineKeyboardButton(" Kara Listeye Al", callback_data=f"blacklist_{user_id}")] if not blacklisted else [InlineKeyboardButton(" Kara Listeden Cikar", callback_data=f"unblacklist_{user_id}")]]
    await message.reply_text(f" Kullanici Detayi\n\nID: {user_id}\nUsername: {username}\nKara liste: {'Evet' if blacklisted else 'Hayir'}\nReferans puan: {user_row.get('referral_points') or 0}", reply_markup=InlineKeyboardMarkup(kb_top))
    subs = supabase.table("subscriptions").select("*").eq("user_id", user_id).order("id", desc=True).execute().data or []
    if not subs:
        await message.reply_text("Uyelik yok."); return
    for sub in subs:
        ch = await get_channel(sub.get("channel_id"))
        name = ch.get("name") if ch else f"Kanal ID {sub.get('channel_id')}"
        kb = [[InlineKeyboardButton("Iptal Et", callback_data=f"usub_cancel_{sub['id']}"), InlineKeyboardButton(" Link Gonder", callback_data=f"usub_link_{sub['id']}")], [InlineKeyboardButton("+7 gun", callback_data=f"usub_extend_{sub['id']}_7"), InlineKeyboardButton("+30 gun", callback_data=f"usub_extend_{sub['id']}_30")]]
        await message.reply_text(f" {name}\nDurum: {sub.get('status')}\nBitis: {sub.get('end_date')}", reply_markup=InlineKeyboardMarkup(kb))


async def users_message(message):
    await show_users_for_grant(message)


async def sales_message(message):
    rows = supabase.table("sales").select("*").order("id", desc=True).limit(20).execute().data or []
    if not rows:
        await message.reply_text(" Henuz satis yok."); return
    for s in rows:
        refund = s.get("refund_status") or "none"
        kb = [] if refund == "refunded" else [[InlineKeyboardButton(" Iade Isaretle", callback_data=f"refund_sale_{s['id']}")]]
        await message.reply_text(f" Satis\n\nID: {s['id']}\nKullanici: @{s.get('username') or 'yok'}\nUser ID: {s.get('user_id')}\nKanal ID: {s.get('channel_id')}\nPaket ID: {s.get('package_id') or '-'}\nFiyat: {s.get('price')} \nKupon: {s.get('coupon_code') or 'Yok'}\nIade: {refund}\nTarih: {s.get('created_at')}", reply_markup=InlineKeyboardMarkup(kb) if kb else None)


async def report_message(message):
    rows = supabase.table("sales").select("*").execute().data or []
    today, month = now_utc().date().isoformat(), now_utc().strftime("%Y-%m")
    tc = ts = mc = ms = totalc = totals = refundc = 0
    for s in rows:
        if s.get("refund_status") == "refunded":
            refundc += 1; continue
        price, created = safe_int(s.get("price"), 0), str(s.get("created_at") or "")
        totalc += 1; totals += price
        if created.startswith(today): tc += 1; ts += price
        if created.startswith(month): mc += 1; ms += price
    await message.reply_text(f" Satis Raporu\n\nBugun satis: {tc}\nBugun Stars: {ts}\n\nBu ay satis: {mc}\nBu ay Stars: {ms}\n\nToplam satis: {totalc}\nToplam Stars: {totals}\nIade isaretli satis: {refundc}")


async def channel_stats_message(message):
    rows = supabase.table("sales").select("*").execute().data or []
    stats = {}
    for s in rows:
        if s.get("refund_status") == "refunded" or not s.get("channel_id"):
            continue
        cid = s.get("channel_id")
        stats.setdefault(cid, {"count": 0, "stars": 0})
        stats[cid]["count"] += 1
        stats[cid]["stars"] += safe_int(s.get("price"), 0)
    if not stats:
        await message.reply_text(" Henuz kanal satisi yok."); return
    text = " Kanal Bazli Istatistik\n\n"
    for cid, val in stats.items():
        ch = await get_channel(cid)
        name = ch.get("name") if ch else f"Kanal ID {cid}"
        text += f" {name}\nSatis: {val['count']}\nStars: {val['stars']}\n\n"
    await message.reply_text(text)


async def abandoned_message(message):
    rows = supabase.table("checkout_intents").select("*").eq("status", "started").order("id", desc=True).limit(20).execute().data or []
    if not rows:
        await message.reply_text(" Yarim kalan odeme yok."); return
    text = " Yarim Kalan Odemeler\n\n"
    for r in rows:
        text += f"ID: {r['id']} | User: {r.get('user_id')} | {r.get('item_type')} {r.get('item_id')} | {r.get('price')}  | Hatirlatma: {r.get('reminder_sent')}\n"
    await message.reply_text(text[:3900])


async def coupons_message(message):
    rows = supabase.table("coupons").select("*").order("id", desc=True).execute().data or []
    await message.reply_text("\U0001f39f\ufe0f Kuponlar", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(" Kupon Olustur", callback_data="coupon_add")]]))
    if not rows:
        await message.reply_text("Henuz kupon yok."); return
    for c in rows[:30]:
        status = "Aktif " if c.get("active") else "Pasif "
        ch_text = f"Kanal ID: {c.get('channel_id')}" if c.get("channel_id") else "Tum kanallar"
        await message.reply_text(f"Kupon: {c.get('code')}\nYuzde: %{c.get('discount_percent') or 0}\nStars indirim: {c.get('discount_stars') or 0}\nGecerli: {ch_text}\nKullanim: {c.get('used_count') or 0}/{c.get('max_uses') or ''}\nDurum: {status}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Ac/Kapat", callback_data=f"coupon_toggle_{c['id']}")]]))


async def campaign_message(message):
    text = f" Kampanya\n\nDurum: {'Aktif' if campaign_active() else 'Kapali'}\nIndirim: %{get_setting('campaign_percent', '0')}\nBitis: {get_setting('campaign_end', '') or '-'}"
    kb = [[InlineKeyboardButton(" Baslat", callback_data="campaign_start"), InlineKeyboardButton(" Kapat", callback_data="campaign_stop")]]
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def support_requests_message(message):
    rows = supabase.table("support_requests").select("*").eq("status", "open").order("id", desc=True).limit(20).execute().data or []
    if not rows:
        await message.reply_text(" Acik destek talebi yok."); return
    for r in rows:
        await message.reply_text(f"Destek Talebi\n\nID: {r['id']}\nKullanici: @{r.get('username') or 'yok'}\nUser ID: {r.get('user_id')}\nMesaj:\n{r.get('message')}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(" Kapat", callback_data=f"support_close_{r['id']}")]]))


async def cancel_requests_message(message):
    rows = supabase.table("cancel_requests").select("*").eq("status", "pending").execute().data or []
    if not rows:
        await message.reply_text(" Bekleyen iptal talebi yok."); return
    for r in rows:
        kb = [[InlineKeyboardButton(" Onayla", callback_data=f"cancel_ok_{r['id']}"), InlineKeyboardButton(" Reddet", callback_data=f"cancel_no_{r['id']}")]]
        await message.reply_text(f"Iptal Talebi\n\nTalep ID: {r['id']}\nKullanici ID: {r.get('user_id')}\nKanal ID: {r.get('channel_id')}", reply_markup=InlineKeyboardMarkup(kb))


async def blacklist_message(message):
    rows = supabase.table("blacklist").select("*").eq("active", True).order("id", desc=True).execute().data or []
    if not rows:
        await message.reply_text(" Kara listede aktif kullanici yok."); return
    for b in rows:
        await message.reply_text(f" User ID: {b.get('user_id')}\nSebep: {b.get('reason') or '-'}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(" Cikar", callback_data=f"unblacklist_{b['user_id']}")]]))


async def admins_message(message):
    rows = supabase.table("admins").select("*").order("id", desc=True).execute().data or []
    await message.reply_text("\U0001f46e Adminler", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(" Admin Ekle", callback_data="admin_add_admin")]]))
    await message.reply_text(f"Owner: {OWNER_ID}")
    for a in rows:
        status = "Aktif " if a.get("active") else "Pasif "
        await message.reply_text(f"User ID: {a.get('user_id')}\nRole: {a.get('role')}\nDurum: {status}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Ac/Kapat", callback_data=f"admin_toggle_{a['user_id']}")]]))


async def logs_message(message):
    rows = supabase.table("logs").select("*").order("id", desc=True).limit(30).execute().data or []
    if not rows:
        await message.reply_text(" Henuz log yok."); return
    text = " Son Islemler\n\n"
    for l in rows:
        text += f"ID: {l['id']}\nIslem: {l.get('action')}\nActor: {l.get('actor_id')}\nTarget: {l.get('target_user_id')}\nKanal: {l.get('channel_id')}\nDetay: {l.get('details') or '-'}\nTarih: {l.get('created_at')}\n\n"
    await message.reply_text(text[:3900])


async def export_sales_csv(message):
    rows = supabase.table("sales").select("*").order("id", desc=True).execute().data or []
    output = io.StringIO()
    fieldnames = ["id", "user_id", "username", "channel_id", "package_id", "price", "coupon_code", "refund_status", "payment_payload", "created_at"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k) for k in fieldnames})
    file_data = io.BytesIO(output.getvalue().encode("utf-8"))
    file_data.name = "sales.csv"
    await message.reply_document(document=file_data, filename="sales.csv", caption="\U0001f4c4 Sat\u0131\u015f CSV")

# =========================================================
# ADMIN ACTIONS
# =========================================================

async def handle_cancel_admin(query, context):
    if not can_manage(query.from_user.id):
        await query.message.reply_text(" Yetkin yok."); return
    parts = query.data.split("_")
    action, rid = parts[1], int(parts[2])
    req = supabase.table("cancel_requests").select("*").eq("id", rid).single().execute().data
    if not req:
        await query.message.reply_text(" Talep bulunamadi."); return
    if action == "ok":
        supabase.table("cancel_requests").update({"status": "approved"}).eq("id", rid).execute()
        supabase.table("subscriptions").update({"status": "cancelled"}).eq("user_id", req["user_id"]).eq("channel_id", req["channel_id"]).execute()
        ch = await get_channel(req["channel_id"])
        if ch:
            await remove_user_from_channel(context, ch, req["user_id"])
        await log_event("cancel_approved", query.from_user.id, req["user_id"], req["channel_id"])
        await query.message.reply_text("Iptal talebi onaylandi.")
    else:
        supabase.table("cancel_requests").update({"status": "rejected"}).eq("id", rid).execute()
        await log_event("cancel_rejected", query.from_user.id, req["user_id"], req["channel_id"])
        await query.message.reply_text("Iptal talebi reddedildi.")


async def admin_cancel_subscription(message, context, sub_id):
    sub = await get_subscription(sub_id)
    if not sub:
        await message.reply_text(" Uyelik bulunamadi."); return
    ch = await get_channel(sub["channel_id"])
    supabase.table("subscriptions").update({"status": "cancelled"}).eq("id", sub_id).execute()
    if ch:
        await remove_user_from_channel(context, ch, sub["user_id"])
    await log_event("subscription_cancelled_by_admin", message.chat_id, sub["user_id"], sub["channel_id"])
    await message.reply_text(" Uyelik iptal edildi.")


async def admin_resend_link_for_subscription(message, context, sub_id):
    sub = await get_subscription(sub_id)
    if not sub:
        await message.reply_text(" Uyelik bulunamadi."); return
    ch = await get_channel(sub["channel_id"])
    link = await safe_create_and_store_link(context, sub["user_id"], sub["channel_id"], ch)
    if link:
        try:
            await context.bot.send_message(sub["user_id"], f" Yeni VIP giris linkin:\n{link}")
            await message.reply_text(" Yeni link kullaniciya gonderildi.")
        except Exception:
            await message.reply_text(f" Link uretildi ama gonderilemedi. Manuel gonder:\n{link}")
    else:
        await message.reply_text(" Link uretilemedi.")


async def admin_extend_subscription_simple(sub_id, days):
    sub = await get_subscription(sub_id)
    if not sub:
        return False
    old_end = parse_dt(sub.get("end_date")) or now_utc()
    base = old_end if old_end > now_utc() else now_utc()
    new_end = base + timedelta(days=days)
    supabase.table("subscriptions").update({"end_date": new_end.isoformat(), "warn_3d_sent": False, "warn_1d_sent": False}).eq("id", sub_id).execute()
    return True


async def admin_extend_subscription(message, sub_id, days):
    ok = await admin_extend_subscription_simple(sub_id, days)
    await message.reply_text(f" Uyelik {days} gun uzatildi." if ok else " Uyelik bulunamadi.")


async def mark_refund(message, admin_id, sale_id):
    sale = supabase.table("sales").select("*").eq("id", sale_id).single().execute().data
    if not sale:
        await message.reply_text(" Satis bulunamadi."); return
    supabase.table("sales").update({"refund_status": "refunded", "refunded_at": now_utc().isoformat(), "refunded_by": admin_id}).eq("id", sale_id).execute()
    await log_event("refund_marked", admin_id, sale.get("user_id"), sale.get("channel_id"), f"sale_id={sale_id}")
    await message.reply_text(" Satis iade edildi olarak isaretlendi. Not: Bu sadece sistem ici isarettir; Telegram Stars iadesini otomatik yapmaz.")


async def resend_invite_link(query, context):
    sub_id = int(query.data.split("_")[1])
    sub = await get_subscription(sub_id)
    if not sub or int(sub.get("user_id")) != query.from_user.id or sub.get("status") != "active":
        await query.message.reply_text(" Aktif uyelik bulunamadi."); return
    ch = await get_channel(sub["channel_id"])
    link = await safe_create_and_store_link(context, sub["user_id"], sub["channel_id"], ch)
    await query.message.reply_text(f" Yeni tek kullanimlik linkin:\n{link}" if link else " Link uretilemedi. Admin ile iletisime gec.")


async def broadcast_message(message, context, text):
    rows = supabase.table("users").select("*").execute().data or []
    sent = failed = 0
    await message.reply_text(f" Duyuru basladi. Kullanici sayisi: {len(rows)}")
    for u in rows:
        try:
            if not await is_blacklisted(u["user_id"]):
                await context.bot.send_message(u["user_id"], text)
                sent += 1
            await asyncio.sleep(BROADCAST_DELAY_SECONDS)
        except Exception:
            failed += 1
    await log_event("broadcast_sent", message.chat_id, details=f"sent={sent}, failed={failed}")
    await message.reply_text(f" Duyuru bitti. Gonderildi: {sent}, Hata: {failed}")

# =========================================================
# AD MARKETPLACE / BALANCE SYSTEM
# =========================================================


def get_channel_ad_price(ch):
    """Return per-channel ad price. Falls back to default setting."""
    try:
        value = ch.get("ad_price")
        if value is not None:
            price = int(value)
            if price > 0:
                return price
    except Exception:
        pass
    return safe_int(get_setting("ad_default_single_price", "1000"), 1000)

async def get_ad_balance(user_id):
    try:
        row = supabase.table("ad_balances").select("*").eq("user_id", int(user_id)).execute().data
        if row:
            return int(row[0].get("balance") or 0)
        supabase.table("ad_balances").insert({"user_id": int(user_id), "balance": 0, "spent": 0}).execute()
    except Exception as e:
        logger.warning("ad balance read failed: %s", e)
    return 0


async def change_ad_balance(user_id, amount, tx_type, description, order_id=None):
    user_id = int(user_id)
    amount = int(amount)
    current = await get_ad_balance(user_id)
    new_balance = current + amount
    if new_balance < 0:
        return False
    try:
        row = supabase.table("ad_balances").select("*").eq("user_id", user_id).execute().data
        if row:
            spent = int(row[0].get("spent") or 0)
            if amount < 0:
                spent += abs(amount)
            supabase.table("ad_balances").update({"balance": new_balance, "spent": spent, "updated_at": now_utc().isoformat()}).eq("user_id", user_id).execute()
        else:
            supabase.table("ad_balances").insert({"user_id": user_id, "balance": new_balance, "spent": abs(amount) if amount < 0 else 0}).execute()
        supabase.table("ad_transactions").insert({"user_id": user_id, "amount": amount, "type": tx_type, "description": description, "order_id": order_id}).execute()
        return True
    except Exception as e:
        logger.error("ad balance update failed: %s", e)
        return False


async def ensure_default_ad_packages():
    try:
        rows = supabase.table("ad_packages").select("*").execute().data or []
        if rows:
            return
        supabase.table("ad_packages").insert([
            {"name": "Tek Kanal Reklami", "price": safe_int(get_setting("ad_default_single_price", "1000"), 1000), "target_type": "single", "channel_id": None, "description": "Adminin sectigi tek aktif VIP kanalda reklam", "active": True},
            {"name": "Tum Kanallar Reklami", "price": safe_int(get_setting("ad_default_all_price", "3000"), 3000), "target_type": "all", "channel_id": None, "description": "Tum aktif VIP kanallarda reklam", "active": True},
        ]).execute()
    except Exception as e:
        logger.warning("default ad packages failed: %s", e)


async def show_balance_center(message, user_id):
    balance = await get_ad_balance(user_id)
    rows = supabase.table("ad_balances").select("*").eq("user_id", int(user_id)).execute().data or []
    spent = int(rows[0].get("spent") or 0) if rows else 0
    orders = supabase.table("ad_orders").select("*").eq("user_id", int(user_id)).execute().data or []
    pending = len([o for o in orders if o.get("status") == "pending"])
    published = len([o for o in orders if o.get("status") == "published"])
    rejected = len([o for o in orders if str(o.get("status") or "").startswith("rejected")])

    kb = [
        [InlineKeyboardButton("\u2b50 Bakiye Ekle", callback_data="ad_topup_custom")],
        [InlineKeyboardButton("\U0001f4e3 Kanallara Reklam Ver", callback_data="ad_show_packages")],
        [InlineKeyboardButton("\U0001f4c4 Reklamlar\u0131m", callback_data="ad_my_orders")],
        [InlineKeyboardButton("\U0001f9fe Bakiye Hareketleri", callback_data="ad_transactions")],
    ]

    await message.reply_text(
        f"\U0001f4b0 Bakiye Merkezi\n\n"
        f"Mevcut bakiye: {balance} Stars\n"
        f"Toplam harcanan: {spent} Stars\n\n"
        f"Bekleyen reklam: {pending}\n"
        f"Yay\u0131nlanan reklam: {published}\n"
        f"Reddedilen/iade edilen reklam: {rejected}\n\n"
        f"Ne yapmak istiyorsun?",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def show_ad_balance(message, user_id):
    await show_balance_center(message, user_id)


async def ask_custom_topup_amount(message, context):
    context.user_data.clear()
    context.user_data["mode"] = "ad_topup_amount"
    await message.reply_text(
        "\u2b50 Bakiye Ekle\n\n"
        "Y\u00fcklemek istedi\u011fin Stars miktar\u0131n\u0131 yaz.\n\n"
        "\u00d6rnek:\n"
        "2500\n\n"
        "Minimum: 50 Stars\n"
        "Maksimum: 100000 Stars"
    )


async def show_topup_options(message):
    await message.reply_text(
        "\u2b50 Bakiye Ekle\n\n"
        "Art\u0131k sabit tutar butonu yok. Bakiye Merkezi > Bakiye Ekle ile istedi\u011fin tutar\u0131 yazabilirsin.\n"
        "\u00d6rnek: 2500"
    )


async def send_custom_topup_invoice(message, context, amount):
    await context.bot.send_invoice(
        chat_id=message.chat_id,
        title="Reklam Bakiyesi",
        description=f"{amount} Stars reklam bakiyesi y\u00fckleme",
        payload=f"topup_{amount}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Reklam Bakiyesi", amount=amount)],
    )


async def handle_topup(query, context):
    try:
        amount = int(query.data.split("_")[1])
    except Exception:
        await query.message.reply_text("Ge\u00e7ersiz tutar.")
        return
    if amount < 50 or amount > 100000:
        await query.message.reply_text("Ge\u00e7ersiz tutar. 50 ile 100000 Stars aras\u0131 olmal\u0131.")
        return
    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title="Reklam Bakiyesi",
        description=f"{amount} Stars reklam bakiyesi y\u00fckleme",
        payload=f"topup_{amount}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Reklam Bakiyesi", amount=amount)],
    )


async def show_ad_transactions(message, user_id):
    rows = supabase.table("ad_transactions").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute().data or []
    if not rows:
        await message.reply_text("Hen\u00fcz bakiye hareketi yok.")
        return
    text = "\U0001f9fe Son Bakiye Hareketleri\n\n"
    for r in rows:
        sign = "+" if int(r.get("amount") or 0) > 0 else ""
        text += f"{sign}{r.get('amount')} Stars | {r.get('type')}\n{r.get('description') or '-'}\n{r.get('created_at')}\n\n"
    await message.reply_text(text[:3900])



async def show_ad_channels_user(message, user_id):
    rows = supabase.table("channels").select("*").eq("active", True).order("id").execute().data or []
    if not rows:
        await message.reply_text("Su anda reklam verilebilecek aktif kanal yok.")
        return

    balance = await get_ad_balance(user_id)
    await message.reply_text(
        f"\U0001f4e3 Kanallara Reklam Ver\n\n"
        f"Bakiyen: {balance} Stars\n\n"
        f"Reklam vermek istedigin kanali sec.\n"
        f"Bakiyen yeterliyse reklam formu acilir, yetmezse once bakiye yuklemen istenir."
    )

    for ch in rows:
        price = get_channel_ad_price(ch)
        chat_id = ch.get("chat_id") or "-"
        desc = ch.get("description") or "-"
        can_buy = balance >= price
        button_text = "Bu kanala reklam ver" if can_buy else "Bakiye yetersiz"
        await message.reply_text(
            f"\U0001f4e2 {ch.get('name')}\n"
            f"Reklam fiyati: {price} Stars\n"
            f"Chat ID: {chat_id}\n"
            f"Aciklama: {desc}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(button_text, callback_data=f"adch_{ch['id']}")]])
        )


async def show_ad_packages_user(message, user_id):
    # Backward-compatible name. New flow has no ad packages; user selects channel directly.
    await show_ad_channels_user(message, user_id)


async def start_ad_order_channel(query, context):
    channel_id = int(query.data.split("_")[1])
    ch = await get_channel(channel_id)

    if not ch or not ch.get("active"):
        await query.message.reply_text("Kanal bulunamadi veya pasif.")
        return

    price = get_channel_ad_price(ch)
    balance = await get_ad_balance(query.from_user.id)

    if balance < price and not (test_mode_on() and is_admin(query.from_user.id)):
        await query.message.reply_text(
            f"Bakiyen yetersiz.\n\n"
            f"Bu kanal reklam fiyati: {price} Stars\n"
            f"Bakiyen: {balance} Stars\n\n"
            f"Once Bakiye > Bakiye Ekle kismindan bakiye yukle."
        )
        return

    context.user_data.clear()
    context.user_data["ad_channel_id"] = channel_id
    context.user_data["ad_price"] = price
    context.user_data["ad_channel_name"] = ch.get("name") or f"Kanal ID {channel_id}"

    kb = [
        [InlineKeyboardButton("\u26a1 Tek Mesajla Reklam", callback_data="ad_method_single")],
        [InlineKeyboardButton("\u2728 Haz\u0131r Reklam Olu\u015ftur", callback_data="ad_method_template")],
        [InlineKeyboardButton("\u270d\ufe0f Ad\u0131m Ad\u0131m Olu\u015ftur", callback_data="ad_method_step")],
        [InlineKeyboardButton("\u274c \u0130ptal", callback_data="ad_cancel")],
    ]

    await query.message.reply_text(
        f"Reklam kanalÄ± seÃ§ildi: {ch.get('name')}\n"
        f"Fiyat: {price} Stars\n\n"
        "NasÄ±l reklam oluÅturmak istiyorsun?",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def start_ad_order(query, context):
    # Old package callback support. New UI does not use packages.
    await query.message.reply_text("Reklam paketi sistemi kapatildi. Bakiye > Kanallara Reklam Ver kismindan kanal sec.")


async def preview_ad_order(message, context):
    channel_id = context.user_data.get("ad_channel_id")
    price = int(context.user_data.get("ad_price") or 0)
    channel_name = context.user_data.get("ad_channel_name") or "Secilen kanal"

    if not channel_id:
        context.user_data.clear()
        await message.reply_text("Reklam kanali bulunamadi. Islem iptal edildi.")
        return

    ch = await get_channel(channel_id)
    if not ch or not ch.get("active"):
        context.user_data.clear()
        await message.reply_text("Secilen kanal bulunamadi veya pasif. Islem iptal edildi.")
        return

    if price <= 0:
        price = get_channel_ad_price(ch)
        context.user_data["ad_price"] = price

    title = context.user_data.get("ad_title")
    ad_text = context.user_data.get("ad_text")
    link = context.user_data.get("ad_link")
    image_line = "Var" if context.user_data.get("ad_image_file_id") else "Yok"

    kb = [[
        InlineKeyboardButton("Onaya Gonder", callback_data="ad_submit"),
        InlineKeyboardButton("Iptal", callback_data="ad_cancel"),
    ]]

    await message.reply_text(
        f"\U0001f4e3 Reklam Onizleme\n\n"
        f"Kanal: {channel_name}\n"
        f"Fiyat: {price} Stars\n"
        f"Gorsel: {image_line}\n\n"
        f"Baslik: {title}\n\n"
        f"Metin:\n{ad_text}\n\n"
        f"Link: {link}\n\n"
        f"Onaya gonderirsen bakiye hemen duser. Admin reddederse iade edilir.",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    context.user_data["mode"] = "ad_preview"


async def submit_ad_order(query, context):
    if context.user_data.get("mode") != "ad_preview":
        await query.message.reply_text("Aktif reklam onizlemesi yok.")
        return

    channel_id = context.user_data.get("ad_channel_id")
    ch = await get_channel(channel_id) if channel_id else None

    if not ch or not ch.get("active"):
        context.user_data.clear()
        await query.message.reply_text("Secilen kanal bulunamadi veya pasif.")
        return

    price = int(context.user_data.get("ad_price") or get_channel_ad_price(ch))
    test_order = test_mode_on() and is_admin(query.from_user.id)
    balance = await get_ad_balance(query.from_user.id)

    if balance < price and not test_order:
        context.user_data.clear()
        await query.message.reply_text(
            f"Bakiyen yetersiz. Islem iptal edildi.\n\n"
            f"Gerekli: {price} Stars\n"
            f"Bakiyen: {balance} Stars"
        )
        return

    if not test_order:
        ok = await change_ad_balance(
            query.from_user.id,
            -price,
            "ad_hold",
            f"Reklam talebi icin bakiye dusuldu: {ch.get('name')}",
        )
        if not ok:
            context.user_data.clear()
            await query.message.reply_text("Bakiye dusulemedi. Islem iptal edildi.")
            return
    else:
        price = 0

    order = {
        "user_id": query.from_user.id,
        "username": safe_username(query.from_user),
        "package_id": None,
        "channel_id": int(channel_id),
        "target_type": "single",
        "title": context.user_data.get("ad_title"),
        "ad_text": context.user_data.get("ad_text"),
        "link": context.user_data.get("ad_link"),
        "image_file_id": context.user_data.get("ad_image_file_id"),
        "status": "pending",
        "price": price,
    }

    res = supabase.table("ad_orders").insert(order).execute()
    order_id = res.data[0]["id"] if res.data else None

    await log_event(
        "ad_order_created",
        query.from_user.id,
        query.from_user.id,
        channel_id=int(channel_id),
        details=f"order_id={order_id}, price={price}",
    )

    context.user_data.clear()

    await query.message.reply_text(
        f"Reklam talebin admin onayina gonderildi.\n\n"
        f"Kanal: {ch.get('name')}\n"
        f"Kesilen bakiye: {price} Stars\n"
        f"Kalan bakiye: {await get_ad_balance(query.from_user.id)} Stars"
        + ("\n\nTest modu aktif: admin reklamindan bakiye dusulmedi." if test_order else "")
    )

    try:
        await context.bot.send_message(
            OWNER_ID,
            f"Yeni reklam talebi\n\n"
            f"Order ID: {order_id}\n"
            f"Kullanici: @{safe_username(query.from_user) or 'yok'}\n"
            f"Kanal: {ch.get('name')}\n"
            f"Fiyat: {price} Stars\n"
            f"Baslik: {order['title']}"
        )
    except Exception:
        pass


async def my_ad_orders(message, user_id):
    rows = supabase.table("ad_orders").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute().data or []
    if not rows:
        await message.reply_text("Henuz reklam talebin yok.")
        return

    for o in rows:
        views = o.get("views_count")
        if views is None:
            views = 0
        clicks = safe_int(o.get("clicks_count"), 0)
        links = o.get("published_links") or ""

        ch_name = "-"
        if o.get("channel_id"):
            ch = await get_channel(o.get("channel_id"))
            ch_name = (ch or {}).get("name") or f"Kanal ID {o.get('channel_id')}"

        msg = (
            f"\U0001f4c4 Reklam #{o['id']}\n\n"
            f"Kanal: {ch_name}\n"
            f"Durum: {o.get('status')}\n"
            f"Fiyat: {o.get('price')} Stars\n"
            f"Baslik: {o.get('title')}\n"
            f"Goruntulenme: {views}\n"
            f"Tiklama: {clicks}\n"
        )

        if links:
            msg += f"\nYayin linkleri:\n{links[:1200]}"
        else:
            msg += "\nYayin linki henuz yok."

        await message.reply_text(msg[:3900])

async def ad_orders_admin_message(message):
    rows = supabase.table("ad_orders").select("*").eq("status", "pending").order("id", desc=True).limit(20).execute().data or []
    if not rows:
        await message.reply_text("Bekleyen reklam talebi yok.")
        return

    for o in rows:
        ch = None
        if o.get("channel_id"):
            ch = await get_channel(o.get("channel_id"))

        kb = [
            [
                InlineKeyboardButton("Onayla ve Yayinla", callback_data=f"ad_approve_{o['id']}"),
                InlineKeyboardButton("Reddet ve Iade", callback_data=f"ad_reject_{o['id']}"),
            ],
            [
                InlineKeyboardButton("Uygunsuz", callback_data=f"ad_reject_reason_content_{o['id']}"),
                InlineKeyboardButton("Link Hatali", callback_data=f"ad_reject_reason_link_{o['id']}"),
            ],
            [
                InlineKeyboardButton("Eksik Bilgi", callback_data=f"ad_reject_reason_missing_{o['id']}"),
                InlineKeyboardButton("Kurallara Aykiri", callback_data=f"ad_reject_reason_rules_{o['id']}"),
            ],
            [InlineKeyboardButton("Goruntulenme Gir", callback_data=f"ad_views_{o['id']}")],
        ]

        image_line = "Var" if o.get("image_file_id") else "Yok"
        channel_line = (ch or {}).get("name") or f"Kanal ID {o.get('channel_id') or '-'}"

        await message.reply_text(
            f"\U0001f4e3 Reklam Talebi #{o['id']}\n\n"
            f"Kullanici: @{o.get('username') or 'yok'}\n"
            f"User ID: {o.get('user_id')}\n"
            f"Kanal: {channel_line}\n"
            f"Fiyat: {o.get('price')} Stars\n"
            f"Gorsel: {image_line}\n\n"
            f"Baslik: {o.get('title')}\n\n"
            f"Metin:\n{o.get('ad_text')}\n\n"
            f"Link: {o.get('link')}",
            reply_markup=InlineKeyboardMarkup(kb),
        )

async def ad_packages_admin_message(message):
    await ensure_default_ad_packages()
    rows = supabase.table("ad_packages").select("*").order("id").execute().data or []
    if not rows:
        await message.reply_text("Reklam paketi yok.")
        return
    for p in rows:
        status = "Aktif" if p.get("active") else "Pasif"
        target = "Tum kanallar" if p.get("target_type") == "all" else f"Tek kanal / channel_id={p.get('channel_id') or 'ilk aktif kanal'}"
        kb = [
            [InlineKeyboardButton("Fiyat", callback_data=f"adpkg_price_{p['id']}"), InlineKeyboardButton("Aciklama", callback_data=f"adpkg_desc_{p['id']}")],
            [InlineKeyboardButton("Hedef", callback_data=f"adpkg_target_{p['id']}"), InlineKeyboardButton("Ac/Kapat", callback_data=f"adpkg_toggle_{p['id']}")],
            [InlineKeyboardButton("Sil", callback_data=f"adpkg_delete_{p['id']}")],
        ]
        await message.reply_text(
            f"Paket ID: {p['id']}\n"
            f"Ad: {p.get('name')}\n"
            f"Fiyat: {p.get('price')} Stars\n"
            f"Hedef: {target}\n"
            f"Durum: {status}\n"
            f"Aciklama: {p.get('description') or '-'}",
            reply_markup=InlineKeyboardMarkup(kb),
        )


async def ad_channel_prices_admin_message(message):
    rows = supabase.table("channels").select("*").eq("active", True).order("id").execute().data or []
    if not rows:
        await message.reply_text("Aktif kanal yok. Once VIP kanal eklemelisin.")
        return

    await message.reply_text("ð£ Kanal Reklam Fiyatlari\n\nKullanicilar reklam verirken paket secmez; direkt kanal secer.")

    for ch in rows:
        price = get_channel_ad_price(ch)
        await message.reply_text(
            f"Kanal ID: {ch.get('id')}\n"
            f"Ad: {ch.get('name')}\n"
            f"Reklam fiyati: {price} Stars\n"
            f"Chat ID: {ch.get('chat_id') or '-'}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Fiyat Degistir", callback_data=f"adchprice_{ch['id']}")]])
        )

async def ad_balances_admin_message(message):
    rows = supabase.table("ad_balances").select("*").order("balance", desc=True).limit(20).execute().data or []
    if not rows:
        await message.reply_text(" Bakiye kaydi yok.")
        return
    text = "\U0001f4b0 Reklam Bakiyeleri\n\n"
    for r in rows:
        text += f"User ID: {r.get('user_id')} | Bakiye: {r.get('balance')} | Harcanan: {r.get('spent') or 0}\n"
    await message.reply_text(text[:3900])


async def toggle_ad_package(message, package_id, admin_id):
    row = supabase.table("ad_packages").select("*").eq("id", package_id).single().execute().data
    if not row:
        await message.reply_text(" Paket bulunamadi.")
        return
    supabase.table("ad_packages").update({"active": not bool(row.get("active"))}).eq("id", package_id).execute()
    await log_event("ad_package_toggled", admin_id, details=f"package_id={package_id}")
    await message.reply_text(" Reklam paketi durumu degistirildi.")


def build_ad_message(order):
    return f"\U0001f4e3 Sponsorlu Reklam\n\n{order.get('title')}\n\n{order.get('ad_text')}"



def build_private_message_link(chat_id, message_id):
    raw = str(chat_id)
    if raw.startswith("-100"):
        return f"https://t.me/c/{raw[4:]}/{message_id}"
    return ""


async def get_bot_username(context):
    try:
        me = await context.bot.get_me()
        return me.username
    except Exception:
        return None



async def publish_ad_to_targets(context, order, package=None):
    channels = []

    # New flow: user selected a concrete channel. No ad package is used.
    if order.get("channel_id"):
        ch = await get_channel(order.get("channel_id"))
        if ch:
            channels = [ch]

    # Backward compatibility for old orders created with packages.
    elif package:
        if package.get("target_type") == "all":
            channels = supabase.table("channels").select("*").eq("active", True).execute().data or []
        else:
            cid = package.get("channel_id")
            if cid:
                ch = await get_channel(cid)
                if ch:
                    channels = [ch]
            else:
                rows = supabase.table("channels").select("*").eq("active", True).order("id").limit(1).execute().data or []
                channels = rows

    sent = []
    errors = []
    links = []
    total_views = 0

    bot_username = await get_bot_username(context)
    target_url = order.get("link")

    if bot_username and order.get("id"):
        button_url = f"https://t.me/{bot_username}?start=ad_{order['id']}"
    else:
        button_url = target_url

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Incele", url=button_url)]])

    for ch in channels:
        chat_id = ch.get("chat_id")
        if not chat_id:
            errors.append(f"{ch.get('name')}: chat_id yok")
            continue

        try:
            if order.get("image_file_id"):
                msg = await context.bot.send_photo(
                    chat_id=int(chat_id),
                    photo=order.get("image_file_id"),
                    caption=build_ad_message(order),
                    reply_markup=kb,
                )
            else:
                msg = await context.bot.send_message(
                    chat_id=int(chat_id),
                    text=build_ad_message(order),
                    reply_markup=kb,
                    disable_web_page_preview=False,
                )

            sent.append(f"{chat_id}:{msg.message_id}")
            link = build_private_message_link(chat_id, msg.message_id)
            if link:
                links.append(link)
            total_views += safe_int(getattr(msg, "views", 0), 0)

        except Exception as e:
            errors.append(f"{chat_id}:{e}")

    return sent, errors, links, total_views


async def approve_and_publish_ad(message, context, order_id, admin_id):
    order = supabase.table("ad_orders").select("*").eq("id", order_id).single().execute().data
    if not order:
        await message.reply_text("Reklam talebi bulunamadi.")
        return

    if order.get("status") != "pending":
        await message.reply_text(f"Bu reklam artik pending degil. Durum: {order.get('status')}")
        return

    package = None
    if not order.get("channel_id") and order.get("package_id"):
        try:
            package = supabase.table("ad_packages").select("*").eq("id", order.get("package_id")).single().execute().data
        except Exception:
            package = None

    if not order.get("channel_id") and not package:
        await reject_and_refund_ad(message, order_id, admin_id, reason="Kanal bulunamadi")
        return

    sent, errors, links, total_views = await publish_ad_to_targets(context, order, package)

    if sent:
        update_data = {
            "status": "published",
            "published_message_ids": ",".join(sent),
            "published_links": "\n".join(links),
            "published_chat_count": len(sent),
            "views_count": total_views,
            "published_at": now_utc().isoformat(),
        }
        supabase.table("ad_orders").update(update_data).eq("id", order_id).execute()

        await log_event(
            "ad_published",
            admin_id,
            order.get("user_id"),
            channel_id=order.get("channel_id"),
            details=f"order_id={order_id}, sent={len(sent)}, errors={len(errors)}",
        )

        await message.reply_text(f"Reklam yayinlandi. Gonderilen kanal/grup: {len(sent)}")

        links_text = "\n".join(links) if links else "Link olusmadi ama reklam gonderildi."
        try:
            await context.bot.send_message(
                order.get("user_id"),
                f"Reklamin onaylandi ve yayinlandi.\n\n"
                f"Reklam ID: {order_id}\n"
                f"Gonderilen kanal/grup: {len(sent)}\n\n"
                f"Yayin linkleri:\n{links_text[:1500]}"
            )
        except Exception:
            pass
    else:
        await change_ad_balance(
            order.get("user_id"),
            int(order.get("price") or 0),
            "ad_auto_refund",
            "Reklam yayinlanamadi, otomatik iade",
            order_id,
        )
        supabase.table("ad_orders").update({"status": "failed_refunded", "reject_reason": "; ".join(errors)[:900]}).eq("id", order_id).execute()
        await log_event("ad_publish_failed_refunded", admin_id, order.get("user_id"), channel_id=order.get("channel_id"), details=f"order_id={order_id}")
        await message.reply_text("Reklam yayinlanamadi. Bakiye otomatik iade edildi. Botun kanalda admin ve mesaj gonderme yetkisi oldugunu kontrol et.")

async def reject_and_refund_ad(message, order_id, admin_id, reason="Admin reddetti"):
    order = supabase.table("ad_orders").select("*").eq("id", order_id).single().execute().data
    if not order:
        await message.reply_text(" Reklam talebi bulunamadi.")
        return
    if order.get("status") != "pending":
        await message.reply_text(f" Bu reklam artik pending degil. Durum: {order.get('status')}")
        return
    await change_ad_balance(order.get("user_id"), int(order.get("price") or 0), "ad_refund", reason, order_id)
    supabase.table("ad_orders").update({"status": "rejected_refunded", "reject_reason": reason}).eq("id", order_id).execute()
    await log_event("ad_rejected_refunded", admin_id, order.get("user_id"), details=f"order_id={order_id}")
    await message.reply_text(" Reklam reddedildi ve bakiye iade edildi.")


async def delete_ad_package(message, package_id, admin_id):
    row = supabase.table("ad_packages").select("*").eq("id", package_id).execute().data
    if not row:
        await message.reply_text("Paket bulunamadi.")
        return
    supabase.table("ad_packages").delete().eq("id", package_id).execute()
    await log_event("ad_package_deleted", admin_id, details=f"package_id={package_id}")
    await message.reply_text("Reklam paketi silindi.")


async def ad_stats_admin_message(message):
    rows = supabase.table("ad_orders").select("*").execute().data or []
    today = now_utc().date().isoformat()
    month = now_utc().strftime("%Y-%m")
    total = len(rows)
    pending = len([r for r in rows if r.get("status") == "pending"])
    published = len([r for r in rows if r.get("status") == "published"])
    rejected = len([r for r in rows if "reject" in str(r.get("status"))])
    failed = len([r for r in rows if "failed" in str(r.get("status"))])
    revenue_today = 0
    revenue_month = 0
    total_revenue = 0
    total_views = 0
    total_clicks = 0
    for r in rows:
        if r.get("status") == "published":
            price = safe_int(r.get("price"), 0)
            created = str(r.get("created_at") or "")
            total_revenue += price
            if created.startswith(today):
                revenue_today += price
            if created.startswith(month):
                revenue_month += price
        total_views += safe_int(r.get("views_count"), 0)
        total_clicks += safe_int(r.get("clicks_count"), 0)
    await message.reply_text(
        "\U0001f4ca Reklam Istatistikleri\n\n"
        f"Toplam talep: {total}\n"
        f"Bekleyen: {pending}\n"
        f"Yayinlanan: {published}\n"
        f"Reddedilen: {rejected}\n"
        f"Basarisiz: {failed}\n\n"
        f"Bugun reklam geliri: {revenue_today} Stars\n"
        f"Bu ay reklam geliri: {revenue_month} Stars\n"
        f"Toplam reklam geliri: {total_revenue} Stars\n\n"
        f"Kayitli goruntulenme: {total_views}\n"
        f"Bot uzerinden tiklama: {total_clicks}"
    )


async def system_test_message(message, context):
    checks = []
    def ok(name): checks.append(f"â {name}")
    def bad(name, err): checks.append(f"â {name}: {str(err)[:120]}")
    for table in ["users", "channels", "ad_balances", "ad_orders", "ad_transactions", "settings"]:
        try:
            supabase.table(table).select("*").limit(1).execute()
            ok(f"{table} tablosu")
        except Exception as e:
            bad(f"{table} tablosu", e)
    try:
        me = await context.bot.get_me()
        ok(f"Bot baglantisi @{me.username}")
    except Exception as e:
        bad("Bot baglantisi", e)
    try:
        ch = await get_first_active_channel()
        if not ch:
            checks.append("â ï¸ Aktif kanal yok; reklam ve VIP link testi atlandi.")
        else:
            me = await context.bot.get_me()
            member = await context.bot.get_chat_member(int(ch["chat_id"]), me.id)
            ok(f"Bot kanal/grupta gorunuyor: {member.status}")
    except Exception as e:
        bad("Bot kanal admin/yetki kontrolu", e)
    await message.reply_text("\U0001f9ea Sistem Testi\n\n" + "\n".join(checks)[:3500])


async def handle_ad_click_start(update, context, raw_arg):
    raw = raw_arg.replace("ad_", "")
    if not raw.isdigit():
        return False
    order_id = int(raw)
    order = supabase.table("ad_orders").select("*").eq("id", order_id).execute().data
    if not order:
        await update.message.reply_text("Reklam bulunamadi veya kaldirilmis.")
        return True
    order = order[0]
    current = safe_int(order.get("clicks_count"), 0) + 1
    try:
        supabase.table("ad_orders").update({"clicks_count": current}).eq("id", order_id).execute()
        supabase.table("ad_clicks").insert({"order_id": order_id, "user_id": update.effective_user.id}).execute()
    except Exception:
        pass
    link = order.get("link")
    await update.message.reply_text(
        f"\U0001f4e3 Reklam\n\n{order.get('title') or ''}\n\nDevam etmek icin butona bas.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Reklam Linkine Git", url=link)]]) if link else None,
    )
    return True


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    if mode != "ad_image":
        await update.message.reply_text("Foto alindi ama aktif bir reklam islemi yok. Reklam icin Bakiye > Kanallara Reklam Ver akisini kullan.")
        return
    if not update.message.photo:
        await update.message.reply_text("Foto bulunamadi. Tekrar gonder veya skip yaz.")
        return
    context.user_data["ad_image_file_id"] = update.message.photo[-1].file_id
    await preview_ad_order(update.message, context)

# =========================================================
# JOBS
# =========================================================

async def expire_old_subscriptions_job(context: ContextTypes.DEFAULT_TYPE):
    await expire_old_subscriptions(context)


async def expire_old_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    rows = supabase.table("subscriptions").select("*").eq("status", "active").execute().data or []
    current = now_utc()
    for sub in rows:
        end = parse_dt(sub.get("end_date"))
        if end and end < current:
            ch = await get_channel(sub["channel_id"])
            if ch:
                await remove_user_from_channel(context, ch, sub["user_id"])
            supabase.table("subscriptions").update({"status": "expired"}).eq("id", sub["id"]).execute()
            supabase.table("users").update({"active_coupon": "WINBACK20"}).eq("user_id", sub["user_id"]).execute()
            await log_event("subscription_expired", None, sub["user_id"], sub["channel_id"])
            try:
                await context.bot.send_message(sub["user_id"], " VIP uyelik suren bitti. 48 saat icinde yenilersen WINBACK20 kuponuyla %20 indirim alirsin.")
            except Exception:
                pass


async def warning_job(context: ContextTypes.DEFAULT_TYPE):
    rows = supabase.table("subscriptions").select("*").eq("status", "active").execute().data or []
    current = now_utc()
    for sub in rows:
        end = parse_dt(sub.get("end_date"))
        if not end:
            continue
        remaining = end - current
        ch = await get_channel(sub["channel_id"])
        name = ch.get("name") if ch else f"Kanal ID {sub['channel_id']}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(" Uyeligi Uzat", callback_data=f"buyc_{sub['channel_id']}")]])
        if remaining <= timedelta(days=1) and not sub.get("warn_1d_sent"):
            try:
                await context.bot.send_message(sub["user_id"], f" VIP uyeligin 1 gun icinde bitiyor.\n\n Kanal: {name}\nSimdi yenilersen erken yenileme bonusu kazanirsin.", reply_markup=kb)
                supabase.table("subscriptions").update({"warn_1d_sent": True}).eq("id", sub["id"]).execute()
            except Exception:
                pass
        elif remaining <= timedelta(days=3) and not sub.get("warn_3d_sent"):
            try:
                await context.bot.send_message(sub["user_id"], f" VIP uyeligin 3 gun icinde bitiyor.\n\n Kanal: {name}\nSimdi yenilersen erken yenileme bonusu kazanirsin.", reply_markup=kb)
                supabase.table("subscriptions").update({"warn_3d_sent": True}).eq("id", sub["id"]).execute()
            except Exception:
                pass


async def abandoned_checkout_job(context: ContextTypes.DEFAULT_TYPE):
    rows = supabase.table("checkout_intents").select("*").eq("status", "started").eq("reminder_sent", False).execute().data or []
    current = now_utc()
    for row in rows:
        created = parse_dt(row.get("created_at"))
        if not created or current - created < timedelta(hours=ABANDONED_REMINDER_HOURS):
            continue
        callback = f"buyc_{row['item_id']}" if row.get("item_type") == "channel" else f"buyp_{row['item_id']}"
        try:
            await context.bot.send_message(row["user_id"], " Odemeyi baslatmistin ama tamamlanmamis gorunuyor. Devam etmek istersen asagidaki butona basabilirsin.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(" Odemeye Devam Et", callback_data=callback)]]))
            supabase.table("checkout_intents").update({"reminder_sent": True}).eq("id", row["id"]).execute()
        except Exception:
            pass


async def daily_report_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_message(OWNER_ID, f" Gunluk Rapor\n\n{await admin_dashboard_text()}")
    except Exception:
        pass



async def weekly_giveaway_job(context: ContextTypes.DEFAULT_TYPE):
    if now_utc().weekday() != 0:  # Monday
        return
    week = previous_week_key()

    already = []
    for table_name in ["giveaway_winners", "raffle_winners"]:
        try:
            already = supabase.table(table_name).select("*").eq("week_key", week).execute().data or []
            if already:
                break
        except Exception:
            pass
    if already:
        return

    class DummyMsg:
        async def reply_text(self, text, **kwargs):
            try:
                await context.bot.send_message(OWNER_ID, text)
            except Exception:
                pass

    await run_giveaway(DummyMsg(), context, week, manual=False)

# =========================================================
# APP
# =========================================================

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.TEXT, channel_id_reader))
app.add_handler(CallbackQueryHandler(button_router))
app.add_handler(PreCheckoutQueryHandler(precheckout))
app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))
app.job_queue.run_repeating(expire_old_subscriptions_job, interval=3600, first=30)
app.job_queue.run_repeating(warning_job, interval=21600, first=60)
app.job_queue.run_repeating(abandoned_checkout_job, interval=1800, first=300)
app.job_queue.run_repeating(daily_report_job, interval=86400, first=120)
print("Pasha VIP sade sistem calisiyor...")
app.run_polling()
