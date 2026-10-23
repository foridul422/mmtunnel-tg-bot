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
import base64
import urllib.parse
import datetime
from typing import Dict, Any, List, Optional
import re
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


def html_escape(text: Any) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ================= MAIN DECRYPTION LOGIC =================
def decrypt_hc_file(raw_content: bytes) -> Dict[str, Any]:
    """
    Decrypts an HTTP Custom (.hc) configuration file and extracts:
    - Protocol (V2Ray VLESS/VMess/Trojan, SSH, OpenVPN)
    - Host / IP & Port
    - Username / Password / UUID
    - SNI / Bug Host
    - Payloads / Custom Headers / WebSocket settings
    - Protection & Expiry Details
    - Styled Direct Message string ready for Telegram
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

    # 5. Extract Rich Connection Details across ALL profiles
    primary_profile = profiles[0] if profiles else {}

    v2ray_prof = None
    ssh_prof = None
    payload_prof = None

    for prof in profiles:
        p_proto = str(prof.get("b", "")).lower()
        p_raw_h = str(prof.get("h", ""))
        p_e = str(prof.get("e", ""))

        if "v2ray" in p_proto or "vmess" in p_proto or "vless" in p_proto:
            v2ray_prof = prof
        elif p_raw_h and ("\"vnext\"" in p_raw_h or "\"outbounds\"" in p_raw_h or "\"vless\"" in p_raw_h or "\"vmess\"" in p_raw_h):
            v2ray_prof = prof
        elif re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", p_e):
            v2ray_prof = prof

        if "ssh" in p_proto or (prof.get("e") and prof.get("f") and not re.search(r"[0-9a-fA-F]{8}-", prof.get("e", ""))):
            ssh_prof = prof

        if p_raw_h and not p_raw_h.strip().startswith("{") and len(p_raw_h.strip()) > 5:
            payload_prof = prof

    target_profile = v2ray_prof or ssh_prof or primary_profile

    name = target_profile.get("a", "Config")
    protocol = target_profile.get("b") or parts or "HTTP Custom"
    host = target_profile.get("c", "N/A")
    port = target_profile.get("d", 0)
    username = target_profile.get("e", "")
    password = target_profile.get("f", "")
    sni = target_profile.get("g", "")
    raw_h = target_profile.get("h", "")
    inject_flag = str(target_profile.get("k", "0"))
    inject_mode = "PROXY" if inject_flag == "1" else "DIRECT"
    proxy_val = ""
    notes = protections.get("v") or protections.get("note") or ""

    custom_payload = ""
    if payload_prof and payload_prof != target_profile:
        custom_payload = payload_prof.get("h", "")

    v2ray_proto = ""
    uuid = ""
    network = "ws"
    ws_path = ""
    ws_host = ""
    tls_security = "none"
    v2ray_link = ""
    is_tls = False
    alter_id = "0"

    all_raw_h = [p.get("h", "") for p in profiles if p.get("h")]
    all_raw_e = [p.get("e", "") for p in profiles if p.get("e")]
    all_raw_g = [p.get("g", "") for p in profiles if p.get("g")]
    all_text = " ".join(all_raw_h + all_raw_e + all_raw_g)

    # 1. Parse JSON configs inside any profile
    for h_candidate in all_raw_h:
        if h_candidate and (h_candidate.strip().startswith("{") or h_candidate.strip().startswith("[")):
            try:
                v2ray_data = json.loads(h_candidate)
                if v2ray_data.get("remarks"):
                    name = v2ray_data["remarks"]

                outbounds = v2ray_data.get("outbounds", [])
                for ob in outbounds:
                    ob_proto = ob.get("protocol", "").lower()
                    if ob_proto in ["vless", "vmess", "trojan", "shadowsocks"]:
                        v2ray_proto = ob_proto.upper()
                        settings = ob.get("settings", {})
                        vnext = settings.get("vnext", [])
                        if vnext:
                            v_srv = vnext[0]
                            host = v_srv.get("address") or host
                            port = v_srv.get("port") or port
                            users = v_srv.get("users", [])
                            if users:
                                u0 = users[0]
                                uuid = u0.get("id") or u0.get("password") or uuid
                                alter_id = str(u0.get("alterId", "0"))
                                if u0.get("security"):
                                    tls_security = u0.get("security")
                                elif u0.get("encryption"):
                                    tls_security = u0.get("encryption")

                        servers = settings.get("servers", [])
                        if servers:
                            s_srv = servers[0]
                            host = s_srv.get("address") or host
                            port = s_srv.get("port") or port
                            users = s_srv.get("users", [])
                            if users:
                                uuid = users[0].get("password") or users[0].get("id") or uuid
                            elif s_srv.get("password"):
                                password = s_srv.get("password")

                        stream = ob.get("streamSettings", {})
                        if stream.get("network"):
                            network = stream.get("network").lower()
                        stream_sec = stream.get("security", "")
                        if stream_sec:
                            tls_security = stream_sec
                        if stream_sec.lower() == "tls" or port in [443, 8443, 2053, 2083, 2087, 2096]:
                            is_tls = True

                        ws_settings = stream.get("wsSettings", {})
                        if ws_settings.get("path"):
                            ws_path = ws_settings.get("path")
                        ws_headers = ws_settings.get("headers", {})
                        if ws_headers.get("Host"):
                            ws_host = ws_headers.get("Host")

                        tls_settings = stream.get("tlsSettings", {})
                        if tls_settings.get("serverName"):
                            sni = tls_settings.get("serverName")
                        break
            except Exception:
                pass
        else:
            if not custom_payload and h_candidate.strip():
                custom_payload = h_candidate.strip()

    # 2. Comprehensive Fallback for UUID
    if not uuid:
        for e_cand in all_raw_e:
            uuid_match = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", e_cand)
            if uuid_match:
                uuid = uuid_match.group(0)
                break
            elif len(e_cand) == 36 and e_cand.count("-") == 4:
                uuid = e_cand
                break

    if not uuid:
        uuid_match = re.search(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", all_text)
        if uuid_match:
            uuid = uuid_match.group(0)

    # 3. Comprehensive Fallback for PATH
    if not ws_path:
        path_m = re.search(r"\"path\"\s*:\s*\"([^\"]+)\"", all_text)
        if path_m:
            ws_path = path_m.group(1)
        elif custom_payload:
            payload_path = re.search(r"(?:GET|POST|CONNECT|HEAD)\s+([/\w\.\-\?=&%]+)", custom_payload)
            if payload_path and payload_path.group(1).startswith("/"):
                ws_path = payload_path.group(1)
        if not ws_path and (uuid or "v2ray" in str(protocol).lower() or v2ray_proto):
            ws_path = "/"

    # 4. Comprehensive Fallback for HOST Header / SNI
    if not ws_host:
        host_m = re.search(r"\"Host\"\s*:\s*\"([^\"]+)\"", all_text, re.IGNORECASE)
        if host_m:
            ws_host = host_m.group(1)
        elif custom_payload:
            pl_host = re.search(r"Host:\s*([^\r\n\[\s]+)", custom_payload, re.IGNORECASE)
            if pl_host:
                ws_host = pl_host.group(1)
        if not ws_host and sni and sni != "None":
            ws_host = sni

    # 5. Determine Active Protocol
    is_v2ray = bool(uuid or "v2ray" in str(protocol).lower() or v2ray_proto or "v2ray" in str(parts).lower())
    if is_v2ray:
        if v2ray_proto:
            active_proto = v2ray_proto
        elif "vless" in all_text.lower():
            active_proto = "VLESS"
        elif "trojan" in all_text.lower():
            active_proto = "TROJAN"
        else:
            active_proto = "VMESS"
    elif "ssh" in str(protocol).lower() or "ssh" in str(parts).lower():
        active_proto = "SSH"
    elif "udp" in str(protocol).lower() or "udp-custom" in str(parts).lower():
        active_proto = "UDP CUSTOM"
    else:
        active_proto = str(protocol).upper()

    # 6. Generate 1-Click Ready Link
    if active_proto == "VLESS" and uuid:
        qp = {"type": network, "security": "tls" if is_tls else "none"}
        if ws_path: qp["path"] = ws_path
        if ws_host: qp["host"] = ws_host
        if sni and sni != ws_host: qp["sni"] = sni
        v2ray_link = f"vless://{uuid}@{host}:{port}?{urllib.parse.urlencode(qp)}#{urllib.parse.quote(name)}"

    elif active_proto == "VMESS" and uuid:
        vmess_dict = {
            "v": "2",
            "ps": name,
            "add": host,
            "port": str(port),
            "id": uuid,
            "aid": alter_id,
            "scy": tls_security if tls_security not in ["none", ""] else "chacha20-poly1305",
            "net": network,
            "type": "none",
            "host": ws_host or "",
            "path": ws_path or "/",
            "tls": "tls" if is_tls else "none",
            "sni": sni or ""
        }
        v2ray_link = "vmess://" + base64.b64encode(json.dumps(vmess_dict).encode()).decode()

    elif active_proto == "TROJAN" and (uuid or password):
        auth_pw = uuid or password
        qp = {"type": network, "security": "tls" if is_tls else "none"}
        if ws_path: qp["path"] = ws_path
        if ws_host: qp["host"] = ws_host
        if sni: qp["sni"] = sni
        v2ray_link = f"trojan://{auth_pw}@{host}:{port}?{urllib.parse.urlencode(qp)}#{urllib.parse.quote(name)}"

    elif active_proto == "SSH" and host and username:
        v2ray_link = f"{host}:{port}@{username}:{password}"

    elif active_proto == "UDP CUSTOM" and host and username:
        v2ray_link = f"{host}:{port}@{username}:{password}"

    # Check unlock status for name display
    is_unlocked = (protections.get("a") == "normal" or not protections.get("a"))
    name_display = name
    if is_unlocked and "(Unlocked)" not in name_display:
        name_display = f"{name_display}  (Unlocked)"

    # Expiry parsing
    expiry_ms = protections.get("d")
    expiry_str = ""
    if expiry_ms and protections.get("c", False):
        try:
            exp_dt = datetime.datetime.fromtimestamp(expiry_ms / 1000.0, datetime.timezone(datetime.timedelta(hours=6)))
            expiry_str = exp_dt.strftime("%Y-%m-%d %I:%M %p BST")
        except Exception:
            expiry_str = str(expiry_ms)

    # 7. Build Clean, Styled Direct Telegram Message
    msg_lines = [
        "╔════════════════════════╗",
        f"   {active_proto} EXTRACTED INFO",
        "╚════════════════════════╝",
        "",
        f"🚨 NAME: {html_escape(name_display)}",
        ""
    ]

    tls_str = "ON ✅" if is_tls else "OFF ❌"

    if is_v2ray or active_proto in ["VMESS", "VLESS", "TROJAN", "SHADOWSOCKS"]:
        if host and host != "N/A":
            msg_lines.append(f"📍 ADDRESS : {html_escape(host)}")
        if uuid:
            msg_lines.append(f"🔑 UUID    : {html_escape(uuid)}")
        elif password:
            msg_lines.append(f"🔑 PASSWORD: {html_escape(password)}")
        if ws_host:
            msg_lines.append(f"🌐 HOST    : {html_escape(ws_host)}")
        if ws_path:
            msg_lines.append(f"📁 PATH    : {html_escape(ws_path)}")
        msg_lines.append(f"🔌 PORT    : {port}")
        msg_lines.append(f"🛡️ TLS     : {tls_str}")
        msg_lines.append(f"🚦 TRANSPORT: {html_escape(network)}")
        msg_lines.append(f"🔒 SECURITY: {html_escape(tls_security or 'none')}")
        msg_lines.append(f"🧩 INJECT  : {inject_mode}")
        if proxy_val:
            msg_lines.append(f"🧭 PROXY   : {html_escape(proxy_val)}")
        if sni and sni != ws_host and sni != "None":
            msg_lines.append(f"🌐 SNI     : {html_escape(sni)}")

    elif active_proto == "SSH":
        msg_lines.append(f"🌐 HOST    : {html_escape(host)}")
        msg_lines.append(f"🔌 PORT    : {port}")
        if username:
            msg_lines.append(f"👤 USER    : {html_escape(username)}")
        if password:
            msg_lines.append(f"🔑 PASS    : {html_escape(password)}")
        msg_lines.append(f"🧩 INJECT  : {inject_mode}")
        if proxy_val:
            msg_lines.append(f"🧭 PROXY   : {html_escape(proxy_val)}")
        if sni and sni != "None":
            msg_lines.append(f"🌐 SNI     : {html_escape(sni)}")

    elif active_proto == "UDP CUSTOM":
        msg_lines.append(f"🌐 HOST    : {html_escape(host)}")
        msg_lines.append(f"🔌 PORT    : {port}")
        if username:
            msg_lines.append(f"👤 USER    : {html_escape(username)}")
        if password:
            msg_lines.append(f"🔑 PASS    : {html_escape(password)}")
        if sni and sni != "None":
            msg_lines.append(f"🌐 SNI     : {html_escape(sni)}")
        msg_lines.append(f"🧩 INJECT  : {inject_mode}")

    else:
        msg_lines.append(f"🌐 HOST    : {html_escape(host)}")
        msg_lines.append(f"🔌 PORT    : {port}")
        if username:
            msg_lines.append(f"👤 USER    : {html_escape(username)}")
        if password:
            msg_lines.append(f"🔑 PASS    : {html_escape(password)}")
        if sni and sni != "None":
            msg_lines.append(f"🌐 SNI     : {html_escape(sni)}")
        msg_lines.append(f"🧩 INJECT  : {inject_mode}")

    # Custom Payload block
    if custom_payload and custom_payload.strip() and not custom_payload.strip().startswith("{"):
        msg_lines.extend([
            "",
            "📦 PAYLOAD:",
            html_escape(custom_payload.strip()[:1000])
        ])

    # Ready Link block
    if v2ray_link:
        link_title = "🔗 READY LINK:"
        if active_proto == "SSH":
            link_title = "🔐 SSH READY LINK:"
        elif active_proto == "UDP CUSTOM":
            link_title = "🔗 UDP READY LINK:"

        msg_lines.extend([
            "",
            "────────────────────────",
            link_title,
            "────────────────────────",
            "",
            f"<code>{v2ray_link}</code>"
        ])

    # Notes & Expiry
    if expiry_str:
        msg_lines.extend([
            "",
            f"⏳ EXPIRY  : {html_escape(expiry_str)}"
        ])

    if notes and notes.strip() and notes.strip() != "None":
        clean_note = html_escape(notes.strip()[:500])
        msg_lines.extend([
            "",
            f"📝 NOTE    : {clean_note}"
        ])

    styled_message = "\n".join(msg_lines)

    return {
        "styled_message": styled_message,
        "protocol": active_proto,
        "server_host": host,
        "server_port": port,
        "creator": creator,
        "name": name,
        "version": f"v{container_version} ({key_scheme})",
        "total_profiles": len(profiles),
        "notes": notes.strip() if notes else "None"
    }


if __name__ == "__main__":
    import sys
    test_file = sys.argv[1] if len(sys.argv) > 1 else "/home/foridul/Downloads/Telegram Desktop/AISO.hc"
    with open(test_file, "rb") as f:
        res = decrypt_hc_file(f.read())
        print(res["styled_message"])
        print("\n[+] Direct styled message tested successfully!")
