"""
بوت تلجرام لاستخراج الصور من ملفات PDF
- أزرار ملونة (primary = أزرق / success = أخضر / danger = أحمر)
- عرض قنوات الأدمن للمستخدم عند /start
- لوحة تحكم للأدمن: إدارة القنوات + إحصائيات + المستخدمين + سجل الملفات

التثبيت:
    pip install -r requirements.txt

التشغيل:
    export BOT_TOKEN="123456:ABC..."
    export ADMIN_IDS="111111111,222222222"     # آيديات الأدمن (تعرف آيديك من /id)
    python pdf_images_bot.py
"""

import asyncio
import html
import logging
import math
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import zipfile
from pathlib import Path

try:
    import pymupdf as fitz  # الاسم الجديد
except ImportError:  # نسخ قديمة
    import fitz

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaDocument,
    InputMediaPhoto,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ───────────────────────── الإعدادات ─────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8495428783:AAGCVxJ-DL_9PpmN3DJGZWlXtQHvpPuruxo")
ADMIN_IDS = {8952384711
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()
}
DB_PATH = os.getenv("DB_PATH", "bot_data.db")

MAX_PDF_MB = 20      # حد تلجرام لتحميل الملفات للبوتات
MAX_IMAGES = 100     # أقصى عدد صور يستخرجها البوت لكل ملف
MIN_SIZE = 50        # تجاهل الصور الأصغر من هذا (بالبكسل) مثل الأيقونات
ZIP_LIMIT_MB = 49    # حد رفع تلجرام 50MB
MAX_CHANNELS = 30    # أقصى عدد قنوات
PAGE_SIZE = 8        # عدد العناصر في كل صفحة بلوحة الأدمن

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO
)
logger = logging.getLogger("pdf-images-bot")


# ───────────────────────── قاعدة البيانات (SQLite) ─────────────────────────
_db: sqlite3.Connection | None = None
_lock = threading.Lock()


def init_db() -> None:
    global _db
    _db = sqlite3.connect(DB_PATH, check_same_thread=False)
    _db.row_factory = sqlite3.Row
    with _lock:
        _db.executescript(
            """
            CREATE TABLE IF NOT EXISTS channels (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                title    TEXT NOT NULL,
                url      TEXT NOT NULL UNIQUE,
                added_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                first_name TEXT,
                username   TEXT,
                joined_at  TEXT DEFAULT (datetime('now','localtime')),
                last_seen  TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS extractions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                file_name  TEXT,
                images     INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_ext_user ON extractions(user_id);
            """
        )
        _db.commit()


def db_run(sql: str, params: tuple = ()) -> None:
    with _lock:
        _db.execute(sql, params)
        _db.commit()


def db_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        return _db.execute(sql, params).fetchall()


def db_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    with _lock:
        return _db.execute(sql, params).fetchone()


def upsert_user(user) -> None:
    db_run(
        """
        INSERT INTO users (user_id, first_name, username) VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            first_name = excluded.first_name,
            username   = excluded.username,
            last_seen  = datetime('now','localtime')
        """,
        (user.id, user.first_name, user.username),
    )


def record_extraction(user_id: int, file_name: str, images: int) -> None:
    db_run(
        "INSERT INTO extractions (user_id, file_name, images) VALUES (?, ?, ?)",
        (user_id, file_name, images),
    )
    db_run(
        "UPDATE users SET last_seen = datetime('now','localtime') WHERE user_id = ?",
        (user_id,),
    )


def get_channels() -> list[sqlite3.Row]:
    return db_all("SELECT id, title, url FROM channels ORDER BY id")


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ───────────────────────── الأزرار الملونة ─────────────────────────
def btn(text: str, data: str, style: str | None = None) -> InlineKeyboardButton:
    """style: 'primary' أزرق | 'success' أخضر | 'danger' أحمر"""
    return InlineKeyboardButton(text, callback_data=data, style=style)


def url_btn(text: str, url: str, style: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, url=url, style=style)


def start_keyboard(channels: list[sqlite3.Row]) -> InlineKeyboardMarkup:
    rows = [[url_btn(f"📢 {ch['title']}", ch["url"], "primary")] for ch in channels]
    rows.append([btn("📖 طريقة الاستخدام", "help", "success")])
    rows.append([btn("❌ إغلاق", "close", "danger")])
    return InlineKeyboardMarkup(rows)


def options_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [btn("🖼 إرسال كصور", "mode:photo", "success")],
            [
                btn("📎 كملفات (جودة أصلية)", "mode:doc", "primary"),
                btn("📦 ZIP", "mode:zip", "primary"),
            ],
            [btn("❌ إلغاء", "cancel", "danger")],
        ]
    )


def again_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[btn("📄 ملف PDF جديد", "new", "success")]])


HELP_TEXT = (
    "📖 طريقة الاستخدام:\n\n"
    f"1️⃣ أرسل ملف PDF (لين {MAX_PDF_MB}MB)\n"
    "2️⃣ اختر طريقة الإرسال\n"
    "3️⃣ استلم الصور 🎉\n\n"
    f"ملاحظة: الحد الأقصى {MAX_IMAGES} صورة لكل ملف، "
    "والملفات المحمية بكلمة مرور غير مدعومة."
)


# ───────────────────────── استخراج الصور ─────────────────────────
def extract_images(pdf_path: Path, out_dir: Path) -> list[Path]:
    """يستخرج الصور من الـ PDF ويرجّع مسارات الملفات (دالة blocking)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    seen: set[int] = set()

    with fitz.open(pdf_path) as doc:
        for page_num, page in enumerate(doc, start=1):
            for idx, img in enumerate(page.get_images(full=True), start=1):
                if len(results) >= MAX_IMAGES:
                    return results

                xref, smask = img[0], img[1]
                if xref in seen:  # نفس الصورة مكررة في أكثر من صفحة
                    continue
                seen.add(xref)

                try:
                    info = doc.extract_image(xref)
                    if (
                        not info
                        or info["width"] < MIN_SIZE
                        or info["height"] < MIN_SIZE
                    ):
                        continue

                    base = out_dir / f"page{page_num:03d}_img{idx:02d}"

                    # JPEG عادي بدون شفافية → نحفظه كما هو (أفضل جودة وأصغر حجم)
                    if (
                        info["ext"] in ("jpeg", "jpg")
                        and not smask
                        and info.get("colorspace") in (1, 3)
                    ):
                        path = base.with_suffix(".jpg")
                        path.write_bytes(info["image"])
                    else:
                        pix = fitz.Pixmap(doc, xref)
                        # CMYK أو غيره → RGB
                        if pix.colorspace is None or pix.colorspace.n not in (1, 3):
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        # شفافية الصورة
                        if smask and not pix.alpha:
                            try:
                                pix = fitz.Pixmap(pix, fitz.Pixmap(doc, smask))
                            except Exception:
                                pass
                        path = base.with_suffix(".png")
                        pix.save(path)

                    results.append(path)
                except Exception as e:  # صورة وحدة خربانة ما توقف الباقي
                    logger.warning("skip xref=%s: %s", xref, e)

    return results


# ───────────────────────── أدوات مساعدة ─────────────────────────
def cleanup(context: ContextTypes.DEFAULT_TYPE) -> None:
    workdir = context.user_data.pop("workdir", None)
    context.user_data.pop("file_name", None)
    if workdir:
        shutil.rmtree(workdir, ignore_errors=True)


async def send_chunk(bot, chat_id: int, chunk: list[Path], as_photo: bool, caption: str):
    if len(chunk) == 1:  # send_media_group يحتاج 2–10 عناصر
        p = chunk[0]
        if as_photo:
            await bot.send_photo(chat_id, p.read_bytes(), caption=caption, write_timeout=120)
        else:
            await bot.send_document(
                chat_id, p.read_bytes(), filename=p.name, caption=caption, write_timeout=120
            )
        return

    if as_photo:
        media = [
            InputMediaPhoto(p.read_bytes(), caption=caption if i == 0 else None)
            for i, p in enumerate(chunk)
        ]
    else:
        media = [
            InputMediaDocument(
                p.read_bytes(), filename=p.name, caption=caption if i == 0 else None
            )
            for i, p in enumerate(chunk)
        ]
    await bot.send_media_group(chat_id, media, write_timeout=120)


async def send_images(bot, chat_id: int, images: list[Path], as_photo: bool):
    total = len(images)
    for start in range(0, total, 10):
        chunk = images[start : start + 10]
        caption = f"{start + 1}–{start + len(chunk)} من {total}"
        try:
            await send_chunk(bot, chat_id, chunk, as_photo, caption)
        except TelegramError as e:
            logger.warning("group failed (%s) → fallback to documents", e)
            for p in chunk:  # تلجرام رفض الصور (حجم/أبعاد) → نرسلها كملفات
                try:
                    await bot.send_document(
                        chat_id, p.read_bytes(), filename=p.name, write_timeout=120
                    )
                except TelegramError as e2:
                    logger.error("failed %s: %s", p.name, e2)
        await asyncio.sleep(1)  # تجنب الـ flood


async def safe_edit(q, text: str, markup=None, html_mode: bool = True) -> None:
    try:
        await q.edit_message_text(
            text,
            parse_mode=ParseMode.HTML if html_mode else None,
            reply_markup=markup,
        )
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


def user_link(user_id: int, first_name: str | None, username: str | None) -> str:
    name = html.escape((first_name or "بدون اسم")[:30])
    s = f'<a href="tg://user?id={user_id}">{name}</a>'
    if username:
        s += f" (@{html.escape(username)})"
    return s


def short(text: str | None, n: int = 60) -> str:
    text = text or "بدون اسم"
    return html.escape(text if len(text) <= n else text[: n - 1] + "…")


def pager_row(prefix: str, page: int, pages: int, suffix: str = "") -> list:
    row = []
    if page > 0:
        row.append(btn("◀️ السابق", f"adm:{prefix}:{page - 1}{suffix}", "primary"))
    if page < pages - 1:
        row.append(btn("التالي ▶️", f"adm:{prefix}:{page + 1}{suffix}", "primary"))
    return row


# ───────────────────────── أوامر المستخدم ─────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user)
    context.user_data.pop("state", None)

    channels = get_channels()
    text = (
        f"هلا {user.first_name or 'صديقي'} 👋\n\n"
        "أرسل لي أي ملف PDF وأنا أستخرج لك كل الصور اللي داخله 🖼"
    )
    if channels:
        text += "\n\n📢 لا تنسى تتابع قنواتنا:"
    await update.message.reply_text(text, reply_markup=start_keyboard(channels))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 آيديك: <code>{update.effective_user.id}</code>", parse_mode=ParseMode.HTML
    )


async def hint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 أرسل لي ملف PDF عشان أستخرج الصور منه.")


async def wrong_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ الملف لازم يكون بصيغة PDF.")


async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    doc = msg.document
    upsert_user(update.effective_user)

    if doc.file_size and doc.file_size > MAX_PDF_MB * 1024 * 1024:
        await msg.reply_text(f"❌ الملف كبير. الحد الأقصى {MAX_PDF_MB}MB.")
        return

    cleanup(context)  # نظّف أي جلسة قديمة
    status = await msg.reply_text("⏳ جاري تحميل الملف...")

    workdir = Path(tempfile.mkdtemp(prefix="pdfimg_"))
    context.user_data["workdir"] = str(workdir)
    context.user_data["file_name"] = doc.file_name or "document.pdf"
    pdf_path = workdir / "input.pdf"

    try:
        tg_file = await doc.get_file()
        await tg_file.download_to_drive(pdf_path)

        with fitz.open(pdf_path) as pdf:
            if pdf.needs_pass:
                raise ValueError("encrypted")
            pages = pdf.page_count
    except ValueError:
        cleanup(context)
        await status.edit_text("🔒 الملف محمي بكلمة مرور، ما أقدر أفتحه.")
        return
    except Exception as e:
        logger.exception("download/open failed: %s", e)
        cleanup(context)
        await status.edit_text("❌ ما قدرت أفتح الملف. تأكد إنه PDF سليم.")
        return

    await status.edit_text(
        f"✅ تم استلام الملف ({pages} صفحة)\n\nاختر طريقة الإرسال:",
        reply_markup=options_keyboard(),
    )


# ───────────────────────── أزرار المستخدم ─────────────────────────
async def on_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    mode = q.data.split(":", 1)[1]  # photo | doc | zip

    workdir = context.user_data.get("workdir")
    pdf_path = Path(workdir) / "input.pdf" if workdir else None
    if not pdf_path or not pdf_path.exists():
        await q.edit_message_text("⚠️ انتهت الجلسة، أرسل الملف من جديد.")
        return

    await q.edit_message_text("⏳ جاري استخراج الصور...")
    chat_id = q.message.chat_id

    try:
        images = await asyncio.to_thread(extract_images, pdf_path, Path(workdir) / "images")
    except Exception as e:
        logger.exception("extract failed: %s", e)
        cleanup(context)
        await q.edit_message_text("❌ صار خطأ أثناء الاستخراج.")
        return

    if not images:
        cleanup(context)
        await q.edit_message_text(
            "🤷 ما لقيت صور داخل الملف.", reply_markup=again_keyboard()
        )
        return

    note = f"\n(أول {MAX_IMAGES} صورة فقط)" if len(images) >= MAX_IMAGES else ""
    await q.edit_message_text(f"📤 جاري إرسال {len(images)} صورة...{note}")

    keep_session = False
    try:
        if mode == "zip":
            zip_path = Path(workdir) / "images.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
                for p in images:
                    zf.write(p, p.name)
            if zip_path.stat().st_size > ZIP_LIMIT_MB * 1024 * 1024:
                keep_session = True  # خله يختار طريقة ثانية
                await q.edit_message_text(
                    "⚠️ حجم الـ ZIP كبير، اختر طريقة ثانية:",
                    reply_markup=options_keyboard(),
                )
                return
            await context.bot.send_document(
                chat_id,
                zip_path.read_bytes(),
                filename="images.zip",
                caption=f"📦 {len(images)} صورة",
                write_timeout=180,
            )
        else:
            await send_images(context.bot, chat_id, images, as_photo=(mode == "photo"))

        # تسجيل العملية للأدمن (المستخدم + اسم الملف + عدد الصور)
        record_extraction(
            q.from_user.id,
            context.user_data.get("file_name", "document.pdf"),
            len(images),
        )
        await q.edit_message_text(
            f"✅ تم! أرسلت {len(images)} صورة.", reply_markup=again_keyboard()
        )
    except TelegramError as e:
        logger.exception("send failed: %s", e)
        await q.edit_message_text("❌ صار خطأ أثناء الإرسال.")
    finally:
        if not keep_session:
            cleanup(context)


async def on_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("تم الإلغاء")
    cleanup(context)
    await q.edit_message_text("❌ تم الإلغاء.", reply_markup=again_keyboard())


async def on_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(HELP_TEXT)


async def on_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("📄 أرسل ملف PDF الجديد.")


async def on_close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.delete()


# ───────────────────────── لوحة الأدمن: العروض (Views) ─────────────────────────
def admin_home_view() -> tuple[str, InlineKeyboardMarkup]:
    kb = InlineKeyboardMarkup(
        [
            [btn("📢 إدارة القنوات", "adm:chs", "primary")],
            [
                btn("📊 الإحصائيات", "adm:stats", "success"),
                btn("👥 المستخدمين", "adm:users:0", "primary"),
            ],
            [btn("📄 سجل الملفات", "adm:files:0:0", "primary")],
            [btn("❌ إغلاق", "close", "danger")],
        ]
    )
    return "🛠 <b>لوحة التحكم</b>\n\nاختر من الأزرار:", kb


def channels_view() -> tuple[str, InlineKeyboardMarkup]:
    channels = get_channels()
    rows = []
    for ch in channels:
        rows.append(
            [
                url_btn(f"📢 {ch['title'][:28]}", ch["url"], "primary"),
                btn("🗑 حذف", f"adm:del:{ch['id']}", "danger"),
            ]
        )
    rows.append([btn("➕ إضافة قناة", "adm:addch", "success")])
    rows.append([btn("🔙 رجوع", "adm:home")])

    if channels:
        text = f"📢 <b>القنوات المضافة</b> ({len(channels)}/{MAX_CHANNELS})\n\nهذي القنوات تظهر للمستخدمين عند /start"
    else:
        text = "📢 ما في قنوات مضافة بعد.\n\nاضغط ➕ إضافة قناة."
    return text, InlineKeyboardMarkup(rows)


def stats_view() -> tuple[str, InlineKeyboardMarkup]:
    today = "date({col}) = date('now','localtime')"
    users = db_one("SELECT COUNT(*) c FROM users")["c"]
    users_today = db_one(
        f"SELECT COUNT(*) c FROM users WHERE {today.format(col='joined_at')}"
    )["c"]
    files = db_one("SELECT COUNT(*) c, COALESCE(SUM(images),0) s FROM extractions")
    files_today = db_one(
        f"SELECT COUNT(*) c FROM extractions WHERE {today.format(col='created_at')}"
    )["c"]
    channels = db_one("SELECT COUNT(*) c FROM channels")["c"]

    text = (
        "📊 <b>الإحصائيات</b>\n\n"
        f"👥 المستخدمين: <b>{users}</b> (جدد اليوم: {users_today})\n"
        f"📄 الملفات المستخرجة: <b>{files['c']}</b> (اليوم: {files_today})\n"
        f"🖼 مجموع الصور: <b>{files['s']}</b>\n"
        f"📢 القنوات: <b>{channels}</b>"
    )
    return text, InlineKeyboardMarkup([[btn("🔙 رجوع", "adm:home")]])


def users_view(page: int) -> tuple[str, InlineKeyboardMarkup]:
    total = db_one("SELECT COUNT(*) c FROM users")["c"]
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(max(page, 0), pages - 1)

    rows = db_all(
        """
        SELECT u.user_id, u.first_name, u.username, u.joined_at, u.last_seen,
               COUNT(e.id) AS files, COALESCE(SUM(e.images), 0) AS imgs
        FROM users u LEFT JOIN extractions e ON e.user_id = u.user_id
        GROUP BY u.user_id
        ORDER BY u.last_seen DESC
        LIMIT ? OFFSET ?
        """,
        (PAGE_SIZE, page * PAGE_SIZE),
    )

    if not rows:
        text = "👥 ما في مستخدمين بعد."
    else:
        lines = [f"👥 <b>المستخدمين</b> ({total}) — صفحة {page + 1}/{pages}\n"]
        for i, r in enumerate(rows, start=page * PAGE_SIZE + 1):
            lines.append(
                f"{i}. {user_link(r['user_id'], r['first_name'], r['username'])}\n"
                f"    🆔 <code>{r['user_id']}</code> • 📄 {r['files']} ملف • 🖼 {r['imgs']} صورة\n"
                f"    🕒 آخر نشاط: {r['last_seen']}"
            )
        lines.append("\nلعرض ملفات مستخدم: <code>/user الآيدي</code>")
        text = "\n".join(lines)

    kb_rows = []
    pr = pager_row("users", page, pages)
    if pr:
        kb_rows.append(pr)
    kb_rows.append([btn("🔙 رجوع", "adm:home")])
    return text, InlineKeyboardMarkup(kb_rows)


def files_view(page: int, uid: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    where, params = ("WHERE e.user_id = ?", (uid,)) if uid else ("", ())
    total = db_one(f"SELECT COUNT(*) c FROM extractions e {where}", params)["c"]
    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(max(page, 0), pages - 1)

    rows = db_all(
        f"""
        SELECT e.file_name, e.images, e.created_at, e.user_id,
               u.first_name, u.username
        FROM extractions e LEFT JOIN users u ON u.user_id = e.user_id
        {where}
        ORDER BY e.id DESC
        LIMIT ? OFFSET ?
        """,
        params + (PAGE_SIZE, page * PAGE_SIZE),
    )

    title = "📄 <b>سجل الملفات</b>"
    if uid:
        u = db_one("SELECT first_name, username FROM users WHERE user_id = ?", (uid,))
        if u:
            title = f"📄 <b>ملفات</b> {user_link(uid, u['first_name'], u['username'])}"

    if not rows:
        text = f"{title}\n\nما في ملفات مسجلة."
    else:
        lines = [f"{title} ({total}) — صفحة {page + 1}/{pages}\n"]
        for i, r in enumerate(rows, start=page * PAGE_SIZE + 1):
            lines.append(
                f"{i}. 📄 <b>{short(r['file_name'])}</b>\n"
                f"    👤 {user_link(r['user_id'], r['first_name'], r['username'])}\n"
                f"    🖼 {r['images']} صورة • 🕒 {r['created_at']}"
            )
        text = "\n".join(lines)

    kb_rows = []
    pr = pager_row("files", page, pages, suffix=f":{uid}")
    if pr:
        kb_rows.append(pr)
    kb_rows.append([btn("🔙 رجوع", "adm:home")])
    return text, InlineKeyboardMarkup(kb_rows)


# ───────────────────────── لوحة الأدمن: الأوامر والأزرار ─────────────────────────
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ هذا الأمر للأدمن فقط.")
        return
    context.user_data.pop("state", None)
    text, kb = admin_home_view()
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/user 123456789 → ملفات مستخدم معيّن"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ هذا الأمر للأدمن فقط.")
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("الاستخدام: /user 123456789")
        return
    uid = int(context.args[0])
    if not db_one("SELECT 1 FROM users WHERE user_id = ?", (uid,)):
        await update.message.reply_text("🤷 ما لقيت هذا المستخدم.")
        return
    text, kb = files_view(0, uid)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def on_admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("⛔ للأدمن فقط", show_alert=True)
        return
    await q.answer()

    parts = q.data.split(":")  # adm:<action>[:arg][:arg]
    action = parts[1]

    if action == "home":
        context.user_data.pop("state", None)
        text, kb = admin_home_view()

    elif action == "chs":
        context.user_data.pop("state", None)
        text, kb = channels_view()

    elif action == "addch":
        if db_one("SELECT COUNT(*) c FROM channels")["c"] >= MAX_CHANNELS:
            await q.answer(f"وصلت للحد الأقصى ({MAX_CHANNELS} قناة)", show_alert=True)
            return
        context.user_data["state"] = "add_channel"
        text = (
            "➕ <b>إضافة قناة</b>\n\n"
            "أرسل القناة بإحدى هذي الصيغ:\n\n"
            "• <code>@username</code>\n"
            "• <code>https://t.me/username</code>\n"
            "• <code>الاسم | الرابط</code>\n\n"
            "القنوات الخاصة (رابط الدعوة) لازم تكتبها بصيغة <code>الاسم | الرابط</code>"
        )
        kb = InlineKeyboardMarkup([[btn("❌ إلغاء", "adm:chs", "danger")]])

    elif action == "del":
        db_run("DELETE FROM channels WHERE id = ?", (int(parts[2]),))
        text, kb = channels_view()

    elif action == "stats":
        text, kb = stats_view()

    elif action == "users":
        text, kb = users_view(int(parts[2]))

    elif action == "files":
        text, kb = files_view(int(parts[2]), int(parts[3]) if len(parts) > 3 else 0)

    else:
        return

    await safe_edit(q, text, kb)


# ───────────────────────── إضافة قناة (رسالة نصية من الأدمن) ─────────────────────────
CHANNEL_RE = re.compile(
    r"^(?:https?://)?(?:t|telegram)\.me/"
    r"(joinchat/[\w\-]+|\+[\w\-]+|[A-Za-z]\w{4,31})/?(?:\?.*)?$",
    re.IGNORECASE,
)
USERNAME_RE = re.compile(r"^@?([A-Za-z]\w{4,31})$")


def parse_channel(text: str):
    """يرجّع (title|None, url, public_username|None) أو None إذا الصيغة غلط."""
    title = None
    link = text.strip()
    if "|" in link:
        title, link = (x.strip() for x in link.split("|", 1))
        title = title or None

    m = CHANNEL_RE.match(link)
    if m:
        path = m.group(1)
    else:
        m = USERNAME_RE.match(link)
        if not m:
            return None
        path = m.group(1)

    is_public = not (path.startswith("+") or path.lower().startswith("joinchat/"))
    return title, f"https://t.me/{path}", (path if is_public else None)


async def process_add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    cancel_kb = InlineKeyboardMarkup([[btn("❌ إلغاء", "adm:chs", "danger")]])

    parsed = parse_channel(msg.text or "")
    if not parsed:
        await msg.reply_text(
            "⚠️ الصيغة غير صحيحة، جرّب:\n@username\nأو\nالاسم | الرابط",
            reply_markup=cancel_kb,
        )
        return

    title, url, username = parsed
    if title is None:
        if username:  # قناة عامة → نجيب اسمها تلقائياً
            try:
                chat = await context.bot.get_chat(f"@{username}")
                title = chat.title or f"@{username}"
            except TelegramError:
                title = f"@{username}"
        else:
            await msg.reply_text(
                "🔒 هذا رابط قناة خاصة، اكتب الاسم قبل الرابط:\nالاسم | الرابط",
                reply_markup=cancel_kb,
            )
            return

    if db_one("SELECT COUNT(*) c FROM channels")["c"] >= MAX_CHANNELS:
        context.user_data.pop("state", None)
        await msg.reply_text(f"⚠️ وصلت للحد الأقصى ({MAX_CHANNELS} قناة).")
        return

    try:
        db_run("INSERT INTO channels (title, url) VALUES (?, ?)", (title[:60], url))
    except sqlite3.IntegrityError:
        await msg.reply_text("⚠️ هذي القناة مضافة من قبل.", reply_markup=cancel_kb)
        return

    context.user_data.pop("state", None)
    text, kb = channels_view()
    await msg.reply_text(
        f"✅ تمت إضافة: <b>{html.escape(title)}</b>\n\n{text}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") == "add_channel" and is_admin(update.effective_user.id):
        await process_add_channel(update, context)
        return
    await hint(update, context)

from flask import Flask
import threading
import os

web_app = Flask(__name__)
@web_app.route('/')
def home(): return "Bot is Running! 🚀"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_web, daemon=True).start()

# ───────────────────────── التشغيل ─────────────────────────
def main():
    if BOT_TOKEN == "PUT_YOUR_TOKEN_HERE":
        raise SystemExit("حط توكن البوت في المتغير BOT_TOKEN")
    if not ADMIN_IDS:
        logger.warning("ADMIN_IDS فاضي — ما راح تشتغل لوحة الأدمن. حط آيديك بالمتغير.")

    init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)  # أكثر من مستخدم بنفس الوقت
        .read_timeout(60)
        .write_timeout(60)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("user", user_cmd))

    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
    app.add_handler(MessageHandler(filters.Document.ALL, wrong_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.add_handler(CallbackQueryHandler(on_admin_cb, pattern=r"^adm:"))
    app.add_handler(CallbackQueryHandler(on_mode, pattern=r"^mode:(photo|doc|zip)$"))
    app.add_handler(CallbackQueryHandler(on_cancel, pattern=r"^cancel$"))
    app.add_handler(CallbackQueryHandler(on_help, pattern=r"^help$"))
    app.add_handler(CallbackQueryHandler(on_new, pattern=r"^new$"))
    app.add_handler(CallbackQueryHandler(on_close, pattern=r"^close$"))

    logger.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
