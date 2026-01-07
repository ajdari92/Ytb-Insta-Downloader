import os
import logging
import asyncio
import threading
import shutil
import yt_dlp
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.request import HTTPXRequest

# --- تنظیمات ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
# آدرس سرور لوکال که در Dockerfile روی پورت 8081 تنظیم کردیم
LOCAL_API_URL = "http://127.0.0.1:8081/bot"

COOKIES_FILE = "cookies.txt"

# پوشه‌های دیتا برای تمیزکاری
DOWNLOAD_DIR = "downloads"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- وب‌سرویس Flask (Fake Server) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running with Local API Server!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- توابع yt-dlp ---
def get_formats(url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info: info = info['entries'][0]

            formats = info.get('formats', [])
            clean_formats = []
            
            for f in formats:
                if f.get('vcodec') != 'none' and f.get('height'):
                    height = f.get('height')
                    filesize = f.get('filesize') or f.get('filesize_approx')
                    size_str = f"{filesize / (1024*1024):.1f}MB" if filesize else "N/A"
                    clean_formats.append({'label': f"{height}p - {size_str}", 'format_id': f['format_id'], 'height': height})

            # حذف تکراری‌ها و مرتب‌سازی
            unique_formats = {f['height']: f for f in clean_formats}
            sorted_formats = sorted(unique_formats.values(), key=lambda x: x['height'], reverse=True)
            
            final_list = [{'label': '🌟 بهترین کیفیت (Max)', 'format_id': 'best'}] + sorted_formats[:6]
            final_list.append({'label': '🎵 فقط صدا (MP3)', 'format_id': 'audio_only'})
            
            return final_list, info.get('title', 'Video')
    except Exception as e:
        logger.error(f"Error fetching formats: {e}")
        return None, None

async def download_and_send(url, format_id, chat_id, context):
    if not os.path.exists(DOWNLOAD_DIR): os.makedirs(DOWNLOAD_DIR)
    
    # نام فایل خروجی
    out_name = f"{chat_id}_{context.job_queue.scheduler.time()}"
    output_template = f"{DOWNLOAD_DIR}/{out_name}.%(ext)s"

    ydl_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        # نکته: برای کیفیت بالا باید video+audio مرج شود. ffmpeg در داکر نصب شده است.
        'format': 'bestvideo+bestaudio/best' if format_id == 'best' else format_id,
        'merge_output_format': 'mp4',
    }

    if format_id == 'audio_only':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio','preferredcodec': 'mp3','preferredquality': '192'}]
        output_template = f"{DOWNLOAD_DIR}/{out_name}.mp3"

    status_msg = await context.bot.send_message(chat_id, "⬇️ شروع دانلود روی سرور...")

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([url]))

        # پیدا کردن فایل نهایی
        final_file = None
        for file in os.listdir(DOWNLOAD_DIR):
            if file.startswith(out_name):
                final_file = os.path.join(DOWNLOAD_DIR, file)
                break
        
        if final_file:
            file_size_mb = os.path.getsize(final_file) / (1024 * 1024)
            await status_msg.edit_text(f"⬆️ دانلود تمام شد ({file_size_mb:.1f} MB).\nدر حال آپلود به تلگرام (Local Server)...")
            
            # ارسال فایل (چون لوکال سرور داریم، فایل‌های تا 2000 مگابایت مجاز است)
            # نکته مهم: برای لوکال سرور، فایل را باز می‌کنیم و می‌فرستیم
            with open(final_file, 'rb') as f:
                if format_id == 'audio_only' or final_file.endswith('.mp3'):
                    await context.bot.send_audio(chat_id, audio=f, title="Audio", performer="Bot")
                else:
                    await context.bot.send_video(chat_id, video=f, supports_streaming=True)
            
            await status_msg.delete()
            # پاک کردن فایل دانلود شده
            os.remove(final_file)
        else:
            await status_msg.edit_text("❌ خطا: فایل دانلود شده پیدا نشد.")

    except Exception as e:
        logger.error(f"Download Error: {e}")
        await status_msg.edit_text(f"❌ خطا: {str(e)}")

# --- هندلرها ---
async def start(update: Update, context):
    await update.message.reply_text("👋 سلام! لینک یوتیوب یا اینستاگرام بفرست.")

async def handle_url(update: Update, context):
    url = update.message.text
    msg = await update.message.reply_text("🔎 بررسی...")
    
    loop = asyncio.get_event_loop()
    formats, title = await loop.run_in_executor(None, get_formats, url)
    
    if not formats:
        await msg.edit_text("❌ خطا در دریافت اطلاعات. (لینک پرایوت است یا کوکی معتبر نیست؟)")
        return

    context.user_data['url'] = url
    keyboard = [[InlineKeyboardButton(f['label'], callback_data=f['format_id'])] for f in formats]
    await msg.edit_text(f"🎬 {title}\nکیفیت را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    url = context.user_data.get('url')
    if not url: return
    await query.edit_message_text("⏳ در صف دانلود...")
    await download_and_send(url, query.data, update.effective_chat.id, context)

# --- اجرا ---
def main():
    if not TOKEN:
        print("Set TELEGRAM_TOKEN env var!")
        return

    # استارت Flask
    threading.Thread(target=run_flask, daemon=True).start()

    # تنظیم ریکوئست تایم‌اوت بالا برای آپلود فایل‌های سنگین
    request = HTTPXRequest(connection_pool_size=8, read_timeout=3000, write_timeout=3000, connect_timeout=60)

    # اتصال به سرور لوکال
    application = ApplicationBuilder().token(TOKEN).base_url(LOCAL_API_URL).request(request).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_handler(CallbackQueryHandler(button_callback))

    print("Bot started on Local Server...")
    application.run_polling()

if __name__ == '__main__':
    main()