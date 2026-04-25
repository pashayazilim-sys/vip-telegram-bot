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


# =========================
# ENV VARIABLES
# Railway Variables içinde olmalı:
# BOT_TOKEN
# SUPABASE_URL
# SUPABASE_KEY
# =========================

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


# =========================
# MENÜ
# =========================

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["📢 VIP Kanallar"],
        ["📅 Üyeliğim", "❌ İptal Talebi"],
        ["ℹ️ Yardım"],
    ],
    resize_keyboard=True,
)


# =========================
# HELPERS
# =========================

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


async def save_user(user):
    try:
        existing = (
            supabase.table("users")
            .select("*")
            .eq("user_id", user.id)
            .execute()
        )

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
                }
            ).execute()

    except Exception as e:
        logging.error(f"Kullanıcı kaydedilemedi: {e}")


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
    """
    Ödeme sonrası tek kullanımlık davet linki üretir.
    Botun VIP kanalda admin olması gerekir.
    """

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
    """
    Kullanıcıyı kanaldan çıkarır.
    Botun kanalda admin ve ban yetkisi olmalı.
    """

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
    """
    Süresi biten aktif üyelikleri expired yapar.
    Mümkünse kullanıcıyı kanaldan çıkarır.
    """

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

    except Exception as e:
        logging.error(f"Üyelik süre kontrol hatası: {e}")


# =========================
# USER COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    await save_user(user)

    await update.message.reply_text(
        "👋 Pasha VIP sistemine hoş geldin.\n\n"
        "VIP kanalları görebilir, üyeliğini kontrol edebilir ve iptal talebi gönderebilirsin.",
        reply_markup=MAIN_MENU,
    )


async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    VIP kanal chat ID bulmak için.
    Botu VIP kanala admin yap, kanalda /id yaz.
    """

    chat = update.effective_chat
    await update.effective_message.reply_text(f"Chat ID:\n{chat.id}")


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    await save_user(update.effective_user)
    await expire_old_subscriptions(context)

    if text == "📢 VIP Kanallar":
        data = (
            supabase.table("channels")
            .select("*")
            .order("id")
            .execute()
        )

        if not data.data:
            await update.message.reply_text("📢 Henüz VIP kanal eklenmedi.")
            return

        for ch in data.data:
            duration = ch.get("duration_days") or DEFAULT_DURATION_DAYS

            keyboard = [
                [
                    InlineKeyboardButton(
                        f"⭐ {ch['price']} Stars ile Satın Al",
                        callback_data=f"buy_{ch['id']}",
                    )
                ]
            ]

            await update.message.reply_text(
                f"📢 {ch['name']}\n"
                f"⭐ Fiyat: {ch['price']} Stars\n"
                f"⏳ Süre: {duration} gün",
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

    elif text == "ℹ️ Yardım":
        await update.message.reply_text(
            "ℹ️ Yardım\n\n"
            "📢 VIP Kanallar: Satın alınabilir kanalları gösterir.\n"
            "📅 Üyeliğim: Aktif üyeliklerini gösterir.\n"
            "❌ İptal Talebi: Admin onayına iptal talebi gönderir."
        )

    else:
        await update.message.reply_text("Menüden bir seçenek seçebilirsin.")


# =========================
# ADMIN PANEL
# =========================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Yetkin yok.")
        return

    keyboard = [
        [InlineKeyboardButton("➕ Kanal Ekle", callback_data="admin_add")],
        [InlineKeyboardButton("📢 Kanalları Gör", callback_data="admin_list")],
        [InlineKeyboardButton("📊 Satışlar", callback_data="admin_sales")],
        [InlineKeyboardButton("👥 Kullanıcılar", callback_data="admin_users")],
        [InlineKeyboardButton("❌ İptal Talepleri", callback_data="admin_cancel")],
    ]

    await update.message.reply_text(
        "👑 Admin Panel",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        await query.message.reply_text("❌ Yetkin yok.")
        return

    if query.data == "admin_add":
        await query.message.reply_text(
            "➕ Kanal ekle:\n\n"
            "/ekle KanalAdı Fiyat ChatID SüreGün\n\n"
            "Örnek:\n"
            "/ekle VIP 2500 -1001234567890 30\n\n"
            "ChatID almak için botu VIP kanala admin yap ve kanalda /id yaz."
        )

    elif query.data == "admin_list":
        await list_channels_message(query.message)

    elif query.data == "admin_sales":
        await sales_message(query.message)

    elif query.data == "admin_users":
        await users_message(query.message)

    elif query.data == "admin_cancel":
        await cancel_requests_message(query.message)


async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Yetkin yok.")
        return

    if len(context.args) < 4:
        await update.message.reply_text(
            "❌ Kullanım:\n"
            "/ekle KanalAdı Fiyat ChatID SüreGün\n\n"
            "Örnek:\n"
            "/ekle VIP 2500 -1001234567890 30"
        )
        return

    name = context.args[0]
    price = int(context.args[1])
    chat_id = context.args[2]
    duration = int(context.args[3])

    supabase.table("channels").insert(
        {
            "name": name,
            "price": price,
            "chat_id": chat_id,
            "invite_link": "",
            "duration_days": duration,
        }
    ).execute()

    await update.message.reply_text(
        f"✅ Kanal eklendi!\n\n"
        f"📢 {name}\n"
        f"⭐ {price} Stars\n"
        f"🆔 Chat ID: {chat_id}\n"
        f"⏳ {duration} gün"
    )


async def delete_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Yetkin yok.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("❌ Kullanım: /sil KanalID")
        return

    channel_id = int(context.args[0])

    supabase.table("channels").delete().eq("id", channel_id).execute()

    await update.message.reply_text(f"✅ Kanal silindi. ID: {channel_id}")


async def change_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Yetkin yok.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ Kullanım: /fiyat KanalID YeniFiyat")
        return

    channel_id = int(context.args[0])
    price = int(context.args[1])

    supabase.table("channels").update(
        {"price": price}
    ).eq("id", channel_id).execute()

    await update.message.reply_text(f"✅ Fiyat güncellendi: {price} ⭐")


async def change_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Yetkin yok.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ Kullanım: /sure KanalID Gün")
        return

    channel_id = int(context.args[0])
    days = int(context.args[1])

    supabase.table("channels").update(
        {"duration_days": days}
    ).eq("id", channel_id).execute()

    await update.message.reply_text(f"✅ Süre güncellendi: {days} gün")


async def change_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Yetkin yok.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ Kullanım: /chat KanalID ChatID")
        return

    channel_id = int(context.args[0])
    chat_id = context.args[1]

    supabase.table("channels").update(
        {"chat_id": chat_id}
    ).eq("id", channel_id).execute()

    await update.message.reply_text("✅ Chat ID güncellendi.")


async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Yetkin yok.")
        return

    await list_channels_message(update.message)


async def list_channels_message(message):
    data = (
        supabase.table("channels")
        .select("*")
        .order("id")
        .execute()
    )

    if not data.data:
        await message.reply_text("📢 Henüz kanal yok.")
        return

    text = "📢 Kanallar:\n\n"

    for ch in data.data:
        text += (
            f"ID: {ch['id']}\n"
            f"Ad: {ch['name']}\n"
            f"Fiyat: {ch['price']} ⭐\n"
            f"Süre: {ch.get('duration_days') or DEFAULT_DURATION_DAYS} gün\n"
            f"Chat ID: {ch.get('chat_id')}\n\n"
        )

    await message.reply_text(text)


async def sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Yetkin yok.")
        return

    await sales_message(update.message)


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

    text = "📊 Son satışlar:\n\n"

    for s in data.data:
        text += (
            f"Satış ID: {s['id']}\n"
            f"Kullanıcı: @{s.get('username') or 'yok'}\n"
            f"Kullanıcı ID: {s['user_id']}\n"
            f"Kanal ID: {s['channel_id']}\n"
            f"Fiyat: {s['price']} ⭐\n"
            f"Tarih: {s['created_at']}\n\n"
        )

    await message.reply_text(text)


async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Yetkin yok.")
        return

    await users_message(update.message)


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


# =========================
# STARS PAYMENT
# =========================

async def buy_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    channel_id = int(query.data.split("_")[1])
    ch = await get_channel(channel_id)

    if not ch:
        await query.message.reply_text("❌ Kanal bulunamadı.")
        return

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=f"{ch['name']} VIP Üyelik",
        description=f"{ch.get('duration_days') or DEFAULT_DURATION_DAYS} günlük VIP üyelik.",
        payload=f"vip_{channel_id}",
        provider_token="",
        currency="XTR",
        prices=[
            LabeledPrice(
                label=ch["name"],
                amount=int(ch["price"]),
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

    channel_id = int(payload.split("_")[1])
    ch = await get_channel(channel_id)

    if not ch:
        await update.message.reply_text(
            "✅ Ödeme alındı ama kanal bulunamadı. Admin ile iletişime geç."
        )
        return

    duration_days = int(ch.get("duration_days") or DEFAULT_DURATION_DAYS)
    price = int(ch["price"])

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
                "price": price,
                "status": "active",
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
                "price": price,
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
            "price": price,
            "payment_payload": payload,
        }
    ).execute()

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
            "Muhtemel sebep: Bot VIP kanalda admin değil veya Invite Users yetkisi yok."
        )

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "⚠️ Davet linki üretilemedi!\n\n"
                f"Kullanıcı ID: {user_id}\n"
                f"Kanal: {ch['name']}\n"
                f"Kanal ID: {channel_id}\n\n"
                "Botun VIP kanalda admin ve davet linki yetkisi olduğundan emin ol."
            ),
        )


# =========================
# CANCEL REQUESTS
# =========================

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


async def cancel_admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

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


# =========================
# APP
# =========================

app = ApplicationBuilder().token(TOKEN).build()

# User commands
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("id", get_chat_id))

# Admin commands
app.add_handler(CommandHandler("admin", admin))
app.add_handler(CommandHandler("ekle", add_channel))
app.add_handler(CommandHandler("sil", delete_channel))
app.add_handler(CommandHandler("fiyat", change_price))
app.add_handler(CommandHandler("sure", change_duration))
app.add_handler(CommandHandler("chat", change_chat_id))
app.add_handler(CommandHandler("kanallar", list_channels))
app.add_handler(CommandHandler("satislar", sales))
app.add_handler(CommandHandler("kullanicilar", users))

# Buttons
app.add_handler(CallbackQueryHandler(buy_button, pattern="^buy_"))
app.add_handler(CallbackQueryHandler(cancel_admin_buttons, pattern="^cancel_"))
app.add_handler(CallbackQueryHandler(admin_buttons, pattern="^admin_"))

# Payments
app.add_handler(PreCheckoutQueryHandler(precheckout))
app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

# Menu
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))

# Periodic membership expiry check
app.job_queue.run_repeating(
    expire_old_subscriptions_job,
    interval=3600,
    first=30,
)

print("VIP bot çalışıyor...")
app.run_polling()
