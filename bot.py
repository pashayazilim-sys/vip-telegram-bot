import os
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

logging.basicConfig(level=logging.INFO)

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
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def is_admin(user_id):
    return user_id == ADMIN_ID


def safe_username(user):
    return user.username if user and user.username else None


def get_setting(key, default=None):
    try:
        result = supabase.table("settings").select("*").eq("key", key).execute()
        if result.data:
            return result.data[0].get("value")
    except Exception as e:
        logging.error(f"Setting okunamadı: {e}")
    return default


def set_setting(key, value):
    try:
        existing = supabase.table("settings").select("*").eq("key", key).execute()
        if existing.data:
            supabase.table("settings").update({"value": value}).eq("key", key).execute()
        else:
            supabase.table("settings").insert({"key": key, "value": value}).execute()
    except Exception as e:
        logging.error(f"Setting yazılamadı: {e}")


def maintenance_on():
    return get_setting("maintenance", "off") == "on"


async def get_user_row(user_id):
    try:
        result = supabase.table("users").select("*").eq("user_id", user_id).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        logging.error(f"Kullanıcı alınamadı: {e}")
    return None


async def save_user(user):
    try:
        existing = supabase.table("users").select("*").eq("user_id", user.id).execute()

        if existing.data:
            supabase.table("users").update(
                {
                    "username": safe_username(user),
                }
            ).eq("user_id", user.id).execute()
        else:
            supabase.table("users").insert(
                {
                    "user_id": user.id,
                    "username": safe_username(user),
                    "accepted_terms": False,
                    "active_coupon": None,
                }
            ).execute()

    except Exception as e:
        logging.error(f"Kullanıcı kaydedilemedi: {e}")


async def user_accepted_terms(user_id):
    row = await get_user_row(user_id)
    if not row:
        return False
    return bool(row.get("accepted_terms"))


async def show_terms(message):
    keyboard = [
        [InlineKeyboardButton("✅ Kabul Ediyorum", callback_data="accept_terms")]
    ]

    await message.reply_text(
        "⚠️ Kurallar ve Kullanım Onayı\n\n"
        "Bu bot üzerinden verilen VIP erişimler yalnızca yasal, rızaya dayalı ve kurallara uygun içerikler içindir.\n\n"
        "Devam ederek kuralları kabul etmiş olursun.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def get_channel(channel_id):
    try:
        result = (
            supabase.table("channels")
            .select("*")
            .eq("id", channel_id)
            .single()
            .execute()
        )
        return result.data
    except Exception as e:
        logging.error(f"Kanal alınamadı: {e}")
        return None


async def create_one_time_invite_link(context, ch, user_id):
    chat_id_raw = ch.get("chat_id")
    if not chat_id_raw:
        return None

    chat_id = int(chat_id_raw)

    expire_timestamp = int(
        (now_utc() + timedelta(minutes=INVITE_LINK_EXPIRE_MINUTES)).timestamp()
    )

    invite = await context.bot.create_chat_invite_link(
        chat_id=chat_id,
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
        chat_id = int(chat_id_raw)

        await context.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
        )

        await context.bot.unban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            only_if_banned=True,
        )

        return True

    except Exception as e:
        logging.error(f"Kullanıcı kanaldan çıkarılamadı: {e}")
        return False


async def expire_old_subscriptions_job(context: ContextTypes.DEFAULT_TYPE):
    await expire_old_subscriptions(context)


async def expire_old_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    try:
        data = (
            supabase.table("subscriptions")
            .select("*")
            .eq("status", "active")
            .execute()
        )

        current_time = now_utc()

        for sub in data.data:
            end = parse_dt(sub.get("end_date"))

            if end and end < current_time:
                ch = await get_channel(sub["channel_id"])

                if ch:
                    await remove_user_from_channel(
                        context=context,
                        ch=ch,
                        user_id=sub["user_id"],
                    )

                supabase.table("subscriptions").update(
                    {"status": "expired"}
                ).eq("id", sub["id"]).execute()

                try:
                    await context.bot.send_message(
                        chat_id=sub["user_id"],
                        text="⛔ VIP üyelik süren bitti. Yenilemek için bot üzerinden tekrar satın alabilirsin."
                    )
                except Exception:
                    pass

    except Exception as e:
        logging.error(f"Üyelik süre kontrol hatası: {e}")


async def warning_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        data = (
            supabase.table("subscriptions")
            .select("*")
            .eq("status", "active")
            .execute()
        )

        current_time = now_utc()

        for sub in data.data:
            end = parse_dt(sub.get("end_date"))
            if not end:
                continue

            remaining = end - current_time
            channel_id = sub["channel_id"]
            user_id = sub["user_id"]

            ch = await get_channel(channel_id)
            channel_name = ch["name"] if ch else f"Kanal ID {channel_id}"

            keyboard = [
                [
                    InlineKeyboardButton(
                        "⭐ Üyeliği Uzat",
                        callback_data=f"buy_{channel_id}"
                    )
                ]
            ]

            if remaining <= timedelta(days=1) and not sub.get("warn_1d_sent"):
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "⏳ VIP üyeliğin 1 gün içinde bitiyor.\n\n"
                            f"📢 Kanal: {channel_name}\n"
                            "Yenilemek için aşağıdaki butona bas."
                        ),
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )

                    supabase.table("subscriptions").update(
                        {"warn_1d_sent": True}
                    ).eq("id", sub["id"]).execute()
                except Exception as e:
                    logging.error(f"1 gün uyarısı gönderilemedi: {e}")

            elif remaining <= timedelta(days=3) and not sub.get("warn_3d_sent"):
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            "⏳ VIP üyeliğin 3 gün içinde bitiyor.\n\n"
                            f"📢 Kanal: {channel_name}\n"
                            "Yenilemek için aşağıdaki butona bas."
                        ),
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )

                    supabase.table("subscriptions").update(
                        {"warn_3d_sent": True}
                    ).eq("id", sub["id"]).execute()
                except Exception as e:
                    logging.error(f"3 gün uyarısı gönderilemedi: {e}")

    except Exception as e:
        logging.error(f"Uyarı job hatası: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user)

    if not is_admin(user.id):
        accepted = await user_accepted_terms(user.id)
        if not accepted:
            await show_terms(update.message)
            return

    if is_admin(user.id):
        await update.message.reply_text(
            "👋 Pasha VIP admin sistemine hoş geldin.",
            reply_markup=ADMIN_MENU,
        )
    else:
        await update.message.reply_text(
            "👋 Pasha VIP sistemine hoş geldin.",
            reply_markup=MAIN_MENU,
        )


async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    await update.effective_message.reply_text(f"Chat ID:\n{chat.id}")


async def channel_id_reader(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.channel_post:
        return

    text = update.channel_post.text or ""

    if text.startswith("/id"):
        chat_id = update.channel_post.chat_id

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Chat ID:\n{chat_id}"
        )


async def open_admin_panel(message):
    maintenance = maintenance_on()
    maintenance_text = "AÇIK 🔧" if maintenance else "KAPALI ✅"

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
        [InlineKeyboardButton("🆘 Destek Talepleri", callback_data="admin_support")],
        [InlineKeyboardButton("❌ İptal Talepleri", callback_data="admin_cancel")],
        [InlineKeyboardButton(f"🔧 Bakım Modu: {maintenance_text}", callback_data="admin_maintenance")],
    ]

    await message.reply_text(
        "👑 Admin Panel\n\nBir işlem seç:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Yetkin yok.")
        return

    await open_admin_panel(update.message)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    user_id = user.id

    await save_user(user)
    await expire_old_subscriptions(context)

    if not is_admin(user_id):
        accepted = await user_accepted_terms(user_id)
        if not accepted:
            await show_terms(update.message)
            return

    mode = context.user_data.get("mode")

    if mode:
        await handle_text_mode(update, context)
        return

    if maintenance_on() and not is_admin(user_id):
        await update.message.reply_text("🔧 Bot şu anda bakım modunda. Lütfen daha sonra tekrar dene.")
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

        user_row = await get_user_row(user_id)
        active_coupon = user_row.get("active_coupon") if user_row else None

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

            await update.message.reply_text(
                f"📢 {ch['name']}\n"
                f"⭐ Fiyat: {base_price} Stars\n"
                f"✅ Ödenecek: {final_price} Stars\n"
                f"⏳ Süre: {duration} gün"
                f"{coupon_line}",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    elif text == "📅 Üyeliğim":
        data = (
            supabase.table("subscriptions")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )

        if not data.data:
            await update.message.reply_text("📅 Aktif üyelik bulunamadı.")
            return

        msg = "📅 Aktif üyeliklerin:\n\n"

        for sub in data.data:
            ch = await get_channel(sub["channel_id"])
            channel_name = ch["name"] if ch else f"Kanal ID {sub['channel_id']}"

            msg += (
                f"📢 Kanal: {channel_name}\n"
                f"Başlangıç: {sub['start_date']}\n"
                f"Bitiş: {sub['end_date']}\n"
                f"Durum: {sub['status']}\n\n"
            )

        await update.message.reply_text(msg)

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


async def handle_text_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    text = update.message.text.strip()
    user = update.effective_user
    user_id = user.id

    try:
        if mode == "add_channel":
            parts = text.split()
            if len(parts) < 4:
                await update.message.reply_text(
                    "❌ Format yanlış.\n\n"
                    "Şöyle yaz:\n"
                    "KanalAdı Fiyat ChatID SüreGün\n\n"
                    "Örnek:\n"
                    "VIP 2500 -1001234567890 30"
                )
                return

            name = parts[0]
            price = int(parts[1])
            chat_id = parts[2]
            duration = int(parts[3])

            supabase.table("channels").insert(
                {
                    "name": name,
                    "price": price,
                    "chat_id": chat_id,
                    "invite_link": "",
                    "duration_days": duration,
                    "active": True,
                }
            ).execute()

            context.user_data.clear()

            await update.message.reply_text(
                f"✅ Kanal eklendi!\n\n"
                f"📢 {name}\n"
                f"⭐ {price} Stars\n"
                f"🆔 Chat ID: {chat_id}\n"
                f"⏳ {duration} gün"
            )

        elif mode == "edit_price":
            channel_id = context.user_data.get("channel_id")
            price = int(text)

            supabase.table("channels").update(
                {"price": price}
            ).eq("id", channel_id).execute()

            context.user_data.clear()
            await update.message.reply_text(f"✅ Fiyat güncellendi: {price} ⭐")

        elif mode == "edit_duration":
            channel_id = context.user_data.get("channel_id")
            days = int(text)

            supabase.table("channels").update(
                {"duration_days": days}
            ).eq("id", channel_id).execute()

            context.user_data.clear()
            await update.message.reply_text(f"✅ Süre güncellendi: {days} gün")

        elif mode == "edit_chat":
            channel_id = context.user_data.get("channel_id")
            chat_id = text

            supabase.table("channels").update(
                {"chat_id": chat_id}
            ).eq("id", channel_id).execute()

            context.user_data.clear()
            await update.message.reply_text("✅ Chat ID güncellendi.")

        elif mode == "search_user":
            await search_user(update.message, text)
            context.user_data.clear()

        elif mode == "add_coupon":
            parts = text.split()
            if len(parts) < 4:
                await update.message.reply_text(
                    "❌ Format yanlış.\n\n"
                    "Şöyle yaz:\n"
                    "KOD Yüzdeİndirim SabitStarsİndirim MaxKullanım\n\n"
                    "Örnek:\n"
                    "PASHA50 50 0 100\n\n"
                    "MaxKullanım 0 olursa sınırsız."
                )
                return

            code = parts[0].upper()
            percent = int(parts[1])
            stars = int(parts[2])
            max_uses = int(parts[3])

            supabase.table("coupons").insert(
                {
                    "code": code,
                    "discount_percent": percent,
                    "discount_stars": stars,
                    "max_uses": max_uses,
                    "used_count": 0,
                    "active": True,
                }
            ).execute()

            context.user_data.clear()
            await update.message.reply_text(f"✅ Kupon oluşturuldu: {code}")

        elif mode == "custom_grant_days":
            target_user_id = context.user_data.get("target_user_id")
            channel_id = context.user_data.get("channel_id")
            days = int(text)

            context.user_data.clear()

            await grant_vip_to_user(
                message=update.message,
                context=context,
                target_user_id=target_user_id,
                channel_id=channel_id,
                custom_days=days,
            )

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

            supabase.table("users").update(
                {"active_coupon": code}
            ).eq("user_id", user_id).execute()

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
                chat_id=ADMIN_ID,
                text=(
                    "🆘 Yeni destek talebi!\n\n"
                    f"Kullanıcı: @{safe_username(user) or 'yok'}\n"
                    f"ID: {user_id}\n\n"
                    f"Mesaj:\n{text}"
                ),
            )

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("❌ İşlem sırasında hata oldu. Formatı kontrol et.")


async def create_cancel_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    created_any = False

    for sub in data.data:
        existing = (
            supabase.table("cancel_requests")
            .select("*")
            .eq("user_id", user_id)
            .eq("channel_id", sub["channel_id"])
            .eq("status", "pending")
            .execute()
        )

        if existing.data:
            continue

        supabase.table("cancel_requests").insert(
            {
                "user_id": user_id,
                "channel_id": sub["channel_id"],
                "status": "pending",
            }
        ).execute()

        created_any = True

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "❌ Yeni iptal talebi!\n\n"
                f"Kullanıcı ID: {user_id}\n"
                f"Kanal ID: {sub['channel_id']}\n\n"
                "Admin panelden onaylayabilir veya reddedebilirsin."
            ),
        )

    if created_any:
        await update.message.reply_text("✅ İptal talebin admin onayına gönderildi.")
    else:
        await update.message.reply_text("⚠️ Zaten bekleyen iptal talebin var.")


async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "accept_terms":
        user_id = query.from_user.id

        supabase.table("users").update(
            {"accepted_terms": True}
        ).eq("user_id", user_id).execute()

        await query.message.reply_text(
            "✅ Kuralları kabul ettin. Menüden devam edebilirsin.",
            reply_markup=MAIN_MENU,
        )
        return

    if data.startswith("buy_"):
        await handle_buy(query, context)
        return

    if data.startswith("cancel_"):
        await handle_cancel_admin(query, context)
        return

    if data.startswith("support_close_"):
        if not is_admin(query.from_user.id):
            await query.message.reply_text("❌ Yetkin yok.")
            return

        request_id = int(data.split("_")[2])
        supabase.table("support_requests").update(
            {"status": "closed"}
        ).eq("id", request_id).execute()

        await query.message.reply_text("✅ Destek talebi kapatıldı.")
        return

    if not is_admin(query.from_user.id):
        await query.message.reply_text("❌ Yetkin yok.")
        return

    if data == "admin_add":
        context.user_data["mode"] = "add_channel"

        await query.message.reply_text(
            "➕ Kanal bilgilerini tek mesaj olarak yaz:\n\n"
            "KanalAdı Fiyat ChatID SüreGün\n\n"
            "Örnek:\n"
            "VIP 2500 -1001234567890 30\n\n"
            "Not: Kanal adı boşluk içermesin."
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
            "PASHA50 50 0 100\n\n"
            "MaxKullanım 0 olursa sınırsız."
        )

    elif data.startswith("coupon_toggle_"):
        coupon_id = int(data.split("_")[2])
        result = supabase.table("coupons").select("*").eq("id", coupon_id).single().execute()
        coupon = result.data

        if coupon:
            supabase.table("coupons").update(
                {"active": not bool(coupon.get("active"))}
            ).eq("id", coupon_id).execute()

        await query.message.reply_text("✅ Kupon durumu değiştirildi.")

    elif data == "admin_support":
        await support_requests_message(query.message)

    elif data == "admin_cancel":
        await cancel_requests_message(query.message)

    elif data == "admin_maintenance":
        current = maintenance_on()
        set_setting("maintenance", "off" if current else "on")
        await query.message.reply_text("✅ Bakım modu değiştirildi.")
        await open_admin_panel(query.message)

    elif data == "admin_grant":
        await show_users_for_grant(query.message)

    elif data.startswith("ch_delete_"):
        channel_id = int(data.split("_")[2])
        supabase.table("channels").delete().eq("id", channel_id).execute()
        await query.message.reply_text(f"✅ Kanal silindi. ID: {channel_id}")

    elif data.startswith("ch_toggle_"):
        channel_id = int(data.split("_")[2])
        result = supabase.table("channels").select("*").eq("id", channel_id).single().execute()
        ch = result.data
        if ch:
            supabase.table("channels").update(
                {"active": not bool(ch.get("active"))}
            ).eq("id", channel_id).execute()
        await query.message.reply_text("✅ Kanal aktif/pasif durumu değiştirildi.")

    elif data.startswith("ch_price_"):
        channel_id = int(data.split("_")[2])
        context.user_data["mode"] = "edit_price"
        context.user_data["channel_id"] = channel_id
        await query.message.reply_text("💰 Yeni fiyatı yaz. Örnek: 3000")

    elif data.startswith("ch_duration_"):
        channel_id = int(data.split("_")[2])
        context.user_data["mode"] = "edit_duration"
        context.user_data["channel_id"] = channel_id
        await query.message.reply_text("⏳ Yeni süreyi gün olarak yaz. Örnek: 60")

    elif data.startswith("ch_chat_"):
        channel_id = int(data.split("_")[2])
        context.user_data["mode"] = "edit_chat"
        context.user_data["channel_id"] = channel_id
        await query.message.reply_text("🆔 Yeni Chat ID yaz. Örnek: -1001234567890")

    elif data.startswith("grant_user_"):
        target_user_id = int(data.split("_")[2])
        await show_channels_for_grant(query.message, target_user_id)

    elif data.startswith("grant_channel_"):
        parts = data.split("_")
        target_user_id = int(parts[2])
        channel_id = int(parts[3])
        await show_grant_duration(query.message, target_user_id, channel_id)

    elif data.startswith("grant_days_"):
        parts = data.split("_")
        target_user_id = int(parts[2])
        channel_id = int(parts[3])
        days = int(parts[4])

        await grant_vip_to_user(
            message=query.message,
            context=context,
            target_user_id=target_user_id,
            channel_id=channel_id,
            custom_days=days,
        )

    elif data.startswith("grant_custom_"):
        parts = data.split("_")
        target_user_id = int(parts[2])
        channel_id = int(parts[3])

        context.user_data["mode"] = "custom_grant_days"
        context.user_data["target_user_id"] = target_user_id
        context.user_data["channel_id"] = channel_id

        await query.message.reply_text("⏳ Kaç günlük VIP vermek istiyorsun? Örnek: 14")


async def list_channels_manage(message):
    data = (
        supabase.table("channels")
        .select("*")
        .order("id")
        .execute()
    )

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
                InlineKeyboardButton("Aç/Kapat", callback_data=f"ch_toggle_{ch['id']}"),
            ],
            [
                InlineKeyboardButton("🗑️ Sil", callback_data=f"ch_delete_{ch['id']}"),
            ],
        ]

        await message.reply_text(
            f"📢 Kanal\n\n"
            f"ID: {ch['id']}\n"
            f"Ad: {ch['name']}\n"
            f"Fiyat: {ch['price']} ⭐\n"
            f"Süre: {ch.get('duration_days') or DEFAULT_DURATION_DAYS} gün\n"
            f"Chat ID: {ch.get('chat_id')}\n"
            f"Durum: {active_text}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def show_users_for_grant(message):
    data = (
        supabase.table("users")
        .select("*")
        .order("id", desc=True)
        .limit(20)
        .execute()
    )

    if not data.data:
        await message.reply_text("👥 Henüz kullanıcı yok. Kullanıcı önce /start yazmalı.")
        return

    for u in data.data:
        username = f"@{u['username']}" if u.get("username") else "username yok"

        keyboard = [
            [
                InlineKeyboardButton(
                    "🎁 Bu kullanıcıya VIP ver",
                    callback_data=f"grant_user_{u['user_id']}",
                )
            ]
        ]

        await message.reply_text(
            f"👤 Kullanıcı\n\n"
            f"ID: {u['user_id']}\n"
            f"Username: {username}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def show_channels_for_grant(message, target_user_id):
    data = (
        supabase.table("channels")
        .select("*")
        .eq("active", True)
        .order("id")
        .execute()
    )

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

    await message.reply_text(
        "⏳ VIP süresini seç:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def grant_vip_to_user(message, context, target_user_id, channel_id, custom_days=None):
    ch = await get_channel(channel_id)

    if not ch:
        await message.reply_text("❌ Kanal bulunamadı.")
        return

    duration_days = int(custom_days or ch.get("duration_days") or DEFAULT_DURATION_DAYS)
    current_time = now_utc()

    existing = (
        supabase.table("subscriptions")
        .select("*")
        .eq("user_id", target_user_id)
        .eq("channel_id", channel_id)
        .eq("status", "active")
        .execute()
    )

    if existing.data:
        sub = existing.data[0]
        old_end = parse_dt(sub.get("end_date")) or current_time
        base_date = old_end if old_end > current_time else current_time
        new_end = base_date + timedelta(days=duration_days)

        supabase.table("subscriptions").update(
            {
                "end_date": new_end.isoformat(),
                "status": "active",
                "price": 0,
                "warn_3d_sent": False,
                "warn_1d_sent": False,
            }
        ).eq("id", sub["id"]).execute()

        start_date = sub["start_date"]
        end_date = new_end.isoformat()

    else:
        start = current_time
        end = start + timedelta(days=duration_days)

        supabase.table("subscriptions").insert(
            {
                "user_id": target_user_id,
                "channel_id": channel_id,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "status": "active",
                "price": 0,
                "warn_3d_sent": False,
                "warn_1d_sent": False,
            }
        ).execute()

        start_date = start.isoformat()
        end_date = end.isoformat()

    vip_link = None

    try:
        vip_link = await create_one_time_invite_link(
            context=context,
            ch=ch,
            user_id=target_user_id,
        )
    except Exception as e:
        logging.error(f"VIP link üretilemedi: {e}")

    if vip_link:
        supabase.table("subscriptions").update(
            {"generated_invite_link": vip_link}
        ).eq("user_id", target_user_id).eq("channel_id", channel_id).eq("status", "active").execute()

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
                chat_id=target_user_id,
                text=(
                    "🎁 Admin sana VIP erişim verdi!\n\n"
                    f"📢 Kanal: {ch['name']}\n"
                    f"🔗 Tek kullanımlık giriş linkin:\n{vip_link}\n\n"
                    f"Başlangıç: {start_date}\n"
                    f"Bitiş: {end_date}"
                ),
            )

            await message.reply_text("✅ VIP yetki verildi ve link kullanıcıya gönderildi.")

        except Exception:
            await message.reply_text(
                "✅ VIP yetki verildi ama kullanıcıya mesaj gönderilemedi.\n\n"
                "Muhtemelen kullanıcı botu başlatmamış.\n\n"
                f"Linki manuel gönder:\n{vip_link}"
            )

    else:
        await message.reply_text(
            "✅ VIP yetki verildi ama davet linki üretilemedi.\n\n"
            "Botun kanalda admin ve davet yetkisi olduğundan emin ol."
        )


async def get_coupon(code):
    if not code:
        return None

    try:
        result = supabase.table("coupons").select("*").eq("code", code.upper()).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        logging.error(f"Kupon alınamadı: {e}")

    return None


async def calculate_price(user_id, base_price):
    user_row = await get_user_row(user_id)
    code = user_row.get("active_coupon") if user_row else None

    if not code:
        return base_price, None, None

    coupon = await get_coupon(code)

    if not coupon or not coupon.get("active"):
        return base_price, None, None

    max_uses = int(coupon.get("max_uses") or 0)
    used = int(coupon.get("used_count") or 0)

    if max_uses > 0 and used >= max_uses:
        return base_price, None, None

    percent = int(coupon.get("discount_percent") or 0)
    stars = int(coupon.get("discount_stars") or 0)

    final_price = base_price

    if percent > 0:
        final_price = int(final_price * (100 - percent) / 100)

    if stars > 0:
        final_price = final_price - stars

    if final_price < 1:
        final_price = 1

    discount_text = f"%{percent} indirim" if percent > 0 else f"{stars} Stars indirim"

    return final_price, code.upper(), discount_text


async def handle_buy(query, context):
    if maintenance_on() and not is_admin(query.from_user.id):
        await query.message.reply_text("🔧 Bot bakım modunda. Satın alma geçici olarak kapalı.")
        return

    channel_id = int(query.data.split("_")[1])
    ch = await get_channel(channel_id)

    if not ch or not ch.get("active"):
        await query.message.reply_text("❌ Kanal bulunamadı veya pasif.")
        return

    base_price = int(ch["price"])
    final_price, coupon_code, discount_text = await calculate_price(query.from_user.id, base_price)

    payload_coupon = coupon_code if coupon_code else "NONE"
    payload = f"vip_{channel_id}_{final_price}_{payload_coupon}"

    desc = f"{ch.get('duration_days') or DEFAULT_DURATION_DAYS} günlük VIP üyelik."
    if coupon_code:
        desc += f" Kupon: {coupon_code}"

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=f"{ch['name']} VIP Üyelik",
        description=desc,
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[
            LabeledPrice(
                label=ch["name"],
                amount=final_price,
            )
        ],
    )


async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = update.message.successful_payment.invoice_payload
    user = update.effective_user
    user_id = user.id

    parts = payload.split("_", 3)
    channel_id = int(parts[1])
    paid_price = int(parts[2])
    coupon_code = parts[3] if len(parts) >= 4 and parts[3] != "NONE" else None

    ch = await get_channel(channel_id)

    if not ch:
        await update.message.reply_text("✅ Ödeme alındı ama kanal bulunamadı. Admin ile iletişime geç.")
        return

    duration_days = int(ch.get("duration_days") or DEFAULT_DURATION_DAYS)
    current_time = now_utc()

    existing = (
        supabase.table("subscriptions")
        .select("*")
        .eq("user_id", user_id)
        .eq("channel_id", channel_id)
        .eq("status", "active")
        .execute()
    )

    if existing.data:
        sub = existing.data[0]
        old_end = parse_dt(sub.get("end_date")) or current_time
        base_date = old_end if old_end > current_time else current_time
        new_end = base_date + timedelta(days=duration_days)

        supabase.table("subscriptions").update(
            {
                "end_date": new_end.isoformat(),
                "price": paid_price,
                "status": "active",
                "warn_3d_sent": False,
                "warn_1d_sent": False,
            }
        ).eq("id", sub["id"]).execute()

        start_date = sub["start_date"]
        end_date = new_end.isoformat()

    else:
        start = current_time
        end = start + timedelta(days=duration_days)

        supabase.table("subscriptions").insert(
            {
                "user_id": user_id,
                "channel_id": channel_id,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "status": "active",
                "price": paid_price,
                "warn_3d_sent": False,
                "warn_1d_sent": False,
            }
        ).execute()

        start_date = start.isoformat()
        end_date = end.isoformat()

    vip_link = None

    try:
        vip_link = await create_one_time_invite_link(
            context=context,
            ch=ch,
            user_id=user_id,
        )
    except Exception as e:
        logging.error(f"Davet linki üretilemedi: {e}")

    if vip_link:
        supabase.table("subscriptions").update(
            {
                "generated_invite_link": vip_link,
            }
        ).eq("user_id", user_id).eq("channel_id", channel_id).eq("status", "active").execute()

    supabase.table("sales").insert(
        {
            "user_id": user_id,
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
            used = int(coupon.get("used_count") or 0)
            supabase.table("coupons").update(
                {"used_count": used + 1}
            ).eq("id", coupon["id"]).execute()

        supabase.table("users").update(
            {"active_coupon": None}
        ).eq("user_id", user_id).execute()

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            "✅ Yeni satış!\n\n"
            f"Kullanıcı: @{safe_username(user) or 'yok'}\n"
            f"User ID: {user_id}\n"
            f"Kanal: {ch['name']}\n"
            f"Fiyat: {paid_price} Stars\n"
            f"Kupon: {coupon_code or 'Yok'}\n"
            f"Bitiş: {end_date}"
        ),
    )

    if vip_link:
        await update.message.reply_text(
            "✅ Ödeme başarılı!\n\n"
            f"📢 Kanal: {ch['name']}\n"
            f"🔗 Tek kullanımlık VIP giriş linkin:\n{vip_link}\n\n"
            f"⚠️ Link {INVITE_LINK_EXPIRE_MINUTES} dakika geçerlidir ve sadece 1 kişi kullanabilir.\n\n"
            f"Başlangıç: {start_date}\n"
            f"Bitiş: {end_date}"
        )
    else:
        await update.message.reply_text(
            "✅ Ödeme başarılı fakat otomatik davet linki üretilemedi.\n\n"
            "Admin ile iletişime geç.\n\n"
            "Muhtemel sebep: Bot VIP kanalda admin değil veya davet yetkisi yok."
        )

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "⚠️ Davet linki üretilemedi!\n\n"
                f"Kullanıcı ID: {user_id}\n"
                f"Kanal: {ch['name']}\n"
                f"Kanal ID: {channel_id}"
            ),
        )


async def sales_message(message):
    data = (
        supabase.table("sales")
        .select("*")
        .order("id", desc=True)
        .limit(20)
        .execute()
    )

    if not data.data:
        await message.reply_text("📊 Henüz satış yok.")
        return

    text = "📊 Son kayıtlar:\n\n"

    for s in data.data:
        text += (
            f"ID: {s['id']}\n"
            f"Kullanıcı: @{s.get('username') or 'yok'}\n"
            f"Kullanıcı ID: {s['user_id']}\n"
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

    today_count = 0
    today_stars = 0
    month_count = 0
    month_stars = 0
    total_count = 0
    total_stars = 0

    for s in data.data:
        price = int(s.get("price") or 0)
        created = str(s.get("created_at") or "")

        total_count += 1
        total_stars += price

        if created.startswith(today):
            today_count += 1
            today_stars += price

        if created.startswith(month):
            month_count += 1
            month_stars += price

    await message.reply_text(
        "📈 Satış Raporu\n\n"
        f"Bugün satış: {today_count}\n"
        f"Bugün Stars: {today_stars}\n\n"
        f"Bu ay satış: {month_count}\n"
        f"Bu ay Stars: {month_stars}\n\n"
        f"Toplam satış: {total_count}\n"
        f"Toplam Stars: {total_stars}"
    )


async def channel_stats_message(message):
    sales = supabase.table("sales").select("*").execute()

    if not sales.data:
        await message.reply_text("📢 Henüz kanal satışı yok.")
        return

    stats = {}

    for s in sales.data:
        channel_id = s["channel_id"]
        price = int(s.get("price") or 0)

        if channel_id not in stats:
            stats[channel_id] = {"count": 0, "stars": 0}

        stats[channel_id]["count"] += 1
        stats[channel_id]["stars"] += price

    text = "📢 Kanal Bazlı İstatistik\n\n"

    for channel_id, value in stats.items():
        ch = await get_channel(channel_id)
        name = ch["name"] if ch else f"Kanal ID {channel_id}"

        text += (
            f"📢 {name}\n"
            f"Satış: {value['count']}\n"
            f"Stars: {value['stars']}\n\n"
        )

    await message.reply_text(text)


async def users_message(message):
    data = (
        supabase.table("users")
        .select("*")
        .order("id", desc=True)
        .limit(30)
        .execute()
    )

    if not data.data:
        await message.reply_text("👥 Henüz kullanıcı yok.")
        return

    text = "👥 Kullanıcılar:\n\n"

    for u in data.data:
        username = f"@{u['username']}" if u.get("username") else "username yok"
        text += f"ID: {u['user_id']} | {username}\n"

    await message.reply_text(text)


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


async def show_user_detail(message, user_row):
    user_id = user_row["user_id"]
    username = f"@{user_row['username']}" if user_row.get("username") else "username yok"

    subs = (
        supabase.table("subscriptions")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )

    text = (
        "👤 Kullanıcı Detayı\n\n"
        f"ID: {user_id}\n"
        f"Username: {username}\n\n"
    )

    if subs.data:
        text += "Üyelikler:\n"
        for sub in subs.data:
            ch = await get_channel(sub["channel_id"])
            ch_name = ch["name"] if ch else f"Kanal ID {sub['channel_id']}"
            text += (
                f"- {ch_name} | {sub['status']} | Bitiş: {sub['end_date']}\n"
            )
    else:
        text += "Üyelik yok.\n"

    keyboard = [
        [
            InlineKeyboardButton(
                "🎁 VIP Ver",
                callback_data=f"grant_user_{user_id}",
            )
        ]
    ]

    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def coupons_message(message):
    data = supabase.table("coupons").select("*").order("id", desc=True).execute()

    keyboard = [
        [InlineKeyboardButton("➕ Kupon Oluştur", callback_data="coupon_add")]
    ]

    if not data.data:
        await message.reply_text(
            "🎟️ Henüz kupon yok.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    await message.reply_text("🎟️ Kuponlar:", reply_markup=InlineKeyboardMarkup(keyboard))

    for c in data.data:
        status = "Aktif ✅" if c.get("active") else "Pasif ⛔"

        kb = [
            [InlineKeyboardButton("Aç/Kapat", callback_data=f"coupon_toggle_{c['id']}")]
        ]

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
        keyboard = [
            [InlineKeyboardButton("✅ Kapat", callback_data=f"support_close_{r['id']}")]
        ]

        await message.reply_text(
            f"🆘 Destek Talebi\n\n"
            f"ID: {r['id']}\n"
            f"Kullanıcı: @{r.get('username') or 'yok'}\n"
            f"User ID: {r['user_id']}\n"
            f"Mesaj:\n{r['message']}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def cancel_requests_message(message):
    data = (
        supabase.table("cancel_requests")
        .select("*")
        .eq("status", "pending")
        .execute()
    )

    if not data.data:
        await message.reply_text("❌ Bekleyen iptal talebi yok.")
        return

    for req in data.data:
        keyboard = [
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
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def handle_cancel_admin(query, context):
    if not is_admin(query.from_user.id):
        await query.message.reply_text("❌ Yetkin yok.")
        return

    parts = query.data.split("_")
    action = parts[1]
    request_id = int(parts[2])

    result = (
        supabase.table("cancel_requests")
        .select("*")
        .eq("id", request_id)
        .single()
        .execute()
    )

    req = result.data

    if not req:
        await query.message.reply_text("❌ Talep bulunamadı.")
        return

    ch = await get_channel(req["channel_id"])

    if action == "ok":
        supabase.table("cancel_requests").update(
            {"status": "approved"}
        ).eq("id", request_id).execute()

        supabase.table("subscriptions").update(
            {"status": "cancelled"}
        ).eq("user_id", req["user_id"]).eq("channel_id", req["channel_id"]).execute()

        if ch:
            await remove_user_from_channel(
                context=context,
                ch=ch,
                user_id=req["user_id"],
            )

        await query.message.reply_text("✅ İptal talebi onaylandı.")

        try:
            await context.bot.send_message(
                chat_id=req["user_id"],
                text="✅ Üyelik iptal talebin onaylandı."
            )
        except Exception:
            pass

    elif action == "no":
        supabase.table("cancel_requests").update(
            {"status": "rejected"}
        ).eq("id", request_id).execute()

        await query.message.reply_text("❌ İptal talebi reddedildi.")

        try:
            await context.bot.send_message(
                chat_id=req["user_id"],
                text="❌ Üyelik iptal talebin reddedildi."
            )
        except Exception:
            pass


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
