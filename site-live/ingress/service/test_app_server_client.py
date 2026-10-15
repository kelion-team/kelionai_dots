import base64
import hashlib
import json
import socket
import struct
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import app_server_client as asc

SCHEMA = Path(__file__).resolve().parents[3] / "orchestration" / "app-server-schema"


class FakeAppServer:
    """app-server simulat: WebSocket real pe loopback, răspunde ca în schemă."""

    def __init__(self):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.port = self.listener.getsockname()[1]
        self.received = []
        self.conn = None
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            self.conn = conn
            threading.Thread(target=self.handle, args=(conn,), daemon=True).start()

    def handle(self, conn):
        head = b""
        while b"\r\n\r\n" not in head:
            head += conn.recv(4096)
        key = [l.split(":", 1)[1].strip() for l in head.decode().split("\r\n") if l.lower().startswith("sec-websocket-key")][0]
        accept = base64.b64encode(hashlib.sha1((key + asc.WS_GUID).encode()).digest()).decode()
        conn.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      "Sec-WebSocket-Accept: " + accept + "\r\n\r\n").encode())
        buf = b""

        def read(n):
            nonlocal buf
            while len(buf) < n:
                chunk = conn.recv(65536)
                if not chunk:
                    raise ConnectionError
                buf += chunk
            out, buf = buf[:n], buf[n:]
            return out
        try:
            while True:
                b1, b2 = read(2)
                n = b2 & 0x7F
                if n == 126:
                    n = struct.unpack("!H", read(2))[0]
                elif n == 127:
                    n = struct.unpack("!Q", read(8))[0]
                mask = read(4)
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(read(n)))
                if b1 & 0x0F == 0x8:
                    return
                msg = json.loads(payload)
                self.received.append(msg)
                self.answer(msg)
        except (ConnectionError, OSError):
            return

    def send(self, msg):
        data = json.dumps(msg).encode()
        n = len(data)
        head = bytes([0x81]) + (bytes([n]) if n < 126 else bytes([126]) + struct.pack("!H", n) if n < 65536
                                else bytes([127]) + struct.pack("!Q", n))
        self.conn.sendall(head + data)

    def answer(self, msg):
        method, rid = msg.get("method"), msg.get("id")
        if rid is None:
            return
        if method == "initialize":
            self.send({"id": rid, "result": {"userAgent": "codex/0.162.0-alpha.17.2"}})
        elif method == "model/list":
            self.send({"id": rid, "result": {"data": [{"id": "gpt-6-astra", "displayName": "Astra"}], "nextCursor": None}})
        elif method == "thread/start":
            self.send({"id": rid, "result": {"thread": {"id": "t1"}, "model": "gpt-6-astra"}})
            self.send({"method": "thread/started", "params": {"thread": {"id": "t1"}}})
        elif method == "turn/start":
            self.send({"id": rid, "result": {"turn": {"id": "u1", "status": "inProgress", "items": []}}})
            self.send({"method": "item/agentMessage/delta", "params": {"threadId": "t1", "turnId": "u1", "itemId": "i1", "delta": "Bun"}})
            self.send({"id": 900, "method": "item/fileChange/requestApproval", "params": {"threadId": "t1", "turnId": "u1", "itemId": "i2"}})
            self.send({"id": 901, "method": "attestation/generate", "params": {}})
        elif method == "fs/writeFile":
            self.send({"id": rid, "result": {}})
        elif method == "big":
            pass
        elif method == "thread/read":
            self.send({"id": rid, "result": {"thread": {"id": "t1", "preview": "x" * 70000}}})
        else:
            self.send({"id": rid, "error": {"code": -32601, "message": "unknown"}})

    def close(self):
        self.listener.close()
        if self.conn:
            self.conn.close()


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.server = FakeAppServer()
        self.uploads = tempfile.mkdtemp()
        self.bridge = asc.Bridge("ws://127.0.0.1:{}/".format(self.server.port), uploads_dir=self.uploads)
        self.bridge.start()
        self.assertTrue(self.bridge.ready.wait(5), self.bridge.last_error)

    def tearDown(self):
        self.bridge.stop()
        self.server.close()

    def test_initialize_then_initialized(self):
        first, second = self.server.received[:2]
        self.assertEqual(first["method"], "initialize")
        self.assertEqual(first["params"]["clientInfo"]["name"], "kelionai_mask")
        self.assertEqual(second, {"method": "initialized"})
        self.assertTrue(self.bridge.health()["connected"])

    def test_rpc_result_and_large_frames(self):
        self.assertEqual(self.bridge.rpc("model/list", {})["data"][0]["id"], "gpt-6-astra")
        self.assertEqual(len(self.bridge.rpc("thread/read", {"threadId": "t1"})["thread"]["preview"]), 70000)

    def test_blocked_and_unknown_methods_never_reach_server(self):
        before = len(self.server.received)
        with self.assertRaises(asc.RpcError) as blocked:
            self.bridge.rpc("account/rateLimitResetCredit/consume", {})
        self.assertIn("plafonului", blocked.exception.message)
        with self.assertRaises(asc.RpcError):
            self.bridge.rpc("web/search", {})
        with self.assertRaises(asc.RpcError):
            self.bridge.rpc("fs/writeFile", {"path": "/etc/passwd", "dataBase64": ""})
        self.assertEqual(len(self.server.received), before)

    def test_upload_scope_allows_writes_inside(self):
        self.assertEqual(self.bridge.rpc("fs/writeFile", {"path": self.uploads + "/a.png", "dataBase64": "AA=="}), {})

    def test_enable_unblocks_from_config(self):
        bridge = asc.Bridge("ws://127.0.0.1:1/", enable=["command/exec"])
        self.assertNotIn("command/exec", bridge.blocked)
        self.assertIn("command/exec", bridge.allowed)

    def test_stream_events_requests_and_response(self):
        self.bridge.rpc("thread/start", {})
        self.bridge.rpc("turn/start", {"threadId": "t1", "input": [{"type": "text", "text": "Salut"}]})
        deadline = time.time() + 5
        while time.time() < deadline and not (self.bridge.pending_requests() and any(m.get("id") == 901 for m in self.server.received)):
            time.sleep(0.05)
        events = self.bridge.wait_events(0, 1)["events"]
        methods = [e["method"] for e in events]
        self.assertIn("thread/started", methods)
        self.assertIn("item/agentMessage/delta", methods)
        self.assertNotIn("attestation/generate", methods)
        declined = [m for m in self.server.received if m.get("id") == 901]
        self.assertTrue(declined and "error" in declined[0])
        pending = self.bridge.pending_requests()
        self.assertEqual([p["id"] for p in pending], [900])
        self.bridge.respond(900, {"decision": "decline"})
        time.sleep(0.2)
        self.assertIn({"id": 900, "result": {"decision": "decline"}}, self.server.received)
        self.assertEqual(self.bridge.pending_requests(), [])
        with self.assertRaises(KeyError):
            self.bridge.respond(900, {"decision": "accept"})
        last = self.bridge.wait_events(0, 0)["last"]
        self.assertEqual(self.bridge.wait_events(last, 0.2)["events"], [])

    def test_reconnects_after_drop(self):
        self.server.conn.shutdown(socket.SHUT_RDWR)
        deadline = time.time() + 6
        while time.time() < deadline and not (self.bridge.ready.is_set() and len(
                [m for m in self.server.received if m.get("method") == "initialize"]) >= 2):
            time.sleep(0.1)
        self.assertEqual(self.bridge.rpc("model/list", {})["data"][0]["displayName"], "Astra")

    def test_http_routes_require_token(self):
        token = "t" * 40
        http = ThreadingHTTPServer(("127.0.0.1", 0), asc.handler_for(self.bridge, token))
        threading.Thread(target=http.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:{}".format(http.server_address[1])

        def call(path, data=None, auth=True):
            req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                                         headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if auth else {})})
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        try:
            self.assertEqual(call("/v1/health", auth=False)[0], 401)
            self.assertTrue(call("/v1/health")[1]["connected"])
            self.assertIn("command/exec", call("/v1/methods")[1]["blocked"])
            self.assertEqual(call("/v1/rpc", {"method": "model/list", "params": {}})[1]["result"]["data"][0]["id"], "gpt-6-astra")
            self.assertEqual(call("/v1/rpc", {"method": "account/logout"})[1]["error"]["code"], -32003)
            self.assertEqual(call("/v1/rpc", {"method": "model/list", "extra": 1})[0], 400)
            self.assertEqual(call("/v1/events", {"since": 0, "timeout": 0})[0], 200)
            self.assertEqual(call("/v1/respond", {"id": 12345, "result": {}})[0], 404)
        finally:
            http.shutdown()


class SchemaTests(unittest.TestCase):
    @unittest.skipUnless(SCHEMA.is_dir(), "schema app-server absentă")
    def test_method_list_matches_generated_schema(self):
        def methods(name):
            return [v["properties"]["method"]["enum"][0] for v in json.loads((SCHEMA / name).read_text())["oneOf"]]
        self.assertEqual(asc.METHODS["client_requests"], methods("ClientRequest.json"))
        self.assertEqual(asc.METHODS["server_requests"], methods("ServerRequest.json"))
        self.assertEqual(asc.METHODS["server_notifications"], methods("ServerNotification.json"))

    def test_every_blocked_method_exists_in_schema(self):
        for method in asc.BLOCKED:
            self.assertIn(method, asc.METHODS["client_requests"])
        for method in asc.AUTO_DECLINE:
            self.assertIn(method, asc.METHODS["server_requests"])


if __name__ == "__main__":
    unittest.main()
