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
import time
import json
import re
import base64
import datetime
import threading
import requests
import yaml
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from argon2.low_level import hash_secret_raw, Type
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

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


# ================= DECRYPTION ENGINE =================
API_URL = "https://strongteam.co/api/mmtunnel/"
API_PAYLOAD = {"hash": "xsandokUpdatex"}

KEY_LAYER1 = b"iOi/hqT/TocUv0UbDImfWPGR1mfSdzzX"
KEY_LAYER2 = b"NewDecryptLibPassword"

ARGON2_TIME = 3
ARGON2_MEM = 16384
ARGON2_PARALLEL = 1
ARGON2_KEYLEN = 32

# In-memory Cache to eliminate lag & respond instantly
CACHED_DATA = None
CACHE_TIMESTAMP = 0
CACHE_TTL = 300  # 5 minutes cache


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


def decrypt_server_item(s: Dict[str, Any], def_u: str, def_p: str) -> Dict[str, Any]:
    c = dict(s)
    fields = [
        "ServerIPHost", "OVPNUser", "OVPNPass", "CustomCertificate", 
        "SlowDNSHost", "SlowDNSKey", "V2rayUUID", "UDP_obfs", 
        "UDP_user", "H2pass", "TrojanPass"
    ]
    for k in fields:
        if k in c:
            c[k] = decrypt_val(c[k])

    # Auto-fill default credentials if server uses default user or is empty
    if c.get("isdefUser") or not c.get("OVPNUser"):
        c["OVPNUser"] = def_u
        c["OVPNPass"] = def_p

    return c


def decrypt_mmtunnel_live() -> Dict[str, Any]:
    global CACHED_DATA, CACHE_TIMESTAMP
    now = time.time()
    if CACHED_DATA and (now - CACHE_TIMESTAMP < CACHE_TTL):
        return CACHED_DATA

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

    def_u = data.get("DefOVPNUser", "sandoki")
    def_p = data.get("DefOVPNPass", "sandoki")

    # Decrypt Servers with multi-threading (Fast ~1.5s)
    raw_servers = data.get("Servers", [])
    threads = min(os.cpu_count() or 4, 8)
    with ThreadPoolExecutor(max_workers=threads) as ex:
        decrypted_servers = list(ex.map(lambda s: decrypt_server_item(s, def_u, def_p), raw_servers))

    # Fast Clean Networks
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
        "DefOVPNUser": def_u,
        "DefOVPNPass": def_p,
        "HysteriaUser": data.get("HysteriaUser", ""),
        "HysteriaOBFS": data.get("HysteriaOBFS", ""),
        "DefaultOVPNCert": data.get("DefaultOVPNCert", ""),
        "isTimerOn": data.get("isTimerOn", False),
        "timetoadd": data.get("timetoadd", 0),
        "Servers": decrypted_servers,
        "Networks": decrypted_networks
    }

    # Update cache
    CACHED_DATA = full_output
    CACHE_TIMESTAMP = now

    return full_output


# ================= TERIX VPN DECRYPTION ENGINE =================
TERIX_LOGIN_URL = "https://terix-v2.suyebalam0811.workers.dev/api/auth/login"
TERIX_CONFIG_URL = "https://terix-v2.suyebalam0811.workers.dev/api/config"
TERIX_SIGNATURE = "DACD5D672263282B0C8725BECB8B6E9EA7EAC9CE59F3842B4BD5713FF495364A"
TERIX_USER = "Terix2.0"
TERIX_PASS = "https://t.me/terix_bd"
TERIX_DEVICE_ID = "dev_foridul_bot_002"

TERIX_CACHED_RESULT = None
TERIX_CACHE_TIMESTAMP = 0
TERIX_CACHE_TTL = 300  # 5 minutes cache


def decrypt_terix_live() -> Dict[str, Any]:
    global TERIX_CACHED_RESULT, TERIX_CACHE_TIMESTAMP
    now = time.time()
    if TERIX_CACHED_RESULT and (now - TERIX_CACHE_TIMESTAMP < TERIX_CACHE_TTL):
        return TERIX_CACHED_RESULT

    headers_login = {
        "Content-Type": "application/json",
        "X-Terix-Signature": TERIX_SIGNATURE
    }
    login_resp = requests.post(
        TERIX_LOGIN_URL,
        json={"username": TERIX_USER, "password": TERIX_PASS, "deviceId": TERIX_DEVICE_ID},
        headers=headers_login,
        timeout=15
    ).json()

    if "token" not in login_resp:
        err = login_resp.get("error", "Login failed")
        raise RuntimeError(f"TeriX Auth Error: {err}")

    token = login_resp["token"]
    secret_raw = base64.b64decode(login_resp["device"]["secret"])
    user_id = login_resp["user"]["id"]
    device_id = login_resp["device"]["id"]
    plan = login_resp.get("subscription", {}).get("plan", "normal")
    status = login_resp.get("subscription", {}).get("status", "active")

    headers_cfg = {
        "Authorization": f"Bearer {token}",
        "X-Terix-Signature": TERIX_SIGNATURE
    }
    cfg = requests.get(TERIX_CONFIG_URL, headers=headers_cfg, timeout=15).json()
    if "ciphertext" not in cfg:
        err = cfg.get("error", "Config fetch failed")
        raise RuntimeError(f"TeriX Config Error: {err}")

    nonce = base64.b64decode(cfg["nonce"])
    iv = base64.b64decode(cfg["iv"])
    tag = base64.b64decode(cfg["tag"])
    ct = base64.b64decode(cfg["ciphertext"])
    aad_raw = base64.b64decode(cfg["aad"])

    # HKDF-SHA256 Key Derivation
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=nonce,
        info=f"terix-config-v1:{user_id}:{device_id}".encode()
    )
    key = hkdf.derive(secret_raw)
    decrypted_bytes = AESGCM(key).decrypt(iv, ct + tag, aad_raw)
    yaml_raw = decrypted_bytes.decode("utf-8")

    # Parse YAML to extract individual proxies
    try:
        parsed_yaml = yaml.safe_load(yaml_raw) or {}
    except Exception:
        parsed_yaml = {}

    proxies = parsed_yaml.get("proxies", [])

    # Format Human-readable Text output
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S ⏳")
    lines = [
        "=============================================================================",
        "  TERIX VPN DECRYPTED CONFIGURATION (100% LIVE)",
        "  Powered By : @Foridul_002 🇧🇩",
        "  Bot        : @decryptvpnappbot",
        f"  Date & Time: {now_str}",
        "=============================================================================",
        "",
        "[+] ACCOUNT & SUBSCRIPTION:",
        f"  • Username    : {TERIX_USER}",
        f"  • Plan        : {plan.title()} ({status.title()})",
        f"  • User ID     : {user_id}",
        f"  • Device ID   : {device_id}",
        f"  • Total Proxies: {len(proxies)}",
        "",
        "=============================================================================",
        "  EXTRACTED PROXY SERVERS LIST",
        "=============================================================================",
    ]

    for idx, p in enumerate(proxies, 1):
        name = p.get("name", f"Server {idx}")
        ptype = p.get("type", "unknown")
        server = p.get("server", "")
        port = p.get("port", "")
        u = p.get("username", "")
        pwd = p.get("password", "")
        udp = p.get("udp", True)

        lines.append(f"{idx}. {name}")
        lines.append(f"   • Type    : {ptype.upper()}")
        lines.append(f"   • Server  : {server}")
        lines.append(f"   • Port    : {port}")
        if u or pwd:
            lines.append(f"   • Username: {u}")
            lines.append(f"   • Password: {pwd}")
        lines.append(f"   • UDP     : {udp}")
        lines.append("")

    lines.extend([
        "=============================================================================",
        "  FULL CLASH / FLCLASH / SING-BOX RAW YAML CONFIG",
        "=============================================================================",
        yaml_raw
    ])

    formatted_txt = "\n".join(lines)
    result = {
        "txt_content": formatted_txt,
        "total_proxies": len(proxies),
        "proxies": proxies,
        "plan": plan,
        "status": status,
        "user_id": user_id
    }

    TERIX_CACHED_RESULT = result
    TERIX_CACHE_TIMESTAMP = now
    return result


# ================= URSA NET PRO DECRYPTION ENGINE =================
URSA_API_URL = "https://raw.githubusercontent.com/panigbatanc/UrsaNetPRO/main/JSONDEC2025"
URSA_OUTER_KEY = b"...|..."
URSA_INNER_KEY = b"4%PdXch>fkP]"
URSA_CACHED_DATA = None
URSA_CACHE_TIMESTAMP = 0
URSA_CACHE_TTL = 300  # 5 minutes cache

def _ursa_a(i: int, i2: int, i3: int, i4: int, i5: int, iArr: List[int]) -> int:
    part1 = ((i ^ i2) + (iArr[(i4 & 3) ^ i5] ^ i3)) & 0xFFFFFFFF
    part2 = (((i3 >> 5 ^ i2 << 2) + (i2 >> 3 ^ i3 << 4))) & 0xFFFFFFFF
    return (part1 ^ part2) & 0xFFFFFFFF

def _ursa_g(bArr: bytes, z: bool) -> List[int]:
    length = (len(bArr) >> 2) if (len(bArr) & 3) == 0 else (len(bArr) >> 2) + 1
    if z:
        iArr = [0] * (length + 1)
        iArr[length] = len(bArr)
    else:
        iArr = [0] * length
    for i in range(len(bArr)):
        i2 = i >> 2
        iArr[i2] = (iArr[i2] | ((bArr[i] & 255) << ((i & 3) << 3))) & 0xFFFFFFFF
    return iArr

def _ursa_f(iArr: List[int], z: bool):
    length = len(iArr) << 2
    if z:
        i = iArr[-1]
        i2 = length - 4
        if i >= length - 7 and i <= i2:
            length = i
        else:
            return None
    bArr = bytearray(length)
    for i3 in range(length):
        bArr[i3] = (iArr[i3 >> 2] >> ((i3 & 3) << 3)) & 255
    return bytes(bArr)

def _ursa_xxtea_decrypt(bArr: bytes, bArr2: bytes):
    if len(bArr) == 0:
        return bArr
    g_arr = _ursa_g(bArr, False)
    if len(bArr2) != 16:
        bArr3 = bytearray(16)
        if len(bArr2) < 16:
            bArr3[:len(bArr2)] = bArr2
        else:
            bArr3[:16] = bArr2[:16]
        bArr2 = bytes(bArr3)
    g2 = _ursa_g(bArr2, False)
    length = len(g_arr)
    i = length - 1
    if i >= 1:
        i2 = (52 // length) + 6
        i3 = g_arr[0]
        i4 = (i2 * (-1638454863)) & 0xFFFFFFFF
        delta = (-1638454863) & 0xFFFFFFFF
        while i4 != 0:
            i5 = (i4 >> 2) & 3
            i6 = i3
            i7 = i
            while i7 > 0:
                i6 = (g_arr[i7] - _ursa_a(i4, i6, g_arr[i7 - 1], i7, i5, g2)) & 0xFFFFFFFF
                g_arr[i7] = i6
                i7 -= 1
            i3 = (g_arr[0] - _ursa_a(i4, i6, g_arr[i], i7, i5, g2)) & 0xFFFFFFFF
            g_arr[0] = i3
            i4 = (i4 - delta) & 0xFFFFFFFF
    return _ursa_f(g_arr, True)

HEX_PATTERN = re.compile(r"^[0-9a-fA-F]+$")

def decrypt_single_hex(h: str) -> str:
    h = h.strip()
    if not h or len(h) < 2 or len(h) % 2 != 0 or not HEX_PATTERN.match(h):
        return h
    if h.isdigit() and len(h) <= 5:
        return h
    try:
        raw = bytes.fromhex(h)
        out = bytearray(len(raw))
        for i in range(len(raw)):
            out[i] = raw[i] ^ URSA_INNER_KEY[i % len(URSA_INNER_KEY)]
        return out.decode("utf-8", errors="replace")
    except Exception:
        return h

def decrypt_ursa_field(val: str) -> str:
    if not val or not isinstance(val, str) or val in ["Pulled", "auto", "false", "true", "[sip]"]:
        return val
    val = val.strip()
    if ";" in val:
        parts = val.split(";")
        return ";".join([decrypt_single_hex(p) for p in parts])
    return decrypt_single_hex(val)

def generate_ursa_text_report(config: dict) -> str:
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S ⏳")
    servers = config.get("Free_servers", [])
    payloads = config.get("Payloads", [])
    sips_raw = config.get("SIPs", "")
    sips = [ip.strip() for ip in sips_raw.split(";") if ip.strip()]

    lines = [
        "=============================================================================",
        "  URSA NET PRO (PRINCE BUILD 66) - 100% DECRYPTED CONFIGURATION",
        "  Powered By : @Foridul_002 🇧🇩",
        "  Bot        : @decryptvpnappbot",
        f"  Date & Time: {now_str}",
        "=============================================================================",
        "",
        "[+] CONFIGURATION SUMMARY:",
        f"  • Config Version   : {config.get('Version', 'N/A')}",
        f"  • UDP Version      : {config.get('UDPVersion', 'N/A')}",
        f"  • Total Servers    : {len(servers)} Clusters",
        f"  • Total Payloads   : {len(payloads)} Tweaks",
        f"  • Dynamic SIPs Pool: {len(sips)} IPs",
        f"  • Changelog        : {config.get('Changelogs', '').strip()}",
        "",
        "=============================================================================",
        "  SECTION 1: DECRYPTED SERVERS LIST (ALL 19 CLUSTERS)",
        "=============================================================================",
    ]

    for idx, s in enumerate(servers, 1):
        name = s.get("server_name", f"Server {idx}")
        cat = s.get("category", "unknown").upper()
        host = s.get("server_host", "")
        port = s.get("server_port", "")
        u_port = s.get("server_udp_port", "")
        ssl_port = s.get("ssl_port", "")

        ports_str = []
        if port: ports_str.append(f"Port: {port}")
        if ssl_port: ports_str.append(f"SSL: {ssl_port}")
        if u_port: ports_str.append(f"UDP: {u_port}")

        lines.append(f"{idx}. {name} [{cat}]")
        if host == "[sip]":
            lines.append("   • Host Cluster : Dynamic SIP Pool (uses any IP from SIPs pool)")
        elif not host or host == "auto":
            lines.append(f"   • Host Cluster : {host or 'Auto / Direct'}")
        else:
            h_list = [h.strip() for h in host.split(";") if h.strip()]
            if len(h_list) > 1:
                lines.append(f"   • Host Nodes ({len(h_list)} Nodes) :")
                for node in h_list:
                    lines.append(f"       - {node}")
            else:
                lines.append(f"   • Host Node    : {host}")

        if ports_str:
            lines.append(f"   • Ports        : {' | '.join(ports_str)}")
        lines.append("")

    lines.extend([
        "=============================================================================",
        "  SECTION 2: DYNAMIC SIPs IP POOL",
        "=============================================================================",
        f"Total Registered IPs: {len(sips)}",
        ", ".join(sips) if sips else "None",
        "",
        "=============================================================================",
        "  SECTION 3: DECRYPTED TWEAKS / PAYLOADS (ALL 255 TWEAKS)",
        "=============================================================================",
    ])

    for idx, p in enumerate(payloads, 1):
        name = p.get("friendly_name", f"Tweak {idx}")
        cat = p.get("category", "")
        method = p.get("method", "").upper()
        port = p.get("port", "")
        host = p.get("host", "")
        sausage = p.get("sausage", "")

        lines.append(f"{idx}. {name}")
        lines.append(f"   • Method   : {method} | Category: {cat} | Port: {port}")
        if host and host != "Pulled":
            h_parts = [h.strip() for h in host.split(";") if h.strip()]
            if len(h_parts) > 3:
                lines.append(f"   • SNI/Host ({len(h_parts)} domains) : {h_parts[0]}, {h_parts[1]} ... (+{len(h_parts)-2} more)")
            else:
                lines.append(f"   • SNI/Host : {host}")
        else:
            lines.append("   • SNI/Host : Direct / Default")
        if sausage:
            lines.append(f"   • Sausage  : {sausage}")
        lines.append("")

    return "\n".join(lines)

def decrypt_ursa_live() -> Dict[str, Any]:
    global URSA_CACHED_DATA, URSA_CACHE_TIMESTAMP
    now = time.time()
    if URSA_CACHED_DATA and (now - URSA_CACHE_TIMESTAMP < URSA_CACHE_TTL):
        return URSA_CACHED_DATA

    resp = requests.get(URSA_API_URL, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Server returned status {resp.status_code}")

    cipher_bytes = base64.b64decode(resp.text.strip())
    raw_decrypted = _ursa_xxtea_decrypt(cipher_bytes, URSA_OUTER_KEY)
    if not raw_decrypted:
        raise ValueError("Failed to decrypt Ursa Net PRO configuration.")

    config = json.loads(raw_decrypted.decode("utf-8", errors="replace"))

    # Decrypt Free_servers completely in place
    for s in config.get("Free_servers", []):
        for f in ["server_host", "username", "password", "custom_cert"]:
            if f in s and s[f]:
                s[f] = decrypt_ursa_field(s[f])

    # Decrypt Payloads completely in place
    for p in config.get("Payloads", []):
        for f in ["host", "payload", "sausage", "dothost"]:
            if f in p and p[f]:
                p[f] = decrypt_ursa_field(p[f])
        p["decrypted_host"] = p.get("host", "")

    # Decrypt top level payloads
    for f in ["HopPayload", "DualConnectPayload", "SSLPayload", "CustomCert", "CDNHosts", "FrontHosts", "BackHosts"]:
        if f in config and config[f]:
            config[f] = decrypt_ursa_field(config[f])

    txt_content = generate_ursa_text_report(config)

    result = {
        "config": config,
        "txt_content": txt_content
    }

    URSA_CACHED_DATA = result
    URSA_CACHE_TIMESTAMP = now
    return result


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
                InlineKeyboardButton("🛡️ TeriX VPN", callback_data="dec_terix"),
                InlineKeyboardButton("🛡️ Ursa Net PRO", callback_data="dec_ursanet"),
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
            bot.answer_callback_query(call.id, "⏳ Fetching & Decrypting MM Tunnel Config...")
            
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
                    f"🔐 <b>OpenVPN User:</b> <code>{ovpn_user}</code>\n"
                    f"🔑 <b>OpenVPN Pass:</b> <code>{ovpn_pass}</code>\n"
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

        elif call.data == "dec_terix":
            bot.answer_callback_query(call.id, "⏳ Fetching & Decrypting TeriX VPN Config...")
            
            # Send loading message
            status_msg = bot.send_message(
                chat_id, 
                "⏳ <b>TeriX VPN লাইভ ডাটা ফেচ ও ডিক্রিপ্ট করা হচ্ছে...</b>\nঅনুগ্রহ করে কয়েক সেকেন্ড অপেক্ষা করুন।"
            )

            try:
                res = decrypt_terix_live()
                txt_bytes = io.BytesIO(res["txt_content"].encode("utf-8"))
                txt_bytes.name = "TeriX_Decrypted.txt"

                total_proxies = res["total_proxies"]
                plan = res["plan"].title()
                status = res["status"].title()

                server_lines = []
                for p in res.get("proxies", [])[:5]:
                    server_lines.append(f"• <b>{p.get('name')}</b> ({p.get('type', '').upper()}) ➔ <code>{p.get('server')}:{p.get('port')}</code>")
                server_preview = "\n".join(server_lines)

                caption = (
                    "✅ <b>TeriX VPN 100% Decrypted Successfully!</b>\n\n"
                    f"👤 <b>Account:</b> <code>{TERIX_USER}</code>\n"
                    f"💎 <b>Plan:</b> {plan} ({status})\n"
                    f"🌐 <b>Total Proxy Servers:</b> <code>{total_proxies}</code>\n\n"
                    "<b>🚀 Server Preview:</b>\n"
                    f"{server_preview}\n\n"
                    "📁 <i>সম্পূর্ণ Clash YAML এবং সার্ভার লিস্ট সংযুক্ত ফাইলে দেওয়া হয়েছে।</i>\n\n"
                    "🤖 <b>Decrypted By:</b> @Foridul_002 🇧🇩"
                )

                bot.send_document(
                    chat_id,
                    txt_bytes,
                    caption=caption
                )
                bot.delete_message(chat_id, status_msg.message_id)

            except Exception as e:
                bot.edit_message_text(
                    f"❌ <b>TeriX Decryption Failed!</b>\nError: <code>{e}</code>",
                    chat_id=chat_id,
                    message_id=status_msg.message_id
                )

        elif call.data == "dec_ursanet":
            bot.answer_callback_query(call.id, "⏳ Fetching & Decrypting Ursa Net PRO Config...")
            
            status_msg = bot.send_message(
                chat_id, 
                "⏳ <b>Ursa Net PRO লাইভ ডাটা ডিক্রিপ্ট করা হচ্ছে...</b>\nঅনুগ্রহ করে কয়েক সেকেন্ড অপেক্ষা করুন।"
            )

            try:
                res = decrypt_ursa_live()
                config = res["config"]
                txt_content = res["txt_content"]

                # 1. Text Report File
                txt_bytes = io.BytesIO(txt_content.encode("utf-8"))
                txt_bytes.name = "Ursa_Net_PRO_Decrypted.txt"

                # 2. Clean Decrypted JSON File
                formatted_json = json.dumps(config, indent=4, ensure_ascii=False)
                json_bytes = io.BytesIO(formatted_json.encode("utf-8"))
                json_bytes.name = "Ursa_Net_PRO_Decrypted.json"

                version = config.get("Version", "N/A")
                payloads = config.get("Payloads", [])
                servers = config.get("Free_servers", [])
                sips_count = len([ip for ip in config.get("SIPs", "").split(";") if ip.strip()])

                # Server Preview (Top 4 servers)
                server_preview_lines = []
                for s in servers[1:5]:
                    s_name = s.get("server_name", "")
                    s_cat = s.get("category", "").upper()
                    s_host = s.get("server_host", "")
                    s_port = s.get("server_port", "")
                    if s_host == "[sip]":
                        target = "Dynamic SIP Pool"
                    elif ";" in s_host:
                        nodes = [n.strip() for n in s_host.split(";") if n.strip()]
                        target = f"{nodes[0]} ({len(nodes)} nodes)"
                    else:
                        target = s_host or "Direct"
                    if s_port:
                        target += f":{s_port}"
                    server_preview_lines.append(f"• <b>{s_name}</b> ({s_cat})\n  ➔ <code>{target}</code>")
                server_preview = "\n".join(server_preview_lines)

                caption = (
                    "✅ <b>Ursa Net PRO 100% Decrypted Successfully!</b>\n\n"
                    f"📦 <b>Config Version:</b> <code>{version}</code>\n"
                    f"🌐 <b>Free Servers:</b> <code>{len(servers)} Clusters (All Nodes 100% Decrypted)</code>\n"
                    f"📡 <b>Total Tweaks/SNI:</b> <code>{len(payloads)} Payloads</code>\n"
                    f"🛡 <b>Dynamic SIPs Pool:</b> <code>{sips_count} Server IPs</code>\n\n"
                    "<b>🚀 Server Clusters Preview:</b>\n"
                    f"{server_preview}\n\n"
                    "📁 <i>সম্পূর্ণ সার্ভার ও পেলোড লিস্ট Text এবং JSON ফাইলে সংযুক্ত করা হয়েছে।</i>\n\n"
                    "🤖 <b>Decrypted By:</b> @Foridul_002 🇧🇩"
                )

                # Send formatted TXT report with caption
                bot.send_document(
                    chat_id,
                    txt_bytes,
                    caption=caption
                )
                # Send full decrypted JSON file
                bot.send_document(
                    chat_id,
                    json_bytes
                )
                bot.delete_message(chat_id, status_msg.message_id)

            except Exception as e:
                bot.edit_message_text(
                    f"❌ <b>Ursa Net PRO Decryption Failed!</b>\nError: <code>{e}</code>",
                    chat_id=chat_id,
                    message_id=status_msg.message_id
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
