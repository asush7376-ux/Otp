# ═══════════════════════════════════════════════════════════════
# OTP APP IBRAHIM — Telegram Bot (Zenex + Combos + Mino)
#   pip install "python-telegram-bot>=21.6" requests flask
#   python bot.py
# ═══════════════════════════════════════════════════════════════
import asyncio, hashlib, html, json, logging, os, re, threading, time
from collections import defaultdict

import requests
try:
    from flask import Flask
except ImportError:
    Flask = None
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler,
    ContextTypes, MessageHandler, filters,
)

# ══════════════════ TEXT BOLD HELPER (ألوان) ══════════════════
def make_bold_unicode(text):
    out = []
    for char in text:
        codepoint = ord(char)
        if 65 <= codepoint <= 90:  # A-Z
            out.append(chr(codepoint - 65 + 0x1D5D4))
        elif 97 <= codepoint <= 122:  # a-z
            out.append(chr(codepoint - 97 + 0x1D5EE))
        elif 48 <= codepoint <= 57:  # 0-9
            out.append(chr(codepoint - 48 + 0x1D7EC))
        else:
            out.append(char)
    return "".join(out)

esc = html.escape

# أزرار ملوّنة (style): تُتجاهل تلقائياً لو نسخة المكتبة لا تدعمها بدل أن يتعطل البوت
_STYLE_OK = None
def IBtn(text, style=None, **kw):
    global _STYLE_OK
    if style and _STYLE_OK is not False:
        try:
            b = InlineKeyboardButton(text, style=style, **kw)
            _STYLE_OK = True
            return b
        except TypeError:
            _STYLE_OK = False
    return InlineKeyboardButton(text, **kw)

# ══════════════════ STICKERS SECTION (ANIMATED) ══════════════════
# هذه الستيكرات كلها متحركة (Animated) وتم اختبارها
SERVICE_STICKERS = {
    "telegram":  "CAACAgQAAxkBAAMWalE9ysTxPY_EIMEcm0NLLR5TzQsAAoMVAALNcSBQbezxTdykgl48BA",
    "instagram": "CAACAgQAAxkBAAMXalE-o09K3zpAd6TZZ76xX75VMk8AAhsRAALqYClQBW59mi-1AUY8BA",
    "whatsapp":  "CAACAgQAAxkBAAMdalFNLyEkOG2l1Aw2V5PtSdeR7sQAAgMUAALzjSBTFdGk8PyPORM8BA",
    "facebook":  "CAACAgQAAxkBAAMfalFw15F8SBq8Lk-gWb9B_puK_QkAAq4VAAJ-fxFTzOJ3pX02GEM8BA",
    "tiktok":    "CAACAgQAAxkBAAMfalFw6FEoKF7x_xiLxYgFkNGc61gAAq0VAAJ-fxFTbGJtXnFQs8A8BA",
    "imo":       "",  # ← ضع file_id لستيكر imo (أرسل الستيكر للبوت ليعطيك الـ file_id)
    # لإضافة/تحديث: أرسل الستيكر مباشرة للبوت وسيرجع لك الـ file_id لتضعه هنا
}

# ══════════════════ CONFIG (edit here) ══════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "8865573357:AAHXH9kC_fIwhQRhhQuY6alSpxk6oNY6IU0")
ADMIN_IDS = [8952384711]

# Zenex — direct credentials
ZENEX_URL   = "https://api.zenexnetwork.com/v1"
ZENEX_TOKEN = os.getenv("ZENEX_TOKEN", "ZNX_KB2H1GOF4PJR4H6FN9GJ1VMX")

# Mino
MINO_API_KEY = os.getenv("MINO_API_KEY", "mino_live_286408936c463de9e9da08db0255ac1c")
MINO_BASE_URL = "https://mino-sms-panel.xyz"

# OTP group (send masked notice to this group). 0 = disabled.
OTP_GROUP_ID = -1003921031641
OTP_GROUP_LINK = "https://t.me/shHsu77"
MASK_GROUP_CODE = False
BOT_USERNAME = "@Otptestre_bot"

# رابط قناة اختياري يظهر كزر "اذهب للقناة" فقط (لا يوجد اشتراك إجباري). اتركه "" لإخفاء الزر.
CHANNEL_URL = "https://t.me/gvbhvc669"
STATE_FILE = "state.json"
USERS_FILE = "users.json"
COMBO_FILE = "combos.json"

NUMBER_TTL_MIN = 20
POLL_INTERVAL  = 3
POLL_TIMEOUT   = NUMBER_TTL_MIN * 60

SERVICE_MAP = {
    "whatsapp":  {"emoji": "🟢", "keys": ["whatsapp"],  "name": {"ar": "واتساب", "en": "WhatsApp",  "ku": "واتساپ"}},
    "facebook":  {"emoji": "🔵", "keys": ["facebook"],  "name": {"ar": "فيسبوك", "en": "Facebook",  "ku": "فەیسبوک"}},
    "telegram":  {"emoji": "✈️", "keys": ["telegram"],  "name": {"ar": "تيليجرام","en": "Telegram", "ku": "تێلێگرام"}},
    "instagram": {"emoji": "📸", "keys": ["instagram"], "name": {"ar": "إنستجرام","en": "Instagram","ku": "ئینستاگرام"}},
    "tiktok":    {"emoji": "🎵", "keys": ["tiktok"],    "name": {"ar": "تيك توك","en": "TikTok",    "ku": "تیک تۆک"}},
    "imo":       {"emoji": "💬", "keys": ["imo"],       "name": {"ar": "إيمو",   "en": "imo",       "ku": "ئیمۆ"}},
}

# اسم كل دولة بثلاث لغات
ISO_NAMES = {
    "sd":{"ar":"السودان","en":"Sudan","ku":"سوودان"},
    "eg":{"ar":"مصر","en":"Egypt","ku":"میسر"},
    "sa":{"ar":"السعودية","en":"Saudi Arabia","ku":"سعوودیە"},
    "ae":{"ar":"الإمارات","en":"UAE","ku":"ئیمارات"},
    "kw":{"ar":"الكويت","en":"Kuwait","ku":"کوەیت"},
    "qa":{"ar":"قطر","en":"Qatar","ku":"قەتەر"},
    "bh":{"ar":"البحرين","en":"Bahrain","ku":"بەحرەین"},
    "om":{"ar":"عُمان","en":"Oman","ku":"عومان"},
    "ye":{"ar":"اليمن","en":"Yemen","ku":"یەمەن"},
    "iq":{"ar":"العراق","en":"Iraq","ku":"عێراق"},
    "sy":{"ar":"سوريا","en":"Syria","ku":"سووریا"},
    "lb":{"ar":"لبنان","en":"Lebanon","ku":"لوبنان"},
    "jo":{"ar":"الأردن","en":"Jordan","ku":"ئوردن"},
    "ps":{"ar":"فلسطين","en":"Palestine","ku":"فەڵەستین"},
    "il":{"ar":"إسرائيل","en":"Israel","ku":"ئیسرائیل"},
    "tr":{"ar":"تركيا","en":"Turkey","ku":"تورکیا"},
    "ir":{"ar":"إيران","en":"Iran","ku":"ئێران"},
    "af":{"ar":"أفغانستان","en":"Afghanistan","ku":"ئەفغانستان"},
    "pk":{"ar":"باكستان","en":"Pakistan","ku":"پاکستان"},
    "in":{"ar":"الهند","en":"India","ku":"هیندستان"},
    "bd":{"ar":"بنغلاديش","en":"Bangladesh","ku":"بەنگلادێش"},
    "lk":{"ar":"سريلانكا","en":"Sri Lanka","ku":"سریلانکا"},
    "np":{"ar":"نيبال","en":"Nepal","ku":"نیپاڵ"},
    "mm":{"ar":"ميانمار","en":"Myanmar","ku":"میانمار"},
    "th":{"ar":"تايلاند","en":"Thailand","ku":"تایلەند"},
    "vn":{"ar":"فيتنام","en":"Vietnam","ku":"ڤیەتنام"},
    "id":{"ar":"إندونيسيا","en":"Indonesia","ku":"ئەندۆنیسیا"},
    "my":{"ar":"ماليزيا","en":"Malaysia","ku":"مالیزیا"},
    "sg":{"ar":"سنغافورة","en":"Singapore","ku":"سینگاپور"},
    "ph":{"ar":"الفلبين","en":"Philippines","ku":"فلیپین"},
    "cn":{"ar":"الصين","en":"China","ku":"چین"},
    "jp":{"ar":"اليابان","en":"Japan","ku":"یابان"},
    "kr":{"ar":"كوريا الجنوبية","en":"South Korea","ku":"کۆریای باشوور"},
    "kp":{"ar":"كوريا الشمالية","en":"North Korea","ku":"کۆریای باکوور"},
    "kh":{"ar":"كمبوديا","en":"Cambodia","ku":"کەمبۆدیا"},
    "la":{"ar":"لاوس","en":"Laos","ku":"لاوس"},
    "mn":{"ar":"منغوليا","en":"Mongolia","ku":"مەنگۆلیا"},
    "us":{"ar":"الولايات المتحدة","en":"United States","ku":"ئەمریکا"},
    "ca":{"ar":"كندا","en":"Canada","ku":"کەنەدا"},
    "mx":{"ar":"المكسيك","en":"Mexico","ku":"مەکسیک"},
    "br":{"ar":"البرازيل","en":"Brazil","ku":"برازیل"},
    "ar":{"ar":"الأرجنتين","en":"Argentina","ku":"ئەرجەنتین"},
    "cl":{"ar":"تشيلي","en":"Chile","ku":"چیلی"},
    "co":{"ar":"كولومبيا","en":"Colombia","ku":"کۆلۆمبیا"},
    "pe":{"ar":"بيرو","en":"Peru","ku":"پیرو"},
    "ve":{"ar":"فنزويلا","en":"Venezuela","ku":"ڤەنزوێلا"},
    "ec":{"ar":"الإكوادور","en":"Ecuador","ku":"ئیکوادۆر"},
    "bo":{"ar":"بوليفيا","en":"Bolivia","ku":"بۆلیڤیا"},
    "py":{"ar":"باراغواي","en":"Paraguay","ku":"پاراگوای"},
    "uy":{"ar":"أوروغواي","en":"Uruguay","ku":"ئوروگوای"},
    "gy":{"ar":"غيانا","en":"Guyana","ku":"گویانا"},
    "cu":{"ar":"كوبا","en":"Cuba","ku":"کووبا"},
    "ht":{"ar":"هايتي","en":"Haiti","ku":"هایتی"},
    "jm":{"ar":"جامايكا","en":"Jamaica","ku":"جامایکا"},
    "gt":{"ar":"غواتيمالا","en":"Guatemala","ku":"گواتیمالا"},
    "sv":{"ar":"السلفادور","en":"El Salvador","ku":"سالڤادۆر"},
    "hn":{"ar":"هندوراس","en":"Honduras","ku":"هوندۆراس"},
    "cr":{"ar":"كوستاريكا","en":"Costa Rica","ku":"کۆستاریکا"},
    "pa":{"ar":"بنما","en":"Panama","ku":"پەنەما"},
    "bz":{"ar":"بليز","en":"Belize","ku":"بێلیز"},
    "gb":{"ar":"بريطانيا","en":"United Kingdom","ku":"بەریتانیا"},
    "fr":{"ar":"فرنسا","en":"France","ku":"فەڕەنسا"},
    "de":{"ar":"ألمانيا","en":"Germany","ku":"ئەڵمانیا"},
    "it":{"ar":"إيطاليا","en":"Italy","ku":"ئیتاڵیا"},
    "es":{"ar":"إسبانيا","en":"Spain","ku":"ئیسپانیا"},
    "pt":{"ar":"البرتغال","en":"Portugal","ku":"پورتوگاڵ"},
    "nl":{"ar":"هولندا","en":"Netherlands","ku":"هۆڵەندا"},
    "be":{"ar":"بلجيكا","en":"Belgium","ku":"بەلجیکا"},
    "ch":{"ar":"سويسرا","en":"Switzerland","ku":"سویسرا"},
    "at":{"ar":"النمسا","en":"Austria","ku":"نەمسا"},
    "se":{"ar":"السويد","en":"Sweden","ku":"سوید"},
    "no":{"ar":"النرويج","en":"Norway","ku":"نەرویج"},
    "dk":{"ar":"الدنمارك","en":"Denmark","ku":"دانمارک"},
    "fi":{"ar":"فنلندا","en":"Finland","ku":"فینلاندا"},
    "ie":{"ar":"أيرلندا","en":"Ireland","ku":"ئیرلەندا"},
    "hu":{"ar":"المجر","en":"Hungary","ku":"هەنگاریا"},
    "pl":{"ar":"بولندا","en":"Poland","ku":"پۆڵۆنیا"},
    "ua":{"ar":"أوكرانيا","en":"Ukraine","ku":"ئۆکرانیا"},
    "ru":{"ar":"روسيا","en":"Russia","ku":"ڕووسیا"},
    "by":{"ar":"بيلاروسيا","en":"Belarus","ku":"بێلاڕوس"},
    "lt":{"ar":"ليتوانيا","en":"Lithuania","ku":"لیتوانیا"},
    "lv":{"ar":"لاتفيا","en":"Latvia","ku":"لاتڤیا"},
    "ee":{"ar":"إستونيا","en":"Estonia","ku":"ئیستۆنیا"},
    "md":{"ar":"مولدوفا","en":"Moldova","ku":"مۆلدۆڤا"},
    "am":{"ar":"أرمينيا","en":"Armenia","ku":"ئەرمینیا"},
    "az":{"ar":"أذربيجان","en":"Azerbaijan","ku":"ئازەربایجان"},
    "ge":{"ar":"جورجيا","en":"Georgia","ku":"جۆرجیا"},
    "kg":{"ar":"قيرغيزستان","en":"Kyrgyzstan","ku":"قرغیزستان"},
    "tj":{"ar":"طاجيكستان","en":"Tajikistan","ku":"تاجیکستان"},
    "tm":{"ar":"تركمانستان","en":"Turkmenistan","ku":"تورکمانستان"},
    "uz":{"ar":"أوزبكستان","en":"Uzbekistan","ku":"ئوزبەکستان"},
    "ro":{"ar":"رومانيا","en":"Romania","ku":"ڕۆمانیا"},
    "bg":{"ar":"بلغاريا","en":"Bulgaria","ku":"بولگاریا"},
    "rs":{"ar":"صربيا","en":"Serbia","ku":"سربیا"},
    "hr":{"ar":"كرواتيا","en":"Croatia","ku":"کرواتیا"},
    "si":{"ar":"سلوفينيا","en":"Slovenia","ku":"سلۆڤینیا"},
    "sk":{"ar":"سلوفاكيا","en":"Slovakia","ku":"سلۆڤاکیا"},
    "cz":{"ar":"التشيك","en":"Czech Republic","ku":"چیک"},
    "ba":{"ar":"البوسنة","en":"Bosnia","ku":"بۆسنیا"},
    "me":{"ar":"الجبل الأسود","en":"Montenegro","ku":"مۆنتێنیگرۆ"},
    "mk":{"ar":"مقدونيا","en":"North Macedonia","ku":"مەقدۆنیا"},
    "al":{"ar":"ألبانيا","en":"Albania","ku":"ئەڵبانیا"},
    "gr":{"ar":"اليونان","en":"Greece","ku":"یۆنان"},
    "cy":{"ar":"قبرص","en":"Cyprus","ku":"قوبرس"},
    "mt":{"ar":"مالطا","en":"Malta","ku":"ماڵتا"},
    "is":{"ar":"آيسلندا","en":"Iceland","ku":"ئایسلاندا"},
    "lu":{"ar":"لوكسمبورغ","en":"Luxembourg","ku":"لوکسەمبورگ"},
    "mc":{"ar":"موناكو","en":"Monaco","ku":"مۆناکۆ"},
    "ad":{"ar":"أندورا","en":"Andorra","ku":"ئەندۆرا"},
    "gi":{"ar":"جبل طارق","en":"Gibraltar","ku":"جەبەل تارق"},
    "fo":{"ar":"جزر فارو","en":"Faroe Islands","ku":"دوورگەکانی فارۆ"},
    "gl":{"ar":"غرينلاند","en":"Greenland","ku":"گرینلاند"},
    "au":{"ar":"أستراليا","en":"Australia","ku":"ئوسترالیا"},
    "nz":{"ar":"نيوزيلندا","en":"New Zealand","ku":"نیوزیلاند"},
    "fj":{"ar":"فيجي","en":"Fiji","ku":"فیجی"},
    "pg":{"ar":"بابوا غينيا الجديدة","en":"Papua New Guinea","ku":"پاپوا"},
    "ma":{"ar":"المغرب","en":"Morocco","ku":"مەغریب"},
    "dz":{"ar":"الجزائر","en":"Algeria","ku":"جەزائیر"},
    "tn":{"ar":"تونس","en":"Tunisia","ku":"تونس"},
    "ly":{"ar":"ليبيا","en":"Libya","ku":"لیبیا"},
    "et":{"ar":"إثيوبيا","en":"Ethiopia","ku":"ئەتیۆپیا"},
    "so":{"ar":"الصومال","en":"Somalia","ku":"سۆماڵ"},
    "dj":{"ar":"جيبوتي","en":"Djibouti","ku":"جیبووتی"},
    "tz":{"ar":"تنزانيا","en":"Tanzania","ku":"تانزانیا"},
    "ug":{"ar":"أوغندا","en":"Uganda","ku":"ئوگاندا"},
    "bi":{"ar":"بوروندي","en":"Burundi","ku":"بوروندی"},
    "mz":{"ar":"موزمبيق","en":"Mozambique","ku":"مۆزەمبیک"},
    "zm":{"ar":"زامبيا","en":"Zambia","ku":"زامبیا"},
    "zw":{"ar":"زيمبابوي","en":"Zimbabwe","ku":"زیمبابوی"},
    "na":{"ar":"ناميبيا","en":"Namibia","ku":"نامیبیا"},
    "mw":{"ar":"مالاوي","en":"Malawi","ku":"ماڵاوی"},
    "ls":{"ar":"ليسوتو","en":"Lesotho","ku":"لیسۆتۆ"},
    "bw":{"ar":"بوتسوانا","en":"Botswana","ku":"بۆتسوانا"},
    "sz":{"ar":"إسواتيني","en":"Eswatini","ku":"سوازیلاند"},
    "km":{"ar":"جزر القمر","en":"Comoros","ku":"کۆمۆرۆس"},
    "gm":{"ar":"غامبيا","en":"Gambia","ku":"گامبیا"},
    "sn":{"ar":"السنغال","en":"Senegal","ku":"سینیگاڵ"},
    "mr":{"ar":"موريتانيا","en":"Mauritania","ku":"مۆریتانیا"},
    "ml":{"ar":"مالي","en":"Mali","ku":"ماڵی"},
    "gn":{"ar":"غينيا","en":"Guinea","ku":"گینێ"},
    "bf":{"ar":"بوركينا فاسو","en":"Burkina Faso","ku":"بورکینا فاسۆ"},
    "ne":{"ar":"النيجر","en":"Niger","ku":"نیجەر"},
    "tg":{"ar":"توغو","en":"Togo","ku":"تۆگۆ"},
    "bj":{"ar":"بنين","en":"Benin","ku":"بێنین"},
    "mu":{"ar":"موريشيوس","en":"Mauritius","ku":"مۆریشس"},
    "lr":{"ar":"ليبيريا","en":"Liberia","ku":"لیبێریا"},
    "sl":{"ar":"سيراليون","en":"Sierra Leone","ku":"سیرالیۆن"},
    "cm":{"ar":"الكاميرون","en":"Cameroon","ku":"کامیرۆن"},
    "ci":{"ar":"ساحل العاج","en":"Ivory Coast","ku":"کۆتی دیڤوار"},
    "mg":{"ar":"مدغشقر","en":"Madagascar","ku":"مەدەگاسکار"},
    "td":{"ar":"تشاد","en":"Chad","ku":"چاد"},
    "cf":{"ar":"إفريقيا الوسطى","en":"Central African Republic","ku":"ئەفریقای ناوەڕاست"},
    "cv":{"ar":"الرأس الأخضر","en":"Cape Verde","ku":"کاپڤێرد"},
    "st":{"ar":"ساو تومي","en":"Sao Tome","ku":"ساوتۆمێ"},
    "gq":{"ar":"غينيا الاستوائية","en":"Equatorial Guinea","ku":"گینێی ئیستوایی"},
    "ga":{"ar":"الغابون","en":"Gabon","ku":"گابۆن"},
    "cg":{"ar":"الكونغو","en":"Congo","ku":"کۆنگۆ"},
    "cd":{"ar":"جمهورية الكونغو الديمقراطية","en":"DR Congo","ku":"کۆنگۆی د.ک."},
    "ao":{"ar":"أنغولا","en":"Angola","ku":"ئەنگۆلا"},
    "gw":{"ar":"غينيا بيساو","en":"Guinea-Bissau","ku":"گینێ بیساو"},
    "sh":{"ar":"سانت هيلينا","en":"Saint Helena","ku":"سانت هیلینا"},
    "sc":{"ar":"سيشل","en":"Seychelles","ku":"سیشێل"},
    "rw":{"ar":"رواندا","en":"Rwanda","ku":"ڕواندا"},
    "er":{"ar":"إريتريا","en":"Eritrea","ku":"ئێریتریا"},
    "ng":{"ar":"نيجيريا","en":"Nigeria","ku":"نایجیریا"},
    "ke":{"ar":"كينيا","en":"Kenya","ku":"کینیا"},
    "gh":{"ar":"غانا","en":"Ghana","ku":"گانا"},
    "za":{"ar":"جنوب أفريقيا","en":"South Africa","ku":"باشوری ئەفریقا"},
}

CC_TO_ISO = {
    "20":"eg","27":"za","30":"gr","31":"nl","32":"be","33":"fr","34":"es","36":"hu",
    "39":"it","40":"ro","41":"ch","43":"at","44":"gb","45":"dk","46":"se","47":"no",
    "48":"pl","49":"de","51":"pe","52":"mx","53":"cu","54":"ar","55":"br","56":"cl",
    "57":"co","58":"ve","60":"my","61":"au","62":"id","63":"ph","64":"nz","65":"sg",
    "66":"th","81":"jp","82":"kr","84":"vn","86":"cn","90":"tr","91":"in","92":"pk",
    "93":"af","94":"lk","95":"mm","98":"ir","1":"us","7":"ru",
    "212":"ma","213":"dz","216":"tn","218":"ly","220":"gm","221":"sn","222":"mr",
    "223":"ml","224":"gn","225":"ci","226":"bf","227":"ne","228":"tg","229":"bj",
    "230":"mu","231":"lr","232":"sl","233":"gh","234":"ng","235":"td","236":"cf",
    "237":"cm","238":"cv","239":"st","240":"gq","241":"ga","242":"cg","243":"cd",
    "244":"ao","245":"gw","247":"sh","248":"sc","249":"sd","250":"rw","251":"et",
    "252":"so","253":"dj","254":"ke","255":"tz","256":"ug","257":"bi","258":"mz",
    "260":"zm","261":"mg","263":"zw","264":"na","265":"mw","266":"ls","267":"bw",
    "268":"sz","269":"km","290":"sh","291":"er","298":"fo","299":"gl",
    "350":"gi","351":"pt","352":"lu","353":"ie","354":"is","355":"al","356":"mt",
    "357":"cy","358":"fi","359":"bg","370":"lt","371":"lv","372":"ee","373":"md",
    "374":"am","375":"by","376":"ad","377":"mc","380":"ua","381":"rs","382":"me",
    "385":"hr","386":"si","387":"ba","389":"mk","420":"cz","421":"sk",
    "501":"bz","502":"gt","503":"sv","504":"hn","506":"cr","507":"pa","509":"ht",
    "591":"bo","592":"gy","593":"ec","595":"py","598":"uy",
    "670":"tl","675":"pg","679":"fj","850":"kp","852":"hk","853":"mo","855":"kh",
    "856":"la","880":"bd","886":"tw",
    "960":"mv","961":"lb","962":"jo","963":"sy","964":"iq","965":"kw","966":"sa",
    "967":"ye","968":"om","970":"ps","971":"ae","972":"il","973":"bh","974":"qa",
    "975":"bt","976":"mn","977":"np","992":"tj","993":"tm","994":"az","995":"ge",
    "996":"kg","998":"uz",
}

def find_iso_by_name(text):
    """يقبل ISO / اسم دولة (عربي/إن/كردي) / رمز اتصال / رقم كامل."""
    s = str(text or "").strip().lower()
    if not s: return ""
    if s in ISO_NAMES: return s
    if s in CC_TO_ISO: return CC_TO_ISO[s]
    digits = re.sub(r"\D","", s)
    if digits:
        for L in (4,3,2,1):
            if len(digits) >= L and digits[:L] in CC_TO_ISO: return CC_TO_ISO[digits[:L]]
    for iso, d in ISO_NAMES.items():
        for v in d.values():
            if v.lower() == s: return iso
    for iso, d in ISO_NAMES.items():
        for v in d.values():
            if len(s) >= 3 and (s in v.lower() or v.lower() in s): return iso
    return ""

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger("otp")

# ══════════════════ i18n ══════════════════
T = {
    "ar": {"hi":"أهلاً","get_number":"📞 احصل على رقم","language":"🌐 اللغة",
        "admin_panel":"🛠 لوحة الأدمن","pick_service":"📱 اختر الخدمة:","pick_country":"🌍 اختر الدولة:",
        "no_country":"⚠️ لا توجد دول متاحة حالياً.","reserving":"⏳ جاري حجز الرقم...",
        "reserved":"✅ تم حجز الرقم","no_range":"⚠️ لا يوجد رقم متاح لهذه الدولة.",
        "waiting_code":"⏳ بانتظار الكود...","code_arrived":"🔐 وصل الكود!",
        "cancel_number":"❌ إلغاء","change_country":"🌍 تغيير الدولة","new_number":"🔄 رقم جديد",
        "back":"⬅️ رجوع","copy":"📋 نسخ","timeout":"⌛ انتهت المهلة","banned":"⛔ محظور",
        "admin_only":"⛔ للأدمن فقط","choose_lang":"🌐 اختر لغتك:","lang_set":"✅ تم تغيير اللغة",
        "add_range_zenex":"➕ إضافة رينج زينيكس","add_range_mino":"➕ إضافة رينج Mino",
        "code_label":"🔑 الرمز","copy_hint":"(اضغط على الرمز/الرقم لنسخه)",
        "back_ar":"⬅️ رجوع",
        "operator":"📶 المشغل","service":"📱 الخدمة","country":"🌍 الدولة","number":"☎️ الرقم",
        "open_bot":"🤖 افتح البوت لرؤية الكود","join_group":"🔔 جروب OTP","goto_group":"🔔 اذهب لجروب OTP",
        "goto_channel":"📢 اذهب للقناة","otp_arrived":"🔔 وصل OTP!","pulled_by":"👤 سحب بواسطة","code_word":"الرمز",
        "code_hidden":"🔒 الكود مخفي — افتح البوت لعرضه",
        "copy_code":"📋 نسخ الكود","repeat_last":"🔁 كرر آخر طلب","history":"📜 السجل","my_history":"📜 سجل رموزي",
        "no_history":"لا يوجد أي رمز في السجل بعد.","waiting_second":"⏳ بانتظار كود ثاني (60ث)...",
        "second_code":"🔐 كود ثانٍ وصل!","stats_me":"📊 إحصائياتي","favorite":"⭐ المفضلة"},
    "en": {"hi":"Hi","get_number":"📞 Get Number","language":"🌐 Language",
        "admin_panel":"🛠 Admin","pick_service":"📱 Choose a service:","pick_country":"🌍 Choose a country:",
        "no_country":"⚠️ No countries available.","reserving":"⏳ Reserving...",
        "reserved":"✅ Number reserved","no_range":"⚠️ No number available.",
        "waiting_code":"⏳ Waiting for code...","code_arrived":"🔐 Code received!",
        "cancel_number":"❌ Cancel","change_country":"🌍 Change Country","new_number":"🔄 New Number",
        "back":"⬅️ Back","copy":"📋 Copy","timeout":"⌛ Timed out","banned":"⛔ Banned",
        "admin_only":"⛔ Admin only","choose_lang":"🌐 Choose language:","lang_set":"✅ Language updated",
        "add_range_zenex":"➕ Add Zenex range","add_range_mino":"➕ Add Mino range",
        "code_label":"🔑 Code","copy_hint":"(Tap the code/number to copy)",
        "back_ar":"⬅️ Back",
        "operator":"📶 Operator","service":"📱 Service","country":"🌍 Country","number":"☎️ Number",
        "open_bot":"🤖 Open the bot to see the code","join_group":"🔔 OTP Group","goto_group":"🔔 Go to OTP Group",
        "goto_channel":"📢 Go to Channel","otp_arrived":"🔔 OTP Received!","pulled_by":"👤 Pulled by","code_word":"Code",
        "code_hidden":"🔒 Code hidden — open the bot to view it",
        "copy_code":"📋 Copy Code","repeat_last":"🔁 Repeat Last","history":"📜 History","my_history":"📜 My OTP History",
        "no_history":"No OTPs in history yet.","waiting_second":"⏳ Waiting for second code (60s)...",
        "second_code":"🔐 Second code received!","stats_me":"📊 My Stats","favorite":"⭐ Favorites"},
    "ku": {"hi":"بەخێربێی","get_number":"📞 وەرگرتنی ژمارە","language":"🌐 زمان",
        "admin_panel":"🛠 ئەدمین","pick_service":"📱 خزمەتگوزارییەک هەڵبژێرە:","pick_country":"🌍 وڵاتێک هەڵبژێرە:",
        "no_country":"⚠️ هیچ وڵاتێک بەردەست نییە.","reserving":"⏳ خەریکە ژمارە دەگرێت...",
        "reserved":"✅ ژمارە گیرا","no_range":"⚠️ ژمارە بەردەست نییە.",
        "waiting_code":"⏳ چاوەڕوانی کۆد...","code_arrived":"🔐 کۆد گەیشت!",
        "cancel_number":"❌ هەڵوەشاندنەوە","change_country":"🌍 گۆڕینی وڵات","new_number":"🔄 ژمارەیەکی نوێ",
        "back":"⬅️ گەڕانەوە","copy":"📋 لەبەرگرتنەوە","timeout":"⌛ کاتی تەواو بوو","banned":"⛔ قەدەغەکراوی",
        "admin_only":"⛔ تەنیا بۆ ئەدمین","choose_lang":"🌐 زمانەکەت هەڵبژێرە:","lang_set":"✅ زمان گۆڕدرا",
        "add_range_zenex":"➕ زیادکردنی ڕەنجی Zenex","add_range_mino":"➕ زیادکردنی ڕەنجی Mino",
        "code_label":"🔑 کۆد","copy_hint":"(کلیک لە کۆد/ژمارە بۆ کۆپیکردن)",
        "back_ar":"⬅️ گەڕانەوە",
        "operator":"📶 ئۆپەراتۆر","service":"📱 خزمەتگوزاری","country":"🌍 وڵات","number":"☎️ ژمارە",
        "open_bot":"🤖 بۆتەکە بکەرەوە بۆ بینینی کۆد","join_group":"🔔 گرووپی OTP","goto_group":"🔔 بڕۆ بۆ گرووپی OTP",
        "goto_channel":"📢 بڕۆ بۆ کەناڵ","otp_arrived":"🔔 کۆد گەیشت!","pulled_by":"👤 وەرگیرا لەلایەن","code_word":"کۆد",
        "code_hidden":"🔒 کۆد شاراوەیە — بۆتەکە بکەرەوە",
        "copy_code":"📋 کۆپی کۆد","repeat_last":"🔁 دووبارەکردنەوە","history":"📜 مێژوو","my_history":"📜 مێژووی کۆدەکانم",
        "no_history":"هیچ کۆدێک لە مێژوودا نییە.","waiting_second":"⏳ چاوەڕوانی کۆدی دووەم (٦٠چ)...",
        "second_code":"🔐 کۆدی دووەم گەیشت!","stats_me":"📊 ئامارەکانم","favorite":"⭐ دڵخوازەکان"},
}
def tr(lang, k): return T.get(lang, T["ar"]).get(k, T["ar"].get(k, k))
def svc_name(sid, lang):
    s = SERVICE_MAP.get(sid)
    return s["name"].get(lang, s["name"]["en"]) if s else sid
def iso_name(iso, lang):
    d = ISO_NAMES.get((iso or "").lower())
    return d.get(lang, d.get("en")) if d else (iso or "").upper()

# ══════════════════ Storage ══════════════════
def _load(fp, default):
    if not os.path.exists(fp): _save(fp, default); return default
    try:
        with open(fp, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return default
def _save(fp, data):
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

STATE  = _load(STATE_FILE, {"disabled": [], "custom": {}, "mino_ranges": []})
USERS  = _load(USERS_FILE, {})
COMBOS = _load(COMBO_FILE, {})
STATE.pop("provider", None); STATE.setdefault("custom", {}); STATE.setdefault("disabled", []); STATE.setdefault("mino_ranges", [])

def save_state(): _save(STATE_FILE, STATE)
def save_users(): _save(USERS_FILE, USERS)
def save_combos(): _save(COMBO_FILE, COMBOS)

RESERVATIONS = {}
LAST_OTP = _load("last_otp.json", None)

def save_last_otp(): _save("last_otp.json", LAST_OTP)
def _norm_num(n): return re.sub(r"\D", "", str(n or ""))
def register_reservation(number, uid, sid, iso, svc_name_, country):
    k = _norm_num(number)
    if not k: return
    RESERVATIONS[k] = {"uid": int(uid), "sid": sid, "iso": iso, "svc_name": svc_name_, "country": country, "ts": int(time.time())}
def unregister_reservation(number): RESERVATIONS.pop(_norm_num(number), None)
def find_reserver(number): return RESERVATIONS.get(_norm_num(number))

def set_last_otp(uid, number, code, svc_name_, country, iso):
    global LAST_OTP
    u = USERS.get(str(uid), {}) if uid else {}
    LAST_OTP = {"uid": int(uid) if uid else 0, "name": u.get("name") or "", "username": u.get("username") or "", "number": str(number), "code": str(code), "service": svc_name_, "country": country, "iso": iso, "ts": int(time.time())}
    save_last_otp()

def get_user(uid):
    k = str(uid)
    if k not in USERS:
        USERS[k] = {"lang":"ar","banned":False, "stats":{"numbers":0,"otps":0,"cancels":0}, "history":[], "joined": int(time.time())}
        save_users()
    u = USERS[k]
    u.setdefault("lang","ar"); u.setdefault("stats",{"numbers":0,"otps":0,"cancels":0}); u.setdefault("history",[])
    return u

def note_user(tg_user):
    u = get_user(tg_user.id)
    try:
        u["name"] = tg_user.full_name
        u["username"] = tg_user.username or ""
        u.setdefault("joined", int(time.time()))
        save_users()
    except Exception: pass
    return u

def flag(iso):
    if not iso or len(iso) != 2: return "🌍"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in iso.upper())
def guess_iso(number):
    d = re.sub(r"\D", "", number or "")
    for L in (3,2,1):
        if len(d) >= L and d[:L] in CC_TO_ISO: return CC_TO_ISO[d[:L]]
    return ""
def mask_number(num):
    d = re.sub(r"\D", "", num or "")
    if len(d) < 6: return "•" * len(d)
    prefix = "+" if str(num).startswith("+") else ""
    return f"{prefix}{d[:3]}{'★'*(len(d)-5)}{d[-2:]}"
def mask_code(code):
    s = str(code or "")
    if len(s) <= 2: return "★" * max(1, len(s))
    return f"{s[0]}{'★'*(len(s)-1)}"

# ══════════════════ Zenex ══════════════════
def zx_headers(): return {"mapikey": ZENEX_TOKEN, "Content-Type":"application/json","Accept":"application/json"}
def zx_active_ranges():
    try:
        r = requests.get(f"{ZENEX_URL}/active-ranges", headers=zx_headers(), timeout=15)
        if not r.ok: return []
        return ((r.json().get("data") or {}).get("active_ranges") or [])
    except Exception: return []
def zx_get_number(rng):
    try:
        r = requests.post(f"{ZENEX_URL}/getnum", headers=zx_headers(), json={"range": rng, "is_national": False, "remove_plus": False}, timeout=20)
        if not r.ok: return None
        d = r.json().get("data") or {}
        num = d.get("number") or d.get("copy") or d.get("full_number")
        if not num: return None
        return {"number": str(num), "country": d.get("country") or "", "iso": (d.get("iso") or "").lower(), "operator": d.get("operator") or ""}
    except Exception: return None
def zx_cancel(number):
    try: requests.post(f"{ZENEX_URL}/cancelnum", headers=zx_headers(), json={"number": number}, timeout=10)
    except Exception: pass
def zx_fetch_otps():
    try:
        r = requests.get(f"{ZENEX_URL}/numsuccess/info", headers=zx_headers(), timeout=15)
        if not r.ok: return []
        return ((r.json().get("data") or {}).get("otps") or [])
    except Exception: return []

# ══════════════════ Mino ══════════════════
# API الفعلي لموقع mino-sms-panel.xyz (حسب توثيق /docs):
#   POST/GET /getnumber   ?api_key=&rid=&national_format=0/1&remove_plus=0/1
#   GET      /check       ?api_key=&number=
#   GET      /live        ?api_key=
#   GET      /success_otp ?api_key=
#   GET      /console     ?api_key=
# ملاحظة: الرينجات (rid) تُضاف يدوياً من الأدمن (لا يوجد endpoint لسردها).
class MinoSource:
    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base = base_url.rstrip("/")

    def _get(self, path, params=None):
        try:
            params = dict(params or {})
            params.setdefault("api_key", self.api_key)
            r = requests.get(f"{self.base}{path}", params=params, timeout=15)
            if r.ok:
                try: return r.json()
                except Exception: return {"raw": r.text}
        except Exception as e:
            logging.warning(f"Mino GET {path} error: {e}")
        return None

    def ranges(self):
        """يبني الرينجات من قائمة STATE['mino_ranges'] التي يضيفها الأدمن يدوياً."""
        out = []
        for r in STATE.get("mino_ranges", []):
            rid  = str(r.get("rid") or "").strip()
            sid  = (r.get("sid") or "").lower()
            iso  = (r.get("iso") or "").lower()
            hits = int(r.get("hits") or 1)
            if not rid or not sid or sid not in SERVICE_MAP: continue
            country = r.get("country") or iso_name(iso, "en") or iso.upper()
            out.append({
                "service": sid,
                "range":   f"mino::{rid}::{sid}::{iso}",
                "iso":     iso,
                "hits":    hits,
                "country": country,
            })
        return out

    def get_number(self, rng):
        """rng = mino::<rid>::<sid>::<iso> — يعالج JSON + text (ACCESS_NUMBER:ID:NUMBER) + raw."""
        try:
            parts = rng.split("::")
            if len(parts) < 4: return None
            _, rid, sid, iso = parts[0], parts[1], parts[2], parts[3]
            # نفس صيغة URL في bot.py المرجعي مع fallback params
            url = f"{self.base}/getnumber"
            params = {"api_key": self.api_key, "rid": rid, "range": rid,
                      "target": rid, "national": 1, "remove_plus": 1}
            r = requests.get(url, params=params, timeout=20)
            if not r.ok:
                logging.warning(f"Mino getnumber HTTP {r.status_code}: {r.text[:200]}")
                return None
            raw_text = r.text.strip()
            if not raw_text: return None
            err_keywords = ["NO_NUMBERS","NO_NUMBER","OUT_OF_STOCK","BANNED","LIMIT","ERROR","BALANCE","EMPTY","SQL"]
            number = None
            # 1) JSON: إن وُجد رقم فهو نجاح بغض النظر عن باقي الحقول
            try:
                data = r.json()
            except Exception:
                data = None
            if isinstance(data, dict):
                d = data.get("data") if isinstance(data.get("data"), dict) else data
                number = (d.get("full_number") or d.get("number") or d.get("phone")
                          or d.get("phoneNumber") or d.get("mobile"))
                if not number and str(data.get("status")).lower() in ["error","fail","false"]:
                    return None
            if not number:
                if any(err in raw_text.upper() for err in err_keywords):
                    logging.info(f"Mino no number for rid={rid}: {raw_text[:100]}")
                    return None
                # 2) split على : أو |
                for part in reversed(re.split(r'[:|]', raw_text)):
                    clean = re.sub(r'\D','', part.strip())
                    if 7 <= len(clean) <= 15:
                        number = clean; break
            # 3) نص خام
            if not number:
                clean_all = re.sub(r'\D','', raw_text)
                if 7 <= len(clean_all) <= 15:
                    number = clean_all
            if not number: return None
            clean_num = re.sub(r'\D','', str(number))
            real_iso = iso or guess_iso(clean_num) or iso
            return {"number": clean_num,
                    "country": iso_name(real_iso, "en") or real_iso.upper(),
                    "iso": real_iso, "operator": "Mino"}
        except Exception as e:
            logging.warning(f"Mino get_number error: {e}")
        return None

    def fetch_otps(self):
        new = []
        try:
            data = self._get("/success_otp")
            if not data: return new
            otps = data.get("otps") or data.get("data") or data.get("results") or []
            if isinstance(otps, dict): otps = otps.get("items") or []
            for otp in otps:
                if not isinstance(otp, dict): continue
                number  = otp.get("number") or otp.get("phone") or ""
                message = otp.get("message") or otp.get("sms") or otp.get("text") or ""
                code    = otp.get("otp_code") or otp.get("otp") or otp.get("code") or ""
                if not (number and code): continue
                uid = f"mino:{number}:{code}:{otp.get('id') or otp.get('timestamp') or ''}"
                new.append({"id": uid, "number": str(number), "code": str(code),
                            "otp": str(code), "message": message,
                            "date": otp.get("timestamp") or "",
                            "service": otp.get("service") or "",
                            "country": otp.get("country") or ""})
        except Exception as e:
            logging.warning(f"Mino fetch_otps error: {e}")
        return new

    def check(self, number):
        return self._get("/check", {"number": number})

MINO = MinoSource(MINO_API_KEY, MINO_BASE_URL)

# ══════════════════ Login / health status ══════════════════
def zenex_status():
    try:
        r = requests.get(f"{ZENEX_URL}/active-ranges", headers=zx_headers(), timeout=15)
        if r.ok: return True, f"✅ ناجح ({len((r.json().get('data') or {}).get('active_ranges') or [])} رينج نشط)"
        return False, f"❌ فشل (HTTP {r.status_code})"
    except Exception as e: return False, f"❌ خطأ: {e}"

def mino_status():
    try:
        numbers = MINO.ranges()
        return (True, f"✅ ناجح ({len(numbers)} رقم)") if numbers is not None else (False, "❌ فشل")
    except Exception as e: return False, f"❌ خطأ: {e}"

def logins_report():
    zx_ok, zx_msg = zenex_status()
    mino_ok, mino_msg = mino_status()
    return (
        "🔐 <b>حالة الدخول للمواقع</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔹 <b>Zenex</b>: {zx_msg}\n"
        f"🔹 <b>Mino</b>: {mino_msg}\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )

# ══════════════════ Unified ranges ══════════════════
_CACHE = {}
def _cached(key, fn, ttl=15):
    now = time.time(); e = _CACHE.get(key)
    if e and now - e[0] < ttl: return e[1]
    data = fn()
    if data: _CACHE[key] = (now, data)
    return data

def all_ranges():
    base = []
    # 1. Zenex
    base.extend(_cached("zx", zx_active_ranges))
    # 2. Custom (رينجات زينيكس اليدوية)
    for sid, arr in STATE.get("custom", {}).items():
        for r in arr: base.append({**r, "service": sid})
    # 3. Mino
    try:
        base.extend(MINO.ranges())
    except Exception: pass
    return base

def ranges_for_service(sid):
    svc = SERVICE_MAP.get(sid)
    if not svc: return []
    keys = svc["keys"]
    out = []
    for r in all_ranges():
        s = str(r.get("service") or "").lower()
        if any(k in s for k in keys):
            iso = (r.get("iso") or "").lower() or guess_iso(str(r.get("range","")))
            out.append({"range": r["range"], "iso": iso, "hits": int(r.get("hits") or 0)})
    for name, c in COMBOS.get(sid, {}).items():
        remaining = [n for n in c.get("numbers", []) if n not in c.get("used", []) and not find_reserver(n)]
        if remaining:
            iso = c.get("iso") or guess_iso(remaining[0])
            out.append({"range": f"combo::{sid}::{name}", "iso": iso, "hits": len(remaining), "combo": name})
    return out

def _gkey_of(r):
    # Unique group key: allows two ranges with same ISO (e.g. Guinea 1 / Guinea 2)
    gid = r.get("gid")
    if gid: return f"{r.get('iso') or '??'}#{gid}"
    return r.get("iso") or "??"

def countries_for_service(sid):
    groups = defaultdict(lambda: {"iso":"","gkey":"","label":"","country":"","ranges":[],"hits":0})
    for r in ranges_for_service(sid):
        gk = _gkey_of(r)
        g = groups[gk]
        g["gkey"] = gk
        g["iso"] = r.get("iso") or ""
        g["label"] = r.get("gid") or ""
        if not g["country"]: g["country"] = r.get("country") or ""
        g["ranges"].append(r); g["hits"] += r["hits"]
    return sorted(groups.values(), key=lambda x: (-x["hits"], x["iso"], x["label"]))

def best_range(sid, gkey):
    for c in countries_for_service(sid):
        if c["gkey"] == gkey or c["iso"] == gkey:  # backward compatible
            rs = sorted(c["ranges"], key=lambda r: -r["hits"])
            return rs[0] if rs else None
    return None

def reserve_number(rng):
    if rng.startswith("combo::"):
        _, sid, name = rng.split("::", 2)
        c = COMBOS.get(sid, {}).get(name)
        if not c: return None
        rem = [n for n in c["numbers"] if n not in c.get("used", []) and not find_reserver(n)]
        if not rem: return None
        num = rem[0]
        return {"number": num, "country": name, "iso": c.get("iso") or guess_iso(num), "operator": "combo", "combo": (sid, name)}
    if rng.startswith("mino::"):
        return MINO.get_number(rng)
    return zx_get_number(rng)

def cancel_number(number): zx_cancel(number)

def consume_combo(sid, name, number):
    c = COMBOS.get(sid, {}).get(name)
    if not c: return
    c.setdefault("used", []).append(number)
    c["numbers"] = [n for n in c["numbers"] if n != number]
    save_combos()

_OTP_CACHE = {"ts": 0.0, "data": []}
def _all_otp_msgs():
    """كل الأكواد الحالية من كل المصادر (مخزّنة ثانيتين كي لا تُرهق الـ API مع كثرة الجلسات)."""
    now = time.time()
    if now - _OTP_CACHE["ts"] < 2: return _OTP_CACHE["data"]
    data = []
    for msg in zx_fetch_otps():
        mid = str(msg.get("nid") or msg.get("id") or msg.get("created_at") or "")
        raw = str(msg.get("otp") or "")
        m = re.search(r"\b(\d{4,8})\b", raw)
        data.append({"id": mid, "number": str(msg.get("number") or ""), "code": m.group(1) if m else raw, "raw": raw})
    for source in (MINO,):
        try:
            for m in source.fetch_otps():
                raw = m["otp"]
                mm = re.search(r"\b(\d{3}[-\s]?\d{3,4}|\d{4,8})\b", raw)
                code = re.sub(r"\D", "", mm.group(1)) if mm else raw
                data.append({"id": m["id"], "number": m["number"], "code": code, "raw": raw})
        except Exception: pass
    _OTP_CACHE.update(ts=now, data=data)
    return data

def _tail(number): return re.sub(r"\D", "", str(number or ""))[-9:]

def snapshot_seen(number):
    """معرّفات الأكواد الموجودة مسبقاً لهذا الرقم حتى لا تُعرض كأنها جديدة."""
    tail = _tail(number)
    return {m["id"] for m in _all_otp_msgs() if re.sub(r"\D", "", m["number"]).endswith(tail)}

def find_otp_for(number, seen):
    tail = _tail(number)
    for m in _all_otp_msgs():
        if m["id"] in seen: continue
        if not re.sub(r"\D", "", m["number"]).endswith(tail): continue
        return m
    return None

# ══════════════════ Links ══════════════════
def bot_url(): return f"https://t.me/{BOT_USERNAME.lstrip('@')}" if BOT_USERNAME else None
def group_url(): return OTP_GROUP_LINK or None
def channel_url(): return CHANNEL_URL or None

# اسم البوت المعروض في رسائل الرمز (يمكن تغييره بحرّية)
BOT_BRAND = "OTP ABO IBRAHIM"

# ══════════════════ Keyboards ══════════════════
def _kb_btn(text, style=None):
    """KeyboardButton مع style (يعمل في الفورك)، آمن لو المكتبة لا تدعم style."""
    try:
        return KeyboardButton(text, style=style) if style else KeyboardButton(text)
    except TypeError:
        return KeyboardButton(text)

def _norm_btn(x): return str(x or "").replace("\ufe0f", "").strip()
_BTN_LABELS = {k: [_norm_btn(make_bold_unicode(T[l][k])) for l in T]
               for k in ("get_number", "language", "admin_panel", "history", "repeat_last")}
def _is_btn(text, key):
    """مطابقة زر لوحة المفاتيح بنص الزر نفسه (وليس بوجود إيموجي) — تعمل أيضاً مع الأزرار القديمة."""
    t = _norm_btn(text)
    return any(lbl and lbl in t for lbl in _BTN_LABELS[key])

def main_kb(lang, is_admin):
    rows = [[_kb_btn(make_bold_unicode(tr(lang, "get_number")), style="danger")]]
    rows.append([
        _kb_btn(make_bold_unicode(tr(lang, "repeat_last")), style="primary"),
        _kb_btn(make_bold_unicode(tr(lang, "history")), style="primary"),
    ])
    row3 = [_kb_btn(make_bold_unicode(tr(lang, "language")), style="success")]
    if is_admin:
        row3.append(_kb_btn(make_bold_unicode(tr(lang, "admin_panel")), style="success"))
    rows.append(row3)
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def services_kb(lang):
    rows = []
    for sid, s in SERVICE_MAP.items():
        if sid in STATE.get("disabled", []): continue
        rows.append([IBtn(
            make_bold_unicode(f"{s['emoji']} {svc_name(sid, lang)}"),
            callback_data=f"svc:{sid}",
            style="primary"
        )])
    return InlineKeyboardMarkup(rows)

def countries_kb(sid, lang, page=0):
    countries = countries_for_service(sid)
    if not countries: return None
    per_page = 10
    pages = max(1, (len(countries) + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    sl = countries[page*per_page:(page+1)*per_page]
    rows = []
    for idx, c in enumerate(sl):
        iso = c["iso"]
        label = c.get("label") or ""
        country_display_name = (c.get("country") or "").strip()
        if not country_display_name:
            country_display_name = iso_name(iso, lang) or (iso.upper() if iso else "Unknown")
        if label and label not in country_display_name:
            country_display_name = f"{country_display_name} {label}"
        rows.append([IBtn(
            make_bold_unicode(f"{flag(iso)} {country_display_name} ✅ {c['hits']}"),
            callback_data=f"co:{sid}:{c['gkey']}",
            style="primary"
        )])
    nav = []
    if page > 0: nav.append(IBtn("◀️", callback_data=f"cop:{sid}:{page-1}", style="primary"))
    nav.append(IBtn(f"{page+1}/{pages}", callback_data="noop"))
    if page < pages - 1: nav.append(IBtn("▶️", callback_data=f"cop:{sid}:{page+1}", style="primary"))
    if nav: rows.append(nav)
    rows.append([IBtn("🔄", callback_data=f"cop:{sid}:{page}", style="primary"),
                 IBtn(make_bold_unicode(tr(lang, "back")), callback_data="services", style="danger")])
    return InlineKeyboardMarkup(rows)

def number_kb(sid, iso, number, lang):
    rows = [
        [IBtn(make_bold_unicode(tr(lang, "new_number")), callback_data=f"new:{sid}:{iso}", style="success")],
        [IBtn(make_bold_unicode(tr(lang, "change_country")), callback_data=f"svc:{sid}", style="primary"),
         IBtn(make_bold_unicode(tr(lang, "copy")), callback_data=f"cp:{number}", style="primary")],
    ]
    gu = group_url()
    if gu: rows.append([IBtn(make_bold_unicode(tr(lang, "goto_group")), url=gu, style="primary")])
    rows.append([IBtn(make_bold_unicode(tr(lang, "cancel_number")), callback_data=f"cxl:{number}:{sid}:{iso}", style="danger")])
    rows.append([IBtn(make_bold_unicode(tr(lang, "back")), callback_data="services", style="danger")])
    return InlineKeyboardMarkup(rows)

def admin_kb():
    return InlineKeyboardMarkup([
        [IBtn(make_bold_unicode("🟢 تفعيل/إيقاف الخدمات"), callback_data="adm:toggle", style="primary")],
        [IBtn(make_bold_unicode("➕ رينج زينيكس"), callback_data="adm:add_zx", style="success"),
         IBtn(make_bold_unicode("➕ رينج Mino"), callback_data="adm:add_mino", style="success")],
        [IBtn(make_bold_unicode("🗑 حذف رينج زينيكس"), callback_data="adm:del", style="danger"),
         IBtn(make_bold_unicode("🗑 حذف رينج Mino"), callback_data="adm:del_mino", style="danger")],
        [IBtn(make_bold_unicode("📤 رفع كومبو"), callback_data="adm:combo_up", style="success"),
         IBtn(make_bold_unicode("📁 كومبوهاتي"), callback_data="adm:combo_list", style="primary")],
        [IBtn(make_bold_unicode("📋 الرينجات المباشرة"), callback_data="adm:list", style="primary")],
        [IBtn(make_bold_unicode("📣 إعلان للجميع"), callback_data="adm:bc", style="primary"),
         IBtn(make_bold_unicode("👥 مستخدمون"), callback_data="adm:users", style="primary")],
        [IBtn(make_bold_unicode("🚫 حظر / فك مستخدم"), callback_data="adm:ban", style="danger")],
        [IBtn(make_bold_unicode("📊 إحصائيات"), callback_data="adm:stats", style="primary"),
         IBtn(make_bold_unicode("🔐 حالة الدخول"), callback_data="adm:logins", style="primary")],
    ])

def lang_kb():
    return InlineKeyboardMarkup([
        [IBtn(make_bold_unicode("العربية"), callback_data="lang:ar", style="primary")],
        [IBtn(make_bold_unicode("English"), callback_data="lang:en", style="primary")],
        [IBtn(make_bold_unicode("کوردی"), callback_data="lang:ku", style="primary")],
    ])

# ══════════════════ Session helpers ══════════════════
def cancel_task(ctx, chat_id):
    t = ctx.application.bot_data.get(f"task:{chat_id}")
    if t and not t.done(): t.cancel()
    ctx.application.bot_data.pop(f"task:{chat_id}", None)
def set_task(ctx, chat_id, t):
    cancel_task(ctx, chat_id)
    ctx.application.bot_data[f"task:{chat_id}"] = t

WELCOME = ("<b>OTP APP IBRAHIM</b>\n"
           "━━━━━━━━━━━━━━━━━━━━━\n"
           "<b>Premium</b> • <b>Fast</b> • <b>Secure</b>\n"
           "━━━━━━━━━━━━━━━━━━━━━")

# ══════════════════ Commands ══════════════════
async def cmd_start(update, ctx):
    u = note_user(update.effective_user)
    if u.get("banned"): return
    u["started"] = True; save_users()
    lang = u["lang"]; is_admin = update.effective_user.id in ADMIN_IDS
    tgu = update.effective_user
    who = esc(("@" + tgu.username) if tgu.username else (tgu.first_name or "أخي"))
    greet = f"<b>السلام عليكم ورحمة الله وبركاته</b>\nحيّاك الله أخي <b>{who}</b>"
    await update.message.reply_text(f"{WELCOME}\n\n{greet}", parse_mode=ParseMode.HTML, reply_markup=main_kb(lang, is_admin))

async def cmd_admin(update, ctx):
    if update.effective_user.id not in ADMIN_IDS:
        u = get_user(update.effective_user.id)
        await update.message.reply_text(tr(u["lang"], "admin_only")); return
    await update.message.reply_text(make_bold_unicode("🛠 Admin Panel"), parse_mode=ParseMode.HTML, reply_markup=admin_kb())

async def cmd_lang(update, ctx):
    u = get_user(update.effective_user.id)
    await update.message.reply_text(tr(u["lang"], "choose_lang"), reply_markup=lang_kb())

async def cmd_last(update, ctx):
    uid = update.effective_user.id
    is_admin = uid in ADMIN_IDS
    if not LAST_OTP:
        await update.message.reply_text("لا يوجد أي OTP مسجّل بعد."); return
    L = LAST_OTP
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(L.get("ts", 0)))
    if is_admin:
        num = L.get("number") or "—"
        code = L.get("code") or "—"
        user_line = esc(f"@{L['username']}" if L.get("username") else (L.get("name") or "—")) + f" (<code>{L.get('uid')}</code>)"
    else:
        num = mask_number(L.get("number") or "")
        code = mask_code(L.get("code") or "")
        user_line = esc(L.get("name") or (f"@{L['username']}" if L.get("username") else "—"))
    txt = ("📊 <b>آخر OTP</b>\n"
           "━━━━━━━━━━━━━━━━━━━━━\n"
           f"👤 <b>المستخدم:</b> {user_line}\n"
           f"📱 <b>الخدمة:</b> {L.get('service') or '—'}\n"
           f"🌍 <b>الدولة:</b> {flag(L.get('iso') or '')} {L.get('country') or '—'}\n"
           f"☎️ <b>الرقم:</b> <code>{num}</code>\n"
           f"🔑 <b>الكود:</b> <code>{code}</code>\n"
           f"⏰ {ts}")
    await update.message.reply_text(txt, parse_mode=ParseMode.HTML)

async def cmd_pm(update, ctx):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ للأدمن فقط."); return
    args = ctx.args or []
    if len(args) < 2:
        await update.message.reply_text("الاستخدام:\n<code>/pm &lt;user_id&gt; نص الرسالة</code>", parse_mode=ParseMode.HTML); return
    tid_raw = args[0]
    text = " ".join(args[1:]).strip()
    tid = re.sub(r"\D", "", tid_raw)
    if not tid or not text:
        await update.message.reply_text("⚠️ ID غير صحيح أو الرسالة فارغة."); return
    try:
        await ctx.bot.send_message(int(tid), f"📩 <b>رسالة من الإدارة:</b>\n━━━━━━━━━━━━━━━━━━━━━\n{text}", parse_mode=ParseMode.HTML)
        await update.message.reply_text(f"✅ أُرسلت إلى <code>{tid}</code>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ فشل الإرسال: {e}")

async def on_sticker(update, ctx):
    """للأدمن فقط: أرسل ستيكراً للبوت ليعطيك الـ file_id."""
    if update.effective_user.id not in ADMIN_IDS: return
    st = update.message.sticker
    if not st: return
    await update.message.reply_text(
        f"<b>File ID:</b>\n<code>{st.file_id}</code>\n\n"
        f"<b>Unique ID:</b>\n<code>{st.file_unique_id}</code>\n\n"
        f"<b>Emoji:</b> {esc(st.emoji or '—')}\n"
        f"<b>Set:</b> {esc(st.set_name or '—')}",
        parse_mode=ParseMode.HTML)

async def on_text(update, ctx):

    t = (update.message.text or "").strip()
    uid = update.effective_user.id
    u = note_user(update.effective_user); lang = u["lang"]
    if u.get("banned"): return
    is_admin = uid in ADMIN_IDS
    # Force /start before interacting
    if not u.get("started") and t != "/start":
        await update.message.reply_text("👋 يرجى الضغط على /start للبدء أولاً.")
        return

    if is_admin and ctx.user_data.get("await_ban"):
        ctx.user_data.pop("await_ban")
        tid = re.sub(r"\D", "", t)
        if not tid:
            await update.message.reply_text("⚠️ أرسل ID رقمي صحيح."); return
        tu = get_user(int(tid)); tu["banned"] = not tu.get("banned"); save_users()
        state = "⛔ تم الحظر" if tu["banned"] else "✅ تم فك الحظر"
        await update.message.reply_text(f"{state} للمستخدم <code>{tid}</code>", parse_mode=ParseMode.HTML); return

    if is_admin and ctx.user_data.get("await_mino_range_for"):
        sid = ctx.user_data.pop("await_mino_range_for")
        parts = [x.strip() for x in t.split("|")]
        if len(parts) < 2:
            await update.message.reply_text(
                "❌ الصيغة: <code>rid|country[|label]</code>\nمثال:\n<code>12345|غينيا|1</code>\n<code>12345|Guinea|2</code>\n<code>12345|249</code>",
                parse_mode=ParseMode.HTML); return
        rid = parts[0]
        country_hint = parts[1]
        label = parts[2] if len(parts) >= 3 else ""
        iso = find_iso_by_name(country_hint) or (country_hint.lower() if len(country_hint) == 2 else "")
        if not iso:
            await update.message.reply_text(f"⚠️ لم أتعرف على الدولة: <b>{country_hint}</b>", parse_mode=ParseMode.HTML); return
        country_full = iso_name(iso, "ar") or iso.upper()
        if label: country_full = f"{country_full} {label}"
        entry = {"rid": rid, "sid": sid, "iso": iso, "country": country_full, "hits": 1}
        if label: entry["gid"] = label
        STATE.setdefault("mino_ranges", []).append(entry)
        save_state()
        await update.message.reply_text(
            make_bold_unicode(f"✅ أُضيف رينج Mino\n📱 {svc_name(sid,'ar')}\n🌍 {flag(iso)} {country_full}\n🆔 rid={rid}"),
            parse_mode=ParseMode.HTML); return
    if is_admin and ctx.user_data.get("await_range_for"):
        sid = ctx.user_data.pop("await_range_for")
        parts = [x.strip() for x in t.split("|")]
        if len(parts) < 2:
            await update.message.reply_text(
                "❌ الصيغة: <code>code|country[|label]</code>\nمثال:\n<code>+9627|الأردن</code>\n<code>+224|غينيا|1</code>\n<code>+224|Guinea|2</code>",
                parse_mode=ParseMode.HTML); return
        code = parts[0]
        country_hint = parts[1]
        label = parts[2] if len(parts) >= 3 else ""
        iso = find_iso_by_name(country_hint) or guess_iso(code)
        if not iso:
            await update.message.reply_text(f"⚠️ لم أتعرف على الدولة: <b>{country_hint}</b>", parse_mode=ParseMode.HTML); return
        country_full = iso_name(iso, "ar") or iso.upper()
        if label: country_full = f"{country_full} {label}"
        entry = {"range": code, "country": country_full, "iso": iso, "hits": 0}
        if label: entry["gid"] = label
        STATE["custom"].setdefault(sid, []).append(entry)
        save_state()
        await update.message.reply_text(
            make_bold_unicode(f"✅ أُضيف رينج زينيكس\n📱 {svc_name(sid,'ar')}\n🌍 {flag(iso)} {country_full}\n🔢 {code}"),
            parse_mode=ParseMode.HTML); return
    if is_admin and ctx.user_data.get("await_bc"):
        ctx.user_data.pop("await_bc"); sent = 0
        for k in list(USERS.keys()):
            if USERS[k].get("banned"): continue
            try: await ctx.bot.send_message(int(k), f"📣 {t}"); sent += 1
            except Exception: pass
            await asyncio.sleep(0.05)
        await update.message.reply_text(f"✅ {sent}"); return

    if _is_btn(t, "get_number"):
        await update.message.reply_text(tr(lang,"pick_service"), reply_markup=services_kb(lang)); return
    if _is_btn(t, "language"):
        await update.message.reply_text(tr(lang,"choose_lang"), reply_markup=lang_kb()); return
    if _is_btn(t, "admin_panel") and is_admin:
        await update.message.reply_text(make_bold_unicode("🛠 Admin Panel"), parse_mode=ParseMode.HTML, reply_markup=admin_kb()); return
    if _is_btn(t, "history"):
        hist = (u.get("history") or [])[-10:][::-1]
        if not hist:
            await update.message.reply_text(tr(lang, "no_history")); return
        lines = [f"<b>{make_bold_unicode(tr(lang,'my_history'))}</b>\n━━━━━━━━━━━━━━━━━━━━━"]
        for h in hist:
            ts = time.strftime("%m-%d %H:%M", time.localtime(h.get("ts", 0)))
            lines.append(f"⏰ {ts} | {flag(h.get('iso',''))} <b>{h.get('service','—')}</b>\n"
                         f"☎️ <code>{h.get('number','—')}</code>  🔑 <code>{h.get('otp','—')}</code>")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML); return
    if _is_btn(t, "repeat_last"):
        hist = u.get("history") or []
        if not hist:
            await update.message.reply_text(tr(lang, "no_history")); return
        last = hist[-1]
        sid_last = None
        for k, v in SERVICE_MAP.items():
            if v["name"].get(lang) == last.get("service") or v["name"].get("en") == last.get("service") or v["name"].get("ar") == last.get("service"):
                sid_last = k; break
        iso_last = (last.get("iso") or "").lower()
        if not sid_last or not iso_last:
            await update.message.reply_text(tr(lang, "no_history")); return
        cancel_task(ctx, update.effective_chat.id)
        task = asyncio.create_task(run_session(ctx, update.effective_chat.id, uid, sid_last, iso_last))
        set_task(ctx, update.effective_chat.id, task); return

async def on_document(update, ctx):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS: return
    sid = ctx.user_data.get("combo_sid")
    if not sid:
        await update.message.reply_text("⚠️ اختر أولاً الخدمة من: 🛠 Admin → 📤 رفع كومبو"); return
    doc = update.message.document
    if not doc: return
    fname = (doc.file_name or "combo.txt")
    base = os.path.splitext(os.path.basename(fname))[0]
    file = await doc.get_file()
    raw = bytes(await file.download_as_bytearray()).decode("utf-8", errors="ignore")
    numbers = []
    for line in raw.splitlines():
        n = re.sub(r"[^\d+]", "", line)
        if len(re.sub(r"\D", "", n)) >= 6: numbers.append(n)
    if not numbers:
        await update.message.reply_text("⚠️ الملف لا يحتوي أرقاماً."); return
    iso = guess_iso(numbers[0])
    COMBOS.setdefault(sid, {})[base] = {"numbers": numbers, "used": [], "iso": iso}
    save_combos()
    ctx.user_data.pop("combo_sid", None)
    await update.message.reply_text(
        f"✅ رُفع الكومبو <b>{esc(base)}</b> ({len(numbers)} رقم) للخدمة <b>{svc_name(sid,'ar')}</b>.\n"
        f"سيظهر كقائمة داخل هذه الخدمة.",
        parse_mode=ParseMode.HTML)

async def send_number(ctx, chat_id, uid, sid, gkey, edit_mid=None):
    u = get_user(uid); lang = u["lang"]
    svc = SERVICE_MAP.get(sid, {"emoji":"📱"})
    rg = await asyncio.to_thread(best_range, sid, gkey)
    if not rg:
        text = tr(lang, "no_range")
        if edit_mid:
            try: await ctx.bot.edit_message_text(text, chat_id=chat_id, message_id=edit_mid)
            except Exception: await ctx.bot.send_message(chat_id, text)
        else: await ctx.bot.send_message(chat_id, text)
        return None
    iso = rg.get("iso") or gkey.split("#",1)[0]
    country_label = rg.get("country") or iso_name(iso, lang) or iso.upper()
    if edit_mid:
        try:
            await ctx.bot.edit_message_text(
                f"{tr(lang,'reserving')}\n{svc['emoji']} <b>{svc_name(sid,lang)}</b> — {flag(iso)} {esc(country_label)}",
                chat_id=chat_id, message_id=edit_mid, parse_mode=ParseMode.HTML)
        except Exception: pass
    res = await asyncio.to_thread(reserve_number, rg["range"])
    if not res:
        text = tr(lang, "no_range")
        if edit_mid:
            try: await ctx.bot.edit_message_text(text, chat_id=chat_id, message_id=edit_mid)
            except Exception: pass
        else: await ctx.bot.send_message(chat_id, text)
        return None
    country = country_label
    op = res.get("operator") or "—"
    u["stats"]["numbers"] += 1; save_users()
    header = f"{flag(iso)} <b>{esc(make_bold_unicode(country))} Number Assigned:</b>"
    box = (f"┌──────────────────────┐\n"
           f"│   ⏳ {make_bold_unicode(tr(lang,'waiting_code'))}   │\n"
           f"└──────────────────────┘")
    body = (f"{header}\n{box}\n"
            f"\n{svc['emoji']} <b>{make_bold_unicode(svc_name(sid,lang))}</b> — {tr(lang,'operator')}: <code>{esc(make_bold_unicode(op))}</code>\n"
            f"☎️ <code>+{re.sub(r'[^0-9]','',str(res['number']))}</code>\n"
            f"<i>{tr(lang,'copy_hint')}</i>")
    kb = number_kb(sid, gkey, res["number"], lang)
    if edit_mid:
        try:
            await ctx.bot.edit_message_text(body, chat_id=chat_id, message_id=edit_mid, parse_mode=ParseMode.HTML, reply_markup=kb); mid = edit_mid
        except Exception:
            m = await ctx.bot.send_message(chat_id, body, parse_mode=ParseMode.HTML, reply_markup=kb); mid = m.message_id
    else:
        m = await ctx.bot.send_message(chat_id, body, parse_mode=ParseMode.HTML, reply_markup=kb); mid = m.message_id
    register_reservation(res["number"], uid, sid, iso, svc_name(sid,lang), country)
    return {"number": res["number"], "range": rg["range"], "msg_id": mid, "combo": res.get("combo"), "svc_name": svc_name(sid,lang), "country": country, "iso": iso, "sid": sid}

async def run_session(ctx, chat_id, uid, sid, gkey, init_mid=None):
    u = get_user(uid); lang = u["lang"]
    current = await send_number(ctx, chat_id, uid, sid, gkey, edit_mid=init_mid)
    if not current: return
    iso = current["iso"]
    svc_emoji = SERVICE_MAP.get(current.get("sid") or sid, {}).get("emoji", "📱")
    try:
        seen = await asyncio.to_thread(snapshot_seen, current["number"])
    except Exception:
        seen = set()
    end = time.time() + POLL_TIMEOUT
    try:
        while time.time() < end:
            await asyncio.sleep(POLL_INTERVAL)
            hit = await asyncio.to_thread(find_otp_for, current["number"], seen)
            if hit:
                seen.add(hit["id"])
                u["stats"]["otps"] += 1
                u["history"].append({"ts": int(time.time()), "service": current["svc_name"], "number": current["number"], "iso": iso, "otp": hit["code"]})
                u["history"] = u["history"][-100:]; save_users()
                if current.get("combo"):
                    consume_combo(current["combo"][0], current["combo"][1], current["number"])
                await asyncio.to_thread(cancel_number, current["number"])
                unregister_reservation(current["number"])
                set_last_otp(uid, current["number"], hit["code"], current["svc_name"], current["country"], iso)
                dm_kb_rows = [[
                    IBtn(make_bold_unicode(tr(lang, "copy_code")), callback_data=f"cpc:{hit['code']}", style="success"),
                    IBtn(make_bold_unicode(tr(lang, "repeat_last")), callback_data=f"new:{current.get('sid') or sid}:{gkey}", style="primary"),
                ]]
                gu = group_url()
                cu = channel_url()
                if gu: dm_kb_rows.append([IBtn(make_bold_unicode(tr(lang, "goto_group")), url=gu, style="primary")])
                if cu: dm_kb_rows.append([IBtn(make_bold_unicode(tr(lang, "goto_channel")), url=cu, style="success")])
                dm_kb = InlineKeyboardMarkup(dm_kb_rows)
                iso_up = (iso or "").upper()
                pretty_num = "+" + re.sub(r'[^0-9]','', str(current['number']))
                brand_line = f"<b>{make_bold_unicode(BOT_BRAND)}</b>"
                try:
                    await ctx.bot.send_message(chat_id,
                        f"{brand_line}\n"
                        f"<b>{make_bold_unicode(tr(lang,'otp_arrived'))}</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        f"{flag(iso)} <b>{make_bold_unicode(iso_up)}</b> | 📱 SMS <code>{pretty_num}</code> | {svc_emoji} <b>{make_bold_unicode(current['svc_name'])}</b>\n"
                        f"🌍 <b>{esc(make_bold_unicode(current['country']))}</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🔑 <b>{make_bold_unicode(tr(lang,'code_word'))}:</b>\n"
                        f"<code>{hit['code']}</code>\n"
                        f"<i>{tr(lang,'copy_hint')}</i>",
                        parse_mode=ParseMode.HTML, reply_markup=dm_kb)
                except Exception as e: log.warning("dm otp send failed: %s", e)
                if OTP_GROUP_ID:
                    try:
                        shown_code = mask_code(hit["code"]) if MASK_GROUP_CODE else hit["code"]
                        gkb_rows = [[IBtn(make_bold_unicode(tr(lang, "copy_code")), callback_data=f"cpc:{hit['code']}", style="success")]]
                        bu = bot_url()
                        if bu: gkb_rows.append([IBtn(make_bold_unicode(tr(lang, "open_bot")), url=bu, style="primary")])
                        if cu: gkb_rows.append([IBtn(make_bold_unicode(tr(lang, "goto_channel")), url=cu, style="success")])
                        gkb = InlineKeyboardMarkup(gkb_rows)
                        who = u.get("username")
                        who_disp = f"@{who}" if who else (u.get('name') or ('ID '+str(uid)))
                        who_line = f"<b>{make_bold_unicode(tr(lang,'pulled_by'))}:</b> {esc(make_bold_unicode(who_disp))}"
                        code_line = f"🔑 <b>{make_bold_unicode(tr(lang,'code_word'))}:</b>\n<code>{shown_code}</code>"
                        await ctx.bot.send_message(
                            OTP_GROUP_ID,
                            f"{brand_line}\n"
                            f"<b>{make_bold_unicode(tr(lang,'otp_arrived'))}</b>\n"
                            "━━━━━━━━━━━━━━━━━━━━━\n"
                            f"📱 <b>{make_bold_unicode(current['svc_name'])}</b>\n"
                            f"🌍 {flag(iso)} <b>{esc(make_bold_unicode(current['country']))}</b>\n"
                            f"☎️ <code>{mask_number(current['number'])}</code>\n"
                            "━━━━━━━━━━━━━━━━━━━━━\n"
                            f"{code_line}\n"
                            f"{who_line}",
                            parse_mode=ParseMode.HTML, reply_markup=gkb)
                    except Exception as e: log.warning("group send failed: %s", e)
                # ميزة: انتظر كوداً ثانياً لمدة 60 ثانية (2FA)
                try:
                    await ctx.bot.send_message(chat_id, f"<i>{tr(lang,'waiting_second')}</i>", parse_mode=ParseMode.HTML)
                except Exception: pass
                second_end = time.time() + 60
                while time.time() < second_end:
                    await asyncio.sleep(POLL_INTERVAL)
                    hit2 = await asyncio.to_thread(find_otp_for, current["number"], seen)
                    if hit2:
                        seen.add(hit2["id"])
                        try:
                            kb2 = InlineKeyboardMarkup([[IBtn(make_bold_unicode(tr(lang,"copy_code")), callback_data=f"cpc:{hit2['code']}", style="success")]])
                            await ctx.bot.send_message(chat_id,
                                f"<b>{make_bold_unicode(tr(lang,'second_code'))}</b>\n"
                                "━━━━━━━━━━━━━━━━━━━━━\n"
                                f"🔑 <code>{hit2['code']}</code>",
                                parse_mode=ParseMode.HTML, reply_markup=kb2)
                        except Exception: pass
                        break
                return
    except asyncio.CancelledError:
        unregister_reservation(current["number"]); return
    except Exception:
        log.exception("run_session crashed")
        unregister_reservation(current["number"]); return
    try:
        await asyncio.to_thread(cancel_number, current["number"])
        unregister_reservation(current["number"])
        await ctx.bot.send_message(chat_id, f"{tr(lang,'timeout')}: <code>{current['number']}</code>", parse_mode=ParseMode.HTML)
    except Exception: pass

def toggle_kb(lang):
    rows = []
    for sid, sv in SERVICE_MAP.items():
        mark = "✅" if sid not in STATE.get("disabled", []) else "🚫"
        rows.append([IBtn(f"{mark} {sv['emoji']} {svc_name(sid,lang)}", callback_data=f"tgl:{sid}", style="primary")])
    rows.append([IBtn("⬅️", callback_data="adm:panel", style="danger")])
    return InlineKeyboardMarkup(rows)

def _h(name): return hashlib.md5(str(name).encode("utf-8")).hexdigest()[:10]

async def on_callback(update, ctx):
    q = update.callback_query
    data = q.data or ""
    uid = q.from_user.id
    chat_id = q.message.chat_id
    u = note_user(q.from_user); lang = u["lang"]
    if u.get("banned"): await q.answer(tr(lang,"banned"), show_alert=True); return
    if not u.get("started"):
        await q.answer("اضغط /start أولاً", show_alert=True)
        try: await ctx.bot.send_message(chat_id, "👋 يرجى الضغط على /start للبدء أولاً.")
        except Exception: pass
        return
    await q.answer()

    if data == "noop": return
    if data == "sub:check":   # زر قديم من النسخة السابقة (الاشتراك الإجباري أُلغي)
        try: await q.edit_message_text(tr(lang,"pick_service"), reply_markup=services_kb(lang))
        except Exception: pass
        return

    if data == "services":
        cancel_task(ctx, chat_id)
        await q.edit_message_text(tr(lang,"pick_service"), reply_markup=services_kb(lang)); return

    if data.startswith("lang:"):
        u["lang"] = data.split(":",1)[1]; save_users()
        try: await q.edit_message_text(tr(u["lang"], "lang_set"))
        except Exception: pass
        try: await ctx.bot.send_message(chat_id, "✅", reply_markup=main_kb(u["lang"], uid in ADMIN_IDS))
        except Exception: pass
        return

    if data.startswith("svc:"):
        sid = data.split(":",1)[1]; cancel_task(ctx, chat_id)
        kb = await asyncio.to_thread(countries_kb, sid, lang, 0)
        if not kb:
            await q.edit_message_text(tr(lang,"no_country"),
                reply_markup=InlineKeyboardMarkup([[IBtn(tr(lang,"back"), callback_data="services", style="danger")]]))
            return
        s = SERVICE_MAP.get(sid, {})
        await q.edit_message_text(f"{s.get('emoji','')} <b>{svc_name(sid,lang)}</b>\n{tr(lang,'pick_country')}", parse_mode=ParseMode.HTML, reply_markup=kb); return

    if data.startswith("cop:"):
        _, sid, page = data.split(":",2)
        try: await q.edit_message_reply_markup(reply_markup=await asyncio.to_thread(countries_kb, sid, lang, int(page)))
        except Exception: pass
        return

    if data.startswith("co:") or data.startswith("new:"):
        _, sid, gkey = data.split(":",2)
        cancel_task(ctx, chat_id)
        task = asyncio.create_task(run_session(ctx, chat_id, uid, sid, gkey, init_mid=q.message.message_id))
        set_task(ctx, chat_id, task); return

    if data.startswith("cp:"):
        num = data.split(":",1)[1]
        await ctx.bot.send_message(chat_id, f"<code>{num}</code>", parse_mode=ParseMode.HTML); return

    if data.startswith("cpc:"):
        code_val = data.split(":",1)[1]
        try: await q.answer(f"📋 {code_val}", show_alert=False)
        except Exception: pass
        await ctx.bot.send_message(chat_id, f"<code>{code_val}</code>", parse_mode=ParseMode.HTML); return

    if data.startswith("cxl:"):
        num = data.split(":")[1]
        cancel_task(ctx, chat_id); await asyncio.to_thread(cancel_number, num); u["stats"]["cancels"] += 1; save_users()
        try: await q.edit_message_text(f"❌ <code>{num}</code>", parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[IBtn(tr(lang,"back"), callback_data="services", style="danger")]]))
        except Exception: pass
        return

    if data.startswith("adm:") and uid in ADMIN_IDS:
        sub = data.split(":",1)[1]
        if sub == "panel":
            await q.edit_message_text(make_bold_unicode("🛠 Admin"), parse_mode=ParseMode.HTML, reply_markup=admin_kb()); return
        if sub == "toggle":
            await q.edit_message_text("Services", reply_markup=toggle_kb(lang)); return
        if sub == "add_zx":
            rows = [[IBtn(make_bold_unicode(f"{sv['emoji']} {svc_name(sid_,lang)}"), callback_data=f"addsvc:{sid_}", style="primary")] for sid_, sv in SERVICE_MAP.items()]
            rows.append([IBtn(make_bold_unicode("⬅️"), callback_data="adm:panel", style="danger")])
            await q.edit_message_text(make_bold_unicode("➕ إضافة رينج زينيكس — اختر خدمة:"), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(rows)); return
        if sub == "add_mino":
            rows = [[IBtn(make_bold_unicode(f"{sv['emoji']} {svc_name(sid_,lang)}"), callback_data=f"addminosvc:{sid_}", style="success")] for sid_, sv in SERVICE_MAP.items()]
            rows.append([IBtn(make_bold_unicode("⬅️"), callback_data="adm:panel", style="danger")])
            await q.edit_message_text(make_bold_unicode("➕ إضافة رينج Mino — اختر خدمة:"), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(rows)); return
        if sub == "del_mino":
            rows = []
            for r in STATE.get("mino_ranges", []):
                rid = r.get("rid",""); sid_ = r.get("sid",""); iso = r.get("iso","")
                rows.append([IBtn(f"🗑 Mino {sid_} {flag(iso.upper())} rid={rid}", callback_data=f"delmino:{rid}", style="danger")])
            rows.append([IBtn("⬅️", callback_data="adm:panel", style="danger")])
            await q.edit_message_text(make_bold_unicode("🗑 حذف رينج Mino:"), parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(rows)); return
        if sub == "del":
            rows = []
            for sid, arr in STATE.get("custom", {}).items():
                for r in arr:
                    rows.append([IBtn(f"🗑 {sid} {r['range']} ({r.get('country','')})", callback_data=f"delrng:{sid}:{r['range']}", style="danger")])
            rows.append([IBtn("⬅️", callback_data="adm:panel", style="danger")])
            await q.edit_message_text("حذف رينج:", reply_markup=InlineKeyboardMarkup(rows)); return
        if sub == "combo_up":
            rows = [[IBtn(f"{s['emoji']} {svc_name(sid,lang)}", callback_data=f"cbsvc:{sid}", style="success")] for sid, s in SERVICE_MAP.items()]
            rows.append([IBtn("⬅️", callback_data="adm:panel", style="danger")])
            await q.edit_message_text("📤 اختر الخدمة لرفع الكومبو:", reply_markup=InlineKeyboardMarkup(rows)); return
        if sub == "combo_list":
            rows = []
            for sid, dct in COMBOS.items():
                for name, c in dct.items():
                    rows.append([IBtn(f"📁 {sid}/{name} — {len(c['numbers'])} (used {len(c.get('used',[]))})", callback_data=f"cbdel:{sid}:{_h(name)}", style="primary")])
            rows.append([IBtn("⬅️", callback_data="adm:panel", style="danger")])
            await q.edit_message_text("Combos (اضغط للحذف):", reply_markup=InlineKeyboardMarkup(rows)); return
        if sub == "list":
            base = await asyncio.to_thread(all_ranges)
            lines = [f"📋 {len(base)}:"]
            for r in base[:60]:
                lines.append(f"• {r.get('service')} — <code>{r.get('range')}</code> {flag((r.get('iso') or '').lower())} {r.get('hits',0)}")
            await q.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[IBtn("⬅️", callback_data="adm:panel", style="danger")]])); return
        if sub == "bc":
            ctx.user_data["await_bc"] = True
            await q.edit_message_text("📣 أرسل نص الإعلان."); return
        if sub == "ban":
            ctx.user_data["await_ban"] = True
            await q.edit_message_text("🚫 أرسل <b>ID</b> المستخدم لحظره أو فك حظره.\n(الايدي يظهر بجانب اسم المستخدم في قائمة 👥 مستخدمون)", parse_mode=ParseMode.HTML); return
        if sub == "users":
            lines = [f"👥 <b>المستخدمون:</b> {len(USERS)}", "━━━━━━━━━━━━━━━━━━━━━"]
            items = sorted(USERS.items(), key=lambda kv: -(kv[1].get("stats", {}).get("numbers", 0)))
            for k, x in items[:40]:
                st = x.get("stats", {})
                name = esc(x.get("name") or "—")
                un = esc(f"@{x['username']}") if x.get("username") else ""
                ban = "⛔ " if x.get("banned") else ""
                lines.append(f"{ban}<b>{name}</b> {un}\n   🆔 <code>{k}</code> — 📞 {st.get('numbers',0)} • 🔑 {st.get('otps',0)} • ❌ {st.get('cancels',0)}")
            txt = "\n".join(lines)
            if len(txt) > 3900: txt = txt[:3900] + "\n…"
            await q.edit_message_text(txt, parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[IBtn("⬅️", callback_data="adm:panel", style="danger")]])); return
        if sub == "stats":
            n = sum(x.get("stats", {}).get("numbers", 0) for x in USERS.values())
            o = sum(x.get("stats", {}).get("otps", 0) for x in USERS.values())
            c = sum(x.get("stats", {}).get("cancels", 0) for x in USERS.values())
            banned = sum(1 for x in USERS.values() if x.get("banned"))
            await q.edit_message_text(
                "📊 <b>إحصائيات عامة</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"👥 المستخدمون: <b>{len(USERS)}</b>\n"
                f"⛔ المحظورون: <b>{banned}</b>\n"
                f"📞 الأرقام المحجوزة: <b>{n}</b>\n"
                f"🔑 الأكواد الواصلة: <b>{o}</b>\n"
                f"❌ الإلغاءات: <b>{c}</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[IBtn("⬅️", callback_data="adm:panel", style="danger")]])); return
        if sub == "logins":
            await q.edit_message_text("🔐 جاري فحص تسجيل الدخول...")
            report = await asyncio.to_thread(logins_report)
            await q.edit_message_text(report, parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [IBtn("🔄 إعادة الفحص", callback_data="adm:logins", style="primary")],
                    [IBtn("⬅️", callback_data="adm:panel", style="danger")]])); return

    if data.startswith("tgl:") and uid in ADMIN_IDS:
        sid = data.split(":",1)[1]
        dis = STATE.setdefault("disabled", [])
        (dis.remove(sid) if sid in dis else dis.append(sid))
        save_state()
        try: await q.edit_message_text("Services", reply_markup=toggle_kb(lang))
        except Exception: pass
        return
    if data.startswith("addsvc:") and uid in ADMIN_IDS:
        sid = data.split(":",1)[1]
        ctx.user_data["await_range_for"] = sid
        await q.edit_message_text(
            f"➕ رينج زينيكس — {svc_name(sid,'ar')}\n\nأرسل: <code>code|country</code>\nمثال: <code>+9627|الأردن</code> أو <code>+20|Egypt</code>",
            parse_mode=ParseMode.HTML); return
    if data.startswith("delrng:") and uid in ADMIN_IDS:
        _, sid, code = data.split(":",2)
        STATE["custom"][sid] = [r for r in STATE.get("custom",{}).get(sid,[]) if r["range"] != code]
        save_state(); await q.edit_message_text(f"✅ حُذف {code}",
            reply_markup=InlineKeyboardMarkup([[IBtn("⬅️", callback_data="adm:panel", style="danger")]])); return
    if data.startswith("addminosvc:") and uid in ADMIN_IDS:
        sid = data.split(":",1)[1]
        ctx.user_data["await_mino_range_for"] = sid
        await q.edit_message_text(
            f"➕ رينج Mino — {svc_name(sid,'ar')}\n\nأرسل: <code>rid|country</code>\nمثال: <code>12345|السودان</code> أو <code>12345|Egypt</code> أو <code>12345|249</code>",
            parse_mode=ParseMode.HTML); return
    if data.startswith("delmino:") and uid in ADMIN_IDS:
        rid = data.split(":",1)[1]
        STATE["mino_ranges"] = [r for r in STATE.get("mino_ranges", []) if str(r.get("rid")) != rid]
        save_state()
        await q.edit_message_text(f"✅ حُذف rid={rid}",
            reply_markup=InlineKeyboardMarkup([[IBtn("⬅️", callback_data="adm:panel", style="danger")]])); return

    if data.startswith("cbsvc:") and uid in ADMIN_IDS:
        sid = data.split(":",1)[1]
        ctx.user_data["combo_sid"] = sid
        await q.edit_message_text(
            f"📤 <b>{svc_name(sid,'ar')}</b>\nأرسل الآن ملف <code>.txt</code> يحتوي رقم في كل سطر.\n"
            f"سيتم استخدامه كمصدر للأرقام لهذه الخدمة (لا سحب من الموقع).",
            parse_mode=ParseMode.HTML); return
    if data.startswith("cbdel:") and uid in ADMIN_IDS:
        _, sid, hname = data.split(":",2)
        name = next((n for n in COMBOS.get(sid, {}) if _h(n) == hname), None)
        if name: COMBOS[sid].pop(name, None); save_combos()
        await q.edit_message_text(f"🗑 تم حذف {sid}/{esc(name or '—')}",
            reply_markup=InlineKeyboardMarkup([[IBtn("⬅️", callback_data="adm:panel", style="danger")]])); return

# ══════════════════ Main ══════════════════
async def on_startup(app):
    global BOT_USERNAME, OTP_GROUP_LINK
    try:
        me = await app.bot.get_me()
        BOT_USERNAME = me.username or ""
        log.info("Bot username: @%s", BOT_USERNAME)
    except Exception as e:
        log.warning("get_me failed: %s", e)
    if not OTP_GROUP_LINK and OTP_GROUP_ID:
        try:
            OTP_GROUP_LINK = await app.bot.export_chat_invite_link(OTP_GROUP_ID)
            log.info("OTP group invite link ready")
        except Exception as e:
            log.warning("export group link failed (البوت يجب أن يكون أدمن بالجروب): %s", e)
    try:
        report = await asyncio.to_thread(logins_report)
        info = (f"{report}\n🤖 <b>Bot</b>: @{BOT_USERNAME or '—'}\n"
                f"🔔 <b>Group link</b>: {OTP_GROUP_LINK or '⚪ غير متاح'}")
        for aid in ADMIN_IDS:
            try: await app.bot.send_message(aid, info, parse_mode=ParseMode.HTML)
            except Exception: pass
    except Exception as e:
        log.warning("startup report failed: %s", e)

# ═══════════════════════════════════════════════════════════════
# خادم ويب صغير للحفاظ على البوت نشطاً (اختياري)
# ═══════════════════════════════════════════════════════════════
def start_keepalive_server():
    if Flask is None:
        log.warning("flask غير مثبت — خادم keep-alive متوقف (pip install flask)")
        return
    web_app = Flask(__name__)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    @web_app.route("/")
    def home(): return "Bot is Running!"

    def run_web():
        port = int(os.environ.get("PORT", 8080))
        web_app.run(host="0.0.0.0", port=port)

    threading.Thread(target=run_web, daemon=True).start()

def main():
    start_keepalive_server()
    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("lang", cmd_lang))
    app.add_handler(CommandHandler("last", cmd_last))
    app.add_handler(CommandHandler("pm",   cmd_pm))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.Sticker.ALL, on_sticker))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("OTP APP IBRAHIM started.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
