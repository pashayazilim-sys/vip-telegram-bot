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
    raise ValueError("BOT_TOKEN Railway Variables iÃ§inde yok.")
if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL Railway Variables iÃ§inde yok.")
if not SUPABASE_KEY:
    raise ValueError("SUPABASE_KEY Railway Variables iÃ§inde yok.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["ð¢ VIP Kanallar", "ð¦ Paketler"],
        ["ð ÃyeliÄim", "ð GeÃ§miÅim"],
        ["ð Referans", "ð Liderlik"],
        ["ð ÃekiliÅ", "ðï¸ Kupon Gir"],
        ["â SSS", "ð Destek"],
        ["â¹ï¸ YardÄ±m"],
    ],
    resize_keyboard=True,
)

ADMIN_MENU = ReplyKeyboardMarkup(
    [
        ["ð Admin Panel"],
        ["ð¢ VIP Kanallar", "ð¦ Paketler"],
        ["ð ÃyeliÄim", "ð GeÃ§miÅim"],
        ["ð Referans", "ð Liderlik"],
        ["ð ÃekiliÅ", "ðï¸ Kupon Gir"],
        ["â SSS", "ð Destek"],
        ["â¹ï¸ YardÄ±m"],
    ],
    resize_keyboard=True,
)

MENU_TEXTS = {
    "ð Admin Panel",
    "ð¢ VIP Kanallar",
    "ð¦ Paketler",
    "ð ÃyeliÄim",
    "ð GeÃ§miÅim",
    "â Ä°ptal Talebi",
    "ð Referans",
    "ð Liderlik",
    "ð ÃekiliÅ",
    "ðï¸ Kupon Gir",
    "â SSS",
    "ð Destek",
    "â¹ï¸ YardÄ±m",
}
CANCEL_TEXTS = {"iptal", "cancel", "vazgeÃ§", "vazgec", "geri", "menÃ¼", "menu"}
DEFAULT_GROUP_FAQS = [
    (
        "Botu VIP gruba/kanala nasÄ±l baÄlarÄ±m?",
        "Botu VIP grup veya kanala yÃ¶netici olarak ekle. Mesaj gÃ¶nder, kullanÄ±cÄ± davet et ve kullanÄ±cÄ± yasakla yetkilerini aÃ§. Sonra grup/kanal iÃ§ine dÃ¼z mesaj olarak id yaz; bot -100 ile baÅlayan Chat ID verir.",
    ),
    (
        "Kanal ID ile grup ID aynÄ± mÄ±?",
        "Ä°kisi de Chat ID olarak kullanÄ±lÄ±r. Telegram sÃ¼per gruplar ve kanallar genelde -100 ile baÅlayan ID verir. Bot VIP link Ã¼retirken bu IDâyi kullanÄ±r.",
    ),
    (
        "Bot kullanÄ±cÄ±yÄ± gruba direkt ekleyebilir mi?",
        "HayÄ±r. Telegram botlarÄ± kullanÄ±cÄ±yÄ± zorla gruba/kanala ekleyemez. Bot tek kullanÄ±mlÄ±k davet linki Ã¼retir; kullanÄ±cÄ± linke basÄ±p katÄ±lÄ±r.",
    ),
    (
        "Davet linki Ã§alÄ±ÅmÄ±yor, ne yapmalÄ±yÄ±m?",
        "ÃyeliÄim bÃ¶lÃ¼mÃ¼nden Yeni link gÃ¶nder butonuna bas. Link yine oluÅmuyorsa bot VIP grupta/kanalda admin deÄildir veya kullanÄ±cÄ± davet et yetkisi kapalÄ±dÄ±r.",
    ),
    (
        "VIP grup mu kanal mÄ± kullanmalÄ±yÄ±m?",
        "Sadece iÃ§erik yayÄ±nlayacaksan kanal daha temizdir. Ãyelerin konuÅmasÄ±nÄ± istiyorsan grup kullan. SatÄ±Å ve Ã¼yelik sistemi ikisinde de Ã§alÄ±ÅÄ±r.",
    ),
    (
        "Grup gizli mi olmalÄ±?",
        "Evet. VIP eriÅim satÄ±yorsan grup/kanal gizli olmalÄ±. KullanÄ±cÄ±lar sadece botun Ã¼rettiÄi tek kullanÄ±mlÄ±k linkle girmeli.",
    ),
]

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
        logger.warning("Setting okunamadÄ±: %s", e)
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
        logger.warning("Admin rol okunamadÄ±: %s", e)
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
        logger.warning("Log yazÄ±lamadÄ±: %s", e)


async def ensure_defaults_once(context: ContextTypes.DEFAULT_TYPE = None):
    # DB kurulmuÅsa eksik ayarlarÄ± ve grup SSS kayÄ±tlarÄ±nÄ± tamamlar.
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
        for q, a in DEFAULT_GROUP_FAQS:
            existing = supabase.table("faq").select("id").eq("question", q).execute()
            if not existing.data:
                supabase.table("faq").insert({"question": q, "answer": a, "active": True}).execute()
    except Exception as e:
        logger.warning("VarsayÄ±lan SSS eklenemedi: %s", e)

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
        # Var olan kullanÄ±cÄ±nÄ±n referrer'Ä±nÄ± sonradan deÄiÅtirme; sahte referansÄ± azaltÄ±r.
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
        logger.error("Davet linki Ã¼retilemedi: %s", e)
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
        logger.error("Kanaldan Ã§Ä±karÄ±lamadÄ±: %s", e)
        return False

# =========================================================
# START / TERMS / MENU ROUTING
# =========================================================

async def show_terms(message):
    kb = [[InlineKeyboardButton("â Kabul Ediyorum", callback_data="accept_terms")]]
    await message.reply_text(
        "â ï¸ Kurallar ve KullanÄ±m OnayÄ±\n\n"
        "Bu bot Ã¼zerinden verilen VIP eriÅimler yalnÄ±zca yasal, rÄ±zaya dayalÄ± ve kurallara uygun iÃ§erikler iÃ§indir.\n\n"
        "Devam ederek kurallarÄ± kabul etmiÅ olursun.",
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
    if await is_blacklisted(user.id) and not is_admin(user.id):
        await update.message.reply_text("ð« Bu botu kullanma yetkin kÄ±sÄ±tlandÄ±.")
        return
    if not is_admin(user.id) and not await user_accepted_terms(user.id):
        await show_terms(update.message)
        return
    await update.message.reply_text(
        "ð Pasha VIP admin sistemine hoÅ geldin." if is_admin(user.id) else "ð Pasha VIP sistemine hoÅ geldin.",
        reply_markup=ADMIN_MENU if is_admin(user.id) else MAIN_MENU,
    )


async def channel_id_reader(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post:
        return
    text = (update.channel_post.text or "").lower().strip()
    if text in ["id", "chat id", "kanal id", "grup id", "group id", "kanalid"]:
        await context.bot.send_message(chat_id=update.channel_post.chat_id, text=f"Chat ID:\n{update.channel_post.chat_id}")


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_defaults_once(context)
    text = update.message.text.strip()
    user = update.effective_user
    user_id = user.id
    await save_user(user)

    # CRITICAL FIX: mode stuck bug. Any menu/cancel text clears the pending flow.
    if context.user_data.get("mode") and (text in MENU_TEXTS or text.lower() in CANCEL_TEXTS):
        context.user_data.clear()
        if text.lower() in CANCEL_TEXTS:
            await update.message.reply_text(
                "â Ä°Ålem iptal edildi. MenÃ¼den tekrar seÃ§im yapabilirsin.",
                reply_markup=ADMIN_MENU if is_admin(user_id) else MAIN_MENU,
            )
            return
        # Continue with the selected menu instead of treating it as form input.

    if await is_blacklisted(user_id) and not is_admin(user_id):
        await update.message.reply_text("ð« Bu botu kullanma yetkin kÄ±sÄ±tlandÄ±.")
        return
    if not is_admin(user_id) and not await user_accepted_terms(user_id):
        await show_terms(update.message)
        return
    if context.user_data.get("mode"):
        await handle_text_mode(update, context)
        return
    if maintenance_on() and not is_admin(user_id):
        await update.message.reply_text("ð§ Bot bakÄ±m modunda. LÃ¼tfen daha sonra tekrar dene.")
        return

    if is_admin(user_id) and text == "ð Admin Panel":
        await open_admin_panel(update.message)
    elif text == "ð¢ VIP Kanallar":
        await show_vip_channels(update.message, user_id)
    elif text == "ð¦ Paketler":
        await show_packages(update.message, user_id)
    elif text == "ð ÃyeliÄim":
        await show_my_subscriptions(update.message, user_id)
    elif text == "ð GeÃ§miÅim":
        await my_history(update.message, user_id)
    elif text == "ð Referans":
        await referral_user_message(update.message, context, user_id)
    elif text == "ð Liderlik":
        await leaderboard_message(update.message)
    elif text == "ð ÃekiliÅ":
        await giveaway_user_message(update.message)
    elif text == "â Ä°ptal Talebi":
        await create_cancel_request(update, context)
    elif text == "ðï¸ Kupon Gir":
        context.user_data["mode"] = "user_coupon"
        await update.message.reply_text("ðï¸ Kupon kodunu yaz:")
    elif text == "ð Destek":
        await support_menu(update.message)
    elif text == "â SSS":
        await faq_user_message(update.message)
    elif text == "â¹ï¸ YardÄ±m":
        await help_message(update.message)
    else:
        await update.message.reply_text("MenÃ¼den bir seÃ§enek seÃ§ebilirsin.")


async def help_message(message):
    await message.reply_text(
        "â¹ï¸ YardÄ±m\n\n"
        "ð¢ VIP Kanallar: SatÄ±n alÄ±nabilir kanallarÄ± gÃ¶sterir.\n"
        "ð¦ Paketler: Birden fazla kanalÄ± avantajlÄ± paketle verir.\n"
        "ð ÃyeliÄim: Aktif Ã¼yeliklerini ve link yenilemeyi gÃ¶sterir.\n"
        "ð Referans: ArkadaÅ getirip puan kazanÄ±rsÄ±n.\n"
        "ð Liderlik: En Ã§ok davet yapanlarÄ± gÃ¶sterir.\n"
        "â SSS: Grup/kanal ve Ã¶deme sorunlarÄ± iÃ§in hazÄ±r cevaplar.\n"
        "ð Destek: Adminâe destek talebi gÃ¶nderir."
    )

# =========================================================
# ADMIN PANEL
# =========================================================

async def admin_dashboard_text():
    today = now_utc().date().isoformat()
    month = now_utc().strftime("%Y-%m")
    sales = supabase.table("sales").select("*").execute().data or []
    active_subs = supabase.table("subscriptions").select("*").eq("status", "active").execute().data or []
    supports = supabase.table("support_requests").select("*").eq("status", "open").execute().data or []
    abandoned = supabase.table("checkout_intents").select("*").eq("status", "started").execute().data or []
    blacklisted = supabase.table("blacklist").select("*").eq("active", True).execute().data or []
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
        "ð Admin Panel\n\n"
        f"ð BugÃ¼n: {today_count} satÄ±Å / {today_stars} Stars\n"
        f"ð Bu ay: {month_count} satÄ±Å / {month_stars} Stars\n"
        f"ð¥ Aktif Ã¼ye: {len(active_subs)}\n"
        f"ð YarÄ±m kalan Ã¶deme: {len(abandoned)}\n"
        f"â³ BugÃ¼n bitecek Ã¼yelik: {expiring_today}\n"
        f"ð AÃ§Ä±k destek: {len(supports)}\n"
        f"ð« Kara liste: {len(blacklisted)}\n"
        f"ð§ BakÄ±m modu: {'AÃIK' if maintenance_on() else 'KAPALI'}"
    )


async def open_admin_panel(message):
    kb = [
        [InlineKeyboardButton("â Kanal Ekle", callback_data="admin_add_channel"), InlineKeyboardButton("ð¦ Paket Ekle", callback_data="admin_add_package")],
        [InlineKeyboardButton("ð¢ KanallarÄ± YÃ¶net", callback_data="admin_channels"), InlineKeyboardButton("ð¦ Paketleri YÃ¶net", callback_data="admin_packages")],
        [InlineKeyboardButton("ð KullanÄ±cÄ±ya VIP Ver", callback_data="admin_grant")],
        [InlineKeyboardButton("ð Son SatÄ±Ålar", callback_data="admin_sales"), InlineKeyboardButton("ð Rapor", callback_data="admin_report")],
        [InlineKeyboardButton("ð¢ Kanal Ä°statistikleri", callback_data="admin_channel_stats"), InlineKeyboardButton("ð YarÄ±m Kalanlar", callback_data="admin_abandoned")],
        [InlineKeyboardButton("ð¥ KullanÄ±cÄ±lar", callback_data="admin_users"), InlineKeyboardButton("ð KullanÄ±cÄ± Ara", callback_data="admin_search_user")],
        [InlineKeyboardButton("ðï¸ Kuponlar", callback_data="admin_coupons"), InlineKeyboardButton("ð¥ Kampanya", callback_data="admin_campaign")],
        [InlineKeyboardButton("ð Referans Paneli", callback_data="admin_referrals"), InlineKeyboardButton("ð ÃekiliÅ Paneli", callback_data="admin_giveaway")],
        [InlineKeyboardButton("â SSS YÃ¶net", callback_data="admin_faq"), InlineKeyboardButton("ð Destek Talepleri", callback_data="admin_support")],
        [InlineKeyboardButton("â Ä°ptal Talepleri", callback_data="admin_cancel"), InlineKeyboardButton("ð« Kara Liste", callback_data="admin_blacklist")],
        [InlineKeyboardButton("ð® Adminler", callback_data="admin_admins"), InlineKeyboardButton("ð Ä°Ålem LoglarÄ±", callback_data="admin_logs")],
        [InlineKeyboardButton("ð SatÄ±Å CSV", callback_data="admin_export_sales"), InlineKeyboardButton("ð Grup/Kanal ID YardÄ±mÄ±", callback_data="admin_channel_id_help")],
        [InlineKeyboardButton("ð§ BakÄ±m AÃ§/Kapat", callback_data="admin_maintenance")],
    ]
    await message.reply_text(await admin_dashboard_text(), reply_markup=InlineKeyboardMarkup(kb))

# =========================================================
# DISPLAY CHANNELS / PACKAGES
# =========================================================

async def show_vip_channels(message, user_id):
    rows = supabase.table("channels").select("*").eq("active", True).order("id").execute().data or []
    if not rows:
        await message.reply_text("ð¢ HenÃ¼z VIP kanal eklenmedi.")
        return
    for ch in rows:
        base_price = safe_int(ch.get("price"), 0)
        final_price, coupon_code, discount_text = await calculate_price(user_id, base_price, ch.get("id"))
        variant = ab_variant(user_id)
        title = "ð¥ BugÃ¼ne Ã¶zel VIP eriÅim" if variant == "B" else "ð¢ VIP Kanal"
        campaign_line = f"\nð¥ Kampanya indirimi: %{campaign_percent()}" if campaign_percent() else ""
        coupon_line = f"\nðï¸ Kupon: {coupon_code} ({discount_text})" if coupon_code else ""
        text = (
            f"{title}\n\n"
            f"ð¢ {ch.get('name')}\n"
            f"â­ Fiyat: {base_price} Stars\n"
            f"â Ãdenecek: {final_price} Stars\n"
            f"â³ SÃ¼re: {ch.get('duration_days') or DEFAULT_DURATION_DAYS} gÃ¼n"
            f"{campaign_line}{coupon_line}"
        )
        kb = [
            [InlineKeyboardButton("ðï¸ Ãnizleme", callback_data=f"preview_channel_{ch['id']}")],
            [InlineKeyboardButton(f"â­ {final_price} Stars ile SatÄ±n Al", callback_data=f"buyc_{ch['id']}")],
        ]
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def show_channel_preview(message, channel_id, user_id):
    ch = await get_channel(channel_id)
    if not ch:
        await message.reply_text("â Kanal bulunamadÄ±.")
        return
    final_price, coupon_code, discount_text = await calculate_price(user_id, safe_int(ch.get("price"), 0), channel_id)
    coupon_line = f"\nðï¸ Kupon: {coupon_code} ({discount_text})" if coupon_code else ""
    text = (
        "ðï¸ Kanal Ãnizleme\n\n"
        f"ð¢ {ch.get('name')}\n"
        f"â­ Fiyat: {ch.get('price')} Stars\n"
        f"â Ãdenecek: {final_price} Stars\n"
        f"â³ SÃ¼re: {ch.get('duration_days') or DEFAULT_DURATION_DAYS} gÃ¼n\n"
        f"ð {ch.get('description') or 'AÃ§Ä±klama yok.'}\n\n"
        "â Ãdeme Telegram Stars ile yapÄ±lÄ±r\n"
        "â Link otomatik gÃ¶nderilir\n"
        "â Ãyelik tarihi botta gÃ¶rÃ¼nÃ¼r\n"
        "â Sorun olursa destek aÃ§abilirsin"
        f"{coupon_line}"
    )
    kb = [[InlineKeyboardButton(f"â­ {final_price} Stars ile SatÄ±n Al", callback_data=f"buyc_{channel_id}")]]
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
        await message.reply_text("ð¦ HenÃ¼z paket eklenmedi.")
        return
    for p in rows:
        base_price = safe_int(p.get("price"), 0)
        final_price, coupon_code, discount_text = await calculate_price(user_id, base_price, None)
        coupon_line = f"\nðï¸ Kupon: {coupon_code} ({discount_text})" if coupon_code else ""
        text = (
            f"ð¦ {p.get('name')}\n"
            f"â­ Fiyat: {base_price} Stars\n"
            f"â Ãdenecek: {final_price} Stars\n"
            f"â³ SÃ¼re: {p.get('duration_days') or DEFAULT_DURATION_DAYS} gÃ¼n\n"
            f"ð {p.get('description') or ''}"
            f"{coupon_line}"
        )
        kb = [[InlineKeyboardButton(f"â­ {final_price} Stars ile Paketi Al", callback_data=f"buyp_{p['id']}")]]
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

# =========================================================
# TEXT MODES
# =========================================================

async def handle_text_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    text = update.message.text.strip()
    user = update.effective_user
    user_id = user.id
    try:
        if mode == "add_channel":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 4:
                await update.message.reply_text("â Format: KanalAdÄ± | Fiyat | ChatID | SÃ¼reGÃ¼n | AÃ§Ä±klama")
                return
            payload = {
                "name": parts[0],
                "price": int(parts[1]),
                "chat_id": parts[2],
                "duration_days": int(parts[3]),
                "description": parts[4] if len(parts) >= 5 else None,
                "photo_url": None,
                "invite_link": "",
                "active": True,
            }
            supabase.table("channels").insert(payload).execute()
            await log_event("channel_added", user_id, details=str(payload))
            context.user_data.clear()
            await update.message.reply_text(f"â Kanal eklendi: {payload['name']}")

        elif mode == "add_package":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 4:
                await update.message.reply_text("â Format: PaketAdÄ± | Fiyat | SÃ¼reGÃ¼n | KanalIDleri | AÃ§Ä±klama")
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
            await update.message.reply_text(f"â Paket eklendi: {payload['name']}")

        elif mode in ["edit_price", "edit_duration", "edit_chat", "edit_description", "edit_photo"]:
            channel_id = context.user_data.get("channel_id")
            if mode == "edit_price":
                field, value, reply = "price", int(text), "â Fiyat gÃ¼ncellendi."
            elif mode == "edit_duration":
                field, value, reply = "duration_days", int(text), "â SÃ¼re gÃ¼ncellendi."
            elif mode == "edit_chat":
                field, value, reply = "chat_id", text, "â Chat ID gÃ¼ncellendi."
            elif mode == "edit_description":
                field, value, reply = "description", text, "â AÃ§Ä±klama gÃ¼ncellendi."
            else:
                field, value, reply = "photo_url", None if text == "-" else text, "â GÃ¶rsel URL gÃ¼ncellendi."
            supabase.table("channels").update({field: value}).eq("id", channel_id).execute()
            await log_event("channel_updated", user_id, channel_id=channel_id, details=f"{field}={value}")
            context.user_data.clear()
            await update.message.reply_text(reply)

        elif mode == "add_coupon":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 5:
                await update.message.reply_text("â Format: KOD | YÃ¼zdeÄ°ndirim | StarsÄ°ndirim | MaxKullanÄ±m | KanalID/0")
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
            await update.message.reply_text("â Kupon oluÅturuldu.")

        elif mode == "add_faq":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 2:
                await update.message.reply_text("â Format: Soru | Cevap")
                return
            supabase.table("faq").insert({"question": parts[0], "answer": parts[1], "active": True}).execute()
            await log_event("faq_added", user_id, details=text)
            context.user_data.clear()
            await update.message.reply_text("â SSS eklendi.")

        elif mode == "add_admin":
            if not is_owner(user_id):
                context.user_data.clear()
                await update.message.reply_text("â Sadece owner admin ekleyebilir.")
                return
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 2 or parts[1].lower() not in ["manager", "viewer"]:
                await update.message.reply_text("â Format: UserID | role\nRole: manager veya viewer")
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
            await update.message.reply_text("â Admin eklendi.")

        elif mode == "blacklist_reason":
            target_id = context.user_data.get("target_user_id")
            existing = supabase.table("blacklist").select("*").eq("user_id", target_id).execute()
            if existing.data:
                supabase.table("blacklist").update({"reason": text, "active": True}).eq("user_id", target_id).execute()
            else:
                supabase.table("blacklist").insert({"user_id": target_id, "reason": text, "active": True}).execute()
            await log_event("blacklisted", user_id, target_user_id=target_id, details=text)
            context.user_data.clear()
            await update.message.reply_text("â KullanÄ±cÄ± kara listeye alÄ±ndÄ±.")

        elif mode == "custom_grant_days":
            target_user_id = context.user_data.get("target_user_id")
            channel_id = context.user_data.get("channel_id")
            days = int(text)
            context.user_data.clear()
            await grant_vip_to_user(update.message, context, target_user_id, channel_id, custom_days=days)

        elif mode == "campaign_start":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 2:
                await update.message.reply_text("â Format: Ä°ndirimYÃ¼zde | Saat")
                return
            percent = max(1, min(95, int(parts[0])))
            hours = max(1, int(parts[1]))
            set_setting("campaign_enabled", "on")
            set_setting("campaign_percent", str(percent))
            set_setting("campaign_end", (now_utc() + timedelta(hours=hours)).isoformat())
            await log_event("campaign_started", user_id, details=text)
            context.user_data.clear()
            await update.message.reply_text(f"â Kampanya baÅladÄ±: %{percent} / {hours} saat")

        elif mode == "search_user":
            await search_user(update.message, text)
            context.user_data.clear()

        elif mode == "user_coupon":
            code = text.upper()
            coupon = await get_coupon(code)
            if not coupon or not coupon.get("active"):
                context.user_data.clear()
                await update.message.reply_text("â Kupon bulunamadÄ± veya aktif deÄil.")
                return
            if int(coupon.get("max_uses") or 0) > 0 and int(coupon.get("used_count") or 0) >= int(coupon.get("max_uses") or 0):
                context.user_data.clear()
                await update.message.reply_text("â Bu kuponun kullanÄ±m limiti dolmuÅ.")
                return
            supabase.table("users").update({"active_coupon": code}).eq("user_id", user_id).execute()
            context.user_data.clear()
            await update.message.reply_text(f"â Kupon uygulandÄ±: {code}")

        elif mode == "user_support":
            if await is_blacklisted(user_id):
                context.user_data.clear()
                await update.message.reply_text("ð« Destek talebi oluÅturamazsÄ±n.")
                return
            supabase.table("support_requests").insert({"user_id": user_id, "username": safe_username(user), "message": text, "status": "open"}).execute()
            await log_event("support_created", user_id, target_user_id=user_id, details=text)
            context.user_data.clear()
            await update.message.reply_text("â Destek talebin adminâe gÃ¶nderildi.")
            await context.bot.send_message(OWNER_ID, f"ð Yeni destek talebi!\n\nKullanÄ±cÄ±: @{safe_username(user) or 'yok'}\nID: {user_id}\n\n{text}")

        elif mode == "broadcast":
            context.user_data.clear()
            await broadcast_message(update.message, context, text)

    except Exception as e:
        logger.error("Text mode hatasÄ±: %s", e)
        context.user_data.clear()
        await update.message.reply_text("â Ä°Ålem sÄ±rasÄ±nda hata oldu. FormatÄ± kontrol et. Ä°Ålem modu kapatÄ±ldÄ±.")

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
        await query.message.reply_text("â KurallarÄ± kabul ettin. MenÃ¼den devam edebilirsin.", reply_markup=MAIN_MENU)
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

    # protected callbacks
    if not is_admin(user_id):
        await query.message.reply_text("â Yetkin yok.")
        return

    if data.startswith("cancel_"):
        await handle_cancel_admin(query, context)
        return
    if data.startswith("support_close_"):
        if not can_manage(user_id):
            await query.message.reply_text("â Yetkin yok.")
            return
        rid = int(data.split("_")[2])
        supabase.table("support_requests").update({"status": "closed"}).eq("id", rid).execute()
        await log_event("support_closed", user_id, details=f"request_id={rid}")
        await query.message.reply_text("â Destek talebi kapatÄ±ldÄ±.")
        return

    try:
        await admin_callback(query, context, data)
    except Exception as e:
        logger.error("Callback hatasÄ±: %s", e)
        context.user_data.clear()
        await query.message.reply_text("â Ä°Ålem sÄ±rasÄ±nda hata oldu. Mod kapatÄ±ldÄ±.")


async def admin_callback(query, context, data):
    user_id = query.from_user.id
    if data == "admin_add_channel":
        if not can_manage(user_id):
            await query.message.reply_text("â Yetkin yok."); return
        context.user_data["mode"] = "add_channel"
        await query.message.reply_text("â Kanal bilgilerini yaz:\n\nKanalAdÄ± | Fiyat | ChatID | SÃ¼reGÃ¼n | AÃ§Ä±klama\n\nÃrnek:\nVIP | 2500 | -1001234567890 | 30 | GÃ¼nlÃ¼k VIP kanal")
    elif data == "admin_add_package":
        if not can_manage(user_id):
            await query.message.reply_text("â Yetkin yok."); return
        context.user_data["mode"] = "add_package"
        await query.message.reply_text("ð¦ Paket ekle:\n\nPaketAdÄ± | Fiyat | SÃ¼reGÃ¼n | KanalIDleri | AÃ§Ä±klama\n\nÃrnek:\nTumVIP | 6000 | 30 | 1,2,3 | TÃ¼m VIP kanallar")
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
        await query.message.reply_text("ð KullanÄ±cÄ± ID veya username yaz:")
    elif data == "admin_coupons":
        await coupons_message(query.message)
    elif data == "coupon_add":
        if not can_manage(user_id):
            await query.message.reply_text("â Yetkin yok."); return
        context.user_data["mode"] = "add_coupon"
        await query.message.reply_text("ðï¸ Kupon oluÅtur:\n\nKOD | YÃ¼zdeÄ°ndirim | StarsÄ°ndirim | MaxKullanÄ±m | KanalID/0\n\nÃrnek:\nPASHA50 | 50 | 0 | 100 | 0")
    elif data.startswith("coupon_toggle_"):
        cid = int(data.split("_")[2])
        row = supabase.table("coupons").select("*").eq("id", cid).single().execute().data
        if row:
            supabase.table("coupons").update({"active": not bool(row.get("active"))}).eq("id", cid).execute()
        await log_event("coupon_toggled", user_id, details=f"coupon_id={cid}")
        await query.message.reply_text("â Kupon durumu deÄiÅtirildi.")
    elif data == "admin_campaign":
        await campaign_message(query.message)
    elif data == "campaign_start":
        context.user_data["mode"] = "campaign_start"
        await query.message.reply_text("ð¥ Kampanya baÅlat:\n\nÄ°ndirimYÃ¼zde | Saat\n\nÃrnek:\n30 | 6")
    elif data == "campaign_stop":
        set_setting("campaign_enabled", "off")
        await log_event("campaign_stopped", user_id)
        await query.message.reply_text("â Kampanya kapatÄ±ldÄ±.")
    elif data == "admin_referrals":
        await referrals_admin_message(query.message)
    elif data == "admin_giveaway":
        await giveaway_admin_message(query.message)
    elif data == "giveaway_run":
        await run_giveaway(query.message, context, previous_week_key(), manual=True)
    elif data == "admin_faq":
        await faq_admin_message(query.message)
    elif data == "faq_add":
        context.user_data["mode"] = "add_faq"
        await query.message.reply_text("â SSS ekle:\n\nSoru | Cevap")
    elif data.startswith("faq_toggle_"):
        fid = int(data.split("_")[2])
        row = supabase.table("faq").select("*").eq("id", fid).single().execute().data
        if row:
            supabase.table("faq").update({"active": not bool(row.get("active"))}).eq("id", fid).execute()
        await query.message.reply_text("â SSS durumu deÄiÅtirildi.")
    elif data == "admin_broadcast":
        context.user_data["mode"] = "broadcast"
        await query.message.reply_text("ð£ TÃ¼m kullanÄ±cÄ±lara gÃ¶ndermek istediÄin duyuruyu yaz:")
    elif data == "admin_channel_id_help":
        await query.message.reply_text("ð Grup/Kanal ID alma:\n\n1. Botu VIP grup/kanala yÃ¶netici yap.\n2. Mesaj gÃ¶nder, kullanÄ±cÄ± davet et ve kullanÄ±cÄ± yasakla yetkilerini aÃ§.\n3. VIP grup/kanal iÃ§ine dÃ¼z mesaj olarak sadece id yaz.\n4. Bot -100 ile baÅlayan Chat ID verir.")
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
            await query.message.reply_text("â Sadece owner admin ekleyebilir."); return
        context.user_data["mode"] = "add_admin"
        await query.message.reply_text("ð® Admin ekle:\n\nUserID | role\n\nRole: manager veya viewer\n\nÃÄ±kmak iÃ§in: iptal")
    elif data.startswith("admin_toggle_"):
        if not is_owner(user_id):
            await query.message.reply_text("â Yetkin yok."); return
        tid = int(data.split("_")[2])
        row = supabase.table("admins").select("*").eq("user_id", tid).single().execute().data
        if row:
            supabase.table("admins").update({"active": not bool(row.get("active"))}).eq("user_id", tid).execute()
        await log_event("admin_toggled", user_id, target_user_id=tid)
        await query.message.reply_text("â Admin durumu deÄiÅtirildi.")
    elif data == "admin_logs":
        await logs_message(query.message)
    elif data == "admin_export_sales":
        await export_sales_csv(query.message)
    elif data == "admin_maintenance":
        set_setting("maintenance", "off" if maintenance_on() else "on")
        await log_event("maintenance_toggled", user_id)
        await query.message.reply_text("â BakÄ±m modu deÄiÅtirildi.")
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
        await query.message.reply_text("â³ KaÃ§ gÃ¼nlÃ¼k VIP vermek istiyorsun? Ãrnek: 14")
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
        await query.message.reply_text("ð« Kara liste sebebini yaz:")
    elif data.startswith("unblacklist_"):
        tid = int(data.split("_")[1])
        supabase.table("blacklist").update({"active": False}).eq("user_id", tid).execute()
        await log_event("unblacklisted", user_id, target_user_id=tid)
        await query.message.reply_text("â KullanÄ±cÄ± kara listeden Ã§Ä±karÄ±ldÄ±.")

# =========================================================
# CHANNEL/PACKAGE ADMIN
# =========================================================

async def handle_channel_admin_button(query, context):
    if not can_manage(query.from_user.id):
        await query.message.reply_text("â Yetkin yok."); return
    data = query.data
    if data.startswith("ch_delete_"):
        cid = int(data.split("_")[2])
        supabase.table("channels").delete().eq("id", cid).execute()
        await log_event("channel_deleted", query.from_user.id, channel_id=cid)
        await query.message.reply_text("â Kanal silindi.")
    elif data.startswith("ch_toggle_"):
        cid = int(data.split("_")[2])
        row = supabase.table("channels").select("*").eq("id", cid).single().execute().data
        if row:
            supabase.table("channels").update({"active": not bool(row.get("active"))}).eq("id", cid).execute()
        await query.message.reply_text("â Kanal aktif/pasif deÄiÅtirildi.")
    else:
        parts = data.split("_")
        action, cid = parts[1], int(parts[2])
        maps = {
            "price": ("edit_price", "ð° Yeni fiyatÄ± yaz. Ãrnek: 3000"),
            "duration": ("edit_duration", "â³ Yeni sÃ¼reyi gÃ¼n olarak yaz. Ãrnek: 60"),
            "chat": ("edit_chat", "ð Yeni Chat ID yaz. Ãrnek: -1001234567890"),
            "description": ("edit_description", "ð Yeni aÃ§Ä±klamayÄ± yaz."),
            "photo": ("edit_photo", "ð¼ï¸ GÃ¶rsel URL yaz. BoÅ bÄ±rakmak iÃ§in - yaz."),
        }
        mode, prompt = maps[action]
        context.user_data["mode"] = mode
        context.user_data["channel_id"] = cid
        await query.message.reply_text(prompt)


async def handle_package_admin_button(query, context):
    if not can_manage(query.from_user.id):
        await query.message.reply_text("â Yetkin yok."); return
    data = query.data
    if data.startswith("pkg_delete_"):
        pid = int(data.split("_")[2])
        supabase.table("packages").delete().eq("id", pid).execute()
        await query.message.reply_text("â Paket silindi.")
    elif data.startswith("pkg_toggle_"):
        pid = int(data.split("_")[2])
        row = supabase.table("packages").select("*").eq("id", pid).single().execute().data
        if row:
            supabase.table("packages").update({"active": not bool(row.get("active"))}).eq("id", pid).execute()
        await query.message.reply_text("â Paket aktif/pasif deÄiÅtirildi.")


async def list_channels_manage(message):
    rows = supabase.table("channels").select("*").order("id").execute().data or []
    if not rows:
        await message.reply_text("ð¢ HenÃ¼z kanal yok."); return
    for ch in rows:
        status = "Aktif â" if ch.get("active") else "Pasif â"
        kb = [
            [InlineKeyboardButton("ð° Fiyat", callback_data=f"ch_price_{ch['id']}"), InlineKeyboardButton("â³ SÃ¼re", callback_data=f"ch_duration_{ch['id']}")],
            [InlineKeyboardButton("ð Chat ID", callback_data=f"ch_chat_{ch['id']}"), InlineKeyboardButton("ð AÃ§Ä±klama", callback_data=f"ch_description_{ch['id']}")],
            [InlineKeyboardButton("ð¼ï¸ GÃ¶rsel", callback_data=f"ch_photo_{ch['id']}"), InlineKeyboardButton("AÃ§/Kapat", callback_data=f"ch_toggle_{ch['id']}")],
            [InlineKeyboardButton("ðï¸ Sil", callback_data=f"ch_delete_{ch['id']}")],
        ]
        await message.reply_text(
            f"ð¢ Kanal\n\nID: {ch['id']}\nAd: {ch.get('name')}\nFiyat: {ch.get('price')} â­\nSÃ¼re: {ch.get('duration_days')} gÃ¼n\nChat ID: {ch.get('chat_id')}\nDurum: {status}\nAÃ§Ä±klama: {ch.get('description') or '-'}",
            reply_markup=InlineKeyboardMarkup(kb),
        )


async def list_packages_manage(message):
    rows = supabase.table("packages").select("*").order("id").execute().data or []
    if not rows:
        await message.reply_text("ð¦ HenÃ¼z paket yok."); return
    for p in rows:
        status = "Aktif â" if p.get("active") else "Pasif â"
        kb = [[InlineKeyboardButton("AÃ§/Kapat", callback_data=f"pkg_toggle_{p['id']}"), InlineKeyboardButton("ðï¸ Sil", callback_data=f"pkg_delete_{p['id']}")]]
        await message.reply_text(
            f"ð¦ Paket\n\nID: {p['id']}\nAd: {p.get('name')}\nFiyat: {p.get('price')} â­\nSÃ¼re: {p.get('duration_days')} gÃ¼n\nKanallar: {p.get('channel_ids')}\nDurum: {status}\nAÃ§Ä±klama: {p.get('description') or '-'}",
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
        await message.reply_text("â Kanal bulunamadÄ±."); return
    days = int(custom_days or ch.get("duration_days") or DEFAULT_DURATION_DAYS)
    start_date, end_date = await upsert_subscription(target_user_id, channel_id, days, 0)
    vip_link = await safe_create_and_store_link(context, target_user_id, channel_id, ch)
    supabase.table("sales").insert({"user_id": target_user_id, "username": "manual_admin", "channel_id": channel_id, "price": 0, "payment_payload": "manual_admin_grant", "coupon_code": None, "refund_status": "none"}).execute()
    await log_event("vip_granted", message.chat_id, target_user_id, channel_id, f"{days} gÃ¼n")
    if vip_link:
        try:
            await context.bot.send_message(target_user_id, f"ð Admin sana VIP eriÅim verdi!\n\nð¢ Kanal: {ch.get('name')}\nð Tek kullanÄ±mlÄ±k giriÅ linkin:\n{vip_link}\n\nBaÅlangÄ±Ã§: {start_date}\nBitiÅ: {end_date}")
            await message.reply_text("â VIP yetki verildi ve link kullanÄ±cÄ±ya gÃ¶nderildi.")
        except Exception:
            await message.reply_text(f"â VIP yetki verildi ama kullanÄ±cÄ±ya mesaj gÃ¶nderilemedi. Linki manuel gÃ¶nder:\n{vip_link}")
    else:
        await message.reply_text("â VIP yetki verildi ama davet linki Ã¼retilemedi. Botun grupta/kanalda admin olduÄundan emin ol.")


async def show_my_subscriptions(message, user_id):
    rows = supabase.table("subscriptions").select("*").eq("user_id", int(user_id)).eq("status", "active").execute().data or []
    if not rows:
        await message.reply_text("ð Aktif Ã¼yelik bulunamadÄ±."); return
    for sub in rows:
        ch = await get_channel(sub["channel_id"])
        name = ch.get("name") if ch else f"Kanal ID {sub['channel_id']}"
        kb = [
            [InlineKeyboardButton("â­ Bu Ã¼yeliÄi uzat", callback_data=f"buyc_{sub['channel_id']}")],
            [InlineKeyboardButton("ð Yeni link gÃ¶nder", callback_data=f"resend_{sub['id']}"), InlineKeyboardButton("â Ä°ptal talebi", callback_data=f"request_cancel_{sub['id']}")],
        ]
        await message.reply_text(f"ð Aktif Ã¼yeliÄin:\n\nð¢ Kanal: {name}\nBaÅlangÄ±Ã§: {sub.get('start_date')}\nBitiÅ: {sub.get('end_date')}\nDurum: {sub.get('status')}", reply_markup=InlineKeyboardMarkup(kb))


async def my_history(message, user_id):
    sales = supabase.table("sales").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute().data or []
    subs = supabase.table("subscriptions").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute().data or []
    text = "ð GeÃ§miÅin\n\n"
    text += "SatÄ±n almalar:\n" if sales else "SatÄ±n alma geÃ§miÅi yok.\n"
    for s in sales:
        ch = await get_channel(s.get("channel_id")) if s.get("channel_id") else None
        name = ch.get("name") if ch else f"Kanal ID {s.get('channel_id')}"
        text += f"- {name} | {s.get('price')} Stars | {s.get('created_at')}\n"
    text += "\nÃyelikler:\n" if subs else "\nÃyelik geÃ§miÅi yok."
    for sub in subs:
        ch = await get_channel(sub.get("channel_id"))
        name = ch.get("name") if ch else f"Kanal ID {sub.get('channel_id')}"
        text += f"- {name} | {sub.get('status')} | BitiÅ: {sub.get('end_date')}\n"
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
        await query.message.reply_text("ð§ Bot bakÄ±m modunda. SatÄ±n alma geÃ§ici olarak kapalÄ±."); return
    if await is_blacklisted(query.from_user.id) and not is_admin(query.from_user.id):
        await query.message.reply_text("ð« SatÄ±n alma yetkin kÄ±sÄ±tlandÄ±."); return
    channel_id = int(query.data.split("_")[1])
    ch = await get_channel(channel_id)
    if not ch or not ch.get("active"):
        await query.message.reply_text("â Kanal bulunamadÄ± veya pasif."); return
    price, coupon_code, _ = await calculate_price(query.from_user.id, int(ch.get("price") or 1), channel_id)
    payload = f"channel_{channel_id}_{price}_{coupon_code or 'NONE'}_{ab_variant(query.from_user.id)}"
    await create_checkout_intent(query.from_user, "channel", channel_id, price, payload)
    await context.bot.send_invoice(chat_id=query.message.chat_id, title=f"{ch.get('name')} VIP Ãyelik", description=f"{ch.get('duration_days') or DEFAULT_DURATION_DAYS} gÃ¼nlÃ¼k VIP Ã¼yelik.", payload=payload, provider_token="", currency="XTR", prices=[LabeledPrice(label=ch.get("name"), amount=price)])


async def handle_buy_package(query, context):
    package_id = int(query.data.split("_")[1])
    p = await get_package(package_id)
    if not p or not p.get("active"):
        await query.message.reply_text("â Paket bulunamadÄ± veya pasif."); return
    price, coupon_code, _ = await calculate_price(query.from_user.id, int(p.get("price") or 1), None)
    payload = f"package_{package_id}_{price}_{coupon_code or 'NONE'}_{ab_variant(query.from_user.id)}"
    await create_checkout_intent(query.from_user, "package", package_id, price, payload)
    await context.bot.send_invoice(chat_id=query.message.chat_id, title=f"{p.get('name')} VIP Paket", description=f"{p.get('duration_days') or DEFAULT_DURATION_DAYS} gÃ¼nlÃ¼k paket.", payload=payload, provider_token="", currency="XTR", prices=[LabeledPrice(label=p.get("name"), amount=price)])


async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = update.message.successful_payment.invoice_payload
    user = update.effective_user
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
            await update.message.reply_text("â Ãdeme alÄ±ndÄ± ama kanal bulunamadÄ±. Admin ile iletiÅime geÃ§."); return
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
            await update.message.reply_text("â Ãdeme alÄ±ndÄ± ama paket bulunamadÄ±. Admin ile iletiÅime geÃ§."); return
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
    await context.bot.send_message(OWNER_ID, f"â Yeni satÄ±Å!\n\nKullanÄ±cÄ±: @{safe_username(user) or 'yok'}\nUser ID: {user.id}\nÃrÃ¼n: {item_name}\nFiyat: {paid_price} Stars\nKupon: {coupon_code or 'Yok'}")
    if links:
        link_text = "\n\n".join([f"ð¢ {name}\nð {link}" for name, link in links])
        await update.message.reply_text(f"â Ãdeme baÅarÄ±lÄ±!\n\n{link_text}\n\nâ ï¸ Linkler {INVITE_LINK_EXPIRE_MINUTES} dakika geÃ§erlidir ve tek kullanÄ±mlÄ±ktÄ±r.")
    else:
        await update.message.reply_text("â Ãdeme baÅarÄ±lÄ± fakat otomatik davet linki Ã¼retilemedi. Admin ile iletiÅime geÃ§.")

# =========================================================
# REFERRALS / GIVEAWAY
# =========================================================

async def add_referral_points(referrer_id, referred_id, points, event_type):
    week = current_week_key()
    try:
        supabase.table("referral_events").insert({"referrer_id": referrer_id, "referred_id": referred_id, "points": points, "event_type": event_type, "week_key": week}).execute()
        row = await get_user_row(referrer_id)
        if row:
            supabase.table("users").update({"referral_points": int(row.get("referral_points") or 0) + points, "referral_total_points": int(row.get("referral_total_points") or 0) + points}).eq("user_id", referrer_id).execute()
    except Exception as e:
        logger.warning("Referans puan eklenemedi: %s", e)


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
        await context.bot.send_message(referrer_id, f"ð ReferansÄ±n ilk satÄ±n almayÄ± yaptÄ±! +{pts} puan ve +{bonus_days} gÃ¼n bonus kazandÄ±n.")
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
        await context.bot.send_message(user_id, f"ð Bonus VIP kazandÄ±n!\n\nð¢ {ch.get('name')}\nð {link or 'Link Ã¼retilemedi, admin ile iletiÅime geÃ§.'}")
    except Exception:
        pass
    return ch["id"]


async def referral_user_message(message, context, user_id):
    me = await context.bot.get_me()
    row = await get_user_row(user_id)
    points = int(row.get("referral_points") or 0) if row else 0
    total = int(row.get("referral_total_points") or 0) if row else 0
    link = f"https://t.me/{me.username}?start=ref_{user_id}"
    kb = [
        [InlineKeyboardButton("ð 3 puan = 1 gÃ¼n", callback_data="redeem_3_1")],
        [InlineKeyboardButton("ð¥ 10 puan = 7 gÃ¼n", callback_data="redeem_10_7")],
        [InlineKeyboardButton("ð 25 puan = 30 gÃ¼n", callback_data="redeem_25_30")],
    ]
    await message.reply_text(f"ð Davet Et Kazan\n\nSenin linkin:\n{link}\n\nMevcut puan: {points}\nToplam puan: {total}\n\n1 yeni kullanÄ±cÄ± = +{get_referral_invite_points()} puan\nÄ°lk satÄ±n alma = +{get_referral_purchase_points()} puan + bonus gÃ¼n", reply_markup=InlineKeyboardMarkup(kb))


async def redeem_referral_reward(query, context):
    _, cost, days = query.data.split("_")
    cost, days = int(cost), int(days)
    row = await get_user_row(query.from_user.id)
    points = int(row.get("referral_points") or 0) if row else 0
    if points < cost:
        await query.message.reply_text(f"â Yetersiz puan. Gerekli: {cost}, mevcut: {points}"); return
    supabase.table("users").update({"referral_points": points - cost}).eq("user_id", query.from_user.id).execute()
    await extend_first_active_or_default_subscription(context, query.from_user.id, days)
    await log_event("referral_reward_redeemed", query.from_user.id, query.from_user.id, details=f"{cost} puan -> {days} gÃ¼n")
    await query.message.reply_text(f"â {cost} puan harcandÄ±, {days} gÃ¼n VIP Ã¶dÃ¼l uygulandÄ±.")


async def leaderboard_message(message):
    rows = supabase.table("users").select("*").order("referral_total_points", desc=True).limit(10).execute().data or []
    if not rows:
        await message.reply_text("ð HenÃ¼z liderlik verisi yok."); return
    text = "ð Liderlik Tablosu\n\n"
    for i, u in enumerate(rows, start=1):
        text += f"{i}. @{u.get('username') or u.get('user_id')} â {u.get('referral_total_points') or 0} puan\n"
    await message.reply_text(text)


async def referrals_admin_message(message):
    events = supabase.table("referral_events").select("*").execute().data or []
    joins = len([e for e in events if e.get("event_type") == "join"])
    purchases = len([e for e in events if e.get("event_type") == "purchase"])
    await message.reply_text(f"ð Referans Paneli\n\nToplam referans kayÄ±t: {joins}\nSatÄ±n almaya dÃ¶nen: {purchases}\nToplam puan olayÄ±: {len(events)}")
    await leaderboard_message(message)


async def giveaway_user_message(message):
    week = current_week_key()
    rows = supabase.table("referral_events").select("*").eq("week_key", week).execute().data or []
    total_points = sum(int(r.get("points") or 0) for r in rows)
    participants = len(set(r.get("referrer_id") for r in rows if r.get("referrer_id")))
    await message.reply_text(f"ð HaftalÄ±k ÃekiliÅ\n\nBu hafta katÄ±lÄ±mcÄ±: {participants}\nToplam Ã§ekiliÅ hakkÄ±: {total_points}\n\nHer referans puanÄ± Ã§ekiliÅ hakkÄ±dÄ±r. HaftanÄ±n kazananÄ± {get_weekly_winner_prize_days()} gÃ¼n VIP alÄ±r.")


async def giveaway_admin_message(message):
    await giveaway_user_message(message)
    kb = [[InlineKeyboardButton("ð² ÃekiliÅi Åimdi Yap", callback_data="giveaway_run")]]
    await message.reply_text("Admin Ã§ekiliÅ paneli", reply_markup=InlineKeyboardMarkup(kb))


async def run_giveaway(message, context, week_key, manual=False):
    rows = supabase.table("referral_events").select("*").eq("week_key", week_key).execute().data or []
    tickets = []
    for r in rows:
        rid = r.get("referrer_id")
        pts = int(r.get("points") or 0)
        if rid:
            tickets.extend([int(rid)] * max(0, pts))
    if not tickets:
        await message.reply_text("ð Bu hafta Ã§ekiliÅ hakkÄ± yok.")
        return
    winner = random.choice(tickets)
    days = get_weekly_winner_prize_days()
    cid = await extend_first_active_or_default_subscription(context, winner, days)
    supabase.table("giveaway_winners").insert({"week_key": week_key, "user_id": winner, "prize_days": days, "channel_id": cid}).execute()
    await log_event("giveaway_winner", None, winner, cid, f"week={week_key}, days={days}")
    try:
        await context.bot.send_message(winner, f"ð HaftalÄ±k Ã§ekiliÅi kazandÄ±n! {days} gÃ¼n VIP Ã¶dÃ¼l uygulandÄ±.")
    except Exception:
        pass
    await message.reply_text(f"ð Kazanan: {winner}\nÃdÃ¼l: {days} gÃ¼n VIP")

# =========================================================
# USER SUPPORT / FAQ / CANCEL
# =========================================================

async def support_menu(message):
    kb = [
        [InlineKeyboardButton("ð Link Ã§alÄ±ÅmÄ±yor", callback_data="support_auto_link")],
        [InlineKeyboardButton("â­ Ãdeme yaptÄ±m", callback_data="support_auto_payment")],
        [InlineKeyboardButton("ð Ãyelik tarihi", callback_data="support_auto_date")],
        [InlineKeyboardButton("ðï¸ Kupon Ã§alÄ±ÅmÄ±yor", callback_data="support_auto_coupon")],
        [InlineKeyboardButton("ð¤ Admin ile konuÅ", callback_data="support_auto_admin")],
    ]
    await message.reply_text("ð Sorunun ne?", reply_markup=InlineKeyboardMarkup(kb))


async def support_auto_answer(message, key):
    answers = {
        "link": "ð ÃyeliÄim bÃ¶lÃ¼mÃ¼nden Yeni link gÃ¶nder butonuna bas. Link yine Ã§alÄ±Åmazsa destek mesajÄ± yaz.",
        "payment": "â­ Ãdeme yaptÄ±ysan ÃyeliÄim bÃ¶lÃ¼mÃ¼nde aktif Ã¼yeliÄin gÃ¶rÃ¼nmeli. GÃ¶rÃ¼nmÃ¼yorsa destek mesajÄ± yaz.",
        "date": "ð ÃyeliÄim bÃ¶lÃ¼mÃ¼nde baÅlangÄ±Ã§ ve bitiÅ tarihini gÃ¶rebilirsin.",
        "coupon": "ðï¸ Kupon kodunu Kupon Gir bÃ¶lÃ¼mÃ¼nden yaz. BazÄ± kuponlar sadece belirli kanal iÃ§in geÃ§erli olabilir.",
        "admin": "ð¤ Sorununu tek mesaj olarak yaz; adminâe iletilecek.",
    }
    if key == "admin":
        # mode is per user, but we only have message here. A new text will go to menu without mode. Ask user to use Destek menu.
        await message.reply_text("ð¤ Adminâe yazmak iÃ§in ana menÃ¼de ð Destek butonuna basÄ±p mesajÄ±nÄ± yaz.")
    else:
        await message.reply_text(answers.get(key, "Destek iÃ§in ð Destek butonunu kullan."))


async def faq_user_message(message):
    rows = supabase.table("faq").select("*").eq("active", True).order("id").execute().data or []
    if not rows:
        await message.reply_text("â HenÃ¼z SSS eklenmedi."); return
    kb = [[InlineKeyboardButton(row.get("question") or f"SSS {row['id']}", callback_data=f"faq_view_{row['id']}")] for row in rows[:40]]
    await message.reply_text("â SÄ±k Sorulan Sorular", reply_markup=InlineKeyboardMarkup(kb))


async def faq_answer(message, faq_id):
    row = supabase.table("faq").select("*").eq("id", faq_id).single().execute().data
    if not row:
        await message.reply_text("â SSS bulunamadÄ±."); return
    await message.reply_text(f"â {row.get('question')}\n\n{row.get('answer')}")


async def faq_admin_message(message):
    rows = supabase.table("faq").select("*").order("id", desc=True).execute().data or []
    await message.reply_text("â SSS YÃ¶netimi", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("â SSS Ekle", callback_data="faq_add")]]))
    for row in rows[:30]:
        status = "Aktif â" if row.get("active") else "Pasif â"
        await message.reply_text(f"ID: {row['id']}\nSoru: {row.get('question')}\nDurum: {status}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("AÃ§/Kapat", callback_data=f"faq_toggle_{row['id']}")]]))


async def create_cancel_request(update, context):
    rows = supabase.table("subscriptions").select("*").eq("user_id", update.effective_user.id).eq("status", "active").execute().data or []
    if not rows:
        await update.message.reply_text("â Aktif Ã¼yeliÄin olmadÄ±ÄÄ± iÃ§in iptal talebi oluÅturulamaz."); return
    for sub in rows:
        await create_cancel_request_for_sub(update.message, context, sub)


async def request_cancel_from_button(query, context):
    sub_id = int(query.data.split("_")[2])
    sub = await get_subscription(sub_id)
    if not sub or int(sub.get("user_id")) != query.from_user.id or sub.get("status") != "active":
        await query.message.reply_text("â Aktif Ã¼yelik bulunamadÄ±."); return
    await create_cancel_request_for_sub(query.message, context, sub)


async def create_cancel_request_for_sub(message, context, sub):
    existing = supabase.table("cancel_requests").select("*").eq("user_id", sub["user_id"]).eq("channel_id", sub["channel_id"]).eq("status", "pending").execute().data or []
    if existing:
        await message.reply_text("â ï¸ Zaten bekleyen iptal talebin var."); return
    supabase.table("cancel_requests").insert({"user_id": sub["user_id"], "channel_id": sub["channel_id"], "status": "pending"}).execute()
    await log_event("cancel_requested", sub["user_id"], sub["user_id"], sub["channel_id"])
    await message.reply_text("â Ä°ptal talebin admin onayÄ±na gÃ¶nderildi.")
    await context.bot.send_message(OWNER_ID, f"â Yeni iptal talebi!\n\nKullanÄ±cÄ± ID: {sub['user_id']}\nKanal ID: {sub['channel_id']}")

# =========================================================
# ADMIN LISTS / REPORTS / USER DETAILS
# =========================================================

async def show_users_for_grant(message):
    rows = supabase.table("users").select("*").order("id", desc=True).limit(20).execute().data or []
    if not rows:
        await message.reply_text("ð¥ HenÃ¼z kullanÄ±cÄ± yok."); return
    for u in rows:
        username = f"@{u.get('username')}" if u.get("username") else "username yok"
        kb = [[InlineKeyboardButton("ðï¸ Detay", callback_data=f"userdetail_{u['user_id']}")], [InlineKeyboardButton("ð VIP Ver", callback_data=f"grant_user_{u['user_id']}")]]
        await message.reply_text(f"ð¤ {username}\nID: {u['user_id']}", reply_markup=InlineKeyboardMarkup(kb))


async def show_channels_for_grant(message, target_user_id):
    rows = supabase.table("channels").select("*").eq("active", True).order("id").execute().data or []
    if not rows:
        await message.reply_text("ð¢ Ãnce kanal eklemelisin."); return
    for ch in rows:
        await message.reply_text(f"ð¢ Kanal seÃ§\n\nAd: {ch.get('name')}\nFiyat: {ch.get('price')} â­\nSÃ¼re: {ch.get('duration_days')} gÃ¼n", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"ð {ch.get('name')} seÃ§", callback_data=f"grant_channel_{target_user_id}_{ch['id']}")]]))


async def show_grant_duration(message, target_user_id, channel_id):
    kb = [[InlineKeyboardButton("ð 7 GÃ¼n", callback_data=f"grant_days_{target_user_id}_{channel_id}_7"), InlineKeyboardButton("ð 30 GÃ¼n", callback_data=f"grant_days_{target_user_id}_{channel_id}_30")], [InlineKeyboardButton("ð 90 GÃ¼n", callback_data=f"grant_days_{target_user_id}_{channel_id}_90"), InlineKeyboardButton("âï¸ Ãzel SÃ¼re", callback_data=f"grant_custom_{target_user_id}_{channel_id}")]]
    await message.reply_text("â³ VIP sÃ¼resini seÃ§:", reply_markup=InlineKeyboardMarkup(kb))


async def search_user(message, query):
    q = query.replace("@", "").strip()
    if q.isdigit():
        rows = supabase.table("users").select("*").eq("user_id", int(q)).execute().data or []
    else:
        rows = supabase.table("users").select("*").ilike("username", f"%{q}%").execute().data or []
    if not rows:
        await message.reply_text("â KullanÄ±cÄ± bulunamadÄ±."); return
    for row in rows[:5]:
        await show_user_detail(message, row)


async def show_user_detail_by_id(message, user_id):
    row = await get_user_row(user_id)
    if not row:
        await message.reply_text("â KullanÄ±cÄ± bulunamadÄ±."); return
    await show_user_detail(message, row)


async def show_user_detail(message, user_row):
    user_id = user_row["user_id"]
    username = f"@{user_row.get('username')}" if user_row.get("username") else "username yok"
    blacklisted = await is_blacklisted(user_id)
    kb_top = [[InlineKeyboardButton("ð VIP Ver", callback_data=f"grant_user_{user_id}")], [InlineKeyboardButton("ð« Kara Listeye Al", callback_data=f"blacklist_{user_id}")] if not blacklisted else [InlineKeyboardButton("â Kara Listeden ÃÄ±kar", callback_data=f"unblacklist_{user_id}")]]
    await message.reply_text(f"ð¤ KullanÄ±cÄ± DetayÄ±\n\nID: {user_id}\nUsername: {username}\nKara liste: {'Evet' if blacklisted else 'HayÄ±r'}\nReferans puan: {user_row.get('referral_points') or 0}", reply_markup=InlineKeyboardMarkup(kb_top))
    subs = supabase.table("subscriptions").select("*").eq("user_id", user_id).order("id", desc=True).execute().data or []
    if not subs:
        await message.reply_text("Ãyelik yok."); return
    for sub in subs:
        ch = await get_channel(sub.get("channel_id"))
        name = ch.get("name") if ch else f"Kanal ID {sub.get('channel_id')}"
        kb = [[InlineKeyboardButton("â Ä°ptal Et", callback_data=f"usub_cancel_{sub['id']}"), InlineKeyboardButton("ð Link GÃ¶nder", callback_data=f"usub_link_{sub['id']}")], [InlineKeyboardButton("+7 gÃ¼n", callback_data=f"usub_extend_{sub['id']}_7"), InlineKeyboardButton("+30 gÃ¼n", callback_data=f"usub_extend_{sub['id']}_30")]]
        await message.reply_text(f"ð¢ {name}\nDurum: {sub.get('status')}\nBitiÅ: {sub.get('end_date')}", reply_markup=InlineKeyboardMarkup(kb))


async def users_message(message):
    await show_users_for_grant(message)


async def sales_message(message):
    rows = supabase.table("sales").select("*").order("id", desc=True).limit(20).execute().data or []
    if not rows:
        await message.reply_text("ð HenÃ¼z satÄ±Å yok."); return
    for s in rows:
        refund = s.get("refund_status") or "none"
        kb = [] if refund == "refunded" else [[InlineKeyboardButton("ð¸ Ä°ade Ä°Åaretle", callback_data=f"refund_sale_{s['id']}")]]
        await message.reply_text(f"ð SatÄ±Å\n\nID: {s['id']}\nKullanÄ±cÄ±: @{s.get('username') or 'yok'}\nUser ID: {s.get('user_id')}\nKanal ID: {s.get('channel_id')}\nPaket ID: {s.get('package_id') or '-'}\nFiyat: {s.get('price')} â­\nKupon: {s.get('coupon_code') or 'Yok'}\nÄ°ade: {refund}\nTarih: {s.get('created_at')}", reply_markup=InlineKeyboardMarkup(kb) if kb else None)


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
    await message.reply_text(f"ð SatÄ±Å Raporu\n\nBugÃ¼n satÄ±Å: {tc}\nBugÃ¼n Stars: {ts}\n\nBu ay satÄ±Å: {mc}\nBu ay Stars: {ms}\n\nToplam satÄ±Å: {totalc}\nToplam Stars: {totals}\nÄ°ade iÅaretli satÄ±Å: {refundc}")


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
        await message.reply_text("ð¢ HenÃ¼z kanal satÄ±ÅÄ± yok."); return
    text = "ð¢ Kanal BazlÄ± Ä°statistik\n\n"
    for cid, val in stats.items():
        ch = await get_channel(cid)
        name = ch.get("name") if ch else f"Kanal ID {cid}"
        text += f"ð¢ {name}\nSatÄ±Å: {val['count']}\nStars: {val['stars']}\n\n"
    await message.reply_text(text)


async def abandoned_message(message):
    rows = supabase.table("checkout_intents").select("*").eq("status", "started").order("id", desc=True).limit(20).execute().data or []
    if not rows:
        await message.reply_text("ð YarÄ±m kalan Ã¶deme yok."); return
    text = "ð YarÄ±m Kalan Ãdemeler\n\n"
    for r in rows:
        text += f"ID: {r['id']} | User: {r.get('user_id')} | {r.get('item_type')} {r.get('item_id')} | {r.get('price')} â­ | HatÄ±rlatma: {r.get('reminder_sent')}\n"
    await message.reply_text(text[:3900])


async def coupons_message(message):
    rows = supabase.table("coupons").select("*").order("id", desc=True).execute().data or []
    await message.reply_text("ðï¸ Kuponlar", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("â Kupon OluÅtur", callback_data="coupon_add")]]))
    if not rows:
        await message.reply_text("HenÃ¼z kupon yok."); return
    for c in rows[:30]:
        status = "Aktif â" if c.get("active") else "Pasif â"
        ch_text = f"Kanal ID: {c.get('channel_id')}" if c.get("channel_id") else "TÃ¼m kanallar"
        await message.reply_text(f"Kupon: {c.get('code')}\nYÃ¼zde: %{c.get('discount_percent') or 0}\nStars indirim: {c.get('discount_stars') or 0}\nGeÃ§erli: {ch_text}\nKullanÄ±m: {c.get('used_count') or 0}/{c.get('max_uses') or 'â'}\nDurum: {status}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("AÃ§/Kapat", callback_data=f"coupon_toggle_{c['id']}")]]))


async def campaign_message(message):
    text = f"ð¥ Kampanya\n\nDurum: {'Aktif' if campaign_active() else 'KapalÄ±'}\nÄ°ndirim: %{get_setting('campaign_percent', '0')}\nBitiÅ: {get_setting('campaign_end', '') or '-'}"
    kb = [[InlineKeyboardButton("ð¥ BaÅlat", callback_data="campaign_start"), InlineKeyboardButton("â Kapat", callback_data="campaign_stop")]]
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def support_requests_message(message):
    rows = supabase.table("support_requests").select("*").eq("status", "open").order("id", desc=True).limit(20).execute().data or []
    if not rows:
        await message.reply_text("ð AÃ§Ä±k destek talebi yok."); return
    for r in rows:
        await message.reply_text(f"ð Destek Talebi\n\nID: {r['id']}\nKullanÄ±cÄ±: @{r.get('username') or 'yok'}\nUser ID: {r.get('user_id')}\nMesaj:\n{r.get('message')}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("â Kapat", callback_data=f"support_close_{r['id']}")]]))


async def cancel_requests_message(message):
    rows = supabase.table("cancel_requests").select("*").eq("status", "pending").execute().data or []
    if not rows:
        await message.reply_text("â Bekleyen iptal talebi yok."); return
    for r in rows:
        kb = [[InlineKeyboardButton("â Onayla", callback_data=f"cancel_ok_{r['id']}"), InlineKeyboardButton("â Reddet", callback_data=f"cancel_no_{r['id']}")]]
        await message.reply_text(f"â Ä°ptal Talebi\n\nTalep ID: {r['id']}\nKullanÄ±cÄ± ID: {r.get('user_id')}\nKanal ID: {r.get('channel_id')}", reply_markup=InlineKeyboardMarkup(kb))


async def blacklist_message(message):
    rows = supabase.table("blacklist").select("*").eq("active", True).order("id", desc=True).execute().data or []
    if not rows:
        await message.reply_text("ð« Kara listede aktif kullanÄ±cÄ± yok."); return
    for b in rows:
        await message.reply_text(f"ð« User ID: {b.get('user_id')}\nSebep: {b.get('reason') or '-'}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("â ÃÄ±kar", callback_data=f"unblacklist_{b['user_id']}")]]))


async def admins_message(message):
    rows = supabase.table("admins").select("*").order("id", desc=True).execute().data or []
    await message.reply_text("ð® Adminler", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("â Admin Ekle", callback_data="admin_add_admin")]]))
    await message.reply_text(f"Owner: {OWNER_ID}")
    for a in rows:
        status = "Aktif â" if a.get("active") else "Pasif â"
        await message.reply_text(f"User ID: {a.get('user_id')}\nRole: {a.get('role')}\nDurum: {status}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("AÃ§/Kapat", callback_data=f"admin_toggle_{a['user_id']}")]]))


async def logs_message(message):
    rows = supabase.table("logs").select("*").order("id", desc=True).limit(30).execute().data or []
    if not rows:
        await message.reply_text("ð HenÃ¼z log yok."); return
    text = "ð Son Ä°Ålemler\n\n"
    for l in rows:
        text += f"ID: {l['id']}\nÄ°Ålem: {l.get('action')}\nActor: {l.get('actor_id')}\nTarget: {l.get('target_user_id')}\nKanal: {l.get('channel_id')}\nDetay: {l.get('details') or '-'}\nTarih: {l.get('created_at')}\n\n"
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
    await message.reply_document(document=file_data, filename="sales.csv", caption="ð SatÄ±Å CSV")

# =========================================================
# ADMIN ACTIONS
# =========================================================

async def handle_cancel_admin(query, context):
    if not can_manage(query.from_user.id):
        await query.message.reply_text("â Yetkin yok."); return
    parts = query.data.split("_")
    action, rid = parts[1], int(parts[2])
    req = supabase.table("cancel_requests").select("*").eq("id", rid).single().execute().data
    if not req:
        await query.message.reply_text("â Talep bulunamadÄ±."); return
    if action == "ok":
        supabase.table("cancel_requests").update({"status": "approved"}).eq("id", rid).execute()
        supabase.table("subscriptions").update({"status": "cancelled"}).eq("user_id", req["user_id"]).eq("channel_id", req["channel_id"]).execute()
        ch = await get_channel(req["channel_id"])
        if ch:
            await remove_user_from_channel(context, ch, req["user_id"])
        await log_event("cancel_approved", query.from_user.id, req["user_id"], req["channel_id"])
        await query.message.reply_text("â Ä°ptal talebi onaylandÄ±.")
    else:
        supabase.table("cancel_requests").update({"status": "rejected"}).eq("id", rid).execute()
        await log_event("cancel_rejected", query.from_user.id, req["user_id"], req["channel_id"])
        await query.message.reply_text("â Ä°ptal talebi reddedildi.")


async def admin_cancel_subscription(message, context, sub_id):
    sub = await get_subscription(sub_id)
    if not sub:
        await message.reply_text("â Ãyelik bulunamadÄ±."); return
    ch = await get_channel(sub["channel_id"])
    supabase.table("subscriptions").update({"status": "cancelled"}).eq("id", sub_id).execute()
    if ch:
        await remove_user_from_channel(context, ch, sub["user_id"])
    await log_event("subscription_cancelled_by_admin", message.chat_id, sub["user_id"], sub["channel_id"])
    await message.reply_text("â Ãyelik iptal edildi.")


async def admin_resend_link_for_subscription(message, context, sub_id):
    sub = await get_subscription(sub_id)
    if not sub:
        await message.reply_text("â Ãyelik bulunamadÄ±."); return
    ch = await get_channel(sub["channel_id"])
    link = await safe_create_and_store_link(context, sub["user_id"], sub["channel_id"], ch)
    if link:
        try:
            await context.bot.send_message(sub["user_id"], f"ð Yeni VIP giriÅ linkin:\n{link}")
            await message.reply_text("â Yeni link kullanÄ±cÄ±ya gÃ¶nderildi.")
        except Exception:
            await message.reply_text(f"â Link Ã¼retildi ama gÃ¶nderilemedi. Manuel gÃ¶nder:\n{link}")
    else:
        await message.reply_text("â Link Ã¼retilemedi.")


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
    await message.reply_text(f"â Ãyelik {days} gÃ¼n uzatÄ±ldÄ±." if ok else "â Ãyelik bulunamadÄ±.")


async def mark_refund(message, admin_id, sale_id):
    sale = supabase.table("sales").select("*").eq("id", sale_id).single().execute().data
    if not sale:
        await message.reply_text("â SatÄ±Å bulunamadÄ±."); return
    supabase.table("sales").update({"refund_status": "refunded", "refunded_at": now_utc().isoformat(), "refunded_by": admin_id}).eq("id", sale_id).execute()
    await log_event("refund_marked", admin_id, sale.get("user_id"), sale.get("channel_id"), f"sale_id={sale_id}")
    await message.reply_text("ð¸ SatÄ±Å iade edildi olarak iÅaretlendi. Not: Bu sadece sistem iÃ§i iÅarettir; Telegram Stars iadesini otomatik yapmaz.")


async def resend_invite_link(query, context):
    sub_id = int(query.data.split("_")[1])
    sub = await get_subscription(sub_id)
    if not sub or int(sub.get("user_id")) != query.from_user.id or sub.get("status") != "active":
        await query.message.reply_text("â Aktif Ã¼yelik bulunamadÄ±."); return
    ch = await get_channel(sub["channel_id"])
    link = await safe_create_and_store_link(context, sub["user_id"], sub["channel_id"], ch)
    await query.message.reply_text(f"ð Yeni tek kullanÄ±mlÄ±k linkin:\n{link}" if link else "â Link Ã¼retilemedi. Admin ile iletiÅime geÃ§.")


async def broadcast_message(message, context, text):
    rows = supabase.table("users").select("*").execute().data or []
    sent = failed = 0
    await message.reply_text(f"ð£ Duyuru baÅladÄ±. KullanÄ±cÄ± sayÄ±sÄ±: {len(rows)}")
    for u in rows:
        try:
            if not await is_blacklisted(u["user_id"]):
                await context.bot.send_message(u["user_id"], text)
                sent += 1
            await asyncio.sleep(BROADCAST_DELAY_SECONDS)
        except Exception:
            failed += 1
    await log_event("broadcast_sent", message.chat_id, details=f"sent={sent}, failed={failed}")
    await message.reply_text(f"â Duyuru bitti. GÃ¶nderildi: {sent}, Hata: {failed}")

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
                await context.bot.send_message(sub["user_id"], "â VIP Ã¼yelik sÃ¼ren bitti. 48 saat iÃ§inde yenilersen WINBACK20 kuponuyla %20 indirim alÄ±rsÄ±n.")
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
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("â­ ÃyeliÄi Uzat", callback_data=f"buyc_{sub['channel_id']}")]])
        if remaining <= timedelta(days=1) and not sub.get("warn_1d_sent"):
            try:
                await context.bot.send_message(sub["user_id"], f"â³ VIP Ã¼yeliÄin 1 gÃ¼n iÃ§inde bitiyor.\n\nð¢ Kanal: {name}\nÅimdi yenilersen erken yenileme bonusu kazanÄ±rsÄ±n.", reply_markup=kb)
                supabase.table("subscriptions").update({"warn_1d_sent": True}).eq("id", sub["id"]).execute()
            except Exception:
                pass
        elif remaining <= timedelta(days=3) and not sub.get("warn_3d_sent"):
            try:
                await context.bot.send_message(sub["user_id"], f"â³ VIP Ã¼yeliÄin 3 gÃ¼n iÃ§inde bitiyor.\n\nð¢ Kanal: {name}\nÅimdi yenilersen erken yenileme bonusu kazanÄ±rsÄ±n.", reply_markup=kb)
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
            await context.bot.send_message(row["user_id"], "ð Ãdemeyi baÅlatmÄ±ÅtÄ±n ama tamamlanmamÄ±Å gÃ¶rÃ¼nÃ¼yor. Devam etmek istersen aÅaÄÄ±daki butona basabilirsin.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("â­ Ãdemeye Devam Et", callback_data=callback)]]))
            supabase.table("checkout_intents").update({"reminder_sent": True}).eq("id", row["id"]).execute()
        except Exception:
            pass


async def daily_report_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_message(OWNER_ID, f"ð GÃ¼nlÃ¼k Rapor\n\n{await admin_dashboard_text()}")
    except Exception:
        pass


async def weekly_giveaway_job(context: ContextTypes.DEFAULT_TYPE):
    if now_utc().weekday() != 0:  # Monday
        return
    week = previous_week_key()
    already = supabase.table("giveaway_winners").select("*").eq("week_key", week).execute().data or []
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
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))
app.job_queue.run_repeating(expire_old_subscriptions_job, interval=3600, first=30)
app.job_queue.run_repeating(warning_job, interval=21600, first=60)
app.job_queue.run_repeating(abandoned_checkout_job, interval=1800, first=300)
app.job_queue.run_repeating(daily_report_job, interval=86400, first=120)
app.job_queue.run_repeating(weekly_giveaway_job, interval=86400, first=600)
print("Pasha VIP V6 bot Ã§alÄ±ÅÄ±yor...")
app.run_polling()
