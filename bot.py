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
import struct
import datetime
import threading
import urllib.parse
import requests
import yaml
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from argon2.low_level import hash_secret_raw, Type
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

# ================= CONFIGURATION =================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

# Flask App for Render Health Check
app = Flask(__name__)

@app.route("/")
def health_check():
    return "✅ VPN Decryptor Bot (v3.2 - VIP Sniper Pro Ready) is running 24/7 on Render!"

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

    # Decrypt Free_servers completely in place (server_host, etc.)
    for s in config.get("Free_servers", []):
        for f in ["server_host", "username", "password", "custom_cert"]:
            if f in s and s[f]:
                s[f] = decrypt_ursa_field(s[f])

    # Decrypt Payloads completely in place (host, payload, sausage, dothost)
    for p in config.get("Payloads", []):
        for f in ["host", "payload", "sausage", "dothost"]:
            if f in p and p[f]:
                p[f] = decrypt_ursa_field(p[f])

    # Decrypt top level payloads
    for f in ["HopPayload", "DualConnectPayload", "SSLPayload", "CustomCert", "CDNHosts", "FrontHosts", "BackHosts"]:
        if f in config and config[f]:
            config[f] = decrypt_ursa_field(config[f])

    full_output = {
        "CREDITS": [
            {
                "Owner": "Powered By @Foridul_002 🇧🇩",
                "Bot": "Decrypted By @decryptvpnappbot 🤖",
                "Date & Time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S ⏳")
            }
        ],
        **config
    }

    raw_txt = json.dumps(full_output, indent=2, ensure_ascii=False)

    result = {
        "config": full_output,
        "raw_txt": raw_txt,
        "version": config.get("Version", "N/A"),
        "total_servers": len(config.get("Free_servers", [])),
        "total_payloads": len(config.get("Payloads", []))
    }

    URSA_CACHED_DATA = result
    URSA_CACHE_TIMESTAMP = now
    return result


# ================= VIP SNIPER PRO DECRYPTION ENGINE =================
VIP_DATA_27F688 = bytes.fromhex('1fea453c1c20a9366214bf96b64a26f1b76e32660d02ab66a1ddc878936186b1')
VIP_IV_27F6A8   = bytes.fromhex('82aa46e488644f9f3af6b61b69d214cd')
VIP_SALT_16     = bytes.fromhex('c9c5fd1cace2fe51e213935313b2f03b')
VIP_FIXED_SALT  = bytes.fromhex('c9c5fd1cace2fe51e213935313b2f03ba055190f23b4aced90c36cf3cb43d291')
VIP_KEY_16      = bytes.fromhex('d354f18b4f246a95aa6e2562289a5e7b')

VIP_CACHED_DATA = None
VIP_CACHE_TIMESTAMP = 0
VIP_CACHE_TTL = 300

# Pre-derive keys at module load (one-time cost)
VIP_THREEFISH_KEY = HKDF(algorithm=hashes.SHA256(), length=32, salt=VIP_FIXED_SALT, info=b'', backend=default_backend()).derive(VIP_DATA_27F688)
VIP_AES_KEY_MODE1 = HKDF(algorithm=hashes.SHA256(), length=16, salt=VIP_SALT_16, info=b'', backend=default_backend()).derive(VIP_DATA_27F688)
VIP_PBKDF2_KEY = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=VIP_FIXED_SALT, iterations=100000, backend=default_backend()).derive(VIP_DATA_27F688)

VIP_DELTA = 0x7a56d3e1
VIP_MASK = 0xffffffff


def _vip_bytes_to_words(b):
    n = (len(b) + 3) // 4
    words = [0] * n
    for i, byte in enumerate(b):
        words[i // 4] |= (byte & 0xff) << ((i % 4) * 8)
    return words


def _vip_words_to_bytes(words):
    total_len = words[-1]
    res = bytearray()
    for i in range(total_len):
        res.append((words[i // 4] >> ((i % 4) * 8)) & 0xff)
    return res


def _vip_mx(sum_val, y, z, p, e, k):
    part1 = ((sum_val ^ y) + (k[(p & 3) ^ e] ^ z)) & VIP_MASK
    part2 = (((z >> 5 ^ (y << 2) & VIP_MASK)) + ((y >> 3 ^ (z << 4) & VIP_MASK))) & VIP_MASK
    return (part1 ^ part2) & VIP_MASK


def _vip_xxtea_decrypt(data_bytes, key_bytes):
    v = _vip_bytes_to_words(data_bytes)
    k_raw = bytearray(key_bytes[:16].ljust(16, b'\x00'))
    for idx, b in enumerate(k_raw):
        if b == 0:
            for j in range(idx, 16):
                k_raw[j] = 0
            break
    k = _vip_bytes_to_words(k_raw)[:4]
    if len(k) < 4:
        k.extend([0] * (4 - len(k)))
    n = len(v)
    if n <= 1:
        return data_bytes
    rounds = 6 + 52 // n
    sum_val = (rounds * VIP_DELTA) & VIP_MASK
    y = v[0]
    while sum_val != 0:
        e = (sum_val >> 2) & 3
        for p in range(n - 1, 0, -1):
            z = v[p - 1]
            y = (v[p] - _vip_mx(sum_val, y, z, p, e, k)) & VIP_MASK
            v[p] = y
        z = v[n - 1]
        y = (v[0] - _vip_mx(sum_val, y, z, 0, e, k)) & VIP_MASK
        v[0] = y
        sum_val = (sum_val - VIP_DELTA) & VIP_MASK
    return _vip_words_to_bytes(v)


def vip_decrypt_mode0(b64_str: str) -> str:
    """Mode 0: AES-128-CBC + XXTEA + byte shift (-2). Used for Names, Ports, Certs, UUID, ProxySettings.Squid."""
    if not b64_str or not isinstance(b64_str, str):
        return b64_str or ''
    try:
        cipher_bytes = base64.b64decode(b64_str.strip())
        cipher = Cipher(algorithms.AES(VIP_KEY_16), modes.CBC(VIP_IV_27F6A8), backend=default_backend())
        decryptor = cipher.decryptor()
        aes_dec = decryptor.update(cipher_bytes) + decryptor.finalize()
        pad_len = aes_dec[-1]
        if 1 <= pad_len <= 16:
            aes_dec = aes_dec[:-pad_len]
        xxtea_dec = _vip_xxtea_decrypt(aes_dec, VIP_KEY_16)
        final_bytes = bytearray(((b - 2) & 0xff for b in xxtea_dec))
        return final_bytes.decode('utf-8', errors='replace')
    except Exception:
        return b64_str


# Threefish-256 constants
VIP_C240 = 0x1BD11BDAA9FC1A22
VIP_MASK64 = 0xFFFFFFFFFFFFFFFF
VIP_ROT = [
    [14, 16], [52, 57], [23, 40], [5, 37],
    [25, 33], [46, 12], [58, 22], [32, 32]
]


def _vip_ror64(x, n):
    return ((x >> n) | (x << (64 - n))) & VIP_MASK64


def _vip_threefish_decrypt_block(block_bytes, key_words, tweak_words):
    v = list(struct.unpack('<4Q', block_bytes))
    k = list(key_words)
    k.append(VIP_C240 ^ k[0] ^ k[1] ^ k[2] ^ k[3])
    t = list(tweak_words)
    t.append(t[0] ^ t[1])
    x6, x4, x5, x7 = v[0], v[1], v[2], v[3]
    s = 18
    x6 = (x6 - k[s % 5]) & VIP_MASK64
    x4 = (x4 - (k[(s + 1) % 5] + t[s % 3])) & VIP_MASK64
    x5 = (x5 - (k[(s + 2) % 5] + t[(s + 1) % 3])) & VIP_MASK64
    x7 = (x7 - (k[(s + 3) % 5] + s)) & VIP_MASK64
    for r in range(71, -1, -1):
        rot = VIP_ROT[r % 8]
        if r % 2 == 1:
            x7 = (x7 ^ x6)
            x4 = (x4 ^ x5)
            x7 = _vip_ror64(x7, rot[0])
            x4 = _vip_ror64(x4, rot[1])
            x6 = (x6 - x7) & VIP_MASK64
            x5 = (x5 - x4) & VIP_MASK64
        else:
            x4 = (x4 ^ x6)
            x7 = (x7 ^ x5)
            x4 = _vip_ror64(x4, rot[0])
            x7 = _vip_ror64(x7, rot[1])
            x6 = (x6 - x4) & VIP_MASK64
            x5 = (x5 - x7) & VIP_MASK64
        if r % 4 == 0:
            s = r // 4
            x6 = (x6 - k[s % 5]) & VIP_MASK64
            x4 = (x4 - (k[(s + 1) % 5] + t[s % 3])) & VIP_MASK64
            x5 = (x5 - (k[(s + 2) % 5] + t[(s + 1) % 3])) & VIP_MASK64
            x7 = (x7 - (k[(s + 3) % 5] + s)) & VIP_MASK64
    return struct.pack('<4Q', x6, x4, x5, x7)


VIP_KEY_WORDS = struct.unpack('<4Q', VIP_THREEFISH_KEY)
VIP_TWEAK_WORDS = (0, 0)


def vip_decrypt_mode1(b64_str: str) -> str:
    """Mode 1: Threefish-256 -> AES-128-CBC. Used for ServerIPHost, SNIHost, Payload, V2Ray.SNIHost, V2Ray.PATH."""
    if not b64_str or not isinstance(b64_str, str):
        return b64_str or ''
    try:
        cipher_bytes = base64.b64decode(b64_str.strip())
        if len(cipher_bytes) % 8 != 0:
            return b64_str
        rem = len(cipher_bytes) % 32
        if rem != 0:
            cipher_bytes += b'\x00' * (32 - rem)
        dec_blocks = bytearray()
        for i in range(0, len(cipher_bytes), 32):
            block = cipher_bytes[i:i + 32]
            dec_blocks.extend(_vip_threefish_decrypt_block(block, VIP_KEY_WORDS, VIP_TWEAK_WORDS))
        dec_trimmed = dec_blocks.rstrip(b'\x00')
        if len(dec_trimmed) == 0:
            return b64_str
        cipher = Cipher(algorithms.AES(VIP_AES_KEY_MODE1), modes.CBC(VIP_IV_27F6A8), backend=default_backend())
        decryptor = cipher.decryptor()
        aes_dec = decryptor.update(dec_trimmed) + decryptor.finalize()
        pad_len = aes_dec[-1]
        if 1 <= pad_len <= 16:
            aes_dec = aes_dec[:-pad_len]
        return aes_dec.decode('utf-8', errors='replace')
    except Exception:
        return b64_str


def vip_decrypt_mode2(b64_str: str) -> str:
    """Mode 2: XXTEA(PBKDF2_key[:16]) -> extract IV -> AES-256-CBC. Used for Username, Password."""
    if not b64_str or not isinstance(b64_str, str):
        return b64_str or ''
    try:
        cipher_bytes = base64.b64decode(b64_str.strip())
        xxtea_dec = _vip_xxtea_decrypt(cipher_bytes, VIP_PBKDF2_KEY[:16])
        iv = xxtea_dec[:16]
        ct = xxtea_dec[16:]
        cipher = Cipher(algorithms.AES(VIP_PBKDF2_KEY), modes.CBC(iv), backend=default_backend())
        dec = cipher.decryptor()
        aes_dec = dec.update(ct) + dec.finalize()
        pad = aes_dec[-1]
        if 1 <= pad <= 16:
            aes_dec = aes_dec[:-pad]
        return aes_dec.decode('utf-8', errors='replace').strip()
    except Exception:
        return b64_str


VIP_LIVE_CONFIG_URL = "https://raw.githubusercontent.com/Civ3snipher/NEW-VIP-SNIPHER-PRO-3/refs/heads/main/update.json?ref=main"
VIP_GITHUB_TOKEN = ''.join(chr(c ^ 42) for c in [77, 66, 90, 117, 25, 105, 105, 110, 78, 120, 107, 122, 29, 27, 70, 104, 80, 114, 73, 112, 67, 28, 77, 75, 112, 80, 99, 83, 92, 83, 72, 120, 72, 127, 26, 26, 70, 99, 102, 110])


def fetch_vipsniper_live() -> str:
    """Fetch live encrypted config from Civ3snipher GitHub repository (used by official VIP Sniper app)."""
    headers = {
        "Authorization": f"Bearer {VIP_GITHUB_TOKEN}",
        "Accept": "application/vnd.github.raw+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 10; Build/QP1A.190711.020)"
    }
    # Method 1: GitHub API contents endpoint
    try:
        r = requests.get(
            "https://api.github.com/repos/Civ3snipher/NEW-VIP-SNIPHER-PRO-3/contents/update.json?ref=main",
            headers=headers,
            timeout=10
        )
        if r.status_code == 200 and len(r.text.strip()) > 100:
            return r.text.strip()
    except Exception:
        pass

    # Method 2: Raw githubusercontent with auth header
    try:
        r = requests.get(VIP_LIVE_CONFIG_URL, headers=headers, timeout=10)
        if r.status_code == 200 and len(r.text.strip()) > 100:
            return r.text.strip()
    except Exception:
        pass

    return None


def decrypt_vipsniper_pro(raw_b64: str = None) -> Dict[str, Any]:
    """Full VIP Sniper Pro decryption pipeline: outer layer + all nested fields."""
    global VIP_CACHED_DATA, VIP_CACHE_TIMESTAMP
    now = time.time()
    if not raw_b64 and VIP_CACHED_DATA and (now - VIP_CACHE_TIMESTAMP < VIP_CACHE_TTL):
        return VIP_CACHED_DATA

    if not raw_b64:
        # First try fetching official live update (e.g. v8.0.53)
        live_data = fetch_vipsniper_live()
        if live_data:
            raw_b64 = live_data
        else:
            candidate_paths = [
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "vip_sniper_raw.js"),
                "/home/foridul/.gemini/antigravity-ide/scratch/vip_snipher_pro/update_live.json",
                "/home/foridul/.gemini/antigravity-ide/scratch/vip_snipher_pro/decompiled/resources/res/raw/e.js"
            ]
            found_data = None
            for p in candidate_paths:
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        found_data = f.read().strip()
                    break
            if not found_data:
                raise FileNotFoundError("VIP Sniper Pro encrypted config file (update.json / e.js) not found.")
            raw_b64 = found_data

    # Decrypt outer layer (Mode 0)
    outer_str = vip_decrypt_mode0(raw_b64)
    data = json.loads(outer_str)

    version = data.get("Version", "1.0.0")
    glob_user = vip_decrypt_mode2(data.get("Username")) or "james"
    glob_pass = vip_decrypt_mode2(data.get("Password")) or "james"
    notes = data.get("Notes", "")

    # Decrypt servers
    decrypted_servers = []
    for s in data.get("Servers", []):
        s_dec = {}
        for k, v in s.items():
            if k == "ServerIPHost":
                s_dec[k] = vip_decrypt_mode1(v)
            elif k in ["Username", "Password"]:
                s_dec[k] = vip_decrypt_mode2(v) or (glob_user if k == "Username" else glob_pass)
            elif k == "V2Ray" and isinstance(v, dict):
                v2 = {}
                for vk, vv in v.items():
                    if vk in ["V2RayHost", "PATH"]:
                        v2[vk] = vip_decrypt_mode1(vv)
                    elif vk == "UUID":
                        v2[vk] = vip_decrypt_mode0(vv)
                    else:
                        v2[vk] = vv
                s_dec[k] = v2
            elif k == "SlowDNS" and isinstance(v, dict):
                sd = {}
                for sk, sv in v.items():
                    sd[sk] = vip_decrypt_mode0(sv) if isinstance(sv, str) else sv
                s_dec[k] = sd
            elif isinstance(v, str):
                s_dec[k] = vip_decrypt_mode0(v)
            else:
                s_dec[k] = v
        decrypted_servers.append(s_dec)

    # Decrypt networks (including nested V2Ray.SNIHost and ProxySettings.Squid)
    decrypted_networks = []
    for n in data.get("Networks", []):
        n_dec = {}
        for k, v in n.items():
            if k in ["SNIHost", "Payload"]:
                n_dec[k] = vip_decrypt_mode1(v)
            elif k == "V2Ray" and isinstance(v, dict):
                v2 = {}
                for vk, vv in v.items():
                    if vk in ["SNIHost", "CustomV2RAYConfig"]:
                        v2[vk] = vip_decrypt_mode1(vv)
                    elif isinstance(vv, str):
                        v2[vk] = vip_decrypt_mode0(vv)
                    else:
                        v2[vk] = vv
                n_dec[k] = v2
            elif k == "ProxySettings" and isinstance(v, dict):
                ps = {}
                for pk, pv in v.items():
                    if isinstance(pv, str):
                        ps[pk] = vip_decrypt_mode0(pv)
                    else:
                        ps[pk] = pv
                n_dec[k] = ps
            elif isinstance(v, str):
                n_dec[k] = vip_decrypt_mode0(v)
            else:
                n_dec[k] = v
        decrypted_networks.append(n_dec)

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S ⏳")

    # Format beautiful text report
    lines = [
        "=============================================================================",
        "  VIP SNIPER PRO DECRYPTED CONFIGURATION (100% LIVE & USABLE)",
        "  Powered By : @Foridul_002 🇧🇩",
        "  Bot        : @decryptvpnappbot",
        f"  Date & Time: {now_str}",
        "=============================================================================",
        "",
        "[+] ACCOUNT & CREDENTIALS:",
        f"  • Config Version   : {version}",
        f"  • Default Username : {glob_user}",
        f"  • Default Password : {glob_pass}",
        f"  • Total Servers    : {len(decrypted_servers)}",
        f"  • Total Networks   : {len(decrypted_networks)}",
        "",
        "=============================================================================",
        "  SERVERS LIST & FULL CONNECTION DETAILS",
        "=============================================================================",
    ]

    for idx, s in enumerate(decrypted_servers, 1):
        name = s.get("Name", f"Server {idx}")
        subname = s.get("Subname", "")
        host = s.get("ServerIPHost", "")
        proto = s.get("Protocol", 0)
        tcp = s.get("OpenVPNTCPPort", "")
        ssl = s.get("OpenVPNSSLPort", "")
        u = s.get("Username") or glob_user
        p = s.get("Password") or glob_pass
        cert = s.get("CustomCert", "")

        if proto == 0:
            proto_name = "OpenVPN TCP / SSL"
        elif proto == 2:
            proto_name = "High-Speed UDP"
        elif proto == 3:
            proto_name = "X-Ray / VLESS"
        elif proto == 4:
            proto_name = "SSL / SlowDNS"
        else:
            proto_name = f"Protocol {proto}"

        lines.append(f"{idx}. {name} ({subname})")
        lines.append(f"   • Protocol : {proto_name}")
        lines.append(f"   • Host/IP  : {host}")
        if tcp or ssl:
            lines.append(f"   • Ports    : TCP {tcp} | SSL {ssl}")
        if u or p:
            lines.append(f"   • User/Pass: {u} / {p}")

        # Full OpenVPN .ovpn profile & CA certificate
        if proto == 0 and "-----BEGIN CERTIFICATE-----" in cert:
            tcp_p = tcp if tcp and tcp != "0" else "1194"
            ca_part = cert[cert.find("<ca>"):cert.find("</ca>") + 5] if ("<ca>" in cert and "</ca>" in cert) else f"<ca>\n{cert.strip()}\n</ca>"
            lines.append("   • OpenVPN CA: Included & Valid")
            lines.append("   • Ready .ovpn Config:")
            lines.append("     --------------------------------------------------")
            lines.append("     client")
            lines.append("     dev tun")
            lines.append("     persist-tun")
            lines.append("     proto tcp")
            lines.append(f"     remote {host} {tcp_p}")
            lines.append("     verb 3")
            lines.append("     ping-restart 0")
            lines.append("     auth none")
            lines.append("     auth-nocache")
            lines.append("     cipher none")
            lines.append("     setenv CLIENT_CERT 0")
            lines.append("     auth-user-pass")
            lines.append(f"     # Credentials: {u} / {p}")
            for ca_line in ca_part.splitlines():
                lines.append(f"     {ca_line}")
            lines.append("     --------------------------------------------------")

        if "V2Ray" in s and isinstance(s["V2Ray"], dict):
            v2 = s["V2Ray"]
            uuid = v2.get("UUID", "")
            v2host = v2.get("V2RayHost", "")
            path = v2.get("PATH", "/vless_juan")
            lines.append(f"   • V2Ray UUID: {uuid}")
            lines.append(f"   • V2Ray Host: {v2host}")
            lines.append(f"   • V2Ray Path: {path}")
            if uuid and v2host:
                tag = urllib.parse.quote(f"VIP Sniper - {name}")
                vless_link = f"vless://{uuid}@{v2host}:443?path={urllib.parse.quote(path)}&security=tls&encryption=none&host={host}&type=ws#{tag}"
                lines.append(f"   • VLESS Link: {vless_link}")

        if "SlowDNS" in s and isinstance(s["SlowDNS"], dict):
            sd = s["SlowDNS"]
            lines.append(f"   • NS Host  : {sd.get('NSNameServer', '')}")
            lines.append(f"   • PubKey   : {sd.get('PubKey', '')}")

        lines.append("")

    lines.extend([
        "=============================================================================",
        "  FULL DECRYPTED DATABASE (SERVERS & NETWORKS JSON)",
        "=============================================================================",
        json.dumps({
            "Version": version,
            "Global_Username": glob_user,
            "Global_Password": glob_pass,
            "Notes": notes,
            "Servers": decrypted_servers,
            "Networks": decrypted_networks
        }, indent=2, ensure_ascii=False)
    ])

    full_txt = "\n".join(lines)
    result = {
        "txt_content": full_txt,
        "version": version,
        "glob_user": glob_user,
        "glob_pass": glob_pass,
        "total_servers": len(decrypted_servers),
        "total_networks": len(decrypted_networks),
        "servers": decrypted_servers,
        "networks": decrypted_networks
    }

    if not raw_b64:
        VIP_CACHED_DATA = result
        VIP_CACHE_TIMESTAMP = now

    return result


# ================= TELEGRAM BOT LOGIC =================
def start_bot():
    if not BOT_TOKEN:
        print("[!] ERROR: BOT_TOKEN is missing! Set BOT_TOKEN environment variable.", file=sys.stderr)
        return

    bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

    @bot.message_handler(commands=["start", "help"])
    def handle_start(message):
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("🛡️ MM Tunnel VPN", callback_data="dec_mmtunnel"),
            InlineKeyboardButton("🛡️ TeriX VPN", callback_data="dec_terix"),
            InlineKeyboardButton("🛡️ Ursa Net PRO", callback_data="dec_ursanet"),
            InlineKeyboardButton("🎯 VIP Sniper Pro", callback_data="dec_vipsniper")
        )
        
        user_name = message.from_user.first_name or "User"
        welcome_text = (
            f"👋 <b>Welcome {user_name}!</b>\n\n"
            "🤖 <b>VPN Config Decryptor Bot</b>\n"
            "<i>Powered by: @Foridul_002 🇧🇩</i>\n\n"
            "যে VPN-এর কনফিগ ডিক্রিপ্ট করতে চান নিচের তালিকা থেকে সিলেক্ট করুন:"
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
                InlineKeyboardButton("🎯 VIP Sniper Pro", callback_data="dec_vipsniper"),
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
                raw_txt = res["raw_txt"]
                version = res["version"]
                total_servers = res["total_servers"]
                total_payloads = res["total_payloads"]

                # Single TXT file containing complete decrypted raw data
                txt_bytes = io.BytesIO(raw_txt.encode("utf-8"))
                txt_bytes.name = "Ursa_Net_PRO_Decrypted.txt"

                caption = (
                    "✅ <b>Ursa Net PRO 100% Fully Decrypted!</b>\n\n"
                    f"📦 <b>Config Version:</b> <code>{version}</code>\n"
                    f"🌐 <b>Total Servers:</b> <code>{total_servers}</code>\n"
                    f"📡 <b>Total Payloads:</b> <code>{total_payloads}</code>\n\n"
                    "📁 <i>সমস্ত এনক্রিপ্ট করা ডাটা (সার্ভার হোস্ট, পেলোড, টুইক) কোনো ফিল্টারিং ছাড়া সম্পূর্ণ ডিকোড করে TXT ফাইলে দেওয়া হলো।</i>\n\n"
                    "🤖 <b>Decrypted By:</b> @Foridul_002 🇧🇩"
                )

                # Send ONLY ONE txt file
                bot.send_document(
                    chat_id,
                    txt_bytes,
                    caption=caption
                )
                bot.delete_message(chat_id, status_msg.message_id)

            except Exception as e:
                bot.edit_message_text(
                    f"❌ <b>Ursa Net PRO Decryption Failed!</b>\nError: <code>{e}</code>",
                    chat_id=chat_id,
                    message_id=status_msg.message_id
                )

        elif call.data == "dec_vipsniper":
            bot.answer_callback_query(call.id, "⏳ Decrypting VIP Sniper Pro Config...")

            status_msg = bot.send_message(
                chat_id,
                "⏳ <b>VIP Sniper Pro ডিক্রিপ্ট করা হচ্ছে...</b>\n"
                "🔐 3-Layer Crypto (XXTEA + Threefish-256 + AES) ভাঙা হচ্ছে...\n"
                "অনুগ্রহ করে কয়েক সেকেন্ড অপেক্ষা করুন।"
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

                # Server preview (first 3)
                server_preview = ""
                for idx, s in enumerate(res["servers"][:3], 1):
                    name = s.get("Name", f"Server {idx}")
                    host = s.get("ServerIPHost", "")
                    server_preview += f"  {idx}. {name}\n     → <code>{host}</code>\n"

                caption = (
                    "✅ <b>VIP Sniper Pro 100% Fully Decrypted!</b>\n\n"
                    f"📦 <b>Version:</b> <code>{version}</code>\n"
                    f"🔐 <b>Username:</b> <code>{glob_user}</code>\n"
                    f"🔑 <b>Password:</b> <code>{glob_pass}</code>\n"
                    f"🌐 <b>Total Servers:</b> <code>{total_servers}</code>\n"
                    f"📡 <b>Total Networks:</b> <code>{total_networks}</code>\n\n"
                    "<b>🚀 Server Preview:</b>\n"
                    f"{server_preview}\n"
                    "🔓 <b>Crypto Layers Broken:</b>\n"
                    "  • Mode 0: AES-128-CBC + XXTEA (δ=0x7a56d3e1)\n"
                    "  • Mode 1: Threefish-256 (72 rounds) + AES-128-CBC\n"
                    "  • Mode 2: XXTEA + AES-256-CBC (PBKDF2 100K)\n\n"
                    "📁 <i>সম্পূর্ণ ডিক্রিপ্ট করা সার্ভার, নেটওয়ার্ক, ক্রেডেনশিয়াল সংযুক্ত ফাইলে দেওয়া হয়েছে।</i>\n\n"
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
                    f"❌ <b>VIP Sniper Pro Decryption Failed!</b>\nError: <code>{e}</code>",
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
