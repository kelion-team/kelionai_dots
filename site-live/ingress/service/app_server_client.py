"""Puntea măștii KelionAI către Codex app-server de pe kelion-nou (doar loopback).

Masca din kelionai.app vorbește cu această punte; puntea ține o singură conexiune JSON-RPC (WebSocket)
către `codex app-server` (implicit ws://127.0.0.1:18767) și expune 1:1 operațiile din schema generată
(orchestration/app-server-schema, listate în app_server_methods.json). Nimic nu se inventează: metodele
necunoscute schemei sunt refuzate, iar cele cu efect pe cont, plăți sau configurația serverului sunt
blocate implicit, cu motivul exact, și se pot activa doar din configurația punții.

HTTP pe 127.0.0.1 (token în KELION_MASK_TOKEN, niciodată în repo):
  GET  /v1/health    -> starea conexiunii și a inițializării
  GET  /v1/methods   -> metodele permise și cele blocate (cu motiv)
  GET  /v1/pending   -> cererile serverului care așteaptă răspuns (aprobări, întrebări)
  POST /v1/rpc       {"method": "...", "params": {...}} -> {"result": ...} sau {"error": {...}}
  POST /v1/events    {"since": n, "timeout": s} -> notificări și cereri ale serverului, cu număr de ordine
  POST /v1/respond   {"id": ..., "result": {...}} sau {"id": ..., "error": {...}} -> răspuns la o cerere a serverului
"""
import argparse
import base64
import collections
import hashlib
import hmac
import json
import os
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
METHODS = json.loads((HERE / "app_server_methods.json").read_text(encoding="utf-8"))
MAX_BODY = 12 * 1024 * 1024
MAX_MESSAGE = 64 * 1024 * 1024
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

_ACCOUNT = "schimbă autentificarea contului de pe server; se face doar de Adrian, direct pe server"
_CONFIG = "modifică configurația Codex de pe kelion-nou; se activează doar din configurația punții"
_PLUGINS = "instalează sau modifică pluginuri/conectori pe server; regula: fără conectori noi nevalidați"
_EXEC = "execuție directă de comenzi pe kelion-nou din browser; se activează doar din configurația punții"
BLOCKED = {
    "initialize": "intern: puntea face inițializarea conexiunii",
    "account/login/start": _ACCOUNT, "account/login/cancel": _ACCOUNT, "account/logout": _ACCOUNT,
    "account/gatewayOAuth/login": _ACCOUNT, "account/gatewayOAuth/cancel": _ACCOUNT,
    "account/rateLimitResetCredit/consume": "consumă credit; regula plafonului de plată (plățile le face doar Adrian)",
    "account/sendAddCreditsNudgeEmail": "trimite e-mail de cumpărare credite; regula plafonului de plată",
    "windowsSandbox/setupStart": "doar pentru Windows; kelion-nou e Linux",
    "windowsSandbox/readiness": "doar pentru Windows; kelion-nou e Linux",
    "command/exec": _EXEC, "command/exec/write": _EXEC, "command/exec/terminate": _EXEC,
    "command/exec/resize": _EXEC, "thread/shellCommand": _EXEC,
    "fs/remove": "șterge fișiere de pe server; se activează doar din configurația punții",
    "fs/copy": "copiază fișiere pe server în afara directorului de încărcări; se activează doar din configurație",
    "config/value/write": _CONFIG, "config/batchWrite": _CONFIG, "skills/config/write": _CONFIG,
    "skills/extraRoots/set": _CONFIG, "experimentalFeature/enablement/set": _CONFIG,
    "externalAgentConfig/import": _CONFIG, "externalAgentConfig/import/recordHistory": _CONFIG,
    "config/mcpServer/reload": _CONFIG,
    "marketplace/add": _PLUGINS, "marketplace/remove": _PLUGINS, "marketplace/upgrade": _PLUGINS,
    "plugin/install": _PLUGINS, "plugin/uninstall": _PLUGINS, "plugin/reconcile": _PLUGINS,
    "plugin/share/save": _PLUGINS, "plugin/share/updateTargets": _PLUGINS,
    "plugin/share/checkout": _PLUGINS, "plugin/share/delete": _PLUGINS,
    "mcpServer/oauth/login": "autorizare OAuth nouă pentru un conector; doar Adrian",
    "feedback/upload": "trimite date în afara serverului; necesită aprobarea lui Adrian",
}
# Cereri ale serverului la care masca nu poate răspunde (capabilități neactivate la inițializare).
AUTO_DECLINE = {"account/chatgptAuthTokens/refresh", "attestation/generate", "item/tool/call"}
# Operații cu fișiere scrise: permise doar în directorul de încărcări al măștii (imagini, atașamente).
UPLOAD_SCOPED = {"fs/writeFile": "path", "fs/createDirectory": "path"}
SLOW = {"thread/compact/start": 600, "review/start": 600, "plugin/list": 180, "app/list": 180, "mcpServerStatus/list": 180}


class RpcError(Exception):
    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code, self.message, self.data = code, message, data

    def as_dict(self):
        return {"code": self.code, "message": self.message, **({"data": self.data} if self.data is not None else {})}


class WebSocket:
    """Client WebSocket minimal (RFC 6455): cadre text, fragmentare, ping/pong, închidere."""

    def __init__(self, url, headers=None, timeout=10):
        parts = urlsplit(url)
        if parts.scheme != "ws" or parts.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("Doar ws:// pe loopback")
        self.sock = socket.create_connection((parts.hostname, parts.port or 80), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        lines = ["GET {} HTTP/1.1".format(parts.path or "/"), "Host: {}:{}".format(parts.hostname, parts.port or 80),
                 "Upgrade: websocket", "Connection: Upgrade", "Sec-WebSocket-Key: " + key, "Sec-WebSocket-Version: 13"]
        lines += ["{}: {}".format(k, v) for k, v in (headers or {}).items()]
        self.sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk or len(head) > 65536:
                raise ConnectionError("Handshake WebSocket eșuat")
            head += chunk
        head, self.buffer = head.split(b"\r\n\r\n", 1)
        status, *fields = head.decode("latin-1").split("\r\n")
        if " 101 " not in status + " ":
            raise ConnectionError("Handshake WebSocket refuzat: " + status[:80])
        accept = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        got = {f.split(":", 1)[0].strip().lower(): f.split(":", 1)[1].strip() for f in fields if ":" in f}
        if got.get("sec-websocket-accept") != accept:
            raise ConnectionError("Sec-WebSocket-Accept invalid")
        self.sock.settimeout(None)
        self.lock = threading.Lock()

    def _frame(self, opcode, payload):
        head = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack("!H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack("!Q", n)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload)) if n < 4096 else _xor(payload, mask)
        with self.lock:
            self.sock.sendall(head + mask + masked)

    def send(self, text):
        self._frame(0x1, text.encode("utf-8"))

    def _read(self, n):
        while len(self.buffer) < n:
            chunk = self.sock.recv(max(65536, n - len(self.buffer)))
            if not chunk:
                raise ConnectionError("Conexiune închisă")
            self.buffer += chunk
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def recv(self):
        parts, total = [], 0
        while True:
            b1, b2 = self._read(2)
            fin, opcode, n = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            # Limita se verifică înainte de citirea conținutului (inclusiv totalul fragmentelor).
            if n > MAX_MESSAGE or (opcode in (0x0, 0x1, 0x2) and total + n > MAX_MESSAGE):
                raise ConnectionError("Mesaj prea mare")
            payload = self._read(n)
            if mask:
                payload = _xor(payload, mask)
            if opcode == 0x8:
                raise ConnectionError("Serverul a închis conexiunea")
            if opcode == 0x9:
                self._frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            total += n
            parts.append(payload)
            if fin:
                return b"".join(parts).decode("utf-8")

    def close(self):
        try:
            self._frame(0x8, b"")
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


def _xor(data, mask):
    key = (mask * (len(data) // 4 + 1))[:len(data)]
    return (int.from_bytes(data, "big") ^ int.from_bytes(key, "big")).to_bytes(len(data), "big") if data else b""


class Bridge:
    """O conexiune persistentă la app-server; reconectare automată; evenimente cu număr de ordine."""

    def __init__(self, url, headers=None, enable=(), uploads_dir="/var/lib/kelion-magistrala/mask-uploads",
                 client_version="1", connect=WebSocket, keep=5000):
        self.url, self.headers, self.connect = url, headers or {}, connect
        self.blocked = {m: r for m, r in BLOCKED.items() if m not in set(enable)}
        self.allowed = [m for m in METHODS["client_requests"] if m not in self.blocked]
        self.uploads_dir = os.path.realpath(uploads_dir)
        self.client_version = client_version
        self.ws = None
        self.ready = threading.Event()
        self.lock = threading.Lock()
        self.cond = threading.Condition()
        self.events = collections.deque(maxlen=keep)
        self.seq = 0
        self.next_id = 0
        self.waiting = {}
        self.pending = {}
        self.server_info = None
        self.last_error = None
        self.stopped = False

    # --- conexiune ---
    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.stopped = True
        if self.ws:
            self.ws.close()

    def _loop(self):
        delay = 1
        while not self.stopped:
            try:
                self.ws = self.connect(self.url, self.headers)
                threading.Thread(target=self._reader, args=(self.ws,), daemon=True).start()
                self.server_info = self._call("initialize", {
                    "clientInfo": {"name": "kelionai_mask", "title": "KelionAI", "version": self.client_version},
                    "capabilities": {"experimentalApi": True}}, 30)
                self.ws.send(json.dumps({"method": "initialized"}))
                self.last_error = None
                self.ready.set()
                self._push({"kind": "bridge", "method": "bridge/connected", "params": {}})
                delay = 1
                while not self.stopped and self.ws is not None and self.ready.is_set():
                    time.sleep(0.5)
            except Exception as error:  # conexiune, handshake, inițializare
                self.last_error = str(error)[:300]
                self._drop(error)
            if not self.stopped:
                time.sleep(delay)
                delay = min(delay * 2, 30)

    def _drop(self, error):
        was = self.ready.is_set()
        self.ready.clear()
        ws, self.ws = self.ws, None
        if ws:
            ws.close()
        with self.lock:
            waiting, self.waiting = self.waiting, {}
            self.pending.clear()
        for slot in waiting.values():
            slot["error"] = RpcError(-32000, "Conexiunea cu app-server s-a întrerupt")
            slot["done"].set()
        if was:
            self._push({"kind": "bridge", "method": "bridge/disconnected", "params": {"reason": str(error)[:300]}})

    def _reader(self, ws):
        try:
            while True:
                self._dispatch(json.loads(ws.recv()))
        except Exception as error:
            if self.ws is ws:
                self.last_error = str(error)[:300]
                self._drop(error)

    def _dispatch(self, msg):
        if "method" not in msg:
            with self.lock:
                slot = self.waiting.pop(msg.get("id"), None)
            if slot:
                if "error" in msg:
                    e = msg["error"] or {}
                    slot["error"] = RpcError(e.get("code", -32000), e.get("message", "Eroare"), e.get("data"))
                else:
                    slot["result"] = msg.get("result")
                slot["done"].set()
            return
        method, params = msg["method"], msg.get("params")
        if "id" in msg:
            if method in AUTO_DECLINE:
                self._send({"id": msg["id"], "error": {"code": -32601, "message": "Nesuportat de masca KelionAI"}})
                return
            with self.lock:
                self.pending[json.dumps(msg["id"])] = {"id": msg["id"], "method": method, "params": params}
            self._push({"kind": "request", "id": msg["id"], "method": method, "params": params})
            return
        if method == "serverRequest/resolved" and isinstance(params, dict):
            with self.lock:
                self.pending.pop(json.dumps(params.get("requestId")), None)
        self._push({"kind": "notification", "method": method, "params": params})

    def _push(self, event):
        with self.cond:
            self.seq += 1
            event["seq"] = self.seq
            self.events.append(event)
            self.cond.notify_all()

    def _send(self, msg):
        ws = self.ws
        if ws is None:
            raise RpcError(-32000, "app-server indisponibil")
        ws.send(json.dumps(msg, ensure_ascii=False))

    def _call(self, method, params, timeout):
        with self.lock:
            self.next_id += 1
            rid = self.next_id
            slot = self.waiting[rid] = {"done": threading.Event()}
        try:
            self._send({"id": rid, "method": method, **({"params": params} if params is not None else {})})
        except Exception:
            with self.lock:
                self.waiting.pop(rid, None)
            raise
        if not slot["done"].wait(timeout):
            with self.lock:
                self.waiting.pop(rid, None)
            raise RpcError(-32001, "Timp depășit pentru " + method)
        if "error" in slot:
            raise slot["error"]
        return slot.get("result")

    # --- operații pentru mască ---
    def rpc(self, method, params=None):
        if method in self.blocked:
            raise RpcError(-32003, "Blocat: " + self.blocked[method])
        if method not in METHODS["client_requests"]:
            raise RpcError(-32601, "Metodă inexistentă în schema app-server: " + str(method)[:80])
        if method in UPLOAD_SCOPED:
            target = os.path.realpath(str((params or {}).get(UPLOAD_SCOPED[method], "")))
            if os.path.commonpath([target, self.uploads_dir]) != self.uploads_dir:
                raise RpcError(-32003, "Blocat: scrierea e permisă doar în " + self.uploads_dir)
        if not self.ready.wait(5):
            raise RpcError(-32000, "app-server indisponibil: " + (self.last_error or "se conectează"))
        return self._call(method, params, SLOW.get(method, 120))

    def respond(self, request_id, result=None, error=None):
        # Cererea rămâne în așteptare până când trimiterea răspunsului reușește; la eșec nu se retrimite automat.
        key = json.dumps(request_id)
        with self.lock:
            if key not in self.pending:
                raise KeyError(request_id)
        self._send({"id": request_id, **({"error": error} if error is not None else {"result": result})})
        with self.lock:
            self.pending.pop(key, None)

    def wait_events(self, since, timeout):
        with self.cond:
            if self.seq <= since:
                self.cond.wait_for(lambda: self.seq > since or self.stopped, timeout)
            oldest = self.events[0]["seq"] if self.events else self.seq + 1
            items = [e for e in self.events if e["seq"] > since]
            return {"events": items, "last": self.seq, "reset": since + 1 < oldest and since < self.seq}

    def health(self):
        with self.lock:
            pending = len(self.pending)
        return {"connected": self.ready.is_set(), "url": self.url, "server": self.server_info,
                "last_error": self.last_error, "pending_requests": pending, "last_event": self.seq}

    def methods(self):
        return {"allowed": self.allowed, "blocked": self.blocked, "server_requests": METHODS["server_requests"],
                "uploads_dir": self.uploads_dir, "source": METHODS["source"]}

    def pending_requests(self):
        with self.lock:
            return list(self.pending.values())


def handler_for(bridge, token):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass  # fără conținutul conversațiilor în jurnale

        def reply(self, status, body):
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            given = self.headers.get("Authorization", "")
            return self.client_address[0] in ("127.0.0.1", "::1") and hmac.compare_digest(given, "Bearer " + token)

        def body(self):
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                raise ValueError("Content-Length lipsă") from None
            if length <= 0 or length > MAX_BODY:
                raise ValueError("Corp gol sau prea mare")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Obiect JSON necesar")
            return data

        def do_GET(self):
            if not self.authorized():
                return self.reply(401, {"error": "Unauthorized"})
            routes = {"/v1/health": bridge.health, "/v1/methods": bridge.methods,
                      "/v1/pending": lambda: {"requests": bridge.pending_requests()}}
            if self.path in routes:
                return self.reply(200, routes[self.path]())
            return self.reply(404, {"error": "Unknown endpoint"})

        def do_POST(self):
            if not self.authorized():
                return self.reply(401, {"error": "Unauthorized"})
            try:
                data = self.body()
                if self.path == "/v1/rpc":
                    if set(data) - {"method", "params"} or not isinstance(data.get("method"), str):
                        raise ValueError("Cerere invalidă")
                    params = data.get("params")
                    if params is not None and not isinstance(params, dict):
                        raise ValueError("params trebuie să fie obiect")
                    try:
                        return self.reply(200, {"result": bridge.rpc(data["method"], params)})
                    except RpcError as error:
                        return self.reply(200, {"error": error.as_dict()})
                if self.path == "/v1/events":
                    since = data.get("since", 0)
                    timeout = min(max(float(data.get("timeout", 25)), 0), 25)
                    if not isinstance(since, int) or since < 0:
                        raise ValueError("since invalid")
                    return self.reply(200, bridge.wait_events(since, timeout))
                if self.path == "/v1/respond":
                    if "id" not in data or set(data) - {"id", "result", "error"} or ("result" in data) == ("error" in data):
                        raise ValueError("Cerere invalidă")
                    try:
                        bridge.respond(data["id"], data.get("result"), data.get("error"))
                    except KeyError:
                        return self.reply(404, {"error": "Cererea serverului nu mai așteaptă răspuns"})
                    except RpcError as error:
                        return self.reply(503, {"error": error.message})
                    return self.reply(200, {"ok": True})
                return self.reply(404, {"error": "Unknown endpoint"})
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
                return self.reply(400, {"error": str(error)[:200]})
    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="/etc/kelion-mask/config.json")
    args = parser.parse_args(argv)
    token = os.environ.get("KELION_MASK_TOKEN", "")
    if len(token) < 32:
        raise SystemExit("KELION_MASK_TOKEN lipsește din mediul serviciului")
    config = json.loads(Path(args.config).read_text(encoding="utf-8")) if Path(args.config).is_file() else {}
    headers = {}
    if os.environ.get("KELION_APPSERVER_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["KELION_APPSERVER_TOKEN"]
    bridge = Bridge(config.get("app_server_url", "ws://127.0.0.1:18767/"), headers, config.get("enable", ()),
                    config.get("uploads_dir", "/var/lib/kelion-magistrala/mask-uploads"))
    bridge.start()
    port = int(config.get("port", 8775))
    print("[kelion-mask] puntea ascultă pe 127.0.0.1:{} -> {}".format(port, bridge.url), flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), handler_for(bridge, token)).serve_forever()


if __name__ == "__main__":
    main()
