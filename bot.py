import os
import io
import csv
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

TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OWNER_ID = 957422314

DEFAULT_DURATION_DAYS = 30
INVITE_LINK_EXPIRE_MINUTES = 30
BROADCAST_DELAY_SECONDS = 0.05
ABANDONED_REMINDER_HOURS = 2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pasha-vip")

if not TOKEN:
    raise ValueError("BOT_TOKEN Railway Variables içinde yok.")
if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL Railway Variables içinde yok.")
if not SUPABASE_KEY:
    raise ValueError("SUPABASE_KEY Railway Variables içinde yok.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["📢 VIP Kanallar"],
        ["📅 Üyeliğim", "📜 Geçmişim"],
        ["❌ İptal Talebi", "🎟️ Kupon Gir"],
        ["🎁 Referans", "❓ SSS"],
        ["🆘 Destek", "ℹ️ Yardım"],
    ],
    resize_keyboard=True,
)

ADMIN_MENU = ReplyKeyboardMarkup(
    [
        ["👑 Admin Panel"],
        ["📢 VIP Kanallar"],
        ["📅 Üyeliğim", "📜 Geçmişim"],
        ["❌ İptal Talebi", "🎟️ Kupon Gir"],
        ["🎁 Referans", "❓ SSS"],
        ["🆘 Destek", "ℹ️ Yardım"],
    ],
    resize_keyboard=True,
)

# ---------- helpers ----------

def now_utc():
    return datetime.utcnow()


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def safe_username(user):
    return user.username if user and user.username else None


def is_owner(user_id):
    return int(user_id) == OWNER_ID


def get_admin_role(user_id):
    if is_owner(user_id):
        return "owner"
    try:
        res = supabase.table("admins").select("*").eq("user_id", int(user_id)).eq("active", True).execute()
        if res.data:
            return res.data[0].get("role") or "manager"
    except Exception as e:
        logger.error("Admin rol okunamadı: %s", e)
    return None


def is_admin(user_id):
    return get_admin_role(user_id) is not None


def can_manage(user_id):
    return get_admin_role(user_id) in ["owner", "manager"]


def can_view_reports(user_id):
    return get_admin_role(user_id) in ["owner", "manager", "viewer"]


def get_setting(key, default=None):
    try:
        res = supabase.table("settings").select("*").eq("key", key).execute()
        if res.data:
            return res.data[0].get("value")
    except Exception:
        pass
    return default


def set_setting(key, value):
    existing = supabase.table("settings").select("*").eq("key", key).execute()
    if existing.data:
        supabase.table("settings").update({"value": str(value)}).eq("key", key).execute()
    else:
        supabase.table("settings").insert({"key": key, "value": str(value)}).execute()


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
    try:
        return int(get_setting("campaign_percent", "0") or 0)
    except Exception:
        return 0


def get_referral_bonus_days():
    try:
        return int(get_setting("referral_bonus_days", "3") or 3)
    except Exception:
        return 3


def get_renewal_bonus_days():
    try:
        return int(get_setting("renewal_bonus_days", "3") or 3)
    except Exception:
        return 3


def ab_variant(user_id):
    return "A" if int(user_id) % 2 == 0 else "B"


def parse_channel_ids(text):
    if not text:
        return []
    return [int(x.strip()) for x in str(text).split(",") if x.strip().isdigit()]


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
        logger.error("Log yazılamadı: %s", e)


async def get_user_row(user_id):
    try:
        res = supabase.table("users").select("*").eq("user_id", int(user_id)).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None


async def save_user(user, referrer_id=None):
    if not user:
        return
    existing = supabase.table("users").select("*").eq("user_id", user.id).execute()
    payload = {"username": safe_username(user)}
    if referrer_id and int(referrer_id) != int(user.id):
        payload["referrer_id"] = int(referrer_id)
    if existing.data:
        # referrer yalnızca daha önce yoksa yazılsın
        if referrer_id and existing.data[0].get("referrer_id"):
            payload.pop("referrer_id", None)
        supabase.table("users").update(payload).eq("user_id", user.id).execute()
    else:
        payload.update(
            {
                "user_id": user.id,
                "accepted_terms": False,
                "active_coupon": None,
                "referral_bonus_given": False,
            }
        )
        supabase.table("users").insert(payload).execute()


async def user_accepted_terms(user_id):
    row = await get_user_row(user_id)
    return bool(row and row.get("accepted_terms"))


async def is_blacklisted(user_id):
    try:
        res = supabase.table("blacklist").select("*").eq("user_id", int(user_id)).eq("active", True).execute()
        return bool(res.data)
    except Exception:
        return False


async def get_channel(channel_id):
    try:
        res = supabase.table("channels").select("*").eq("id", int(channel_id)).single().execute()
        return res.data
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


async def create_one_time_invite_link(context, ch, user_id):
    chat_id_raw = ch.get("chat_id")
    if not chat_id_raw:
        return None
    expire_ts = int((now_utc() + timedelta(minutes=INVITE_LINK_EXPIRE_MINUTES)).timestamp())
    invite = await context.bot.create_chat_invite_link(
        chat_id=int(chat_id_raw),
        name=f"{ch['name']} - {user_id}",
        expire_date=expire_ts,
        member_limit=1,
    )
    return invite.invite_link


async def remove_user_from_channel(context, ch, user_id):
    chat_id_raw = ch.get("chat_id")
    if not chat_id_raw:
        return False
    try:
        await context.bot.ban_chat_member(chat_id=int(chat_id_raw), user_id=int(user_id))
        await context.bot.unban_chat_member(chat_id=int(chat_id_raw), user_id=int(user_id), only_if_banned=True)
        return True
    except Exception as e:
        logger.error("Kanaldan çıkarma hatası: %s", e)
        return False


async def show_terms(message):
    kb = [[InlineKeyboardButton("✅ Kabul Ediyorum", callback_data="accept_terms")]]
    await message.reply_text(
        "⚠️ Kurallar ve Kullanım Onayı\n\n"
        "Bu bot üzerinden verilen VIP erişimler yalnızca yasal, rızaya dayalı ve kurallara uygun içerikler içindir.\n\n"
        "Devam ederek kuralları kabul etmiş olursun.",
        reply_markup=InlineKeyboardMarkup(kb),
    )

# ---------- start / channel id ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referrer_id = None
    if context.args:
        raw = context.args[0]
        if raw.startswith("ref") and raw[3:].isdigit():
            referrer_id = int(raw[3:])
    await save_user(user, referrer_id=referrer_id)
    if await is_blacklisted(user.id) and not is_admin(user.id):
        await update.message.reply_text("🚫 Bu botu kullanma yetkin kısıtlandı.")
        return
    if not is_admin(user.id) and not await user_accepted_terms(user.id):
        await show_terms(update.message)
        return
    await update.message.reply_text(
        "👋 Pasha VIP admin sistemine hoş geldin." if is_admin(user.id) else "👋 Pasha VIP sistemine hoş geldin.",
        reply_markup=ADMIN_MENU if is_admin(user.id) else MAIN_MENU,
    )


async def channel_id_reader(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post:
        return
    text = (update.channel_post.text or "").lower().strip()
    if text in ["id", "chat id", "kanal id", "kanalid"]:
        await context.bot.send_message(chat_id=update.channel_post.chat_id, text=f"Chat ID:\n{update.channel_post.chat_id}")

# ---------- admin dashboard ----------

async def admin_dashboard_text():
    today = now_utc().date().isoformat()
    month = now_utc().strftime("%Y-%m")
    sales = supabase.table("sales").select("*").execute().data or []
    active_subs = supabase.table("subscriptions").select("*").eq("status", "active").execute().data or []
    supports = supabase.table("support_requests").select("*").eq("status", "open").execute().data or []
    blacklisted = supabase.table("blacklist").select("*").eq("active", True).execute().data or []
    abandoned = supabase.table("checkout_intents").select("*").eq("status", "started").execute().data or []

    today_count = today_stars = month_count = month_stars = 0
    for s in sales:
        if s.get("refund_status") == "refunded":
            continue
        created = str(s.get("created_at") or "")
        price = int(s.get("price") or 0)
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
        "👑 Admin Panel\n\n"
        f"📊 Bugün: {today_count} satış / {today_stars} Stars\n"
        f"📆 Bu ay: {month_count} satış / {month_stars} Stars\n"
        f"👥 Aktif üye: {len(active_subs)}\n"
        f"⏳ Bugün bitecek üyelik: {expiring_today}\n"
        f"🛒 Yarım kalan ödeme: {len(abandoned)}\n"
        f"🆘 Açık destek talebi: {len(supports)}\n"
        f"🚫 Kara liste: {len(blacklisted)}\n"
        f"🔥 Kampanya: {'AÇIK' if campaign_active() else 'KAPALI'}\n"
        f"🔧 Bakım modu: {'AÇIK' if maintenance_on() else 'KAPALI'}"
    )


async def open_admin_panel(message):
    kb = [
        [InlineKeyboardButton("✅ Görev Merkezi", callback_data="admin_tasks")],
        [InlineKeyboardButton("➕ Kanal Ekle", callback_data="admin_add_channel"), InlineKeyboardButton("📦 Paket Ekle", callback_data="admin_add_package")],
        [InlineKeyboardButton("📢 Kanallar", callback_data="admin_channels"), InlineKeyboardButton("📦 Paketler", callback_data="admin_packages")],
        [InlineKeyboardButton("🎁 Kullanıcıya VIP Ver", callback_data="admin_grant")],
        [InlineKeyboardButton("📊 Son Satışlar", callback_data="admin_sales"), InlineKeyboardButton("📈 Rapor", callback_data="admin_report")],
        [InlineKeyboardButton("📢 Kanal İstatistikleri", callback_data="admin_channel_stats")],
        [InlineKeyboardButton("👥 Kullanıcılar", callback_data="admin_users"), InlineKeyboardButton("🔍 Kullanıcı Ara", callback_data="admin_search_user")],
        [InlineKeyboardButton("🎟️ Kuponlar", callback_data="admin_coupons"), InlineKeyboardButton("🔥 Kampanya", callback_data="admin_campaign")],
        [InlineKeyboardButton("❓ SSS Yönet", callback_data="admin_faq"), InlineKeyboardButton("📣 Toplu Duyuru", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🆔 Kanal ID Yardımı", callback_data="admin_channel_id_help")],
        [InlineKeyboardButton("🆘 Destek", callback_data="admin_support"), InlineKeyboardButton("❌ İptal Talepleri", callback_data="admin_cancel")],
        [InlineKeyboardButton("🚫 Kara Liste", callback_data="admin_blacklist"), InlineKeyboardButton("👮 Adminler", callback_data="admin_admins")],
        [InlineKeyboardButton("📜 Loglar", callback_data="admin_logs"), InlineKeyboardButton("📄 Satış CSV", callback_data="admin_export_sales")],
        [InlineKeyboardButton("🔧 Bakım Aç/Kapat", callback_data="admin_maintenance")],
    ]
    await message.reply_text(await admin_dashboard_text(), reply_markup=InlineKeyboardMarkup(kb))

# ---------- menu ----------

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    user_id = user.id
    await save_user(user)
    await expire_old_subscriptions(context)

    if await is_blacklisted(user_id) and not is_admin(user_id):
        await update.message.reply_text("🚫 Bu botu kullanma yetkin kısıtlandı.")
        return
    if not is_admin(user_id) and not await user_accepted_terms(user_id):
        await show_terms(update.message)
        return
    if context.user_data.get("mode"):
        await handle_text_mode(update, context)
        return
    if maintenance_on() and not is_admin(user_id):
        await update.message.reply_text("🔧 Bot bakım modunda. Lütfen daha sonra tekrar dene.")
        return

    if is_admin(user_id) and text == "👑 Admin Panel":
        await open_admin_panel(update.message)
    elif text == "📢 VIP Kanallar":
        await show_store(update.message, user_id)
    elif text == "📅 Üyeliğim":
        await show_my_subscriptions(update.message, user_id)
    elif text == "📜 Geçmişim":
        await my_history(update.message, user_id)
    elif text == "❌ İptal Talebi":
        await create_cancel_request(update, context)
    elif text == "🎟️ Kupon Gir":
        context.user_data["mode"] = "user_coupon"
        await update.message.reply_text("🎟️ Kupon kodunu yaz:")
    elif text == "🎁 Referans":
        await referral_info(update.message, context, user_id)
    elif text == "❓ SSS":
        await faq_user_message(update.message)
    elif text == "🆘 Destek":
        await support_options(update.message)
    elif text == "ℹ️ Yardım":
        await update.message.reply_text(
            "ℹ️ Yardım\n\n"
            "📢 VIP Kanallar: Kanal ve paketleri gösterir.\n"
            "📅 Üyeliğim: Aktif üyeliklerini gösterir.\n"
            "📜 Geçmişim: Satış/üyelik geçmişini gösterir.\n"
            "🎁 Referans: Arkadaş davet linkini verir.\n"
            "🎟️ Kupon Gir: İndirim kodu uygular.\n"
            "🆘 Destek: Otomatik yardım veya admin desteği açar."
        )
    else:
        await update.message.reply_text("Menüden bir seçenek seçebilirsin.")

# ---------- store / packages ----------

async def trust_text():
    campaign_line = ""
    if campaign_active():
        end = get_setting("campaign_end", "")
        campaign_line = f"\n🔥 Kampanya: %{campaign_percent()} indirim — bitiş: {end}"
    return (
        "✅ Ödeme Telegram Stars ile yapılır\n"
        "✅ VIP link otomatik gelir\n"
        "✅ Üyelik tarihi botta görünür\n"
        "✅ Sorun olursa destek talebi açabilirsin"
        f"{campaign_line}"
    )


async def show_store(message, user_id):
    await message.reply_text(await trust_text())
    await show_channels(message, user_id)
    await show_packages(message, user_id)


async def show_channels(message, user_id):
    data = supabase.table("channels").select("*").eq("active", True).order("id").execute()
    if not data.data:
        await message.reply_text("📢 Henüz VIP kanal eklenmedi.")
        return
    for ch in data.data:
        base = int(ch["price"])
        final, coupon, notes = await calculate_price(user_id, base, ch["id"])
        v = ab_variant(user_id)
        headline = "🚀 VIP erişimini hemen aç" if v == "A" else "🔥 Bugüne özel VIP fırsatı"
        await log_event("offer_view", user_id, channel_id=ch["id"], details=f"variant={v}")
        kb = [
            [InlineKeyboardButton("👁️ Önizleme", callback_data=f"previewc_{ch['id']}")],
            [InlineKeyboardButton(f"⭐ {final} Stars ile Satın Al", callback_data=f"buyc_{ch['id']}")],
        ]
        note_line = f"\n🎟️ {notes}" if notes else ""
        await message.reply_text(
            f"{headline}\n\n📢 {ch['name']}\n⭐ Fiyat: {base}\n✅ Ödenecek: {final}\n⏳ Süre: {ch.get('duration_days') or DEFAULT_DURATION_DAYS} gün{note_line}",
            reply_markup=InlineKeyboardMarkup(kb),
        )


async def show_packages(message, user_id):
    data = supabase.table("packages").select("*").eq("active", True).order("id").execute()
    if not data.data:
        return
    await message.reply_text("📦 Avantajlı Paketler")
    for p in data.data:
        base = int(p["price"])
        final, coupon, notes = await calculate_price(user_id, base, None)
        kb = [
            [InlineKeyboardButton("👁️ Paket Önizleme", callback_data=f"previewp_{p['id']}")],
            [InlineKeyboardButton(f"⭐ {final} Stars ile Paketi Al", callback_data=f"buyp_{p['id']}")],
        ]
        note_line = f"\n🎟️ {notes}" if notes else ""
        await message.reply_text(
            f"📦 {p['name']}\n⭐ Fiyat: {base}\n✅ Ödenecek: {final}\n⏳ Süre: {p.get('duration_days') or DEFAULT_DURATION_DAYS} gün\n📝 {p.get('description') or '-'}{note_line}",
            reply_markup=InlineKeyboardMarkup(kb),
        )


async def preview_channel(message, channel_id, user_id):
    ch = await get_channel(channel_id)
    if not ch:
        await message.reply_text("❌ Kanal bulunamadı.")
        return
    base = int(ch["price"])
    final, coupon, notes = await calculate_price(user_id, base, ch["id"])
    text = (
        f"👁️ Kanal Önizleme\n\n📢 {ch['name']}\n⭐ Fiyat: {base}\n✅ Ödenecek: {final}\n"
        f"⏳ Süre: {ch.get('duration_days') or DEFAULT_DURATION_DAYS} gün\n📝 {ch.get('description') or 'Açıklama yok.'}\n\n{await trust_text()}"
    )
    kb = [[InlineKeyboardButton(f"⭐ {final} Stars ile Satın Al", callback_data=f"buyc_{ch['id']}")]]
    if ch.get("photo_url"):
        try:
            await message.reply_photo(ch["photo_url"], caption=text, reply_markup=InlineKeyboardMarkup(kb))
            return
        except Exception:
            pass
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def preview_package(message, package_id, user_id):
    p = await get_package(package_id)
    if not p:
        await message.reply_text("❌ Paket bulunamadı.")
        return
    channel_names = []
    for cid in parse_channel_ids(p.get("channel_ids")):
        ch = await get_channel(cid)
        channel_names.append(ch["name"] if ch else f"Kanal ID {cid}")
    base = int(p["price"])
    final, coupon, notes = await calculate_price(user_id, base, None)
    kb = [[InlineKeyboardButton(f"⭐ {final} Stars ile Paketi Al", callback_data=f"buyp_{p['id']}")]]
    await message.reply_text(
        f"👁️ Paket Önizleme\n\n📦 {p['name']}\n📢 Kanallar: {', '.join(channel_names)}\n⭐ Fiyat: {base}\n✅ Ödenecek: {final}\n⏳ Süre: {p.get('duration_days') or DEFAULT_DURATION_DAYS} gün\n📝 {p.get('description') or '-'}",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def referral_info(message, context, user_id):
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start=ref{user_id}"
    await message.reply_text(
        f"🎁 Referans sistemin\n\nArkadaşın bu linkten gelip ilk satın almasını yaparsa sana +{get_referral_bonus_days()} gün VIP bonus verilir.\n\n{link}"
    )

# ---------- text modes ----------

async def handle_text_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    text = update.message.text.strip()
    user = update.effective_user
    user_id = user.id
    try:
        if mode == "add_channel":
            parts = text.split("|")
            if len(parts) < 4:
                await update.message.reply_text("❌ Format: KanalAdı | Fiyat | ChatID | SüreGün | Açıklama")
                return
            payload = {
                "name": parts[0].strip(),
                "price": int(parts[1].strip()),
                "chat_id": parts[2].strip(),
                "duration_days": int(parts[3].strip()),
                "description": parts[4].strip() if len(parts) >= 5 else None,
                "photo_url": None,
                "invite_link": "",
                "active": True,
            }
            supabase.table("channels").insert(payload).execute()
            await log_event("channel_added", user_id, details=str(payload))
            context.user_data.clear()
            await update.message.reply_text(f"✅ Kanal eklendi: {payload['name']}")
            await announce_new_item(context, f"🚀 Yeni VIP kanal açıldı: {payload['name']}\nİncelemek için VIP Kanallar butonuna bas.")

        elif mode == "add_package":
            parts = text.split("|")
            if len(parts) < 5:
                await update.message.reply_text("❌ Format: PaketAdı | Fiyat | SüreGün | KanalIDler | Açıklama\nÖrn: TumVIP | 6000 | 30 | 1,2,3 | Tüm kanallar")
                return
            payload = {
                "name": parts[0].strip(),
                "price": int(parts[1].strip()),
                "duration_days": int(parts[2].strip()),
                "channel_ids": parts[3].strip(),
                "description": parts[4].strip(),
                "active": True,
            }
            supabase.table("packages").insert(payload).execute()
            await log_event("package_added", user_id, details=str(payload))
            context.user_data.clear()
            await update.message.reply_text(f"✅ Paket eklendi: {payload['name']}")
            await announce_new_item(context, f"📦 Yeni VIP paket açıldı: {payload['name']}\nİncelemek için VIP Kanallar butonuna bas.")

        elif mode in ["edit_price", "edit_duration", "edit_chat", "edit_description", "edit_photo"]:
            channel_id = context.user_data.get("channel_id")
            if mode == "edit_price":
                field, value, reply = "price", int(text), "✅ Fiyat güncellendi."
            elif mode == "edit_duration":
                field, value, reply = "duration_days", int(text), "✅ Süre güncellendi."
            elif mode == "edit_chat":
                field, value, reply = "chat_id", text, "✅ Chat ID güncellendi."
            elif mode == "edit_description":
                field, value, reply = "description", text, "✅ Açıklama güncellendi."
            else:
                field, value, reply = "photo_url", None if text == "-" else text, "✅ Görsel URL güncellendi."
            supabase.table("channels").update({field: value}).eq("id", channel_id).execute()
            await log_event("channel_updated", user_id, channel_id=channel_id, details=f"{field}={value}")
            context.user_data.clear()
            await update.message.reply_text(reply)

        elif mode == "search_user":
            await search_user(update.message, text)
            context.user_data.clear()

        elif mode == "add_coupon":
            parts = text.split("|")
            if len(parts) < 5:
                await update.message.reply_text("❌ Format: KOD | Yüzde | Starsİndirim | MaxKullanım | KanalID\nKanalID 0=tüm kanallar")
                return
            channel_id = int(parts[4].strip())
            supabase.table("coupons").insert(
                {
                    "code": parts[0].strip().upper(),
                    "discount_percent": int(parts[1].strip()),
                    "discount_stars": int(parts[2].strip()),
                    "max_uses": int(parts[3].strip()),
                    "used_count": 0,
                    "channel_id": None if channel_id == 0 else channel_id,
                    "active": True,
                }
            ).execute()
            await log_event("coupon_added", user_id, details=text)
            context.user_data.clear()
            await update.message.reply_text("✅ Kupon oluşturuldu.")

        elif mode == "add_faq":
            parts = text.split("|")
            if len(parts) < 2:
                await update.message.reply_text("❌ Format: Soru | Cevap")
                return
            supabase.table("faq").insert({"question": parts[0].strip(), "answer": parts[1].strip(), "active": True}).execute()
            await log_event("faq_added", user_id, details=text)
            context.user_data.clear()
            await update.message.reply_text("✅ SSS eklendi.")

        elif mode == "add_admin":
            parts = text.split("|")
            if len(parts) < 2:
                await update.message.reply_text("❌ Format: UserID | role\nRole: manager veya viewer")
                return
            target_id = int(parts[0].strip())
            role = parts[1].strip().lower()
            if role not in ["manager", "viewer"]:
                await update.message.reply_text("❌ Role sadece manager veya viewer olabilir.")
                return
            existing = supabase.table("admins").select("*").eq("user_id", target_id).execute()
            if existing.data:
                supabase.table("admins").update({"role": role, "active": True}).eq("user_id", target_id).execute()
            else:
                supabase.table("admins").insert({"user_id": target_id, "role": role, "active": True}).execute()
            await log_event("admin_added", user_id, target_user_id=target_id, details=role)
            context.user_data.clear()
            await update.message.reply_text("✅ Admin eklendi.")

        elif mode == "blacklist_reason":
            target_id = context.user_data.get("target_user_id")
            existing = supabase.table("blacklist").select("*").eq("user_id", target_id).execute()
            if existing.data:
                supabase.table("blacklist").update({"reason": text, "active": True}).eq("user_id", target_id).execute()
            else:
                supabase.table("blacklist").insert({"user_id": target_id, "reason": text, "active": True}).execute()
            await log_event("blacklisted", user_id, target_user_id=target_id, details=text)
            context.user_data.clear()
            await update.message.reply_text("✅ Kullanıcı kara listeye alındı.")

        elif mode == "custom_grant_days":
            target_user_id = context.user_data.get("target_user_id")
            channel_id = context.user_data.get("channel_id")
            context.user_data.clear()
            await grant_vip_to_user(update.message, context, target_user_id, channel_id, custom_days=int(text))

        elif mode == "user_coupon":
            code = text.upper()
            coupon = await get_coupon(code)
            if not coupon or not coupon.get("active"):
                context.user_data.clear()
                await update.message.reply_text("❌ Kupon bulunamadı veya aktif değil.")
                return
            max_uses = int(coupon.get("max_uses") or 0)
            used = int(coupon.get("used_count") or 0)
            if max_uses > 0 and used >= max_uses:
                context.user_data.clear()
                await update.message.reply_text("❌ Bu kuponun kullanım limiti dolmuş.")
                return
            supabase.table("users").update({"active_coupon": code}).eq("user_id", user_id).execute()
            context.user_data.clear()
            await update.message.reply_text(f"✅ Kupon uygulandı: {code}")

        elif mode == "user_support":
            if await is_blacklisted(user_id):
                context.user_data.clear()
                await update.message.reply_text("🚫 Destek talebi oluşturamazsın.")
                return
            supabase.table("support_requests").insert({"user_id": user_id, "username": safe_username(user), "message": text, "status": "open"}).execute()
            await log_event("support_created", user_id, target_user_id=user_id, details=text)
            context.user_data.clear()
            await update.message.reply_text("✅ Destek talebin admin’e gönderildi.")
            await context.bot.send_message(OWNER_ID, f"🆘 Yeni destek talebi!\n\nKullanıcı: @{safe_username(user) or 'yok'}\nID: {user_id}\n\n{text}")

        elif mode == "broadcast":
            segment = context.user_data.get("segment", "all")
            context.user_data.clear()
            await broadcast_message(update.message, context, text, segment)

        elif mode == "campaign":
            parts = text.split("|")
            if len(parts) < 2:
                await update.message.reply_text("❌ Format: Yüzde | Saat\nÖrn: 30 | 6")
                return
            percent = int(parts[0].strip())
            hours = int(parts[1].strip())
            set_setting("campaign_enabled", "on")
            set_setting("campaign_percent", percent)
            set_setting("campaign_end", (now_utc() + timedelta(hours=hours)).isoformat())
            await log_event("campaign_started", user_id, details=text)
            context.user_data.clear()
            await update.message.reply_text(f"✅ Kampanya başladı: %{percent} / {hours} saat")

    except Exception as e:
        logger.error("Text mode hatası: %s", e)
        await update.message.reply_text("❌ İşlem sırasında hata oldu. Formatı kontrol et.")

# ---------- callbacks ----------

async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "accept_terms":
        supabase.table("users").update({"accepted_terms": True}).eq("user_id", user_id).execute()
        await query.message.reply_text("✅ Kuralları kabul ettin. Menüden devam edebilirsin.", reply_markup=MAIN_MENU)
        return

    if data.startswith("previewc_"):
        await preview_channel(query.message, int(data.split("_")[1]), user_id)
        return
    if data.startswith("previewp_"):
        await preview_package(query.message, int(data.split("_")[1]), user_id)
        return
    if data.startswith("buyc_") or data.startswith("buyp_"):
        await handle_buy(query, context)
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
    if data.startswith("support_auto_"):
        await support_auto_answer(query.message, data)
        return
    if data == "support_manual":
        context.user_data["mode"] = "user_support"
        await query.message.reply_text("🆘 Sorununu tek mesaj olarak yaz:")
        return
    if data.startswith("cancel_"):
        await handle_cancel_admin(query, context)
        return
    if data.startswith("support_close_"):
        if not can_manage(user_id):
            await query.message.reply_text("❌ Yetkin yok.")
            return
        request_id = int(data.split("_")[2])
        supabase.table("support_requests").update({"status": "closed"}).eq("id", request_id).execute()
        await log_event("support_closed", user_id, details=f"request_id={request_id}")
        await query.message.reply_text("✅ Destek talebi kapatıldı.")
        return

    if not is_admin(user_id):
        await query.message.reply_text("❌ Yetkin yok.")
        return

    # viewer allowed reports only
    if data in ["admin_sales", "admin_report", "admin_channel_stats", "admin_users", "admin_logs"] and not can_view_reports(user_id):
        await query.message.reply_text("❌ Yetkin yok.")
        return

    if data == "admin_tasks":
        await task_center(query.message)
    elif data == "admin_add_channel":
        if not can_manage(user_id):
            await query.message.reply_text("❌ Yetkin yok.")
            return
        context.user_data["mode"] = "add_channel"
        await query.message.reply_text("➕ Kanal bilgilerini yaz:\n\nKanalAdı | Fiyat | ChatID | SüreGün | Açıklama\n\nÖrn:\nVIP | 2500 | -1001234567890 | 30 | Günlük VIP kanal")
    elif data == "admin_add_package":
        if not can_manage(user_id):
            await query.message.reply_text("❌ Yetkin yok.")
            return
        context.user_data["mode"] = "add_package"
        await query.message.reply_text("📦 Paket bilgilerini yaz:\n\nPaketAdı | Fiyat | SüreGün | KanalIDler | Açıklama\n\nÖrn:\nTumVIP | 6000 | 30 | 1,2,3 | Tüm VIP kanallar")
    elif data == "admin_channels":
        await list_channels_manage(query.message)
    elif data == "admin_packages":
        await packages_manage(query.message)
    elif data == "admin_grant":
        await show_users_for_grant(query.message)
    elif data == "admin_sales":
        await sales_message(query.message)
    elif data == "admin_report":
        await report_message(query.message)
    elif data == "admin_channel_stats":
        await channel_stats_message(query.message)
    elif data == "admin_users":
        await users_message(query.message)
    elif data == "admin_search_user":
        context.user_data["mode"] = "search_user"
        await query.message.reply_text("🔍 Kullanıcı ID veya username yaz:")
    elif data == "admin_coupons":
        await coupons_message(query.message)
    elif data == "coupon_add":
        if not can_manage(user_id):
            await query.message.reply_text("❌ Yetkin yok.")
            return
        context.user_data["mode"] = "add_coupon"
        await query.message.reply_text("🎟️ Kupon oluştur:\n\nKOD | Yüzde | Starsİndirim | MaxKullanım | KanalID\n\nÖrn:\nPASHA50 | 50 | 0 | 100 | 0")
    elif data.startswith("coupon_toggle_"):
        coupon_id = int(data.split("_")[2])
        row = supabase.table("coupons").select("*").eq("id", coupon_id).single().execute().data
        if row:
            supabase.table("coupons").update({"active": not bool(row.get("active"))}).eq("id", coupon_id).execute()
        await log_event("coupon_toggled", user_id, details=f"coupon_id={coupon_id}")
        await query.message.reply_text("✅ Kupon durumu değiştirildi.")
    elif data == "admin_campaign":
        await campaign_panel(query.message)
    elif data == "campaign_start":
        context.user_data["mode"] = "campaign"
        await query.message.reply_text("🔥 Kampanya başlat:\n\nYüzde | Saat\n\nÖrn:\n30 | 6")
    elif data == "campaign_stop":
        set_setting("campaign_enabled", "off")
        await query.message.reply_text("✅ Kampanya kapatıldı.")
    elif data == "admin_faq":
        await faq_admin_message(query.message)
    elif data == "faq_add":
        context.user_data["mode"] = "add_faq"
        await query.message.reply_text("❓ SSS ekle:\n\nSoru | Cevap")
    elif data.startswith("faq_toggle_"):
        faq_id = int(data.split("_")[2])
        row = supabase.table("faq").select("*").eq("id", faq_id).single().execute().data
        if row:
            supabase.table("faq").update({"active": not bool(row.get("active"))}).eq("id", faq_id).execute()
        await query.message.reply_text("✅ SSS durumu değiştirildi.")
    elif data == "admin_broadcast":
        await broadcast_segments(query.message)
    elif data.startswith("bseg_"):
        context.user_data["mode"] = "broadcast"
        context.user_data["segment"] = data.split("_", 1)[1]
        await query.message.reply_text("📣 Göndermek istediğin duyuruyu yaz:")
    elif data == "admin_channel_id_help":
        await query.message.reply_text("🆔 Kanal ID alma:\n\n1. Botu VIP kanala yönetici yap.\n2. Mesaj gönder / kullanıcı davet et / kullanıcı yasakla yetkilerini aç.\n3. VIP kanalın içine sadece şu kelimeyi yaz:\n\nid")
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
            await query.message.reply_text("❌ Sadece owner admin ekleyebilir.")
            return
        context.user_data["mode"] = "add_admin"
        await query.message.reply_text("👮 Admin ekle:\n\nUserID | role\n\nRole: manager veya viewer")
    elif data.startswith("admin_toggle_"):
        if not is_owner(user_id):
            await query.message.reply_text("❌ Yetkin yok.")
            return
        target_id = int(data.split("_")[2])
        row = supabase.table("admins").select("*").eq("user_id", target_id).single().execute().data
        if row:
            supabase.table("admins").update({"active": not bool(row.get("active"))}).eq("user_id", target_id).execute()
        await log_event("admin_toggled", user_id, target_user_id=target_id)
        await query.message.reply_text("✅ Admin durumu değiştirildi.")
    elif data == "admin_logs":
        await logs_message(query.message)
    elif data == "admin_export_sales":
        await export_sales_csv(query.message)
    elif data == "admin_maintenance":
        set_setting("maintenance", "off" if maintenance_on() else "on")
        await log_event("maintenance_toggled", user_id)
        await query.message.reply_text("✅ Bakım modu değiştirildi.")
        await open_admin_panel(query.message)
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
        await query.message.reply_text("⏳ Kaç günlük VIP vermek istiyorsun? Örnek: 14")
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
        target_id = int(data.split("_")[1])
        context.user_data["mode"] = "blacklist_reason"
        context.user_data["target_user_id"] = target_id
        await query.message.reply_text("🚫 Kara liste sebebini yaz:")
    elif data.startswith("unblacklist_"):
        target_id = int(data.split("_")[1])
        supabase.table("blacklist").update({"active": False}).eq("user_id", target_id).execute()
        await log_event("unblacklisted", user_id, target_user_id=target_id)
        await query.message.reply_text("✅ Kullanıcı kara listeden çıkarıldı.")

# ---------- admin lists and actions ----------

async def handle_channel_admin_button(query, context):
    user_id = query.from_user.id
    if not can_manage(user_id):
        await query.message.reply_text("❌ Yetkin yok.")
        return
    data = query.data
    if data.startswith("ch_delete_"):
        channel_id = int(data.split("_")[2])
        supabase.table("channels").delete().eq("id", channel_id).execute()
        await log_event("channel_deleted", user_id, channel_id=channel_id)
        await query.message.reply_text(f"✅ Kanal silindi. ID: {channel_id}")
    elif data.startswith("ch_toggle_"):
        channel_id = int(data.split("_")[2])
        row = supabase.table("channels").select("*").eq("id", channel_id).single().execute().data
        if row:
            supabase.table("channels").update({"active": not bool(row.get("active"))}).eq("id", channel_id).execute()
        await log_event("channel_toggled", user_id, channel_id=channel_id)
        await query.message.reply_text("✅ Kanal aktif/pasif durumu değiştirildi.")
    else:
        parts = data.split("_")
        action = parts[1]
        channel_id = int(parts[2])
        mode_map = {
            "price": ("edit_price", "💰 Yeni fiyatı yaz. Örnek: 3000"),
            "duration": ("edit_duration", "⏳ Yeni süreyi gün olarak yaz. Örnek: 60"),
            "chat": ("edit_chat", "🆔 Yeni Chat ID yaz. Örnek: -1001234567890"),
            "description": ("edit_description", "📝 Yeni açıklamayı yaz."),
            "photo": ("edit_photo", "🖼️ Görsel URL yaz. Boş bırakmak için - yaz."),
        }
        mode, prompt = mode_map[action]
        context.user_data["mode"] = mode
        context.user_data["channel_id"] = channel_id
        await query.message.reply_text(prompt)


async def handle_package_admin_button(query, context):
    if not can_manage(query.from_user.id):
        await query.message.reply_text("❌ Yetkin yok.")
        return
    data = query.data
    if data.startswith("pkg_toggle_"):
        pid = int(data.split("_")[2])
        row = supabase.table("packages").select("*").eq("id", pid).single().execute().data
        if row:
            supabase.table("packages").update({"active": not bool(row.get("active"))}).eq("id", pid).execute()
        await query.message.reply_text("✅ Paket aktif/pasif değiştirildi.")
    elif data.startswith("pkg_delete_"):
        pid = int(data.split("_")[2])
        supabase.table("packages").delete().eq("id", pid).execute()
        await query.message.reply_text("✅ Paket silindi.")


async def list_channels_manage(message):
    data = supabase.table("channels").select("*").order("id").execute()
    if not data.data:
        await message.reply_text("📢 Henüz kanal yok.")
        return
    for ch in data.data:
        active_text = "Aktif ✅" if ch.get("active") else "Pasif ⛔"
        kb = [
            [InlineKeyboardButton("💰 Fiyat", callback_data=f"ch_price_{ch['id']}"), InlineKeyboardButton("⏳ Süre", callback_data=f"ch_duration_{ch['id']}")],
            [InlineKeyboardButton("🆔 Chat ID", callback_data=f"ch_chat_{ch['id']}"), InlineKeyboardButton("📝 Açıklama", callback_data=f"ch_description_{ch['id']}")],
            [InlineKeyboardButton("🖼️ Görsel", callback_data=f"ch_photo_{ch['id']}"), InlineKeyboardButton("Aç/Kapat", callback_data=f"ch_toggle_{ch['id']}")],
            [InlineKeyboardButton("🗑️ Sil", callback_data=f"ch_delete_{ch['id']}")],
        ]
        await message.reply_text(
            f"📢 Kanal\n\nID: {ch['id']}\nAd: {ch['name']}\nFiyat: {ch['price']} ⭐\nSüre: {ch.get('duration_days') or DEFAULT_DURATION_DAYS} gün\nChat ID: {ch.get('chat_id')}\nDurum: {active_text}\nAçıklama: {ch.get('description') or '-'}",
            reply_markup=InlineKeyboardMarkup(kb),
        )


async def packages_manage(message):
    data = supabase.table("packages").select("*").order("id").execute()
    if not data.data:
        await message.reply_text("📦 Henüz paket yok.")
        return
    for p in data.data:
        status = "Aktif ✅" if p.get("active") else "Pasif ⛔"
        kb = [[InlineKeyboardButton("Aç/Kapat", callback_data=f"pkg_toggle_{p['id']}"), InlineKeyboardButton("Sil", callback_data=f"pkg_delete_{p['id']}")]]
        await message.reply_text(
            f"📦 Paket\n\nID: {p['id']}\nAd: {p['name']}\nFiyat: {p['price']}\nSüre: {p.get('duration_days')} gün\nKanal IDler: {p.get('channel_ids')}\nDurum: {status}\nAçıklama: {p.get('description')}",
            reply_markup=InlineKeyboardMarkup(kb),
        )


async def show_users_for_grant(message):
    data = supabase.table("users").select("*").order("id", desc=True).limit(20).execute()
    if not data.data:
        await message.reply_text("👥 Henüz kullanıcı yok. Kullanıcı önce /start yazmalı.")
        return
    for u in data.data:
        username = f"@{u['username']}" if u.get("username") else "username yok"
        kb = [[InlineKeyboardButton("👁️ Detay", callback_data=f"userdetail_{u['user_id']}")], [InlineKeyboardButton("🎁 VIP Ver", callback_data=f"grant_user_{u['user_id']}")]]
        await message.reply_text(f"👤 {username}\nID: {u['user_id']}", reply_markup=InlineKeyboardMarkup(kb))


async def show_channels_for_grant(message, target_user_id):
    data = supabase.table("channels").select("*").eq("active", True).order("id").execute()
    if not data.data:
        await message.reply_text("📢 Önce kanal eklemelisin.")
        return
    for ch in data.data:
        kb = [[InlineKeyboardButton(f"🎁 {ch['name']} seç", callback_data=f"grant_channel_{target_user_id}_{ch['id']}")]]
        await message.reply_text(f"📢 Kanal seç\n\nAd: {ch['name']}\nFiyat: {ch['price']} ⭐\nSüre: {ch.get('duration_days') or DEFAULT_DURATION_DAYS} gün", reply_markup=InlineKeyboardMarkup(kb))


async def show_grant_duration(message, target_user_id, channel_id):
    kb = [
        [InlineKeyboardButton("🎁 7 Gün", callback_data=f"grant_days_{target_user_id}_{channel_id}_7"), InlineKeyboardButton("🎁 30 Gün", callback_data=f"grant_days_{target_user_id}_{channel_id}_30")],
        [InlineKeyboardButton("🎁 90 Gün", callback_data=f"grant_days_{target_user_id}_{channel_id}_90"), InlineKeyboardButton("✍️ Özel Süre", callback_data=f"grant_custom_{target_user_id}_{channel_id}")],
    ]
    await message.reply_text("⏳ VIP süresini seç:", reply_markup=InlineKeyboardMarkup(kb))


async def grant_vip_to_user(message, context, target_user_id, channel_id, custom_days=None):
    ch = await get_channel(channel_id)
    if not ch:
        await message.reply_text("❌ Kanal bulunamadı.")
        return
    duration = int(custom_days or ch.get("duration_days") or DEFAULT_DURATION_DAYS)
    start_date, end_date = await upsert_subscription(target_user_id, channel_id, duration, 0)
    vip_link = await safe_create_and_store_link(context, target_user_id, channel_id, ch)
    supabase.table("sales").insert({"user_id": target_user_id, "username": "manual_admin", "channel_id": channel_id, "price": 0, "payment_payload": "manual_admin_grant", "coupon_code": None, "refund_status": "none"}).execute()
    await log_event("vip_granted", message.chat_id, target_user_id, channel_id, f"{duration} gün")
    if vip_link:
        try:
            await context.bot.send_message(target_user_id, f"🎁 Admin sana VIP erişim verdi!\n\n📢 Kanal: {ch['name']}\n🔗 Tek kullanımlık giriş linkin:\n{vip_link}\n\nBaşlangıç: {start_date}\nBitiş: {end_date}")
            await message.reply_text("✅ VIP yetki verildi ve link kullanıcıya gönderildi.")
        except Exception:
            await message.reply_text(f"✅ VIP yetki verildi ama kullanıcıya mesaj gönderilemedi.\n\nLinki manuel gönder:\n{vip_link}")
    else:
        await message.reply_text("✅ VIP yetki verildi ama davet linki üretilemedi.")

# ---------- pricing / payment ----------

async def loyalty_info(user_id):
    data = supabase.table("sales").select("*").eq("user_id", int(user_id)).execute().data or []
    paid_count = 0
    spent = 0
    for s in data:
        if s.get("payment_payload") == "manual_admin_grant" or s.get("refund_status") == "refunded":
            continue
        price = int(s.get("price") or 0)
        if price > 0:
            paid_count += 1
            spent += price
    if paid_count >= 5:
        return "Altın", paid_count, spent, 15, 7
    if paid_count >= 3:
        return "Gümüş", paid_count, spent, 10, 0
    if paid_count >= 1:
        return "Bronz", paid_count, spent, 0, 0
    return "Yeni", paid_count, spent, 0, 0


async def get_coupon(code):
    if not code:
        return None
    res = supabase.table("coupons").select("*").eq("code", code.upper()).execute()
    return res.data[0] if res.data else None


async def calculate_price(user_id, base_price, channel_id=None):
    final = int(base_price)
    notes = []
    coupon_code = None

    camp = campaign_percent()
    if camp > 0:
        final = int(final * (100 - camp) / 100)
        notes.append(f"Kampanya %{camp}")

    level, count, spent, loyalty_discount, bonus_days = await loyalty_info(user_id)
    if loyalty_discount > 0:
        final = int(final * (100 - loyalty_discount) / 100)
        notes.append(f"{level} sadakat %{loyalty_discount}")

    user_row = await get_user_row(user_id)
    active_code = user_row.get("active_coupon") if user_row else None
    coupon = await get_coupon(active_code) if active_code else None
    if coupon and coupon.get("active"):
        coupon_channel = coupon.get("channel_id")
        if not coupon_channel or (channel_id and int(coupon_channel) == int(channel_id)):
            max_uses = int(coupon.get("max_uses") or 0)
            used = int(coupon.get("used_count") or 0)
            if max_uses == 0 or used < max_uses:
                percent = int(coupon.get("discount_percent") or 0)
                stars = int(coupon.get("discount_stars") or 0)
                if percent > 0:
                    final = int(final * (100 - percent) / 100)
                    notes.append(f"Kupon %{percent}")
                if stars > 0:
                    final -= stars
                    notes.append(f"Kupon {stars} Stars")
                coupon_code = active_code.upper()

    final = max(final, 1)
    return final, coupon_code, " + ".join(notes)


async def handle_buy(query, context):
    if maintenance_on() and not is_admin(query.from_user.id):
        await query.message.reply_text("🔧 Bot bakım modunda. Satın alma geçici olarak kapalı.")
        return
    if await is_blacklisted(query.from_user.id) and not is_admin(query.from_user.id):
        await query.message.reply_text("🚫 Satın alma yetkin kısıtlandı.")
        return

    user_id = query.from_user.id
    variant = ab_variant(user_id)
    item_type = "channel" if query.data.startswith("buyc_") else "package"
    item_id = int(query.data.split("_")[1])

    if item_type == "channel":
        item = await get_channel(item_id)
        if not item or not item.get("active"):
            await query.message.reply_text("❌ Kanal bulunamadı veya pasif.")
            return
        base = int(item["price"])
        final, coupon, _ = await calculate_price(user_id, base, item_id)
        title = f"{item['name']} VIP Üyelik"
        desc = f"{item.get('duration_days') or DEFAULT_DURATION_DAYS} günlük VIP üyelik."
        label = item["name"]
    else:
        item = await get_package(item_id)
        if not item or not item.get("active"):
            await query.message.reply_text("❌ Paket bulunamadı veya pasif.")
            return
        base = int(item["price"])
        final, coupon, _ = await calculate_price(user_id, base, None)
        title = f"{item['name']} VIP Paket"
        desc = f"{item.get('duration_days') or DEFAULT_DURATION_DAYS} günlük paket üyelik."
        label = item["name"]

    payload = f"{item_type}|{item_id}|{final}|{coupon or 'NONE'}|{variant}"
    supabase.table("checkout_intents").insert({"user_id": user_id, "username": safe_username(query.from_user), "item_type": item_type, "item_id": item_id, "price": final, "payload": payload, "status": "started", "reminder_sent": False}).execute()
    await log_event("checkout_started", user_id, user_id, item_id if item_type == "channel" else None, f"{item_type} price={final} variant={variant}")

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=title,
        description=desc,
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=label, amount=final)],
    )


async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = update.message.successful_payment.invoice_payload
    user = update.effective_user
    parts = payload.split("|")
    item_type, item_id, paid_price, coupon_code, variant = parts[0], int(parts[1]), int(parts[2]), parts[3], parts[4]
    coupon_code = None if coupon_code == "NONE" else coupon_code

    supabase.table("checkout_intents").update({"status": "paid"}).eq("payload", payload).execute()

    if item_type == "channel":
        ch = await get_channel(item_id)
        if not ch:
            await update.message.reply_text("✅ Ödeme alındı ama kanal bulunamadı. Admin ile iletişime geç.")
            return
        duration = int(ch.get("duration_days") or DEFAULT_DURATION_DAYS)
        duration += await paid_bonus_days(user.id)
        start_date, end_date = await upsert_subscription(user.id, item_id, duration, paid_price)
        vip_link = await safe_create_and_store_link(context, user.id, item_id, ch)
        await record_sale(user, item_id, paid_price, payload, coupon_code, None, variant)
        await after_payment_bonus(context, user.id)
        await notify_sale(context, user, ch["name"], paid_price, coupon_code, end_date)
        if vip_link:
            await update.message.reply_text(f"✅ Ödeme başarılı!\n\n📢 Kanal: {ch['name']}\n🔗 Tek kullanımlık VIP giriş linkin:\n{vip_link}\n\nBaşlangıç: {start_date}\nBitiş: {end_date}")
        else:
            await update.message.reply_text("✅ Ödeme başarılı fakat link üretilemedi. Admin ile iletişime geç.")
    else:
        pkg = await get_package(item_id)
        if not pkg:
            await update.message.reply_text("✅ Ödeme alındı ama paket bulunamadı. Admin ile iletişime geç.")
            return
        duration = int(pkg.get("duration_days") or DEFAULT_DURATION_DAYS)
        duration += await paid_bonus_days(user.id)
        links = []
        last_end = None
        for cid in parse_channel_ids(pkg.get("channel_ids")):
            ch = await get_channel(cid)
            if not ch:
                continue
            start_date, end_date = await upsert_subscription(user.id, cid, duration, paid_price)
            last_end = end_date
            vip_link = await safe_create_and_store_link(context, user.id, cid, ch)
            if vip_link:
                links.append(f"📢 {ch['name']}: {vip_link}")
        await record_sale(user, None, paid_price, payload, coupon_code, item_id, variant)
        await after_payment_bonus(context, user.id)
        await notify_sale(context, user, f"Paket: {pkg['name']}", paid_price, coupon_code, last_end)
        await update.message.reply_text("✅ Paket ödeme başarılı!\n\n" + ("\n\n".join(links) if links else "Linkler üretilemedi. Admin ile iletişime geç."))

    if coupon_code:
        coupon = await get_coupon(coupon_code)
        if coupon:
            supabase.table("coupons").update({"used_count": int(coupon.get("used_count") or 0) + 1}).eq("id", coupon["id"]).execute()
        supabase.table("users").update({"active_coupon": None}).eq("user_id", user.id).execute()


async def paid_bonus_days(user_id):
    # Altın kullanıcıya +7 gün; erken yenileyene +renewal_bonus ayrıca upsert_subscription içinde verilir.
    level, count, spent, discount, bonus_days = await loyalty_info(user_id)
    return bonus_days


async def upsert_subscription(user_id, channel_id, duration_days, price):
    current = now_utc()
    existing = supabase.table("subscriptions").select("*").eq("user_id", int(user_id)).eq("channel_id", int(channel_id)).eq("status", "active").execute()
    if existing.data:
        sub = existing.data[0]
        old_end = parse_dt(sub.get("end_date")) or current
        base = old_end if old_end > current else current
        # Erken yenileyene bonus gün
        bonus = get_renewal_bonus_days() if old_end > current else 0
        new_end = base + timedelta(days=int(duration_days) + bonus)
        supabase.table("subscriptions").update({"end_date": new_end.isoformat(), "price": int(price), "status": "active", "warn_3d_sent": False, "warn_1d_sent": False}).eq("id", sub["id"]).execute()
        return sub.get("start_date"), new_end.isoformat()
    start = current
    end = start + timedelta(days=int(duration_days))
    supabase.table("subscriptions").insert({"user_id": int(user_id), "channel_id": int(channel_id), "start_date": start.isoformat(), "end_date": end.isoformat(), "status": "active", "price": int(price), "warn_3d_sent": False, "warn_1d_sent": False}).execute()
    return start.isoformat(), end.isoformat()


async def safe_create_and_store_link(context, user_id, channel_id, ch):
    try:
        link = await create_one_time_invite_link(context, ch, user_id)
        if link:
            supabase.table("subscriptions").update({"generated_invite_link": link}).eq("user_id", int(user_id)).eq("channel_id", int(channel_id)).eq("status", "active").execute()
        return link
    except Exception as e:
        logger.error("Link üretilemedi: %s", e)
        return None


async def record_sale(user, channel_id, price, payload, coupon_code, package_id, variant):
    supabase.table("sales").insert({"user_id": user.id, "username": safe_username(user), "channel_id": channel_id, "package_id": package_id, "price": price, "payment_payload": payload, "coupon_code": coupon_code, "refund_status": "none", "ab_variant": variant}).execute()
    await log_event("payment_success", user.id, user.id, channel_id, f"{price} Stars, pkg={package_id}, variant={variant}")


async def notify_sale(context, user, item_name, price, coupon, end_date):
    await context.bot.send_message(OWNER_ID, f"✅ Yeni satış!\n\nKullanıcı: @{safe_username(user) or 'yok'}\nUser ID: {user.id}\nÜrün: {item_name}\nFiyat: {price} Stars\nKupon: {coupon or 'Yok'}\nBitiş: {end_date}")


async def after_payment_bonus(context, user_id):
    row = await get_user_row(user_id)
    if not row:
        return
    referrer_id = row.get("referrer_id")
    already = row.get("referral_bonus_given")
    if not referrer_id or already:
        return
    subs = supabase.table("subscriptions").select("*").eq("user_id", int(referrer_id)).eq("status", "active").execute().data or []
    if not subs:
        return
    bonus_days = get_referral_bonus_days()
    for sub in subs:
        old_end = parse_dt(sub.get("end_date")) or now_utc()
        new_end = old_end + timedelta(days=bonus_days)
        supabase.table("subscriptions").update({"end_date": new_end.isoformat()}).eq("id", sub["id"]).execute()
    supabase.table("users").update({"referral_bonus_given": True}).eq("user_id", user_id).execute()
    await log_event("referral_bonus_given", user_id, target_user_id=referrer_id, details=f"+{bonus_days} gün")
    try:
        await context.bot.send_message(referrer_id, f"🎁 Referans bonusu kazandın! Aktif üyeliklerine +{bonus_days} gün eklendi.")
    except Exception:
        pass

# ---------- subscription/user actions ----------

async def show_my_subscriptions(message, user_id):
    data = supabase.table("subscriptions").select("*").eq("user_id", int(user_id)).eq("status", "active").execute()
    if not data.data:
        await message.reply_text("📅 Aktif üyelik bulunamadı.")
        return
    for sub in data.data:
        ch = await get_channel(sub["channel_id"])
        name = ch["name"] if ch else f"Kanal ID {sub['channel_id']}"
        kb = [[InlineKeyboardButton("⭐ Bu üyeliği uzat", callback_data=f"buyc_{sub['channel_id']}")], [InlineKeyboardButton("🔗 Yeni link gönder", callback_data=f"resend_{sub['id']}")], [InlineKeyboardButton("❌ İptal talebi oluştur", callback_data=f"request_cancel_{sub['id']}")]]
        await message.reply_text(f"📅 Aktif üyeliğin:\n\n📢 Kanal: {name}\nBaşlangıç: {sub.get('start_date')}\nBitiş: {sub.get('end_date')}\nDurum: {sub.get('status')}", reply_markup=InlineKeyboardMarkup(kb))


async def my_history(message, user_id):
    sales = supabase.table("sales").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute()
    subs = supabase.table("subscriptions").select("*").eq("user_id", int(user_id)).order("id", desc=True).limit(10).execute()
    level, count, spent, discount, bonus = await loyalty_info(user_id)
    text = f"📜 Geçmişin\n\nSadakat: {level}\nSatın alma: {count}\nToplam Stars: {spent}\n"
    if discount:
        text += f"İndirim: %{discount}\n"
    if bonus:
        text += f"Bonus: +{bonus} gün\n"
    text += "\nSatın almalar:\n"
    if sales.data:
        for s in sales.data:
            item = f"Paket ID {s.get('package_id')}" if s.get("package_id") else f"Kanal ID {s.get('channel_id')}"
            text += f"- {item} | {s['price']} Stars | {s['created_at']} | iade: {s.get('refund_status') or 'none'}\n"
    else:
        text += "Yok.\n"
    text += "\nÜyelikler:\n"
    if subs.data:
        for sub in subs.data:
            ch = await get_channel(sub["channel_id"])
            name = ch["name"] if ch else f"Kanal ID {sub['channel_id']}"
            text += f"- {name} | {sub['status']} | Bitiş: {sub['end_date']}\n"
    else:
        text += "Yok."
    await message.reply_text(text[:3900])


async def resend_invite_link(query, context):
    sub_id = int(query.data.split("_")[1])
    sub = await get_subscription(sub_id)
    if not sub or int(sub["user_id"]) != query.from_user.id or sub.get("status") != "active":
        await query.message.reply_text("❌ Aktif üyelik bulunamadı.")
        return
    ch = await get_channel(sub["channel_id"])
    link = await safe_create_and_store_link(context, sub["user_id"], sub["channel_id"], ch)
    await query.message.reply_text(f"🔗 Yeni tek kullanımlık linkin:\n{link}" if link else "❌ Link üretilemedi. Admin ile iletişime geç.")


async def request_cancel_from_button(query, context):
    sub_id = int(query.data.split("_")[2])
    sub = await get_subscription(sub_id)
    if not sub or int(sub["user_id"]) != query.from_user.id or sub.get("status") != "active":
        await query.message.reply_text("❌ Aktif üyelik bulunamadı.")
        return
    await create_cancel_request_for_sub(query.message, context, sub)


async def create_cancel_request(update, context):
    data = supabase.table("subscriptions").select("*").eq("user_id", update.effective_user.id).eq("status", "active").execute()
    if not data.data:
        await update.message.reply_text("❌ Aktif üyeliğin olmadığı için iptal talebi oluşturulamaz.")
        return
    for sub in data.data:
        await create_cancel_request_for_sub(update.message, context, sub)


async def create_cancel_request_for_sub(message, context, sub):
    existing = supabase.table("cancel_requests").select("*").eq("user_id", sub["user_id"]).eq("channel_id", sub["channel_id"]).eq("status", "pending").execute()
    if existing.data:
        await message.reply_text("⚠️ Zaten bekleyen iptal talebin var.")
        return
    supabase.table("cancel_requests").insert({"user_id": sub["user_id"], "channel_id": sub["channel_id"], "status": "pending"}).execute()
    await log_event("cancel_requested", sub["user_id"], sub["user_id"], sub["channel_id"])
    await message.reply_text("✅ İptal talebin admin onayına gönderildi.")
    await context.bot.send_message(OWNER_ID, f"❌ Yeni iptal talebi!\n\nKullanıcı ID: {sub['user_id']}\nKanal ID: {sub['channel_id']}")


async def handle_cancel_admin(query, context):
    if not can_manage(query.from_user.id):
        await query.message.reply_text("❌ Yetkin yok.")
        return
    parts = query.data.split("_")
    action = parts[1]
    request_id = int(parts[2])
    req = supabase.table("cancel_requests").select("*").eq("id", request_id).single().execute().data
    if not req:
        await query.message.reply_text("❌ Talep bulunamadı.")
        return
    ch = await get_channel(req["channel_id"])
    if action == "ok":
        supabase.table("cancel_requests").update({"status": "approved"}).eq("id", request_id).execute()
        supabase.table("subscriptions").update({"status": "cancelled"}).eq("user_id", req["user_id"]).eq("channel_id", req["channel_id"]).execute()
        if ch:
            await remove_user_from_channel(context, ch, req["user_id"])
        await log_event("cancel_approved", query.from_user.id, req["user_id"], req["channel_id"])
        await query.message.reply_text("✅ İptal talebi onaylandı.")
        try:
            await context.bot.send_message(req["user_id"], "✅ Üyelik iptal talebin onaylandı.")
        except Exception:
            pass
    elif action == "no":
        supabase.table("cancel_requests").update({"status": "rejected"}).eq("id", request_id).execute()
        await log_event("cancel_rejected", query.from_user.id, req["user_id"], req["channel_id"])
        await query.message.reply_text("❌ İptal talebi reddedildi.")
        try:
            await context.bot.send_message(req["user_id"], "❌ Üyelik iptal talebin reddedildi.")
        except Exception:
            pass


async def admin_cancel_subscription(message, context, sub_id):
    sub = await get_subscription(sub_id)
    if not sub:
        await message.reply_text("❌ Üyelik bulunamadı.")
        return
    ch = await get_channel(sub["channel_id"])
    supabase.table("subscriptions").update({"status": "cancelled"}).eq("id", sub_id).execute()
    if ch:
        await remove_user_from_channel(context, ch, sub["user_id"])
    await log_event("subscription_cancelled_by_admin", message.chat_id, sub["user_id"], sub["channel_id"])
    await message.reply_text("✅ Üyelik iptal edildi.")


async def admin_resend_link_for_subscription(message, context, sub_id):
    sub = await get_subscription(sub_id)
    if not sub:
        await message.reply_text("❌ Üyelik bulunamadı.")
        return
    ch = await get_channel(sub["channel_id"])
    link = await safe_create_and_store_link(context, sub["user_id"], sub["channel_id"], ch)
    if link:
        try:
            await context.bot.send_message(sub["user_id"], f"🔗 Yeni VIP giriş linkin:\n{link}")
            await message.reply_text("✅ Yeni link kullanıcıya gönderildi.")
        except Exception:
            await message.reply_text(f"✅ Link üretildi ama gönderilemedi. Manuel gönder:\n{link}")
    else:
        await message.reply_text("❌ Link üretilemedi.")


async def admin_extend_subscription(message, sub_id, days):
    sub = await get_subscription(sub_id)
    if not sub:
        await message.reply_text("❌ Üyelik bulunamadı.")
        return
    old_end = parse_dt(sub.get("end_date")) or now_utc()
    base = old_end if old_end > now_utc() else now_utc()
    new_end = base + timedelta(days=days)
    supabase.table("subscriptions").update({"end_date": new_end.isoformat(), "warn_3d_sent": False, "warn_1d_sent": False}).eq("id", sub_id).execute()
    await message.reply_text(f"✅ Üyelik {days} gün uzatıldı. Yeni bitiş: {new_end.isoformat()}")

# ---------- reports, users, faq, support, admin helpers ----------

async def task_center(message):
    active_subs = supabase.table("subscriptions").select("*").eq("status", "active").execute().data or []
    supports = supabase.table("support_requests").select("*").eq("status", "open").execute().data or []
    abandoned = supabase.table("checkout_intents").select("*").eq("status", "started").execute().data or []
    expired = supabase.table("subscriptions").select("*").eq("status", "expired").execute().data or []
    exp_today = 0
    for sub in active_subs:
        end = parse_dt(sub.get("end_date"))
        if end and end.date() == now_utc().date():
            exp_today += 1
    await message.reply_text(f"✅ Görev Merkezi\n\n⏳ Bugün bitecek üyelik: {exp_today}\n🆘 Açık destek: {len(supports)}\n🛒 Yarım kalan ödeme: {len(abandoned)}\n⛔ Süresi bitmiş üyelik: {len(expired)}")


async def campaign_panel(message):
    text = f"🔥 Kampanya\n\nDurum: {'Açık' if campaign_active() else 'Kapalı'}\nYüzde: {get_setting('campaign_percent', '0')}\nBitiş: {get_setting('campaign_end', '-') or '-'}"
    kb = [[InlineKeyboardButton("🔥 Başlat", callback_data="campaign_start"), InlineKeyboardButton("⛔ Kapat", callback_data="campaign_stop")]]
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def announce_new_item(context, text):
    # yeni kanal/paket duyurusu: sonradan satış getirmek için aktif müşterilere ve eski alıcılara gider
    users = supabase.table("users").select("*").execute().data or []
    for u in users[:500]:
        try:
            if not await is_blacklisted(u["user_id"]):
                await context.bot.send_message(u["user_id"], text)
                await asyncio.sleep(BROADCAST_DELAY_SECONDS)
        except Exception:
            pass


async def broadcast_segments(message):
    kb = [
        [InlineKeyboardButton("Herkes", callback_data="bseg_all"), InlineKeyboardButton("Aktif üyeler", callback_data="bseg_active")],
        [InlineKeyboardButton("Süresi bitenler", callback_data="bseg_expired"), InlineKeyboardButton("Hiç satın almayan", callback_data="bseg_never")],
        [InlineKeyboardButton("Çok harcayan", callback_data="bseg_high"), InlineKeyboardButton("Ödemeyi yarım bırakan", callback_data="bseg_abandoned")],
    ]
    await message.reply_text("📣 Hangi gruba duyuru göndermek istiyorsun?", reply_markup=InlineKeyboardMarkup(kb))


async def get_segment_users(segment):
    users = supabase.table("users").select("*").execute().data or []
    if segment == "all":
        return users
    if segment == "active":
        ids = {x["user_id"] for x in supabase.table("subscriptions").select("*").eq("status", "active").execute().data or []}
        return [u for u in users if u["user_id"] in ids]
    if segment == "expired":
        ids = {x["user_id"] for x in supabase.table("subscriptions").select("*").eq("status", "expired").execute().data or []}
        return [u for u in users if u["user_id"] in ids]
    if segment == "never":
        ids = {x["user_id"] for x in supabase.table("sales").select("*").execute().data or []}
        return [u for u in users if u["user_id"] not in ids]
    if segment == "abandoned":
        ids = {x["user_id"] for x in supabase.table("checkout_intents").select("*").eq("status", "started").execute().data or []}
        return [u for u in users if u["user_id"] in ids]
    if segment == "high":
        sales = supabase.table("sales").select("*").execute().data or []
        totals = {}
        for s in sales:
            if s.get("refund_status") == "refunded":
                continue
            totals[s["user_id"]] = totals.get(s["user_id"], 0) + int(s.get("price") or 0)
        ids = {uid for uid, total in totals.items() if total >= 10000}
        return [u for u in users if u["user_id"] in ids]
    return []


async def broadcast_message(message, context, text, segment="all"):
    users = await get_segment_users(segment)
    sent = failed = 0
    await message.reply_text(f"📣 Duyuru başladı. Grup: {segment}. Kullanıcı sayısı: {len(users)}")
    for u in users:
        try:
            if not await is_blacklisted(u["user_id"]):
                await context.bot.send_message(chat_id=u["user_id"], text=text)
                sent += 1
            await asyncio.sleep(BROADCAST_DELAY_SECONDS)
        except Exception:
            failed += 1
    await log_event("broadcast_sent", message.chat_id, details=f"segment={segment}, sent={sent}, failed={failed}")
    await message.reply_text(f"✅ Duyuru bitti. Gönderildi: {sent}, Hata: {failed}")


async def support_options(message):
    kb = [
        [InlineKeyboardButton("Ödeme yaptım link gelmedi", callback_data="support_auto_link")],
        [InlineKeyboardButton("Link süresi doldu", callback_data="support_auto_expired")],
        [InlineKeyboardButton("Kanala giremiyorum", callback_data="support_auto_join")],
        [InlineKeyboardButton("Admin’e yaz", callback_data="support_manual")],
    ]
    await message.reply_text("🆘 Destek konusu seç:", reply_markup=InlineKeyboardMarkup(kb))


async def support_auto_answer(message, data):
    if data == "support_auto_link":
        await message.reply_text("Üyeliğim ekranından Yeni link gönder butonuna bas. Yine olmazsa Admin’e yaz seçeneğini kullan.")
    elif data == "support_auto_expired":
        await message.reply_text("VIP linkleri tek kullanımlık ve kısa sürelidir. Üyeliğim > Yeni link gönder ile yeni link alabilirsin.")
    elif data == "support_auto_join":
        await message.reply_text("Botun gönderdiği linke sadece bir kez bas. Giremezsen yeni link oluştur ve tekrar dene.")


async def sales_message(message):
    data = supabase.table("sales").select("*").order("id", desc=True).limit(20).execute()
    if not data.data:
        await message.reply_text("📊 Henüz satış yok.")
        return
    for s in data.data:
        refund = s.get("refund_status") or "none"
        kb = [] if refund == "refunded" else [[InlineKeyboardButton("💸 İade İşaretle", callback_data=f"refund_sale_{s['id']}")]]
        await message.reply_text(f"📊 Satış\n\nID: {s['id']}\nUser ID: {s['user_id']}\nKanal ID: {s.get('channel_id')}\nPaket ID: {s.get('package_id')}\nFiyat: {s['price']} ⭐\nKupon: {s.get('coupon_code') or 'Yok'}\nA/B: {s.get('ab_variant') or '-'}\nİade: {refund}\nTarih: {s['created_at']}", reply_markup=InlineKeyboardMarkup(kb) if kb else None)


async def report_message(message):
    data = supabase.table("sales").select("*").execute()
    if not data.data:
        await message.reply_text("📈 Henüz satış yok.")
        return
    today = now_utc().date().isoformat()
    month = now_utc().strftime("%Y-%m")
    stats = {"tc": 0, "ts": 0, "mc": 0, "ms": 0, "ac": 0, "as": 0, "rf": 0, "a": 0, "b": 0}
    for s in data.data:
        if s.get("refund_status") == "refunded":
            stats["rf"] += 1
            continue
        price = int(s.get("price") or 0)
        created = str(s.get("created_at") or "")
        stats["ac"] += 1
        stats["as"] += price
        if created.startswith(today):
            stats["tc"] += 1
            stats["ts"] += price
        if created.startswith(month):
            stats["mc"] += 1
            stats["ms"] += price
        if s.get("ab_variant") == "A":
            stats["a"] += 1
        elif s.get("ab_variant") == "B":
            stats["b"] += 1
    await message.reply_text(f"📈 Satış Raporu\n\nBugün: {stats['tc']} satış / {stats['ts']} Stars\nBu ay: {stats['mc']} satış / {stats['ms']} Stars\nToplam: {stats['ac']} satış / {stats['as']} Stars\nİade işaretli: {stats['rf']}\n\nA/B satış:\nA: {stats['a']}\nB: {stats['b']}")


async def channel_stats_message(message):
    sales = supabase.table("sales").select("*").execute()
    if not sales.data:
        await message.reply_text("📢 Henüz kanal satışı yok.")
        return
    stats = {}
    for s in sales.data:
        if s.get("refund_status") == "refunded" or not s.get("channel_id"):
            continue
        cid = s["channel_id"]
        stats.setdefault(cid, {"count": 0, "stars": 0})
        stats[cid]["count"] += 1
        stats[cid]["stars"] += int(s.get("price") or 0)
    text = "📢 Kanal Bazlı İstatistik\n\n"
    for cid, val in stats.items():
        ch = await get_channel(cid)
        name = ch["name"] if ch else f"Kanal ID {cid}"
        text += f"📢 {name}\nSatış: {val['count']}\nStars: {val['stars']}\n\n"
    await message.reply_text(text)


async def users_message(message):
    data = supabase.table("users").select("*").order("id", desc=True).limit(30).execute()
    if not data.data:
        await message.reply_text("👥 Henüz kullanıcı yok.")
        return
    for u in data.data:
        username = f"@{u['username']}" if u.get("username") else "username yok"
        kb = [[InlineKeyboardButton("👁️ Detay", callback_data=f"userdetail_{u['user_id']}")], [InlineKeyboardButton("🎁 VIP Ver", callback_data=f"grant_user_{u['user_id']}")]]
        await message.reply_text(f"👤 {username}\nID: {u['user_id']}", reply_markup=InlineKeyboardMarkup(kb))


async def search_user(message, query):
    q = query.replace("@", "").strip()
    if q.isdigit():
        data = supabase.table("users").select("*").eq("user_id", int(q)).execute()
    else:
        data = supabase.table("users").select("*").ilike("username", f"%{q}%").execute()
    if not data.data:
        await message.reply_text("❌ Kullanıcı bulunamadı.")
        return
    for u in data.data[:5]:
        await show_user_detail(message, u)


async def show_user_detail_by_id(message, user_id):
    row = await get_user_row(user_id)
    if not row:
        await message.reply_text("❌ Kullanıcı bulunamadı.")
        return
    await show_user_detail(message, row)


async def show_user_detail(message, row):
    user_id = row["user_id"]
    username = f"@{row['username']}" if row.get("username") else "username yok"
    black = await is_blacklisted(user_id)
    level, count, spent, discount, bonus = await loyalty_info(user_id)
    kb = [[InlineKeyboardButton("🎁 VIP Ver", callback_data=f"grant_user_{user_id}")], [InlineKeyboardButton("🚫 Kara Listeye Al", callback_data=f"blacklist_{user_id}")] if not black else [InlineKeyboardButton("✅ Kara Listeden Çıkar", callback_data=f"unblacklist_{user_id}")]]
    await message.reply_text(f"👤 Kullanıcı Detayı\n\nID: {user_id}\nUsername: {username}\nSadakat: {level}\nAlışveriş: {count}\nStars: {spent}\nKara liste: {'Evet' if black else 'Hayır'}", reply_markup=InlineKeyboardMarkup(kb))
    subs = supabase.table("subscriptions").select("*").eq("user_id", user_id).execute()
    if not subs.data:
        await message.reply_text("Üyelik yok.")
        return
    for sub in subs.data:
        ch = await get_channel(sub["channel_id"])
        name = ch["name"] if ch else f"Kanal ID {sub['channel_id']}"
        kb = [[InlineKeyboardButton("❌ İptal Et", callback_data=f"usub_cancel_{sub['id']}"), InlineKeyboardButton("🔗 Link Gönder", callback_data=f"usub_link_{sub['id']}")], [InlineKeyboardButton("+7 gün", callback_data=f"usub_extend_{sub['id']}_7"), InlineKeyboardButton("+30 gün", callback_data=f"usub_extend_{sub['id']}_30")]]
        await message.reply_text(f"📢 {name}\nDurum: {sub['status']}\nBitiş: {sub.get('end_date')}", reply_markup=InlineKeyboardMarkup(kb))


async def coupons_message(message):
    data = supabase.table("coupons").select("*").order("id", desc=True).execute()
    await message.reply_text("🎟️ Kuponlar", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Kupon Oluştur", callback_data="coupon_add")]]))
    if not data.data:
        await message.reply_text("Henüz kupon yok.")
        return
    for c in data.data:
        status = "Aktif ✅" if c.get("active") else "Pasif ⛔"
        ch_text = f"Kanal ID: {c.get('channel_id')}" if c.get("channel_id") else "Tüm kanallar"
        await message.reply_text(f"Kupon: {c['code']}\nYüzde: %{c.get('discount_percent') or 0}\nStars indirim: {c.get('discount_stars') or 0}\nGeçerli: {ch_text}\nKullanım: {c.get('used_count') or 0}/{c.get('max_uses') or '∞'}\nDurum: {status}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Aç/Kapat", callback_data=f"coupon_toggle_{c['id']}")]]))


async def faq_user_message(message):
    data = supabase.table("faq").select("*").eq("active", True).order("id").execute()
    if not data.data:
        await message.reply_text("❓ Henüz SSS eklenmedi.")
        return
    kb = [[InlineKeyboardButton(x["question"], callback_data=f"faq_view_{x['id']}")] for x in data.data]
    await message.reply_text("❓ Sık Sorulan Sorular", reply_markup=InlineKeyboardMarkup(kb))


async def faq_answer(message, faq_id):
    item = supabase.table("faq").select("*").eq("id", faq_id).single().execute().data
    if not item:
        await message.reply_text("❌ SSS bulunamadı.")
        return
    await message.reply_text(f"❓ {item['question']}\n\n{item['answer']}")


async def faq_admin_message(message):
    data = supabase.table("faq").select("*").order("id", desc=True).execute()
    await message.reply_text("❓ SSS Yönetimi", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ SSS Ekle", callback_data="faq_add")]]))
    if not data.data:
        await message.reply_text("Henüz SSS yok.")
        return
    for item in data.data:
        status = "Aktif ✅" if item.get("active") else "Pasif ⛔"
        await message.reply_text(f"ID: {item['id']}\nSoru: {item['question']}\nDurum: {status}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Aç/Kapat", callback_data=f"faq_toggle_{item['id']}")]]))


async def support_requests_message(message):
    data = supabase.table("support_requests").select("*").eq("status", "open").order("id", desc=True).limit(20).execute()
    if not data.data:
        await message.reply_text("🆘 Açık destek talebi yok.")
        return
    for r in data.data:
        await message.reply_text(f"🆘 Destek Talebi\n\nID: {r['id']}\nKullanıcı: @{r.get('username') or 'yok'}\nUser ID: {r['user_id']}\nMesaj:\n{r['message']}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Kapat", callback_data=f"support_close_{r['id']}")]]))


async def cancel_requests_message(message):
    data = supabase.table("cancel_requests").select("*").eq("status", "pending").execute()
    if not data.data:
        await message.reply_text("❌ Bekleyen iptal talebi yok.")
        return
    for req in data.data:
        kb = [[InlineKeyboardButton("✅ Onayla", callback_data=f"cancel_ok_{req['id']}"), InlineKeyboardButton("❌ Reddet", callback_data=f"cancel_no_{req['id']}")]]
        await message.reply_text(f"❌ İptal Talebi\n\nTalep ID: {req['id']}\nKullanıcı ID: {req['user_id']}\nKanal ID: {req['channel_id']}", reply_markup=InlineKeyboardMarkup(kb))


async def blacklist_message(message):
    data = supabase.table("blacklist").select("*").eq("active", True).order("id", desc=True).execute()
    if not data.data:
        await message.reply_text("🚫 Kara listede aktif kullanıcı yok.")
        return
    for b in data.data:
        await message.reply_text(f"🚫 User ID: {b['user_id']}\nSebep: {b.get('reason') or '-'}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Çıkar", callback_data=f"unblacklist_{b['user_id']}")]]))


async def admins_message(message):
    data = supabase.table("admins").select("*").order("id", desc=True).execute()
    await message.reply_text("👮 Adminler", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Admin Ekle", callback_data="admin_add_admin")]]))
    await message.reply_text(f"Owner: {OWNER_ID}")
    for a in data.data or []:
        status = "Aktif ✅" if a.get("active") else "Pasif ⛔"
        await message.reply_text(f"User ID: {a['user_id']}\nRole: {a['role']}\nDurum: {status}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Aç/Kapat", callback_data=f"admin_toggle_{a['user_id']}")]]))


async def logs_message(message):
    data = supabase.table("logs").select("*").order("id", desc=True).limit(30).execute()
    if not data.data:
        await message.reply_text("📜 Henüz log yok.")
        return
    text = "📜 Son İşlemler\n\n"
    for log in data.data:
        text += f"ID: {log['id']}\nİşlem: {log['action']}\nActor: {log.get('actor_id')}\nTarget: {log.get('target_user_id')}\nKanal: {log.get('channel_id')}\nDetay: {log.get('details') or '-'}\nTarih: {log['created_at']}\n\n"
    await message.reply_text(text[:3900])


async def export_sales_csv(message):
    data = supabase.table("sales").select("*").order("id", desc=True).execute().data or []
    output = io.StringIO()
    fields = ["id", "user_id", "username", "channel_id", "package_id", "price", "coupon_code", "refund_status", "ab_variant", "payment_payload", "created_at"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in data:
        writer.writerow({k: row.get(k) for k in fields})
    file_data = io.BytesIO(output.getvalue().encode("utf-8"))
    file_data.name = "sales.csv"
    await message.reply_document(document=file_data, filename="sales.csv", caption="📄 Satış CSV")


async def mark_refund(message, admin_id, sale_id):
    sale = supabase.table("sales").select("*").eq("id", sale_id).single().execute().data
    if not sale:
        await message.reply_text("❌ Satış bulunamadı.")
        return
    supabase.table("sales").update({"refund_status": "refunded", "refunded_at": now_utc().isoformat(), "refunded_by": admin_id}).eq("id", sale_id).execute()
    await log_event("refund_marked", admin_id, sale.get("user_id"), sale.get("channel_id"), f"sale_id={sale_id}")
    await message.reply_text("💸 Satış iade edildi olarak işaretlendi.\n\nNot: Bu sadece sistem içi işarettir; Telegram Stars iadesini otomatik yapmaz.")

# ---------- jobs ----------

async def expire_old_subscriptions_job(context: ContextTypes.DEFAULT_TYPE):
    await expire_old_subscriptions(context)


async def expire_old_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    data = supabase.table("subscriptions").select("*").eq("status", "active").execute()
    current = now_utc()
    for sub in data.data:
        end = parse_dt(sub.get("end_date"))
        if end and end < current:
            ch = await get_channel(sub["channel_id"])
            if ch:
                await remove_user_from_channel(context, ch, sub["user_id"])
            supabase.table("subscriptions").update({"status": "expired"}).eq("id", sub["id"]).execute()
            supabase.table("users").update({"active_coupon": "WINBACK20"}).eq("user_id", sub["user_id"]).execute()
            await log_event("subscription_expired", None, sub["user_id"], sub["channel_id"])
            try:
                await context.bot.send_message(sub["user_id"], "⛔ VIP üyelik süren bitti. 48 saat içinde yenilersen WINBACK20 kuponuyla %20 indirim alırsın.")
            except Exception:
                pass


async def warning_job(context: ContextTypes.DEFAULT_TYPE):
    data = supabase.table("subscriptions").select("*").eq("status", "active").execute()
    current = now_utc()
    for sub in data.data:
        end = parse_dt(sub.get("end_date"))
        if not end:
            continue
        remaining = end - current
        ch = await get_channel(sub["channel_id"])
        name = ch["name"] if ch else f"Kanal ID {sub['channel_id']}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⭐ Üyeliği Uzat", callback_data=f"buyc_{sub['channel_id']}")]])
        if remaining <= timedelta(days=1) and not sub.get("warn_1d_sent"):
            try:
                await context.bot.send_message(sub["user_id"], f"⏳ VIP üyeliğin 1 gün içinde bitiyor.\n\n📢 Kanal: {name}\nŞimdi yenilersen erken yenileme bonusu kazanırsın.", reply_markup=kb)
                supabase.table("subscriptions").update({"warn_1d_sent": True}).eq("id", sub["id"]).execute()
            except Exception:
                pass
        elif remaining <= timedelta(days=3) and not sub.get("warn_3d_sent"):
            try:
                await context.bot.send_message(sub["user_id"], f"⏳ VIP üyeliğin 3 gün içinde bitiyor.\n\n📢 Kanal: {name}\nŞimdi yenilersen erken yenileme bonusu kazanırsın.", reply_markup=kb)
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
            await context.bot.send_message(
                row["user_id"],
                "👀 Ödemeyi başlatmıştın ama tamamlanmamış görünüyor. Devam etmek istersen aşağıdaki butona basabilirsin.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⭐ Ödemeye Devam Et", callback_data=callback)]]),
            )
            supabase.table("checkout_intents").update({"reminder_sent": True}).eq("id", row["id"]).execute()
            await log_event("abandoned_reminder_sent", None, row["user_id"], details=f"intent_id={row['id']}")
        except Exception:
            pass


async def daily_report_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_message(OWNER_ID, f"📊 Günlük Rapor\n\n{await admin_dashboard_text()}")
    except Exception:
        pass

# ---------- app ----------

app = ApplicationBuilder().token(TOKEN).build()
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
print("Pasha VIP satış botu çalışıyor...")
app.run_polling()
