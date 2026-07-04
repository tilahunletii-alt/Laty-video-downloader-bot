import os
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import yt_dlp

TOKEN = "8926121379:AAHjOb1JAvHMIFI_ROq2RI6pZz5XHIZ89m8"
DOWNLOAD_FOLDER = "downloads"

os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def sanitize_filename(name):
    name = re.sub(r'[\\/*?:"<>|]', "_", name)   # Replace bad chars with _
    name = re.sub(r'\s+', " ", name).strip()
    return name[:150]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎥 Send link and choose format.")

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith(("http", "https")):
        await update.message.reply_text("Send valid URL.")
        return

    keyboard = [
        [InlineKeyboardButton("Video Low", callback_data=f"vlow|{url}")],
        [InlineKeyboardButton("Video Medium", callback_data=f"vmed|{url}")],
        [InlineKeyboardButton("Video High", callback_data=f"vhigh|{url}")],
        [InlineKeyboardButton("Audio MP3", callback_data=f"audio|{url}")]
    ]
    await update.message.reply_text("Choose format:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice, url = query.data.split("|", 1)
    msg = await query.edit_message_text("⏳ Downloading...")

    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s.%(ext)s',
        'noplaylist': True,
    }

    if choice.startswith("v"):
        height = {"vlow": 360, "vmed": 480, "vhigh": 720}[choice]
        ydl_opts['format'] = f'best[height<={height}]/best'
        send_func = context.bot.send_video
    else:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]
        send_func = context.bot.send_audio

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Get the actual downloaded file
            if 'requested_downloads' in info:
                downloaded = info['requested_downloads'][0]
                filename = downloaded.get('filepath') or downloaded.get('filename')
            else:
                filename = ydl.prepare_filename(info)

            # Strong sanitization
            if not os.path.exists(filename):
                dir_path = DOWNLOAD_FOLDER
                base = sanitize_filename(os.path.basename(filename))
                filename = os.path.join(dir_path, base)

            size_mb = os.path.getsize(filename) / (1024 * 1024)
            title = info.get('title', 'Media')

            await msg.edit_text(f"✅ Downloaded ({size_mb:.1f} MB)")

            with open(filename, 'rb') as f:
                await send_func(chat_id=update.effective_chat.id, 
                               **{send_func.__name__.split('_')[1]: f}, 
                               caption=title)

            os.remove(filename)

    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)[:300]}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("Bot Running...")
    app.run_polling()

if __name__ == '__main__':
    main()