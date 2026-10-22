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
                "Owner": "By @Foridul_002 🇧🇩",
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
            block_idx = i // 32
            tweak = (block_idx, block_idx * 0x40)
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

    full_output = {
        "CREDITS": [
            {
                "Owner": "By: @Foridul_002 🇧🇩"
            }
        ],
        "Version": version,
        "Global_Username": glob_user,
        "Global_Password": glob_pass,
        "Notes": notes,
        "Servers": decrypted_servers,
        "Networks": decrypted_networks
    }
    full_txt = json.dumps(full_output, indent=2, ensure_ascii=False)
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
