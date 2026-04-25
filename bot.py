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

logging.basicConfig(level=logging.INFO)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["📢 VIP Kanallar"],
        ["📅 Üyeliğim", "❌ İptal Talebi"],
        ["ℹ️ Yardım"],
    ],
    resize_keyboard=True,
)


def now_utc():
    return datetime.utcnow()


def parse_dt(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    try:
        supabase.table("users").upsert(
            {
                "user_id": user.id,
                "username": user.username,
            },
            on_conflict="user_id",
        ).execute()
    except Exception as e:
        logging.error(e)

    await update.message.reply_text(
        "👋 Pasha VIP sistemine hoş geldin.",
        reply_markup=MAIN_MENU,
    )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
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

    if query.from_user.id != ADMIN_ID:
        await query.message.reply_text("❌ Yetkin yok.")
        return

    if query.data == "admin_add":
        await query.message.reply_text(
            "➕ Kanal ekle:\n"
            "/ekle KanalAdı Fiyat Link SüreGün\n\n"
            "Örnek:\n"
            "/ekle VIP 2500 https://t.me/+xxxx 30"
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
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkin yok.")
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "❌ Kullanım:\n"
            "/ekle KanalAdı Fiyat Link SüreGün\n\n"
            "Örnek:\n"
            "/ekle VIP 2500 https://t.me/+xxxx 30"
        )
        return

    name = context.args[0]
    price = int(context.args[1])
    link = context.args[2]
    duration = int(context.args[3]) if len(context.args) >= 4 else 30

    supabase.table("channels").insert(
        {
            "name": name,
            "price": price,
            "invite_link": link,
            "duration_days": duration,
        }
    ).execute()

    await update.message.reply_text(
        f"✅ Kanal eklendi!\n\n📢 {name}\n⭐ {price} Stars\n⏳ {duration} gün"
    )


async def delete_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkin yok.")
        return

    if len(context.args) < 1:
        await update.message.reply_text("❌ Kullanım: /sil KanalID")
        return

    channel_id = int(context.args[0])
    supabase.table("channels").delete().eq("id", channel_id).execute()

    await update.message.reply_text(f"✅ Kanal silindi. ID: {channel_id}")


async def change_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkin yok.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ Kullanım: /fiyat KanalID YeniFiyat")
        return

    channel_id = int(context.args[0])
    price = int(context.args[1])

    supabase.table("channels").update({"price": price}).eq("id", channel_id).execute()
    await update.message.reply_text(f"✅ Fiyat güncellendi: {price} ⭐")


async def change_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Kullanım: /link KanalID YeniLink")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ Kullanım: /link KanalID YeniLink")
        return

    channel_id = int(context.args[0])
    link = context.args[1]

    supabase.table("channels").update({"invite_link": link}).eq("id", channel_id).execute()
    await update.message.reply_text("✅ Link güncellendi.")


async def change_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkin yok.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ Kullanım: /sure KanalID Gun")
        return

    channel_id = int(context.args[0])
    days = int(context.args[1])

    supabase.table("channels").update({"duration_days": days}).eq("id", channel_id).execute()
    await update.message.reply_text(f"✅ Süre güncellendi: {days} gün")


async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkin yok.")
        return

    await list_channels_message(update.message)


async def list_channels_message(message):
    data = supabase.table("channels").select("*").order("id").execute()

    if not data.data:
        await message.reply_text("📢 Henüz kanal yok.")
        return

    text = "📢 Kanallar:\n\n"
    for ch in data.data:
        text += (
            f"ID: {ch['id']}\n"
            f"Ad: {ch['name']}\n"
            f"Fiyat: {ch['price']} ⭐\n"
            f"Süre: {ch.get('duration_days', 30)} gün\n"
            f"Link: {ch['invite_link']}\n\n"
        )

    await message.reply_text(text)


async def sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkin yok.")
        return

    await sales_message(update.message)


async def sales_message(message):
    data = supabase.table("sales").select("*").order("id", desc=True).limit(20).execute()

    if not data.data:
        await message.reply_text("📊 Henüz satış yok.")
        return

    text = "📊 Son satışlar:\n\n"
    for s in data.data:
        text += (
            f"ID: {s['id']}\n"
            f"Kullanıcı: {s.get('username') or s['user_id']}\n"
            f"Kanal ID: {s['channel_id']}\n"
            f"Fiyat: {s['price']} ⭐\n"
            f"Tarih: {s['created_at']}\n\n"
        )

    await message.reply_text(text)


async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkin yok.")
        return

    await users_message(update.message)


async def users_message(message):
    data = supabase.table("users").select("*").order("id", desc=True).limit(30).execute()

    if not data.data:
        await message.reply_text("👥 Henüz kullanıcı yok.")
        return

    text = "👥 Kullanıcılar:\n\n"
    for u in data.data:
        text += f"ID: {u['user_id']} | @{u.get('username')}\n"

    await message.reply_text(text)


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    await expire_old_subscriptions()

    if text == "📢 VIP Kanallar":
        data = supabase.table("channels").select("*").order("id").execute()

        if not data.data:
            await update.message.reply_text("📢 Henüz kanal eklenmedi.")
            return

        for ch in data.data:
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
                f"⏳ Süre: {ch.get('duration_days', 30)} gün",
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
            ch_result = (
                supabase.table("channels")
                .select("*")
                .eq("id", sub["channel_id"])
                .single()
                .execute()
            )
            ch = ch_result.data
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
            await update.message.reply_text("❌ Aktif üyelik yok.")
            return

        for sub in data.data:
            supabase.table("cancel_requests").insert(
                {
                    "user_id": user_id,
                    "channel_id": sub["channel_id"],
                    "status": "pending",
                }
            ).execute()

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "❌ Yeni iptal talebi!\n\n"
                    f"Kullanıcı ID: {user_id}\n"
                    f"Kanal ID: {sub['channel_id']}\n\n"
                    "Admin panelden yönet."
                ),
            )

        await update.message.reply_text("✅ İptal talebin admin onayına gönderildi.")

    elif text == "ℹ️ Yardım":
        await update.message.reply_text("Destek için admin ile iletişime geç.")


async def buy_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    channel_id = int(query.data.split("_")[1])

    result = (
        supabase.table("channels")
        .select("*")
        .eq("id", channel_id)
        .single()
        .execute()
    )
    ch = result.data

    if not ch:
        await query.message.reply_text("❌ Kanal bulunamadı.")
        return

    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=f"{ch['name']} VIP Üyelik",
        description=f"{ch.get('duration_days', 30)} günlük VIP üyelik.",
        payload=f"vip_{channel_id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(ch["name"], int(ch["price"]))],
    )


async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = update.message.successful_payment.invoice_payload
    user = update.effective_user
    user_id = user.id
    channel_id = int(payload.split("_")[1])

    result = (
        supabase.table("channels")
        .select("*")
        .eq("id", channel_id)
        .single()
        .execute()
    )
    ch = result.data

    if not ch:
        await update.message.reply_text("✅ Ödeme alındı ama kanal bulunamadı. Admin ile iletişime geç.")
        return

    duration_days = int(ch.get("duration_days", 30))
    price = int(ch["price"])

    existing = (
        supabase.table("subscriptions")
        .select("*")
        .eq("user_id", user_id)
        .eq("channel_id", channel_id)
        .eq("status", "active")
        .execute()
    )

    current_time = now_utc()

    if existing.data:
        sub = existing.data[0]
        old_end = parse_dt(sub["end_date"]) or current_time
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

    supabase.table("sales").insert(
        {
            "user_id": user_id,
            "username": user.username,
            "channel_id": channel_id,
            "price": price,
            "payment_payload": payload,
        }
    ).execute()

    await update.message.reply_text(
        "✅ Ödeme başarılı!\n\n"
        f"📢 Kanal: {ch['name']}\n"
        f"🔗 VIP giriş linkin:\n{ch['invite_link']}\n\n"
        f"Başlangıç: {start_date}\n"
        f"Bitiş: {end_date}"
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


async def cancel_admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
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

    if action == "ok":
        supabase.table("cancel_requests").update({"status": "approved"}).eq("id", request_id).execute()

        supabase.table("subscriptions").update({"status": "cancelled"}).eq("user_id", req["user_id"]).eq("channel_id", req["channel_id"]).execute()

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


async def expire_old_subscriptions():
    data = (
        supabase.table("subscriptions")
        .select("*")
        .eq("status", "active")
        .execute()
    )

    current_time = now_utc()

    for sub in data.data:
        end = parse_dt(sub["end_date"])
        if end and end < current_time:
            supabase.table("subscriptions").update({"status": "expired"}).eq("id", sub["id"]).execute()


app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))
app.add_handler(CommandHandler("ekle", add_channel))
app.add_handler(CommandHandler("sil", delete_channel))
app.add_handler(CommandHandler("fiyat", change_price))
app.add_handler(CommandHandler("link", change_link))
app.add_handler(CommandHandler("sure", change_duration))
app.add_handler(CommandHandler("kanallar", list_channels))
app.add_handler(CommandHandler("satislar", sales))
app.add_handler(CommandHandler("kullanicilar", users))

app.add_handler(CallbackQueryHandler(buy_button, pattern="^buy_"))
app.add_handler(CallbackQueryHandler(cancel_admin_buttons, pattern="^cancel_"))
app.add_handler(CallbackQueryHandler(admin_buttons, pattern="^admin_"))

app.add_handler(PreCheckoutQueryHandler(precheckout))
app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))

print("VIP bot çalışıyor...")
app.run_polling()
