import asyncio
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
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

TALEP_BITIS = datetime(2026, 8, 1, 0, 0, 0, tzinfo=ZoneInfo("Europe/Istanbul"))

def kalan_sure_metni():
    simdi = datetime.now(ZoneInfo("Europe/Istanbul"))
    kalan = TALEP_BITIS - simdi

    if kalan.total_seconds() <= 0:
        return "⏳ Süre doldu."

    toplam_saniye = int(kalan.total_seconds())
    gun, kalan_saniye = divmod(toplam_saniye, 86400)
    saat, kalan_saniye = divmod(kalan_saniye, 3600)
    dakika, saniye = divmod(kalan_saniye, 60)

    if gun > 0:
        return f"⏳ Kalan süre: {gun} gün {saat} saat {dakika} dakika {saniye} saniye"
    return f"⏳ Kalan süre: {saat} saat {dakika} dakika {saniye} saniye"


def sure_doldu_mu():
    return datetime.now(ZoneInfo("Europe/Istanbul")) >= TALEP_BITIS


def talep_durumu_acik_mi():
    try:
        if sure_doldu_mu():
            if settings_sheet.acell("B2").value.strip().lower() != "kapalı":
                talep_durumunu_ayarla("kapalı")
            return False
        return settings_sheet.acell("B2").value.strip().lower() == "açık"
    except Exception:
        return False

def talep_durumunu_ayarla(durum):
    settings_sheet.update_acell("B2", durum)

async def talep_ac(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if sure_doldu_mu():
        talep_durumunu_ayarla("kapalı")
        await update.message.reply_text(
            "🔒 Belirlenen talep süresi sona ermiştir.\n\n"
            "Son tarih: 31 Temmuz 2026 23:59"
        )
        return

    talep_durumunu_ayarla("açık")
    await update.message.reply_text(
        "✅ MESAİ TALEP ALIMI AÇILMIŞTIR\n\n"
        "📅 Son gün: 31 Temmuz 2026\n"
        f"{kalan_sure_metni()}\n\n"
        "Personeller artık /start komutu ile mesai talebi oluşturabilir."
    )

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
UPDATE_CONFIRM = 8

def normalize_name(value):
    return " ".join(str(value).strip().casefold().split())

def mevcut_talep_satiri(isim):
    try:
        hedef = normalize_name(isim)
        for row_number, row in enumerate(sheet.get_all_values(), start=1):
            if row and normalize_name(row[0]) == hedef:
                return row_number, row
    except Exception:
        pass
    return None, None

async def guncelleme_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["⭐ Operatör", "⭐⭐ Kıdemli Operatör"],
        ["⭐⭐⭐ Danışman", "⭐⭐⭐⭐ Kıdemli Danışman"],
        ["🎯 RMT"]
    ]
    await update.message.reply_text(
        "✏️ TALEP GÜNCELLEME\n\nMevcut talebiniz güncellenecektir. Yeni bir talep oluşturulmayacaktır.\n\n👔 Lütfen ünvanınızı yeniden seçiniz:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    )
    return TITLE

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not talep_durumu_acik_mi():
        await update.message.reply_text(
            "🔒 MESAİ TALEP ALIMI SONA ERMİŞTİR\n\nŞu anda yeni mesai talebi alınmamaktadır."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🕒 MESAİ TALEP SİSTEMİ\n\n"
        "🟢 Talep alımı devam ediyor.\n"
        "📅 Son gün: 31 Temmuz 2026\n"
        f"{kalan_sure_metni()}\n\n"
        "👤 Devam etmek için lütfen sistem adınızı yazınız:"
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
    context.user_data["isim"] = update.message.text.strip()
    row_number, row = mevcut_talep_satiri(context.user_data["isim"])

    if row_number:
        context.user_data["guncelleme_modu"] = True
        context.user_data["mevcut_satir"] = row_number
        mevcut_ozet = ""
        if len(row) >= 5:
            mevcut_ozet = (
                f"\n\n📋 MEVCUT TALEBİNİZ\n"
                f"👤 Personel: {row[0]}\n👔 Ünvan: {row[1]}\n"
                f"🕒 Mesai: {row[2]}\n📅 İzin Günü: {row[3]}\n📝 Özel Durum: {row[4]}"
            )
        await update.message.reply_text(
            "ℹ️ Bu dönem için zaten bir mesai talebiniz bulunmaktadır.\n\n"
            "Aynı dönem için ikinci bir talep oluşturamazsınız.\n"
            "⏳ Talep süresi dolana kadar mevcut talebinizi güncelleyebilirsiniz."
            f"{mevcut_ozet}",
            reply_markup=ReplyKeyboardMarkup([["✏️ TALEBİMİ GÜNCELLE"]], resize_keyboard=True, one_time_keyboard=True)
        )
        return UPDATE_CONFIRM

    context.user_data["guncelleme_modu"] = False
    title_keyboard = [
        ["⭐ Operatör", "⭐⭐ Kıdemli Operatör"],
        ["⭐⭐⭐ Danışman", "⭐⭐⭐⭐ Kıdemli Danışman"],
        ["🎯 RMT"],
        ["⏳ KALAN SÜRE"]
    ]
    await update.message.reply_text(
        f"👋 Hoş geldiniz, {context.user_data['isim']}!\n\n🕒 MESAİ TALEP SİSTEMİ\n\n👔 Lütfen ünvanınızı seçiniz:",
        reply_markup=ReplyKeyboardMarkup(title_keyboard, resize_keyboard=True, one_time_keyboard=True)
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
        yeni_veri = [[
            context.user_data["isim"], context.user_data["unvan"],
            context.user_data["mesai"], context.user_data["izin_gunu"],
            context.user_data["ozel_durum"]
        ]]
        if context.user_data.get("guncelleme_modu") and context.user_data.get("mevcut_satir"):
            row_number = context.user_data["mevcut_satir"]
            sheet.update(f"A{row_number}:E{row_number}", yeni_veri)
            basari_mesaji = (
                "✅ MESAİ TALEBİNİZ BAŞARIYLA GÜNCELLENDİ\n\n"
                "📄 Mevcut talebiniz yeni bilgilerinizle güncellendi.\n"
                "⏳ Talep süresi sona erene kadar tekrar güncelleyebilirsiniz."
            )
        else:
            sheet.append_row(yeni_veri[0])
            basari_mesaji = (
                "✅ MESAİ TALEBİNİZ BAŞARIYLA GÖNDERİLDİ\n\n"
                "📄 Talebiniz sisteme kaydedildi.\n"
                "⏳ Talep süresi sona erene kadar mevcut talebinizi güncelleyebilirsiniz.\n"
                "⚠️ Aynı dönem için ikinci bir talep oluşturamazsınız."
            )
        await update.message.reply_text(basari_mesaji, reply_markup=ReplyKeyboardRemove())

    except Exception as e:
        await update.message.reply_text(
            f"❌ Kayıt sırasında hata oluştu.\n\n{e}",
            reply_markup=ReplyKeyboardRemove()
        )

    return ConversationHandler.END


async def kalan_sure(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if sure_doldu_mu():
        talep_durumunu_ayarla("kapalı")
        await update.message.reply_text(
            "🔒 MESAİ TALEP ALIMI SONA ERMİŞTİR\n\n"
            "📅 Son gün: 31 Temmuz 2026"
        )
        return

    durum = "🟢 Talep alımı devam ediyor." if talep_durumu_acik_mi() else "🔒 Talep alımı şu anda kapalı."
    await update.message.reply_text(
        f"{durum}\n\n"
        "📅 Son gün: 31 Temmuz 2026\n"
        f"{kalan_sure_metni()}"
    )


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
],
UPDATE_CONFIRM: [
    MessageHandler(filters.Regex(r"^✏️ TALEBİMİ GÜNCELLE$"), guncelleme_baslat)
]},
        
        fallbacks=[],
    )

    app.add_handler(MessageHandler(filters.Regex(r"(?i)^talep aç$"), talep_ac))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^talep kapa$"), talep_kapa))
    app.add_handler(MessageHandler(filters.Regex(r"^⏳ KALAN SÜRE$"), kalan_sure))
    app.add_handler(conv)

    print("Bot çalışıyor...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
