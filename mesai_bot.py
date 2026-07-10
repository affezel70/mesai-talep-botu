from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = "8859190739:AAHxAZ8F0hPdQ3EDodRXsJ3Q09thgL8CeyY"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Mesai Talep Formuna Hoş Geldiniz.\n\n"
        "👤 Lütfen çalışan adınızı ve görevinizi aşağıdaki formatta yazınız.\n\n"
        "📝 Örnek:\n"
        "Rmt.Ayşe - Remote"
    )


async def mesaj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"✅ Bilgileriniz kaydedildi.\n\n"
        f"Kaydedilen bilgi:\n{update.message.text}"
    )


app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mesaj))

print("Bot çalışıyor...")

app.run_polling()
