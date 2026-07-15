import asyncio
import os
import json
import time
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
    """Aktif dönem sayfasını döndürür; yoksa iki ekipli yeni düzende oluşturur."""
    baslik = aktif_donem_adi()
    try:
        ws = spreadsheet.worksheet(baslik)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=baslik, rows=1005, cols=11)
        ws.update("A4:K5", [
            ["CANLI DESTEK EKİBİ", "", "", "", "", "", "KIDEMLİ PERSONEL", "", "", "", ""],
            ["Personel", "Ünvan", "Mesai", "İzin Günü", "Özel Durum", "", "Personel", "Ünvan", "Mesai", "İzin Günü", "Özel Durum"],
        ])
    return ws


VERI_BASLANGIC_SATIRI = 6
CANLI_DESTEK_UNVANLARI = {"⭐ Operatör", "🎯 RMT"}
KIDEMLI_UNVANLARI = {"⭐⭐ Kıdemli Operatör", "⭐⭐⭐ Danışman", "⭐⭐⭐⭐ Kıdemli Danışman"}


def unvan_grubu(unvan):
    unvan = str(unvan).strip()
    if unvan in KIDEMLI_UNVANLARI:
        return "kidemli"
    return "canli"


def grup_araligi(grup, satir):
    return f"G{satir}:K{satir}" if grup == "kidemli" else f"A{satir}:E{satir}"


def tablo_kayitlarini_oku(ws=None):
    """A:E ve G:K tablolarındaki tüm talepleri ortak biçimde döndürür."""
    ws = ws or aktif_talep_sheet()
    cache_key = f"talep_kayitlari:{ws.title}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    values = ws.get_all_values()
    kayitlar = []
    for row_number in range(VERI_BASLANGIC_SATIRI, len(values) + 1):
        row = values[row_number - 1]
        sol = (row[0:5] + [""] * 5)[:5]
        if any(str(v).strip() for v in sol):
            kayitlar.append({"grup": "canli", "satir": row_number, "veri": sol})
        sag = ((row[6:11] if len(row) > 6 else []) + [""] * 5)[:5]
        if any(str(v).strip() for v in sag):
            kayitlar.append({"grup": "kidemli", "satir": row_number, "veri": sag})
    return cache_set(cache_key, kayitlar)


def bos_satir_bul(ws, grup):
    """İlgili tabloda 6. satırdan itibaren ilk tamamen boş satırı bulur."""
    values = ws.get_all_values()
    baslangic = 6 if grup == "kidemli" else 0
    son = max(len(values) + 1, VERI_BASLANGIC_SATIRI + 1)
    for row_number in range(VERI_BASLANGIC_SATIRI, son):
        row = values[row_number - 1] if row_number <= len(values) else []
        alan = (row[baslangic:baslangic + 5] + [""] * 5)[:5]
        if not any(str(v).strip() for v in alan):
            return row_number
    return max(len(values) + 1, VERI_BASLANGIC_SATIRI)


MESAI_RENKLERI = {
    "05:00-14:00": "#FFFF00",
    "08:00-17:00": "#00DDEB",
    "11:00-20:00": "#1F67C1",
    "14:00-23:00": "#F6DFC3",
    "17:00-02:00": "#6AA84F",
    "20:00-05:00": "#D99A9A",
}

def hex_to_rgb01(hex_color):
    h = hex_color.lstrip("#")
    return {"red": int(h[0:2], 16)/255, "green": int(h[2:4], 16)/255, "blue": int(h[4:6], 16)/255}

def mesai_hucresini_renklendir(ws, grup, satir, mesai):
    sutun = "I" if grup == "kidemli" else "C"
    renk = MESAI_RENKLERI.get(str(mesai).strip())
    if renk:
        ws.format(f"{sutun}{satir}", {
            "backgroundColor": hex_to_rgb01(renk),
            "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}},
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
        })

def talep_yaz(veri):
    ws = aktif_talep_sheet()
    grup = unvan_grubu(veri[1])
    satir = bos_satir_bul(ws, grup)
    ws.update(grup_araligi(grup, satir), [veri])
    mesai_hucresini_renklendir(ws, grup, satir, veri[2])
    cache_clear(f"talep_kayitlari:{ws.title}")
    return grup, satir


def talep_guncelle(eski_grup, eski_satir, veri):
    """Ünvan grubu değişirse kaydı diğer tabloya taşır; değişmezse yerinde günceller."""
    ws = aktif_talep_sheet()
    yeni_grup = unvan_grubu(veri[1])
    if eski_grup == yeni_grup:
        ws.update(grup_araligi(eski_grup, eski_satir), [veri])
        mesai_hucresini_renklendir(ws, yeni_grup, eski_satir, veri[2])
        cache_clear(f"talep_kayitlari:{ws.title}")
        return yeni_grup, eski_satir
    ws.batch_clear([grup_araligi(eski_grup, eski_satir)])
    yeni_satir = bos_satir_bul(ws, yeni_grup)
    ws.update(grup_araligi(yeni_grup, yeni_satir), [veri])
    mesai_hucresini_renklendir(ws, yeni_grup, yeni_satir, veri[2])
    cache_clear(f"talep_kayitlari:{ws.title}")
    return yeni_grup, yeni_satir

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
    return ayar_degeri("talep_durumu", "kapalı").lower() == "açık"


def talep_durumunu_ayarla(durum):
    ayar_yaz("talep_durumu", durum)


TOKEN = os.environ["BOT_TOKEN"]
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
PANEL_ANNOUNCE_CONFIRM = 28
PANEL_OPEN_NOTIFY_CONFIRM = 29
PANEL_CLOSE_NOTIFY_CONFIRM = 30
PANEL_REMIND_CONFIRM = 31
PANEL_REMIND_LIST_CONFIRM = 32

_CACHE = {}
CACHE_TTL = 8  # saniye


def cache_get(key):
    item = _CACHE.get(key)
    if not item:
        return None
    created_at, value = item
    if time.monotonic() - created_at > CACHE_TTL:
        _CACHE.pop(key, None)
        return None
    return value


def cache_set(key, value):
    _CACHE[key] = (time.monotonic(), value)
    return value


def cache_clear(*keys):
    if not keys:
        _CACHE.clear()
        return
    for key in keys:
        _CACHE.pop(key, None)


def kullanicilar_verisi():
    cached = cache_get("kullanicilar")
    if cached is not None:
        return cached
    return cache_set("kullanicilar", users_sheet.get_all_values())


def engelli_isimleri():
    cached = cache_get("engelliler")
    if cached is not None:
        return cached
    values = blocked_sheet.col_values(1)[1:]
    return cache_set("engelliler", {normalize_name(v) for v in values if str(v).strip()})


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
        values = ws.get_all_values()
        for row_number in range(VERI_BASLANGIC_SATIRI, len(values) + 1):
            row = values[row_number - 1]
            sol = (row[0:5] + [""] * 5)[:5]
            if normalize_name(sol[0]) == hedef:
                return sol
            sag = ((row[6:11] if len(row) > 6 else []) + [""] * 5)[:5]
            if normalize_name(sag[0]) == hedef:
                return sag
    except Exception:
        return None
    return None

def mevcut_talep_satiri(isim):
    try:
        hedef = normalize_name(isim)
        for kayit in tablo_kayitlarini_oku():
            row = kayit["veri"]
            if row and normalize_name(row[0]) == hedef:
                return kayit["satir"], row, kayit["grup"]
    except Exception:
        pass
    return None, None, None

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
    return normalize_name(isim) in engelli_isimleri()


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
    cache_clear("engelliler")
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
                cache_clear("engelliler")
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
        for row_number, row in enumerate(kullanicilar_verisi()[1:], start=2):
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
    cache_clear("kullanicilar")

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

        row_number, row, grup = mevcut_talep_satiri(context.user_data["isim"])
        if row_number:
            context.user_data["guncelleme_modu"] = True
            context.user_data["mevcut_satir"] = row_number
            context.user_data["mevcut_grup"] = grup
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

    row_number, row, grup = mevcut_talep_satiri(context.user_data["isim"])
    if row_number:
        context.user_data["guncelleme_modu"] = True
        context.user_data["mevcut_satir"] = row_number
        context.user_data["mevcut_grup"] = grup
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
        context.user_data.pop("mevcut_grup", None)
        return await yeni_talep_baslat(update, context)

    if secim != "✅ ONAYLA VE OLUŞTUR":
        await update.message.reply_text("Lütfen aşağıdaki seçeneklerden birini kullanınız.")
        return PREVIOUS_CONFIRM

    # Prevent duplicate creation on repeated button taps.
    row_number, _, _ = mevcut_talep_satiri(context.user_data["isim"])
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
        talep_yaz(yeni_veri)
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
            eski_grup = context.user_data.get("mevcut_grup", "canli")
            yeni_grup, yeni_satir = talep_guncelle(eski_grup, row_number, yeni_veri[0])
            context.user_data["mevcut_grup"] = yeni_grup
            context.user_data["mevcut_satir"] = yeni_satir
            basari_mesaji = (
                "✅ MESAİ TALEBİNİZ BAŞARIYLA GÜNCELLENDİ\n\n"
                "📄 Mevcut talebiniz yeni bilgilerinizle güncellendi.\n"
                "⏳ Talep süresi sona erene kadar tekrar güncelleyebilirsiniz."
            )
        else:
            talep_yaz(yeni_veri[0])
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
    raw = os.environ.get("ADMIN_IDS", "").strip()
    izinli = {x.strip() for x in raw.split(",") if x.strip()}
    return str(update.effective_user.id) in izinli


def yonetici_bilgisi(update: Update):
    _, row = kayitli_kullanici_bul(update.effective_user.id)
    if row and len(row) >= 3:
        return f"{row[2].strip()} {row[1].strip()}".strip()
    return update.effective_user.first_name or str(update.effective_user.id)


def panel_klavyesi():
    return ReplyKeyboardMarkup([
        ["🟢 AÇ", "🔴 KAPAT", "📊 DURUM"],
        ["📣 DUYURU", "📋 EKSİKLER"],
        ["🚫 ENGELLE", "✅ ENGEL KALDIR"],
        ["❌ PANELİ KAPAT"]
    ], resize_keyboard=True, one_time_keyboard=False)


async def panel_ac(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not yonetici_mi(update):
        await update.message.reply_text("⛔ Bu komut yalnızca yöneticiler içindir.")
        return ConversationHandler.END
    await update.message.reply_text("🛠️ YÖNETİCİ PANELİ\n\nYapmak istediğiniz işlemi seçiniz:", reply_markup=panel_klavyesi())
    return PANEL


async def panel_secim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    secim = update.message.text.strip()
    yonetici = yonetici_bilgisi(update)
    simdi = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")

    if secim == "❌ PANELİ KAPAT":
        await update.message.reply_text("✅ Yönetici paneli kapatıldı.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if secim in {"🟢 AÇ", "🟢 TALEPLERİ AÇ"}:
        talep_durumunu_ayarla("açık")
        ayar_yaz("talep_baslangic", "")
        ayar_yaz("talep_bitis", "")
        ayar_yaz("son_acilma_zamani", simdi)
        ayar_yaz("son_acan_yonetici", yonetici)
        await update.message.reply_text(
            f"🟢 Mesai talep alımı AÇILDI.\n\n🕒 {simdi}\n👤 {yonetici}\n\n📣 Kayıtlı kullanıcılara taleplerin açıldığı bildirilsin mi?",
            reply_markup=ReplyKeyboardMarkup([["✅ BİLDİRİM GÖNDER"], ["❌ GÖNDERME"]], resize_keyboard=True, one_time_keyboard=True)
        )
        return PANEL_OPEN_NOTIFY_CONFIRM

    if secim in {"🔴 KAPAT", "🔴 TALEPLERİ KAPAT"}:
        talep_durumunu_ayarla("kapalı")
        ayar_yaz("talep_baslangic", "")
        ayar_yaz("talep_bitis", "")
        ayar_yaz("son_kapanma_zamani", simdi)
        ayar_yaz("son_kapatan_yonetici", yonetici)
        await update.message.reply_text(
            f"🔴 Mesai talep alımı KAPATILDI.\n\n🕒 {simdi}\n👤 {yonetici}\n\n📣 Kayıtlı kullanıcılara talep sürecinin kapandığı bildirilsin mi?",
            reply_markup=ReplyKeyboardMarkup([["✅ BİLDİRİM GÖNDER"], ["❌ GÖNDERME"]], resize_keyboard=True, one_time_keyboard=True)
        )
        return PANEL_CLOSE_NOTIFY_CONFIRM

    if secim in {"📊 DURUM", "📊 TALEP DURUMU"}:
        durum = "🟢 AÇIK" if talep_durumu_acik_mi() else "🔴 KAPALI"
        await update.message.reply_text(
            "📊 TALEP DURUMU\n\n"
            f"Durum: {durum}\n📁 Dönem: {aktif_donem_adi()}\n\n"
            f"🟢 Son açılma: {ayar_degeri('son_acilma_zamani', 'Kayıt yok')}\n"
            f"👤 Açan: {ayar_degeri('son_acan_yonetici', 'Kayıt yok')}\n\n"
            f"🔴 Son kapanma: {ayar_degeri('son_kapanma_zamani', 'Kayıt yok')}\n"
            f"👤 Kapatan: {ayar_degeri('son_kapatan_yonetici', 'Kayıt yok')}",
            reply_markup=panel_klavyesi()
        )
        return PANEL

    if secim in {"📣 DUYURU", "📣 GENEL DUYURU", "📣 GENEL DUYURU GÖNDER"}:
        await update.message.reply_text(
            "📣 GENEL DUYURU\n\nKayıtlı tüm kullanıcılara mesai taleplerini oluşturmaları için bildirim gönderilecek.\n\nGönderilsin mi?",
            reply_markup=ReplyKeyboardMarkup([["✅ DUYURUYU GÖNDER"], ["❌ İPTAL"]], resize_keyboard=True, one_time_keyboard=True)
        )
        return PANEL_ANNOUNCE_CONFIRM

    if secim in {"📋 EKSİKLER", "📋 TALEP VERMEYENLER"}:
        eksikler = talep_vermeyen_kullanicilar()
        if not eksikler:
            await update.message.reply_text("✅ Aktif dönemde talep vermeyen kayıtlı kullanıcı bulunmuyor.", reply_markup=panel_klavyesi())
            return PANEL
        satirlar = [f"{i}. {k['isim']} — {k['unvan'] or 'Ünvan yok'}" for i, k in enumerate(eksikler, start=1)]
        metin = f"📋 TALEP VERMEYENLER ({len(eksikler)})\n\n" + "\n".join(satirlar)
        for parca in mesaj_parcala(metin):
            await update.message.reply_text(parca)
        await update.message.reply_text(
            "Bu kişilere şimdi hatırlatma gönderilsin mi?",
            reply_markup=ReplyKeyboardMarkup([["🔔 BU KİŞİLERE HATIRLAT"], ["❌ İPTAL"]], resize_keyboard=True, one_time_keyboard=True)
        )
        return PANEL_REMIND_LIST_CONFIRM

    if secim in {"🔔 EKSİKLERE HATIRLAT", "🔔 TALEP VERMEYENLERE HATIRLAT"}:
        eksik_sayisi = len(talep_vermeyen_kullanicilar())
        if eksik_sayisi == 0:
            await update.message.reply_text("✅ Aktif dönemde hatırlatma gönderilecek talep vermeyen kullanıcı bulunmuyor.", reply_markup=panel_klavyesi())
            return PANEL
        await update.message.reply_text(
            f"🔔 HATIRLATMA\n\nAktif dönemde henüz mesai talebi oluşturmamış, kayıtlı ve engelli olmayan {eksik_sayisi} kullanıcıya hatırlatma gönderilecek.\n\nGönderilsin mi?",
            reply_markup=ReplyKeyboardMarkup([["✅ HATIRLATMAYI GÖNDER"], ["❌ İPTAL"]], resize_keyboard=True, one_time_keyboard=True)
        )
        return PANEL_REMIND_CONFIRM

    if secim in {"🚫 ENGELLE", "🚫 KULLANICI ENGELLE"}:
        await update.message.reply_text("🚫 Engellemek istediğiniz kullanıcının sistem adını yazınız:", reply_markup=ReplyKeyboardRemove())
        return PANEL_BLOCK_NAME

    if secim == "✅ ENGEL KALDIR":
        await update.message.reply_text("✅ Engelini kaldırmak istediğiniz kullanıcının sistem adını yazınız:", reply_markup=ReplyKeyboardRemove())
        return PANEL_UNBLOCK_NAME

    await update.message.reply_text("Lütfen paneldeki butonlardan birini kullanınız.", reply_markup=panel_klavyesi())
    return PANEL


def talep_vermeyen_kullanicilar():
    talep_verenler = set()
    for kayit in tablo_kayitlarini_oku():
        row = kayit["veri"]
        if row and str(row[0]).strip():
            talep_verenler.add(normalize_name(row[0]))

    eksikler = []
    gorulen_idler = set()
    engelliler = engelli_isimleri()
    for row in kullanicilar_verisi()[1:]:
        if not row:
            continue
        tid = str(row[0]).strip()
        isim = str(row[1]).strip() if len(row) > 1 else ""
        unvan = str(row[2]).strip() if len(row) > 2 else ""
        if not tid or not isim or tid in gorulen_idler:
            continue
        gorulen_idler.add(tid)
        if normalize_name(isim) in engelliler or normalize_name(isim) in talep_verenler:
            continue
        eksikler.append({"telegram_id": tid, "isim": isim, "unvan": unvan})
    return eksikler


def mesaj_parcala(metin, limit=3900):
    parcalar, mevcut = [], ""
    for satir in metin.splitlines(keepends=True):
        if len(mevcut) + len(satir) > limit and mevcut:
            parcalar.append(mevcut.rstrip())
            mevcut = ""
        mevcut += satir
    if mevcut:
        parcalar.append(mevcut.rstrip())
    return parcalar or [metin]


async def toplu_mesaj_gonder(context, mesaj, sadece_talep_vermeyenler=False):
    basarili = basarisiz = zaten_talep_vermis = engelli = 0
    gorulen_idler = set()
    talep_verenler = set()

    if sadece_talep_vermeyenler:
        for kayit in tablo_kayitlarini_oku():
            row = kayit["veri"]
            if row and str(row[0]).strip():
                talep_verenler.add(normalize_name(row[0]))

    engelliler_set = engelli_isimleri()
    for row in kullanicilar_verisi()[1:]:
        if not row:
            continue
        tid = str(row[0]).strip()
        isim = str(row[1]).strip() if len(row) > 1 else ""
        if not tid or tid in gorulen_idler:
            continue
        gorulen_idler.add(tid)
        if normalize_name(isim) in engelliler_set:
            engelli += 1
            continue
        if sadece_talep_vermeyenler and normalize_name(isim) in talep_verenler:
            zaten_talep_vermis += 1
            continue
        try:
            await context.bot.send_message(chat_id=int(tid), text=mesaj)
            basarili += 1
        except Exception as e:
            basarisiz += 1
            print(f"Toplu mesaj gönderilemedi ({tid}): {e}")
    return basarili, basarisiz, zaten_talep_vermis, engelli


async def panel_acilis_bildirim_onay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ GÖNDERME":
        await update.message.reply_text("📣 Açılış bildirimi gönderilmedi.", reply_markup=panel_klavyesi())
        return PANEL
    if update.message.text != "✅ BİLDİRİM GÖNDER":
        return PANEL_OPEN_NOTIFY_CONFIRM
    mesaj = "📣 MESAİ TALEPLERİ AÇILDI\n\nMesai taleplerinizi oluşturabilirsiniz.\n\n📝 Talebinizi oluşturmak veya mevcut talebinizi güncellemek için /start komutunu kullanabilirsiniz."
    b, x, _, e = await toplu_mesaj_gonder(context, mesaj)
    await update.message.reply_text(f"📣 AÇILIŞ BİLDİRİMİ TAMAMLANDI\n\n✅ Başarılı: {b}\n⚠️ Ulaşılamayan: {x}\n🚫 Engelli kullanıcı: {e}", reply_markup=panel_klavyesi())
    return PANEL


async def panel_kapanis_bildirim_onay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ GÖNDERME":
        await update.message.reply_text("📣 Kapanış bildirimi gönderilmedi.", reply_markup=panel_klavyesi())
        return PANEL
    if update.message.text != "✅ BİLDİRİM GÖNDER":
        return PANEL_CLOSE_NOTIFY_CONFIRM
    mesaj = "🔴 MESAİ TALEP ALIMI KAPATILDI\n\nBu dönem için mesai talep süreci sona ermiştir."
    b, x, _, e = await toplu_mesaj_gonder(context, mesaj)
    await update.message.reply_text(f"📣 KAPANIŞ BİLDİRİMİ TAMAMLANDI\n\n✅ Başarılı: {b}\n⚠️ Ulaşılamayan: {x}\n🚫 Engelli kullanıcı: {e}", reply_markup=panel_klavyesi())
    return PANEL


async def panel_hatirlatma_onay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ İPTAL":
        await update.message.reply_text("🔔 Hatırlatma gönderimi iptal edildi.", reply_markup=panel_klavyesi())
        return PANEL
    if update.message.text != "✅ HATIRLATMAYI GÖNDER":
        return PANEL_REMIND_CONFIRM
    mesaj = "🔔 MESAİ TALEBİ HATIRLATMASI\n\nBu dönem için henüz mesai talebiniz bulunmuyor.\n\n📝 Talebinizi oluşturmak için /start komutunu kullanabilirsiniz."
    b, x, z, e = await toplu_mesaj_gonder(context, mesaj, True)
    simdi = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")
    ayar_yaz("son_hatirlatma_zamani", simdi)
    ayar_yaz("son_hatirlatmayi_gonderen", yonetici_bilgisi(update))
    await update.message.reply_text(f"🔔 HATIRLATMA TAMAMLANDI\n\n✅ Gönderilen: {b}\n⚠️ Ulaşılamayan: {x}\n📋 Zaten talep vermiş: {z}\n🚫 Engelli kullanıcı: {e}", reply_markup=panel_klavyesi())
    return PANEL


async def panel_liste_hatirlatma_onay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ İPTAL":
        await update.message.reply_text("🔔 Hatırlatma gönderimi iptal edildi.", reply_markup=panel_klavyesi())
        return PANEL
    if update.message.text != "🔔 BU KİŞİLERE HATIRLAT":
        return PANEL_REMIND_LIST_CONFIRM

    mesaj = "🔔 MESAİ TALEBİ HATIRLATMASI\n\nBu dönem için henüz mesai talebiniz bulunmuyor.\n\n📝 Talebinizi oluşturmak için /start komutunu kullanabilirsiniz."
    b, x, z, e = await toplu_mesaj_gonder(context, mesaj, True)
    simdi = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")
    ayar_yaz("son_hatirlatma_zamani", simdi)
    ayar_yaz("son_hatirlatmayi_gonderen", yonetici_bilgisi(update))
    await update.message.reply_text(
        f"🔔 HATIRLATMA TAMAMLANDI\n\n✅ Gönderilen: {b}\n⚠️ Ulaşılamayan: {x}\n📋 Zaten talep vermiş: {z}\n🚫 Engelli kullanıcı: {e}",
        reply_markup=panel_klavyesi()
    )
    return PANEL


async def panel_duyuru_onay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "❌ İPTAL":
        await update.message.reply_text("📣 Duyuru gönderimi iptal edildi.", reply_markup=panel_klavyesi())
        return PANEL
    if update.message.text != "✅ DUYURUYU GÖNDER":
        await update.message.reply_text("Lütfen onay butonlarından birini kullanınız.")
        return PANEL_ANNOUNCE_CONFIRM

    mesaj = ("📣 MESAİ TALEPLERİ AÇILDI\n\n"
             "Mesai taleplerinizi oluşturabilirsiniz.\n\n"
             "📝 Talebinizi oluşturmak veya mevcut talebinizi güncellemek için /start komutunu kullanabilirsiniz.")
    basarili = basarisiz = 0
    gorulen = set()
    for row in kullanicilar_verisi()[1:]:
        if not row: continue
        tid = str(row[0]).strip()
        if not tid or tid in gorulen: continue
        gorulen.add(tid)
        try:
            await context.bot.send_message(chat_id=int(tid), text=mesaj)
            basarili += 1
        except Exception as e:
            basarisiz += 1
            print(f"Duyuru gönderilemedi ({tid}): {e}")

    simdi = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")
    ayar_yaz("son_duyuru_zamani", simdi)
    ayar_yaz("son_duyuruyu_gonderen", yonetici_bilgisi(update))
    await update.message.reply_text(
        f"📣 DUYURU GÖNDERİMİ TAMAMLANDI\n\n✅ Başarılı: {basarili}\n⚠️ Ulaşılamayan: {basarisiz}",
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
    cache_clear("engelliler")
    await update.message.reply_text(f"🚫 {isim} engellendi.", reply_markup=panel_klavyesi())
    return PANEL


async def panel_engel_kaldir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    isim = update.message.text.strip()
    hedef = normalize_name(isim)
    try:
        for row_number, value in enumerate(blocked_sheet.col_values(1), start=1):
            if row_number > 1 and normalize_name(value) == hedef:
                blocked_sheet.delete_rows(row_number)
                cache_clear("engelliler")
                await update.message.reply_text(f"✅ {isim} üzerindeki engel kaldırıldı.", reply_markup=panel_klavyesi())
                return PANEL
    except Exception as e:
        await update.message.reply_text(f"❌ Hata oluştu: {e}", reply_markup=panel_klavyesi())
        return PANEL
    await update.message.reply_text(f"ℹ️ {isim} engelli listesinde bulunamadı.", reply_markup=panel_klavyesi())
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
            PANEL_BLOCK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_kullanici_engelle)],
            PANEL_UNBLOCK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_engel_kaldir)],
            PANEL_ANNOUNCE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_duyuru_onay)],
            PANEL_OPEN_NOTIFY_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_acilis_bildirim_onay)],
            PANEL_CLOSE_NOTIFY_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_kapanis_bildirim_onay)],
            PANEL_REMIND_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_hatirlatma_onay)],
            PANEL_REMIND_LIST_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_liste_hatirlatma_onay)],
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
