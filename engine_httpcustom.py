#!/usr/bin/env python3
"""
=============================================================================
  HTTP CUSTOM (.hc) DECRYPTION ENGINE
  By         : @Foridul_002 🇧🇩
  Supports   : Modern (Build 899 / n11 / XChaCha20Poly1305 + HKDF) & Legacy
=============================================================================
"""

import struct
import hmac
import hashlib
import json
from typing import Dict, Any, List, Optional
import nacl.bindings as nb

# ================= CRYPTOGRAPHIC CONSTANTS =================
PACKAGE = "xyz.easypro.httpcustom"
NONCE_BYTES = 24
TAG_BYTES = 16

CERTIFICATE_DIGEST = bytes.fromhex("95dd433d7e4a0be02d55cc62553edcfc8f077fe780be5a7da7f861c2558dc181")

# SHA-256 state vectors after native 64-byte ipad/opad blocks
IPAD_STATE = [0x82515a9a, 0xf6ec05fc, 0xf650b6cd, 0x523f8ce6, 0xedf419ec, 0x1d6d6573, 0x66ff1b89, 0xf40a0181]
OPAD_STATE = [0x82185b01, 0x35cb48be, 0xdb6c3846, 0xbd714ec5, 0x627728af, 0xdbaae4db, 0x463fbf8d, 0x88a24381]

K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
]


def _ror(x: int, n: int) -> int:
    return ((x >> n) | (x << (32 - n))) & 0xFFFFFFFF


def _sha256_compress(state: List[int], block: bytes) -> List[int]:
    w = list(struct.unpack(">16I", block))
    for i in range(16, 64):
        s0 = _ror(w[i - 15], 7) ^ _ror(w[i - 15], 18) ^ (w[i - 15] >> 3)
        s1 = _ror(w[i - 2], 17) ^ _ror(w[i - 2], 19) ^ (w[i - 2] >> 10)
        w.append((w[i - 16] + s0 + w[i - 7] + s1) & 0xFFFFFFFF)

    a, b, c, d, e, f, g, h = state
    for i in range(64):
        s1 = _ror(e, 6) ^ _ror(e, 11) ^ _ror(e, 25)
        ch = (e & f) ^ ((~e) & g)
        temp1 = (h + s1 + ch + K[i] + w[i]) & 0xFFFFFFFF
        s0 = _ror(a, 2) ^ _ror(a, 13) ^ _ror(a, 22)
        maj = (a & b) ^ (a & c) ^ (b & c)
        temp2 = (s0 + maj) & 0xFFFFFFFF
        h, g, f, e = g, f, e, (d + temp1) & 0xFFFFFFFF
        d, c, b, a = c, b, a, (temp1 + temp2) & 0xFFFFFFFF

    return [(state[idx] + v) & 0xFFFFFFFF for idx, v in enumerate([a, b, c, d, e, f, g, h])]


def _finish_hmac_state(state: List[int], data: bytes) -> bytes:
    padded = bytearray(data)
    padded.append(0x80)
    while len(padded) % 64 != 56:
        padded.append(0)
    padded.extend(struct.pack(">Q", (64 + len(data)) * 8))
    st = list(state)
    for off in range(0, len(padded), 64):
        st = _sha256_compress(st, bytes(padded[off : off + 64]))
    return struct.pack(">8I", *st)


def _derive_key(prefix: bytes, salt: bytes, info: bytes) -> bytes:
    material = b"\xe9" + CERTIFICATE_DIGEST + prefix
    inner = _finish_hmac_state(IPAD_STATE, material)
    ikm = _finish_hmac_state(OPAD_STATE, inner)
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()


# ================= MAIN DECRYPTION LOGIC =================
def decrypt_hc_file(raw_content: bytes) -> Dict[str, Any]:
    """
    Decrypts an HTTP Custom (.hc) configuration file and extracts:
    - Protocol (V2Ray, SSH, OpenVPN, etc.)
    - Host / IP
    - Port
    - Username / Password / UUID
    - SNI / Bug Host
    - Payloads / Custom Headers / WebSocket settings
    - Protection & Expiry Details
    """
    # 1. Unicode code-point mapping to recover raw ciphertext bytes
    try:
        text = raw_content.decode("utf-8")
        mapped = bytes([ord(c) for c in text])
    except Exception:
        mapped = raw_content

    if len(mapped) < NONCE_BYTES + TAG_BYTES:
        raise ValueError("Invalid .hc file: File size is too small.")

    # 2. Derive Outer Seal Key & Decrypt Envelope
    seal_key = _derive_key(
        f"hc-envelope-seal-v4 {PACKAGE}".encode(),
        b"hc-envelope-seal-salt-v4",
        b"hc-envelope-seal-info-v4"
    )

    nonce = mapped[:NONCE_BYTES]
    ciphertext = mapped[NONCE_BYTES:]
    aad = f"HCX4|{PACKAGE}|1".encode()

    try:
        plaintext = nb.crypto_aead_xchacha20poly1305_ietf_decrypt(ciphertext, aad, nonce, seal_key)
    except Exception as e:
        raise ValueError(f"Failed to decrypt .hc envelope. Ensure this is a valid HTTP Custom config. Error: {e}")

    try:
        envelope = json.loads(plaintext.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to parse decrypted envelope JSON: {e}")

    container_version = envelope.get("b", 10)
    key_scheme = envelope.get("e", "n11")
    parts = ",".join(envelope.get("f", []))
    reader = envelope.get("n")
    suffix = f"|{reader}" if reader else ""
    session_aad = f"HCCFG|{container_version}|XCHACHA20P1305|NATIVE-HKDF-SHA256|{key_scheme}|{PACKAGE}|1|{parts}|0{suffix}".encode()
    salt = bytes.fromhex(envelope["g"])

    prefix = b"HCCFG\x00" + PACKAGE.encode() + b"\x001\x00" + parts.encode() + b"\x00"
    if reader:
        prefix += f"{reader}\0".encode()
    prefix += salt
    info = f"app-config|{key_scheme}|{PACKAGE}|1|{parts}{suffix}".encode()

    session_key = _derive_key(prefix, salt, info)

    def _open(s_nonce_hex: str, s_ct_hex: str, ctx: str) -> bytes:
        n = bytes.fromhex(s_nonce_hex)
        ct = bytes.fromhex(s_ct_hex)
        a = session_aad + b"\x00" + ctx.encode()
        return nb.crypto_aead_xchacha20poly1305_ietf_decrypt(ct, a, n, session_key)

    # 3. Decrypt Manifest
    manifest_sec = envelope.get("i", {})
    manifest_raw = _open(manifest_sec["b"], manifest_sec["c"], manifest_sec["a"])
    manifest = json.loads(manifest_raw.decode("utf-8"))

    creator = manifest.get("l") or manifest.get("legacyCreatorLabel") or "Unknown"
    protections = manifest.get("g", {})

    # 4. Decrypt Profile Sections
    profiles = []
    sections = envelope.get("j", [])

    for sec in sections:
        sec_id = sec.get("a", "s1")
        sec_plain = _open(sec["b"], sec["c"], sec_id)

        # Handle HPR1 runtime wrapper if present
        if sec_plain.startswith(b"HPR1"):
            r_nonce = sec_plain[4 : 4 + NONCE_BYTES]
            r_ct = sec_plain[4 + NONCE_BYTES :]
            r_aad = session_aad + b"\x00" + f"{sec_id}:r".encode()
            sec_plain = nb.crypto_aead_xchacha20poly1305_ietf_decrypt(r_ct, r_aad, r_nonce, session_key)

        # Handle HPC1 profile binary structure
        if sec_plain.startswith(b"HPC1\0\0\0\x0b"):
            buf = sec_plain[8:]
            fields = {}
            for fn in ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k"]:
                if fn == "j":
                    val = struct.unpack(">q", buf[:8])[0]
                    buf = buf[8:]
                elif fn in ["d", "i"]:
                    val = struct.unpack(">i", buf[:4])[0]
                    buf = buf[4:]
                else:
                    length = struct.unpack(">I", buf[:4])[0]
                    val = buf[4 : 4 + length].decode("utf-8", errors="ignore")
                    buf = buf[4 + length :]
                fields[fn] = val

            # Parse configJson inside field 'h' if present
            raw_h = fields.get("h", "")
            try:
                if raw_h and (raw_h.startswith("{") or raw_h.startswith("[")):
                    fields["parsed_config"] = json.loads(raw_h)
            except Exception:
                pass

            profiles.append(fields)

    # 5. Build Human-Readable & Raw Text Output
    primary_profile = profiles[0] if profiles else {}
    protocol = primary_profile.get("b") or parts or "HTTP Custom"
    host = primary_profile.get("c") or "N/A"
    port = primary_profile.get("d") or 0
    name = primary_profile.get("a") or "Config"
    sni = primary_profile.get("g") or "None"
    notes = protections.get("v") or protections.get("note") or "None"

    # Format output text file
    lines = [
        "=============================================================================",
        "  HTTP CUSTOM (.hc) 100% FULLY DECRYPTED CONFIGURATION",
        "  By         : @Foridul_002 🇧🇩",
        "  Status     : UNLOCKED & EXTRACTED LIVE",
        "=============================================================================",
        "",
        "📋 [SUMMARY]",
        f"• Creator Label    : {creator}",
        f"• Profile Name     : {name}",
        f"• Tunnel Protocol  : {protocol}",
        f"• Server Host / IP : {host}",
        f"• Server Port      : {port}",
        f"• SNI / Bug Host   : {sni}",
        f"• Notes / Remarks  : {notes.strip()}",
        "",
        "🔒 [SECURITY & PROTECTION FLAGS]",
        f"• Access Mode      : {protections.get('a', 'default')}",
        f"• Expiry Enabled   : {protections.get('c', False)}",
        f"• Block Root       : {protections.get('m', False)}",
        f"• Mobile Data Only : {protections.get('l', False)}",
        "",
        "📁 [FULL DECRYPTED RAW PROFILES (JSON)]",
        json.dumps(profiles, indent=2, ensure_ascii=False),
        "",
        "⚙️ [FULL DECRYPTED MANIFEST METADATA]",
        json.dumps(manifest, indent=2, ensure_ascii=False),
        "",
        "=============================================================================",
        "👑 By: @Foridul_002 🇧🇩"
    ]

    txt_content = "\n".join(lines)

    return {
        "txt_content": txt_content,
        "protocol": protocol,
        "server_host": host,
        "server_port": port,
        "creator": creator,
        "name": name,
        "version": f"v{container_version} ({key_scheme})",
        "total_profiles": len(profiles),
        "notes": notes.strip()
    }


if __name__ == "__main__":
    import sys
    test_file = sys.argv[1] if len(sys.argv) > 1 else "/home/foridul/Downloads/Telegram Desktop/AISO.hc"
    with open(test_file, "rb") as f:
        res = decrypt_hc_file(f.read())
        print(res["txt_content"][:600])
        print("\n[+] Decrypted successfully!")
