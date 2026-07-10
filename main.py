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

TITLE = 1
NAME = 2
SHIFT = 3
DAY = 4
SPECIAL = 5
SPECIAL_TEXT = 6
CONFIRM = 7

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("⭐ Operatör", callback_data="Operatör"),
            InlineKeyboardButton("⭐⭐ Kıdemli Operatör", callback_data="Kıdemli Operatör"),
        ],
        [
            InlineKeyboardButton("⭐⭐⭐ Danışman", callback_data="Danışman"),
            InlineKeyboardButton("⭐⭐⭐⭐ Kıdemli Danışman", callback_data="Kıdemli Danışman"),
        ],
        [
            InlineKeyboardButton("RMT", callback_data="RMT"),
        ],
    ]

    keyboard = [[
        InlineKeyboardButton("✏️ Düzenle", callback_data="edit"),
        InlineKeyboardButton("✅ Gönder", callback_data="send")
    ]]

    await update.message.reply_text(
        f"📋 Lütfen talebinizi kontrol ediniz. "
        f"👤 Personel: {context.user_data['unvan']} {context.user_data['isim']} "
        f"🕒 Mesai: {context.user_data['mesai']} "
        f"📅 İzin Günü: {context.user_data['izin_gunu']} "
        f"📝 Özel Durum: {context.user_data['ozel_durum']}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CONFIRM

    await query.edit_message_text("✍️ Lütfen özel durumunuzu yazınız:")
    return SPECIAL_TEXT


async def special_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ozel_durum"] = update.message.text

    await update.message.reply_text(
        f"✅ Mesai Talebiniz Alındı "
        f"👤 Personel: {context.user_data['unvan']} {context.user_data['isim']} "
        f"🕒 Mesai: {context.user_data['mesai']} "
        f"📅 İzin Günü: {context.user_data['izin_gunu']} "
        f"📝 Özel Durum: {context.user_data['ozel_durum']}"
    )

    return CONFIRM




async def confirm_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "edit":
        await query.message.reply_text("✏️ Talebinizi yeniden oluşturabilirsiniz. Lütfen /start yazınız.")
        return ConversationHandler.END

    await query.edit_message_text("✅ Talebiniz başarıyla alınmıştır. Teşekkür ederiz.")
    return ConversationHandler.END


def main():

    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
    TITLE: [
        CallbackQueryHandler(title_selected)
    ],
    NAME: [
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)
    ],
    SHIFT: [
        CallbackQueryHandler(shift_selected)
    ],
    DAY: [
        CallbackQueryHandler(day_selected)
    ],
SPECIAL: [
    CallbackQueryHandler(special_selected)
],

SPECIAL_TEXT: [
    MessageHandler(filters.TEXT & ~filters.COMMAND, special_text)
],
    CONFIRM: [
        CallbackQueryHandler(confirm_selected)
    ]},
        
        fallbacks=[],
    )

    app.add_handler(conv)

    print("Bot çalışıyor...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()


# TODO: Onay ekranı eklenecek.
# Bu özellik ConversationHandler akışına yeni state'ler eklenmesini gerektirir.
# Mevcut çalışan sürüm korunmuştur.
