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

# ================= IPTUNNEL LIVE DECRYPTION ENGINE =================
IPTUNNEL_KEY = b"8f3c7a1e6d2b4c9f0a5e1d7c3b8f6a2e9c4d1f7b0a3e6c2d5f8a1b9c7e4d2a6"
IPTUNNEL_SECRET = b"4f2ce69b35fc8b67d4e12a14f8e3af5f0caab3c55d5bbd474f74fef076729e2e"
IPTUNNEL_CACHED_DATA = None
IPTUNNEL_CACHE_TIMESTAMP = 0
IPTUNNEL_CACHE_TTL = 300

def _iptunnel_a(i, i2, i3, i4, iArr, i5):
    t1 = ((i3 >> 5) & 0x07FFFFFF) ^ ((i2 << 2) & 0xFFFFFFFF)
    t2 = ((i2 >> 3) & 0x1FFFFFFF) ^ ((i3 << 4) & 0xFFFFFFFF)
    part2 = (t1 + t2) & 0xFFFFFFFF
    part1 = ((i ^ i2) + (iArr[(i4 & 3) ^ i5] ^ i3)) & 0xFFFFFFFF
    return part1 ^ part2

def _iptunnel_D(iArr, z=True):
    length = len(iArr) << 2
    if z:
        i = iArr[-1]
        i2 = length - 4
        if (length - 7) <= i <= i2:
            length = i
        else:
            return None
    bArr = bytearray(length)
    for i3 in range(length):
        bArr[i3] = (iArr[i3 >> 2] >> ((i3 & 3) << 3)) & 0xFF
    return bytes(bArr)

def _iptunnel_E(bArr, z=False):
    length = (len(bArr) >> 2) if (len(bArr) & 3) == 0 else (len(bArr) >> 2) + 1
    if z:
        iArr = [0] * (length + 1)
        iArr[length] = len(bArr)
    else:
        iArr = [0] * length
    for i, b in enumerate(bArr):
        i2 = i >> 2
        iArr[i2] = iArr[i2] | ((b & 0xFF) << ((i & 3) << 3))
    return iArr

def xxtea_decrypt_iptunnel(bArr, bArr2, trimLen=True):
    if len(bArr) == 0:
        return bArr
    E_arr = _iptunnel_E(bArr, False)
    if len(bArr2) != 16:
        bArr3 = bytearray(16)
        if len(bArr2) < 16:
            bArr3[:len(bArr2)] = bArr2
        else:
            bArr3[:] = bArr2[:16]
        bArr2 = bytes(bArr3)
    E2_arr = _iptunnel_E(bArr2, False)
    length = len(E_arr)
    i = length - 1
    if i >= 1:
        i2 = (52 // length) + 6
        i3 = E_arr[0]
        DELTA = (-1703701580) & 0xFFFFFFFF
        i4 = (i2 * (-1703701580)) & 0xFFFFFFFF
        while i4 != 0:
            i5 = (i4 >> 2) & 3
            i6 = i3
            i7 = i
            while i7 > 0:
                i6 = (E_arr[i7] - _iptunnel_a(i4, i6, E_arr[i7 - 1], i7, E2_arr, i5)) & 0xFFFFFFFF
                E_arr[i7] = i6
                i7 -= 1
            i3 = (E_arr[0] - _iptunnel_a(i4, i6, E_arr[i], i7, E2_arr, i5)) & 0xFFFFFFFF
            E_arr[0] = i3
            i4 = (i4 - DELTA) & 0xFFFFFFFF
    return _iptunnel_D(E_arr, trimLen)

def decrypt_iptunnel_live():
    global IPTUNNEL_CACHED_DATA, IPTUNNEL_CACHE_TIMESTAMP
    now = time.time()
    if IPTUNNEL_CACHED_DATA and (now - IPTUNNEL_CACHE_TIMESTAMP < IPTUNNEL_CACHE_TTL):
        return IPTUNNEL_CACHED_DATA

    android_id = "a1b2c3d4e5f60718"
    device_id = hashlib.md5(android_id.encode("utf-8")).hexdigest()
    path_query = "/api/v2/index.php?action=app_config"
    url_str = f"https://iptunnel.internetshub.com{path_query}"
    ts = int(time.time())
    nonce = f"{random.randint(0, 0x7FFFFFFFFFFFFFFF):016x}"
    str5 = f"GET\n{path_query}\n{device_id}\n{ts}\n{nonce}"
    sig = hmac.new(IPTUNNEL_SECRET, str5.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {
        "X-App-Id": "iptunnel-android",
        "X-App-Device": device_id,
        "X-App-Ts": str(ts),
        "X-App-Nonce": nonce,
        "X-App-Auth-Mode": "legacy_v1",
        "X-App-Sign": sig,
        "X-App-Version": "49",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 10; Build/QP1A.190711.020)"
    }
    req = urllib.request.Request(url_str, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read().decode("utf-8").strip()

    dec = xxtea_decrypt_iptunnel(base64.b64decode(data), IPTUNNEL_KEY, True)
    raw_json = json.loads(dec.decode("utf-8"))

    output_dict = {
        "CREDITS": [
            {
                "Owner": "By: @Foridul_002 🇧🇩"
            }
        ]
    }
    output_dict.update(raw_json)

    txt_content = json.dumps(output_dict, indent=2, ensure_ascii=False)
    res = {
        "txt_content": txt_content,
        "version": raw_json.get("Version", "N/A"),
        "total_servers": len(raw_json.get("Servers", [])),
        "total_tweaks": len(raw_json.get("Tweaks", []))
    }
    IPTUNNEL_CACHED_DATA = res
    IPTUNNEL_CACHE_TIMESTAMP = now
    return res
