#!/usr/bin/env python3
"""
=============================================================================
  TELEGRAM VPN DECRYPTOR BOT (FOR RENDER DEPLOYMENT)
  By         : @Foridul_002 🇧🇩
  Version    : 4.1 (HTTP Custom .hc + Dark Tunnel .dark + HTTP Injector .ehi + NapsternetV .npv + 8 Live VPNs)
=============================================================================
"""

import os
import io
import sys
import time
import json
import re
import base64
import struct
import datetime
import threading
import urllib.parse
import urllib.request
import hmac
import random
import requests
import yaml
import hashlib
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= CONFIGURATION =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5802122865"))

# Flask App for Render Health Check
app = Flask(__name__)

@app.route("/")
def health_check():
    return "✅ VPN Decryptor Bot (v4.1 - HTTP Custom .hc, Dark Tunnel .dark, HTTP Injector .ehi, NapsternetV .npv Decryptors & Admin Reporting Active) is running 24/7 on Render!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive_worker():
    """Pings Render URL every 8 minutes to prevent free tier spin-down"""
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "https://mmtunnel-tg-bot.onrender.com")
    time.sleep(30)
    while True:
        try:
            requests.get(render_url, timeout=10)
        except Exception:
            pass
        time.sleep(480)  # Ping every 8 mins to keep free instance active


# ================= VPN DECRYPTION ENGINES =================
from engine_mmtunnel import decrypt_mmtunnel_live, decrypt_terix_live, TERIX_USER
from engine_ursanet import decrypt_ursa_live, decrypt_vipsniper_pro
from engine_sensei_izph import decrypt_sensei_tunnel_live, decrypt_izph_vpn_pro_live
from engine_iptunnel import decrypt_iptunnel_live
from boost_vpn import decrypt_boost_vpn_live
from engine_httpcustom import decrypt_hc_file
from engine_darktunnel import decrypt_dark_file
from engine_httpinjector import decrypt_ehi_file
from engine_npv import decrypt_npv_file


# ================= ADMIN AUDIT & REPORTING SYSTEM =================
def html_escape(text: Any) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def send_admin_report_async(bot: telebot.TeleBot, user: Any, action_name: str, status: str, details: str = ""):
    """
    Sends audit report to Admin ID asynchronously without blocking user requests.
    Tracks user details, app being decrypted, success/failure status, and BST timestamp.
    """
    def _worker():
        try:
            if not ADMIN_ID:
                return

            # Timestamp in BST (Bangladesh Standard Time, UTC+6)
            utc_now = datetime.datetime.now(datetime.timezone.utc)
            bst_now = utc_now + datetime.timedelta(hours=6)
            timestamp_str = bst_now.strftime("%Y-%m-%d %I:%M:%S %p")

            user_id = getattr(user, "id", "Unknown") if user else "Unknown"
            first_name = getattr(user, "first_name", "") if user else ""
            last_name = getattr(user, "last_name", "") if user else ""
            full_name = f"{first_name or ''} {last_name or ''}".strip() or "Unknown User"
            username = f"@{user.username}" if (user and getattr(user, "username", None)) else "None"

            is_success = (status.upper() == "SUCCESS")
            status_text = "✅ SUCCESS" if is_success else "❌ FAILED" if status.upper() == "FAILED" else f"ℹ️ {status}"

            role_tag = "👑 [ADMIN]" if str(user_id) == str(ADMIN_ID) else "👤 [USER]"

            report_msg = (
                f"🚨 <b>ACTIVITY AUDIT REPORT</b> {role_tag}\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Name:</b> {html_escape(full_name)}\n"
                f"🏷️ <b>Username:</b> {html_escape(username)}\n"
                f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
                f"🔗 <b>Profile:</b> <a href=\"tg://user?id={user_id}\">Direct Profile Link</a>\n"
                "────────────────────\n"
                f"📱 <b>Target App:</b> <b>{html_escape(action_name)}</b>\n"
                f"📊 <b>Result:</b> <b>{status_text}</b>\n"
            )
            if details:
                safe_details = html_escape(str(details)[:2500])
                report_msg += f"📋 <b>Details:</b>\n<code>{safe_details}</code>\n"

            report_msg += (
                "────────────────────\n"
                f"⏰ <b>Time (BST):</b> <code>{timestamp_str}</code>\n"
                "━━━━━━━━━━━━━━━━━━━━"
            )

            bot.send_message(ADMIN_ID, report_msg, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as e:
            print(f"[!] Failed to deliver admin report to {ADMIN_ID}: {e}", file=sys.stderr)

    threading.Thread(target=_worker, daemon=True).start()


def get_welcome_text(user: Any) -> str:
    user_name = getattr(user, "first_name", "") or "User"
    user_id = getattr(user, "id", "Unknown")
    return (
        "🌸 <b>VPN DECRYPTOR PRO</b> 🪄\n"
        f"<blockquote>👤 <b>User:</b> {html_escape(user_name)}\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        "⚡ <b>Engine:</b> <code>v4.2 Active 🟢</code></blockquote>\n\n"
        "📖 <b>Supported Files:</b> <code>.hc</code> • <code>.dark</code> • <code>.ehi</code> • <code>.npv</code>\n"
        "✨ <b>Select a Server or Cloud VPN:</b>"
    )


def get_vpn_markup() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    # Row 1: File Decryptors (3 Columns - Primary Deep Blue)
    markup.row(
        InlineKeyboardButton("📁 Custom", callback_data="dec_httpcustom", style="primary"),
        InlineKeyboardButton("🌑 Dark", callback_data="dec_darktunnel", style="primary"),
        InlineKeyboardButton("💉 Injector", callback_data="dec_httpinjector", style="primary")
    )
    # Row 2: File Decryptor + Live VPNs (3 Columns - Primary Deep Blue)
    markup.row(
        InlineKeyboardButton("⚡ Napster", callback_data="dec_npv", style="primary"),
        InlineKeyboardButton("🛡️ MMTunnel", callback_data="dec_mmtunnel", style="primary"),
        InlineKeyboardButton("💎 TeriX", callback_data="dec_terix", style="primary")
    )
    # Row 3: Live OTA Cloud VPNs (3 Columns - Primary Deep Blue)
    markup.row(
        InlineKeyboardButton("🐻 Ursa Net", callback_data="dec_ursanet", style="primary"),
        InlineKeyboardButton("🎯 VIPSniper", callback_data="dec_vipsniper", style="primary"),
        InlineKeyboardButton("🥋 Sensei", callback_data="dec_sensei", style="primary")
    )
    # Row 4: Live OTA Cloud VPNs (3 Columns - Primary Deep Blue)
    markup.row(
        InlineKeyboardButton("🛡️ IZPH Pro", callback_data="dec_izph", style="primary"),
        InlineKeyboardButton("🚀 IPTunnel", callback_data="dec_iptunnel", style="primary"),
        InlineKeyboardButton("⚡ BoostVPN", callback_data="dec_boostvpn", style="primary")
    )
    # Row 5: Action Controls Bar (3 Columns - Blue, Green, Red)
    markup.row(
        InlineKeyboardButton("👑 Admin", callback_data="btn_admin", style="primary"),
        InlineKeyboardButton("🔄 Refresh", callback_data="btn_refresh", style="success"),
        InlineKeyboardButton("❌ Close", callback_data="btn_close", style="danger")
    )
    return markup


# ================= TELEGRAM BOT LOGIC =================
def start_bot():
    if not BOT_TOKEN:
        print("[!] ERROR: BOT_TOKEN is missing! Set BOT_TOKEN environment variable.", file=sys.stderr)
        return

    bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

    @bot.message_handler(commands=["start", "help"])
    def handle_start(message):
        send_admin_report_async(bot, message.from_user, "Bot Menu (/start)", "SUCCESS", details="User accessed main menu")
        markup = get_vpn_markup()
        welcome_text = get_welcome_text(message.from_user)
        bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

    @bot.message_handler(commands=["admin"])
    def handle_admin(message):
        if str(message.from_user.id) == str(ADMIN_ID):
            send_admin_report_async(bot, message.from_user, "Admin Panel (/admin)", "SUCCESS", details="Admin checked bot status")
            bot.reply_to(
                message,
                f"👑 <b>Admin Control Panel</b>\n\n"
                f"<blockquote>🆔 <b>Admin ID:</b> <code>{ADMIN_ID}</code>\n"
                f"📊 <b>Audit Reports:</b> <code>ACTIVE ✅</code>\n"
                f"⚡ <b>Engine Version:</b> <code>v4.2 (Full Decryptors + UI Grid Active)</code>\n"
                f"🌍 <b>Timezone:</b> <code>Asia/Dhaka (BST, UTC+6)</code></blockquote>\n\n"
                f"<i>All bot usage, user decryptions, successes & failures are sent to this chat in real time!</i>"
            )
        else:
            send_admin_report_async(bot, message.from_user, "Unauthorized Admin Access (/admin)", "FAILED", details=f"Unauthorized attempt by ID {message.from_user.id}")
            bot.reply_to(message, "⛔ <b>Access Denied:</b> This command is restricted to the Bot Administrator.")

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callbacks(call):
        chat_id = call.message.chat.id
        msg_id = call.message.message_id

        if call.data == "vpn_list":
            markup = get_vpn_markup()
            welcome_text = get_welcome_text(call.from_user)
            bot.edit_message_text(
                welcome_text,
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=markup
            )

        elif call.data == "back_main":
            markup = get_vpn_markup()
            welcome_text = get_welcome_text(call.from_user)
            bot.edit_message_text(
                welcome_text,
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=markup
            )

        elif call.data == "dec_httpcustom":
            bot.answer_callback_query(call.id, "📁 HTTP Custom (.hc) File Decryptor")
            info_text = (
                "📁 <b>HTTP Custom (.hc) Config Decryptor</b>\n\n"
                "ℹ️ <i>HTTP Custom uses custom encrypted <code>.hc</code> configuration files.</i>\n\n"
                "📤 <b>How to Decrypt:</b>\n"
                "Simply <b>send or forward</b> any <code>.hc</code> file directly to this chat!\n\n"
                "⚡ <b>The bot will automatically:</b>\n"
                "  • Break XChaCha20-Poly1305 + HKDF native crypto\n"
                "  • Unpack binary HPC1 profiles & containers\n"
                "  • Extract Host, Port, V2Ray UUID, SSH Passwords & SNI\n"
                "  • Extract hidden HTTP Payloads & WS Headers\n"
                "  • Deliver clean, copyable credentials and ready links!\n\n"
                "🤖 <b>By:</b> @Foridul_002 🇧🇩"
            )
            bot.send_message(chat_id, info_text)

        elif call.data == "dec_darktunnel":
            bot.answer_callback_query(call.id, "📁 Dark Tunnel (.dark) File Decryptor")
            info_text = (
                "📁 <b>Dark Tunnel (.dark) Config Decryptor</b>\n\n"
                "ℹ️ <i>Dark Tunnel uses custom encrypted <code>.dark</code> configuration files (AES-CFB + MsgPack).</i>\n\n"
                "📤 <b>How to Decrypt:</b>\n"
                "Simply <b>send or forward</b> any <code>.dark</code> file directly to this chat!\n\n"
                "⚡ <b>The bot will automatically:</b>\n"
                "  • Break 2-Layer AES-CFB (256-bit + 192-bit) crypto\n"
                "  • Unpack binary MsgPack containers & V2Ray outbounds\n"
                "  • Extract VLESS / VMess / Trojan / SSH credentials\n"
                "  • Extract hidden Payloads, SNI, WS paths & Proxies\n"
                "  • Generate instant 1-click importable ready links!\n\n"
                "🤖 <b>By:</b> @Foridul_002 🇧🇩"
            )
            bot.send_message(chat_id, info_text)

        elif call.data == "dec_httpinjector":
            bot.answer_callback_query(call.id, "📁 HTTP Injector (.ehi) File Decryptor")
            info_text = (
                "📁 <b>HTTP Injector (.ehi) Config Decryptor</b>\n\n"
                "ℹ️ <i>HTTP Injector uses multi-layer encrypted <code>.ehi</code> configuration files.</i>\n\n"
                "📤 <b>How to Decrypt:</b>\n"
                "Simply <b>send or forward</b> any <code>.ehi</code> file directly to this chat!\n\n"
                "⚡ <b>The bot will automatically:</b>\n"
                "  • Break Layer 1 & Layer 2 AES-CBC + XXTEA crypto\n"
                "  • Reverse Argon2id KDF + ChaCha20-Poly1305\n"
                "  • Decode custom alphabet Base64 + XOR salt translation\n"
                "  • Extract SSH, DNSTT, V2Ray credentials & Payloads\n"
                "  • Generate instant 1-click copyable links & configs!\n\n"
                "🤖 <b>By:</b> @Foridul_002 🇧🇩"
            )
            bot.send_message(chat_id, info_text)

        elif call.data == "dec_npv":
            bot.answer_callback_query(call.id, "📁 NapsternetV (NPV) File Decryptor")
            info_text = (
                "📁 <b>NapsternetV (.npv / .npvt / .npvs / .npv4) Decryptor</b>\n\n"
                "ℹ️ <i>NapsternetV uses custom whitebox AES encrypted configuration containers.</i>\n\n"
                "📤 <b>How to Decrypt:</b>\n"
                "Simply <b>send or forward</b> any <code>.npv</code>, <code>.npvt</code>, <code>.npvs</code>, or <code>.npv4</code> file directly to this chat!\n\n"
                "⚡ <b>The bot will automatically:</b>\n"
                "  • Break custom Whitebox AES cipher & state tables\n"
                "  • Unpack V2Ray profiles (VLESS, VMess, Trojan, Shadowsocks)\n"
                "  • Extract SSH credentials, SNI, HTTP Proxy & Payloads\n"
                "  • Reveal locked passwords, expiration dates & creator notes\n"
                "  • Generate instant 1-click importable ready links!\n\n"
                "🤖 <b>By:</b> @Foridul_002 🇧🇩"
            )
            bot.send_message(chat_id, info_text)

        elif call.data == "btn_close":
            bot.answer_callback_query(call.id, "Menu Closed ❌")
            try:
                bot.delete_message(chat_id, msg_id)
            except Exception:
                pass

        elif call.data == "btn_refresh":
            bot.answer_callback_query(call.id, "Menu Refreshed 🔄")
            markup = get_vpn_markup()
            welcome_text = get_welcome_text(call.from_user)
            try:
                bot.edit_message_text(
                    welcome_text,
                    chat_id=chat_id,
                    message_id=msg_id,
                    reply_markup=markup
                )
            except Exception:
                pass

        elif call.data == "btn_admin":
            if str(call.from_user.id) == str(ADMIN_ID):
                bot.answer_callback_query(call.id, "👑 Welcome Admin!")
                bot.send_message(
                    chat_id,
                    f"👑 <b>Admin Control Panel</b>\n\n"
                    f"🆔 <b>Admin ID:</b> <code>{ADMIN_ID}</code>\n"
                    f"📊 <b>Audit Reports:</b> <code>ACTIVE ✅</code>\n"
                    f"⚡ <b>Engine Version:</b> <code>v4.2 (Full Decryptors + UI Grid Active)</code>\n"
                    f"🌍 <b>Timezone:</b> <code>Asia/Dhaka (BST, UTC+6)</code>"
                )
            else:
                bot.answer_callback_query(call.id, "⛔ Restrict: Admin Only!", show_alert=True)

        elif call.data == "dec_mmtunnel":
            bot.answer_callback_query(call.id, "⏳ Fetching & Decrypting MM Tunnel Config...")
            status_msg = bot.send_message(chat_id, "⏳ <b>Decrypting MM Tunnel live data...</b>\nPlease wait a few seconds.")

            try:
                decrypted_data = decrypt_mmtunnel_live()
                formatted_txt = json.dumps(decrypted_data, indent=4, ensure_ascii=False)
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
                    f"🔐 <b>OpenVPN User:</b> <code>{ovpn_user}</code>\n"
                    f"🔑 <b>OpenVPN Pass:</b> <code>{ovpn_pass}</code>\n"
                    f"🌐 <b>Total Servers:</b> <code>{servers_count}</code>\n"
                    f"📡 <b>Total Networks:</b> <code>{networks_count}</code>\n\n"
                    "🤖 <b>By:</b> @Foridul_002 🇧🇩"
                )

                bot.send_document(chat_id, txt_bytes, caption=caption)
                bot.delete_message(chat_id, status_msg.message_id)

                details = f"Version: {version}\nServers: {servers_count}\nNetworks: {networks_count}\nNotes: {notes}"
                send_admin_report_async(bot, call.from_user, "MM Tunnel VPN", "SUCCESS", details=details)

            except Exception as e:
                bot.edit_message_text(
                    f"❌ <b>Decryption Failed!</b>\nError: <code>{e}</code>",
                    chat_id=chat_id,
                    message_id=status_msg.message_id
                )
                send_admin_report_async(bot, call.from_user, "MM Tunnel VPN", "FAILED", details=str(e))

        elif call.data == "dec_terix":
            bot.answer_callback_query(call.id, "⏳ Fetching & Decrypting TeriX VPN Config...")
            status_msg = bot.send_message(chat_id, "⏳ <b>Fetching & decrypting TeriX VPN live data...</b>\nPlease wait a few seconds.")

            try:
                res = decrypt_terix_live()
                txt_bytes = io.BytesIO(res["txt_content"].encode("utf-8"))
                txt_bytes.name = "TeriX_Decrypted.txt"

                total_proxies = res["total_proxies"]
                plan = res["plan"].title()
                status = res["status"].title()

                caption = (
                    "✅ <b>TeriX VPN 100% Decrypted Successfully!</b>\n\n"
                    f"👤 <b>Account:</b> <code>{TERIX_USER}</code>\n"
                    f"💎 <b>Plan:</b> {plan} ({status})\n"
                    f"🌐 <b>Total Proxy Servers:</b> <code>{total_proxies}</code>\n\n"
                    "📁 <i>Full raw decrypted Clash YAML attached in file.</i>\n\n"
                    "🤖 <b>By:</b> @Foridul_002 🇧🇩"
                )

                bot.send_document(chat_id, txt_bytes, caption=caption)
                bot.delete_message(chat_id, status_msg.message_id)

                details = f"Account: {TERIX_USER}\nPlan: {plan} ({status})\nTotal Proxies: {total_proxies}"
                send_admin_report_async(bot, call.from_user, "TeriX VPN", "SUCCESS", details=details)

            except Exception as e:
                bot.edit_message_text(
                    f"❌ <b>TeriX Decryption Failed!</b>\nError: <code>{e}</code>",
                    chat_id=chat_id,
                    message_id=status_msg.message_id
                )
                send_admin_report_async(bot, call.from_user, "TeriX VPN", "FAILED", details=str(e))

        elif call.data == "dec_ursanet":
            bot.answer_callback_query(call.id, "⏳ Fetching & Decrypting Ursa Net PRO Config...")
            status_msg = bot.send_message(chat_id, "⏳ <b>Decrypting Ursa Net PRO live data...</b>\nPlease wait a few seconds.")

            try:
                res = decrypt_ursa_live()
                raw_txt = res["raw_txt"]
                version = res["version"]
                total_servers = res["total_servers"]
                total_payloads = res["total_payloads"]

                txt_bytes = io.BytesIO(raw_txt.encode("utf-8"))
                txt_bytes.name = "Ursa_Net_PRO_Decrypted.txt"

                caption = (
                    "✅ <b>Ursa Net PRO 100% Fully Decrypted!</b>\n\n"
                    f"📦 <b>Config Version:</b> <code>{version}</code>\n"
                    f"🌐 <b>Total Servers:</b> <code>{total_servers}</code>\n"
                    f"📡 <b>Total Payloads:</b> <code>{total_payloads}</code>\n\n"
                    "📁 <i>All decrypted data attached in TXT file without filtering.</i>\n\n"
                    "🤖 <b>By:</b> @Foridul_002 🇧🇩"
                )

                bot.send_document(chat_id, txt_bytes, caption=caption)
                bot.delete_message(chat_id, status_msg.message_id)

                details = f"Config Version: {version}\nTotal Servers: {total_servers}\nTotal Payloads: {total_payloads}"
                send_admin_report_async(bot, call.from_user, "Ursa Net PRO", "SUCCESS", details=details)

            except Exception as e:
                bot.edit_message_text(
                    f"❌ <b>Ursa Net PRO Decryption Failed!</b>\nError: <code>{e}</code>",
                    chat_id=chat_id,
                    message_id=status_msg.message_id
                )
                send_admin_report_async(bot, call.from_user, "Ursa Net PRO", "FAILED", details=str(e))

        elif call.data == "dec_vipsniper":
            bot.answer_callback_query(call.id, "⏳ Decrypting VIP Sniper Pro Config...")
            status_msg = bot.send_message(
                chat_id,
                "⏳ <b>Decrypting VIP Sniper Pro...</b>\n"
                "🔐 Breaking 3-Layer Crypto (XXTEA + Threefish-256 + AES)...\n"
                "Please wait a few seconds."
            )

            try:
                res = decrypt_vipsniper_pro()
                txt_bytes = io.BytesIO(res["txt_content"].encode("utf-8"))
                txt_bytes.name = "VIP_Sniper_Pro_Decrypted.txt"

                version = res["version"]
                total_servers = res["total_servers"]
                total_networks = res["total_networks"]
                glob_user = res["glob_user"]
                glob_pass = res["glob_pass"]

                caption = (
                    "✅ <b>VIP Sniper Pro 100% Fully Decrypted!</b>\n\n"
                    f"📦 <b>Version:</b> <code>{version}</code>\n"
                    f"🔐 <b>Username:</b> <code>{glob_user}</code>\n"
                    f"🔑 <b>Password:</b> <code>{glob_pass}</code>\n"
                    f"🌐 <b>Total Servers:</b> <code>{total_servers}</code>\n"
                    f"📡 <b>Total Networks:</b> <code>{total_networks}</code>\n\n"
                    "📁 <i>Complete decrypted raw database attached in file.</i>\n\n"
                    "🤖 <b>By:</b> @Foridul_002 🇧🇩"
                )

                bot.send_document(chat_id, txt_bytes, caption=caption)
                bot.delete_message(chat_id, status_msg.message_id)

                details = f"Version: {version}\nServers: {total_servers}\nNetworks: {total_networks}\nUser: {glob_user}"
                send_admin_report_async(bot, call.from_user, "VIP Sniper Pro", "SUCCESS", details=details)

            except Exception as e:
                bot.edit_message_text(
                    f"❌ <b>VIP Sniper Pro Decryption Failed!</b>\nError: <code>{e}</code>",
                    chat_id=chat_id,
                    message_id=status_msg.message_id
                )
                send_admin_report_async(bot, call.from_user, "VIP Sniper Pro", "FAILED", details=str(e))

        elif call.data == "dec_sensei":
            bot.answer_callback_query(call.id, "⏳ Decrypting Sensei Tunnel Live Config...")
            status_msg = bot.send_message(
                chat_id,
                "⏳ <b>Fetching & Decrypting Sensei Tunnel...</b>\n"
                "📡 Connecting to Live GitHub API Repository...\n"
                "🔐 Breaking v3 Native JNI Crypto (AES-256-GCM + Cert-Bound Key)...\n"
                "Please wait a few seconds."
            )

            try:
                res = decrypt_sensei_tunnel_live()
                txt_bytes = io.BytesIO(res["txt_content"].encode("utf-8"))
                txt_bytes.name = "Sensei_Tunnel_Live_Decrypted.txt"

                total_configs = res["total_configs"]
                total_servers = res["total_servers"]

                caption = (
                    "✅ <b>Sensei Tunnel 100% Fully Decrypted!</b>\n\n"
                    f"🌐 <b>Total Live Configs:</b> <code>{total_configs}</code>\n"
                    f"🖥️ <b>Cluster Servers:</b> <code>{total_servers}</code>\n"
                    "⚡ <b>Filter:</b> <code>NONE (100% Raw Live API Data)</code>\n\n"
                    "📁 <i>Complete decrypted raw database attached in file.</i>\n\n"
                    "🤖 <b>By:</b> @Foridul_002 🇧🇩"
                )

                bot.send_document(chat_id, txt_bytes, caption=caption)
                bot.delete_message(chat_id, status_msg.message_id)

                details = f"Configs: {total_configs}\nCluster Servers: {total_servers}\nCrypto: Native JNI AES-256-GCM"
                send_admin_report_async(bot, call.from_user, "Sensei Tunnel (Live)", "SUCCESS", details=details)

            except Exception as e:
                bot.edit_message_text(
                    f"❌ <b>Sensei Tunnel Decryption Failed!</b>\nError: <code>{e}</code>",
                    chat_id=chat_id,
                    message_id=status_msg.message_id
                )
                send_admin_report_async(bot, call.from_user, "Sensei Tunnel (Live)", "FAILED", details=str(e))

        elif call.data == "dec_izph":
            bot.answer_callback_query(call.id, "⏳ Decrypting IZPH VPN PRO Config...")
            status_msg = bot.send_message(
                chat_id,
                "⏳ <b>Fetching & Decrypting IZPH VPN PRO...</b>\n"
                "📡 Connecting to Live GitHub API Repository (kiranoble/config)...\n"
                "🔐 Breaking 3-Layer Native Crypto (Threefish-256 + XXTEA + AES-128-CBC)...\n"
                "Please wait a few seconds."
            )

            try:
                res = decrypt_izph_vpn_pro_live()
                txt_bytes = io.BytesIO(res["txt_content"].encode("utf-8"))
                txt_bytes.name = "IZPH_VPN_PRO_Live_Decrypted.txt"

                version = res["version"]
                glob_user = res["glob_user"]
                glob_pass = res["glob_pass"]
                total_servers = res["total_servers"]
                total_networks = res["total_networks"]

                caption = (
                    "✅ <b>IZPH VPN PRO 100% Fully Decrypted!</b>\n\n"
                    f"📦 <b>Version:</b> <code>{version}</code>\n"
                    f"🔐 <b>Username:</b> <code>{glob_user}</code>\n"
                    f"🔑 <b>Password:</b> <code>{glob_pass}</code>\n"
                    f"🌐 <b>Total Servers:</b> <code>{total_servers}</code>\n"
                    f"📡 <b>Total Networks:</b> <code>{total_networks}</code>\n"
                    "⚡ <b>Filter:</b> <code>NONE (100% Raw Live API Data)</code>\n\n"
                    "📁 <i>Complete decrypted raw database attached in file.</i>\n\n"
                    "🤖 <b>By:</b> @Foridul_002 🇧🇩"
                )

                bot.send_document(chat_id, txt_bytes, caption=caption)
                bot.delete_message(chat_id, status_msg.message_id)

                details = f"Version: {version}\nServers: {total_servers}\nNetworks: {total_networks}\nUser: {glob_user}"
                send_admin_report_async(bot, call.from_user, "IZPH VPN PRO (Live)", "SUCCESS", details=details)

            except Exception as e:
                bot.edit_message_text(
                    f"❌ <b>IZPH VPN PRO Decryption Failed!</b>\nError: <code>{e}</code>",
                    chat_id=chat_id,
                    message_id=status_msg.message_id
                )
                send_admin_report_async(bot, call.from_user, "IZPH VPN PRO (Live)", "FAILED", details=str(e))

        elif call.data == "dec_iptunnel":
            bot.answer_callback_query(call.id, "⏳ Decrypting IPTunnel Config...")
            status_msg = bot.send_message(
                chat_id,
                "⏳ <b>Fetching & Decrypting IPTunnel - Alpha...</b>\n"
                "📡 Connecting to Live Backend API...\n"
                "🔐 Reversing HMAC-SHA256 signature & XXTEA delta-cipher...\n"
                "Please wait a few seconds."
            )

            try:
                res = decrypt_iptunnel_live()
                txt_bytes = io.BytesIO(res["txt_content"].encode("utf-8"))
                txt_bytes.name = "IPTunnel_Decrypted.txt"

                version = res["version"]
                total_servers = res["total_servers"]
                total_tweaks = res["total_tweaks"]

                caption = (
                    "✅ <b>IPTunnel - Alpha 100% Fully Decrypted!</b>\n\n"
                    f"📦 <b>Config Version:</b> <code>{version}</code>\n"
                    f"🌐 <b>Total Servers:</b> <code>{total_servers}</code>\n"
                    f"📡 <b>Total Tweaks / Payloads:</b> <code>{total_tweaks}</code>\n"
                    "⚡ <b>Filter:</b> <code>NONE (100% Raw Live API Data)</code>\n\n"
                    "📁 <i>Complete decrypted raw database attached in file.</i>\n\n"
                    "🤖 <b>By:</b> @Foridul_002 🇧🇩"
                )

                bot.send_document(chat_id, txt_bytes, caption=caption)
                bot.delete_message(chat_id, status_msg.message_id)

                details = f"Version: {version}\nServers: {total_servers}\nTweaks/Payloads: {total_tweaks}"
                send_admin_report_async(bot, call.from_user, "IPTunnel - Alpha (Live)", "SUCCESS", details=details)

            except Exception as e:
                bot.edit_message_text(
                    f"❌ <b>IPTunnel Decryption Failed!</b>\nError: <code>{e}</code>",
                    chat_id=chat_id,
                    message_id=status_msg.message_id
                )
                send_admin_report_async(bot, call.from_user, "IPTunnel - Alpha (Live)", "FAILED", details=str(e))

        elif call.data == "dec_boostvpn":
            bot.answer_callback_query(call.id, "⏳ Decrypting Boost VPN Config...")
            status_msg = bot.send_message(
                chat_id,
                "⏳ <b>Fetching & Decrypting Boost VPN...</b>\n"
                "📡 Connecting to Live GitHub Config (doneeone7/first)...\n"
                "🔐 Reversing XxTea (Delta 772515655) & Double Char Shift (4669)...\n"
                "🔓 Recursively decrypting nested server IPs, credentials & payloads...\n"
                "Please wait a few seconds."
            )

            try:
                res = decrypt_boost_vpn_live()
                txt_bytes = io.BytesIO(res["txt_content"].encode("utf-8"))
                txt_bytes.name = "BoostVPN_Decrypted.txt"

                version = res["version"]
                total_servers = res.get("total_servers", 0)
                total_http = res.get("total_http_networks", res.get("total_http", 0))
                total_ssl = res.get("total_ssl_networks", res.get("total_ssl", 0))

                caption = (
                    "✅ <b>Boost VPN 100% Fully Decrypted!</b>\n\n"
                    f"📦 <b>Config Version:</b> <code>{version}</code>\n"
                    f"🌐 <b>Total Servers:</b> <code>{total_servers}</code>\n"
                    f"📡 <b>HTTP Networks:</b> <code>{total_http}</code>\n"
                    f"🔒 <b>SSL Networks:</b> <code>{total_ssl}</code>\n"
                    "⚡ <b>Filter:</b> <code>NONE (100% Raw Decrypted Data)</code>\n\n"
                    "👑 <b>By: @Foridul_002 🇧🇩</b>"
                )

                bot.send_document(chat_id, txt_bytes, caption=caption)
                bot.delete_message(chat_id, status_msg.message_id)

                details = f"Version: {version}\nServers: {total_servers}\nHTTP Networks: {total_http}\nSSL Networks: {total_ssl}"
                send_admin_report_async(bot, call.from_user, "Boost VPN (Live)", "SUCCESS", details=details)

            except Exception as e:
                bot.edit_message_text(
                    f"❌ <b>Boost VPN Decryption Failed!</b>\nError: <code>{e}</code>",
                    chat_id=chat_id,
                    message_id=status_msg.message_id
                )
                send_admin_report_async(bot, call.from_user, "Boost VPN (Live)", "FAILED", details=str(e))

    # ================= INCOMING DOCUMENT / FILE HANDLER =================
    @bot.message_handler(content_types=["document"])
    def handle_incoming_document(message):
        chat_id = message.chat.id
        doc = message.document
        file_name = doc.file_name or "config"
        ext = os.path.splitext(file_name.lower())[1]

        # Supported extensions
        npv_extensions = [".npv", ".npvt", ".npvs", ".npv4"]
        supported_extensions = [".hc", ".dark", ".ehi"] + npv_extensions

        # Silently ignore non-supported files without sending any response
        if ext not in supported_extensions:
            return

        if ext == ".hc":
            target_app = "HTTP Custom (.hc Upload)"
            crypto_info = "🔐 Breaking XChaCha20-Poly1305 + HKDF native crypto..."
        elif ext == ".dark":
            target_app = "Dark Tunnel (.dark Upload)"
            crypto_info = "🔐 Breaking 2-Layer AES-CFB (256/192-bit) + MsgPack..."
        elif ext == ".ehi":
            target_app = "HTTP Injector (.ehi Upload)"
            crypto_info = "🔐 Breaking AES-CBC + XXTEA + Argon2id/ChaCha20 crypto..."
        elif ext in npv_extensions:
            target_app = f"NapsternetV ({ext} Upload)"
            crypto_info = "🔐 Breaking NapsternetV Whitebox AES Cipher..."

        status_msg = bot.reply_to(
            message,
            f"⏳ <b>Analyzing & Decrypting <code>{html_escape(file_name)}</code>...</b>\n"
            f"{crypto_info}\n"
            "Please wait a few seconds."
        )

        try:
            file_info = bot.get_file(doc.file_id)
            downloaded_bytes = bot.download_file(file_info.file_path)

            if ext == ".hc":
                res = decrypt_hc_file(downloaded_bytes)
            elif ext == ".dark":
                res = decrypt_dark_file(downloaded_bytes)
            elif ext == ".ehi":
                res = decrypt_ehi_file(downloaded_bytes)
            elif ext in npv_extensions:
                res = decrypt_npv_file(downloaded_bytes)

            # Send clean, styled direct message replying to the uploaded file
            msg_text = res["styled_message"]
            if len(msg_text) > 4000:
                msg_text = msg_text[:3990] + "..."

            try:
                bot.send_message(
                    chat_id,
                    msg_text,
                    reply_to_message_id=message.message_id,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except Exception as e_send:
                print(f"[!] HTML send error: {e_send}, sending plain text...")
                clean_text = msg_text.replace("<code>", "").replace("</code>", "").replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
                bot.send_message(
                    chat_id,
                    clean_text,
                    reply_to_message_id=message.message_id,
                    disable_web_page_preview=True
                )

            try:
                bot.delete_message(chat_id, status_msg.message_id)
            except Exception:
                pass

            # Audit report to Admin
            creator = res.get("creator", "Unknown")
            protocol = res.get("protocol", "Unknown")
            details = (
                f"File: {file_name}\n"
                f"App: {target_app}\n"
                f"Creator: {creator}\n"
                f"Protocol: {protocol}\n"
                f"Server: {res.get('server_host', 'N/A')}:{res.get('server_port', 0)}\n"
                f"Size: {len(downloaded_bytes)} bytes"
            )
            send_admin_report_async(bot, message.from_user, target_app, "SUCCESS", details=details)

        except Exception as e:
            bot.edit_message_text(
                f"❌ <b>{target_app} Decryption Failed!</b>\nError: <code>{html_escape(str(e))}</code>",
                chat_id=chat_id,
                message_id=status_msg.message_id
            )
            send_admin_report_async(bot, message.from_user, target_app, "FAILED", details=str(e))

    # ================= GENERAL TEXT MESSAGES =================
    @bot.message_handler(func=lambda m: True)
    def handle_other_messages(message):
        send_admin_report_async(bot, message.from_user, "Direct Text Message", "INFO", details=f"User sent: {message.text}")
        markup = get_vpn_markup()
        bot.reply_to(
            message,
            get_welcome_text(message.from_user),
            reply_markup=markup
        )

    print("[*] Starting Telegram Bot polling...")
    bot.infinity_polling()


# ================= ENTRYPOINT =================
if __name__ == "__main__":
    # Start Flask background server for Render
    threading.Thread(target=run_flask, daemon=True).start()
    # Start Keep-alive ping worker to prevent Render sleep
    threading.Thread(target=keep_alive_worker, daemon=True).start()
    # Start Bot
    start_bot()
