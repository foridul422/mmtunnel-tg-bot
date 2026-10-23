#!/usr/bin/env python3
"""
=============================================================================
  HTTP INJECTOR (.ehi) DECRYPTION ENGINE
  By         : @Foridul_002 🇧🇩
  Supports   : SSH, DNSTT, V2Ray (VMess/VLESS/Trojan/Shadowsocks), Direct & Proxy Payloads
  Zero-Filter: Extracts 100% of server details, credentials, payloads & ready links.
=============================================================================
"""

import struct
import base64
import json
import hashlib
import io
import re
import contextlib
import urllib.parse
import datetime
from typing import Optional, Dict, Any, List
from Crypto.Cipher import AES, ChaCha20_Poly1305
from Crypto.Util.Padding import unpad

try:
    from argon2.low_level import hash_secret_raw, Type
    ARGON2_AVAILABLE = True
except ImportError:
    ARGON2_AVAILABLE = False


class EHIConstants:
    """Master artifacts and cryptographic constants."""
    L1_KEY: bytes = bytes.fromhex("7e1210f7aab956f7a668bda6e57feddb7f84ad840aef8d27b1b969959be3ab6c")
    L2_KEY_STATIC: bytes = bytes.fromhex("b2bc617c32d8b9eb1943a5ffa8051eea")
    EOO_MASTER_KEY: bytes = b"null=V5kU5+FFrY\x00"
    BYPASS_IVS = (
        bytes.fromhex("221d572349555f1d112133236b1f4a3f"),
        bytes.fromhex("5543494c53443e3f4a6a4539384e776a"),
        bytes.fromhex("374c2541575e4d531a3c327b75431e5f")
    )
    STANDARD_IVS = (
        bytes.fromhex("2c5d1147bbad422b3b334d4d235f1a53"),
        bytes.fromhex("522b01433a5e8b2fc7549e1ad368e541"),
        bytes.fromhex("337a1035aaedf3458ca167e92d74b839")
    )

    STD_ALPHABET: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    CUSTOM_ALPHABET: str = "RkLC2QaVMPYgGJW/A4f7qzDb9e+t6Hr0Zp8OlNyjuxKcTw1o5EIimhBn3UvdSFXs"
    TRANSLATION_TABLE = str.maketrans(CUSTOM_ALPHABET, STD_ALPHABET)


def html_escape(text: Any) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


class EHIDecryptor:

    @staticmethod
    def _custom_b64_decode(encoded_str: str) -> bytes:
        clean_str = encoded_str.replace("?", "")
        if rem := len(clean_str) % 4:
            clean_str += "=" * (4 - rem)
        return base64.b64decode(clean_str.translate(EHIConstants.TRANSLATION_TABLE))

    @staticmethod
    def _decrypt_xor_layer(ciphertext_str: str, key: str) -> Optional[str]:
        if not ciphertext_str or not ciphertext_str.strip():
            return ciphertext_str
            
        with contextlib.suppress(Exception):
            hex_bytes_raw = EHIDecryptor._custom_b64_decode(ciphertext_str[::-1])
            hex_string = hex_bytes_raw.decode('ascii')
            
            if len(hex_string) % 2 != 0: 
                hex_string = f"0{hex_string}"
            
            raw_bytes = bytes.fromhex(hex_string)
            key_len = len(key)
            
            decrypted_bytes = bytearray(
                b ^ ord(key[i % key_len]) for i, b in enumerate(raw_bytes) if (b ^ ord(key[i % key_len])) != 0
            )
                    
            plaintext = decrypted_bytes.decode('utf-8')
            
            if plaintext and (sum(1 for c in plaintext if ord(c) < 32 and ord(c) not in (9, 10, 13)) / len(plaintext)) > 0.5:
                return None
                
            return plaintext
        return None

    @staticmethod
    def _decode_config_message(ciphertext_str: str) -> str:
        if not ciphertext_str or not ciphertext_str.strip():
            return ciphertext_str
            
        with contextlib.suppress(Exception):
            padded_str = ciphertext_str + "=" * ((4 - len(ciphertext_str) % 4) % 4)
            raw_bytes = base64.b64decode(padded_str)
            
            utf16_bytes = raw_bytes.decode('utf-8', errors='replace').encode('utf-16-be', errors='surrogatepass')
            num_chars = len(utf16_bytes) // 2
            
            java_chars = struct.unpack(f'>{num_chars}H', utf16_bytes)
            key_chars = [ord(c) for c in "EHIMSG"]
            key_len = len(key_chars)
            
            xored_chars = [jc ^ key_chars[i % key_len] for i, jc in enumerate(java_chars)]
            xored_bytes = struct.pack(f'>{num_chars}H', *xored_chars)
            
            return xored_bytes.decode('utf-16-be', errors='surrogatepass').encode('utf-16', 'surrogatepass').decode('utf-16')
        return ciphertext_str

    @staticmethod
    def _decode_inner_fields(parsed_json: Dict[str, Any], salt_key: str) -> Dict[str, Any]:
        """
        Decrypts XOR fields. If decryption fails or value is already plaintext,
        CRITICAL: NEVER drop the field! Always preserve original value.
        """
        cleaned_json = {}
        for k, v in parsed_json.items():
            if isinstance(v, str) and v.strip():
                if k == "configMessage":
                    cleaned_json[k] = EHIDecryptor._decode_config_message(v)
                else:
                    decrypted_val = EHIDecryptor._decrypt_xor_layer(v, salt_key)
                    if decrypted_val is not None:
                        cleaned_json[k] = decrypted_val
                    else:
                        # Fallback to original value: do not discard unencrypted or plain fields!
                        cleaned_json[k] = v
            else:
                cleaned_json[k] = v
        return cleaned_json

    @staticmethod
    def _xxtea_decrypt(data: bytes, key: bytes) -> bytes:
        if not data: 
            return b""
        if rem := len(data) % 4: 
            data += b'\x00' * (4 - rem)
            
        k = struct.unpack('<4I', key.ljust(16, b'\x00')[:16])
        n = len(data) // 4
        v = list(struct.unpack(f'<{n}I', data))
        
        delta = 0x9e3779b9
        sum_val = ((6 + 52 // n) * delta) & 0xffffffff
        y = v[0]
        
        while sum_val != 0:
            e = (sum_val >> 2) & 3
            for p in range(n - 1, 0, -1):
                z = v[p - 1]
                mx = (((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))) ^ ((sum_val ^ y) + (k[(p & 3) ^ e] ^ z))
                y = v[p] = (v[p] - mx) & 0xffffffff
            
            z = v[n - 1]
            mx = (((z >> 5) ^ (y << 2)) + ((y >> 3) ^ (z << 4))) ^ ((sum_val ^ y) + (k[(0 & 3) ^ e] ^ z))
            y = v[0] = (v[0] - mx) & 0xffffffff
            sum_val = (sum_val - delta) & 0xffffffff
            
        decrypted = struct.pack(f'<{n}I', *v)
        length = v[-1]
        return decrypted[:length] if 0 < length <= n * 4 else decrypted.rstrip(b'\x00')

    @staticmethod
    def _parse_ehi_bytes(file_bytes: bytes) -> Optional[bytes]:
        try:
            f = io.BytesIO(file_bytes)
            
            def r_utf() -> str:
                if len(l_bytes := f.read(2)) < 2: return ""
                return f.read(struct.unpack('>H', l_bytes)[0]).decode('utf-8', errors='ignore')
            
            r_utf(); f.read(8); r_utf(); f.read(8)
            if len(p_len_bytes := f.read(4)) < 4: 
                return None
            
            p_len = struct.unpack('>I', p_len_bytes)[0]
            f.read(8)
            return f.read(p_len)
        except struct.error:
            return None

    @staticmethod
    def _generate_master_key(config: Dict[str, Any]) -> bytes:
        payload = "".join(str(p) for p in (
            config.get("configAesKey", ""),           
            config.get("configIdentifier", ""),       
            config.get("configSalt", ""),             
            str(config.get("configTimestamp", 0)),                                     
            str(config.get("configExpiryTimestamp", 0)),                                    
            config.get("lockModes", ""),              
            config.get("lockModesHash", ""),          
            config.get("configHwid", ""),             
            config.get("configLockMobileOperatorId", "") 
        ) if p)
        return hashlib.sha256(payload.encode('utf-8')).digest()

    @classmethod
    def parse_raw(cls, file_bytes: bytes) -> Optional[Dict[str, Any]]:
        if not ARGON2_AVAILABLE:
            raise ImportError("argon2-cffi is not installed.")

        payload = cls._parse_ehi_bytes(file_bytes)
        if not payload:
            return None

        config, matched_iv = None, None

        for iv in EHIConstants.BYPASS_IVS + EHIConstants.STANDARD_IVS:
            with contextlib.suppress(Exception):
                c1 = AES.new(EHIConstants.L1_KEY, AES.MODE_CBC, iv)
                l1_text = unpad(c1.decrypt(payload), 16).decode('utf-8')
                
                if (parts := l1_text.split(":")) and len(parts) >= 3:
                    c2 = AES.new(EHIConstants.L2_KEY_STATIC, AES.MODE_CBC, base64.b64decode(parts[0]))
                    garbage = unpad(c2.decrypt(base64.b64decode(parts[2])), 16)

                    final_raw = cls._xxtea_decrypt(garbage, EHIConstants.EOO_MASTER_KEY)
                    if (start := final_raw.find(b'{')) != -1:
                        config = json.loads(final_raw[start:].decode('utf-8', errors='ignore'))
                        matched_iv = iv
                        break 

        if not config:
            return None 

        target_salt = config.get('configSalt', "EVZJNI")
        parsed_final = None

        if matched_iv in EHIConstants.BYPASS_IVS:
            parsed_final = config
        else:
            target_data = config.get('configData')
            if target_data:
                aaa_result = cls._decrypt_xor_layer(target_data, target_salt)
                if aaa_result:
                    with contextlib.suppress(Exception):
                        raw_payload = base64.b64decode(aaa_result)
                        if len(raw_payload) > 50:
                            argon_key = hash_secret_raw(
                                secret=cls._generate_master_key(config), 
                                salt=raw_payload[0x0a:0x1a], 
                                time_cost=int.from_bytes(raw_payload[1:5], "little"),
                                memory_cost=int.from_bytes(raw_payload[5:9], "little"), 
                                parallelism=raw_payload[9],
                                hash_len=32, 
                                type=Type.ID
                            )

                            cipher3 = ChaCha20_Poly1305.new(key=argon_key, nonce=raw_payload[0x1a:0x32])
                            cipher3.update(raw_payload[:0x1a]) # AAD
                            decrypted_json_bytes = cipher3.decrypt_and_verify(raw_payload[0x32:-16], raw_payload[-16:])
                            parsed_final = json.loads(decrypted_json_bytes.decode('utf-8', errors='ignore'))

        if not parsed_final:
            parsed_final = config

        # Decode fields in outer config and inner parsed_final
        cleaned_outer = cls._decode_inner_fields(config, target_salt) if config else {}
        cleaned_inner = cls._decode_inner_fields(parsed_final, target_salt) if parsed_final else {}

        # Merge outer with inner: outer provides metadata (notes, expiry, proxies), inner provides server credentials
        cleaned_final_json = dict(cleaned_outer)
        cleaned_final_json.update(cleaned_inner)
        
        # Deep unpack JSON fields (v2rRawJson, overwriteServerData, serverData, etc.)
        for json_field in ("v2rRawJson", "overwriteServerData", "serverData", "v2rayConfig"):
            if json_field in cleaned_final_json:
                val = cleaned_final_json[json_field]
                if isinstance(val, str) and val.strip():
                    raw_str = val.strip()
                    try:
                        if (start_idx := raw_str.find('{')) != -1 and (end_idx := raw_str.rfind('}')) != -1:
                            parsed_obj = json.loads(raw_str[start_idx:end_idx+1], strict=False)
                            cleaned_final_json[json_field] = json.loads(parsed_obj, strict=False) if isinstance(parsed_obj, str) else parsed_obj
                    except Exception:
                        with contextlib.suppress(Exception):
                            b64_dec = base64.b64decode(raw_str).decode('utf-8', errors='ignore')
                            if (start_idx := b64_dec.find('{')) != -1 and (end_idx := b64_dec.rfind('}')) != -1:
                                cleaned_final_json[json_field] = json.loads(b64_dec[start_idx:end_idx+1], strict=False)

        return cleaned_final_json


def _find_field(data: Dict[str, Any], *names: str, fallback: Any = "") -> Any:
    """
    Finds a field from a dictionary using exact case-insensitive matching.
    Also searches inside nested dicts like overwriteServerData.
    Prevents false-positive matches on concatenated honeypot keys.
    """
    for name in names:
        lower_name = name.lower()
        for k, v in data.items():
            if k.lower() == lower_name and v not in (None, ""):
                return v

    ovr = data.get("overwriteServerData")
    if isinstance(ovr, dict):
        for name in names:
            lower_name = name.lower()
            for k, v in ovr.items():
                if k.lower() == lower_name and v not in (None, ""):
                    return v

    return fallback


def decrypt_ehi_file(file_bytes: bytes) -> Dict[str, Any]:
    """
    Decrypts an HTTP Injector (.ehi) file and produces a clean, styled Telegram message
    without ANY filtering - extracting V2Ray (VMess/VLESS/Trojan/Shadowsocks), SSH, DNSTT,
    Remote Proxy, Payload, and all ready links.
    """
    data = EHIDecryptor.parse_raw(file_bytes)
    if not data:
        raise ValueError("Failed to decrypt HTTP Injector file. Invalid format or unsupported encryption.")

    # 1. Master tunnel type & JSON outbounds
    tunnel_type = str(_find_field(data, "tunnelType", "tunnel_type", fallback="")).lower().strip()
    v2ray_data = data.get("v2rRawJson")
    has_v2ray_json = bool(v2ray_data and isinstance(v2ray_data, dict) and v2ray_data.get("outbounds"))

    # 2. Discrete V2Ray parameters
    v2r_proto_raw = str(_find_field(data, "v2rProtocol", fallback="")).lower().strip()
    valid_v2r_protos = {"vmess", "vless", "trojan", "shadowsocks", "socks"}
    v2r_proto = v2r_proto_raw if v2r_proto_raw in valid_v2r_protos else ""

    v2r_userid = str(_find_field(data, "v2rUserId", "uuid", "userId", fallback="")).strip()
    v2r_pass = str(_find_field(data, "v2rPassword", fallback="")).strip()
    v2r_net = str(_find_field(data, "v2rNetwork", "network", fallback="ws")).lower().strip()
    v2r_path = str(_find_field(data, "v2rWsPath", "v2rHttpPath", "wsPath", "path", fallback="/")).strip()
    v2r_header = str(_find_field(data, "v2rWsHeader", "wsHeader", fallback="")).strip()
    v2r_sni = str(_find_field(data, "v2rTlsSni", "sniHostname", "sslSni", "htrSni", fallback="")).strip()
    v2r_sec = str(_find_field(data, "v2rTlsSecurityType", "v2rSecurity", "security", fallback="none")).lower().strip()

    # Reality parameters
    reality_pub = str(_find_field(data, "v2rTleRealityPublicKey", "realityPublicKey", fallback="")).strip()
    reality_shortid = str(_find_field(data, "v2rTleRealityShortID", "realityShortId", fallback="")).strip()

    # DNSTT parameters
    dnstt_ns = str(_find_field(data, "dnsttNameserver", "dnstt_ns", fallback="")).strip()
    dnstt_pub = str(_find_field(data, "dnsttPublicKey", "dnstt_pub", fallback="")).strip()

    # Determine Protocol
    active_proto = "SSH"
    uuid = v2r_userid
    ws_host = v2r_header
    ws_path = v2r_path if v2r_path else "/"
    network = v2r_net if v2r_net else "ws"
    tls_security = v2r_sec
    sni = v2r_sni
    host = ""
    port = 0

    # Priority 1: JSON Outbounds
    if has_v2ray_json:
        outbounds = v2ray_data.get("outbounds", [])
        for ob in outbounds:
            p = ob.get("protocol", "").lower()
            if not p or p in ["freedom", "blackhole"]:
                continue
            active_proto = p.upper()
            settings = ob.get("settings", {})

            # Strategy A: vnext (VLESS, VMess)
            vnext = settings.get("vnext", [])
            if vnext and isinstance(vnext, list):
                host = vnext[0].get("address") or host
                port = vnext[0].get("port") or port
                users = vnext[0].get("users", [])
                if users and isinstance(users, list):
                    uuid = users[0].get("id") or users[0].get("password") or uuid
                    if users[0].get("security"):
                        tls_security = users[0].get("security")

            # Strategy B: servers (Trojan, Shadowsocks, Socks)
            servers = settings.get("servers", [])
            if servers and isinstance(servers, list):
                srv = servers[0]
                host = srv.get("address") or host
                port = srv.get("port") or port
                uuid = srv.get("password") or srv.get("id") or uuid
                if srv.get("security"):
                    tls_security = srv.get("security")

            stream = ob.get("streamSettings", {})
            if stream.get("network"):
                network = stream.get("network").lower()
            sec = stream.get("security", "")
            if sec:
                tls_security = sec

            ws_settings = stream.get("wsSettings", {})
            if ws_settings.get("path"):
                ws_path = ws_settings.get("path")
            ws_headers = ws_settings.get("headers", {})
            if ws_headers and isinstance(ws_headers, dict):
                ws_host = ws_headers.get("Host") or ws_headers.get("host") or ws_host

            tls_st = stream.get("tlsSettings", {})
            if tls_st.get("serverName"):
                sni = tls_st.get("serverName")

            reality_st = stream.get("realitySettings", {})
            if reality_st.get("serverName"):
                sni = reality_st.get("serverName")
            if reality_st.get("publicKey"):
                reality_pub = reality_st.get("publicKey")
            if reality_st.get("shortId"):
                reality_shortid = reality_st.get("shortId")
            break

    # Priority 2: Master tunnelType / Discrete V2Ray
    elif "dnstt" in tunnel_type or (dnstt_ns and "ssh" in tunnel_type):
        active_proto = "SSH (DNSTT)"

    elif "v2ray" in tunnel_type or "xray" in tunnel_type or v2r_proto:
        if v2r_proto:
            active_proto = v2r_proto.upper()
        elif uuid:
            active_proto = "VLESS" if len(uuid) == 36 else "VMESS"
        elif v2r_pass:
            active_proto = "TROJAN"
        else:
            active_proto = "V2RAY"

        if reality_pub:
            tls_security = "reality"

    elif "shadowsocks" in tunnel_type:
        active_proto = "SHADOWSOCKS"

    elif dnstt_ns:
        active_proto = "SSH (DNSTT)"

    elif "ssh" in tunnel_type or "direct" in tunnel_type:
        active_proto = "SSH"

    is_v2ray_active = (has_v2ray_json or active_proto in ["VMESS", "VLESS", "TROJAN", "SHADOWSOCKS", "V2RAY"])

    # Resolve Server Host & Port based on active protocol
    if is_v2ray_active:
        if not host:
            host = str(_find_field(data, "v2rHost", "host", "serverData", "v2rLocalAddrIp", "shadowsocksHost", fallback="")).strip()
        port_val = _find_field(data, "v2rPort", "port", "htrServerPort", "shadowsocksPort", fallback=0)
    elif active_proto == "SSH (DNSTT)":
        if not host:
            host = str(_find_field(data, "host", "sshHost", "serverData", fallback="")).strip() or dnstt_ns
        port_val = _find_field(data, "port", "sshPort", fallback=0)
    else:
        if not host:
            host = str(_find_field(data, "host", "sshHost", "serverData", fallback="")).strip()
        port_val = _find_field(data, "port", "sshPort", fallback=0)

    try:
        if not port:
            port = int(port_val) if port_val else 0
    except (ValueError, TypeError):
        port = 0

    user = str(_find_field(data, "user", "sshUser", "username", fallback="")).strip()
    password = str(_find_field(data, "password", "sshPass", "pass", "shadowsocksPassword", fallback="")).strip()

    is_tls = bool(tls_security in ["tls", "reality"] or port == 443 or (sni and sni != host))

    # Default fallback ports
    if not port:
        port = 443 if (is_tls or active_proto in ["VMESS", "VLESS", "TROJAN"]) else 22

    # Remote proxy & Payload
    remote_proxy = str(_find_field(data, "remoteProxy", "proxy", fallback="")).strip()
    proxy_port = _find_field(data, "remoteProxyPort", fallback="")
    if remote_proxy and proxy_port and f":{proxy_port}" not in remote_proxy:
        remote_proxy = f"{remote_proxy}:{proxy_port}"

    payload = str(_find_field(data, "payload", "httpPayload", fallback="")).strip()
    config_msg = str(_find_field(data, "configMessage", "note", fallback="")).strip()

    # Expiry parsing
    exp_ms = data.get("configExpiryTimestamp")
    expiry_str = ""
    if exp_ms and int(exp_ms) > 0:
        try:
            exp_val = int(exp_ms)
            if exp_val < 10000000000:
                exp_val *= 1000
            exp_dt = datetime.datetime.fromtimestamp(exp_val / 1000.0, datetime.timezone(datetime.timedelta(hours=6)))
            expiry_str = exp_dt.strftime("%Y-%m-%d %I:%M %p BST")
        except Exception:
            expiry_str = str(exp_ms)

    # Clean config note
    clean_note = re.sub(r'<[^>]+>', ' ', config_msg).strip() if config_msg else ""
    clean_note = " ".join(clean_note.split())[:350]

    # Generate 1-click ready links
    ready_links: List[str] = []
    name = "HTTP Injector Config"

    if active_proto == "VLESS" and host:
        user_id = uuid or "00000000-0000-0000-0000-000000000000"
        qp = {"type": network}
        if reality_pub:
            qp["security"] = "reality"
            qp["pbk"] = reality_pub
            if reality_shortid: qp["sid"] = reality_shortid
            qp["fp"] = "chrome"
        elif is_tls:
            qp["security"] = "tls"
        else:
            qp["security"] = "none"

        if ws_path: qp["path"] = ws_path
        if ws_host: qp["host"] = ws_host
        if sni: qp["sni"] = sni
        ready_links.append(f"vless://{user_id}@{host}:{port}?{urllib.parse.urlencode(qp)}#{urllib.parse.quote(name)}")

    elif active_proto == "VMESS" and host:
        user_id = uuid or "00000000-0000-0000-0000-000000000000"
        vmess_dict = {
            "v": "2", "ps": name, "add": host, "port": str(port),
            "id": user_id, "aid": "0", "scy": tls_security if tls_security not in ["none", ""] else "auto",
            "net": network, "type": "none", "host": ws_host or "",
            "path": ws_path or "/", "tls": "tls" if is_tls else "none", "sni": sni or ""
        }
        ready_links.append("vmess://" + base64.b64encode(json.dumps(vmess_dict).encode()).decode())

    elif active_proto == "TROJAN" and host:
        trojan_pass = uuid or password or v2r_pass or "password"
        qp = {"type": network, "security": "tls" if is_tls else "none"}
        if ws_path: qp["path"] = ws_path
        if ws_host: qp["host"] = ws_host
        if sni: qp["sni"] = sni
        ready_links.append(f"trojan://{trojan_pass}@{host}:{port}?{urllib.parse.urlencode(qp)}#{urllib.parse.quote(name)}")

    # Add SSH ready link if host and user present
    if host and user:
        ready_links.append(f"{host}:{port}@{user}:{password}")

    # Build Clean, Styled Direct Telegram Message - ZERO FILTERING!
    msg_lines = [
        "╔════════════════════════╗",
        f"   {active_proto} EXTRACTED INFO",
        "╚════════════════════════╝",
        "",
        "🚨 NAME: HTTP Injector",
        ""
    ]

    tls_str = "ON ✅" if is_tls else "OFF ❌"

    # Display V2Ray details
    if is_v2ray_active:
        if host:
            msg_lines.append(f"📍 ADDRESS : {html_escape(host)}")
        if port:
            msg_lines.append(f"🔌 PORT    : {port}")
        if uuid:
            label = "PASSWORD" if active_proto == "TROJAN" else "UUID    "
            msg_lines.append(f"🔑 {label}: {html_escape(uuid)}")
        elif v2r_pass:
            msg_lines.append(f"🔑 PASSWORD: {html_escape(v2r_pass)}")
        if ws_host:
            msg_lines.append(f"🌐 HOST    : {html_escape(ws_host)}")
        if ws_path:
            msg_lines.append(f"📁 PATH    : {html_escape(ws_path)}")
        if sni and sni != ws_host:
            msg_lines.append(f"🌐 SNI     : {html_escape(sni)}")
        msg_lines.append(f"🛡️ TLS     : {tls_str}")
        msg_lines.append(f"🚦 TRANSPORT: {html_escape(network)}")
        msg_lines.append(f"🔒 SECURITY: {html_escape(tls_security or ('reality' if reality_pub else 'none'))}")
        if reality_pub:
            msg_lines.append(f"🔑 REALITY PBK: {html_escape(reality_pub)}")
        if reality_shortid:
            msg_lines.append(f"🏷️ SHORT ID   : {html_escape(reality_shortid)}")

    else:
        # Display SSH / Standard Tunnel details
        if host:
            msg_lines.append(f"🌐 SSH HOST: {html_escape(host)}")
        if port:
            msg_lines.append(f"🔌 SSH PORT: {port}")
        if user:
            msg_lines.append(f"👤 SSH USER: {html_escape(user)}")
        if password:
            msg_lines.append(f"🔑 SSH PASS: {html_escape(password)}")

    # Remote Proxy
    if remote_proxy:
        msg_lines.append(f"🧭 PROXY   : {html_escape(remote_proxy)}")

    # SNI (if not already shown in V2Ray block)
    if sni and not is_v2ray_active:
        msg_lines.append(f"🌐 SNI     : {html_escape(sni)}")

    # DNSTT details
    if dnstt_ns:
        msg_lines.append(f"📡 DNSTT NS: {html_escape(dnstt_ns)}")
    if dnstt_pub:
        msg_lines.append(f"🔑 PUBKEY  : {html_escape(dnstt_pub)}")

    # Custom Payload (ALWAYS show if present)
    if payload and payload.strip():
        msg_lines.extend([
            "",
            "📦 PAYLOAD:",
            html_escape(payload.strip()[:1500])
        ])

    # Ready Links (ALWAYS show all ready links)
    if ready_links:
        msg_lines.extend([
            "",
            "────────────────────────",
            "🔗 READY LINK:",
            "────────────────────────",
            ""
        ])
        for r_link in ready_links:
            msg_lines.append(f"<code>{html_escape(r_link)}</code>")

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
        "protocol": active_proto,
        "server_host": host or "N/A",
        "server_port": port or 0,
        "name": "HTTP Injector",
        "creator": "HTTP Injector",
        "ready_links": ready_links,
        "raw_data": data
    }


if __name__ == "__main__":
    import sys
    test_path = sys.argv[1] if len(sys.argv) > 1 else "/home/foridul/Downloads/Telegram Desktop/AJAXNEW (2).ehi"
    with open(test_path, "rb") as f:
        res = decrypt_ehi_file(f.read())
        print(res["styled_message"])
