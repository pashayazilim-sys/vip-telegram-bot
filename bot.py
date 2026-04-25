import logging
from telegram import (
    Update, ReplyKeyboardMarkup, InlineKeyboardButton,
    InlineKeyboardMarkup, LabeledPrice
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, PreCheckoutQueryHandler,
    ContextTypes, filters
)

TOKEN = "8661407355:AAGspKLwZznDJDm3eM9OQ_TpkrmkAi68mDg"
ADMIN_ID = 957422314

logging.basicConfig(level=logging.INFO)

channels = []

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["📢 VIP Kanallar"],
        ["📅 Üyeliğim", "❌ İptal Talebi"],
        ["ℹ️ Yardım"],
    ],
    resize_keyboard=True,
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Pasha VIP sistemine hoş geldin.",
        reply_markup=MAIN_MENU,
    )

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkin yok.")
        return

    keyboard = [
        [InlineKeyboardButton("➕ Kanal Ekle", callback_data="add")],
        [InlineKeyboardButton("📢 Kanalları Gör", callback_data="list")],
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

    if query.data == "add":
        await query.message.reply_text(
            "➕ Kanal eklemek için:\n"
            "/ekle KanalAdı Fiyat Link\n\n"
            "Örnek:\n"
            "/ekle VIP 2500 https://t.me/+xxxx"
        )

    elif query.data == "list":
        if not channels:
            await query.message.reply_text("📢 Henüz kanal yok.")
        else:
            text = "📢 Kanallar:\n\n"
            for i, ch in enumerate(channels):
                text += f"{i+1}. {ch['name']} - {ch['price']} ⭐\n{ch['link']}\n\n"
            await query.message.reply_text(text)

async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkin yok.")
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "❌ Kullanım:\n/ekle KanalAdı Fiyat Link"
        )
        return

    name = context.args[0]
    price = int(context.args[1])
    link = context.args[2]

    channels.append({
        "name": name,
        "price": price,
        "link": link
    })

    await update.message.reply_text(
        f"✅ Kanal eklendi:\n{name} - {price} ⭐"
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📢 VIP Kanallar":
        if not channels:
            await update.message.reply_text("📢 Henüz kanal eklenmedi.")
            return

        for i, ch in enumerate(channels):
            keyboard = [
                [InlineKeyboardButton(
                    f"⭐ {ch['price']} Stars ile Satın Al",
                    callback_data=f"buy_{i}"
                )]
            ]

            await update.message.reply_text(
                f"📢 {ch['name']}\n⭐ Fiyat: {ch['price']} Stars",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    elif text == "📅 Üyeliğim":
        await update.message.reply_text("📅 Aktif üyelik sistemi yakında.")

    elif text == "❌ İptal Talebi":
        await update.message.reply_text("❌ İptal sistemi yakında.")

    elif text == "ℹ️ Yardım":
        await update.message.reply_text("Destek için admin ile iletişime geç.")

async def buy_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("buy_"):
        index = int(query.data.split("_")[1])

        if index >= len(channels):
            await query.message.reply_text("❌ Kanal bulunamadı.")
            return

        ch = channels[index]

        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title=f"{ch['name']} VIP Üyelik",
            description="Ödeme sonrası VIP kanal linki otomatik gönderilir.",
            payload=f"vip_{index}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(ch["name"], ch["price"])],
        )

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payload = update.message.successful_payment.invoice_payload

    if payload.startswith("vip_"):
        index = int(payload.split("_")[1])

        if index < len(channels):
            ch = channels[index]

            await update.message.reply_text(
                "✅ Ödeme başarılı!\n\n"
                f"📢 Kanal: {ch['name']}\n"
                f"🔗 VIP giriş linkin:\n{ch['link']}\n\n"
                "Teşekkürler!"
            )
        else:
            await update.message.reply_text("✅ Ödeme alındı ama kanal bulunamadı. Admin ile iletişime geç.")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))
app.add_handler(CommandHandler("ekle", add_channel))
app.add_handler(CallbackQueryHandler(buy_button, pattern="^buy_"))
app.add_handler(CallbackQueryHandler(admin_buttons))
app.add_handler(PreCheckoutQueryHandler(precheckout))
app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))

print("VIP bot çalışıyor...")
app.run_polling()
