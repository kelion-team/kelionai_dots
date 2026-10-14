"""Serviciul DOTS de voce Kelion (doar loopback, 127.0.0.1).

Primește sunetul unei fraze de la kelionai.app (prin serverul web), îl transcrie local pe server
(ffmpeg + whisper.cpp) și sintetizează răspunsul (piper). Fără API plătit: totul rulează pe kelion-nou.
Comenzile sunt configurate în /etc/kelion-voice/config.json (vezi config.example.json); tokenul vine din
mediul serviciului (KELION_VOICE_TOKEN), nu din repo.

Rute:
  GET  /v1/health  -> {"stt": bool, "tts": bool}
  POST /v1/stt     corp = sunet (audio/webm, audio/ogg, audio/wav), antet X-Kelion-Lang (ex. ro) -> {"text": "..."}
  POST /v1/tts     {"text": "...", "lang": "ro"} -> audio/wav
"""
import argparse
import hmac
import json
import os
import shutil
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_AUDIO = 4 * 1024 * 1024
MAX_TEXT = 4000
AUDIO_TYPES = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mp4": ".m4a"}
LANGS = {"ro", "en", "fr", "de", "es", "it", "pt", "hu", "pl", "uk", "ru", "tr", "ar", "hi", "zh", "ja"}


class VoiceError(Exception):
    pass


def _fill(argv, values):
    return [part.format(**values) for part in argv]


def _run(argv, timeout, stdin=None):
    try:
        done = subprocess.run(argv, input=stdin, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise VoiceError("Pachet lipsă pe server: " + argv[0]) from None
    except subprocess.TimeoutExpired:
        raise VoiceError("Timp depășit: " + Path(argv[0]).name) from None
    if done.returncode != 0:
        raise VoiceError(Path(argv[0]).name + ": " + done.stderr.decode(errors="replace")[-300:].strip())
    return done


class Voice:
    """STT/TTS prin comenzi locale configurate. Fiecare comandă e o listă argv cu locuri {in} {wav} {out} {lang} {model}."""

    def __init__(self, config):
        self.config = config

    def available(self):
        def ok(section):
            spec = self.config.get(section) or {}
            cmds = [c for c in (spec.get("convert"), spec.get("command")) if c]
            return bool(cmds) and all(shutil.which(c[0]) or Path(c[0]).is_file() for c in cmds)
        return {"stt": ok("stt"), "tts": ok("tts")}

    def stt(self, audio, content_type, lang):
        spec = self.config.get("stt") or {}
        if lang not in LANGS:
            raise VoiceError("Limbă nesuportată")
        suffix = AUDIO_TYPES.get(content_type.split(";")[0].strip())
        if not suffix:
            raise VoiceError("Format audio nesuportat")
        if not audio or len(audio) > MAX_AUDIO:
            raise VoiceError("Sunet gol sau prea mare")
        with tempfile.TemporaryDirectory(prefix="kelion-stt-") as tmp:
            values = {"in": str(Path(tmp, "in" + suffix)), "wav": str(Path(tmp, "in.wav")),
                      "out": str(Path(tmp, "out")), "lang": lang, "model": spec.get("model", "")}
            Path(values["in"]).write_bytes(audio)
            if spec.get("convert"):
                _run(_fill(spec["convert"], values), spec.get("timeout", 60))
            done = _run(_fill(spec["command"], values), spec.get("timeout", 120))
            text_file = Path(values["out"] + ".txt")
            text = text_file.read_text(encoding="utf-8", errors="replace") if text_file.exists() else done.stdout.decode(errors="replace")
        text = " ".join(text.split())
        return text[:MAX_TEXT]

    def tts(self, text, lang):
        spec = self.config.get("tts") or {}
        if not isinstance(text, str) or not text.strip():
            raise VoiceError("Text gol")
        model = (spec.get("models") or {}).get(lang) or spec.get("model", "")
        with tempfile.TemporaryDirectory(prefix="kelion-tts-") as tmp:
            values = {"out": str(Path(tmp, "out.wav")), "lang": lang, "model": model, "in": "", "wav": ""}
            _run(_fill(spec["command"], values), spec.get("timeout", 120), stdin=text[:MAX_TEXT].encode())
            out = Path(values["out"])
            if not out.exists() or out.stat().st_size < 44:
                raise VoiceError("Sinteza nu a produs sunet")
            return out.read_bytes()


def handler_for(voice, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # fără conținut audio sau text în jurnale

        def reply(self, status, body, content_type="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            given = self.headers.get("Authorization", "")
            return self.client_address[0] in ("127.0.0.1", "::1") and hmac.compare_digest(given, "Bearer " + token)

        def read_body(self, limit):
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                raise VoiceError("Content-Length lipsă") from None
            if length <= 0 or length > limit:
                raise VoiceError("Corp gol sau prea mare")
            return self.rfile.read(length)

        def do_GET(self):
            if not self.authorized():
                return self.reply(401, {"error": "Unauthorized"})
            if self.path == "/v1/health":
                return self.reply(200, voice.available())
            return self.reply(404, {"error": "Unknown endpoint"})

        def do_POST(self):
            if not self.authorized():
                return self.reply(401, {"error": "Unauthorized"})
            try:
                if self.path == "/v1/stt":
                    audio = self.read_body(MAX_AUDIO)
                    return self.reply(200, {"text": voice.stt(audio, self.headers.get("Content-Type", ""), self.headers.get("X-Kelion-Lang", "ro"))})
                if self.path == "/v1/tts":
                    data = json.loads(self.read_body(MAX_TEXT * 4 + 200))
                    if not isinstance(data, dict) or set(data) - {"text", "lang"}:
                        raise VoiceError("Cerere invalidă")
                    return self.reply(200, voice.tts(data.get("text"), data.get("lang", "ro")), "audio/wav")
                return self.reply(404, {"error": "Unknown endpoint"})
            except (VoiceError, json.JSONDecodeError, UnicodeDecodeError) as error:
                return self.reply(422, {"error": str(error)})
    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="/etc/kelion-voice/config.json")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args(argv)
    token = os.environ.get("KELION_VOICE_TOKEN", "")
    if len(token) < 32:
        raise SystemExit("KELION_VOICE_TOKEN lipsește din mediul serviciului")
    voice = Voice(json.loads(Path(args.config).read_text(encoding="utf-8")))
    print("[kelion-voice] " + json.dumps(voice.available()), flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(voice, token)).serve_forever()


if __name__ == "__main__":
    main()
