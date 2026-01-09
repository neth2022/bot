import os
import subprocess
from flask import Flask, request

from telegram import Bot, Update
from telegram.ext import Dispatcher, MessageHandler, Filters

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN env var is missing")

bot = Bot(token=TOKEN)

app = Flask(__name__)

# IMPORTANT: dispatcher must be created BEFORE add_handler()
dispatcher = Dispatcher(bot=bot, update_queue=None, workers=2, use_context=True)

def handle_message(update, context):
    text = (update.message.text or "").strip()

    if not (text.startswith("http") and ".m3u8" in text.lower()):
        update.message.reply_text("Send a valid .m3u8 link (non-DRM / authorized).")
        return

    update.message.reply_text("Downloading…")

    out_path = "/tmp/output.mp4"
    cmd = ["ffmpeg", "-y", "-i", text, "-c", "copy", "-bsf:a", "aac_adtstoasc", out_path]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if r.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        update.message.reply_text("Failed. Possible DRM/protection or bad link.")
        return

    with open(out_path, "rb") as f:
        update.message.reply_video(f, caption="✅ Done")

dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

@app.get("/")
def home():
    return "OK"

@app.post(f"/{TOKEN}")
def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "OK"
@app.get("/")
def home():
    return "OK"

# Telegram will POST updates here
@app.post(f"/{TOKEN}")
def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "OK"
