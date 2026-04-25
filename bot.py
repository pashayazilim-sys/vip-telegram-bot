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
ADMIN_ID = 957422314

DEFAULT_DURATION_DAYS = 30
INVITE_LINK_EXPIRE_MINUTES = 30
BROADCAST_DELAY_SECONDS = 0.05

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        ["📅 Üyeliğim", "❌ İptal Talebi"],
        ["🎟️ Kupon Gir", "🆘 Destek"],
        ["ℹ️ Yardım"],
    ],
    resize_keyboard=True,
)

ADMIN_MENU = ReplyKeyboardMarkup(
    [
        ["👑 Admin Panel"],
        ["📢 VIP Kanallar"],
        ["📅 Üyeliğim", "❌ İptal Talebi"],
        ["🎟️ Kupon Gir", "🆘 Destek"],
        ["ℹ️ Yardım"],
    ],
    resize_keyboard=True,
)


def now_utc():
    return datetime.utcnow()


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def is_admin(user_id):
    return int(user_id) == ADMIN_ID


def safe_username(user):
    return user.username if user and user.username else None


def get_setting(key, default=None):
    try:
        result = supabase.table("settings").select("*").eq("key", key).execute()
        if result.data:
            return result.data[0].get("value")
    except Exception as e:
        logger.error("Setting okunamadı: %s", e)
    return default


def set_setting(key, value):
    try:
        result = supabase.table("settings").select("*").eq("key", key).execute()
        if result.data:
            supabase.table("settings").update({"value": value}).eq("key", key).execute()
        else:
            supabase.table("settings").insert({"key": key, "value": value}).execute()
    except Exception as e:
        logger.error("Setting yazılamadı: %s", e)


def maintenance_on():
    return get_setting("maintenance", "off") == "on"


async def get_user_row(user_id):
    try:
        result = supabase.table("users").select("*").eq("user_id", int(user_id)).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error("Kullanıcı alınamadı: %s", e)
        return None


async def save_user(user):
    if not user:
        return

    try:
        existing = supabase.table("users").select("*").eq("user_id", user.id).execute()
        payload = {"username": safe_username(user)}

        if existing.data:
            supabase.table("users").update(payload).eq("user_id", user.id).execute()
        else:
            payload.update(
                {
                    "user_id": user.id,
                    "accepted_terms": False,
                    "active_coupon": None,
                }
            )
            supabase.table("users").insert(payload).execute()
    except Exception as e:
        logger.error("Kullanıcı kaydedilemedi: %s", e)


async def user_accepted_terms(user_id):
    row = await get_user_row(user_id)
    return bool(row and row.get("accepted_terms"))


async def get_channel(channel_id):
    try:
        result = (
            supabase.table("channels")
            .select("*")
            .eq("id", int(channel_id))
            .single()
            .execute()
        )
        return result.data
    except Exception as e:
        logger.error("Kanal alınamadı: %s", e)
        return None


async def get_subscription(sub_id):
    try:
        result = (
            supabase.table("subscriptions")
            .select("*")
            .eq("id", int(sub_id))
            .single()
            .execute()
        )
        return result.data
    except Exception as e:
        logger.error("Üyelik alınamadı: %s", e)
        return None


async def create_one_time_invite_link(context, ch, user_id):
    chat_id_raw = ch.get("chat_id")
    if not chat_id_raw:
        return None

    expire_timestamp = int(
        (now_utc() + timedelta(minutes=INVITE_LINK_EXPIRE_MINUTES)).timestamp()
    )

    invite = await context.bot.create_chat_invite_link(
        chat_id=int(chat_id_raw),
        name=f"{ch['name']} - {user_id}",
        expire_date=expire_timestamp,
        member_limit=1,
    )
    return invite.invite_link


async def remove_user_from_channel(context, ch, user_id):
    chat_id_raw = ch.get("chat_id")
    if not chat_id_raw:
        return False

    try:
        await context.bot.ban_chat_member(chat_id=int(chat_id_raw), user_id=int(user_id))
        await context.bot.unban_chat_member(
            chat_id=int(chat_id_raw),
            user_id=int(user_id),
            only_if_banned=True,
        )
        return True
    except Exception as e:
        logger.error("Kullanıcı kanaldan çıkarılamadı: %s", e)
        return False


async def show_terms(message):
    keyboard = [[InlineKeyboardButton("✅ Kabul Ediyorum", callback_data="accept_terms")]]

    await message.reply_text(
        "⚠️ Kurallar ve Kullanım Onayı\n\n"
        "Bu bot üzerinden verilen VIP erişimler yalnızca yasal, rızaya dayalı ve kurallara uygun içerikler içindir.\n\n"
        "Devam ederek kuralları kabul etmiş olursun.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def admin_dashboard_text():
    today = now_utc().date().isoformat()
    month = now_utc().strftime("%Y-%m")

    try:
        sales = supabase.table("sales").select("*").execute().data or []
        subs = (
            supabase.table("subscriptions")
            .select("*")
            .eq("status", "active")
            .execute()
            .data
            or []
        )
        supports = (
            supabase.table("support_requests")
            .select("*")
            .eq("status", "open")
            .execute()
            .data
            or []
        )

        today_count = today_stars = month_count = month_stars = 0

        for s in sales:
            created = str(s.get("created_at") or "")
            price = int(s.get("price") or 0)

            if created.startswith(today):
                today_count += 1
                today_stars += price

            if created.startswith(month):
                month_count += 1
                month_stars += price

        expiring_today = 0
        current = now_utc()

        for sub in subs:
            end = parse_dt(sub.get("end_date"))
            if end and end.date() == current.date():
                expiring_today += 1

        return (
            "👑 Admin Panel\n\n"
            f"📊 Bugün: {today_count} satış / {today_stars} Stars\n"
            f"📆 Bu ay: {month_count} satış / {month_stars} Stars\n"
            f"👥 Aktif üye: {len(subs)}\n"
            f"⏳ Bugün bitecek üyelik: {expiring_today}\n"
            f"🆘 Açık destek talebi: {len(supports)}\n"
            f"🔧 Bakım modu: {'AÇIK' if maintenance_on() else 'KAPALI'}"
        )
    except Exception as e:
        logger.error("Dashboard hatası: %s", e)
        return "👑 Admin Panel\n\nÖzet alınamadı."


async def open_admin_panel(message):
    maintenance_text = "AÇIK 🔧" if maintenance_on() else "KAPALI ✅"

    keyboard = [
        [InlineKeyboardButton("➕ Kanal Ekle", callback_data="admin_add")],
        [InlineKeyboardButton("📢 Kanalları Yönet", callback_data="admin_list")],
        [InlineKeyboardButton("🎁 Kullanıcıya VIP Ver", callback_data="admin_grant")],
        [InlineKeyboardButton("📊 Son Satışlar", callback_data="admin_sales")],
        [InlineKeyboardButton("📈 Satış Raporu", callback_data="admin_report")],
        [InlineKeyboardButton("📢 Kanal İstatistikleri", callback_data="admin_channel_stats")],
        [InlineKeyboardButton("👥 Kullanıcılar", callback_data="admin_users")],
        [InlineKeyboardButton("🔍 Kullanıcı Ara", callback_data="admin_search_user")],
        [InlineKeyboardButton("🎟️ Kuponlar", callback_data="admin_coupons")],
        [InlineKeyboardButton("📣 Toplu Duyuru", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🆘 Destek Talepleri", callback_data="admin_support")],
        [InlineKeyboardButton("❌ İptal Talepleri", callback_data="admin_cancel")],
        [InlineKeyboardButton("📄 Satış CSV", callback_data="admin_export_sales")],
        [InlineKeyboardButton(f"🔧 Bakım Modu: {maintenance_text}", callback_data="admin_maintenance")],
    ]

    await message.reply_text(
        await admin_dashboard_text(),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user)

    if not is_admin(user.id) and not await user_accepted_terms(user.id):
        await show_terms(update.message)
        return

    await update.message.reply_text(
        "👋 Pasha VIP admin sistemine hoş geldin."
        if is_admin(user.id)
        else "👋 Pasha VIP sistemine hoş geldin.",
        reply_markup=ADMIN_MENU if is_admin(user.id) else MAIN_MENU,
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Yetkin yok.")
        return

    await open_admin_panel(update.message)


async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    await update.effective_message.reply_text(f"Chat ID:\n{chat.id}")


async def channel_id_reader(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post:
        return

    text = update.channel_post.text or ""

    if text.startswith("/id"):
        chat_id = update.channel_post.chat_id
        await context.bot.send_message(chat_id=chat_id, text=f"Chat ID:\n{chat_id}")


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    user_id = user.id

    await save_user(user)
    await expire_old_subscriptions(context)

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
        return

    if text == "📢 VIP Kanallar":
        data = (
            supabase.table("channels")
            .select("*")
            .eq("active", True)
            .order("id")
            .execute()
        )

        if not data.data:
            await update.message.reply_text("📢 Henüz VIP kanal eklenmedi.")
            return

        for ch in data.data:
            duration = ch.get("duration_days") or DEFAULT_DURATION_DAYS
            base_price = int(ch["price"])
            final_price, coupon_code, discount_text = await calculate_price(user_id, base_price)

            keyboard = [
                [
                    InlineKeyboardButton(
                        f"⭐ {final_price} Stars ile Satın Al",
                        callback_data=f"buy_{ch['id']}",
                    )
                ]
            ]

            coupon_line = f"\n🎟️ Kupon: {coupon_code} ({discount_text})" if coupon_code else ""
            desc = f"\n📝 {ch.get('description')}" if ch.get("description") else ""

            msg = (
                f"📢 {ch['name']}\n"
                f"⭐ Fiyat: {base_price} Stars\n"
                f"✅ Ödenecek: {final_price} Stars\n"
                f"⏳ Süre: {duration} gün"
                f"{coupon_line}{desc}"
            )

            if ch.get("photo_url"):
                try:
                    await update.message.reply_photo(
                        ch["photo_url"],
                        caption=msg,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )
                except Exception:
                    await update.message.reply_text(
                        msg,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )
            else:
                await update.message.reply_text(
                    msg,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )

    elif text == "📅 Üyeliğim":
        await show_my_subscriptions(update.message, user_id)

    elif text == "❌ İptal Talebi":
        await create_cancel_request(update, context)

    elif text == "🎟️ Kupon Gir":
        context.user_data["mode"] = "user_coupon"
        await update.message.reply_text("🎟️ Kupon kodunu yaz:")

    elif text == "🆘 Destek":
        context.user_data["mode"] = "user_support"
        await update.message.reply_text("🆘 Sorununu tek mesaj olarak yaz:")

    elif text == "ℹ️ Yardım":
        await update.message.reply_text(
            "ℹ️ Yardım\n\n"
            "📢 VIP Kanallar: Satın alınabilir kanalları gösterir.\n"
            "📅 Üyeliğim: Aktif üyeliklerini gösterir.\n"
            "🎟️ Kupon Gir: İndirim kodu uygular.\n"
            "🆘 Destek: Admin’e destek talebi gönderir.\n"
            "❌ İptal Talebi: Admin onayına iptal talebi gönderir."
        )

    else:
        await update.message.reply_text("Menüden bir seçenek seçebilirsin.")


async def show_my_subscriptions(message, user_id):
    data = (
        supabase.table("subscriptions")
        .select("*")
        .eq("user_id", int(user_id))
        .eq("status", "active")
        .execute()
    )

    if not data.data:
        await message.reply_text("📅 Aktif üyelik bulunamadı.")
        return

    for sub in data.data:
        ch = await get_channel(sub["channel_id"])
        name = ch["name"] if ch else f"Kanal ID {sub['channel_id']}"

        keyboard = [
            [InlineKeyboardButton("⭐ Bu üyeliği uzat", callback_data=f"buy_{sub['channel_id']}")],
            [InlineKeyboardButton("🔗 Yeni link gönder", callback_data=f"resend_{sub['id']}")],
            [InlineKeyboardButton("❌ İptal talebi oluştur", callback_data=f"request_cancel_{sub['id']}")],
        ]

        await message.reply_text(
            "📅 Aktif üyeliğin:\n\n"
            f"📢 Kanal: {name}\n"
            f"Başlangıç: {sub.get('start_date')}\n"
            f"Bitiş: {sub.get('end_date')}\n"
            f"Durum: {sub.get('status')}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def handle_text_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    text = update.message.text.strip()
    user = update.effective_user
    user_id = user.id

    try:
        if mode == "add_channel":
            parts = text.split(maxsplit=4)

            if len(parts) < 4:
                await update.message.reply_text("❌ Format: KanalAdı Fiyat ChatID SüreGün Açıklama")
                return

            name = parts[0]
            price = int(parts[1])
            chat_id = parts[2]
            duration = int(parts[3])
            description = parts[4] if len(parts) >= 5 else None

            supabase.table("channels").insert(
                {
                    "name": name,
                    "price": price,
                    "chat_id": chat_id,
                    "invite_link": "",
                    "duration_days": duration,
                    "description": description,
                    "photo_url": None,
                    "active": True,
                }
            ).execute()

            context.user_data.clear()
            await update.message.reply_text(f"✅ Kanal eklendi: {name} / {price} Stars / {duration} gün")

        elif mode in ["edit_price", "edit_duration", "edit_chat", "edit_description", "edit_photo"]:
            channel_id = context.user_data.get("channel_id")

            field_map = {
                "edit_price": ("price", int(text), "✅ Fiyat güncellendi."),
                "edit_duration": ("duration_days", int(text), "✅ Süre güncellendi."),
                "edit_chat": ("chat_id", text, "✅ Chat ID güncellendi."),
                "edit_description": ("description", text, "✅ Açıklama güncellendi."),
                "edit_photo": ("photo_url", None if text == "-" else text, "✅ Görsel URL güncellendi."),
            }

            field, value, reply = field_map[mode]

            supabase.table("channels").update({field: value}).eq("id", channel_id).execute()

            context.user_data.clear()
            await update.message.reply_text(reply)

        elif mode == "search_user":
            await search_user(update.message, text)
            context.user_data.clear()

        elif mode == "add_coupon":
            parts = text.split()

            if len(parts) < 4:
                await update.message.reply_text("❌ Format: KOD Yüzdeİndirim SabitStarsİndirim MaxKullanım")
                return

            supabase.table("coupons").insert(
                {
                    "code": parts[0].upper(),
                    "discount_percent": int(parts[1]),
                    "discount_stars": int(parts[2]),
                    "max_uses": int(parts[3]),
                    "used_count": 0,
                    "active": True,
                }
            ).execute()

            context.user_data.clear()
            await update.message.reply_text(f"✅ Kupon oluşturuldu: {parts[0].upper()}")

        elif mode == "custom_grant_days":
            target_user_id = context.user_data.get("target_user_id")
            channel_id = context.user_data.get("channel_id")
            days = int(text)

            context.user_data.clear()
            await grant_vip_to_user(update.message, context, target_user_id, channel_id, custom_days=days)

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
            supabase.table("support_requests").insert(
                {
                    "user_id": user_id,
                    "username": safe_username(user),
                    "message": text,
                    "status": "open",
                }
            ).execute()

            context.user_data.clear()
            await update.message.reply_text("✅ Destek talebin admin’e gönderildi.")

            await context.bot.send_message(
                ADMIN_ID,
                f"🆘 Yeni destek talebi!\n\nKullanıcı: @{safe_username(user) or 'yok'}\nID: {user_id}\n\n{text}",
            )

        elif mode == "broadcast":
            context.user_data.clear()
            await broadcast_message(update.message, context, text)

    except Exception as e:
        logger.error("Text mode hatası: %s", e)
        await update.message.reply_text("❌ İşlem sırasında hata oldu. Formatı kontrol et.")


async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "accept_terms":
        supabase.table("users").update({"accepted_terms": True}).eq("user_id", query.from_user.id).execute()

        await query.message.reply_text(
            "✅ Kuralları kabul ettin. Menüden devam edebilirsin.",
            reply_markup=MAIN_MENU,
        )
        return

    if data.startswith("buy_"):
        await handle_buy(query, context)
        return

    if data.startswith("resend_"):
        await resend_invite_link(query, context)
        return

    if data.startswith("request_cancel_"):
        await request_cancel_from_button(query, context)
        return

    if data.startswith("cancel_"):
        await handle_cancel_admin(query, context)
        return

    if data.startswith("support_close_"):
        if not is_admin(query.from_user.id):
            await query.message.reply_text("❌ Yetkin yok.")
            return

        request_id = int(data.split("_")[2])

        supabase.table("support_requests").update({"status": "closed"}).eq("id", request_id).execute()

        await query.message.reply_text("✅ Destek talebi kapatıldı.")
        return

    if not is_admin(query.from_user.id):
        await query.message.reply_text("❌ Yetkin yok.")
        return

    if data == "admin_add":
        context.user_data["mode"] = "add_channel"
        await query.message.reply_text(
            "➕ Kanal bilgilerini yaz:\n\n"
            "KanalAdı Fiyat ChatID SüreGün Açıklama\n\n"
            "Örnek:\n"
            "VIP 2500 -1001234567890 30 En iyi VIP kanal"
        )

    elif data == "admin_list":
        await list_channels_manage(query.message)

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
        context.user_data["mode"] = "add_coupon"
        await query.message.reply_text(
            "🎟️ Kupon oluştur:\n\n"
            "KOD Yüzdeİndirim SabitStarsİndirim MaxKullanım\n\n"
            "Örnek:\n"
            "PASHA50 50 0 100"
        )

    elif data.startswith("coupon_toggle_"):
        coupon_id = int(data.split("_")[2])

        result = supabase.table("coupons").select("*").eq("id", coupon_id).single().execute()
        coupon = result.data

        if coupon:
            supabase.table("coupons").update({"active": not bool(coupon.get("active"))}).eq("id", coupon_id).execute()

        await query.message.reply_text("✅ Kupon durumu değiştirildi.")

    elif data == "admin_broadcast":
        context.user_data["mode"] = "broadcast"
        await query.message.reply_text("📣 Tüm kullanıcılara göndermek istediğin duyuruyu yaz:")

    elif data == "admin_support":
        await support_requests_message(query.message)

    elif data == "admin_cancel":
        await cancel_requests_message(query.message)

    elif data == "admin_export_sales":
        await export_sales_csv(query.message)

    elif data == "admin_maintenance":
        set_setting("maintenance", "off" if maintenance_on() else "on")
        await query.message.reply_text("✅ Bakım modu değiştirildi.")
        await open_admin_panel(query.message)

    elif data == "admin_grant":
        await show_users_for_grant(query.message)

    elif data.startswith("ch_"):
        await handle_channel_admin_button(query, context)

    elif data.startswith("grant_user_"):
        target_user_id = int(data.split("_")[2])
        await show_channels_for_grant(query.message, target_user_id)

    elif data.startswith("grant_channel_"):
        parts = data.split("_")
        await show_grant_duration(query.message, int(parts[2]), int(parts[3]))

    elif data.startswith("grant_days_"):
        parts = data.split("_")
        await grant_vip_to_user(
            query.message,
            context,
            int(parts[2]),
            int(parts[3]),
            custom_days=int(parts[4]),
        )

    elif data.startswith("grant_custom_"):
        parts = data.split("_")

        context.user_data["mode"] = "custom_grant_days"
        context.user_data["target_user_id"] = int(parts[2])
        context.user_data["channel_id"] = int(parts[3])

        await query.message.reply_text("⏳ Kaç günlük VIP vermek istiyorsun? Örnek: 14")

    elif data.startswith("userdetail_"):
        await show_user_detail_by_id(query.message, int(data.split("_")[1]))

    elif data.startswith("usub_cancel_"):
        sub_id = int(data.split("_")[2])
        await admin_cancel_subscription(query.message, context, sub_id)

    elif data.startswith("usub_link_"):
        sub_id = int(data.split("_")[2])
        await admin_resend_link_for_subscription(query.message, context, sub_id)

    elif data.startswith("usub_extend_"):
        parts = data.split("_")
        await admin_extend_subscription(query.message, int(parts[2]), int(parts[3]))


async def handle_channel_admin_button(query, context):
    data = query.data

    if data.startswith("ch_delete_"):
        channel_id = int(data.split("_")[2])

        supabase.table("channels").delete().eq("id", channel_id).execute()

        await query.message.reply_text(f"✅ Kanal silindi. ID: {channel_id}")

    elif data.startswith("ch_toggle_"):
        channel_id = int(data.split("_")[2])

        result = supabase.table("channels").select("*").eq("id", channel_id).single().execute()
        ch = result.data

        if ch:
            supabase.table("channels").update({"active": not bool(ch.get("active"))}).eq("id", channel_id).execute()

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


async def list_channels_manage(message):
    data = supabase.table("channels").select("*").order("id").execute()

    if not data.data:
        await message.reply_text("📢 Henüz kanal yok.")
        return

    for ch in data.data:
        active_text = "Aktif ✅" if ch.get("active") else "Pasif ⛔"

        keyboard = [
            [
                InlineKeyboardButton("💰 Fiyat", callback_data=f"ch_price_{ch['id']}"),
                InlineKeyboardButton("⏳ Süre", callback_data=f"ch_duration_{ch['id']}"),
            ],
            [
                InlineKeyboardButton("🆔 Chat ID", callback_data=f"ch_chat_{ch['id']}"),
                InlineKeyboardButton("📝 Açıklama", callback_data=f"ch_description_{ch['id']}"),
            ],
            [
                InlineKeyboardButton("🖼️ Görsel", callback_data=f"ch_photo_{ch['id']}"),
                InlineKeyboardButton("Aç/Kapat", callback_data=f"ch_toggle_{ch['id']}"),
            ],
            [InlineKeyboardButton("🗑️ Sil", callback_data=f"ch_delete_{ch['id']}")],
        ]

        await message.reply_text(
            f"📢 Kanal\n\n"
            f"ID: {ch['id']}\n"
            f"Ad: {ch['name']}\n"
            f"Fiyat: {ch['price']} ⭐\n"
            f"Süre: {ch.get('duration_days') or DEFAULT_DURATION_DAYS} gün\n"
            f"Chat ID: {ch.get('chat_id')}\n"
            f"Durum: {active_text}\n"
            f"Açıklama: {ch.get('description') or '-'}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def show_users_for_grant(message):
    data = supabase.table("users").select("*").order("id", desc=True).limit(20).execute()

    if not data.data:
        await message.reply_text("👥 Henüz kullanıcı yok. Kullanıcı önce /start yazmalı.")
        return

    for u in data.data:
        username = f"@{u['username']}" if u.get("username") else "username yok"

        keyboard = [
            [InlineKeyboardButton("👁️ Detay", callback_data=f"userdetail_{u['user_id']}")],
            [InlineKeyboardButton("🎁 VIP Ver", callback_data=f"grant_user_{u['user_id']}")],
        ]

        await message.reply_text(
            f"👤 {username}\nID: {u['user_id']}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def show_channels_for_grant(message, target_user_id):
    data = supabase.table("channels").select("*").eq("active", True).order("id").execute()

    if not data.data:
        await message.reply_text("📢 Önce kanal eklemelisin.")
        return

    for ch in data.data:
        keyboard = [
            [
                InlineKeyboardButton(
                    f"🎁 {ch['name']} seç",
                    callback_data=f"grant_channel_{target_user_id}_{ch['id']}",
                )
            ]
        ]

        await message.reply_text(
            f"📢 Kanal seç\n\n"
            f"Ad: {ch['name']}\n"
            f"Fiyat: {ch['price']} ⭐\n"
            f"Süre: {ch.get('duration_days') or DEFAULT_DURATION_DAYS} gün",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def show_grant_duration(message, target_user_id, channel_id):
    keyboard = [
        [
            InlineKeyboardButton("🎁 7 Gün", callback_data=f"grant_days_{target_user_id}_{channel_id}_7"),
            InlineKeyboardButton("🎁 30 Gün", callback_data=f"grant_days_{target_user_id}_{channel_id}_30"),
        ],
        [
            InlineKeyboardButton("🎁 90 Gün", callback_data=f"grant_days_{target_user_id}_{channel_id}_90"),
            InlineKeyboardButton("✍️ Özel Süre", callback_data=f"grant_custom_{target_user_id}_{channel_id}"),
        ],
    ]

    await message.reply_text("⏳ VIP süresini seç:", reply_markup=InlineKeyboardMarkup(keyboard))


async def grant_vip_to_user(message, context, target_user_id, channel_id, custom_days=None):
    ch = await get_channel(channel_id)

    if not ch:
        await message.reply_text("❌ Kanal bulunamadı.")
        return

    duration_days = int(custom_days or ch.get("duration_days") or DEFAULT_DURATION_DAYS)

    start_date, end_date = await upsert_subscription(
        target_user_id,
        channel_id,
        duration_days,
        0,
    )

    vip_link = await safe_create_and_store_link(context, target_user_id, channel_id, ch)

    supabase.table("sales").insert(
        {
            "user_id": target_user_id,
            "username": "manual_admin",
            "channel_id": channel_id,
            "price": 0,
            "payment_payload": "manual_admin_grant",
            "coupon_code": None,
        }
    ).execute()

    if vip_link:
        try:
            await context.bot.send_message(
                target_user_id,
                f"🎁 Admin sana VIP erişim verdi!\n\n"
                f"📢 Kanal: {ch['name']}\n"
                f"🔗 Tek kullanımlık giriş linkin:\n{vip_link}\n\n"
                f"Başlangıç: {start_date}\n"
                f"Bitiş: {end_date}",
            )

            await message.reply_text("✅ VIP yetki verildi ve link kullanıcıya gönderildi.")
        except Exception:
            await message.reply_text(f"✅ VIP yetki verildi ama kullanıcıya mesaj gönderilemedi. Linki manuel gönder:\n{vip_link}")
    else:
        await message.reply_text("✅ VIP yetki verildi ama davet linki üretilemedi. Botun kanalda admin ve davet yetkisi olduğundan emin ol.")


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
            {
                "end_date": new_end.isoformat(),
                "price": int(price),
                "status": "active",
                "warn_3d_sent": False,
                "warn_1d_sent": False,
            }
        ).eq("id", sub["id"]).execute()

        return sub.get("start_date"), new_end.isoformat()

    start = current
    end = start + timedelta(days=int(duration_days))

    supabase.table("subscriptions").insert(
        {
            "user_id": int(user_id),
            "channel_id": int(channel_id),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "status": "active",
            "price": int(price),
            "warn_3d_sent": False,
            "warn_1d_sent": False,
        }
    ).execute()

    return start.isoformat(), end.isoformat()


async def safe_create_and_store_link(context, user_id, channel_id, ch):
    try:
        vip_link = await create_one_time_invite_link(context, ch, user_id)

        if vip_link:
            supabase.table("subscriptions").update(
                {"generated_invite_link": vip_link}
            ).eq("user_id", int(user_id)).eq("channel_id", int(channel_id)).eq("status", "active").execute()

        return vip_link
    except Exception as e:
        logger.error("Link üretilemedi: %s", e)
        return None


async def get_coupon(code):
    if not code:
        return None

    try:
        result = supabase.table("coupons").select("*").eq("code", code.upper()).execute()
        return result.data[0] if result.data else None
    except Exception:
        return None


async def calculate_price(user_id, base_price):
    user_row = await get_user_row(user_id)
    code = user_row.get("active_coupon") if user_row else None
    coupon = await get_coupon(code) if code else None

    if not coupon or not coupon.get("active"):
        return base_price, None, None

    max_uses = int(coupon.get("max_uses") or 0)
    used = int(coupon.get("used_count") or 0)

    if max_uses > 0 and used >= max_uses:
        return base_price, None, None

    percent = int(coupon.get("discount_percent") or 0)
    stars = int(coupon.get("discount_stars") or 0)

    final = base_price

    if percent > 0:
        final = int(final * (100 - percent) / 100)

    if stars > 0:
        final -= stars

    final = max(final, 1)
    discount_text = f"%{percent} indirim" if percent > 0 else f"{stars} Stars indirim"

    return final, code.upper(), discount_text


async def handle_buy(query, context):
    if maintenance_on() and not is_admin(query.from_user.id):
        await query.message.reply_text("🔧 Bot bakım modunda. Satın alma geçici olarak kapalı.")
        return

    channel_id = int(query.data.split("_")[1])
    ch = await get_channel(channel_id)

    if not ch or not ch.get("active"):
        await query.message.reply_text("❌ Kanal bulunamadı veya pasif.")
        return

    final_price, coupon_code, _ = await calculate_price(query.from_user.id, int(ch["price"]))
    payload = f"vip_{channel_id}_{final_price}_{coupon_code or 'NONE'}"

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=f"{ch['name']} VIP Üyelik",
        description=f"{ch.get('duration_days') or DEFAULT_DURATION_DAYS} günlük VIP üyelik.",
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=ch["name"], amount=final_price)],
    )


async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = update.message.successful_payment.invoice_payload
    user = update.effective_user
    parts = payload.split("_", 3)

    channel_id = int(parts[1])
    paid_price = int(parts[2])
    coupon_code = parts[3] if len(parts) >= 4 and parts[3] != "NONE" else None

    ch = await get_channel(channel_id)

    if not ch:
        await update.message.reply_text("✅ Ödeme alındı ama kanal bulunamadı. Admin ile iletişime geç.")
        return

    start_date, end_date = await upsert_subscription(
        user.id,
        channel_id,
        int(ch.get("duration_days") or DEFAULT_DURATION_DAYS),
        paid_price,
    )

    vip_link = await safe_create_and_store_link(context, user.id, channel_id, ch)

    supabase.table("sales").insert(
        {
            "user_id": user.id,
            "username": safe_username(user),
            "channel_id": channel_id,
            "price": paid_price,
            "payment_payload": payload,
            "coupon_code": coupon_code,
        }
    ).execute()

    if coupon_code:
        coupon = await get_coupon(coupon_code)

        if coupon:
            supabase.table("coupons").update(
                {"used_count": int(coupon.get("used_count") or 0) + 1}
            ).eq("id", coupon["id"]).execute()

        supabase.table("users").update({"active_coupon": None}).eq("user_id", user.id).execute()

    await context.bot.send_message(
        ADMIN_ID,
        f"✅ Yeni satış!\n\n"
        f"Kullanıcı: @{safe_username(user) or 'yok'}\n"
        f"User ID: {user.id}\n"
        f"Kanal: {ch['name']}\n"
        f"Fiyat: {paid_price} Stars\n"
        f"Kupon: {coupon_code or 'Yok'}\n"
        f"Bitiş: {end_date}",
    )

    if vip_link:
        await update.message.reply_text(
            f"✅ Ödeme başarılı!\n\n"
            f"📢 Kanal: {ch['name']}\n"
            f"🔗 Tek kullanımlık VIP giriş linkin:\n{vip_link}\n\n"
            f"⚠️ Link {INVITE_LINK_EXPIRE_MINUTES} dakika geçerlidir ve sadece 1 kişi kullanabilir.\n\n"
            f"Başlangıç: {start_date}\n"
            f"Bitiş: {end_date}"
        )
    else:
        await update.message.reply_text("✅ Ödeme başarılı fakat otomatik davet linki üretilemedi. Admin ile iletişime geç.")
        await context.bot.send_message(ADMIN_ID, f"⚠️ Davet linki üretilemedi!\nKullanıcı ID: {user.id}\nKanal: {ch['name']}")


async def resend_invite_link(query, context):
    sub_id = int(query.data.split("_")[1])
    sub = await get_subscription(sub_id)

    if not sub or int(sub["user_id"]) != query.from_user.id or sub.get("status") != "active":
        await query.message.reply_text("❌ Aktif üyelik bulunamadı.")
        return

    ch = await get_channel(sub["channel_id"])
    vip_link = await safe_create_and_store_link(context, sub["user_id"], sub["channel_id"], ch)

    if vip_link:
        await query.message.reply_text(f"🔗 Yeni tek kullanımlık linkin:\n{vip_link}")
    else:
        await query.message.reply_text("❌ Link üretilemedi. Admin ile iletişime geç.")


async def request_cancel_from_button(query, context):
    sub_id = int(query.data.split("_")[2])
    sub = await get_subscription(sub_id)

    if not sub or int(sub["user_id"]) != query.from_user.id or sub.get("status") != "active":
        await query.message.reply_text("❌ Aktif üyelik bulunamadı.")
        return

    await create_cancel_request_for_sub(query.message, context, sub)


async def create_cancel_request(update, context):
    user_id = update.effective_user.id

    data = (
        supabase.table("subscriptions")
        .select("*")
        .eq("user_id", user_id)
        .eq("status", "active")
        .execute()
    )

    if not data.data:
        await update.message.reply_text("❌ Aktif üyeliğin olmadığı için iptal talebi oluşturulamaz.")
        return

    for sub in data.data:
        await create_cancel_request_for_sub(update.message, context, sub)


async def create_cancel_request_for_sub(message, context, sub):
    existing = (
        supabase.table("cancel_requests")
        .select("*")
        .eq("user_id", sub["user_id"])
        .eq("channel_id", sub["channel_id"])
        .eq("status", "pending")
        .execute()
    )

    if existing.data:
        await message.reply_text("⚠️ Zaten bekleyen iptal talebin var.")
        return

    supabase.table("cancel_requests").insert(
        {
            "user_id": sub["user_id"],
            "channel_id": sub["channel_id"],
            "status": "pending",
        }
    ).execute()

    await message.reply_text("✅ İptal talebin admin onayına gönderildi.")
    await context.bot.send_message(
        ADMIN_ID,
        f"❌ Yeni iptal talebi!\n\nKullanıcı ID: {sub['user_id']}\nKanal ID: {sub['channel_id']}",
    )


async def handle_cancel_admin(query, context):
    if not is_admin(query.from_user.id):
        await query.message.reply_text("❌ Yetkin yok.")
        return

    parts = query.data.split("_")
    action = parts[1]
    request_id = int(parts[2])

    result = supabase.table("cancel_requests").select("*").eq("id", request_id).single().execute()
    req = result.data

    if not req:
        await query.message.reply_text("❌ Talep bulunamadı.")
        return

    ch = await get_channel(req["channel_id"])

    if action == "ok":
        supabase.table("cancel_requests").update({"status": "approved"}).eq("id", request_id).execute()
        supabase.table("subscriptions").update({"status": "cancelled"}).eq("user_id", req["user_id"]).eq("channel_id", req["channel_id"]).execute()

        if ch:
            await remove_user_from_channel(context, ch, req["user_id"])

        await query.message.reply_text("✅ İptal talebi onaylandı.")

        try:
            await context.bot.send_message(req["user_id"], "✅ Üyelik iptal talebin onaylandı.")
        except Exception:
            pass

    elif action == "no":
        supabase.table("cancel_requests").update({"status": "rejected"}).eq("id", request_id).execute()

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

    await message.reply_text("✅ Üyelik iptal edildi.")


async def admin_resend_link_for_subscription(message, context, sub_id):
    sub = await get_subscription(sub_id)

    if not sub:
        await message.reply_text("❌ Üyelik bulunamadı.")
        return

    ch = await get_channel(sub["channel_id"])
    vip_link = await safe_create_and_store_link(context, sub["user_id"], sub["channel_id"], ch)

    if vip_link:
        try:
            await context.bot.send_message(sub["user_id"], f"🔗 Yeni VIP giriş linkin:\n{vip_link}")
            await message.reply_text("✅ Yeni link kullanıcıya gönderildi.")
        except Exception:
            await message.reply_text(f"✅ Link üretildi ama gönderilemedi. Manuel gönder:\n{vip_link}")
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

    supabase.table("subscriptions").update(
        {
            "end_date": new_end.isoformat(),
            "warn_3d_sent": False,
            "warn_1d_sent": False,
        }
    ).eq("id", sub_id).execute()

    await message.reply_text(f"✅ Üyelik {days} gün uzatıldı. Yeni bitiş: {new_end.isoformat()}")


async def sales_message(message):
    data = supabase.table("sales").select("*").order("id", desc=True).limit(20).execute()

    if not data.data:
        await message.reply_text("📊 Henüz satış yok.")
        return

    text = "📊 Son kayıtlar:\n\n"

    for s in data.data:
        text += (
            f"ID: {s['id']}\n"
            f"Kullanıcı: @{s.get('username') or 'yok'}\n"
            f"User ID: {s['user_id']}\n"
            f"Kanal ID: {s['channel_id']}\n"
            f"Fiyat: {s['price']} ⭐\n"
            f"Kupon: {s.get('coupon_code') or 'Yok'}\n"
            f"Tarih: {s['created_at']}\n\n"
        )

    await message.reply_text(text)


async def report_message(message):
    data = supabase.table("sales").select("*").execute()

    if not data.data:
        await message.reply_text("📈 Henüz satış yok.")
        return

    today = now_utc().date().isoformat()
    month = now_utc().strftime("%Y-%m")

    stats = {
        "tc": 0,
        "ts": 0,
        "mc": 0,
        "ms": 0,
        "ac": 0,
        "as": 0,
    }

    for s in data.data:
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

    await message.reply_text(
        f"📈 Satış Raporu\n\n"
        f"Bugün satış: {stats['tc']}\n"
        f"Bugün Stars: {stats['ts']}\n\n"
        f"Bu ay satış: {stats['mc']}\n"
        f"Bu ay Stars: {stats['ms']}\n\n"
        f"Toplam satış: {stats['ac']}\n"
        f"Toplam Stars: {stats['as']}"
    )


async def channel_stats_message(message):
    sales = supabase.table("sales").select("*").execute()

    if not sales.data:
        await message.reply_text("📢 Henüz kanal satışı yok.")
        return

    stats = {}

    for s in sales.data:
        cid = s["channel_id"]

        stats.setdefault(cid, {"count": 0, "stars": 0})
        stats[cid]["count"] += 1
        stats[cid]["stars"] += int(s.get("price") or 0)

    text = "📢 Kanal Bazlı İstatistik\n\n"

    for cid, val in stats.items():
        ch = await get_channel(cid)
        ch_name = ch["name"] if ch else f"Kanal ID {cid}"

        text += (
            f"📢 {ch_name}\n"
            f"Satış: {val['count']}\n"
            f"Stars: {val['stars']}\n\n"
        )

    await message.reply_text(text)


async def users_message(message):
    data = supabase.table("users").select("*").order("id", desc=True).limit(30).execute()

    if not data.data:
        await message.reply_text("👥 Henüz kullanıcı yok.")
        return

    for u in data.data:
        username = f"@{u['username']}" if u.get("username") else "username yok"

        keyboard = [
            [InlineKeyboardButton("👁️ Detay", callback_data=f"userdetail_{u['user_id']}")],
            [InlineKeyboardButton("🎁 VIP Ver", callback_data=f"grant_user_{u['user_id']}")],
        ]

        await message.reply_text(
            f"👤 {username}\nID: {u['user_id']}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


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


async def show_user_detail(message, user_row):
    user_id = user_row["user_id"]
    username = f"@{user_row['username']}" if user_row.get("username") else "username yok"

    await message.reply_text(f"👤 Kullanıcı Detayı\n\nID: {user_id}\nUsername: {username}")

    subs = supabase.table("subscriptions").select("*").eq("user_id", user_id).execute()

    if not subs.data:
        await message.reply_text(
            "Üyelik yok.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🎁 VIP Ver", callback_data=f"grant_user_{user_id}")]]
            ),
        )
        return

    for sub in subs.data:
        ch = await get_channel(sub["channel_id"])
        ch_name = ch["name"] if ch else f"Kanal ID {sub['channel_id']}"

        keyboard = [
            [
                InlineKeyboardButton("❌ İptal Et", callback_data=f"usub_cancel_{sub['id']}"),
                InlineKeyboardButton("🔗 Link Gönder", callback_data=f"usub_link_{sub['id']}"),
            ],
            [
                InlineKeyboardButton("+7 gün", callback_data=f"usub_extend_{sub['id']}_7"),
                InlineKeyboardButton("+30 gün", callback_data=f"usub_extend_{sub['id']}_30"),
            ],
            [InlineKeyboardButton("🎁 Yeni VIP Ver", callback_data=f"grant_user_{user_id}")],
        ]

        await message.reply_text(
            f"📢 {ch_name}\n"
            f"Durum: {sub['status']}\n"
            f"Bitiş: {sub.get('end_date')}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def coupons_message(message):
    data = supabase.table("coupons").select("*").order("id", desc=True).execute()

    await message.reply_text(
        "🎟️ Kuponlar",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Kupon Oluştur", callback_data="coupon_add")]]),
    )

    if not data.data:
        await message.reply_text("Henüz kupon yok.")
        return

    for c in data.data:
        status = "Aktif ✅" if c.get("active") else "Pasif ⛔"

        kb = [[InlineKeyboardButton("Aç/Kapat", callback_data=f"coupon_toggle_{c['id']}")]]

        await message.reply_text(
            f"Kupon: {c['code']}\n"
            f"Yüzde: %{c.get('discount_percent') or 0}\n"
            f"Stars indirim: {c.get('discount_stars') or 0}\n"
            f"Kullanım: {c.get('used_count') or 0}/{c.get('max_uses') or '∞'}\n"
            f"Durum: {status}",
            reply_markup=InlineKeyboardMarkup(kb),
        )


async def support_requests_message(message):
    data = (
        supabase.table("support_requests")
        .select("*")
        .eq("status", "open")
        .order("id", desc=True)
        .limit(20)
        .execute()
    )

    if not data.data:
        await message.reply_text("🆘 Açık destek talebi yok.")
        return

    for r in data.data:
        kb = [[InlineKeyboardButton("✅ Kapat", callback_data=f"support_close_{r['id']}")]]

        await message.reply_text(
            f"🆘 Destek Talebi\n\n"
            f"ID: {r['id']}\n"
            f"Kullanıcı: @{r.get('username') or 'yok'}\n"
            f"User ID: {r['user_id']}\n"
            f"Mesaj:\n{r['message']}",
            reply_markup=InlineKeyboardMarkup(kb),
        )


async def cancel_requests_message(message):
    data = supabase.table("cancel_requests").select("*").eq("status", "pending").execute()

    if not data.data:
        await message.reply_text("❌ Bekleyen iptal talebi yok.")
        return

    for req in data.data:
        kb = [
            [
                InlineKeyboardButton("✅ Onayla", callback_data=f"cancel_ok_{req['id']}"),
                InlineKeyboardButton("❌ Reddet", callback_data=f"cancel_no_{req['id']}"),
            ]
        ]

        await message.reply_text(
            f"❌ İptal Talebi\n\n"
            f"Talep ID: {req['id']}\n"
            f"Kullanıcı ID: {req['user_id']}\n"
            f"Kanal ID: {req['channel_id']}",
            reply_markup=InlineKeyboardMarkup(kb),
        )


async def export_sales_csv(message):
    data = supabase.table("sales").select("*").order("id", desc=True).execute().data or []

    output = io.StringIO()

    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "user_id",
            "username",
            "channel_id",
            "price",
            "coupon_code",
            "payment_payload",
            "created_at",
        ],
    )

    writer.writeheader()

    for row in data:
        writer.writerow({k: row.get(k) for k in writer.fieldnames})

    bio = io.BytesIO(output.getvalue().encode("utf-8"))
    bio.name = "sales.csv"

    await message.reply_document(document=bio, filename="sales.csv", caption="📄 Satış CSV")


async def broadcast_message(message, context, text):
    users = supabase.table("users").select("*").execute().data or []

    sent = 0
    failed = 0

    await message.reply_text(f"📣 Duyuru başladı. Kullanıcı sayısı: {len(users)}")

    for u in users:
        try:
            await context.bot.send_message(chat_id=u["user_id"], text=text)
            sent += 1
            await asyncio.sleep(BROADCAST_DELAY_SECONDS)
        except Exception:
            failed += 1

    await message.reply_text(f"✅ Duyuru bitti. Gönderildi: {sent}, Hata: {failed}")


async def expire_old_subscriptions_job(context: ContextTypes.DEFAULT_TYPE):
    await expire_old_subscriptions(context)


async def expire_old_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    try:
        data = supabase.table("subscriptions").select("*").eq("status", "active").execute()
        current = now_utc()

        for sub in data.data:
            end = parse_dt(sub.get("end_date"))

            if end and end < current:
                ch = await get_channel(sub["channel_id"])

                if ch:
                    await remove_user_from_channel(context, ch, sub["user_id"])

                supabase.table("subscriptions").update({"status": "expired"}).eq("id", sub["id"]).execute()

                try:
                    await context.bot.send_message(
                        sub["user_id"],
                        "⛔ VIP üyelik süren bitti. Yenilemek için bot üzerinden tekrar satın alabilirsin.",
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.error("Üyelik süre kontrol hatası: %s", e)


async def warning_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        data = supabase.table("subscriptions").select("*").eq("status", "active").execute()
        current = now_utc()

        for sub in data.data:
            end = parse_dt(sub.get("end_date"))

            if not end:
                continue

            remaining = end - current
            ch = await get_channel(sub["channel_id"])
            channel_name = ch["name"] if ch else f"Kanal ID {sub['channel_id']}"

            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("⭐ Üyeliği Uzat", callback_data=f"buy_{sub['channel_id']}")]]
            )

            if remaining <= timedelta(days=1) and not sub.get("warn_1d_sent"):
                await context.bot.send_message(
                    sub["user_id"],
                    f"⏳ VIP üyeliğin 1 gün içinde bitiyor.\n\n📢 Kanal: {channel_name}",
                    reply_markup=keyboard,
                )

                supabase.table("subscriptions").update({"warn_1d_sent": True}).eq("id", sub["id"]).execute()

            elif remaining <= timedelta(days=3) and not sub.get("warn_3d_sent"):
                await context.bot.send_message(
                    sub["user_id"],
                    f"⏳ VIP üyeliğin 3 gün içinde bitiyor.\n\n📢 Kanal: {channel_name}",
                    reply_markup=keyboard,
                )

                supabase.table("subscriptions").update({"warn_3d_sent": True}).eq("id", sub["id"]).execute()
    except Exception as e:
        logger.error("Uyarı job hatası: %s", e)


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin_command))
app.add_handler(CommandHandler("id", get_chat_id))

app.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.TEXT, channel_id_reader))

app.add_handler(CallbackQueryHandler(button_router))

app.add_handler(PreCheckoutQueryHandler(precheckout))
app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))

app.job_queue.run_repeating(expire_old_subscriptions_job, interval=3600, first=30)
app.job_queue.run_repeating(warning_job, interval=21600, first=60)

print("VIP bot çalışıyor...")
app.run_polling()
