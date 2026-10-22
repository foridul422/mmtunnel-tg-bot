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

# ================= SENSEI TUNNEL 2026 DECRYPTION ENGINE =================
SENSEI_CERT_SHA256 = "a9e40f078e9361d7114ac6e236402ed1e15c6ba031f9cd6c73f8e7855d7688b0"
SENSEI_V3_SALT = "sensei::cfg::v3::2026"
SENSEI_AES_KEY = hashlib.sha256(f"{SENSEI_CERT_SHA256}:{SENSEI_V3_SALT}".encode("utf-8")).digest()

SENSEI_URL_CONFIGS = "https://raw.githubusercontent.com/JubairZ/sensei-tunnel-configs/master/sensei_configs_2026_v2.enc"
SENSEI_URL_BACKUP = "https://raw.githubusercontent.com/JubairZ/sensei-tunnel-configs/master/sensei_backup.enc"
SENSEI_URL_SETTINGS = "https://raw.githubusercontent.com/JubairZ/sensei-tunnel-configs/master/sensei_app_settings.enc"

SENSEI_CACHED_DATA = None
SENSEI_CACHE_TIMESTAMP = 0
SENSEI_CACHE_TTL = 300


def decrypt_sensei_v3(enc_str: str) -> str:
    """Decrypts sensei:v3: payload using AES-256-GCM."""
    prefix = "sensei:v3:"
    if enc_str.startswith(prefix):
        enc_str = enc_str[len(prefix):]
    raw = base64.b64decode(enc_str.strip())
    nonce = raw[:12]
    ciphertext_with_tag = raw[12:]
    return AESGCM(SENSEI_AES_KEY).decrypt(nonce, ciphertext_with_tag, None).decode("utf-8")


def decrypt_sensei_tunnel_live() -> Dict[str, Any]:
    """Fetch live configs and backup from official Sensei Tunnel repository and decrypt completely."""
    global SENSEI_CACHED_DATA, SENSEI_CACHE_TIMESTAMP
    now = time.time()
    if SENSEI_CACHED_DATA and (now - SENSEI_CACHE_TIMESTAMP < SENSEI_CACHE_TTL):
        return SENSEI_CACHED_DATA

    headers = {"User-Agent": "Dalvik/2.1.0 (Linux; U; Android 10; Build/QP1A.190711.020)"}

    r_cfg = requests.get(SENSEI_URL_CONFIGS, headers=headers, timeout=12)
    r_cfg.raise_for_status()
    configs = json.loads(decrypt_sensei_v3(r_cfg.text))

    backup = {}
    try:
        r_bak = requests.get(SENSEI_URL_BACKUP, headers=headers, timeout=12)
        if r_bak.status_code == 200:
            backup = json.loads(decrypt_sensei_v3(r_bak.text))
    except Exception:
        pass

    settings = {}
    try:
        r_set = requests.get(SENSEI_URL_SETTINGS, headers=headers, timeout=12)
        if r_set.status_code == 200:
            settings = json.loads(decrypt_sensei_v3(r_set.text))
    except Exception:
        pass

    servers = backup.get("servers", [])
    server_map = {s["id"]: s for s in servers if "id" in s}

    full_output = {
        "CREDITS": [
            {
                "Owner": "By: @Foridul_002 🇧🇩"
            }
        ],
        "configs": configs,
        "servers": servers,
        "settings": settings
    }
    full_txt = json.dumps(full_output, indent=2, ensure_ascii=False)
    result = {
        "txt_content": full_txt,
        "total_configs": len(configs),
        "total_servers": len(servers),
        "configs": configs,
        "servers": servers,
        "settings": settings
    }
    SENSEI_CACHED_DATA = result
    SENSEI_CACHE_TIMESTAMP = now
    return result


# ================= IZPH VPN PRO DECRYPTION ENGINE =================
IZPH_DATA_27D878 = bytes.fromhex('8968cb6e895105be625839ad9b9ba6ace8dcd4413d7c5ecfaa1069413ffeb044')
IZPH_IV_27D898   = bytes.fromhex('49e59fdf67eb479ce8b96c24d2495bd1')
IZPH_SALT_16     = bytes.fromhex('c27fd7bee17196d650530886cf4c24f5')
IZPH_FIXED_SALT  = bytes.fromhex('c27fd7bee17196d650530886cf4c24f52cac5abb8bff6ad3a48ebb10f4b1f632')
IZPH_KEY_16      = hashlib.sha256(IZPH_DATA_27D878).digest()[:16]

IZPH_THREEFISH_KEY = HKDF(algorithm=hashes.SHA256(), length=32, salt=IZPH_FIXED_SALT, info=b'', backend=default_backend()).derive(IZPH_DATA_27D878)
IZPH_AES_KEY_MODE1 = HKDF(algorithm=hashes.SHA256(), length=16, salt=IZPH_SALT_16, info=b'', backend=default_backend()).derive(IZPH_DATA_27D878)
IZPH_PBKDF2_KEY    = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=IZPH_FIXED_SALT, iterations=100000, backend=default_backend()).derive(IZPH_DATA_27D878)
IZPH_KEY_WORDS     = struct.unpack('<4Q', IZPH_THREEFISH_KEY)

IZPH_C240 = 0x1BD11BDAA9FC1A22
IZPH_MASK64 = 0xFFFFFFFFFFFFFFFF
IZPH_ROT = [
    [14, 16], [52, 57], [23, 40], [5, 37],
    [25, 33], [46, 12], [58, 22], [32, 32]
]
IZPH_DELTA = 0x7a56d3e1
IZPH_MASK32 = 0xffffffff

IZPH_LIVE_ENDPOINTS = [
    ("izph49", "https://raw.githubusercontent.com/kiranoble/config/main/izph49"),
    ("gcpvpn2026", "https://raw.githubusercontent.com/kiranoble/config/main/gcpvpn2026"),
    ("netflux", "https://raw.githubusercontent.com/kiranoble/config/main/netflux"),
    ("izphvpn2027", "https://raw.githubusercontent.com/kiranoble/config/main/izphvpn2027"),
    ("izphv18", "https://raw.githubusercontent.com/kiranoble/config/main/izphv18"),
    ("izph2026", "https://raw.githubusercontent.com/kiranoble/config/main/izph2026"),
]

IZPH_CACHED_DATA = None
IZPH_CACHE_TIMESTAMP = 0
IZPH_CACHE_TTL = 300


def _izph_bytes_to_words(b: bytes):
    n = (len(b) + 3) // 4
    words = [0] * n
    for i, byte in enumerate(b):
        words[i // 4] |= (byte & 0xff) << ((i % 4) * 8)
    return words


def _izph_words_to_bytes(words):
    total_len = words[-1]
    max_bytes = (len(words) - 1) * 4
    if total_len > max_bytes or total_len < max_bytes - 7:
        total_len = len(words) * 4
    res = bytearray()
    for i in range(total_len):
        if i // 4 < len(words):
            res.append((words[i // 4] >> ((i % 4) * 8)) & 0xff)
    return bytes(res)


def _izph_mx(sum_val, y, z, p, e, k):
    part1 = ((sum_val ^ y) + (k[(p & 3) ^ e] ^ z)) & IZPH_MASK32
    part2 = (((z >> 5 ^ (y << 2) & IZPH_MASK32)) + ((y >> 3 ^ (z << 4) & IZPH_MASK32))) & IZPH_MASK32
    return (part1 ^ part2) & IZPH_MASK32


def _izph_xxtea_decrypt(data_bytes: bytes, key_bytes: bytes) -> bytes:
    v = _izph_bytes_to_words(data_bytes)
    k_raw = bytearray(key_bytes[:16].ljust(16, b'\x00'))
    for idx, b in enumerate(k_raw):
        if b == 0:
            for j in range(idx, 16):
                k_raw[j] = 0
            break
    k = _izph_bytes_to_words(k_raw)[:4]
    n = len(v)
    if n <= 1:
        return data_bytes
    rounds = 6 + 52 // n
    sum_val = (rounds * IZPH_DELTA) & IZPH_MASK32
    y = v[0]
    while sum_val != 0:
        e = (sum_val >> 2) & 3
        for p in range(n - 1, 0, -1):
            z = v[p - 1]
            y = (v[p] - _izph_mx(sum_val, y, z, p, e, k)) & IZPH_MASK32
            v[p] = y
        z = v[n - 1]
        y = (v[0] - _izph_mx(sum_val, y, z, 0, e, k)) & IZPH_MASK32
        v[0] = y
        sum_val = (sum_val - IZPH_DELTA) & IZPH_MASK32
    return _izph_words_to_bytes(v)


def izph_decrypt_outer(raw_b64: str) -> str:
    """Outer Config JSON: AES-128-CBC + XXTEA + byte shift (-2)."""
    cipher_bytes = base64.b64decode(raw_b64.strip())
    cipher = Cipher(algorithms.AES(IZPH_KEY_16), modes.CBC(IZPH_IV_27D898), backend=default_backend())
    decryptor = cipher.decryptor()
    aes_dec = decryptor.update(cipher_bytes) + decryptor.finalize()
    pad_len = aes_dec[-1]
    if 1 <= pad_len <= 16:
        aes_dec = aes_dec[:-pad_len]
    tea = _izph_xxtea_decrypt(aes_dec, IZPH_KEY_16)
    final = bytearray((b - 2) & 0xff for b in tea)
    return final.decode('utf-8', errors='replace')


def izph_decrypt_mode0(b64_str: str) -> str:
    """Mode 0: Name, Ports, flag, CustomCert, UUID, PubKey."""
    if not b64_str or not isinstance(b64_str, str):
        return b64_str or ''
    try:
        cipher_bytes = base64.b64decode(b64_str.strip())
        cipher = Cipher(algorithms.AES(IZPH_KEY_16), modes.CBC(IZPH_IV_27D898), backend=default_backend())
        decryptor = cipher.decryptor()
        aes_dec = decryptor.update(cipher_bytes) + decryptor.finalize()
        pad_len = aes_dec[-1]
        if 1 <= pad_len <= 16:
            aes_dec = aes_dec[:-pad_len]
        tea = _izph_xxtea_decrypt(aes_dec, IZPH_KEY_16)
        final = bytearray((b - 2) & 0xff for b in tea)
        return final.decode('utf-8', errors='replace')
    except Exception:
        return b64_str


def _izph_ror64(x, n):
    return ((x >> n) | (x << (64 - n))) & IZPH_MASK64


def _izph_threefish_decrypt_block(block_bytes, key_words, tweak_words):
    v = list(struct.unpack('<4Q', block_bytes))
    k = list(key_words)
    k.append(IZPH_C240 ^ k[0] ^ k[1] ^ k[2] ^ k[3])
    t = list(tweak_words)
    t.append(t[0] ^ t[1])
    x6, x4, x5, x7 = v[0], v[1], v[2], v[3]
    s = 18
    x6 = (x6 - k[s % 5]) & IZPH_MASK64
    x4 = (x4 - (k[(s + 1) % 5] + t[s % 3])) & IZPH_MASK64
    x5 = (x5 - (k[(s + 2) % 5] + t[(s + 1) % 3])) & IZPH_MASK64
    x7 = (x7 - (k[(s + 3) % 5] + s)) & IZPH_MASK64
    for r in range(71, -1, -1):
        rot = IZPH_ROT[r % 8]
        if r % 2 == 1:
            x7 = (x7 ^ x6)
            x4 = (x4 ^ x5)
            x7 = _izph_ror64(x7, rot[0])
            x4 = _izph_ror64(x4, rot[1])
            x6 = (x6 - x7) & IZPH_MASK64
            x5 = (x5 - x4) & IZPH_MASK64
        else:
            x4 = (x4 ^ x6)
            x7 = (x7 ^ x5)
            x4 = _izph_ror64(x4, rot[0])
            x7 = _izph_ror64(x7, rot[1])
            x6 = (x6 - x4) & IZPH_MASK64
            x5 = (x5 - x7) & IZPH_MASK64
        if r % 4 == 0:
            s = r // 4
            x6 = (x6 - k[s % 5]) & IZPH_MASK64
            x4 = (x4 - (k[(s + 1) % 5] + t[s % 3])) & IZPH_MASK64
            x5 = (x5 - (k[(s + 2) % 5] + t[(s + 1) % 3])) & IZPH_MASK64
            x7 = (x7 - (k[(s + 3) % 5] + s)) & IZPH_MASK64
    return struct.pack('<4Q', x6, x4, x5, x7)


def izph_decrypt_mode1(b64_str: str) -> str:
    """Mode 1: ServerIPHost, SNIHost, Payload, V2RayHost, PATH."""
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
            block_idx = i // 32
            tweak = (block_idx, block_idx * 0x40)
            dec_blocks.extend(_izph_threefish_decrypt_block(block, IZPH_KEY_WORDS, tweak))
        dec_trimmed = dec_blocks.rstrip(b'\x00')
        if len(dec_trimmed) == 0:
            return b64_str
        cipher = Cipher(algorithms.AES(IZPH_AES_KEY_MODE1), modes.CBC(IZPH_IV_27D898), backend=default_backend())
        decryptor = cipher.decryptor()
        aes_dec = decryptor.update(dec_trimmed) + decryptor.finalize()
        pad_len = aes_dec[-1]
        if 1 <= pad_len <= 16:
            aes_dec = aes_dec[:-pad_len]
        return aes_dec.decode('utf-8', errors='replace')
    except Exception:
        return b64_str


def izph_decrypt_mode2(b64_str: str) -> str:
    """Mode 2: Username & Password."""
    if not b64_str or not isinstance(b64_str, str):
        return b64_str or ''
    try:
        cipher_bytes = base64.b64decode(b64_str.strip())
        xxtea_out = _izph_xxtea_decrypt(cipher_bytes, IZPH_PBKDF2_KEY[:16])
        iv = xxtea_out[:16]
        ct = xxtea_out[16:]
        cipher = Cipher(algorithms.AES(IZPH_PBKDF2_KEY), modes.CBC(iv), backend=default_backend())
        dec = cipher.decryptor()
        aes_dec = dec.update(ct) + dec.finalize()
        pad = aes_dec[-1]
        if 1 <= pad <= 16:
            aes_dec = aes_dec[:-pad]
        return aes_dec.decode('utf-8', errors='replace').strip()
    except Exception:
        return b64_str


def fetch_izph_live():
    candidate_endpoints = []
    # Check newer version numbers first (izph55 down to izph49)
    for num in range(55, 48, -1):
        candidate_endpoints.append((f"izph{num}", f"https://raw.githubusercontent.com/kiranoble/config/main/izph{num}"))
    for item in IZPH_LIVE_ENDPOINTS:
        if item not in candidate_endpoints:
            candidate_endpoints.append(item)

    best_config = None
    best_source = None
    best_ver_parts = []
    best_srv_count = 0

    headers = {"User-Agent": "Dalvik/2.1.0 (Linux; U; Android 10; Build/QP1A.190711.020)"}
    for name, url in candidate_endpoints:
        try:
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200 and len(r.text.strip()) > 1000:
                raw = r.text.strip()
                try:
                    dec = izph_decrypt_outer(raw)
                    obj = json.loads(dec)
                    ver = obj.get("Version", "0")
                    vparts = [int(p) for p in re.findall(r'\d+', str(ver))]
                    scount = len(obj.get("Servers", []))

                    if best_config is None:
                        best_config = raw
                        best_source = f"Live GitHub ({name})"
                        best_ver_parts = vparts
                        best_srv_count = scount
                    else:
                        max_l = max(len(vparts), len(best_ver_parts))
                        p1 = vparts + [0] * (max_l - len(vparts))
                        p2 = best_ver_parts + [0] * (max_l - len(best_ver_parts))
                        if p1 > p2 or (p1 == p2 and scount > best_srv_count):
                            best_config = raw
                            best_source = f"Live GitHub ({name})"
                            best_ver_parts = vparts
                            best_srv_count = scount
                    if best_ver_parts and best_ver_parts[0] >= 3108:
                        break
                except Exception:
                    continue
        except Exception:
            continue
    return best_config, best_source


def decrypt_izph_vpn_pro_live(raw_b64: str = None) -> Dict[str, Any]:
    global IZPH_CACHED_DATA, IZPH_CACHE_TIMESTAMP
    now = time.time()
    if not raw_b64 and IZPH_CACHED_DATA and (now - IZPH_CACHE_TIMESTAMP < IZPH_CACHE_TTL):
        return IZPH_CACHED_DATA

    source_name = "Live Cloud API"
    if not raw_b64:
        raw_b64, src = fetch_izph_live()
        if src:
            source_name = src
        else:
            local_fallbacks = [
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "e.rj"),
                "/home/foridul/.gemini/antigravity-ide/scratch/izph_vpn/e.rj",
            ]
            for p in local_fallbacks:
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        raw_b64 = f.read().strip()
                        source_name = f"Local APK Asset ({os.path.basename(p)})"
                        break
    if not raw_b64:
        raise ValueError("Could not fetch or locate IZPH VPN PRO encrypted config.")

    t0 = time.time()
    outer_str = izph_decrypt_outer(raw_b64)
    data = json.loads(outer_str)
    version = data.get("Version", "1.0.0")

    glob_user = izph_decrypt_mode2(data.get("Username")) or "izphy"
    glob_pass = izph_decrypt_mode2(data.get("Password")) or "izphy"

    all_servers = []
    for s in data.get("Servers", []):
        s_dec = {}
        for k, v in s.items():
            if k == "ServerIPHost":
                s_dec[k] = izph_decrypt_mode1(v)
            elif k in ["Username", "Password"]:
                s_dec[k] = izph_decrypt_mode2(v) or (glob_user if k == "Username" else glob_pass)
            elif k in ["Name", "Subname", "OpenVPNTCPPort", "OpenVPNSSLPort", "CustomCert", "ServerCert", "flag"]:
                s_dec[k] = izph_decrypt_mode0(v)
            elif k == "V2Ray" and isinstance(v, dict):
                v2 = {}
                for vk, vv in v.items():
                    if vk in ["V2RayHost", "PATH"]:
                        v2[vk] = izph_decrypt_mode1(vv)
                    elif vk in ["UUID", "DNSMode"]:
                        v2[vk] = izph_decrypt_mode0(vv)
                    else:
                        v2[vk] = vv
                s_dec[k] = v2
            elif k == "SlowDNS" and isinstance(v, dict):
                sd = {}
                for sdk, sdv in v.items():
                    if sdk in ["NSNameServer", "PubKey"]:
                        sd[sdk] = izph_decrypt_mode0(sdv)
                    else:
                        sd[sdk] = sdv
                s_dec[k] = sd
            else:
                s_dec[k] = v
        all_servers.append(s_dec)

    all_networks = []
    for n in data.get("Networks", []):
        n_dec = {}
        for k, v in n.items():
            if k in ["SNIHost", "Payload"]:
                n_dec[k] = izph_decrypt_mode1(v)
            elif k in ["Name", "Info", "TLSVersion", "SSCommand"]:
                n_dec[k] = izph_decrypt_mode0(v)
            elif k == "ProxySettings" and isinstance(v, dict):
                px = {}
                for pk, pv in v.items():
                    px[pk] = izph_decrypt_mode0(pv)
                n_dec[k] = px
            else:
                n_dec[k] = v
        all_networks.append(n_dec)

    elapsed = time.time() - t0

    # Categorize servers
    full_output = {
        "CREDITS": [
            {
                "Owner": "By: @Foridul_002 🇧🇩"
            }
        ],
        "Version": version,
        "Source": source_name,
        "Global_Username": glob_user,
        "Global_Password": glob_pass,
        "Servers": all_servers,
        "Networks": all_networks
    }
    full_txt = json.dumps(full_output, indent=2, ensure_ascii=False)
    result = {
        "txt_content": full_txt,
        "version": version,
        "source": source_name,
        "glob_user": glob_user,
        "glob_pass": glob_pass,
        "total_servers": len(all_servers),
        "total_networks": len(all_networks),
        "servers": all_servers,
        "networks": all_networks,
        "elapsed": elapsed
    }

    if not raw_b64:
        IZPH_CACHED_DATA = result
        IZPH_CACHE_TIMESTAMP = now

    return result
