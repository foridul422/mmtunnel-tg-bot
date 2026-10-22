#!/usr/bin/env python3
"""
=============================================================================
  Boost VPN (com.boostvpn.net) Full Live Config Decryptor & Extractor
  By: @Foridul_002 🇧🇩
=============================================================================
"""

import urllib.request
import json
import base64
import os
import sys

DELTA = 772515655
KEY_STR = '4669'
PASS_INT = 4669

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

def _de2(text, shift=4669):
    out = []
    for c in text:
        out.append(chr((ord(c) - shift) & 0xFFFF))
    return ''.join(out)

def show_json(b64_str):
    if not isinstance(b64_str, str) or not b64_str.strip():
        return b64_str
    try:
        raw = base64.b64decode(b64_str.strip())
        dec = xxtea_decrypt(raw, KEY_STR.encode('utf-8'))
        if not dec:
            return b64_str
        s = dec.decode('utf-8', errors='ignore')
        return _de2(_de2(s, PASS_INT), PASS_INT)
    except:
        return b64_str

def decrypt_field_if_needed(val):
    if isinstance(val, str) and len(val) >= 20 and not val.startswith("http") and not " " in val:
        dec = show_json(val)
        if dec and dec != val and any(c.isprintable() for c in dec):
            return dec
    return val

def recursive_decrypt(obj):
    if isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            if k in ['ServerIP', 'ServerCloudFront', 'ServerHTTP', 'Username', 'Password', 
                     'NetworkPayload', 'SquidProxy', 'ovpnCertificate', 'SSLSNI', 'SSLPayload',
                     'config_url', 'account_api', 'upload_get_api', 'upload_post_api', 'AppConfPass']:
                if isinstance(v, str) and v.strip():
                    new_dict[k] = show_json(v)
                else:
                    new_dict[k] = v
            else:
                new_dict[k] = recursive_decrypt(v)
        return new_dict
    elif isinstance(obj, list):
        return [recursive_decrypt(item) for item in obj]
    else:
        return obj

def decrypt_boost_vpn_live(raw_b64: str = None) -> dict:
    if not raw_b64:
        live_url = "https://raw.githubusercontent.com/doneeone7/first/refs/heads/main/default.hs"
        try:
            req = urllib.request.Request(live_url, headers={"User-Agent": "Dalvik/2.1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw_b64 = resp.read().decode("utf-8").strip()
        except Exception as e:
            fallback = "/home/foridul/.gemini/antigravity-ide/scratch/boost_vpn/decompiled/resources/res/raw/default_local.hs"
            if os.path.exists(fallback):
                with open(fallback, "r", encoding="utf-8") as f:
                    raw_b64 = f.read().strip()
            else:
                raise e

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

    return {
        "txt_content": txt_content,
        "version": version,
        "total_servers": total_servers,
        "total_http_networks": total_http,
        "total_ssl_networks": total_ssl,
        "file_name": decrypted_data.get("FileName", "boostvpn")
    }

if __name__ == "__main__":
    res = decrypt_boost_vpn_live()
    out_file = "/home/foridul/.gemini/antigravity-ide/scratch/BoostVPN_Decrypted_Servers.txt"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(res["txt_content"])
    print(f"Decrypted Boost VPN successfully! Version: {res['version']}, Servers: {res['total_servers']}, HTTP Networks: {res['total_http_networks']}, SSL Networks: {res['total_ssl_networks']}")
    print(f"Saved to: {out_file}")
