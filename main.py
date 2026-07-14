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

try:
    users_sheet = spreadsheet.worksheet("KULLANICILAR")
except gspread.WorksheetNotFound:
    users_sheet = spreadsheet.add_worksheet(title="KULLANICILAR", rows=1000, cols=4)
    users_sheet.update("A1:D1", [["Telegram ID", "Sistem Adı", "Ünvan", "Son Güncelleme"]])

AYLAR_TR = {
    1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan",
    5: "Mayıs", 6: "Haziran", 7: "Temmuz", 8: "Ağustos",
    9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
}


def ayar_degeri(anahtar, varsayilan=""):
    try:
        values = settings_sheet.get_all_values()
        for row in values[1:]:
            if len(row) >= 2 and row[0].strip() == anahtar:
                return row[1].strip()
    except Exception:
        pass
    return varsayilan


def ayar_yaz(anahtar, deger):
    values = settings_sheet.get_all_values()
    for row_number, row in enumerate(values[1:], start=2):
        if row and row[0].strip() == anahtar:
            settings_sheet.update(f"A{row_number}:B{row_number}", [[anahtar, str(deger)]])
            return
    settings_sheet.append_row([anahtar, str(deger)])


def zaman_ayarini_oku(anahtar):
    deger = ayar_degeri(anahtar)
    if not deger:
        return None
    try:
        return datetime.strptime(deger, "%d.%m.%Y %H:%M").replace(tzinfo=ZoneInfo("Europe/Istanbul"))
    except ValueError:
        return None


def zaman_ayarini_yaz(anahtar, dt):
    ayar_yaz(anahtar, dt.strftime("%d.%m.%Y %H:%M"))


def aktif_talep_ayi():
    """Planlanan dönem varsa bitiş tarihinin ait olduğu ayı; yoksa eski otomatik mantığı kullanır."""
    bitis = zaman_ayarini_oku("talep_bitis")
    if bitis:
        hedef = bitis - timedelta(seconds=1)
        return hedef.year, hedef.month

    simdi = datetime.now(ZoneInfo("Europe/Istanbul"))
    aday_yil, aday_ay = simdi.year, simdi.month
    bitis = talep_bitis_zamani(aday_yil, aday_ay)
    if simdi >= bitis:
        if aday_ay == 12:
            return aday_yil + 1, 1
        return aday_yil, aday_ay + 1
    return aday_yil, aday_ay


def talep_bitis_zamani(yil, ay):
    ilk_gun = datetime(yil, ay, 1, tzinfo=ZoneInfo("Europe/Istanbul"))
    ilk_pazartesi = ilk_gun + timedelta(days=(7 - ilk_gun.weekday()) % 7)
    son_cuma = ilk_pazartesi - timedelta(days=3)
    return (son_cuma + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def aktif_baslangic_zamani():
    return zaman_ayarini_oku("talep_baslangic")


def aktif_bitis_zamani():
    return zaman_ayarini_oku("talep_bitis") or talep_bitis_zamani(*aktif_talep_ayi())


def son_talep_gunu():
    return aktif_bitis_zamani() - timedelta(seconds=1)


def aktif_donem_adi():
    yil, ay = aktif_talep_ayi()
    return f"{AYLAR_TR[ay]} {yil} Mesai Talepleri"


def aktif_talep_sheet():
    baslik = aktif_donem_adi()
    try:
        ws = spreadsheet.worksheet(baslik)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=baslik, rows=1000, cols=10)
        ws.update("A1:E1", [["Personel", "Ünvan", "Mesai", "İzin Günü", "Özel Durum"]])
    return ws


def tarih_metni(dt):
    return f"{dt.day} {AYLAR_TR[dt.month]} {dt.year}"


def tarih_saat_metni(dt):
    return dt.strftime("%d.%m.%Y %H:%M")


def kalan_sure_metni():
    simdi = datetime.now(ZoneInfo("Europe/Istanbul"))
    baslangic = aktif_baslangic_zamani()
    bitis = aktif_bitis_zamani()

    if baslangic and simdi < baslangic:
        kalan = baslangic - simdi
        on_ek = "⏳ Açılışa kalan süre:"
    else:
        kalan = bitis - simdi
        on_ek = "⏳ Kapanışa kalan süre:"

    if kalan.total_seconds() <= 0:
        return "⏳ Süre doldu."

    toplam_saniye = int(kalan.total_seconds())
    gun, kalan_saniye = divmod(toplam_saniye, 86400)
    saat, kalan_saniye = divmod(kalan_saniye, 3600)
    dakika, saniye = divmod(kalan_saniye, 60)
    if gun > 0:
        return f"{on_ek} {gun} gün {saat} saat {dakika} dakika {saniye} saniye"
    return f"{on_ek} {saat} saat {dakika} dakika {saniye} saniye"


def sure_doldu_mu():
    return datetime.now(ZoneInfo("Europe/Istanbul")) >= aktif_bitis_zamani()


def talep_durumu_acik_mi():
    simdi = datetime.now(ZoneInfo("Europe/Istanbul"))
    baslangic = aktif_baslangic_zamani()
    bitis = zaman_ayarini_oku("talep_bitis")

    if baslangic and bitis:
        if simdi < baslangic:
            return False
        if simdi >= bitis:
            return False
        return True

    return ayar_degeri("talep_durumu", "kapalı").lower() == "açık"


def talep_durumunu_ayarla(durum):
    ayar_yaz("talep_durumu", durum)


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
PANEL = 20
PANEL_START_DATE = 21
PANEL_START_TIME = 22
PANEL_END_DATE = 23
PANEL_END_TIME = 24
PANEL_PERIOD_CONFIRM = 25
PANEL_BLOCK_NAME = 26
PANEL_UNBLOCK_NAME = 27

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



def kayitli_kullanici_bul(telegram_id):
    try:
        hedef = str(telegram_id)
        for row_number, row in enumerate(users_sheet.get_all_values()[1:], start=2):
            if row and str(row[0]).strip() == hedef:
                return row_number, row
    except Exception as e:
        print(f"KULLANICILAR okuma hatası: {e}")
    return None, None

def kullanici_kaydet(telegram_id, isim, unvan):
    telegram_id = str(telegram_id)
    zaman = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y-%m-%d %H:%M:%S")
    row_number, _ = kayitli_kullanici_bul(telegram_id)
    veri = [[telegram_id, isim, unvan, zaman]]
    if row_number:
        users_sheet.update(f"A{row_number}:D{row_number}", veri)
    else:
        users_sheet.append_row(veri[0])

def kullanici_kaydini_guncelle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        telegram_id = update.effective_user.id
        isim = context.user_data.get("isim")
        unvan = context.user_data.get("unvan")
        if telegram_id and isim and unvan:
            kullanici_kaydet(telegram_id, isim, unvan)
    except Exception as e:
        print(f"KULLANICILAR kayıt hatası: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not talep_durumu_acik_mi():
        await update.message.reply_text(
            "🔒 MESAİ TALEP ALIMI SONA ERMİŞTİR\n\nŞu anda yeni mesai talebi alınmamaktadır."
        )
        return ConversationHandler.END

    telegram_id = update.effective_user.id
    _, kayitli = kayitli_kullanici_bul(telegram_id)

    if kayitli and len(kayitli) >= 3 and kayitli[1].strip() and kayitli[2].strip():
        context.user_data["isim"] = kayitli[1].strip()
        context.user_data["unvan"] = kayitli[2].strip()

        if engelli_mi(context.user_data["isim"]):
            await update.message.reply_text("⛔ MESAİ TALEBİ YETKİNİZ BULUNMAMAKTADIR", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END

        row_number, row = mevcut_talep_satiri(context.user_data["isim"])
        if row_number:
            context.user_data["guncelleme_modu"] = True
            context.user_data["mevcut_satir"] = row_number
            await update.message.reply_text(
                f"👋 Hoş geldiniz, {context.user_data['isim']}!\n\nℹ️ Bu dönem için zaten bir mesai talebiniz bulunmaktadır.",
                reply_markup=ReplyKeyboardMarkup([["✏️ TALEBİMİ GÜNCELLE"]], resize_keyboard=True, one_time_keyboard=True)
            )
            return UPDATE_CONFIRM

        onceki = onceki_talebi_bul(context.user_data["isim"])
        if onceki and len(onceki) >= 5:
            context.user_data["onceki_talep"] = onceki
            await update.message.reply_text(
                f"👋 Hoş geldiniz, {context.user_data['isim']}!\n\n"
                f"📋 ÖNCEKİ DÖNEM TALEBİNİZ\n👔 Ünvan: {onceki[1]}\n🕒 Mesai: {onceki[2]}\n"
                f"📅 İzin Günü: {onceki[3]}\n📝 Özel Durum: {onceki[4]}\n\n"
                "Bu dönem için önceki talebinizi kullanmak ister misiniz?",
                reply_markup=ReplyKeyboardMarkup(
                    [["⚡ ÖNCEKİ TALEBİMİ TEKRARLA"], ["✏️ YENİ TALEP OLUŞTUR"]],
                    resize_keyboard=True, one_time_keyboard=True
                )
            )
            return PREVIOUS_REQUEST

        context.user_data["guncelleme_modu"] = False
        await update.message.reply_text(
            f"👋 Hoş geldiniz, {context.user_data['isim']}!\n👔 Kayıtlı ünvanınız: {context.user_data['unvan']}\n\n"
            "🕒 Lütfen talep ettiğiniz çalışma saatini seçiniz.",
            reply_markup=ReplyKeyboardMarkup(
                [["🌅 05:00-14:00", "☀️ 08:00-17:00"], ["🌤️ 11:00-20:00", "🌇 14:00-23:00"], ["🌙 17:00-02:00", "🌃 20:00-05:00"]],
                resize_keyboard=True, one_time_keyboard=True
            )
        )
        return SHIFT

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
        context.user_data["unvan"] = onceki[1]
        kullanici_kaydini_guncelle(update, context)
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
        kullanici_kaydini_guncelle(update, context)
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



def yonetici_mi(update: Update):
    """Yönetici ID'leri Railway ADMIN_IDS değişkeninden okunur. Örn: 123456789,987654321"""
    raw = os.environ.get("ADMIN_IDS", "").strip()
    izinli = {x.strip() for x in raw.split(",") if x.strip()}
    return str(update.effective_user.id) in izinli


def panel_klavyesi():
    return ReplyKeyboardMarkup(
        [
            ["📅 TALEP DÖNEMİ OLUŞTUR", "📊 TALEP DÖNEMİ DURUMU"],
            ["🟢 TALEPLERİ MANUEL AÇ", "🔴 TALEPLERİ MANUEL KAPAT"],
            ["🚫 KULLANICI ENGELLE", "✅ ENGEL KALDIR"],
            ["❌ PANELİ KAPAT"]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )


async def panel_ac(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yonetici_mi(update):
        await update.message.reply_text("⛔ Bu komut yalnızca yöneticiler içindir.")
        return ConversationHandler.END
    await update.message.reply_text("🛠️ YÖNETİCİ PANELİ\n\nYapmak istediğiniz işlemi seçiniz:", reply_markup=panel_klavyesi())
    return PANEL


async def panel_secim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    secim = update.message.text.strip()

    if secim == "❌ PANELİ KAPAT":
        await update.message.reply_text("✅ Yönetici paneli kapatıldı.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if secim == "📅 TALEP DÖNEMİ OLUŞTUR":
        await update.message.reply_text(
            "📅 Talep döneminin BAŞLANGIÇ tarihini yazınız.\n\nÖrnek: 30.07.2026",
            reply_markup=ReplyKeyboardRemove()
        )
        return PANEL_START_DATE

    if secim == "📊 TALEP DÖNEMİ DURUMU":
        baslangic = aktif_baslangic_zamani()
        bitis = zaman_ayarini_oku("talep_bitis")
        durum = "🟢 AÇIK" if talep_durumu_acik_mi() else "🔴 KAPALI"
        await update.message.reply_text(
            "📊 TALEP DÖNEMİ DURUMU\n\n"
            f"Durum: {durum}\n"
            f"📁 Dönem: {aktif_donem_adi()}\n"
            f"🟢 Başlangıç: {tarih_saat_metni(baslangic) if baslangic else 'Ayarlanmadı'}\n"
            f"🔴 Bitiş: {tarih_saat_metni(bitis) if bitis else 'Ayarlanmadı'}\n"
            f"{kalan_sure_metni()}",
            reply_markup=panel_klavyesi()
        )
        return PANEL

    if secim == "🟢 TALEPLERİ MANUEL AÇ":
        # Planlı dönemi kaldırıp manuel açık moda geçer.
        ayar_yaz("talep_baslangic", "")
        ayar_yaz("talep_bitis", "")
        talep_durumunu_ayarla("açık")
        await update.message.reply_text("🟢 Mesai talep alımı manuel olarak AÇILDI.", reply_markup=panel_klavyesi())
        return PANEL

    if secim == "🔴 TALEPLERİ MANUEL KAPAT":
        # Planlı dönemi kaldırıp manuel kapalı moda geçer.
        ayar_yaz("talep_baslangic", "")
        ayar_yaz("talep_bitis", "")
        talep_durumunu_ayarla("kapalı")
        await update.message.reply_text("🔴 Mesai talep alımı manuel olarak KAPATILDI.", reply_markup=panel_klavyesi())
        return PANEL

    if secim == "🚫 KULLANICI ENGELLE":
        await update.message.reply_text("🚫 Engellemek istediğiniz kullanıcının sistem adını yazınız:", reply_markup=ReplyKeyboardRemove())
        return PANEL_BLOCK_NAME

    if secim == "✅ ENGEL KALDIR":
        await update.message.reply_text("✅ Engelini kaldırmak istediğiniz kullanıcının sistem adını yazınız:", reply_markup=ReplyKeyboardRemove())
        return PANEL_UNBLOCK_NAME

    await update.message.reply_text("Lütfen paneldeki butonlardan birini kullanınız.", reply_markup=panel_klavyesi())
    return PANEL


def panel_tarih_parse(metin):
    return datetime.strptime(metin.strip(), "%d.%m.%Y")


def panel_saat_parse(metin):
    return datetime.strptime(metin.strip(), "%H:%M")


async def panel_baslangic_tarihi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        dt = panel_tarih_parse(update.message.text)
        context.user_data["panel_baslangic_tarih"] = dt.strftime("%d.%m.%Y")
    except ValueError:
        await update.message.reply_text("❌ Geçersiz tarih. Örnek format: 30.07.2026")
        return PANEL_START_DATE
    await update.message.reply_text("🕒 Başlangıç saatini yazınız.\n\nÖrnek: 00:00")
    return PANEL_START_TIME


async def panel_baslangic_saati(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        saat = panel_saat_parse(update.message.text)
        context.user_data["panel_baslangic_saat"] = saat.strftime("%H:%M")
    except ValueError:
        await update.message.reply_text("❌ Geçersiz saat. Örnek format: 00:00")
        return PANEL_START_TIME
    await update.message.reply_text("📅 Talep döneminin BİTİŞ tarihini yazınız.\n\nÖrnek: 01.08.2026")
    return PANEL_END_DATE


async def panel_bitis_tarihi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        dt = panel_tarih_parse(update.message.text)
        context.user_data["panel_bitis_tarih"] = dt.strftime("%d.%m.%Y")
    except ValueError:
        await update.message.reply_text("❌ Geçersiz tarih. Örnek format: 01.08.2026")
        return PANEL_END_DATE
    await update.message.reply_text("🕒 Bitiş saatini yazınız.\n\nÖrnek: 00:00")
    return PANEL_END_TIME


async def panel_bitis_saati(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        panel_saat_parse(update.message.text)
        context.user_data["panel_bitis_saat"] = update.message.text.strip()
        baslangic = datetime.strptime(
            f"{context.user_data['panel_baslangic_tarih']} {context.user_data['panel_baslangic_saat']}",
            "%d.%m.%Y %H:%M"
        ).replace(tzinfo=ZoneInfo("Europe/Istanbul"))
        bitis = datetime.strptime(
            f"{context.user_data['panel_bitis_tarih']} {context.user_data['panel_bitis_saat']}",
            "%d.%m.%Y %H:%M"
        ).replace(tzinfo=ZoneInfo("Europe/Istanbul"))
        if bitis <= baslangic:
            await update.message.reply_text("❌ Bitiş zamanı başlangıç zamanından sonra olmalıdır.")
            return PANEL_END_TIME
        context.user_data["panel_baslangic_dt"] = baslangic
        context.user_data["panel_bitis_dt"] = bitis
    except ValueError:
        await update.message.reply_text("❌ Geçersiz saat. Örnek format: 00:00")
        return PANEL_END_TIME

    await update.message.reply_text(
        "📅 TALEP DÖNEMİ ÖZETİ\n\n"
        f"🟢 Başlangıç: {tarih_saat_metni(baslangic)}\n"
        f"🔴 Bitiş: {tarih_saat_metni(bitis)}\n\n"
        "Bu tarih aralığını kaydetmek istiyor musunuz?",
        reply_markup=ReplyKeyboardMarkup([["✅ DÖNEMİ KAYDET"], ["❌ İPTAL"]], resize_keyboard=True, one_time_keyboard=True)
    )
    return PANEL_PERIOD_CONFIRM


async def panel_donem_onay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ İPTAL":
        await update.message.reply_text("İşlem iptal edildi.", reply_markup=panel_klavyesi())
        return PANEL
    if update.message.text != "✅ DÖNEMİ KAYDET":
        await update.message.reply_text("Lütfen onay butonlarından birini kullanınız.")
        return PANEL_PERIOD_CONFIRM

    baslangic = context.user_data["panel_baslangic_dt"]
    bitis = context.user_data["panel_bitis_dt"]
    zaman_ayarini_yaz("talep_baslangic", baslangic)
    zaman_ayarini_yaz("talep_bitis", bitis)
    talep_durumunu_ayarla("planlı")
    ayar_yaz("son_donem_olusturma", datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M"))

    await update.message.reply_text(
        "✅ TALEP DÖNEMİ OLUŞTURULDU\n\n"
        f"🟢 Başlangıç: {tarih_saat_metni(baslangic)}\n"
        f"🔴 Bitiş: {tarih_saat_metni(bitis)}\n\n"
        "Bot Türkiye saatine göre bu aralıkta otomatik olarak talep kabul edecektir.",
        reply_markup=panel_klavyesi()
    )
    return PANEL


async def panel_kullanici_engelle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    isim = update.message.text.strip()
    if not isim:
        await update.message.reply_text("❌ Lütfen bir sistem adı yazınız.")
        return PANEL_BLOCK_NAME
    if engelli_mi(isim):
        await update.message.reply_text(f"ℹ️ {isim} zaten engelli.", reply_markup=panel_klavyesi())
        return PANEL
    blocked_sheet.append_row([isim])
    await update.message.reply_text(f"🚫 {isim} engellendi.", reply_markup=panel_klavyesi())
    return PANEL


async def panel_engel_kaldir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    isim = update.message.text.strip()
    hedef = normalize_name(isim)
    try:
        values = blocked_sheet.col_values(1)
        for row_number, value in enumerate(values, start=1):
            if row_number > 1 and normalize_name(value) == hedef:
                blocked_sheet.delete_rows(row_number)
                await update.message.reply_text(f"✅ {isim} üzerindeki engel kaldırıldı.", reply_markup=panel_klavyesi())
                return PANEL
    except Exception as e:
        await update.message.reply_text(f"❌ Hata oluştu: {e}", reply_markup=panel_klavyesi())
        return PANEL
    await update.message.reply_text(f"ℹ️ {isim} engelli listesinde bulunamadı.", reply_markup=panel_klavyesi())
    return PANEL


async def panel_iptal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yonetici_mi(update):
        return ConversationHandler.END
    await update.message.reply_text("İşlem iptal edildi. Yönetici paneli yeniden açıldı.", reply_markup=panel_klavyesi())
    return PANEL


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

    panel_conv = ConversationHandler(
        entry_points=[CommandHandler("panel", panel_ac)],
        states={
            PANEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_secim)],
            PANEL_START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_baslangic_tarihi)],
            PANEL_START_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_baslangic_saati)],
            PANEL_END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_bitis_tarihi)],
            PANEL_END_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_bitis_saati)],
            PANEL_PERIOD_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_donem_onay)],
            PANEL_BLOCK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_kullanici_engelle)],
            PANEL_UNBLOCK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_engel_kaldir)],
        },
        fallbacks=[CommandHandler("panel", panel_ac)],
        allow_reentry=True,
    )

    app.add_handler(panel_conv)
    app.add_handler(MessageHandler(filters.Regex(r"^⏳ KALAN SÜRE$"), kalan_sure))
    app.add_handler(conv)

    print("Bot çalışıyor...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
