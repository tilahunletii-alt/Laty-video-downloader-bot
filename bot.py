import os
import re
import uuid
import logging
import asyncio
from pathlib import Path

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TOKEN = os.environ.get("8926121379:AAHjOb1JAvHMIFI_ROq2RI6pZz5XHIZ89m8")
DOWNLOAD_DIR = Path("bots/downloads")
MAX_FILE_MB = 49          # Telegram Bot API hard limit is 50 MB
MAX_CONCURRENT = 3        # max simultaneous downloads per bot instance

# Per-user lock: prevents the same user from spamming downloads
_user_locks: dict[int, asyncio.Lock] = {}

SUPPORTED_DOMAINS = (
    "youtube.com", "youtu.be",
    "instagram.com",
    "tiktok.com", "vm.tiktok.com",
    "twitter.com", "x.com",
    "facebook.com", "fb.watch",
    "reddit.com", "redd.it",
    "twitch.tv",
    "vimeo.com",
    "dailymotion.com",
    "soundcloud.com",
    "pinterest.com",
    "linkedin.com",
    "bilibili.com",
    "ok.ru",
    "vk.com",
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("yt_dlp").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Global semaphore to cap total concurrent downloads
_semaphore = asyncio.Semaphore(MAX_CONCURRENT)


def get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]


def is_supported_url(url: str) -> bool:
    url_lower = url.lower()
    return url_lower.startswith(("http://", "https://")) and any(
        domain in url_lower for domain in SUPPORTED_DOMAINS
    )


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:100]


def build_ydl_opts(choice: str, output_template: str) -> dict:
    """Return yt-dlp options for the requested format choice."""
    base = {
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        # Retry on transient network failures
        "retries": 3,
        "fragment_retries": 3,
        # Use cookies workaround for age-gated / logged-in content where possible
        "nocheckcertificate": False,
    }

    if choice == "audio":
        base["format"] = "bestaudio/best"
        base["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        height = {"vlow": 360, "vmed": 480, "vhigh": 720}[choice]
        # Prefer a single merged file; fall back to best single stream
        base["format"] = (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]"
            f"/best[height<={height}][ext=mp4]"
            f"/best[height<={height}]"
            f"/best"
        )
        base["merge_output_format"] = "mp4"

    return base


def resolve_filepath(info: dict, ydl: yt_dlp.YoutubeDL) -> Path | None:
    """Extract the actual downloaded file path from yt-dlp info dict."""
    if "requested_downloads" in info:
        dl = info["requested_downloads"][0]
        path = dl.get("filepath") or dl.get("filename")
        if path:
            return Path(path)
    fallback = Path(ydl.prepare_filename(info))
    if fallback.exists():
        return fallback
    return None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

WELCOME_TEXT = (
    "👋 *Welcome to Media Downloader Bot!*\n\n"
    "Send me any link from:\n"
    "• YouTube · TikTok · Instagram\n"
    "• Twitter/X · Facebook · Reddit\n"
    "• Twitch · Vimeo · Dailymotion\n"
    "• SoundCloud · Pinterest · and more\n\n"
    "I'll let you pick the format and quality."
)

HELP_TEXT = (
    "*How to use:*\n"
    "1. Paste a video/audio link\n"
    "2. Choose your preferred format\n"
    "3. Wait for the file\n\n"
    "*Limits:* Files up to 49 MB\n"
    "*Commands:* /start · /help"
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME_TEXT, parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = update.message.text.strip()

    if not is_supported_url(url):
        await update.message.reply_text(
            "⚠️ Please send a valid link from a supported platform.\n"
            "Use /help to see the full list."
        )
        return

    keyboard = [
        [
            InlineKeyboardButton("🎬 Low (360p)",  callback_data=f"vlow|{url}"),
            InlineKeyboardButton("🎬 Mid (480p)",  callback_data=f"vmed|{url}"),
        ],
        [
            InlineKeyboardButton("🎬 High (720p)", callback_data=f"vhigh|{url}"),
            InlineKeyboardButton("🎵 Audio MP3",   callback_data=f"audio|{url}"),
        ],
    ]
    await update.message.reply_text(
        "🔗 Link received! Choose format:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    try:
        choice, url = query.data.split("|", 1)
    except ValueError:
        await query.edit_message_text("❌ Invalid request. Please try again.")
        return

    user_id = update.effective_user.id
    user_lock = get_user_lock(user_id)

    # One active download per user at a time
    if user_lock.locked():
        await query.edit_message_text(
            "⏳ You already have a download in progress. Please wait."
        )
        return

    msg = await query.edit_message_text("⏳ Processing your request...")

    async with user_lock:
        async with _semaphore:
            await _do_download(update, context, msg, choice, url)


async def _do_download(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    msg,
    choice: str,
    url: str,
) -> None:
    """Run the actual yt-dlp download and send the file."""
    # Unique prefix per request prevents filename collisions
    uid = uuid.uuid4().hex[:8]
    output_template = str(DOWNLOAD_DIR / f"{uid}_%(title).80s.%(ext)s")
    filepath: Path | None = None

    try:
        await msg.edit_text("⬇️ Downloading... please wait.")

        ydl_opts = build_ydl_opts(choice, output_template)

        # Run blocking yt-dlp in a thread so the event loop stays free
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            None, lambda: _run_ydl(ydl_opts, url)
        )

        if info is None:
            await msg.edit_text("❌ Could not fetch media info. The link may be private or unsupported.")
            return

        # Resolve file path
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            filepath = resolve_filepath(info, ydl)

        # If resolve_filepath failed, scan the folder for our uid prefix
        if filepath is None or not filepath.exists():
            matches = list(DOWNLOAD_DIR.glob(f"{uid}_*"))
            filepath = matches[0] if matches else None

        if filepath is None or not filepath.exists():
            await msg.edit_text("❌ Downloaded file not found. Please try again.")
            return

        size_mb = filepath.stat().st_size / (1024 * 1024)

        if size_mb > MAX_FILE_MB:
            await msg.edit_text(
                f"❌ File is too large ({size_mb:.1f} MB). "
                f"Telegram's limit is {MAX_FILE_MB} MB.\n"
                "Try a lower quality option."
            )
            return

        title = info.get("title", "Media")[:200]
        await msg.edit_text(f"📤 Uploading *{title}* ({size_mb:.1f} MB)…", parse_mode=ParseMode.MARKDOWN)

        with open(filepath, "rb") as f:
            if choice == "audio":
                await context.bot.send_audio(
                    chat_id=update.effective_chat.id,
                    audio=f,
                    caption=f"🎵 {title}",
                    title=title,
                )
            else:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=f,
                    caption=f"🎬 {title}",
                    supports_streaming=True,
                )

        await msg.edit_text("✅ Done!")
        logger.info("Sent %s (%.1f MB) to user %s", filepath.name, size_mb, update.effective_user.id)

    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        logger.warning("DownloadError for %s: %s", url, err)
        if "Private" in err or "login" in err.lower():
            await msg.edit_text("❌ This content is private or requires login.")
        elif "Unsupported URL" in err:
            await msg.edit_text("❌ This URL is not supported by the downloader.")
        else:
            await msg.edit_text(f"❌ Download failed:\n{err[:300]}")

    except Exception as e:
        logger.exception("Unexpected error for %s", url)
        await msg.edit_text(f"❌ Unexpected error: {str(e)[:300]}")

    finally:
        # Always clean up the file
        if filepath and filepath.exists():
            try:
                filepath.unlink()
            except OSError:
                pass


def _run_ydl(ydl_opts: dict, url: str) -> dict | None:
    """Blocking yt-dlp call — runs in a thread executor."""
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=True)


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception", exc_info=context.error)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if not TOKEN:
        raise RuntimeError(
            "BOT_TOKEN environment variable is not set. "
            "Set it before running the bot."
        )

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_error_handler(error_handler)

    logger.info("Bot started. Polling for updates...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,   # ignore messages sent while bot was offline
    )


if __name__ == "__main__":
    main()
