"""Reparațiile apelului WhatsApp pe codul LIVE din /opt/kelion-pod (21.10.2026), aplicate exact și verificabil.

Codul live (kelion_pod.py și pod_locuri/ modificat de Kelion pe server) NU e suprascris: fiecare reparație
înlocuiește un text care trebuie găsit EXACT o dată; dacă un singur text nu se potrivește, nu se scrie nimic.

  python3 repara_pod.py SURSA DESTINATIE
      SURSA = directorul podului (/opt/kelion-pod); DESTINATIE = director nou unde se scriu copiile reparate.
      La final: compilare + proba de comportament pe codul reparat (apelul așteaptă locul care se pregătește).

Dovezi (pod.jsonl, 21.10.2026):
  A  19:36:24 apelul dot s-a închis după 2 s; la 19:36:31 reîncărcarea de recuperare a dat TimeoutError -> apel pierdut.
  B  «canal_dot_esuat channel_slot_not_ready» de 977 de ori (la 4 s); locul canalului (loc0) rămâne «defect» pentru totdeauna.
  C  «locuri_retry CalledProcessError» la 5 s, fără motiv.
  E  18:32:45 și 18:33:24: apeluri refuzate cu «fara_loc», «ocupate»: 0.
"""
import os
import py_compile
import shutil
import sys

R = {}

R["kelion_pod.py"] = [
    ("A4 apel activ: oricare buton vizibil",
     """            if count == 1 and await control.first.is_visible():
                return True""",
     """            for i in range(count):
                if await control.nth(i).is_visible():
                    return True"""),
    ("A1 recuperare fara reload cand pagina raspunde",
     """                        await self.reincarca_dot("recuperare in acelasi apel", page=pg, a=a, generation=generation)""",
     """                        if not await self.pagina_raspunde(pg):
                            await self.reincarca_dot("recuperare in acelasi apel", page=pg, a=a, generation=generation)
                        else:
                            jurnal(ev="dot_recuperare_fara_reload", id=a.id)"""),
    ("A2 reload 20 s",
     """'ui_reload', asyncio.wait_for(pg.reload(wait_until="domcontentloaded"), 8.0))""",
     """'ui_reload', asyncio.wait_for(pg.reload(wait_until="domcontentloaded"), 20.0))"""),
    ("A2 editor 10 s",
     """pg.locator('#prompt-textarea, div[contenteditable="true"]').first.wait_for(state="visible", timeout=4000))""",
     """pg.locator('#prompt-textarea, div[contenteditable="true"]').first.wait_for(state="visible", timeout=10000))"""),
    ("A3 captura la dot_watch_failure",
     """                reason = fault or "dot_ui_lost"
                self._dot_event(a, "dot_watch_failure", reason=reason)""",
     """                reason = fault or "dot_ui_lost"
                await self._captura_dot(a, reason)
                self._dot_event(a, "dot_watch_failure", reason=reason)"""),
    ("A3 captura la pierdere in pornire",
     """            if not await self._owned_dot_visible(a, generation):
                raise RuntimeError("dot_ui_lost")""",
     """            if not await self._owned_dot_visible(a, generation):
                await self._captura_dot(a, "dot_ui_lost_pornire")
                raise RuntimeError("dot_ui_lost")"""),
    ("A3 metoda _captura_dot",
     """    async def _close_owned_dot(self, a):""",
     """    async def _captura_dot(self, a, motiv):
        try:
            pg = a.dot_page
            if pg is None or pg.is_closed():
                return
            os.makedirs("/var/lib/kelion-pod/capturi", exist_ok=True)
            baza = "/var/lib/kelion-pod/capturi/" + time.strftime("%Y%m%d-%H%M%S") + "-" + motiv
            await asyncio.wait_for(pg.screenshot(path=baza + ".png"), 3.0)
            text = await asyncio.wait_for(pg.evaluate("document.body.innerText.slice(-2000)"), 2.0)
            butoane = await asyncio.wait_for(pg.evaluate(
                "[...document.querySelectorAll('button[aria-label]')].map(b => b.getAttribute('aria-label')).slice(0, 80)"), 2.0)
            with open(baza + ".txt", "w", encoding="utf-8") as h:
                h.write(text + "\\n\\n--- butoane ---\\n" + "\\n".join(butoane))
            jurnal(ev="captura_dot", fisier=baza, motiv=motiv)
        except Exception as e:
            jurnal(ev="captura_dot_esuata", motiv=type(e).__name__)

    async def _close_owned_dot(self, a):"""),
    ("B canal: motivul o singura data, reincercare la 30 s",
     """            try:
                await self.canal_scrie(cp, f)
            except Exception as e:
                jurnal(ev="canal_dot_esuat", motiv=f"{type(e).__name__}: {e}"[:200])""",
     """            try:
                await self.canal_scrie(cp, f)
                self._canal_eroare = None
            except Exception as e:
                motiv = f"{type(e).__name__}: {e}"[:200]
                if motiv != getattr(self, "_canal_eroare", None):
                    jurnal(ev="canal_dot_esuat", motiv=motiv, stare_loc_canal=self.channel_loc.stare)
                    self._canal_eroare = motiv
                await asyncio.sleep(30)"""),
    ("B locul canalului iese din «defect» (repornire cel mult o data pe minut)",
     """                    if loc.stare == OPRIT:
                        self.loc_executor.porneste(loc)
                        loc.stare = PORNIRE""",
     """                    if loc.stare == OPRIT or (loc.stare == "defect" and time.monotonic() - getattr(self, "_canal_repornit", 0.0) > 60):
                        self._canal_repornit = time.monotonic()
                        if loc.stare == "defect":
                            self.loc_executor.opreste(loc)
                        self.loc_executor.porneste(loc)
                        loc.stare = PORNIRE"""),
    ("C locuri_retry cu motivul complet, o singura data",
     """                jurnal(ev="locuri_retry", motiv=type(error).__name__)""",
     """                motiv = f"{type(error).__name__}: {error}"[:200]
                if motiv != getattr(self, "_locuri_eroare", None):
                    self._locuri_eroare = motiv
                    jurnal(ev="locuri_retry", motiv=motiv)"""),
]

R["pod_locuri/executor_server.py"] = [
    ("C eroarea pactl cu motivul exact",
     """            listed = subprocess.run(["pactl", "list", "short", kind], env=self._mediu(),
                                    capture_output=True, text=True, check=True, timeout=10)
            names = {x.split("\\t")[1] for x in listed.stdout.splitlines() if "\\t" in x}
            if wanted not in names:
                subprocess.run(comanda, env=self._mediu(), check=True, capture_output=True, timeout=10)""",
     """            listed = subprocess.run(["pactl", "list", "short", kind], env=self._mediu(),
                                    capture_output=True, text=True, timeout=10)
            if listed.returncode != 0:
                self._eroare_sunet(loc, "list " + kind, listed)
            names = {x.split("\\t")[1] for x in listed.stdout.splitlines() if "\\t" in x}
            if wanted not in names:
                r = subprocess.run(comanda, env=self._mediu(), capture_output=True, text=True, timeout=10)
                if r.returncode != 0:
                    self._eroare_sunet(loc, wanted, r)"""),
    ("C metoda _eroare_sunet",
     """    def porneste(self, loc, login=False):""",
     """    def _eroare_sunet(self, loc, ce, r):
        eroare = ((r.stderr or "") + (r.stdout or "")).strip()[:200]
        cheie = (loc.numar, ce, eroare)
        if getattr(self, "_ultima_eroare_sunet", None) != cheie:
            self._ultima_eroare_sunet = cheie
            self.jurnal({"ev": "sunet_loc_esuat", "loc": loc.numar, "ce": ce, "cod": r.returncode, "eroare": eroare})
        raise RuntimeError(f"sunet_loc_esuat {ce}: {eroare}")

    def porneste(self, loc, login=False):"""),
]

R["pod_locuri/resurse.py"] = [
    ("E timpul de asteptare a unui loc",
     """    "locuri_pregatite": 2,       # câte locuri libere stau gata de apel (pornire din prima)
}""",
     """    "locuri_pregatite": 2,       # câte locuri libere stau gata de apel (pornire din prima)
    "asteptare_loc_s": 15,       # un apel așteaptă locul care se pregătește, nu e refuzat
}"""),
]

R["pod_locuri/locuri.py"] = [
    ("E manager cu ceas de asteptare",
     """    def __init__(self, executor, config_cale=None, *, citeste_resurse=None, director_profile="/var/lib/kelion-pod"):
        self.executor = executor""",
     """    def __init__(self, executor, config_cale=None, *, citeste_resurse=None, director_profile="/var/lib/kelion-pod",
                 dormi=time.sleep):
        self.executor = executor
        self._dormi = dormi"""),
    ("E aloca asteapta locul care se pregateste",
     """    def aloca(self, apel_id):
        \"\"\"Primul loc pregătit; None doar când toate locurile posibile sunt ocupate (atunci: mesaj «ocupat» + alertă).\"\"\"
        with self.lock:
            for loc in self.locuri.values():
                if loc.apel == apel_id:
                    return loc
            cap = self.recalculeaza()
            if sum(l.stare == OCUPAT for l in self.locuri.values()) >= cap.maxim:
                self.executor.jurnal({"ev": "fara_loc", "apel": apel_id, "motiv": "capacitate"})
                if self._alerta_la is None or time.time() - self._alerta_la > 600:
                    self._alerta_la = time.time()
                    self.executor.alerta("Capacitatea efectiva de apel este epuizata; verificati resursele si limita configurata.")
                return None
            liber = next((l for l in sorted(self.locuri.values(), key=lambda l: l.numar) if l.stare == PREGATIT), None)
            if liber is None:
                self.sincronizeaza()
                liber = next((l for l in sorted(self.locuri.values(), key=lambda l: l.numar) if l.stare == PREGATIT), None)
            if liber is None:
                ocupate = sum(1 for l in self.locuri.values() if l.stare == OCUPAT)
                if ocupate >= (self.capacitate.maxim if self.capacitate else 1):
                    acum = time.time()
                    if self._alerta_la is None or acum - self._alerta_la > 600:
                        self._alerta_la = acum
                        self.executor.alerta(f"Serverul e la capacitate: {ocupate} apeluri simultane "
                                             f"(limita {self.capacitate.motiv}). Mareste planul Contabo; "
                                             "locurile noi pornesc singure.")
                self.executor.jurnal({"ev": "fara_loc", "apel": apel_id, "ocupate": ocupate})
                return None
            liber.apel = apel_id
            self._schimba(liber, OCUPAT)
            return liber""",
     """    def _primul_pregatit(self):
        return next((l for l in sorted(self.locuri.values(), key=lambda l: l.numar) if l.stare == PREGATIT), None)

    def aloca(self, apel_id, asteapta_s=None):
        \"\"\"Primul loc pregătit. Un loc care doar se pregătește (reîncărcare după apelul anterior) e AȘTEPTAT până la
        asteapta_s secunde, nu refuzat (21.10 18:32: «fara_loc» cu «ocupate»: 0). Refuz imediat doar la capacitate.\"\"\"
        if asteapta_s is None:
            asteapta_s = float(self.config.valori.get("asteptare_loc_s", 15))
        inceput = time.monotonic()
        termen = inceput + max(0.0, asteapta_s)
        sincronizat = False
        while True:
            with self.lock:
                for loc in self.locuri.values():
                    if loc.apel == apel_id:
                        return loc
                cap = self.recalculeaza()
                if sum(l.stare == OCUPAT for l in self.locuri.values()) >= cap.maxim:
                    self.executor.jurnal({"ev": "fara_loc", "apel": apel_id, "motiv": "capacitate"})
                    if self._alerta_la is None or time.time() - self._alerta_la > 600:
                        self._alerta_la = time.time()
                        self.executor.alerta("Capacitatea efectiva de apel este epuizata; verificati resursele si limita configurata.")
                    return None
                liber = self._primul_pregatit()
                if liber is None:
                    for loc in list(self.locuri.values()):   # un loc în pornire poate fi gata chiar acum
                        if loc.stare == PORNIRE and loc.apel is None:
                            self._verifica(loc)
                    liber = self._primul_pregatit()
                if liber is None and not sincronizat:
                    self.sincronizeaza()
                    sincronizat = True
                    liber = self._primul_pregatit()
                if liber is not None:
                    liber.apel = apel_id
                    self._schimba(liber, OCUPAT)
                    asteptat = round(time.monotonic() - inceput, 1)
                    if asteptat > 0.2:
                        self.executor.jurnal({"ev": "loc_dupa_asteptare", "apel": apel_id, "loc": liber.numar,
                                              "asteptat_s": asteptat})
                    return liber
                se_pregatesc = any(l.stare == PORNIRE and l.apel is None for l in self.locuri.values())
                if not se_pregatesc or time.monotonic() >= termen:
                    ocupate = sum(1 for l in self.locuri.values() if l.stare == OCUPAT)
                    self.executor.jurnal({"ev": "fara_loc", "apel": apel_id, "ocupate": ocupate,
                                          "stari": {str(l.numar): l.stare for l in self.locuri.values()},
                                          "asteptat_s": round(time.monotonic() - inceput, 1)})
                    return None
            self._dormi(0.5)"""),
]

MARCAJ = "async def _captura_dot"


def aplica(text, inlocuiri, fisier):
    for nume, vechi, nou in inlocuiri:
        n = text.count(vechi)
        if n != 1:
            raise SystemExit(f"OPRIT: {fisier}: «{nume}» găsit de {n} ori (trebuie exact 1). Nu s-a scris nimic.")
        text = text.replace(vechi, nou)
    return text


def proba_comportament(destinatie):
    """Pe codul REPARAT: locul 1 e în «pornire» (reîncărcare); apelul trebuie să-l aștepte, nu să fie refuzat."""
    sys.path.insert(0, destinatie)
    from pod_locuri.locuri import Manager, PORNIRE, PREGATIT, OCUPAT
    from pod_locuri.resurse import Capacitate

    class Ex:
        ev, raspunsuri = [], iter([PREGATIT, PORNIRE, PORNIRE, PORNIRE])
        def porneste(self, loc, login=False): pass
        def opreste(self, loc): pass
        def pregatit(self, loc): return next(self.raspunsuri, PREGATIT)
        def alerta(self, text): self.ev.append({"ev": "alerta"})
        def jurnal(self, e): self.ev.append(e)

    ex, dormit = Ex(), []
    m = Manager(ex, None, citeste_resurse=lambda cfg, a: Capacitate(12000, 9000, 6, 0.3, 1, 1, 1, "RAM"),
                dormi=dormit.append)
    m.sincronizeaza()
    m.locuri[1].stare = PORNIRE
    loc = m.aloca("apel-proba", asteapta_s=15)
    assert loc is not None and loc.stare == OCUPAT, "apelul a fost refuzat"
    assert dormit, "nu a așteptat"
    assert not any(e.get("ev") == "fara_loc" for e in ex.ev), "a apărut fara_loc"
    pasi = len(dormit)
    assert m.aloca("apel-2", asteapta_s=15) is None and len(dormit) == pasi, "la capacitate trebuie refuz imediat"
    return f"apelul a așteptat {pasi} pași și a primit locul {loc.numar}; la capacitate refuz imediat"


if __name__ == "__main__":
    sursa, destinatie = sys.argv[1], sys.argv[2]
    with open(os.path.join(sursa, "kelion_pod.py"), encoding="utf-8") as h:
        if MARCAJ in h.read():
            raise SystemExit("DEJA APLICAT: kelion_pod.py are deja reparațiile.")
    reparate = {}
    for fisier, inlocuiri in R.items():
        with open(os.path.join(sursa, fisier), encoding="utf-8") as h:
            reparate[fisier] = aplica(h.read(), inlocuiri, fisier)
    os.makedirs(destinatie, exist_ok=True)
    shutil.copytree(os.path.join(sursa, "pod_locuri"), os.path.join(destinatie, "pod_locuri"),
                    ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
    for fisier, text in reparate.items():
        cale = os.path.join(destinatie, fisier)
        with open(cale, "w", encoding="utf-8") as h:
            h.write(text)
        py_compile.compile(cale, doraise=True)
    total = sum(len(v) for v in R.values())
    print(f"OK: {total} reparații în {len(R)} fișiere, compilare reușită.")
    print("OK proba:", proba_comportament(destinatie))
