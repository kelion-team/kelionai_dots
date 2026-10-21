"""Executorul real de pe vmi3583512: pornește/oprește sunetul și Chrome-ul fiecărui loc și verifică pagina dot.

Rulează ca user brain, în același mediu ca kelion-pod-ecran (DISPLAY :77, PulseAudio din /run/kelion-pod).
Nu atinge locul 1 (îl gestionează kelion-pod-ecran.sh, ca azi).
"""
import json
import os
import subprocess
import time
import urllib.request

from .locuri import LOGIN_NECESAR, PREGATIT, PORNIRE, DEFECT, comenzi_sunet, comanda_chrome

MEDIU = {"DISPLAY": ":77", "XDG_RUNTIME_DIR": "/run/kelion-pod",
         "PULSE_SERVER": "unix:/run/kelion-pod/pulse/native"}


class ExecutorServer:
    def __init__(self, jurnal_cale="/var/lib/kelion-pod/pod.jsonl", alerte_cale="/var/lib/kelion-pod/alerte.jsonl",
                 alerta_cmd=None):
        self.jurnal_cale, self.alerte_cale = jurnal_cale, alerte_cale
        self.alerta_cmd = alerta_cmd or os.environ.get("KELION_POD_ALERTA_CMD")   # ex. kelion-noutate / trimitere WhatsApp
        self.procese = {}

    def _mediu(self, extra=None):
        env = dict(os.environ)
        env.update(MEDIU)
        env.update(extra or {})
        return env

    def _sinks(self):
        r = subprocess.run(["pactl", "list", "short", "sinks"], env=self._mediu(), capture_output=True, text=True, timeout=10)
        return {linie.split("\t")[1] for linie in r.stdout.splitlines() if "\t" in linie}

    def porneste(self, loc, login=False):
        if loc.numar == 1:
            return
        if loc.wa_in not in self._sinks():
            for comanda in comenzi_sunet(loc):
                subprocess.run(comanda, env=self._mediu(), check=True, capture_output=True, timeout=10)
        os.makedirs(loc.profil, exist_ok=True)
        env, args = comanda_chrome(loc, login=login)
        self.procese[loc.numar] = subprocess.Popen(args, env=self._mediu(env), stdout=subprocess.DEVNULL,
                                                   stderr=subprocess.DEVNULL, start_new_session=True)

    def opreste(self, loc):
        if loc.numar == 1:
            return
        proc = self.procese.pop(loc.numar, None)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
        r = subprocess.run(["pactl", "list", "short", "modules"], env=self._mediu(), capture_output=True, text=True, timeout=10)
        for linie in r.stdout.splitlines():
            if any(f"={nume}" in linie for nume in (loc.wa_in, loc.chrome_out, loc.mic)):
                subprocess.run(["pactl", "unload-module", linie.split("\t")[0]], env=self._mediu(), capture_output=True, timeout=10)

    def pregatit(self, loc):
        proc = self.procese.get(loc.numar)
        if loc.numar != 1 and (proc is None or proc.poll() is not None):
            return DEFECT
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{loc.port_cdp}/json", timeout=3) as r:
                pagini = json.load(r)
        except (OSError, ValueError):
            # În modul login Chrome nu are CDP: cât timp rulează, așteaptă logarea lui Adrian.
            return LOGIN_NECESAR if proc is not None and proc.poll() is None and loc.numar != 1 else PORNIRE
        urls = [p.get("url", "") for p in pagini if p.get("type") == "page"]
        if any("/auth/" in u or "/login" in u for u in urls):
            return LOGIN_NECESAR
        if any(u.startswith("https://chatgpt.com/dots") for u in urls):
            return PREGATIT
        return PORNIRE

    def alerta(self, text):
        self.jurnal({"ev": "alerta", "text": text}, cale=self.alerte_cale)
        if self.alerta_cmd:
            subprocess.run([self.alerta_cmd, text], capture_output=True, timeout=30)

    def jurnal(self, eveniment, cale=None):
        try:
            with open(cale or self.jurnal_cale, "a", encoding="utf-8") as h:
                h.write(json.dumps({"t": round(time.time(), 3), "ora": time.strftime("%H:%M:%S"), **eveniment},
                                   ensure_ascii=False) + "\n")
        except OSError:
            pass
