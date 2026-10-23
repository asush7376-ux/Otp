"""
بوت تلجرام لاستخراج الصور من ملفات PDF
أزرار ملونة (primary = أزرق / success = أخضر / danger = أحمر)

التثبيت:
    pip install "python-telegram-bot>=22.7" pymupdf

التشغيل:
    export BOT_TOKEN="123456:ABC..."
    python pdf_images_bot.py
"""

import asyncio
import logging
import os
import shutil
import tempfile
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
from telegram.error import TelegramError
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
MAX_PDF_MB = 20      # حد تلجرام لتحميل الملفات للبوتات
MAX_IMAGES = 100     # أقصى عدد صور يستخرجها البوت لكل ملف
MIN_SIZE = 50        # تجاهل الصور الأصغر من هذا (بالبكسل) مثل الأيقونات
ZIP_LIMIT_MB = 49    # حد رفع تلجرام 50MB

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO
)
logger = logging.getLogger("pdf-images-bot")


# ───────────────────────── الأزرار الملونة ─────────────────────────
def btn(text: str, data: str, style: str | None = None) -> InlineKeyboardButton:
    """style: 'primary' أزرق | 'success' أخضر | 'danger' أحمر"""
    return InlineKeyboardButton(text, callback_data=data, style=style)


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [btn("📖 طريقة الاستخدام", "help", "primary")],
            [btn("❌ إغلاق", "close", "danger")],
        ]
    )


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
    "1️⃣ أرسل ملف PDF (لين 20MB)\n"
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


# ───────────────────────── الأوامر ─────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "صديقي"
    await update.message.reply_text(
        f"هلا {name} 👋\n\n"
        "أرسل لي أي ملف PDF وأنا أستخرج لك كل الصور اللي داخله 🖼",
        reply_markup=start_keyboard(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def hint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📄 أرسل لي ملف PDF عشان أستخرج الصور منه.")


async def wrong_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ الملف لازم يكون بصيغة PDF.")


async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    doc = msg.document

    if doc.file_size and doc.file_size > MAX_PDF_MB * 1024 * 1024:
        await msg.reply_text(f"❌ الملف كبير. الحد الأقصى {MAX_PDF_MB}MB.")
        return

    cleanup(context)  # نظّف أي جلسة قديمة
    status = await msg.reply_text("⏳ جاري تحميل الملف...")

    workdir = Path(tempfile.mkdtemp(prefix="pdfimg_"))
    context.user_data["workdir"] = str(workdir)
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


# ───────────────────────── الأزرار (Callbacks) ─────────────────────────
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

    try:
        if mode == "zip":
            zip_path = Path(workdir) / "images.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
                for p in images:
                    zf.write(p, p.name)
            if zip_path.stat().st_size > ZIP_LIMIT_MB * 1024 * 1024:
                await context.bot.send_message(
                    chat_id, "⚠️ حجم الـ ZIP كبير، جرب إرسال الصور كملفات."
                )
            else:
                await context.bot.send_document(
                    chat_id,
                    zip_path.read_bytes(),
                    filename="images.zip",
                    caption=f"📦 {len(images)} صورة",
                    write_timeout=180,
                )
        else:
            await send_images(context.bot, chat_id, images, as_photo=(mode == "photo"))

        await q.edit_message_text(
            f"✅ تم! أرسلت {len(images)} صورة.", reply_markup=again_keyboard()
        )
    except TelegramError as e:
        logger.exception("send failed: %s", e)
        await q.edit_message_text("❌ صار خطأ أثناء الإرسال.")
    finally:
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
    app.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
    app.add_handler(MessageHandler(filters.Document.ALL, wrong_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, hint))

    app.add_handler(CallbackQueryHandler(on_mode, pattern=r"^mode:(photo|doc|zip)$"))
    app.add_handler(CallbackQueryHandler(on_cancel, pattern=r"^cancel$"))
    app.add_handler(CallbackQueryHandler(on_help, pattern=r"^help$"))
    app.add_handler(CallbackQueryHandler(on_new, pattern=r"^new$"))
    app.add_handler(CallbackQueryHandler(on_close, pattern=r"^close$"))

    logger.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
