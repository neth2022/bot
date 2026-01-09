import os
import subprocess
import threading
import uuid
from flask import Flask, request

from telegram import Bot, Update
from telegram.ext import Dispatcher, MessageHandler, Filters
from telegram.utils.request import Request as TgRequest

# ---- Settings ----
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing")

MAX_SECONDS = int(os.environ.get("MAX_SECONDS", "900"))   # max download time (seconds)
MAX_MB = int(os.environ.get("MAX_MB", "200"))             # max file size to upload (MB)

# Increase Telegram request timeouts (helps big uploads)
tg_req = TgRequest(connect_timeout=20, read_timeout=20, con_pool_size=8)
bot = Bot(token=TOKEN, request=tg_req)

app = Flask(__name__)

# Keep workers low to avoid issues
dispatcher = Dispatcher(bot=bot, update_queue=None, workers=1, use_context=True)


def download_and_send(chat_id: int, url: str):
    out_path = f"/tmp/{uuid.uuid4().hex}.mp4"

    try:
        bot.send_message(chat_id, "⏳ Download started…")

        cmd = [
            "ffmpeg",
            "-y",
            "-nostdin",
            "-hide_banner",
            "-loglevel", "error",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-i", url,
            "-t", str(MAX_SECONDS),
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            out_path
        ]

        r = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=MAX_SECONDS + 60
        )

        if r.returncode != 0 or (not os.path.exists(out_path)) or os.path.getsize(out_path) == 0:
            err = r.stderr.decode("utf-8", "ignore") if isinstance(r.stderr, (bytes, bytearray)) else str(r.stderr)
            tail = "\n".join(err.splitlines()[-10:])
            bot.send_message(chat_id, "❌ Download failed.\nLast error:\n" + tail)
            return

        size_mb = os.path.getsize(out_path) / (1024 * 1024)

        bot.send_message(chat_id, f"✅ Download finished ({size_mb:.1f} MB).")

        # Size limit check (prevents Telegram upload timeouts)
        if size_mb > MAX_MB:
            bot.send_message(
                chat_id,
                f"❌ File too large ({size_mb:.1f} MB).\n"
                f"Limit is {MAX_MB} MB. Try a shorter link."
            )
            return

        bot.send_message(chat_id, "📤 Uploading…")

        with open(out_path, "rb") as f:
            bot.send_document(
                chat_id,
                document=f,
                filename="video.mp4",
                caption=f"✅ Done ({size_mb:.1f} MB)",
                timeout=600  # 10 minutes upload timeout
            )

    except subprocess.TimeoutExpired:
        bot.send_message(chat_id, "⏳ Timed out. Try a shorter link.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {e}")
    finally:
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass


def handle_message(update, context):
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id

    if not text.startswith("http") or ".m3u8" not in text.lower():
        update.message.reply_text("Send a valid .m3u8 link (non-DRM).")
        return

    update.message.reply_text("Downloading… please wait ✅")
    threading.Thread(target=download_and_send, args=(chat_id, text), daemon=True).start()


dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))


@app.route("/", methods=["GET"])
def health():
    return "OK"


@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), bot)
        dispatcher.process_update(update)
    except Exception as e:
        print("Webhook error:", e)
    return "OK"
