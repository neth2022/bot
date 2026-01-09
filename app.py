import os
import subprocess
from flask import Flask, request

from telegram import Bot, Update
from telegram.ext import Dispatcher, MessageHandler, Filters

# Read token from environment
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing")

bot = Bot(token=TOKEN)

app = Flask(__name__)

# Dispatcher MUST be created before handlers are added
dispatcher = Dispatcher(bot=bot, update_queue=None, workers=2, use_context=True)


def handle_message(update, context):
    text = (update.message.text or "").strip()

    if not (text.startswith("http") and ".m3u8" in text.lower()):
        update.message.reply_text("Send a valid .m3u8 link (non-DRM).")
        return

    update.message.reply_text("Downloading… please wait")

    output = "/tmp/output.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-i", text,
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        output
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode != 0 or not os.path.exists(output):
        update.message.reply_text("❌ Failed (DRM / invalid link).")
        return

    with open(output, "rb") as f:
        update.message.reply_video(f, caption="✅ Done")


# Register handler
dispatcher.add_handler(
    MessageHandler(Filters.text & ~Filters.command, handle_message)
)


# Health check route (ONLY ONE / route)
@app.route("/", methods=["GET"])
def health():
    return "OK"


# Telegram webhook
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "OK"
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
