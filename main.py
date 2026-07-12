import asyncio
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
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

sheet = gc.open_by_key("16HFBmwlQTyddoYaM19lSEtRsWzy5C0-C8aJpwdlcUvQ").sheet1
spreadsheet = gc.open_by_key("16HFBmwlQTyddoYaM19lSEtRsWzy5C0-C8aJpwdlcUvQ")
try:
    settings_sheet = spreadsheet.worksheet("AYARLAR")
except gspread.WorksheetNotFound:
    settings_sheet = spreadsheet.add_worksheet(title="AYARLAR", rows=10, cols=2)
    settings_sheet.update("A1:B2", [["Ayar", "Değer"], ["talep_durumu", "kapalı"]])

def talep_durumu_acik_mi():
    try:
        return settings_sheet.acell("B2").value.strip().lower() == "açık"
    except Exception:
        return False

def talep_durumunu_ayarla(durum):
    settings_sheet.update_acell("B2", durum)

async def talep_ac(update: Update, context: ContextTypes.DEFAULT_TYPE):
    talep_durumunu_ayarla("açık")
    await update.message.reply_text("✅ MESAİ TALEP ALIMI AÇILMIŞTIR\n\nPersoneller artık /start komutu ile mesai talebi oluşturabilir.")

async def talep_kapa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    talep_durumunu_ayarla("kapalı")
    await update.message.reply_text("🔒 MESAİ TALEP ALIMI SONA ERMİŞTİR\n\nYeni mesai talebi alınmayacaktır.")

TOKEN = "8859190739:AAHPizPBwxa8T-_bxEwFSuPSt4zaVafNIQE"

NAME = 1
TITLE = 2
SHIFT = 3
DAY = 4
SPECIAL = 5
SPECIAL_TEXT = 6
CONFIRM = 7

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not talep_durumu_acik_mi():
        await update.message.reply_text(
            "🔒 MESAİ TALEP ALIMI SONA ERMİŞTİR\n\nŞu anda yeni mesai talebi alınmamaktadır."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🕒 MESAİ TALEP SİSTEMİ\n\n👤 Devam etmek için lütfen sistem adınızı yazınız:"
    )

    return NAME

async def title_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["unvan"] = update.message.text.replace("⭐ ", "").replace("⭐⭐ ", "").replace("⭐⭐⭐ ", "").replace("⭐⭐⭐⭐ ", "").replace("🎯 ", "")

    keyboard = [
        ["🌅 05:00-14:00", "☀️ 08:00-17:00"],
        ["🌤️ 11:00-20:00", "🌇 14:00-23:00"],
        ["🌙 17:00-02:00", "🌃 20:00-05:00"]
    ]

    await update.message.reply_text(
        "🕒 ÇALIŞMA SAATİ\n\nLütfen talep ettiğiniz çalışma saatini seçiniz.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )

    return SHIFT

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["isim"] = update.message.text

    title_keyboard = [
        ["⭐ Operatör", "⭐⭐ Kıdemli Operatör"],
        ["⭐⭐⭐ Danışman", "⭐⭐⭐⭐ Kıdemli Danışman"],
        ["🎯 RMT"]
    ]

    await update.message.reply_text(
        f"👋 Hoş geldiniz, {context.user_data['isim']}!\n\n"
        "🕒 MESAİ TALEP SİSTEMİ\n\n"
        "👔 Lütfen ünvanınızı seçiniz:",
        reply_markup=ReplyKeyboardMarkup(
            title_keyboard,
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )

    return TITLE

async def shift_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mesai"] = update.message.text.split(" ", 1)[-1]

    day_keyboard = [
        ["💼 Pazartesi", "🚀 Salı"],
        ["📈 Çarşamba", "🎯 Perşembe"],
        ["🏖️ Cuma", "🌴 Cumartesi"],
        ["☀️ Pazar"]
    ]

    await update.message.reply_text(
        "📅 HAFTALIK İZİN GÜNÜ\n\nLütfen haftalık izin gününüzü seçiniz:",
        reply_markup=ReplyKeyboardMarkup(
            day_keyboard,
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )

    return DAY


async def day_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["izin_gunu"] = update.message.text.split(" ", 1)[-1]

    keyboard = [["✍️ EVET, VAR", "✅ HAYIR, YOK"]]

    await update.message.reply_text(
        "📝 ÖZEL DURUM\n\nBelirtmek istediğiniz özel bir durum var mı?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )

    return SPECIAL



async def special_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "✅ HAYIR, YOK":
        context.user_data["ozel_durum"] = "Yok"
        return await show_confirm(update, context)

    await update.message.reply_text(
        "✍️ ÖZEL DURUM AÇIKLAMASI\n\nLütfen özel durumunuzu kısa ve açık şekilde yazınız:",
        reply_markup=ReplyKeyboardRemove()
    )
    return SPECIAL_TEXT


async def special_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ozel_durum"] = update.message.text
    return await show_confirm(update, context)


async def show_confirm(update, context):
    keyboard = [
        ["✅ TALEBİ GÖNDER"],
        ["✏️ BAŞTAN DÜZENLE"]
    ]

    await update.message.reply_text(
        f"📋 MESAİ TALEBİ ÖZETİ\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Personel: {context.user_data['isim']}\n"
        f"👔 Ünvan: {context.user_data['unvan']}\n"
        f"🕒 Mesai: {context.user_data['mesai']}\n"
        f"📅 İzin Günü: {context.user_data['izin_gunu']}\n"
        f"📝 Özel Durum: {context.user_data['ozel_durum']}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Bilgileri kontrol edip işleminizi seçiniz.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    return CONFIRM


async def confirm_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "✏️ BAŞTAN DÜZENLE":
        await update.message.reply_text(
            "✏️ Talebiniz iptal edildi.\n\nYeniden oluşturmak için /start komutunu kullanın.",
            reply_markup=ReplyKeyboardRemove()
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

        await update.message.reply_text(
            "✅ MESAİ TALEBİNİZ BAŞARIYLA GÖNDERİLDİ\n\n"
            "📄 Talebiniz sisteme kaydedildi.\n"
            "Teşekkür ederiz.",
            reply_markup=ReplyKeyboardRemove()
        )

    except Exception as e:
        await update.message.reply_text(
            f"❌ Kayıt sırasında hata oluştu.\n\n{e}",
            reply_markup=ReplyKeyboardRemove()
        )

    return ConversationHandler.END


def main():

    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
    TITLE: [
        MessageHandler(filters.TEXT & ~filters.COMMAND, title_selected)
    ],
    NAME: [
        MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)
    ],
    SHIFT: [
        MessageHandler(filters.TEXT & ~filters.COMMAND, shift_selected)
    ],
    DAY: [
        MessageHandler(filters.TEXT & ~filters.COMMAND, day_selected)
    ],
SPECIAL: [
    MessageHandler(filters.TEXT & ~filters.COMMAND, special_selected)
],

SPECIAL_TEXT: [
    MessageHandler(filters.TEXT & ~filters.COMMAND, special_text)
],
CONFIRM: [
    MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_selected)
]},
        
        fallbacks=[],
    )

    app.add_handler(MessageHandler(filters.Regex(r"(?i)^talep aç$"), talep_ac))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^talep kapa$"), talep_kapa))
    app.add_handler(conv)

    print("Bot çalışıyor...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
