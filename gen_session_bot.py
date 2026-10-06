"""Bot generador de SESSION_STRING de Telegram."""
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired

GEN_BOT_TOKEN = "8415318453:AAGYqK6UD0fl5GX-RJMinoMVipSZwkNGo_A"
GEN_API_ID = 32471788
GEN_API_HASH = "cb57130abda56877acf3b3027e569450"

ALLOWED_USERS = {8282703640}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("gen_session_bot")

app = Client("gen_session_bot", api_id=GEN_API_ID, api_hash=GEN_API_HASH, bot_token=GEN_BOT_TOKEN)

sessions: dict[int, dict] = {}

def is_authorized(uid: int) -> bool:
    return uid in ALLOWED_USERS

async def cleanup_user(uid: int):
    state = sessions.pop(uid, None)
    if state and state.get("client"):
        try:
            await state["client"].disconnect()
        except Exception:
            pass

async def delete_msg_safe(msg: Message, delay: int = 0):
    if delay:
        await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass

@app.on_message(filters.command("start") & filters.private)
async def cmd_start(client, message: Message):
    uid = message.from_user.id
    if not is_authorized(uid):
        await message.reply_text("⛔ No autorizado.")
        return
    await cleanup_user(uid)
    await message.reply_text(
        "🔐 **Generador de SESSION_STRING**\n\n"
        "**Paso 1/4** — Envíame tu `api_id` (número).\n"
        "Obtenlo en https://my.telegram.org"
    )
    sessions[uid] = {"step": "api_id"}

@app.on_message(filters.command("cancel") & filters.private)
async def cmd_cancel(client, message: Message):
    uid = message.from_user.id
    await cleanup_user(uid)
    await message.reply_text("❌ Cancelado.")

@app.on_message(filters.private & filters.text & ~filters.command(["start", "cancel"]))
async def handle_text(client, message: Message):
    uid = message.from_user.id
    if not is_authorized(uid):
        return
    state = sessions.get(uid)
    if not state:
        await message.reply_text("Usa /start para comenzar.")
        return
    step = state.get("step")
    text = message.text.strip()

    if step == "api_id":
        if not text.isdigit():
            await message.reply_text("❌ Debe ser numérico.")
            return
        state["api_id"] = int(text)
        state["step"] = "api_hash"
        await message.reply_text("✅ **Paso 2/4** — Envíame tu `api_hash`.")
        return

    if step == "api_hash":
        if len(text) < 20:
            await message.reply_text("❌ `api_hash` inválido.")
            return
        state["api_hash"] = text
        state["step"] = "phone"
        await message.reply_text("✅ **Paso 3/4** — Envíame tu teléfono (ej: `+5350321300`).")
        return

    if step == "phone":
        if not text.startswith("+"):
            await message.reply_text("❌ Debe empezar con `+`.")
            return
        state["phone"] = text
        try:
            user_client = Client(f"gen_{uid}", api_id=state["api_id"], api_hash=state["api_hash"], in_memory=True)
            await user_client.connect()
            sent = await user_client.send_code(text)
            state["client"] = user_client
            state["phone_code_hash"] = sent.phone_code_hash
            state["step"] = "code"
            await message.reply_text("✅ **Paso 4/4** — Envíame el código SMS de 5 dígitos.")
        except Exception as e:
            await cleanup_user(uid)
            await message.reply_text(f"❌ Error: `{str(e)[:200]}`")
        return

    if step == "code":
        code = text.replace(" ", "").replace("-", "")
        asyncio.create_task(delete_msg_safe(message, 1))
        try:
            await state["client"].sign_in(state["phone"], state["phone_code_hash"], code)
            state["step"] = "done"
            await _send_session(uid, message)
        except SessionPasswordNeeded:
            state["step"] = "password"
            await message.reply_text("🔐 Tu cuenta tiene 2FA. Envíame la contraseña.")
        except PhoneCodeInvalid:
            await message.reply_text("❌ Código incorrecto.")
        except PhoneCodeExpired:
            await cleanup_user(uid)
            await message.reply_text("❌ Código expirado. Usa /start.")
        except Exception as e:
            await cleanup_user(uid)
            await message.reply_text(f"❌ Error: `{str(e)[:200]}`")
        return

    if step == "password":
        asyncio.create_task(delete_msg_safe(message, 1))
        try:
            await state["client"].check_password(text)
            state["step"] = "done"
            await _send_session(uid, message)
        except Exception as e:
            await message.reply_text(f"❌ Contraseña incorrecta: `{str(e)[:150]}`")
        return

async def _send_session(uid: int, message: Message):
    state = sessions.get(uid)
    if not state or not state.get("client"):
        await message.reply_text("❌ Sesión perdida.")
        return
    try:
        session_string = await state["client"].export_session_string()
        me = await state["client"].get_me()
        await state["client"].disconnect()
        sent_msg = await message.reply_text(
            f"✅ **Sesión generada**\n\n"
            f"👤 {me.first_name} (`{me.id}`)\n"
            f"📱 `{state['phone']}`\n\n"
            f"🔑 **SESSION_STRING:**\n\n`{session_string}`\n\n"
            f"⚠️ Se borra en 60s. Cópiala ya."
        )
        asyncio.create_task(delete_msg_safe(sent_msg, 60))
    except Exception as e:
        await message.reply_text(f"❌ Error: `{str(e)[:200]}`")
    finally:
        sessions.pop(uid, None)

if __name__ == "__main__":
    log.info("Bot generador arrancando...")
    app.run()
