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
        self.login = {}   # numar loc -> (mtime cookie la pornirea modului login, ultima schimbare văzută, cand)

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
        if login:
            self.login[loc.numar] = [self._cookie_mtime(loc), None, time.time()]
        else:
            self.login.pop(loc.numar, None)
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

    @staticmethod
    def _cookie_mtime(loc):
        for cale in (os.path.join(loc.profil, "Default", "Network", "Cookies"), os.path.join(loc.profil, "Default", "Cookies")):
            try:
                return os.stat(cale).st_mtime
            except OSError:
                continue
        return None

    def logare_terminata(self, loc, liniste_s=20):
        """În modul login nu există CDP: logarea lui Adrian se vede din cookie-urile profilului.
        Când s-au schimbat față de pornire și apoi au stat neschimbate liniste_s secunde, logarea e gata."""
        stare = self.login.get(loc.numar)
        if not stare:
            return False
        actual = self._cookie_mtime(loc)
        if actual is None or actual == stare[0]:
            return False
        if actual != stare[1]:
            stare[1], stare[2] = actual, time.time()
            return False
        return time.time() - stare[2] >= liniste_s

    def pregatit(self, loc):
        proc = self.procese.get(loc.numar)
        if loc.numar != 1 and (proc is None or proc.poll() is not None):
            return DEFECT
        if loc.numar in self.login:
            if not self.logare_terminata(loc):
                return LOGIN_NECESAR
            # Logarea e gata: Chrome repornește în modul pod (cu CDP), apoi se verifică pagina dot.
            self.opreste(loc)
            self.porneste(loc, login=False)
            self.jurnal({"ev": "loc_logat", "loc": loc.numar})
            return PORNIRE
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
