import os
import subprocess
import threading
import uuid
from flask import Flask, request

from telegram import Bot, Update
from telegram.ext import Dispatcher, MessageHandler, Filters

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing")

# Optional headers (set in Koyeb env vars if needed)
UA = os.environ.get("FFMPEG_UA", "")           # e.g. "Mozilla/5.0 ..."
REFERER = os.environ.get("FFMPEG_REFERER", "") # e.g. "https://example.com"

bot = Bot(token=TOKEN)
app = Flask(__name__)
dispatcher = Dispatcher(bot=bot, update_queue=None, workers=1, use_context=True)

MAX_SECONDS = int(os.environ.get("MAX_SECONDS", "900"))  # 15 min default


def ffmpeg_cmd(url: str, out_path: str):
    cmd = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-hide_banner",
        "-loglevel", "error",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_delay_max", "5",
    ]

    # Add headers if provided (many m3u8 require these)
    headers = []
    if REFERER:
        headers.append(f"Referer: {REFERER}")
    if UA:
        headers.append(f"User-Agent: {UA}")
    if headers:
        cmd += ["-headers", "\r\n".join(headers) + "\r\n"]

    cmd += [
        "-i", url,
        "-t", str(MAX_SECONDS),          # stop after MAX_SECONDS
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        out_path
    ]
    return cmd


def download_and_send(chat_id: int, m3u8_url: str, msg_id: int):
    job = uuid.uuid4().hex[:8]
    out_path = f"/tmp/out_{job}.mp4"

    try:
        bot.send_message(chat_id, "⏳ Download started…")

        cmd = ffmpeg_cmd(m3u8_url, out_path)

        r = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=MAX_SECONDS + 60
        )

        if r.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            err = r.stderr.decode("utf-8", "ignore") if isinstance(r.stderr, (bytes, bytearray)) else str(r.stderr)
            tail = "\n".join(err.splitlines()[-10:])
            bot.send_message(chat_id, "❌ Failed.\nPossible: DRM/protected, needs headers/cookies, or invalid link.\n\nLast error:\n" + tail)
            return

        size_mb = os.path.getsize(out_path) / (1024 * 1024)
        bot.send_message(chat_id, f"✅ Download finished ({size_mb:.1f} MB). Uploading…")

        with open(out_path, "rb") as f:
            bot.send_document(chat_id, document=f, filename="output.mp4", caption="✅ Done")

    except subprocess.TimeoutExpired:
        bot.send_message(chat_id, "⏳ Timed out (stream too long / stuck). Try a shorter link.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {e}")
    finally:
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass


def handle_message(update, context):
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if not (text.startswith("http") and ".m3u8" in text.lower()):
        update.message.reply_text("Send a valid .m3u8 link (non-DRM).")
        return

    m = update.message.reply_text("Downloading… please wait ✅")
    threading.Thread(target=download_and_send, args=(chat_id, text, m.message_id), daemon=True).start()


dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))


@app.route("/", methods=["GET"])
def health():
    return "OK"


@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "OK"
