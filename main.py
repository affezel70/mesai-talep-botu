import asyncio
import os
import json
import gspread
from google.oauth2.service_account import Credentials
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
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])

creds = Credentials.from_service_account_info(
    creds_dict,
    scopes=SCOPES
)

gc = gspread.authorize(creds)

sheet = gc.open_by_key("16HFBmw1QTyddoYaM191SEtRsWzy5C0-C8aJpwd123456").sheet1
TOKEN = "8859190739:AAHPizPBwxa8T-_bxEwFSuPSt4zaVafNIQE"

NAME = 1
TITLE = 2
SHIFT = 3
DAY = 4
SPECIAL = 5
SPECIAL_TEXT = 6
CONFIRM = 7

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👤 Lütfen sistem adınızı yazınız:"
    )

    return NAME

async def title_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["unvan"] = query.data

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

    await query.message.reply_text(
        "🕒 Lütfen talep ettiğiniz çalışma saatini seçiniz.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return SHIFT
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

    title_keyboard = [
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

    await update.message.reply_text(
        f"Hoş geldiniz {context.user_data['isim']} 👋\n\n👔 Lütfen ünvanınızı seçiniz:",
        reply_markup=InlineKeyboardMarkup(title_keyboard)
    )

    return TITLE
async def shift_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["mesai"] = query.data

    
    day_keyboard = [
        [
            InlineKeyboardButton("💼 Pazartesi", callback_data="Pazartesi"),
            InlineKeyboardButton("🚀 Salı", callback_data="Salı")
        ],
        [
            InlineKeyboardButton("📈 Çarşamba", callback_data="Çarşamba"),
            InlineKeyboardButton("🎯 Perşembe", callback_data="Perşembe")
        ],
        [
            InlineKeyboardButton("🏖️ Cuma", callback_data="Cuma"),
            InlineKeyboardButton("🌴 Cumartesi", callback_data="Cumartesi")
        ],
        [
            InlineKeyboardButton("☀️ Pazar", callback_data="Pazar")
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

    keyboard = [[
        InlineKeyboardButton("✍️ Var", callback_data="var"),
        InlineKeyboardButton("✅ Yok", callback_data="yok")
    ]]

    await query.edit_message_text(
        "📝 Özel durumunuz var mı?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return SPECIAL



async def special_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "yok":
        context.user_data["ozel_durum"] = "Yok"
        return await show_confirm(query, context)

    await query.edit_message_text("✍️ Lütfen özel durumunuzu yazınız:")
    return SPECIAL_TEXT


async def special_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ozel_durum"] = update.message.text
    keyboard=[[InlineKeyboardButton("✏️ Düzenle",callback_data="edit"),
               InlineKeyboardButton("✅ Gönder",callback_data="send")]]
    await update.message.reply_text(
        f"📋 TALEP ÖZETİ\n\n"
        f"👤 {context.user_data['unvan']} {context.user_data['isim']}\n"
        f"🕒 {context.user_data['mesai']}\n"
        f"📅 {context.user_data['izin_gunu']}\n"
        f"📝 {context.user_data['ozel_durum']}",
        reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM

async def show_confirm(query, context):
    keyboard=[[InlineKeyboardButton("✏️ Düzenle",callback_data="edit"),
               InlineKeyboardButton("✅ Gönder",callback_data="send")]]
    await query.edit_message_text(
        f"📋 TALEP ÖZETİ\n\n"
        f"👤 {context.user_data['unvan']} {context.user_data['isim']}\n"
        f"🕒 {context.user_data['mesai']}\n"
        f"📅 {context.user_data['izin_gunu']}\n"
        f"📝 {context.user_data['ozel_durum']}",
        reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM

async def confirm_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "edit":
        await query.message.reply_text(
            "Yeniden başlatmak için /start komutunu kullanın."
        )
        return ConversationHandler.END

    try:
        sheet.append_row([
            context.user_data["isim"],
            context.user_data["unvan"],
            context.user_data["mesai"],
            context.user_data["izin_gunu"],
            context.user_data["ozel_durum"]
        ])

        await query.edit_message_text(
            "✅ Mesai talebiniz başarıyla gönderildi.\n\n📄 Talebiniz Google Sheets'e kaydedildi."
        )

    except Exception as e:
        await query.edit_message_text(
            f"❌ Kayıt sırasında hata oluştu.\n\n{e}"
        )

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
