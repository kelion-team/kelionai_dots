"""Pasul 2 (21.10.2026): locurile de apel nelogate în ChatGPT sunt recunoscute și ies singure din modul de logare.

Dovezi (server, 20:20): profilul locului 1 are sesiunea ChatGPT; loc2 și loc0 (canalul) NU au. loc2 stătea la
nesfârșit în «pornire» (nicio alertă), iar după logare nimic nu crea fișierul «login-complete» cerut de cod.
Alerta trimitea la kelionai.app/app/pod-ecran, adresă care dă 404.

  python3 repara_logare_locuri.py SURSA DESTINATIE   (SURSA = /opt/kelion-pod; scrie copii reparate în DESTINATIE)
Fiecare text trebuie găsit EXACT o dată; altfel nu se scrie nimic. Valoarea cookie-urilor nu se citește niciodată.
"""
import os
import py_compile
import shutil
import sys

VNC = ("https://kelionai.app/app/pod-ecran/vnc.html?autoconnect=1&resize=scale"
       "&path=app/pod-ecran/websockify")

R = {
    "pod_locuri/executor_server.py": [
        ("loc nelogat recunoscut pe pagina dot",
         """        if any("/auth/" in u or "/login" in u for u in urls):
            return LOGIN_NECESAR""",
         """        if any("/auth/" in u or "/login" in u for u in urls) or not self._are_sesiune(loc):
            return LOGIN_NECESAR"""),
        ("logare terminata: marcaj SAU sesiune stabila 20 s",
         """            marker = Path(loc.profil) / "login-complete"
            if marker.exists():
                marker.unlink()""",
         """            marker = Path(loc.profil) / "login-complete"
            if marker.exists() or self._sesiune_stabila(loc):
                marker.unlink(missing_ok=True)"""),
        ("metodele de sesiune",
         """    def opreste(self, loc):""",
         """    def _are_sesiune(self, loc):
        \"\"\"Profilul are cookie-ul de sesiune ChatGPT? Doar NUMELE cookie-ului, citit read-only; valoarea nu.\"\"\"
        import sqlite3
        for cale in (Path(loc.profil) / "Default" / "Network" / "Cookies", Path(loc.profil) / "Default" / "Cookies"):
            if not cale.exists():
                continue
            try:
                con = sqlite3.connect(f"file:{cale}?mode=ro&immutable=1", uri=True, timeout=2)
                try:
                    return con.execute("SELECT 1 FROM cookies WHERE host_key LIKE '%chatgpt.com' AND "
                                       "name LIKE '__Secure-next-auth.session-token%' LIMIT 1").fetchone() is not None
                finally:
                    con.close()
            except sqlite3.Error:
                return True   # baza necitibilă: nu scoatem din uz un loc posibil logat
        return False

    def _sesiune_stabila(self, loc, liniste_s=20):
        vazut = self.__dict__.setdefault("_sesiune_vazuta", {})
        if not self._are_sesiune(loc):
            vazut.pop(loc.numar, None)
            return False
        return time.monotonic() - vazut.setdefault(loc.numar, time.monotonic()) >= liniste_s

    def opreste(self, loc):"""),
    ],
    "pod_locuri/resurse.py": [
        ("capacitatea nu coboara la 0 la un varf de incarcare (20:21:15: maxim 0, motiv CPU, cu un apel in curs)",
         """    maxim = max(0, min(maxim_ram, maxim_cpu, int(cfg["locuri_maxim_absolut"])))""",
         """    maxim = max(min(1, int(cfg["locuri_maxim_absolut"])), min(maxim_ram, maxim_cpu, int(cfg["locuri_maxim_absolut"])))"""),
    ],
    "pod_locuri/locuri.py": [
        ("adresa corecta a ecranului in alerta",
         """intra pe kelionai.app/app/pod-ecran si logheaza-te in fereastra deschisa.\"""",
         f"""intra pe {VNC} si logheaza-te in fereastra deschisa.\""""),
    ],
}
MARCAJ = "def _are_sesiune"


def aplica(text, inlocuiri, fisier):
    for nume, vechi, nou in inlocuiri:
        n = text.count(vechi)
        if n != 1:
            raise SystemExit(f"OPRIT: {fisier}: «{nume}» găsit de {n} ori (trebuie exact 1). Nu s-a scris nimic.")
        text = text.replace(vechi, nou)
    return text


def proba(destinatie):
    """Pe codul reparat: profil fără sesiune -> login_necesar; după logare (sesiune 20 s) -> repornit în mod pod."""
    import sqlite3
    import tempfile
    import time as t
    sys.path.insert(0, destinatie)
    from pod_locuri.executor_server import ExecutorServer
    from pod_locuri.locuri import descrie_loc
    with tempfile.TemporaryDirectory() as d:
        ex = ExecutorServer(jurnal_cale=os.path.join(d, "j"), alerte_cale=os.path.join(d, "a"))
        loc = descrie_loc(7, director_profile=d)
        os.makedirs(os.path.join(loc.profil, "Default", "Network"))
        db = os.path.join(loc.profil, "Default", "Network", "Cookies")
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, value TEXT)")
        con.execute("INSERT INTO cookies VALUES ('.chatgpt.com', 'oai-did', '')")
        con.commit()
        assert ex._are_sesiune(loc) is False, "profil nelogat văzut ca logat"
        con.execute("INSERT INTO cookies VALUES ('.chatgpt.com', '__Secure-next-auth.session-token', '')")
        con.commit()
        con.close()
        assert ex._are_sesiune(loc) is True, "sesiunea nu e văzută"
        assert ex._sesiune_stabila(loc) is False, "logarea nu trebuie încheiată imediat"
        ex._sesiune_vazuta[loc.numar] -= 30
        assert ex._sesiune_stabila(loc) is True, "după 20 s de sesiune, logarea e încheiată"
    from pod_locuri.resurse import calculeaza, CONFIG_IMPLICIT
    cap = calculeaza(dict(CONFIG_IMPLICIT), meminfo={"MemTotal": 11960, "MemAvailable": 8141}, nuclee=6,
                     incarcare=4.87, cgroup_mb=None, locuri_active=2)
    assert cap.maxim >= 1, f"vârful de încărcare de la 20:21 dă încă maxim {cap.maxim}"
    return (f"profil nelogat -> login_necesar; după logare + 20 s -> revine singur în mod pod; "
            f"la încărcarea 4.87 de la 20:21 capacitatea e {cap.maxim} (înainte 0)")


if __name__ == "__main__":
    sursa, destinatie = sys.argv[1], sys.argv[2]
    with open(os.path.join(sursa, "pod_locuri/executor_server.py"), encoding="utf-8") as h:
        if MARCAJ in h.read():
            raise SystemExit("DEJA APLICAT.")
    reparate = {}
    for fisier, inlocuiri in R.items():
        with open(os.path.join(sursa, fisier), encoding="utf-8") as h:
            reparate[fisier] = aplica(h.read(), inlocuiri, fisier)
    shutil.copytree(os.path.join(sursa, "pod_locuri"), os.path.join(destinatie, "pod_locuri"),
                    ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
    for fisier, text in reparate.items():
        cale = os.path.join(destinatie, fisier)
        with open(cale, "w", encoding="utf-8") as h:
            h.write(text)
        py_compile.compile(cale, doraise=True)
    print(f"OK: {sum(len(v) for v in R.values())} reparații, compilare reușită.")
    print("OK proba:", proba(destinatie))
