import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = "8690578902:AAFcqZ7_-WXwCE4rtfq7tmgOANuZbIfiqpI"

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⭐ VIP Satın Al", url="https://t.me/+x8Vw2rdnTi81YzQ0")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🚀 VIP kanala katılmak için butona bas:",
        reply_markup=reply_markup
    )

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))

print("Bot çalışıyor...")
app.run_polling()
