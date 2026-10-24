#!/usr/bin/env python3
"""
=============================================================================
  BEKAR VPN (com.bekarvpn.org) Full Live Config Decryptor & Extractor
  By: @Foridul_002 🇧🇩
=============================================================================
"""

import urllib.request
import json
import base64
import os
import sys
import time

DELTA = 772515655
KEY_STR = '4669'
PASS_INT = 4669

BEKAR_LIVE_URL = "https://raw.githubusercontent.com/VPN619/Bekar/refs/heads/main/meaow.hs"

# In-memory Cache to eliminate lag & respond instantly
BEKAR_CACHED_DATA = None
BEKAR_CACHE_TIMESTAMP = 0
BEKAR_CACHE_TTL = 300  # 5 minutes cache


def _mx(sum_val, y, z, p, e, k):
    return (((z >> 5 ^ y << 2) + (y >> 3 ^ z << 4)) ^ ((sum_val ^ y) + (k[(p & 3) ^ e] ^ z))) & 0xFFFFFFFF


def _fix_key(k_bytes):
    if len(k_bytes) == 16:
        return k_bytes
    if len(k_bytes) < 16:
        return k_bytes + b'\x00' * (16 - len(k_bytes))
    return k_bytes[:16]


def _to_int_array(b_bytes, include_len=False):
    length = (len(b_bytes) >> 2) if (len(b_bytes) & 3) == 0 else (len(b_bytes) >> 2) + 1
    if include_len:
        arr = [0] * (length + 1)
        arr[length] = len(b_bytes)
    else:
        arr = [0] * length
    for i in range(len(b_bytes)):
        arr[i >> 2] |= (b_bytes[i] & 0xFF) << ((i & 3) << 3)
    return arr


def _to_byte_array(arr, check_len=True):
    length = len(arr) << 2
    if check_len:
        m = arr[-1]
        m2 = length - 4
        if m < length - 7 or m > m2:
            return None
        length = m
    out = bytearray(length)
    for i in range(length):
        out[i] = (arr[i >> 2] >> ((i & 3) << 3)) & 0xFF
    return bytes(out)


def xxtea_decrypt(cipher_bytes, key_bytes):
    if len(cipher_bytes) == 0:
        return cipher_bytes
    v = _to_int_array(cipher_bytes, False)
    k = _to_int_array(_fix_key(key_bytes), False)
    n = len(v)
    if n <= 1:
        return None
    rounds = (52 // n) + 6
    sum_val = (rounds * DELTA) & 0xFFFFFFFF
    y = v[0]
    while sum_val != 0:
        e = (sum_val >> 2) & 3
        p = n - 1
        while p > 0:
            z = v[p - 1]
            v[p] = (v[p] - _mx(sum_val, y, z, p, e, k)) & 0xFFFFFFFF
            y = v[p]
            p -= 1
        z = v[n - 1]
        v[0] = (v[0] - _mx(sum_val, y, z, 0, e, k)) & 0xFFFFFFFF
        y = v[0]
        sum_val = (sum_val - DELTA) & 0xFFFFFFFF
    return _to_byte_array(v, True)


def _de2(text, shift=PASS_INT):
    out = []
    for c in text:
        out.append(chr((ord(c) - shift) & 0xFFFF))
    raw = ''.join(out)
    return raw.encode('utf-16', 'surrogatepass').decode('utf-16', errors='ignore')


def show_json(b64_str):
    if not isinstance(b64_str, str) or len(b64_str.strip()) < 8:
        return b64_str
    try:
        raw = base64.b64decode(b64_str.strip())
        dec = xxtea_decrypt(raw, KEY_STR.encode('utf-8'))
        if not dec:
            return b64_str
        s = dec.decode('utf-8', errors='ignore')
        res = _de2(_de2(s, PASS_INT), PASS_INT)
        return res
    except Exception:
        return b64_str


def recursive_decrypt(obj):
    if isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            if isinstance(v, str):
                dec = show_json(v)
                new_dict[k] = dec if dec else v
            else:
                new_dict[k] = recursive_decrypt(v)
        return new_dict
    elif isinstance(obj, list):
        return [recursive_decrypt(item) for item in obj]
    else:
        return obj


def decrypt_bekar_vpn_live(raw_b64: str = None) -> dict:
    global BEKAR_CACHED_DATA, BEKAR_CACHE_TIMESTAMP
    now = time.time()
    if not raw_b64 and BEKAR_CACHED_DATA and (now - BEKAR_CACHE_TIMESTAMP < BEKAR_CACHE_TTL):
        return BEKAR_CACHED_DATA

    if not raw_b64:
        live_urls = [
            BEKAR_LIVE_URL,
            "https://raw.githubusercontent.com/VPN619/Bekar/main/Bekarvpn.hs",
            "https://raw.githubusercontent.com/VPN619/Bekar/main/Beeeekkkkkaaaaarrrrrr"
        ]
        last_err = None
        for u in live_urls:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "Dalvik/2.1.0"})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    raw_b64 = resp.read().decode("utf-8").strip()
                if raw_b64 and len(raw_b64) > 100:
                    break
            except Exception as e:
                last_err = e

        if not raw_b64:
            fallbacks = [
                "/home/foridul/Downloads/Telegram Desktop/Result_BEKAR_VPN.txt",
                os.path.expanduser("~/Downloads/Telegram Desktop/Result_BEKAR_VPN.txt")
            ]
            for fb in fallbacks:
                if os.path.exists(fb):
                    try:
                        with open(fb, "r", encoding="utf-8") as f:
                            cached_json = json.load(f)
                        output_dict = {"CREDITS": [{"Owner": "By: @Foridul_002 🇧🇩"}]}
                        output_dict.update(cached_json)
                        txt_content = json.dumps(output_dict, indent=2, ensure_ascii=False)
                        res = {
                            "txt_content": txt_content,
                            "version": cached_json.get("Version", "33"),
                            "total_servers": len(cached_json.get("Servers", [])),
                            "total_http_networks": len(cached_json.get("HTTPNetworks", [])),
                            "total_ssl_networks": len(cached_json.get("SSLNetworks", [])),
                            "release_notes": cached_json.get("ReleaseNotes", ""),
                            "file_name": cached_json.get("FileName", "bekarvpn")
                        }
                        BEKAR_CACHED_DATA = res
                        BEKAR_CACHE_TIMESTAMP = now
                        return res
                    except Exception:
                        pass
            if last_err:
                raise last_err

    outer_json_str = show_json(raw_b64)
    data = json.loads(outer_json_str)

    decrypted_data = recursive_decrypt(data)

    output_dict = {
        "CREDITS": [
            {
                "Owner": "By: @Foridul_002 🇧🇩"
            }
        ]
    }
    output_dict.update(decrypted_data)

    txt_content = json.dumps(output_dict, indent=2, ensure_ascii=False)

    total_servers = len(decrypted_data.get("Servers", []))
    total_http = len(decrypted_data.get("HTTPNetworks", []))
    total_ssl = len(decrypted_data.get("SSLNetworks", []))
    version = decrypted_data.get("Version", "N/A")
    release_notes = decrypted_data.get("ReleaseNotes", "")

    res = {
        "txt_content": txt_content,
        "version": version,
        "total_servers": total_servers,
        "total_http_networks": total_http,
        "total_ssl_networks": total_ssl,
        "release_notes": release_notes,
        "file_name": decrypted_data.get("FileName", "bekarvpn")
    }

    BEKAR_CACHED_DATA = res
    BEKAR_CACHE_TIMESTAMP = now
    return res


if __name__ == "__main__":
    print("[*] Decrypting BEKAR VPN live configuration...")
    res = decrypt_bekar_vpn_live()
    out_file = "/home/foridul/.gemini/antigravity-ide/scratch/Bekar_VPN_Decrypted_Servers.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(res["txt_content"])
    print(f"Decrypted BEKAR VPN successfully!")
    print(f"Version: {res['version']}")
    print(f"Total Servers: {res['total_servers']}")
    print(f"HTTP Networks: {res['total_http_networks']}")
    print(f"SSL Networks: {res['total_ssl_networks']}")
    print(f"Release Notes: {res['release_notes']}")
    print(f"Saved to: {out_file}")
