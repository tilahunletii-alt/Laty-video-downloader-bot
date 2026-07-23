# 🎬 Media Downloader Telegram Bot

A production-ready Telegram bot that downloads videos and audio from 15+ platforms using `yt-dlp`.

## Supported Platforms

| Platform      | Video | Audio |
|---------------|-------|-------|
| YouTube       | ✅    | ✅    |
| TikTok        | ✅    | ✅    |
| Instagram     | ✅    | ✅    |
| Twitter / X   | ✅    | ✅    |
| Facebook      | ✅    | ✅    |
| Reddit        | ✅    | ✅    |
| Twitch        | ✅    | ✅    |
| Vimeo         | ✅    | ✅    |
| Dailymotion   | ✅    | ✅    |
| SoundCloud    | —     | ✅    |
| Pinterest     | ✅    | —     |
| LinkedIn      | ✅    | —     |
| Bilibili      | ✅    | ✅    |
| VK / OK.ru    | ✅    | ✅    |

## Features

- 📥 Download videos in Low (360p), Medium (480p), High (720p)
- 🎵 Extract audio as MP3 (192 kbps)
- 🔒 Per-user concurrency lock — no spam abuse
- 📦 50 MB file-size guard with helpful error message
- 🧹 Auto cleanup of downloaded files after sending
- 🚀 Async yt-dlp execution — event loop never blocked
- ✅ Startup validation of BOT_TOKEN
- 📋 Structured logging for production debugging

## Local Setup

```bash
# 1. Clone and enter the folder
git clone <repo-url>
cd bot

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install ffmpeg (required for MP3 extraction and video merging)
#    macOS:   brew install ffmpeg
#    Ubuntu:  sudo apt install ffmpeg
#    Windows: https://ffmpeg.org/download.html

# 4. Set your bot token
set BOT_TOKEN=your_token_here       # Windows CMD
export BOT_TOKEN=your_token_here    # Linux/macOS

# 5. Run
python bot.py
```

## Deployment

### Heroku

```bash
heroku create your-app-name
heroku buildpacks:add heroku/python
heroku buildpacks:add https://github.com/jonathanong/heroku-buildpack-ffmpeg-latest.git
heroku config:set BOT_TOKEN=your_token_here
git push heroku main
heroku ps:scale worker=1
```

### Render

1. Create a new **Background Worker** service
2. Set Build Command: `pip install -r requirements.txt`
3. Set Start Command: `python bot.py`
4. Add environment variable `BOT_TOKEN`
5. Add `ffmpeg` as a system package in the **Environment** tab

### Railway

```bash
railway init
railway add
railway variables set BOT_TOKEN=your_token_here
railway up
```

## Environment Variables

| Variable    | Required | Description              |
|-------------|----------|--------------------------|
| `BOT_TOKEN` | ✅        | Your Telegram bot token  |

## Commands

| Command  | Description         |
|----------|---------------------|
| `/start` | Welcome message     |
| `/help`  | Usage instructions  |
