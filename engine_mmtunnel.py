#!/usr/bin/env python3
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
from argon2.low_level import hash_secret_raw, Type
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

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
                "Owner": "By @Foridul_002 🇧🇩",
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

    formatted_txt = f"# By: @Foridul_002 🇧🇩\n\n{yaml_raw}"
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
