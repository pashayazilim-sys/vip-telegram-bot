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
- Groq/OpenAI AI: ad variations, support pre-answer, daily summary
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

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OWNER_ID = int(os.getenv("OWNER_ID", "957422314"))

AI_PROVIDER = (os.getenv("AI_PROVIDER") or "").lower().strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AI_MODEL = os.getenv("AI_MODEL") or os.getenv("OPENAI_MODEL") or "llama-3.1-8b-instant"
if not AI_PROVIDER:
    AI_PROVIDER = "groq" if GROQ_API_KEY else ("openai" if OPENAI_API_KEY else "")

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
        ["ð HÄ±zlÄ± BaÅla", "ð Durumum"],
        ["ð¢ VIP Kanallar"],
        ["ð° Bakiye", "ð£ Reklam Ver"],
        ["ð ÃyeliÄim", "ð GeÃ§miÅim"],
        ["ð Referans"],
        ["â SSS"],
        ["ð Destek", "â¹ï¸ YardÄ±m"],
    ],
    resize_keyboard=True,
)

ADMIN_MENU = ReplyKeyboardMarkup(
    [
        ["ð Admin Panel"],
        ["ð HÄ±zlÄ± BaÅla", "ð Durumum"],
        ["ð¢ VIP Kanallar"],
        ["ð° Bakiye", "ð£ Reklam Ver"],
        ["ð ÃyeliÄim", "ð GeÃ§miÅim"],
        ["ð Referans"],
        ["â SSS"],
        ["ð Destek", "â¹ï¸ YardÄ±m"],
    ],
    resize_keyboard=True,
)

CANCEL_WORDS = {"iptal", "vazgeÃ§", "vazgec", "geri", "cancel", "menÃ¼", "menu"}

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


def normalize(text: str) -> str:
    t = (text or "").strip()
    # Robust button matching: emoji or no emoji both work.
    if "Admin Panel" in t:
        return "admin"
    if "HÄ±zlÄ±" in t or "Hizli" in t:
        return "quick"
    if "Durumum" in t:
        return "status"
    if "VIP Kanallar" in t:
        return "vip"
    if "Bakiye" in t and "YÃ¼kle" not in t and "Yukle" not in t:
        return "balance"
    if "Reklam Ver" in t:
        return "ad"
    if "ÃyeliÄim" in t or "Uyeligim" in t:
        return "subs"
    if "GeÃ§miÅim" in t or "Gecmisim" in t:
        return "history"
    if "Referans" in t:
        return "ref"
    if "SSS" in t:
        return "faq"
    if "Destek" in t:
        return "support"
    if "YardÄ±m" in t or "Yardim" in t:
        return "help"
    return t


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
    risky = ["ifÅa", "ifsa", "leak", "sÄ±zdÄ±r", "sizdir", "Ã§ocuk", "cocuk", "minor", "reÅit", "resit"]
    low = (text or "").lower()
    return [w for w in risky if w in low]

# =========================
# AI
# =========================
def ai_available() -> bool:
    if OpenAI is None:
        return False
    if AI_PROVIDER == "groq":
        return bool(GROQ_API_KEY)
    if AI_PROVIDER == "openai":
        return bool(OPENAI_API_KEY)
    return bool(GROQ_API_KEY or OPENAI_API_KEY)


def make_ai_client():
    if not ai_available():
        return None
    if AI_PROVIDER == "groq" or (not AI_PROVIDER and GROQ_API_KEY):
        return OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    return OpenAI(api_key=OPENAI_API_KEY)


async def ai_text(prompt: str, system: str = "Sen kÄ±sa, net ve gÃ¼venli TÃ¼rkÃ§e yazan bir asistansÄ±n.", max_tokens: int = 500):
    if not ai_available():
        return None
    client = make_ai_client()
    if not client:
        return None
    try:
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error("AI error: %s", e)
        return None


async def ai_ad_variations(user_text: str):
    if risk_words(user_text):
        return None, "Reklam metninde riskli ifade var. LÃ¼tfen yasal, nÃ¶tr ve izinli bir reklam aÃ§Ä±klamasÄ± yaz."
    prompt = f"""
AÅaÄÄ±daki bilgiye gÃ¶re Telegram botu iÃ§in 3 reklam varyasyonu Ã¼ret.
Her varyasyon JSON dizisi olsun. Alanlar: title, text, button.
Kurallar: kÄ±sa, yasal, abartÄ±sÄ±z, yanÄ±ltÄ±cÄ± deÄil. Linki metne katma.
Bilgi:
{user_text}
"""
    raw = await ai_text(prompt, max_tokens=700)
    if not raw:
        return None, "AI reklam oluÅturulamadÄ±. GROQ_API_KEY / AI_MODEL ve Railway loglarÄ±nÄ± kontrol et."
    try:
        start = raw.find("[")
        end = raw.rfind("]")
        data = json.loads(raw[start:end + 1]) if start != -1 and end != -1 else None
        if isinstance(data, list) and data:
            return data[:3], None
    except Exception:
        pass
    # fallback parse as text
    return [
        {"title": "KÄ±sa ve Net", "text": raw[:250], "button": "Ä°ncele"},
    ], None


async def ai_support_answer(question: str):
    prompt = f"""
KullanÄ±cÄ±nÄ±n Telegram VIP botundaki sorununa kÄ±sa Ã¶n cevap ver.
Kural: Para iadesi, Ã¼yelik silme veya kesin iÅlem sÃ¶zÃ¼ verme. Gerekirse admin'e yÃ¶nlendir.
Soru: {question}
"""
    return await ai_text(prompt, max_tokens=350)


async def ai_daily_summary_text():
    data = collect_daily_metrics()
    prompt = f"""
AÅaÄÄ±daki bot metriklerinden kÄ±sa gÃ¼nlÃ¼k iÅletme Ã¶zeti Ã§Ä±kar.
Reklama odaklanma; VIP satÄ±Å, Ã¼yelik, destek, kullanÄ±cÄ± ve risklere bak.
En sonda 'BugÃ¼n yapÄ±lacak 3 iÅ' yaz.
Veri:
{json.dumps(data, ensure_ascii=False)}
"""
    ans = await ai_text(prompt, max_tokens=700)
    return ans or fallback_daily_summary(data)

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


def spend_balance(user_id, amount, desc="Bakiye harcandÄ±", order_id=None):
    amount = safe_int(amount, 0)
    ensure_balance_row(user_id)
    bal, spent = get_balance(user_id)
    if amount <= 0 or bal < amount:
        return False
    supabase.table("ad_balances").update({"balance": bal - amount, "spent": spent + amount, "updated_at": now_utc().isoformat()}).eq("user_id", int(user_id)).execute()
    supabase.table("ad_transactions").insert({"user_id": int(user_id), "amount": -amount, "type": "debit", "description": desc, "order_id": order_id}).execute()
    return True

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
        await update.message.reply_text("ð« Bu botu kullanma yetkin kÄ±sÄ±tlandÄ±.")
        return
    await update.message.reply_text(
        "ð Pasha VIP admin sistemine hoÅ geldin." if is_admin(user.id) else "ð Pasha VIP sistemine hoÅ geldin.",
        reply_markup=ADMIN_MENU if is_admin(user.id) else MAIN_MENU,
    )
    await quick_start_message(update.message, is_admin(user.id))


async def quick_start_message(message, admin=False):
    kb = [
        [InlineKeyboardButton("â­ VIP SatÄ±n Al", callback_data="quick_vip")],
        [InlineKeyboardButton("ð£ Reklam Ver", callback_data="quick_ad")],
        [InlineKeyboardButton("ð Durumum", callback_data="quick_status")],
        [InlineKeyboardButton("ð Destek", callback_data="quick_support")],
    ]
    await message.reply_text(
        "ð HÄ±zlÄ± BaÅla\n\nNe yapmak istiyorsun?",
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
            await update.message.reply_text("â Ä°Ålem iptal edildi.", reply_markup=ADMIN_MENU if is_admin(user.id) else MAIN_MENU)
            return
        # continue selected menu

    if context.user_data.get("mode"):
        await handle_text_mode(update, context)
        return

    if await is_blacklisted(user.id) and not is_admin(user.id):
        await update.message.reply_text("ð« Bu botu kullanma yetkin kÄ±sÄ±tlandÄ±.")
        return
    if maintenance_on() and not is_admin(user.id):
        await update.message.reply_text("ð§ Bot bakÄ±m modunda. LÃ¼tfen daha sonra tekrar dene.")
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
        await update.message.reply_text("MenÃ¼den bir seÃ§enek seÃ§ebilirsin.")


async def help_message(message):
    await message.reply_text(
        "â¹ï¸ YardÄ±m\n\n"
        "ð¢ VIP Kanallar: SatÄ±n alÄ±nabilir kanallarÄ± gÃ¶sterir.\n"
        "ð ÃyeliÄim: Aktif abonelik, link gÃ¶nderme ve iptal talebi burada.\n"
        "ð° Bakiye: Reklam bakiyeni yÃ¼kler ve gÃ¶sterir.\n"
        "ð£ Reklam Ver: Kanal seÃ§ip reklam talebi oluÅturur.\n"
        "ð¬ Otomatik Video: Admin panelden depo kanalÄ±nÄ± ana kanala baÄlar.\n"
        "ð Destek: Ãnce AI cevap verir, Ã§Ã¶zÃ¼lmezse adminâe gider."
    )

# =========================
# VIP SALES
# =========================
async def show_vip_channels(message, user_id):
    try:
        rows = supabase.table("channels").select("*").eq("active", True).order("id").execute().data or []
    except Exception as e:
        logger.error("channels fetch error: %s", e)
        await message.reply_text("â Kanallar yÃ¼klenemedi. Admin veritabanÄ±nÄ± kontrol etmeli.")
        return

    if not rows:
        await message.reply_text("ð¢ HenÃ¼z aktif VIP kanal yok.")
        return

    await message.reply_text(
        "ð¢ VIP Kanallar\n\n"
        "SatÄ±n almak istediÄin kanal kartÄ±ndaki butona bas. Ãdeme tamamlanÄ±nca tek kullanÄ±mlÄ±k giriÅ linkin otomatik gelir."
    )
    sent_count = 0
    for ch in rows:
        try:
            price = safe_int(ch.get("price"), 0)
            if price < 1 or not ch.get("chat_id") or not ch.get("name"):
                continue
            text = (
                f"ð¢ {ch.get('name')}\n"
                f"â­ Fiyat: {price} Stars\n"
                f"â³ SÃ¼re: {safe_int(ch.get('duration_days'), DEFAULT_DURATION_DAYS)} gÃ¼n"
            )
            if ch.get("description"):
                text += f"\n\nð {ch.get('description')}"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("ðï¸ Ãnizleme", callback_data=f"chprev_{ch['id']}")],
                [InlineKeyboardButton(f"â­ {price} Stars ile SatÄ±n Al", callback_data=f"buych_{ch['id']}")],
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
            "â Aktif kanal bulundu ama kart oluÅturulamadÄ±.\n"
            "Admin: Kanal adÄ±, fiyat ve Chat ID alanlarÄ±nÄ± kontrol et."
        )


async def show_channel_preview(message, channel_id, user_id):
    ch = await get_channel(channel_id)
    if not ch:
        await message.reply_text("â Kanal bulunamadÄ±.")
        return
    price = safe_int(ch.get("price"), 0)
    text = (
        f"ðï¸ Kanal Ãnizleme\n\n"
        f"ð¢ {ch.get('name')}\n"
        f"â­ Fiyat: {price} Stars\n"
        f"â³ SÃ¼re: {safe_int(ch.get('duration_days'), DEFAULT_DURATION_DAYS)} gÃ¼n\n\n"
        f"ð {ch.get('description') or 'AÃ§Ä±klama yok.'}"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"â­ {price} Stars ile SatÄ±n Al", callback_data=f"buych_{channel_id}")]])
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
        await query.message.reply_text("â Kanal aktif deÄil.")
        return
    price = safe_int(ch.get("price"), 0)
    if price < 1:
        await query.message.reply_text("â Kanal fiyatÄ± hatalÄ±.")
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
        title=f"{ch.get('name')} VIP Ãyelik",
        description=f"{safe_int(ch.get('duration_days'), DEFAULT_DURATION_DAYS)} gÃ¼nlÃ¼k VIP Ã¼yelik.",
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
        add_balance(user.id, amount, "Telegram Stars bakiye yÃ¼kleme")
        bal, _ = get_balance(user.id)
        await update.message.reply_text(f"â Bakiye yÃ¼klendi: {amount} Stars\nGÃ¼ncel bakiye: {bal} Stars")
        return

    if payload.startswith("vip_"):
        parts = payload.split("_")
        channel_id = safe_int(parts[1])
        price = safe_int(parts[2])
        ch = await get_channel(channel_id)
        if not ch:
            await update.message.reply_text("â Ãdeme alÄ±ndÄ± ama kanal bulunamadÄ±. Admin ile iletiÅime geÃ§.")
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
        if link:
            await update.message.reply_text(
                f"â Ãdeme baÅarÄ±lÄ±!\n\nð¢ Kanal: {ch.get('name')}\nð Tek kullanÄ±mlÄ±k giriÅ linkin:\n{link}\n\nBitiÅ: {end_date}"
            )
        else:
            await update.message.reply_text("â Ãdeme baÅarÄ±lÄ± ama link Ã¼retilemedi. Admin ile iletiÅime geÃ§.")
        try:
            await context.bot.send_message(OWNER_ID, f"â Yeni VIP satÄ±Å\nKullanÄ±cÄ±: {user.id}\nKanal: {ch.get('name')}\nFiyat: {price} Stars")
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
        await message.reply_text("ð Aktif Ã¼yeliÄin yok.")
        return
    for sub in rows:
        ch = await get_channel(sub.get("channel_id"))
        name = ch.get("name") if ch else f"Kanal ID {sub.get('channel_id')}"
        used = safe_int(sub.get("link_resend_count"), 0)
        left = max(0, MAX_LINK_RESENDS - used)
        kb = []
        row = []
        if left > 0:
            row.append(InlineKeyboardButton(f"ð Link GÃ¶nder ({left}/2)", callback_data=f"resend_{sub['id']}"))
        row.append(InlineKeyboardButton("â Ä°ptal Talebi", callback_data=f"cancelreq_{sub['id']}"))
        kb.append(row)
        kb.append([InlineKeyboardButton("â­ ÃyeliÄi Uzat", callback_data=f"buych_{sub['channel_id']}")])
        await message.reply_text(
            f"ð Aktif Ãyelik\n\nð¢ {name}\nDurum: {sub.get('status')}\nBitiÅ: {sub.get('end_date')}\nYeni link hakkÄ±: {left}/2",
            reply_markup=InlineKeyboardMarkup(kb),
        )


async def resend_link(query, context):
    sub_id = safe_int(query.data.split("_")[1])
    sub = await get_subscription(sub_id)
    if not sub or int(sub.get("user_id")) != int(query.from_user.id) or sub.get("status") != "active":
        await query.message.reply_text("â Aktif Ã¼yelik bulunamadÄ±.")
        return
    used = safe_int(sub.get("link_resend_count"), 0)
    if used >= MAX_LINK_RESENDS:
        await query.message.reply_text("â Yeni link hakkÄ±n bitti. Admin ile iletiÅime geÃ§ebilirsin.")
        return
    ch = await get_channel(sub.get("channel_id"))
    link = await create_and_store_invite(context, sub.get("user_id"), sub.get("channel_id"), ch)
    if not link:
        await query.message.reply_text("â Link Ã¼retilemedi. Botun kanalda admin olduÄundan emin ol.")
        return
    supabase.table("subscriptions").update({"link_resend_count": used + 1}).eq("id", sub_id).execute()
    await query.message.reply_text(f"ð Yeni tek kullanÄ±mlÄ±k linkin:\n{link}\n\nKalan hakkÄ±n: {MAX_LINK_RESENDS - used - 1}/2")


async def request_cancel(query, context):
    sub_id = safe_int(query.data.split("_")[1])
    sub = await get_subscription(sub_id)
    if not sub or int(sub.get("user_id")) != int(query.from_user.id):
        await query.message.reply_text("â Ãyelik bulunamadÄ±.")
        return
    existing = supabase.table("cancel_requests").select("*").eq("user_id", sub.get("user_id")).eq("channel_id", sub.get("channel_id")).eq("status", "pending").execute().data or []
    if existing:
        await query.message.reply_text("â ï¸ Zaten bekleyen iptal talebin var.")
        return
    supabase.table("cancel_requests").insert({"user_id": sub.get("user_id"), "channel_id": sub.get("channel_id"), "status": "pending"}).execute()
    await query.message.reply_text("â Ä°ptal talebin admin onayÄ±na gÃ¶nderildi.")
    try:
        await context.bot.send_message(OWNER_ID, f"â Yeni iptal talebi\nUser ID: {sub.get('user_id')}\nKanal ID: {sub.get('channel_id')}")
    except Exception:
        pass


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
            await context.bot.send_message(sub.get("user_id"), "â VIP Ã¼yelik sÃ¼ren bitti. Yenilemek iÃ§in VIP Kanallar bÃ¶lÃ¼mÃ¼nÃ¼ kullanabilirsin.")
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
        f"ð Durumum\n\n"
        f"ð Aktif Ã¼yelik: {len(active_subs)}\n"
        f"ð° Reklam bakiyesi: {bal} Stars\n"
        f"ð¸ Harcanan reklam bakiyesi: {spent} Stars\n"
        f"ð£ Bekleyen reklam: {len(pending_ads)}"
    )


async def my_history(message, user_id):
    sales = supabase.table("sales").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute().data or []
    ads = supabase.table("ad_orders").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute().data or []
    text = "ð GeÃ§miÅim\n\n"
    text += "â­ VIP SatÄ±ÅlarÄ±:\n"
    if sales:
        for s in sales:
            ch = await get_channel(s.get("channel_id"))
            text += f"- {ch.get('name') if ch else s.get('channel_id')} | {s.get('price')} Stars | {s.get('created_at')}\n"
    else:
        text += "- Yok\n"
    text += "\nð£ Reklamlar:\n"
    if ads:
        for a in ads:
            text += f"- {a.get('title')} | {a.get('status')} | {a.get('price')} Stars | GÃ¶rÃ¼ntÃ¼lenme: {a.get('views_count') or 0} | TÄ±k: {a.get('clicks_count') or 0}\n"
    else:
        text += "- Yok"
    await message.reply_text(text[:3900])


async def referral_user_message(message, context, user_id):
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    rows = supabase.table("users").select("*").eq("user_id", int(user_id)).execute().data or []
    pts = safe_int(rows[0].get("referral_points"), 0) if rows else 0
    await message.reply_text(f"ð Referans\n\nSenin linkin:\n{link}\n\nMevcut puan: {pts}")

# =========================
# BALANCE + ADS
# =========================
async def show_balance_center(message, user_id):
    bal, spent = get_balance(user_id)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("â­ Bakiye Ekle", callback_data="bal_topup")],
        [InlineKeyboardButton("ð£ Kanallara Reklam Ver", callback_data="bal_ad")],
        [InlineKeyboardButton("ð ReklamlarÄ±m", callback_data="bal_myads")],
        [InlineKeyboardButton("ð§¾ Bakiye Hareketleri", callback_data="bal_tx")],
    ])
    await message.reply_text(f"ð° Reklam Bakiyen\n\nBakiye: {bal} Stars\nHarcanan: {spent} Stars", reply_markup=kb)


async def ask_topup_amount(message, context):
    context.user_data["mode"] = "topup_amount"
    await message.reply_text("â­ YÃ¼klemek istediÄin Stars tutarÄ±nÄ± yaz.\n\nÃrnek: 2500")


async def create_topup_invoice(message, context, amount):
    amount = safe_int(amount)
    if amount < AD_MIN_TOPUP:
        await message.reply_text("â Tutar en az 1 Stars olmalÄ±.")
        return
    await context.bot.send_invoice(
        chat_id=message.chat_id,
        title="Reklam Bakiyesi",
        description=f"{amount} Stars reklam bakiyesi yÃ¼kleme.",
        payload=f"adtopup_{amount}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Reklam Bakiyesi", amount=amount)],
    )


async def show_ad_channel_choices(message, user_id):
    rows = supabase.table("channels").select("*").eq("active", True).order("id").execute().data or []
    if not rows:
        await message.reply_text("ð£ Reklam verilecek aktif kanal yok.")
        return
    bal, _ = get_balance(user_id)
    await message.reply_text(f"ð£ Reklam verilecek kanalÄ± seÃ§.\n\nBakiyen: {bal} Stars")
    for ch in rows:
        price = safe_int(ch.get("ad_price"), 1000)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"ð£ Bu kanalda reklam ver - {price} Stars", callback_data=f"adch_{ch['id']}")]])
        await message.reply_text(f"ð¢ {ch.get('name')}\nReklam fiyatÄ±: {price} Stars", reply_markup=kb)


async def start_ad_for_channel(query, context):
    channel_id = safe_int(query.data.split("_")[1])
    ch = await get_channel(channel_id)
    if not ch or not ch.get("active"):
        await query.message.reply_text("â Kanal aktif deÄil.")
        return
    price = safe_int(ch.get("ad_price"), 1000)
    bal, _ = get_balance(query.from_user.id)
    if bal < price and not (is_admin(query.from_user.id) and test_mode_on()):
        await query.message.reply_text(f"â Bakiyen yetersiz.\nGerekli: {price} Stars\nBakiyen: {bal} Stars\n\nð° Bakiye bÃ¶lÃ¼mÃ¼nden yÃ¼kleme yapabilirsin.")
        return
    context.user_data["ad_channel_id"] = channel_id
    context.user_data["ad_price"] = price
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("ð¤ AI ile Reklam YazdÄ±r", callback_data="ad_ai")],
        [InlineKeyboardButton("â¡ Tek Mesajla Reklam", callback_data="ad_one")],
        [InlineKeyboardButton("â¨ HazÄ±r Reklam OluÅtur", callback_data="ad_template")],
        [InlineKeyboardButton("â Ä°ptal", callback_data="flow_cancel")],
    ])
    await query.message.reply_text(
        f"ð£ {ch.get('name')} kanalÄ±na reklam ver\nFiyat: {price} Stars\n\nNasÄ±l reklam oluÅturmak istiyorsun?",
        reply_markup=kb,
    )


async def ask_ad_ai(message, context):
    context.user_data["mode"] = "ad_ai_prompt"
    await message.reply_text("ð¤ ReklamÄ±nÄ± kÄ±saca anlat ve linki ekle.\n\nÃrnek:\nYeni VIP kanal reklamÄ±. HÄ±zlÄ± katÄ±lÄ±m, Stars ile Ã¶deme. Link: https://t.me/kanal")


async def ask_ad_one(message, context):
    context.user_data["mode"] = "ad_one"
    await message.reply_text("â¡ ReklamÄ±nÄ± tek mesajla gÃ¶nder:\n\nBaÅlÄ±k | Metin | Link\n\nÃrnek:\nYeni Kanal | GÃ¼ncel paylaÅÄ±mlar iÃ§in hemen incele | https://t.me/kanal")


async def ask_ad_template(message, context):
    context.user_data["mode"] = "ad_template"
    await message.reply_text("â¨ HazÄ±r reklam iÃ§in Åunu yaz:\n\nBaÅlÄ±k | KÄ±sa aÃ§Ä±klama | Link")


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
        await message.reply_text("â Kanal bulunamadÄ±.")
        return
    clean_link = normalize_link(link)
    if not clean_link:
        await message.reply_text("â Link hatalÄ±. https://t.me/... Åeklinde gÃ¶nder.")
        return
    if risk_words(f"{title} {body} {clean_link}"):
        await message.reply_text("â Reklam metni riskli gÃ¶rÃ¼nÃ¼yor. LÃ¼tfen yasal ve nÃ¶tr bir metinle tekrar dene.")
        return
    if not (is_admin(user.id) and test_mode_on()):
        if not spend_balance(user.id, price, f"Reklam talebi: {ch.get('name')}"):
            await message.reply_text("â Bakiyen yetersiz.")
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
    await message.reply_text("â Reklam talebin admin onayÄ±na gÃ¶nderildi.")
    try:
        await context.bot.send_message(OWNER_ID, f"ð£ Yeni reklam talebi\nID: {row['id']}\nKullanÄ±cÄ±: {user.id}\nKanal: {ch.get('name')}\nFiyat: {price} Stars")
    except Exception:
        pass


async def my_ad_orders(message, user_id):
    rows = supabase.table("ad_orders").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute().data or []
    if not rows:
        await message.reply_text("ð HenÃ¼z reklam talebin yok.")
        return
    text = "ð ReklamlarÄ±m\n\n"
    for o in rows:
        text += f"ID: {o.get('id')}\nBaÅlÄ±k: {o.get('title')}\nDurum: {o.get('status')}\nFiyat: {o.get('price')} Stars\nGÃ¶rÃ¼ntÃ¼lenme: {o.get('views_count') or 0}\nTÄ±klama: {o.get('clicks_count') or 0}\nLink: {o.get('published_links') or '-'}\n\n"
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
    await update.message.reply_text(f"ð Reklam baÄlantÄ±sÄ±:\n{order.get('link')}")
    return True

# =========================
# SUPPORT / FAQ
# =========================
async def support_menu(message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("ð¤ AI Destek CevabÄ±", callback_data="support_ai")],
        [InlineKeyboardButton("ð¤ Admin'e Yaz", callback_data="support_admin")],
    ])
    await message.reply_text("ð Destek\n\nÃnce AI hÄ±zlÄ± cevap verebilir. ÃÃ¶zÃ¼lmezse admin'e iletebilirsin.", reply_markup=kb)


async def faq_user_message(message):
    faqs = [
        ("Botu VIP gruba/kanala nasÄ±l baÄlarÄ±m?", "Botu ilgili kanal veya gruba admin yap. Mesaj gÃ¶nder, kullanÄ±cÄ± davet et ve kullanÄ±cÄ± yasakla yetkilerini aÃ§. Sonra kanala id yaz."),
        ("Yeni link hakkÄ±m kaÃ§?", "Her aktif abonelikte en fazla 2 kez yeni link isteyebilirsin."),
        ("Ãdeme yaptÄ±m link gelmedi", "ÃyeliÄim ekranÄ±ndan Link GÃ¶nder butonunu dene. Olmazsa destek aÃ§."),
        ("Reklam bakiyesi nedir?", "Kanallara reklam vermek iÃ§in kullanÄ±lan Stars bakiyesidir."),
        ("Otomatik video nasÄ±l Ã§alÄ±ÅÄ±r?", "Depo kanalÄ±na video atÄ±lÄ±r, bot ana kanala sadece videoyu gÃ¶nderir. Caption gitmez."),
    ]
    kb = [[InlineKeyboardButton(q, callback_data=f"faq_{i}")] for i, (q, _) in enumerate(faqs)]
    await message.reply_text("â SÄ±k Sorulan Sorular", reply_markup=InlineKeyboardMarkup(kb))


async def answer_faq(message, idx):
    faqs = [
        ("Botu VIP gruba/kanala nasÄ±l baÄlarÄ±m?", "Botu ilgili kanal veya gruba admin yap. Mesaj gÃ¶nder, kullanÄ±cÄ± davet et ve kullanÄ±cÄ± yasakla yetkilerini aÃ§. Sonra kanala id yaz."),
        ("Yeni link hakkÄ±m kaÃ§?", "Her aktif abonelikte en fazla 2 kez yeni link isteyebilirsin."),
        ("Ãdeme yaptÄ±m link gelmedi", "ÃyeliÄim ekranÄ±ndan Link GÃ¶nder butonunu dene. Olmazsa destek aÃ§."),
        ("Reklam bakiyesi nedir?", "Kanallara reklam vermek iÃ§in kullanÄ±lan Stars bakiyesidir."),
        ("Otomatik video nasÄ±l Ã§alÄ±ÅÄ±r?", "Depo kanalÄ±na video atÄ±lÄ±r, bot ana kanala sadece videoyu gÃ¶nderir. Caption gitmez."),
    ]
    if 0 <= idx < len(faqs):
        q, a = faqs[idx]
        await message.reply_text(f"â {q}\n\n{a}")

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
        "ð Admin Panel\n\n"
        f"BugÃ¼nkÃ¼ satÄ±Å: {len(today_sales)}\n"
        f"Aktif Ã¼yelik: {len(active_subs)}\n"
        f"Bekleyen reklam: {len(pending_ads)}\n"
        f"AÃ§Ä±k destek: {len(support)}\n"
        f"BakÄ±m modu: {'AÃIK' if maintenance_on() else 'KAPALI'}"
    )


async def open_admin_panel(message):
    kb = [
        [InlineKeyboardButton("ð Bekleyen Ä°Åler", callback_data="admin_pending")],
        [InlineKeyboardButton("ð¢ Kanal Ekle", callback_data="admin_add_channel")],
        [InlineKeyboardButton("ð¢ KanallarÄ± YÃ¶net", callback_data="admin_channels")],
        [InlineKeyboardButton("ð¥ KullanÄ±cÄ±lar", callback_data="admin_users")],
        [InlineKeyboardButton("ð£ Reklam Talepleri", callback_data="admin_ads")],
        [InlineKeyboardButton("ð¬ Otomatik Video", callback_data="admin_video")],
        [InlineKeyboardButton("ð¤ AI GÃ¼nlÃ¼k Ãzet", callback_data="admin_ai_summary")],
        [InlineKeyboardButton("ð§ª Sistem Testi", callback_data="admin_system_test")],
        [InlineKeyboardButton("ð§ BakÄ±m AÃ§/Kapat", callback_data="admin_maintenance")],
    ]
    await message.reply_text(await admin_dashboard_text(), reply_markup=InlineKeyboardMarkup(kb))


async def admin_pending(message):
    ads = supabase.table("ad_orders").select("*").eq("status", "pending").execute().data or []
    cancels = supabase.table("cancel_requests").select("*").eq("status", "pending").execute().data or []
    support = supabase.table("support_requests").select("*").eq("status", "open").execute().data or []
    failed = supabase.table("ad_orders").select("*").eq("status", "failed").execute().data or []
    await message.reply_text(f"ð Bekleyen Ä°Åler\n\nð£ Reklam: {len(ads)}\nâ Ä°ptal: {len(cancels)}\nð Destek: {len(support)}\nâ ï¸ BaÅarÄ±sÄ±z reklam: {len(failed)}")


async def admin_system_test(message, context):
    lines = ["ð§ª Sistem Testi"]
    try:
        supabase.table("users").select("id").limit(1).execute()
        lines.append("â Supabase baÄlantÄ±sÄ±")
    except Exception as e:
        lines.append(f"â Supabase: {e}")
    lines.append("â AI aktif" if ai_available() else "â ï¸ AI aktif deÄil")
    lines.append("â Bot Ã§alÄ±ÅÄ±yor")
    await message.reply_text("\n".join(lines))


async def admin_add_channel_prompt(message, context):
    context.user_data["mode"] = "add_channel"
    await message.reply_text(
        "ð¢ Kanal ekle\n\nFormat:\nAd | VIP Fiyat | ChatID | SÃ¼reGÃ¼n | AÃ§Ä±klama | GÃ¶rselURL | ReklamFiyatÄ±\n\nÃrnek:\nNUDE PLUS+ | 1000 | -1003921378538 | 30 | VIP kanal | https://site.com/a.jpg | 1000"
    )


async def admin_channels(message):
    rows = supabase.table("channels").select("*").order("id").execute().data or []
    if not rows:
        await message.reply_text("ð¢ Kanal yok.")
        return
    for ch in rows:
        status = "Aktif" if ch.get("active") else "Pasif"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("âï¸ Ad", callback_data=f"ched_name_{ch['id']}"), InlineKeyboardButton("ð° VIP Fiyat", callback_data=f"ched_price_{ch['id']}")],
            [InlineKeyboardButton("ð Chat ID", callback_data=f"ched_chat_{ch['id']}"), InlineKeyboardButton("â³ SÃ¼re", callback_data=f"ched_days_{ch['id']}")],
            [InlineKeyboardButton("ð¼ï¸ GÃ¶rsel", callback_data=f"ched_photo_{ch['id']}"), InlineKeyboardButton("ð£ Reklam FiyatÄ±", callback_data=f"ched_adprice_{ch['id']}")],
            [InlineKeyboardButton("AÃ§/Kapat", callback_data=f"chtoggle_{ch['id']}"), InlineKeyboardButton("ðï¸ Sil", callback_data=f"chdel_{ch['id']}")],
        ])
        await message.reply_text(
            f"ð¢ Kanal ID: {ch.get('id')}\nAd: {ch.get('name')}\nVIP fiyat: {ch.get('price')}\nReklam fiyatÄ±: {ch.get('ad_price') or 1000}\nChat ID: {ch.get('chat_id')}\nSÃ¼re: {ch.get('duration_days')} gÃ¼n\nDurum: {status}",
            reply_markup=kb,
        )


async def admin_users(message):
    rows = supabase.table("users").select("*").order("id", desc=True).limit(20).execute().data or []
    if not rows:
        await message.reply_text("ð¥ KullanÄ±cÄ± yok.")
        return
    for u in rows:
        bal, spent = get_balance(u.get("user_id"))
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("ð° Bakiye YÃ¼kle", callback_data=f"userbal_{u.get('user_id')}")]])
        await message.reply_text(f"ð¤ User ID: {u.get('user_id')}\nUsername: @{u.get('username') or '-'}\nBakiye: {bal} Stars\nHarcanan: {spent} Stars", reply_markup=kb)


async def admin_ads(message):
    rows = supabase.table("ad_orders").select("*").eq("status", "pending").order("id", desc=True).execute().data or []
    if not rows:
        await message.reply_text("ð£ Bekleyen reklam yok.")
        return
    for o in rows:
        ch = await get_channel(o.get("channel_id"))
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("â Onayla ve YayÄ±nla", callback_data=f"adapprove_{o['id']}")],
            [InlineKeyboardButton("â Reddet ve Ä°ade Et", callback_data=f"adreject_{o['id']}")],
        ])
        await message.reply_text(
            f"ð£ Reklam Talebi\n\nID: {o.get('id')}\nKullanÄ±cÄ±: {o.get('user_id')}\nKanal: {ch.get('name') if ch else o.get('channel_id')}\nFiyat: {o.get('price')} Stars\n\nBaÅlÄ±k:\n{o.get('title')}\n\nMetin:\n{o.get('ad_text')}\n\nLink:\n{o.get('link')}",
            reply_markup=kb,
        )


async def publish_ad_order(query, context, order_id):
    rows = supabase.table("ad_orders").select("*").eq("id", int(order_id)).execute().data or []
    if not rows:
        await query.message.reply_text("â Reklam bulunamadÄ±.")
        return
    o = rows[0]
    ch = await get_channel(o.get("channel_id"))
    if not ch or not ch.get("chat_id"):
        await query.message.reply_text("â Kanal Chat ID yok.")
        return
    try:
        bot_username = (await context.bot.get_me()).username
        track_url = f"https://t.me/{bot_username}?start=ad_{order_id}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("ð Ä°ncele", url=track_url)]])
        text = f"ð£ Sponsorlu Reklam\n\nð¥ {o.get('title')}\n{o.get('ad_text')}"
        sent = await context.bot.send_message(chat_id=int(ch.get("chat_id")), text=text, reply_markup=kb)
        link = private_channel_link(ch.get("chat_id"), sent.message_id)
        supabase.table("ad_orders").update({
            "status": "published",
            "published_at": now_utc().isoformat(),
            "published_links": link,
            "published_chat_count": 1,
        }).eq("id", int(order_id)).execute()
        await query.message.reply_text("â Reklam yayÄ±nlandÄ±.")
        try:
            await context.bot.send_message(o.get("user_id"), f"â ReklamÄ±n yayÄ±nlandÄ±.\nLink: {link or 'Kanal iÃ§inde yayÄ±nlandÄ±.'}")
        except Exception:
            pass
    except Exception as e:
        logger.error("publish ad error: %s", e)
        add_balance(o.get("user_id"), safe_int(o.get("price"), 0), "Reklam yayÄ±nlanamadÄ± iade", order_id)
        supabase.table("ad_orders").update({"status": "failed"}).eq("id", int(order_id)).execute()
        await query.message.reply_text("â Reklam yayÄ±nlanamadÄ±. Bakiye iade edildi. Botun kanalda mesaj gÃ¶nderme yetkisini kontrol et.")


async def reject_ad_order(query, context, order_id):
    rows = supabase.table("ad_orders").select("*").eq("id", int(order_id)).execute().data or []
    if not rows:
        await query.message.reply_text("â Reklam bulunamadÄ±.")
        return
    o = rows[0]
    add_balance(o.get("user_id"), safe_int(o.get("price"), 0), "Reklam reddi iadesi", order_id)
    supabase.table("ad_orders").update({"status": "rejected_refunded"}).eq("id", int(order_id)).execute()
    await query.message.reply_text("â Reklam reddedildi ve bakiye iade edildi.")
    try:
        await context.bot.send_message(o.get("user_id"), "â Reklam talebin reddedildi. Bakiye hesabÄ±na iade edildi.")
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
        await context.bot.send_message(post.chat_id, f"Chat ID:\n{post.chat_id}\n\nKanal kaydedildi. Admin Panel > Otomatik Video bÃ¶lÃ¼mÃ¼nden butonla seÃ§ebilirsin.")
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
    kb = [[InlineKeyboardButton("ð§­ Butonlu Kurulum", callback_data="av_setup")]]
    await message.reply_text(
        "ð¬ Otomatik Video\n\nDepo kanalÄ±na video attÄ±ÄÄ±nda ana kanala sadece video gider. YazÄ±/caption gÃ¶nderilmez.",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    if not routes:
        await message.reply_text("HenÃ¼z rota yok. Ãnce iki kanala da id yaz, sonra Butonlu Kurulum kullan.")
        return
    for r in routes:
        status = "Aktif" if r.get("active") else "Pasif"
        ikb = InlineKeyboardMarkup([[InlineKeyboardButton("AÃ§/Kapat", callback_data=f"avtoggle_{r['id']}"), InlineKeyboardButton("Sil", callback_data=f"avdel_{r['id']}")]])
        await message.reply_text(f"Rota ID: {r.get('id')}\n{r.get('name') or '-'}\nKaynak: {r.get('source_chat_id')}\nHedef: {r.get('target_chat_id')}\nDurum: {status}", reply_markup=ikb)


async def auto_video_setup_source(message):
    chats = supabase.table("auto_video_detected_chats").select("*").order("updated_at", desc=True).limit(20).execute().data or []
    if not chats:
        await message.reply_text("KayÄ±tlÄ± kanal yok. Depo ve ana kanala dÃ¼z mesaj olarak id yaz.")
        return
    kb = [[InlineKeyboardButton(f"{c.get('title')} ({c.get('chat_id')})", callback_data=f"avsrc_{c.get('chat_id')}")] for c in chats]
    await message.reply_text("Ãnce depo/kaynak kanalÄ±nÄ± seÃ§:", reply_markup=InlineKeyboardMarkup(kb))

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
                await update.message.reply_text("â Format: BaÅlÄ±k | Metin | Link")
                return
            await create_ad_order(update.message, context, *parsed)

        elif mode == "ad_template":
            parsed = parse_ad_pipe(text)
            if not parsed:
                await update.message.reply_text("â Format: BaÅlÄ±k | KÄ±sa aÃ§Ä±klama | Link")
                return
            title, short, link = parsed
            body = f"{short}\n\nDetaylar iÃ§in butona bas."
            await create_ad_order(update.message, context, title, body, link)

        elif mode == "ad_ai_prompt":
            await update.message.reply_text("Yapay zeka reklam metnini hazÄ±rlÄ±yor...")
            variations, err = await ai_ad_variations(text)
            if err:
                await update.message.reply_text(err)
                return
            context.user_data["ai_ad_variations"] = variations
            for i, v in enumerate(variations, start=1):
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("â Bu metni kullan", callback_data=f"aiaduse_{i-1}")]])
                await update.message.reply_text(
                    f"ð¤ SeÃ§enek {i}\n\nBaÅlÄ±k: {v.get('title')}\nMetin: {v.get('text')}\nButon: {v.get('button') or 'Ä°ncele'}",
                    reply_markup=kb,
                )

        elif mode == "ad_ai_link":
            title = context.user_data.get("ai_ad_title")
            body = context.user_data.get("ai_ad_text")
            if not title or not body:
                context.user_data.clear()
                await update.message.reply_text("â AI metni kayboldu. ReklamÄ± tekrar oluÅtur.")
                return
            await create_ad_order(update.message, context, title, body, text)

        elif mode == "support_ai_text":
            context.user_data["last_support_text"] = text
            await update.message.reply_text("ð¤ Destek cevabÄ± hazÄ±rlanÄ±yor...")
            ans = await ai_support_answer(text) or "Bu konu iÃ§in admin desteÄi gerekebilir. Ä°stersen mesajÄ±nÄ± adminâe iletebilirim."
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("â Sorunum Ã§Ã¶zÃ¼ldÃ¼", callback_data="support_done"), InlineKeyboardButton("ð¤ Admin'e gÃ¶nder", callback_data="support_send_admin")]])
            await update.message.reply_text(ans, reply_markup=kb)

        elif mode == "support_admin_text":
            context.user_data.clear()
            supabase.table("support_requests").insert({"user_id": user.id, "username": username_of(user), "message": text, "status": "open"}).execute()
            await update.message.reply_text("â Destek talebin adminâe gÃ¶nderildi.")
            try:
                await context.bot.send_message(OWNER_ID, f"ð Yeni destek\nUser ID: {user.id}\nMesaj:\n{text}")
            except Exception:
                pass

        elif mode == "add_channel":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 4:
                await update.message.reply_text("â Format: Ad | VIP Fiyat | ChatID | SÃ¼reGÃ¼n | AÃ§Ä±klama | GÃ¶rselURL | ReklamFiyatÄ±")
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
            await update.message.reply_text("â Kanal eklendi.")

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
            await update.message.reply_text("â Kanal bilgisi gÃ¼ncellendi.")

        elif mode == "admin_add_balance":
            target = context.user_data.get("target_user_id")
            amount = safe_int(text)
            if amount <= 0:
                await update.message.reply_text("â Sadece tutarÄ± yaz. Ãrnek: 2500")
                return
            add_balance(target, amount, f"Admin manuel bakiye yÃ¼kledi: {user.id}")
            context.user_data.clear()
            await update.message.reply_text(f"â {target} kullanÄ±cÄ±sÄ±na {amount} Stars bakiye eklendi.")
            try:
                await context.bot.send_message(target, f"â Admin hesabÄ±na {amount} Stars reklam bakiyesi ekledi.")
            except Exception:
                pass

        else:
            context.user_data.clear()
            await update.message.reply_text("Ä°Ålem anlaÅÄ±lamadÄ±. MenÃ¼den tekrar seÃ§.")
    except Exception as e:
        logger.error("mode error: %s", e)
        context.user_data.clear()
        await update.message.reply_text("â Ä°Ålem sÄ±rasÄ±nda hata oldu. LÃ¼tfen tekrar dene.")

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
        await query.message.reply_text("â Ä°Ålem iptal edildi.")
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
    if data.startswith("cancelreq_"):
        await request_cancel(query, context); return

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
    if data == "ad_ai":
        await ask_ad_ai(query.message, context); return
    if data == "ad_one":
        await ask_ad_one(query.message, context); return
    if data == "ad_template":
        await ask_ad_template(query.message, context); return
    if data.startswith("aiaduse_"):
        idx = safe_int(data.split("_")[1])
        variations = context.user_data.get("ai_ad_variations") or []
        if idx >= len(variations):
            await query.message.reply_text("â SeÃ§enek bulunamadÄ±."); return
        v = variations[idx]
        context.user_data["mode"] = "ad_ai_link"
        context.user_data["ai_ad_title"] = v.get("title") or "Sponsorlu Reklam"
        context.user_data["ai_ad_text"] = v.get("text") or "Detaylar iÃ§in incele."
        await query.message.reply_text("SeÃ§ilen reklam metni hazÄ±r. Åimdi sadece linki gÃ¶nder:\n\nÃrnek: https://t.me/kanal")
        return

    # support
    if data == "support_ai":
        context.user_data["mode"] = "support_ai_text"
        await query.message.reply_text("Sorununu tek mesaj olarak yaz:")
        return
    if data == "support_admin":
        context.user_data["mode"] = "support_admin_text"
        await query.message.reply_text("Adminâe iletilecek mesajÄ±nÄ± yaz:")
        return
    if data == "support_done":
        context.user_data.clear()
        await query.message.reply_text("â Sevindim. BaÅka sorun olursa destek bÃ¶lÃ¼mÃ¼nÃ¼ kullanabilirsin.")
        return
    if data == "support_send_admin":
        text = context.user_data.get("last_support_text") or "KullanÄ±cÄ± admin desteÄi istedi."
        context.user_data.clear()
        supabase.table("support_requests").insert({"user_id": user_id, "username": username_of(query.from_user), "message": text, "status": "open"}).execute()
        await query.message.reply_text("â MesajÄ±n adminâe iletildi.")
        try:
            await context.bot.send_message(OWNER_ID, f"ð Destek\nUser ID: {user_id}\nMesaj:\n{text}")
        except Exception:
            pass
        return

    # admin only from here
    if not is_admin(user_id):
        await query.message.reply_text("â Yetkin yok.")
        return

    if data == "admin_pending": await admin_pending(query.message); return
    if data == "admin_add_channel": await admin_add_channel_prompt(query.message, context); return
    if data == "admin_channels": await admin_channels(query.message); return
    if data == "admin_users": await admin_users(query.message); return
    if data == "admin_ads": await admin_ads(query.message); return
    if data == "admin_video": await auto_video_panel(query.message); return
    if data == "admin_ai_summary":
        await query.message.reply_text("ð¤ GÃ¼nlÃ¼k Ã¶zet hazÄ±rlanÄ±yor...")
        await query.message.reply_text(await ai_daily_summary_text()); return
    if data == "admin_system_test": await admin_system_test(query.message, context); return
    if data == "admin_maintenance":
        set_setting("maintenance", "off" if maintenance_on() else "on")
        await query.message.reply_text("â BakÄ±m modu deÄiÅtirildi."); return

    if data.startswith("ched_"):
        parts = data.split("_")
        field = parts[1]
        ch_id = safe_int(parts[2])
        context.user_data["mode"] = f"edit_channel_{field}"
        context.user_data["channel_id"] = ch_id
        prompts = {
            "name": "Yeni kanal adÄ±nÄ± yaz:",
            "price": "Yeni VIP fiyatÄ±nÄ± yaz:",
            "chat": "Yeni Chat ID yaz:",
            "days": "Yeni sÃ¼reyi gÃ¼n olarak yaz:",
            "photo": "GÃ¶rsel URL yaz. KaldÄ±rmak iÃ§in - yaz:",
            "adprice": "Yeni reklam fiyatÄ±nÄ± yaz:",
        }
        await query.message.reply_text(prompts.get(field, "Yeni deÄeri yaz:")); return
    if data.startswith("chtoggle_"):
        ch_id = safe_int(data.split("_")[1])
        ch = await get_channel(ch_id)
        if ch:
            supabase.table("channels").update({"active": not bool(ch.get("active"))}).eq("id", ch_id).execute()
        await query.message.reply_text("â Kanal durumu deÄiÅtirildi."); return
    if data.startswith("chdel_"):
        ch_id = safe_int(data.split("_")[1])
        supabase.table("channels").delete().eq("id", ch_id).execute()
        await query.message.reply_text("â Kanal silindi."); return
    if data.startswith("userbal_"):
        target = safe_int(data.split("_")[1])
        context.user_data["mode"] = "admin_add_balance"
        context.user_data["target_user_id"] = target
        await query.message.reply_text(f"ð° {target} kullanÄ±cÄ±sÄ±na eklenecek bakiyeyi yaz.\n\nÃrnek: 2500"); return
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
        await query.message.reply_text("Åimdi ana/hedef kanalÄ± seÃ§:", reply_markup=InlineKeyboardMarkup(kb)); return
    if data.startswith("avtgt_"):
        tgt = data.replace("avtgt_", "")
        src = context.user_data.get("av_source")
        if not src:
            await query.message.reply_text("â Kaynak seÃ§imi kayboldu. Tekrar baÅlat."); return
        supabase.table("auto_video_routes").insert({"source_chat_id": src, "target_chat_id": tgt, "name": f"{src} -> {tgt}", "active": True, "strip_caption": True}).execute()
        context.user_data.pop("av_source", None)
        await query.message.reply_text("â Otomatik video aktarma kuruldu. Depo kanalÄ±ndaki videolar ana kanala sadece video olarak gider."); return
    if data.startswith("avtoggle_"):
        rid = safe_int(data.split("_")[1])
        rows = supabase.table("auto_video_routes").select("*").eq("id", rid).execute().data or []
        if rows:
            supabase.table("auto_video_routes").update({"active": not bool(rows[0].get("active"))}).eq("id", rid).execute()
        await query.message.reply_text("â Rota durumu deÄiÅtirildi."); return
    if data.startswith("avdel_"):
        rid = safe_int(data.split("_")[1])
        supabase.table("auto_video_routes").delete().eq("id", rid).execute()
        await query.message.reply_text("â Rota silindi."); return


async def balance_transactions(message, user_id):
    rows = supabase.table("ad_transactions").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute().data or []
    if not rows:
        await message.reply_text("ð§¾ Bakiye hareketi yok.")
        return
    text = "ð§¾ Bakiye Hareketleri\n\n"
    for r in rows:
        text += f"{r.get('amount')} Stars | {r.get('description')} | {r.get('created_at')}\n"
    await message.reply_text(text[:3900])

# =========================
# DAILY SUMMARY
# =========================
def collect_daily_metrics():
    today = now_utc().date().isoformat()
    yesterday = (now_utc().date() - timedelta(days=1)).isoformat()
    def table(name):
        try:
            return supabase.table(name).select("*").execute().data or []
        except Exception:
            return []
    sales = table("sales"); users = table("users"); subs = table("subscriptions"); support = table("support_requests"); ads = table("ad_orders"); balances = table("ad_balances")
    return {
        "today": today,
        "sales_today": len([s for s in sales if str(s.get("created_at") or "").startswith(today)]),
        "sales_yesterday": len([s for s in sales if str(s.get("created_at") or "").startswith(yesterday)]),
        "new_users_today": len([u for u in users if str(u.get("created_at") or "").startswith(today)]),
        "active_subscriptions": len([s for s in subs if s.get("status") == "active"]),
        "expiring_today": len([s for s in subs if s.get("status") == "active" and parse_dt(s.get("end_date")) and parse_dt(s.get("end_date")).date().isoformat() == today]),
        "open_support": len([s for s in support if s.get("status") == "open"]),
        "pending_ads": len([a for a in ads if a.get("status") == "pending"]),
        "failed_ads": len([a for a in ads if a.get("status") == "failed"]),
        "total_ad_balance": sum(safe_int(b.get("balance"), 0) for b in balances),
    }


def fallback_daily_summary(data):
    return (
        "ð¤ GÃ¼nlÃ¼k Ãzet\n\n"
        f"BugÃ¼nkÃ¼ VIP satÄ±Å: {data['sales_today']}\n"
        f"Yeni kullanÄ±cÄ±: {data['new_users_today']}\n"
        f"Aktif Ã¼yelik: {data['active_subscriptions']}\n"
        f"BugÃ¼n bitecek Ã¼yelik: {data['expiring_today']}\n"
        f"AÃ§Ä±k destek: {data['open_support']}\n"
        f"Bekleyen reklam: {data['pending_ads']}\n\n"
        "BugÃ¼n yapÄ±lacak 3 iÅ:\n"
        "1. AÃ§Ä±k destekleri kontrol et.\n"
        "2. BugÃ¼n bitecek Ã¼yeliklere yenileme hatÄ±rlatmasÄ± yap.\n"
        "3. Bekleyen reklamlarÄ± onayla veya iade et."
    )


async def daily_ai_report_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_message(OWNER_ID, await ai_daily_summary_text())
    except Exception as e:
        logger.error("daily report error: %s", e)

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
app.job_queue.run_repeating(daily_ai_report_job, interval=43200, first=300)

print("Pasha Store bot Ã§alÄ±ÅÄ±yor...")
app.run_polling()
