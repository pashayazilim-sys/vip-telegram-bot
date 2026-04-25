import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

TOKEN = "8661407355:AAGspKLwZznDJDm3eM9OQ_TpkrmkAi68mDg"
ADMIN_ID = 957422314

logging.basicConfig(level=logging.INFO)

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
        "👋 Pasha VIP sistemine hoş geldin.\n\n"
        "Buradan VIP kanalları görebilir, üyeliğini kontrol edebilir ve iptal talebi gönderebilirsin.",
        reply_markup=MAIN_MENU,
    )

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkin yok.")
        return

    keyboard = [
        [InlineKeyboardButton("➕ Kanal Ekle", callback_data="add")],
        [InlineKeyboardButton("📢 Kanalları Gör", callback_data="list")],
        [InlineKeyboardButton("❌ Talepler", callback_data="cancel")],
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
            "/ekle VIP 2500 https://t.me/+xxxx"
        )
    elif query.data == "list":
        await query.message.reply_text("📢 Henüz kanal yok.")
    elif query.data == "cancel":
        await query.message.reply_text("❌ İptal talebi yok.")

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📢 VIP Kanallar":
        await update.message.reply_text("📢 Henüz kanal eklenmedi.")
    elif text == "📅 Üyeliğim":
        await update.message.reply_text("📅 Aktif üyelik bulunamadı.")
    elif text == "❌ İptal Talebi":
        await update.message.reply_text(
            "❌ Şu anda aktif üyeliğin olmadığı için iptal talebi oluşturulamadı."
        )
    elif text == "ℹ️ Yardım":
        await update.message.reply_text("Destek için admin ile iletişime geç.")
    else:
        await update.message.reply_text("Menüden bir seçenek seçebilirsin.")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))
app.add_handler(CallbackQueryHandler(admin_buttons))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))

print("VIP bot çalışıyor...")
app.run_polling()
