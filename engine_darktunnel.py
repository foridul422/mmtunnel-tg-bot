#!/usr/bin/env python3
"""
=============================================================================
  DARK TUNNEL (.dark) DECRYPTION ENGINE
  By         : @Foridul_002 🇧🇩
  Supports   : VLESS, VMess, Trojan, SSH, DNSTT & Direct Payloads
=============================================================================
"""

import json
import base64
import re
import contextlib
import urllib.parse
import datetime
from typing import Optional, Dict, Any, Union, List
from Crypto.Cipher import AES

try:
    import msgpack
    MSGPACK_AVAILABLE = True
except ImportError:
    MSGPACK_AVAILABLE = False


class DTConstants:
    """Cryptographic artifacts and static keys for Dark Tunnel."""
    KEY_256: bytes = b"$B&E)H@McQfThWmZq4t7w!z%C*F-JaNd"
    KEY_192: bytes = b"F)J@NcRfUjXn2r4u7x!A%D*G"
    IV: bytes = bytes.fromhex("232e39185523184a5723586242200e05")


def html_escape(text: Any) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


class DTDecryptor:
    """Core decryption and parsing engine for Dark Tunnel configs."""

    @staticmethod
    def _base64_decode_safe(data: str) -> bytes:
        clean_data = data.replace("-", "+").replace("_", "/")
        if pad := len(clean_data) % 4:
            clean_data += "=" * (4 - pad)
        return base64.b64decode(clean_data)

    @staticmethod
    def _aes_cfb_decrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
        return AES.new(key, AES.MODE_CFB, iv=iv, segment_size=128).decrypt(data)

    @staticmethod
    def _is_utf8_printable(value: bytes) -> bool:
        if not value: 
            return False
        try:
            return bool(re.fullmatch(r"[^\x00-\x08\x0B\x0C\x0E-\x1F\x7F]*", value.decode("utf-8")))
        except UnicodeDecodeError:
            return False

    @classmethod
    def _try_parse_json_string(cls, value: str) -> Union[Dict, List, str]:
        stripped = value.strip()
        if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
            with contextlib.suppress(Exception):
                fixed_json = re.sub(r'(:\s*)(\$[A-Za-z0-9_]+)', r'\1"\2"', stripped)
                return cls._normalize_for_json(json.loads(fixed_json))
        return value

    @classmethod
    def _normalize_for_json(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: cls._normalize_for_json(v) for k, v in value.items() if k != "Password"}
        if isinstance(value, list):
            return [cls._normalize_for_json(v) for v in value]
        if isinstance(value, bytes):
            return cls._try_parse_json_string(value.decode("utf-8")) if cls._is_utf8_printable(value) else list(value)
        if isinstance(value, str):
            return cls._try_parse_json_string(value)
        return value

    @classmethod
    def _clean_encrypted(cls, value: Any, key: bytes, iv: bytes) -> Any:
        if isinstance(value, dict):
            cleaned = {}
            for k, v in value.items():
                if isinstance(k, str) and k.startswith("Encrypted") and v and isinstance(v, (bytes, bytearray)):
                    try:
                        cleaned[k] = cls._aes_cfb_decrypt(bytes(v), key, iv)
                    except Exception:
                        cleaned[k] = v
                else:
                    cleaned[k] = cls._clean_encrypted(v, key, iv)
            return cleaned
        if isinstance(value, list):
            return [cls._clean_encrypted(v, key, iv) for v in value]
        return value

    @classmethod
    def parse_raw(cls, file_bytes: bytes) -> Optional[Dict[str, Any]]:
        if not MSGPACK_AVAILABLE:
            raise ImportError("msgpack is not installed. Install with: pip install msgpack")

        raw_input = file_bytes.decode('utf-8', errors='ignore').strip()
        if not raw_input: 
            return None
        
        if "://" in raw_input:
            raw_input = raw_input.split("://", 1)[1]

        outer = json.loads(cls._base64_decode_safe(raw_input).decode("utf-8"))
        if "encryptedLockedConfig" not in outer:
            return None 

        encrypted_locked_config = cls._base64_decode_safe(outer["encryptedLockedConfig"])
        decrypted_outer = cls._aes_cfb_decrypt(encrypted_locked_config, DTConstants.KEY_256, DTConstants.IV)
        unpacked_outer = msgpack.unpackb(decrypted_outer, raw=False, strict_map_key=False)
        
        if "EncryptedLockedConfig" in unpacked_outer:
            decrypted_inner = cls._aes_cfb_decrypt(unpacked_outer["EncryptedLockedConfig"], DTConstants.KEY_192, DTConstants.IV)
            unpacked_inner = msgpack.unpackb(decrypted_inner, raw=False, strict_map_key=False)
            unpacked_outer["EncryptedLockedConfig"] = cls._clean_encrypted(unpacked_inner, DTConstants.KEY_192, DTConstants.IV)

        outer["encryptedLockedConfig"] = unpacked_outer
        return cls._normalize_for_json(outer)


def decrypt_dark_file(file_bytes: bytes) -> Dict[str, Any]:
    """
    Decrypts Dark Tunnel (.dark) file and produces clean styled Telegram message.
    """
    data = DTDecryptor.parse_raw(file_bytes)
    if not data:
        raise ValueError("Failed to decrypt Dark Tunnel file. Invalid or corrupted file.")

    name = data.get("name", "Dark Tunnel Config")
    config_type = data.get("type", "DARK TUNNEL").upper()

    enc_config = data.get("encryptedLockedConfig", {})
    app_config = enc_config.get("LockedAppConfig", {})
    inner_config = enc_config.get("EncryptedLockedConfig", {})

    inject_cfg = inner_config.get("InjectConfig", {})
    ssh_cfg = inner_config.get("SshConfig", {})
    v2ray_cfg = inner_config.get("V2RayConfig", {}).get("EncryptedConfig", {})

    # Extract common connection fields
    host = ""
    port = 0
    username = ""
    password = ""
    uuid = ""
    ws_host = ""
    ws_path = "/"
    network = "ws"
    tls_security = "none"
    is_tls = False
    custom_payload = ""
    inject_mode = inject_cfg.get("EncryptedMode", "DIRECT")
    proxy_val = ""
    sni = ""
    ready_link = ""

    # Check payload
    if inject_cfg.get("EncryptedPayload"):
        pl = inject_cfg["EncryptedPayload"]
        if isinstance(pl, str) and pl.strip():
            custom_payload = pl.strip()

    # Check proxy
    p_host = inject_cfg.get("EncryptedProxyHost")
    p_port = inject_cfg.get("EncryptedProxyPort")
    if p_host and p_host != "localhost":
        proxy_val = f"{p_host}:{p_port}" if p_port else p_host

    # Check SNI
    if inject_cfg.get("EncryptedServerNameIndication"):
        sni_candidate = inject_cfg["EncryptedServerNameIndication"]
        if isinstance(sni_candidate, str):
            sni = sni_candidate
        elif isinstance(sni_candidate, list) and sni_candidate:
            sni = str(sni_candidate[0])

    # 1. Parse V2Ray Config if present
    is_v2ray = bool(v2ray_cfg and v2ray_cfg.get("outbounds"))
    if is_v2ray:
        outbounds = v2ray_cfg.get("outbounds", [])
        for ob in outbounds:
            ob_proto = ob.get("protocol", "").lower()
            if ob_proto in ["vless", "vmess", "trojan"]:
                config_type = ob_proto.upper()
                settings = ob.get("settings", {})
                vnext = settings.get("vnext", [])
                if vnext:
                    host = vnext[0].get("address") or host
                    port = vnext[0].get("port") or port
                    users = vnext[0].get("users", [])
                    if users:
                        uuid = users[0].get("id") or users[0].get("password") or ""
                        if users[0].get("security"):
                            tls_security = users[0].get("security")

                stream = ob.get("streamSettings", {})
                if stream.get("network"):
                    network = stream.get("network").lower()
                sec = stream.get("security", "")
                if sec:
                    tls_security = sec
                is_tls = (sec.lower() == "tls")

                ws_settings = stream.get("wsSettings", {})
                if ws_settings.get("path"):
                    ws_path = ws_settings.get("path")
                ws_headers = ws_settings.get("headers", {})
                if ws_headers.get("Host"):
                    ws_host = ws_headers.get("Host")

                tls_st = stream.get("tlsSettings", {})
                if tls_st.get("serverName"):
                    sni = tls_st.get("serverName")
                break

    # 2. Parse SSH Config if present
    if not host and ssh_cfg:
        ssh_h = ssh_cfg.get("EncryptedHost")
        if isinstance(ssh_h, str):
            host = ssh_h
        elif isinstance(ssh_h, list) and ssh_h:
            host = str(ssh_h[0])

        port = ssh_cfg.get("EncryptedPort", 80)
        u_cand = ssh_cfg.get("EncryptedUsername")
        if isinstance(u_cand, str):
            username = u_cand
        elif isinstance(u_cand, list) and u_cand:
            username = str(u_cand[0])

        p_cand = ssh_cfg.get("EncryptedPassword")
        if isinstance(p_cand, str):
            password = p_cand
        elif isinstance(p_cand, list) and p_cand:
            password = str(p_cand[0])

    # 3. Generate 1-Click Ready Link
    if config_type == "VLESS" and uuid and host:
        qp = {"type": network, "security": "tls" if is_tls else "none"}
        if ws_path: qp["path"] = ws_path
        if ws_host: qp["host"] = ws_host
        if sni and sni != ws_host: qp["sni"] = sni
        ready_link = f"vless://{uuid}@{host}:{port}?{urllib.parse.urlencode(qp)}#{urllib.parse.quote(name)}"

    elif config_type == "VMESS" and uuid and host:
        vmess_dict = {
            "v": "2", "ps": name, "add": host, "port": str(port),
            "id": uuid, "aid": "0", "scy": tls_security if tls_security not in ["none", ""] else "chacha20-poly1305",
            "net": network, "type": "none", "host": ws_host or "",
            "path": ws_path or "/", "tls": "tls" if is_tls else "none", "sni": sni or ""
        }
        ready_link = "vmess://" + base64.b64encode(json.dumps(vmess_dict).encode()).decode()

    elif config_type in ["SSH", "SSH_DNSTT"] and host and username:
        ready_link = f"{host}:{port}@{username}:{password}"

    # Expiry parsing
    exp_ms = app_config.get("ExpiredAtTimestamp")
    expiry_str = ""
    if exp_ms and int(exp_ms) > 0:
        try:
            exp_dt = datetime.datetime.fromtimestamp(int(exp_ms) / 1000.0, datetime.timezone(datetime.timedelta(hours=6)))
            expiry_str = exp_dt.strftime("%Y-%m-%d %I:%M %p BST")
        except Exception:
            expiry_str = str(exp_ms)

    # Clean note message
    raw_msg = app_config.get("Message", "")
    clean_note = re.sub(r'<[^>]+>', ' ', raw_msg).strip() if raw_msg else ""
    clean_note = " ".join(clean_note.split())[:350]

    # Build Clean, Styled Telegram Message
    msg_lines = [
        "╔════════════════════════╗",
        f"   {config_type} EXTRACTED INFO",
        "╚════════════════════════╝",
        "",
        f"🚨 NAME: {html_escape(name)}",
        ""
    ]

    tls_str = "ON ✅" if is_tls else "OFF ❌"

    if is_v2ray or config_type in ["VMESS", "VLESS", "TROJAN"]:
        if host:
            msg_lines.append(f"📍 ADDRESS : {html_escape(host)}")
        if uuid:
            msg_lines.append(f"🔑 UUID    : {html_escape(uuid)}")
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
        if sni and sni != ws_host:
            msg_lines.append(f"🌐 SNI     : {html_escape(sni)}")

    elif "SSH" in config_type:
        if host:
            msg_lines.append(f"🌐 HOST    : {html_escape(host)}")
        msg_lines.append(f"🔌 PORT    : {port}")
        if username:
            msg_lines.append(f"👤 USER    : {html_escape(username)}")
        if password:
            msg_lines.append(f"🔑 PASS    : {html_escape(password)}")
        msg_lines.append(f"🧩 INJECT  : {inject_mode}")
        if proxy_val:
            msg_lines.append(f"🧭 PROXY   : {html_escape(proxy_val)}")
        if sni:
            msg_lines.append(f"🌐 SNI     : {html_escape(sni)}")

    else:
        if host:
            msg_lines.append(f"🌐 HOST    : {html_escape(host)}")
        msg_lines.append(f"🔌 PORT    : {port}")
        if username:
            msg_lines.append(f"👤 USER    : {html_escape(username)}")
        if password:
            msg_lines.append(f"🔑 PASS    : {html_escape(password)}")
        msg_lines.append(f"🧩 INJECT  : {inject_mode}")

    if custom_payload:
        msg_lines.extend([
            "",
            "📦 PAYLOAD:",
            html_escape(custom_payload[:800])
        ])

    if ready_link:
        msg_lines.extend([
            "",
            "────────────────────────",
            "🔗 READY LINK:",
            "────────────────────────",
            "",
            f"<code>{ready_link}</code>"
        ])

    if expiry_str:
        msg_lines.extend([
            "",
            f"⏳ EXPIRY  : {html_escape(expiry_str)}"
        ])

    if clean_note:
        msg_lines.extend([
            "",
            f"📝 NOTE    : {html_escape(clean_note)}"
        ])

    return {
        "styled_message": "\n".join(msg_lines),
        "protocol": config_type,
        "server_host": host or "N/A",
        "server_port": port or 0,
        "name": name,
        "creator": "Dark Tunnel",
        "raw_data": data
    }


if __name__ == "__main__":
    import sys
    test_path = sys.argv[1] if len(sys.argv) > 1 else "/home/foridul/Downloads/Telegram Desktop/DXX.dark"
    with open(test_path, "rb") as f:
        res = decrypt_dark_file(f.read())
        print(res["styled_message"])
