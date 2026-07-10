import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

TOKEN = "8859190739:AAHxAZ8F0hPdQ3EDodRXsJ3Q09thgL8CeyY"

NAME = 1
SHIFT = 2
DAY = 3

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Mesai Talep Formuna Hoş Geldiniz.\n\n"
        "👤 Lütfen çalışan adınızı ve görevinizi yazınız.\n\n"
        "📝 Örnek:\n"
        "Rmt.Ayşe - Remote"
    )
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["isim"] = update.message.text

    keyboard = [
    [
        InlineKeyboardButton("🌅 05:00-14:00", callback_data="05:00-14:00"),
        InlineKeyboardButton("☀️ 08:00-17:00", callback_data="08:00-17:00")
    ],
    [
        InlineKeyboardButton("🌤️ 11:00-20:00", callback_data="11:00-20:00"),
        InlineKeyboardButton("🌇 14:00-23:00", callback_data="14:00-23:00")
    ],
    [
        InlineKeyboardButton("🌙 17:00-02:00", callback_data="17:00-02:00"),
        InlineKeyboardButton("🌃 20:00-05:00", callback_data="20:00-05:00")
    ]
    ]

    await update.message.reply_text(
    "🕒 Lütfen talep ettiğiniz çalışma saatini seçiniz.",
    reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return SHIFT
async def shift_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["mesai"] = query.data

    await query.edit_message_text(
        f"✅ Mesai seçildi: {query.data}\n\n"
        f"👤 Çalışan: {context.user_data['isim']}"
    )

        day_keyboard = [
        [
            InlineKeyboardButton("Pazartesi", callback_data="Pazartesi"),
            InlineKeyboardButton("Salı", callback_data="Salı")
        ],
        [
            InlineKeyboardButton("Çarşamba", callback_data="Çarşamba"),
            InlineKeyboardButton("Perşembe", callback_data="Perşembe")
        ],
        [
            InlineKeyboardButton("Cuma", callback_data="Cuma"),
            InlineKeyboardButton("Cumartesi", callback_data="Cumartesi")
        ],
        [
            InlineKeyboardButton("Pazar", callback_data="Pazar")
        ]
    ]

    await query.message.reply_text(
        "📅 Haftalık izin gününüzü seçiniz:",
        reply_markup=InlineKeyboardMarkup(day_keyboard)
    )

    return DAY
 async def day_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["izin_gunu"] = query.data

    await query.edit_message_text(
        f"✅ Mesai: {context.user_data['mesai']}\n"
        f"📅 İzin Günü: {query.data}\n"
        f"👤 Çalışan: {context.user_data['isim']}"
    )

    return ConversationHandler.END
def main():
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
    NAME: [
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)
    ],
    SHIFT: [
        CallbackQueryHandler(shift_selected)
    ],
    DAY: [
        CallbackQueryHandler(day_selected)
    ]
},
        fallbacks=[],
    )

    app.add_handler(conv)

    print("Bot çalışıyor...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
