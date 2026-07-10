from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

TOKEN = "8859190739:AAHxAZ8F0hPdQ3EDodRXsJ3Q09thgL8CeyY"

NAME = 1

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Mesai Talep Formuna Hoş Geldiniz.\n\n"
        "👤 Lütfen çalışan adınızı ve görevinizi yazınız.\n\n"
        "📝 Örnek:\n"
        "Rmt.Ayşe - Remote"
    )
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bilgileriniz kaydedildi.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)
            ]
        },
        fallbacks=[],
    )

    app.add_handler(conv)

    print("Bot çalışıyor...")
    app.run_polling()

if __name__ == "__main__":
    main()
