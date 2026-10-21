"""Executorul real de pe vmi3583512: pornește/oprește sunetul și Chrome-ul fiecărui loc și verifică pagina dot.

Rulează ca user brain, în același mediu ca kelion-pod-ecran (DISPLAY :77, PulseAudio din /run/kelion-pod).
Nu atinge locul 1 (îl gestionează kelion-pod-ecran.sh, ca azi).
"""
import json
import os
import sqlite3
import subprocess
import time
import urllib.request

from .locuri import LOGIN_NECESAR, PREGATIT, PORNIRE, DEFECT, comenzi_sunet, comanda_chrome

MEDIU = {"DISPLAY": ":77", "XDG_RUNTIME_DIR": "/run/kelion-pod",
         "PULSE_SERVER": "unix:/run/kelion-pod/pulse/native"}


def module_ale_locului(lista_module, loc):
    """Indexurile modulelor PulseAudio ale ACESTUI loc. Potrivire exactă pe argument
    (sink_name=wa_in_2 nu se potrivește cu wa_in_20), ca oprirea unui loc să nu atingă alt apel."""
    ale_lui = {f"sink_name={loc.wa_in}", f"sink_name={loc.chrome_out}", f"source_name={loc.mic}",
               f"master={loc.wa_in}.monitor"}
    indexuri = []
    for linie in lista_module.splitlines():
        campuri = linie.split("\t")
        if len(campuri) >= 3 and ale_lui & set(campuri[2].split()):
            indexuri.append(campuri[0])
    return indexuri


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
        for index in module_ale_locului(r.stdout, loc):
            subprocess.run(["pactl", "unload-module", index], env=self._mediu(), capture_output=True, timeout=10)

    @staticmethod
    def _cookie_mtime(loc):
        for cale in (os.path.join(loc.profil, "Default", "Network", "Cookies"), os.path.join(loc.profil, "Default", "Cookies")):
            try:
                return os.stat(cale).st_mtime
            except OSError:
                continue
        return None

    @staticmethod
    def _cale_cookies(loc):
        for cale in (os.path.join(loc.profil, "Default", "Network", "Cookies"), os.path.join(loc.profil, "Default", "Cookies")):
            if os.path.exists(cale):
                return cale
        return None

    def sesiune_chatgpt(self, loc):
        """True doar dacă profilul are cookie-ul de sesiune autentificată ChatGPT (numele e în clar; valoarea nu se citește)."""
        cale = self._cale_cookies(loc)
        if not cale:
            return False
        try:
            # Copie read-only prin URI, ca să nu blocăm baza pe care Chrome o scrie.
            con = sqlite3.connect(f"file:{cale}?mode=ro&immutable=1", uri=True, timeout=2)
            try:
                rand = con.execute(
                    "SELECT 1 FROM cookies WHERE host_key LIKE '%chatgpt.com' "
                    "AND name LIKE '__Secure-next-auth.session-token%' LIMIT 1").fetchone()
            finally:
                con.close()
            return rand is not None
        except sqlite3.Error:
            return False

    def logare_terminata(self, loc, liniste_s=20):
        """În modul login nu există CDP. Logarea e gata doar când profilul are cookie-ul de SESIUNE ChatGPT
        și cookie-urile au stat neschimbate liniste_s secunde (MFA / pași în curs nu sunt întrerupți).
        Simpla scriere a altor cookie-uri nu contează ca logare."""
        stare = self.login.get(loc.numar)
        if not stare:
            return False
        actual = self._cookie_mtime(loc)
        if actual is None or actual == stare[0] or not self.sesiune_chatgpt(loc):
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
