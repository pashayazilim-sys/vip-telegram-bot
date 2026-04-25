import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = "8661407355:AAGspKLwZznDJDm3eM9OQ_TpkrmkAi68mDg"
ADMIN_ID = 957422314

logging.basicConfig(level=logging.INFO)

MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["📢 VIP Kanallar"],
        ["📅 Üyeliğim", "❌ İptal Talebi"],
        ["ℹ️ Yardım"]
    ],
    resize_keyboard=True
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Pasha VIP sistemine hoş geldin.\n\n"
        "Buradan VIP kanalları görebilir, üyeliğini kontrol edebilir ve iptal talebi gönderebilirsin.",
        reply_markup=MAIN_MENU
    )

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Yetkin yok.")
        return

    await update.message.reply_text(
        "👑 Admin Panel\n\n"
        "Yakında buradan kanal ekleme, fiyat değiştirme ve iptal taleplerini yönetme eklenecek."
    )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📢 VIP Kanallar":
        await update.message.reply_text("📢 Henüz kanal eklenmedi.")
    elif text == "📅 Üyeliğim":
        await update.message.reply_text("📅 Aktif üyelik bulunamadı.")
    elif text == "❌ İptal Talebi":
        await update.message.reply_text("❌ Şu anda aktif üyeliğin olmadığı için iptal talebi oluşturulamadı.")
    elif text == "ℹ️ Yardım":
        await update.message.reply_text("Destek için admin ile iletişime geç.")
    else:
        await update.message.reply_text("Menüden bir seçenek seçebilirsin.")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))

print("VIP bot çalışıyor...")
app.run_polling()
