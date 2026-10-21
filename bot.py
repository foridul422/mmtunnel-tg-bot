#!/usr/bin/env python3
"""
=============================================================================
  TELEGRAM VPN DECRYPTOR BOT (FOR RENDER DEPLOYMENT)
  Powered By : @Foridul_002 🇧🇩
=============================================================================
"""

import os
import io
import sys
import json
import base64
import datetime
import threading
import requests
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from argon2.low_level import hash_secret_raw, Type
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ================= CONFIGURATION =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

# Flask App for Render Health Check
app = Flask(__name__)

@app.route("/")
def health_check():
    return "✅ VPN Decryptor Bot is running 24/7 on Render!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# ================= DECRYPTION ENGINE =================
API_URL = "https://strongteam.co/api/mmtunnel/"
API_PAYLOAD = {"hash": "xsandokUpdatex"}

KEY_LAYER1 = b"iOi/hqT/TocUv0UbDImfWPGR1mfSdzzX"
KEY_LAYER2 = b"NewDecryptLibPassword"

ARGON2_TIME = 3
ARGON2_MEM = 16384
ARGON2_PARALLEL = 1
ARGON2_KEYLEN = 32


def decrypt_core(raw_bytes: bytes, password: bytes) -> bytes:
    if len(raw_bytes) < 28:
        raise ValueError("Payload too short")
    salt = raw_bytes[:16]
    nonce = raw_bytes[16:28]
    ciphertext = raw_bytes[28:]

    key = hash_secret_raw(
        secret=password,
        salt=salt,
        time_cost=ARGON2_TIME,
        memory_cost=ARGON2_MEM,
        parallelism=ARGON2_PARALLEL,
        hash_len=ARGON2_KEYLEN,
        type=Type.ID
    )
    return AESGCM(key).decrypt(nonce, ciphertext, salt)


def is_likely_encrypted(val: Any) -> bool:
    if not isinstance(val, str) or len(val) < 28:
        return False
    if any(c in val for c in [" ", "\n", "\r", "\t", "://", "<", ">", "[", "]", "@", "%", "&"]):
        return False
    try:
        raw = base64.b64decode(val)
        return len(raw) >= 28
    except Exception:
        return False


def decrypt_val(val: Any) -> str:
    if not is_likely_encrypted(val):
        return str(val) if val is not None else ""
    try:
        raw = base64.b64decode(val.strip())
        dec = decrypt_core(raw, KEY_LAYER2)
        return dec.decode("utf-8", errors="replace")
    except Exception:
        return val


def decrypt_mmtunnel_live() -> Dict[str, Any]:
    headers = {
        "User-Agent": "Go-http-client/1.1",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    resp = requests.post(API_URL, data=API_PAYLOAD, headers=headers, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Server returned status {resp.status_code}")
    
    resp_text = resp.text.strip()
    cleaned_b64 = resp_text[:3] + resp_text[4:]
    raw_payload = base64.b64decode(cleaned_b64)
    decrypted_bytes = decrypt_core(raw_payload, KEY_LAYER1)
    data = json.loads(decrypted_bytes.decode("utf-8"))

    # Decrypt Servers
    decrypted_servers = []
    for s in data.get("Servers", []):
        c = dict(s)
        for k in ["ServerIPHost", "OVPNUser", "OVPNPass", "CustomCertificate", "SlowDNSHost", "SlowDNSKey", "V2rayUUID", "UDP_obfs", "UDP_user"]:
            if k in c:
                c[k] = decrypt_val(c[k])
        decrypted_servers.append(c)

    # Decrypt Networks (clean dummy encrypted strings)
    decrypted_networks = []
    for n in data.get("Networks", []):
        c = dict(n)
        for k in ["Payload", "SNI", "V2rayConfig", "CustomProxy"]:
            if k in c and is_likely_encrypted(c[k]):
                c[k] = ""
        for k in ["V2rayAddress", "V2rayHost", "V2raySNI"]:
            if k in c and is_likely_encrypted(c[k]):
                c[k] = "[host]"
        decrypted_networks.append(c)

    full_output = {
        "CREDITS": [
            {
                "Owner": "Powered By @Foridul_002 🇧🇩",
                "Bot": "Decrypted By @Foridul_002 🤖",
                "User": "@Foridul_002 👤",
                "Date & Time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S ⏳")
            }
        ],
        "Version": data.get("Version", ""),
        "ReleaseNotes": data.get("ReleaseNotes", ""),
        "Telegram": data.get("Telegram", ""),
        "WhatsApp": data.get("WhatsApp", ""),
        "Facebook": data.get("Facebook", ""),
        "DefOVPNUser": data.get("DefOVPNUser", "sandoki"),
        "DefOVPNPass": data.get("DefOVPNPass", "sandoki"),
        "HysteriaUser": data.get("HysteriaUser", ""),
        "HysteriaOBFS": data.get("HysteriaOBFS", ""),
        "DefaultOVPNCert": data.get("DefaultOVPNCert", ""),
        "isTimerOn": data.get("isTimerOn", False),
        "timetoadd": data.get("timetoadd", 0),
        "Servers": decrypted_servers,
        "Networks": decrypted_networks
    }
    return full_output


# ================= TELEGRAM BOT LOGIC =================
def start_bot():
    if not BOT_TOKEN:
        print("[!] ERROR: BOT_TOKEN is missing! Set BOT_TOKEN environment variable.", file=sys.stderr)
        return

    bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

    @bot.message_handler(commands=["start", "help"])
    def handle_start(message):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌐 VPN List", callback_data="vpn_list"))
        
        user_name = message.from_user.first_name or "User"
        welcome_text = (
            f"👋 <b>Welcome {user_name}!</b>\n\n"
            "🤖 <b>VPN Config Decryptor Bot</b>\n"
            "<i>Powered by: @Foridul_002 🇧🇩</i>\n\n"
            "নিচের <b>'VPN List'</b> বাটনে ক্লিক করে VPN নির্বাচন করুন:"
        )
        bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callbacks(call):
        chat_id = call.message.chat.id
        msg_id = call.message.message_id

        if call.data == "vpn_list":
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(
                InlineKeyboardButton("🛡️ MM Tunnel VPN", callback_data="dec_mmtunnel"),
                InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_main")
            )
            bot.edit_message_text(
                "📋 <b>Available VPN List:</b>\n\nযে VPN-এর কনফিগ ডিক্রিপ্ট করতে চান তা সিলেক্ট করুন:",
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=markup
            )

        elif call.data == "back_main":
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🌐 VPN List", callback_data="vpn_list"))
            bot.edit_message_text(
                "🤖 <b>Main Menu</b>\n\nনিচের <b>'VPN List'</b> বাটনে ক্লিক করুন:",
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=markup
            )

        elif call.data == "dec_mmtunnel":
            bot.answer_callback_query(call.id, "⏳ Fetching & Decrypting MM Tunnel Live Config...")
            
            # Send loading message
            status_msg = bot.send_message(
                chat_id, 
                "⏳ <b>MM Tunnel লাইভ ডাটা ডিক্রিপ্ট করা হচ্ছে...</b>\nঅনুগ্রহ করে কয়েক সেকেন্ড অপেক্ষা করুন।"
            )

            try:
                decrypted_data = decrypt_mmtunnel_live()
                formatted_txt = json.dumps(decrypted_data, indent=4, ensure_ascii=False)

                # Convert text to in-memory file for sending
                txt_bytes = io.BytesIO(formatted_txt.encode("utf-8"))
                txt_bytes.name = "MM_Tunnel_Decrypted.txt"

                version = decrypted_data.get("Version", "N/A")
                notes = decrypted_data.get("ReleaseNotes", "N/A")
                servers_count = len(decrypted_data.get("Servers", []))
                networks_count = len(decrypted_data.get("Networks", []))
                ovpn_user = decrypted_data.get("DefOVPNUser", "sandoki")
                ovpn_pass = decrypted_data.get("DefOVPNPass", "sandoki")

                caption = (
                    "✅ <b>MM Tunnel 100% Decrypted Successfully!</b>\n\n"
                    f"📦 <b>Version:</b> <code>{version}</code>\n"
                    f"📝 <b>Release Notes:</b> {notes}\n"
                    f"🔐 <b>Def OpenVPN User:</b> <code>{ovpn_user}</code>\n"
                    f"🔑 <b>Def OpenVPN Pass:</b> <code>{ovpn_pass}</code>\n"
                    f"🌐 <b>Total Servers:</b> <code>{servers_count}</code>\n"
                    f"📡 <b>Total Networks:</b> <code>{networks_count}</code>\n\n"
                    "🤖 <b>Decrypted By:</b> @Foridul_002 🇧🇩"
                )

                # Send .txt file document
                bot.send_document(
                    chat_id,
                    txt_bytes,
                    caption=caption
                )
                bot.delete_message(chat_id, status_msg.message_id)

            except Exception as e:
                bot.edit_message_text(
                    f"❌ <b>Decryption Failed!</b>\nError: <code>{e}</code>",
                    chat_id=chat_id,
                    message_id=status_msg.message_id
                )

    print("[*] Starting Telegram Bot polling...")
    bot.infinity_polling()


# ================= ENTRYPOINT =================
if __name__ == "__main__":
    # Start Flask background server for Render
    threading.Thread(target=run_flask, daemon=True).start()
    # Start Bot
    start_bot()
