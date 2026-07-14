import asyncio
import os
import json
from datetime import datetime, timedelta
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

try:
    blocked_sheet = spreadsheet.worksheet("ENGELLENENLER")
except gspread.WorksheetNotFound:
    blocked_sheet = spreadsheet.add_worksheet(title="ENGELLENENLER", rows=100, cols=1)
    blocked_sheet.update_acell("A1", "Sistem Adı")

AYLAR_TR = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan",
    5: "Mayıs", 6: "Haziran", 7: "Temmuz", 8: "Ağustos",
    9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
}


def aktif_talep_ayi():
    """
    İçinde bulunduğumuz tarihe göre sıradaki mesai dönemini belirler.
    Örnek: Temmuz sonunda toplanan talepler Ağustos ayı sekmesine gider.
    Bir dönemin kapanışından sonra otomatik olarak sonraki ayın dönemine geçilir.
    """
    simdi = datetime.now(ZoneInfo("Europe/Istanbul"))

    # Önce içinde bulunduğumuz ayı aday dönem olarak kontrol et.
    aday_yil = simdi.year
    aday_ay = simdi.month

    bitis = talep_bitis_zamani(aday_yil, aday_ay)
    if simdi >= bitis:
        if aday_ay == 12:
            aday_ay = 1
            aday_yil += 1
        else:
            aday_ay += 1

    return aday_yil, aday_ay


def talep_bitis_zamani(yil, ay):
    """
    İlgili ayın ilk pazartesisinden önceki cuma gününü son talep günü yapar.
    Cuma günü boyunca talep alınır; teknik kapanış cumartesi 00:00'dır.
    """
    ilk_gun = datetime(yil, ay, 1, tzinfo=ZoneInfo("Europe/Istanbul"))
    ilk_pazartesi = ilk_gun + timedelta(days=(7 - ilk_gun.weekday()) % 7)
    son_cuma = ilk_pazartesi - timedelta(days=3)
    return (son_cuma + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def aktif_bitis_zamani():
    yil, ay = aktif_talep_ayi()
    return talep_bitis_zamani(yil, ay)


def son_talep_gunu():
    return aktif_bitis_zamani() - timedelta(days=1)


def aktif_donem_adi():
    yil, ay = aktif_talep_ayi()
    return f"{AYLAR_TR[ay]} {yil} Mesai Talepleri"


def aktif_talep_sheet():
    """
    Aktif ayın çalışma sayfasını bulur; yoksa otomatik oluşturur.
    """
    baslik = aktif_donem_adi()
    try:
        ws = spreadsheet.worksheet(baslik)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=baslik, rows=1000, cols=10)
        ws.update(
            "A1:E1",
            [["Personel", "Ünvan", "Mesai", "İzin Günü", "Özel Durum"]]
        )
    return ws


def tarih_metni(dt):
    return f"{dt.day} {AYLAR_TR[dt.month]} {dt.year}"


def kalan_sure_metni():
    simdi = datetime.now(ZoneInfo("Europe/Istanbul"))
    kalan = aktif_bitis_zamani() - simdi

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
    return datetime.now(ZoneInfo("Europe/Istanbul")) >= aktif_bitis_zamani()


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
            f"Son talep günü: {tarih_metni(son_talep_gunu())}"
        )
        return

    talep_durumunu_ayarla("açık")
    await update.message.reply_text(
        "✅ MESAİ TALEP ALIMI AÇILMIŞTIR\n\n"
        f"📁 Dönem: {aktif_donem_adi()}\n"
        f"📅 Son talep günü: {tarih_metni(son_talep_gunu())}\n"
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
PREVIOUS_REQUEST = 9
PREVIOUS_CONFIRM = 10

def normalize_name(value):
    return " ".join(str(value).strip().casefold().split())

def onceki_donem_bilgisi():
    yil, ay = aktif_talep_ayi()
    if ay == 1:
        return yil - 1, 12
    return yil, ay - 1


def onceki_donem_adi():
    yil, ay = onceki_donem_bilgisi()
    return f"{AYLAR_TR[ay]} {yil} Mesai Talepleri"


def onceki_talebi_bul(isim):
    try:
        ws = spreadsheet.worksheet(onceki_donem_adi())
    except gspread.WorksheetNotFound:
        return None

    hedef = normalize_name(isim)
    try:
        for row in ws.get_all_values()[1:]:
            if row and normalize_name(row[0]) == hedef:
                return row[:5]
    except Exception:
        return None
    return None


def mevcut_talep_satiri(isim):
    try:
        hedef = normalize_name(isim)
        for row_number, row in enumerate(aktif_talep_sheet().get_all_values(), start=1):
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

def engelli_mi(isim):
    hedef = normalize_name(isim)
    try:
        for value in blocked_sheet.col_values(1)[1:]:
            if normalize_name(value) == hedef:
                return True
    except Exception:
        pass
    return False


async def kullanici_engelle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    metin = update.message.text.strip()
    isim = metin[:-len(" engelle")].strip()

    if not isim:
        await update.message.reply_text("❌ Engellenecek sistem adını yazınız.\n\nÖrnek: RMT.Özge engelle")
        return

    if engelli_mi(isim):
        await update.message.reply_text(f"ℹ️ {isim} zaten engelli kullanıcılar listesinde.")
        return

    blocked_sheet.append_row([isim])
    await update.message.reply_text(
        f"🚫 {isim} ENGELLENDİ\n\n"
        "Bu kullanıcı artık mesai talebi oluşturamaz veya mevcut talebini güncelleyemez."
    )


async def kullanici_engel_kaldir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    metin = update.message.text.strip()
    isim = metin[:-len(" engel kaldır")].strip()
    hedef = normalize_name(isim)

    try:
        values = blocked_sheet.col_values(1)
        for row_number, value in enumerate(values, start=1):
            if row_number > 1 and normalize_name(value) == hedef:
                blocked_sheet.delete_rows(row_number)
                await update.message.reply_text(
                    f"✅ {isim} ÜZERİNDEKİ ENGEL KALDIRILDI\n\n"
                    "Talep dönemi açıksa kullanıcı yeniden mesai talebi oluşturabilir."
                )
                return
    except Exception as e:
        await update.message.reply_text(f"❌ Engel kaldırılırken hata oluştu.\n\n{e}")
        return

    await update.message.reply_text(f"ℹ️ {isim} engelli kullanıcılar listesinde bulunamadı.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not talep_durumu_acik_mi():
        await update.message.reply_text(
            "🔒 MESAİ TALEP ALIMI SONA ERMİŞTİR\n\nŞu anda yeni mesai talebi alınmamaktadır."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🕒 MESAİ TALEP SİSTEMİ\n\n"
        "🟢 Talep alımı devam ediyor.\n"
        f"📁 Dönem: {aktif_donem_adi()}\n"
        f"📅 Son talep günü: {tarih_metni(son_talep_gunu())}\n"
        f"{kalan_sure_metni()}\n\n"
        "👤 Devam etmek için lütfen sistem adınızı yazınız:",
        reply_markup=ReplyKeyboardMarkup(
            [["⏳ KALAN SÜRE"]],
            resize_keyboard=True,
            one_time_keyboard=False
        )
    )

    return NAME

async def title_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["unvan"] = update.message.text.strip()

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

    if engelli_mi(context.user_data["isim"]):
        await update.message.reply_text(
            "⛔ MESAİ TALEBİ YETKİNİZ BULUNMAMAKTADIR\n\n"
            "Bu kullanıcı için mesai talebi oluşturma ve güncelleme işlemleri kapatılmıştır.\n"
            "Detaylı bilgi için yöneticinizle iletişime geçiniz.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

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
            reply_markup=ReplyKeyboardMarkup(
                [["✏️ TALEBİMİ GÜNCELLE"]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        return UPDATE_CONFIRM

    onceki = onceki_talebi_bul(context.user_data["isim"])
    if onceki and len(onceki) >= 5:
        context.user_data["onceki_talep"] = onceki
        await update.message.reply_text(
            f"👋 Hoş geldiniz, {context.user_data['isim']}!\n\n"
            f"📋 ÖNCEKİ DÖNEM TALEBİNİZ\n"
            f"📁 {onceki_donem_adi()}\n\n"
            f"👔 Ünvan: {onceki[1]}\n"
            f"🕒 Mesai: {onceki[2]}\n"
            f"📅 İzin Günü: {onceki[3]}\n"
            f"📝 Özel Durum: {onceki[4]}\n\n"
            "Bu dönem için önceki talebinizi kullanmak ister misiniz?",
            reply_markup=ReplyKeyboardMarkup(
                [
                    ["⚡ ÖNCEKİ TALEBİMİ TEKRARLA"],
                    ["✏️ YENİ TALEP OLUŞTUR"]
                ],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        return PREVIOUS_REQUEST

    return await yeni_talep_baslat(update, context)


async def yeni_talep_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["guncelleme_modu"] = False
    title_keyboard = [
        ["⭐ Operatör", "⭐⭐ Kıdemli Operatör"],
        ["⭐⭐⭐ Danışman", "⭐⭐⭐⭐ Kıdemli Danışman"],
        ["🎯 RMT"],
        ["⏳ KALAN SÜRE"]
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


async def onceki_talep_secimi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    secim = update.message.text

    if secim == "✏️ YENİ TALEP OLUŞTUR":
        return await yeni_talep_baslat(update, context)

    if secim != "⚡ ÖNCEKİ TALEBİMİ TEKRARLA":
        await update.message.reply_text("Lütfen aşağıdaki seçeneklerden birini kullanınız.")
        return PREVIOUS_REQUEST

    onceki = context.user_data.get("onceki_talep")
    if not onceki or len(onceki) < 5:
        await update.message.reply_text("❌ Önceki talep bulunamadı. Yeni talep oluşturabilirsiniz.")
        return await yeni_talep_baslat(update, context)

    await update.message.reply_text(
        "⚡ TEKRARLANACAK TALEP\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Personel: {context.user_data['isim']}\n"
        f"👔 Ünvan: {onceki[1]}\n"
        f"🕒 Mesai: {onceki[2]}\n"
        f"📅 İzin Günü: {onceki[3]}\n"
        f"📝 Özel Durum: {onceki[4]}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Talebi aynen oluşturabilir veya bilgileri güncelleyerek oluşturabilirsiniz.",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["✅ ONAYLA VE OLUŞTUR"],
                ["✏️ GÜNCELLEYEREK OLUŞTUR"]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    return PREVIOUS_CONFIRM


async def onceki_talep_onay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    secim = update.message.text

    if secim == "✏️ GÜNCELLEYEREK OLUŞTUR":
        # Start the normal form with update-mode off; this creates the current month's first request.
        context.user_data["guncelleme_modu"] = False
        context.user_data.pop("mevcut_satir", None)
        return await yeni_talep_baslat(update, context)

    if secim != "✅ ONAYLA VE OLUŞTUR":
        await update.message.reply_text("Lütfen aşağıdaki seçeneklerden birini kullanınız.")
        return PREVIOUS_CONFIRM

    # Prevent duplicate creation on repeated button taps.
    row_number, _ = mevcut_talep_satiri(context.user_data["isim"])
    if row_number:
        await update.message.reply_text(
            "ℹ️ Bu dönem için zaten bir mesai talebiniz bulunmaktadır. İkinci talep oluşturulmadı.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    onceki = context.user_data.get("onceki_talep")
    if not onceki or len(onceki) < 5:
        await update.message.reply_text(
            "❌ Önceki talep bilgileri bulunamadı.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    yeni_veri = [
        context.user_data["isim"],
        onceki[1],
        onceki[2],
        onceki[3],
        onceki[4]
    ]

    try:
        aktif_talep_sheet().append_row(yeni_veri)
        await update.message.reply_text(
            "✅ MESAİ TALEBİNİZ BAŞARIYLA OLUŞTURULDU\n\n"
            "⚡ Önceki dönem tercihleriniz aktif döneme aynen aktarıldı.\n"
            "⏳ Talep süresi sona erene kadar mevcut talebinizi güncelleyebilirsiniz.",
            reply_markup=ReplyKeyboardMarkup(
                [["⏳ KALAN SÜRE"]],
                resize_keyboard=True,
                one_time_keyboard=False
            )
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Talep oluşturulurken hata oluştu.\n\n{e}",
            reply_markup=ReplyKeyboardRemove()
        )

    return ConversationHandler.END


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
            aktif_talep_sheet().update(f"A{row_number}:E{row_number}", yeni_veri)
            basari_mesaji = (
                "✅ MESAİ TALEBİNİZ BAŞARIYLA GÜNCELLENDİ\n\n"
                "📄 Mevcut talebiniz yeni bilgilerinizle güncellendi.\n"
                "⏳ Talep süresi sona erene kadar tekrar güncelleyebilirsiniz."
            )
        else:
            aktif_talep_sheet().append_row(yeni_veri[0])
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
            f"📅 Son talep günü: {tarih_metni(son_talep_gunu())}"
        )
        return

    durum = "🟢 Talep alımı devam ediyor." if talep_durumu_acik_mi() else "🔒 Talep alımı şu anda kapalı."
    await update.message.reply_text(
        f"{durum}\n\n"
        f"📅 Son talep günü: {tarih_metni(son_talep_gunu())}\n"
        f"{kalan_sure_metni()}",
        reply_markup=ReplyKeyboardMarkup(
            [["⏳ KALAN SÜRE"]],
            resize_keyboard=True,
            one_time_keyboard=False
        )
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
],
PREVIOUS_REQUEST: [
    MessageHandler(filters.TEXT & ~filters.COMMAND, onceki_talep_secimi)
],
PREVIOUS_CONFIRM: [
    MessageHandler(filters.TEXT & ~filters.COMMAND, onceki_talep_onay)
]},
        
        fallbacks=[],
        allow_reentry=True,
    )

    app.add_handler(MessageHandler(filters.Regex(r"(?i)^.+\s+engel kaldır$"), kullanici_engel_kaldir))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^.+\s+engelle$"), kullanici_engelle))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^talep aç$"), talep_ac))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^talep kapa$"), talep_kapa))
    app.add_handler(MessageHandler(filters.Regex(r"^⏳ KALAN SÜRE$"), kalan_sure))
    app.add_handler(conv)

    print("Bot çalışıyor...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
