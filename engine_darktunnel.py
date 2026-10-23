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
    Decrypts Dark Tunnel (.dark) file and produces clean styled Telegram message
    without ANY filtering - extracting V2Ray (VLESS/VMess/Trojan/SS), SSH, DNSTT,
    Payload, Proxy, and generating all ready-to-import links.
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

    def _clean_str(val: Any) -> str:
        if val is None:
            return ""
        if isinstance(val, list):
            return str(val[0]).strip() if val else ""
        if isinstance(val, (bytes, bytearray)):
            try:
                return val.decode("utf-8").strip()
            except Exception:
                return ""
        return str(val).strip()

    # Common Connection Fields
    v2_protocol = ""
    v2_host = ""
    v2_port = 0
    v2_uuid = ""
    v2_security = ""
    v2_network = "ws"
    v2_path = "/"
    v2_ws_host = ""
    v2_sni = ""
    is_tls = False
    v2_method = ""

    # 1. Parse V2Ray Config (supports outbounds with vnext AND servers)
    has_v2ray = bool(v2ray_cfg and isinstance(v2ray_cfg, dict) and v2ray_cfg.get("outbounds"))
    if has_v2ray:
        outbounds = v2ray_cfg.get("outbounds", [])
        for ob in outbounds:
            proto = ob.get("protocol", "").lower()
            if not proto or proto in ["freedom", "blackhole"]:
                continue
            v2_protocol = proto.upper()
            settings = ob.get("settings", {})

            # Strategy A: vnext (Used in VLESS, VMess)
            vnext = settings.get("vnext", [])
            if vnext and isinstance(vnext, list):
                first_vn = vnext[0]
                v2_host = _clean_str(first_vn.get("address")) or v2_host
                v2_port = first_vn.get("port") or v2_port
                users = first_vn.get("users", [])
                if users and isinstance(users, list):
                    v2_uuid = _clean_str(users[0].get("id") or users[0].get("password")) or v2_uuid
                    v2_security = _clean_str(users[0].get("security") or users[0].get("encryption")) or v2_security

            # Strategy B: servers (Used in Trojan, Shadowsocks, Socks)
            servers = settings.get("servers", [])
            if servers and isinstance(servers, list):
                first_srv = servers[0]
                v2_host = _clean_str(first_srv.get("address")) or v2_host
                v2_port = first_srv.get("port") or v2_port
                v2_uuid = _clean_str(first_srv.get("password") or first_srv.get("id")) or v2_uuid
                v2_method = _clean_str(first_srv.get("method")) or v2_method
                v2_security = _clean_str(first_srv.get("security")) or v2_security

            # StreamSettings
            stream = ob.get("streamSettings", {})
            if stream.get("network"):
                v2_network = str(stream.get("network")).lower()
            sec = str(stream.get("security", "")).lower()
            if sec:
                v2_security = sec
            is_tls = (sec in ["tls", "reality"])

            # WebSockets
            ws_st = stream.get("wsSettings", {})
            if ws_st.get("path"):
                v2_path = _clean_str(ws_st.get("path"))
            ws_headers = ws_st.get("headers", {})
            if ws_headers and isinstance(ws_headers, dict):
                v2_ws_host = _clean_str(ws_headers.get("Host") or ws_headers.get("host"))

            # gRPC
            grpc_st = stream.get("grpcSettings", {})
            if grpc_st.get("serviceName"):
                v2_path = _clean_str(grpc_st.get("serviceName"))

            # TLS SNI
            tls_st = stream.get("tlsSettings", {})
            if tls_st.get("serverName"):
                v2_sni = _clean_str(tls_st.get("serverName"))

            # Reality
            reality_st = stream.get("realitySettings", {})
            if reality_st.get("serverName"):
                v2_sni = _clean_str(reality_st.get("serverName"))

            if v2_protocol and (v2_host or v2_uuid):
                break

    # 2. Parse SSH Config
    ssh_host = ""
    ssh_port = 0
    ssh_user = ""
    ssh_pass = ""
    if ssh_cfg and isinstance(ssh_cfg, dict):
        ssh_host = _clean_str(ssh_cfg.get("EncryptedHost"))
        ssh_port = ssh_cfg.get("EncryptedPort", 0)
        ssh_user = _clean_str(ssh_cfg.get("EncryptedUsername"))
        ssh_pass = _clean_str(ssh_cfg.get("EncryptedPassword"))

    # 3. Parse DNSTT / SlowDNS Config
    dnstt_dns = _clean_str(inject_cfg.get("EncryptedDnsttDnsHost"))
    dnstt_port = _clean_str(inject_cfg.get("EncryptedDnsttDnsPort")) or "53"
    dnstt_ns = _clean_str(inject_cfg.get("EncryptedDnsttServerName"))
    dnstt_pubkey = _clean_str(inject_cfg.get("EncryptedDnsttPubkey"))

    # 4. Parse Inject Mode, Payload, Proxy & SNI
    inject_mode = _clean_str(inject_cfg.get("EncryptedMode")) or "DIRECT"
    custom_payload = _clean_str(inject_cfg.get("EncryptedPayload"))
    p_host = _clean_str(inject_cfg.get("EncryptedProxyHost"))
    p_port = _clean_str(inject_cfg.get("EncryptedProxyPort"))
    proxy_val = f"{p_host}:{p_port}" if (p_host and p_host != "localhost" and p_port) else (p_host if p_host != "localhost" else "")
    sni = _clean_str(inject_cfg.get("EncryptedServerNameIndication")) or v2_sni

    # Fallback host/port/uuid
    primary_proto = v2_protocol or config_type
    if not v2_host and ssh_host:
        v2_host = ssh_host
    if not v2_port and ssh_port:
        v2_port = ssh_port

    # 5. Generate 1-Click Ready Links (VLESS, VMESS, TROJAN, SS, SSH)
    ready_links = []

    # Trojan
    if (v2_protocol == "TROJAN" or primary_proto == "TROJAN") and v2_uuid and v2_host:
        qp = {}
        if v2_network: qp["type"] = v2_network
        qp["security"] = "tls" if is_tls else "none"
        if v2_path: qp["path"] = v2_path
        if v2_ws_host: qp["host"] = v2_ws_host
        if sni and sni != v2_ws_host: qp["sni"] = sni
        trojan_link = f"trojan://{v2_uuid}@{v2_host}:{v2_port}?{urllib.parse.urlencode(qp)}#{urllib.parse.quote(name)}"
        ready_links.append(trojan_link)

    # VLESS
    elif (v2_protocol == "VLESS" or primary_proto == "VLESS") and v2_uuid and v2_host:
        qp = {"type": v2_network, "security": "tls" if is_tls else "none"}
        if v2_path: qp["path"] = v2_path
        if v2_ws_host: qp["host"] = v2_ws_host
        if sni and sni != v2_ws_host: qp["sni"] = sni
        vless_link = f"vless://{v2_uuid}@{v2_host}:{v2_port}?{urllib.parse.urlencode(qp)}#{urllib.parse.quote(name)}"
        ready_links.append(vless_link)

    # VMess
    elif (v2_protocol == "VMESS" or primary_proto == "VMESS") and v2_uuid and v2_host:
        vmess_dict = {
            "v": "2", "ps": name, "add": v2_host, "port": str(v2_port),
            "id": v2_uuid, "aid": "0", "scy": v2_security if v2_security not in ["none", ""] else "auto",
            "net": v2_network, "type": "none", "host": v2_ws_host or "",
            "path": v2_path or "/", "tls": "tls" if is_tls else "none", "sni": sni or ""
        }
        vmess_link = "vmess://" + base64.b64encode(json.dumps(vmess_dict).encode()).decode()
        ready_links.append(vmess_link)

    # Shadowsocks
    elif (v2_protocol in ["SHADOWSOCKS", "SS"] or primary_proto in ["SHADOWSOCKS", "SS"]) and v2_uuid and v2_host:
        ss_method = v2_method or "aes-256-gcm"
        ss_auth = base64.b64encode(f"{ss_method}:{v2_uuid}@{v2_host}:{v2_port}".encode()).decode()
        ready_links.append(f"ss://{ss_auth}#{urllib.parse.quote(name)}")

    # SSH Ready Link
    if ssh_user and (ssh_host or dnstt_ns):
        ssh_target = ssh_host or dnstt_ns
        ssh_ready = f"{ssh_target}:{ssh_port}@{ssh_user}:{ssh_pass}"
        ready_links.append(ssh_ready)

    # Expiry
    exp_ms = app_config.get("ExpiredAtTimestamp")
    expiry_str = ""
    if exp_ms and int(exp_ms) > 0:
        try:
            exp_dt = datetime.datetime.fromtimestamp(int(exp_ms) / 1000.0, datetime.timezone(datetime.timedelta(hours=6)))
            expiry_str = exp_dt.strftime("%Y-%m-%d %I:%M %p BST")
        except Exception:
            expiry_str = str(exp_ms)

    # Note
    raw_msg = app_config.get("Message", "")
    clean_note = re.sub(r'<[^>]+>', ' ', raw_msg).strip() if raw_msg else ""
    clean_note = " ".join(clean_note.split())[:350]

    # Build Clean, Styled Output Message - NEVER FILTER ANYTHING!
    display_proto = v2_protocol or config_type
    msg_lines = [
        "╔════════════════════════╗",
        f"   {display_proto} EXTRACTED INFO",
        "╚════════════════════════╝",
        "",
        f"🚨 NAME: {html_escape(name)}",
        ""
    ]

    tls_str = "ON ✅" if is_tls else "OFF ❌"

    # If V2Ray / Trojan / VLESS / VMess details exist:
    if has_v2ray or v2_uuid or v2_protocol in ["VLESS", "VMESS", "TROJAN", "SHADOWSOCKS"]:
        if v2_host:
            msg_lines.append(f"📍 ADDRESS : {html_escape(v2_host)}")
        if v2_uuid:
            label = "PASSWORD" if v2_protocol in ["TROJAN", "SHADOWSOCKS"] else "UUID    "
            msg_lines.append(f"🔑 {label}: {html_escape(v2_uuid)}")
        if v2_ws_host:
            msg_lines.append(f"🌐 HOST    : {html_escape(v2_ws_host)}")
        if v2_path:
            msg_lines.append(f"📁 PATH    : {html_escape(v2_path)}")
        if v2_port:
            msg_lines.append(f"🔌 PORT    : {v2_port}")
        msg_lines.append(f"🛡️ TLS     : {tls_str}")
        msg_lines.append(f"🚦 TRANSPORT: {html_escape(v2_network)}")
        msg_lines.append(f"🔒 SECURITY: {html_escape(v2_security or 'none')}")

    # If SSH credentials exist:
    if ssh_user or (ssh_host and not has_v2ray):
        if ssh_host:
            msg_lines.append(f"🌐 SSH HOST: {html_escape(ssh_host)}")
        if ssh_port:
            msg_lines.append(f"🔌 SSH PORT: {ssh_port}")
        if ssh_user:
            msg_lines.append(f"👤 SSH USER: {html_escape(ssh_user)}")
        if ssh_pass:
            msg_lines.append(f"🔑 SSH PASS: {html_escape(ssh_pass)}")

    # If DNSTT / SlowDNS exists:
    if dnstt_ns or dnstt_dns:
        if dnstt_dns:
            msg_lines.append(f"🧭 DNS SERVER: {html_escape(dnstt_dns)}:{dnstt_port}")
        if dnstt_ns:
            msg_lines.append(f"🌐 NAMESERVER: {html_escape(dnstt_ns)}")
        if dnstt_pubkey:
            msg_lines.append(f"🔑 PUBKEY    : {html_escape(dnstt_pubkey)}")

    # Inject Mode & Proxy
    msg_lines.append(f"🧩 INJECT  : {inject_mode}")
    if proxy_val:
        msg_lines.append(f"🧭 PROXY   : {html_escape(proxy_val)}")
    if sni and sni != v2_ws_host:
        msg_lines.append(f"🌐 SNI     : {html_escape(sni)}")

    # Payload (Full Payload without filtering)
    if custom_payload:
        msg_lines.extend([
            "",
            "📦 PAYLOAD:",
            html_escape(custom_payload[:1500])
        ])

    # Ready Link(s)
    if ready_links:
        msg_lines.extend([
            "",
            "────────────────────────",
            "🔗 READY LINK:",
            "────────────────────────",
            ""
        ])
        for rl in ready_links:
            msg_lines.append(f"<code>{html_escape(rl)}</code>")

    # Expiry
    if expiry_str:
        msg_lines.extend([
            "",
            f"⏳ EXPIRY  : {html_escape(expiry_str)}"
        ])

    # Note
    if clean_note:
        msg_lines.extend([
            "",
            f"📝 NOTE    : {html_escape(clean_note)}"
        ])

    return {
        "styled_message": "\n".join(msg_lines),
        "protocol": display_proto,
        "server_host": v2_host or ssh_host or "N/A",
        "server_port": v2_port or ssh_port or 0,
        "name": name,
        "creator": "Dark Tunnel",
        "ready_links": ready_links,
        "raw_data": data
    }


if __name__ == "__main__":
    import sys
    test_path = sys.argv[1] if len(sys.argv) > 1 else "/home/foridul/Downloads/Telegram Desktop/DXX.dark"
    with open(test_path, "rb") as f:
        res = decrypt_dark_file(f.read())
        print(res["styled_message"])
