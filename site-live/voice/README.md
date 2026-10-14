# Serviciul DOTS de voce Kelion

Ruta audio rămâne în kelionai.app. Fiecare frază ajunge pe server, unde e transcrisă local, trimisă pe
magistrală (Kelion alege canalul: chat / codex / work / magentic), iar răspunsul e sintetizat local și
redat în pagină. Vorbitul peste răspuns îl oprește (full duplex prin întrerupere).

```
browser (microfon, detector de vorbire) ─► /api/voice/stt ─► kelion-voice: ffmpeg + whisper.cpp ─► text
text ─► /api/tasks ─► magistrala (Kelion alege canalul) ─► răspuns
răspuns ─► /api/voice/tts ─► kelion-voice: piper ─► sunet ─► redare în pagină
```

Totul rulează pe kelion-nou, fără API plătit și fără cota de lucru pentru transcriere/sinteză.
Doar răspunsul (canalul ales de Kelion) consumă din abonamentul Business.

## Pachete Ubuntu (lipsesc azi pe server)

Ca root pe kelion-nou:

```bash
apt-get update && apt-get install -y ffmpeg build-essential cmake git curl
install -d -m 0755 /opt/kelion-voice/models /opt/kelion-voice/voices /opt/kelion-app/voice /etc/kelion-voice

# Recunoașterea vorbirii: whisper.cpp + model multilingv (include româna)
git clone --depth 1 https://github.com/ggml-org/whisper.cpp /opt/kelion-voice/whisper.cpp
cmake -S /opt/kelion-voice/whisper.cpp -B /opt/kelion-voice/whisper.cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build /opt/kelion-voice/whisper.cpp/build -j"$(nproc)" --target whisper-cli
sh /opt/kelion-voice/whisper.cpp/models/download-ggml-model.sh small /opt/kelion-voice/models

# Sinteza vocii: piper + vocea română
curl -L https://github.com/rhasspy/piper/releases/latest/download/piper_linux_x86_64.tar.gz | tar -xz -C /opt/kelion-voice
curl -L -o /opt/kelion-voice/voices/ro_RO-mihai-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/ro/ro_RO/mihai/medium/ro_RO-mihai-medium.onnx
curl -L -o /opt/kelion-voice/voices/ro_RO-mihai-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/ro/ro_RO/mihai/medium/ro_RO-mihai-medium.onnx.json
```

Verificați căile din `config.example.json` față de ce s-a instalat efectiv (numele fișierului de model
whisper, directorul piper) și ajustați-le în `/etc/kelion-voice/config.json`.

## Instalare serviciu

```bash
REPO=<clona kelionai_dots la main>
cp "$REPO/site-live/voice/voice_service.py" /opt/kelion-app/voice/
cp "$REPO/site-live/voice/config.example.json" /etc/kelion-voice/config.json
TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
install -m 0600 /dev/null /etc/kelion-voice/voice.env && echo "KELION_VOICE_TOKEN=$TOKEN" > /etc/kelion-voice/voice.env
# același token în mediul serverului web (fișierul de mediu al serviciului web): KELION_VOICE_TOKEN=$TOKEN
install -m 0644 "$REPO/site-live/voice/kelion-voice.service" /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now kelion-voice && systemctl restart <serviciul web kelionai.app>
```

Tokenul nu se scrie în repo, în chat sau în jurnale.

## Verificare

- `journalctl -u kelion-voice -n 5` → `[kelion-voice] {"stt": true, "tts": true}`
- `curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8770/v1/health` → `{"stt": true, "tts": true}`
- pe kelionai.app, `/api/config` → `"voice": true`; microfonul afișează „Voce prin serviciul DOTS de pe server”
- o frază rostită apare scrisă, pașii apar pe monitor, răspunsul se aude în pagină
- teste: `cd site-live/voice && python3 -m unittest test_voice_service -v`

Până la instalare, pagina folosește recunoașterea vocală a browserului (aceeași rută în aplicație).
