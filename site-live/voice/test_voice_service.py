import json
import stat
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import voice_service as vs  # noqa: E402

TOKEN = "t" * 40


def script(dirpath, name, body):
    p = Path(dirpath) / name
    p.write_text("#!/bin/sh\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        conv = script(d, "conv", '[ "$1" = "$2" ] && exit 1; cp "$1" "$2"\n')  # ca ffmpeg: aceeași cale = eroare
        stt = script(d, "stt", 'echo "  salut   kelion ($2)  " > "$3.txt"\n')
        tts = script(d, "tts", 'cat > /dev/null; printf "RIFF%040d" 0 > "$1"\n')
        self.voice = vs.Voice({
            "stt": {"convert": [conv, "{in}", "{wav}"], "command": [stt, "{wav}", "{lang}", "{out}"]},
            "tts": {"command": [tts, "{out}"], "models": {"ro": "m.onnx"}},
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_available(self):
        self.assertEqual(self.voice.available(), {"stt": True, "tts": True})
        self.assertEqual(vs.Voice({"stt": {"command": ["/nu/exista"]}}).available()["stt"], False)

    def test_stt_normalizes_text(self):
        self.assertEqual(self.voice.stt(b"x" * 100, "audio/webm;codecs=opus", "ro"), "salut kelion (ro)")

    def test_stt_accepts_wav_input(self):
        self.assertEqual(self.voice.stt(b"RIFF" + b"x" * 100, "audio/wav", "ro"), "salut kelion (ro)")

    def test_stt_rejects_bad_input(self):
        for args in ((b"", "audio/webm", "ro"), (b"x", "text/plain", "ro"), (b"x", "audio/webm", "xx")):
            with self.assertRaises(vs.VoiceError):
                self.voice.stt(*args)

    def test_tts_returns_wav(self):
        self.assertTrue(self.voice.tts("Bună!", "ro").startswith(b"RIFF"))

    def test_missing_package_is_reported(self):
        v = vs.Voice({"tts": {"command": ["/opt/lipsa/piper", "{out}"]}})
        with self.assertRaisesRegex(vs.VoiceError, "Pachet lipsă"):
            v.tts("x", "ro")

    def test_http_auth_and_routes(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), vs.handler_for(self.voice, TOKEN))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d" % server.server_address[1]
        try:
            def call(path, data=None, headers=None):
                req = urllib.request.Request(base + path, data=data, headers=headers or {}, method="POST" if data else "GET")
                try:
                    with urllib.request.urlopen(req, timeout=10) as r:
                        return r.status, r.headers.get("Content-Type"), r.read()
                except urllib.error.HTTPError as e:
                    return e.code, e.headers.get("Content-Type"), e.read()
            auth = {"Authorization": "Bearer " + TOKEN}
            self.assertEqual(call("/v1/health")[0], 401)
            self.assertEqual(json.loads(call("/v1/health", headers=auth)[2]), {"stt": True, "tts": True})
            st, _, body = call("/v1/stt", b"abc", {**auth, "Content-Type": "audio/ogg", "X-Kelion-Lang": "ro"})
            self.assertEqual((st, json.loads(body)["text"]), (200, "salut kelion (ro)"))
            st, ct, body = call("/v1/tts", json.dumps({"text": "Bună"}).encode(), {**auth, "Content-Type": "application/json"})
            self.assertEqual((st, ct), (200, "audio/wav"))
            self.assertEqual(call("/v1/stt", b"abc", {**auth, "Content-Type": "text/plain"})[0], 422)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
