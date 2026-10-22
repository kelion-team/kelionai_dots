"""Locurile de apel: fiecare apel WhatsApp are Chrome-ul lui, pagina dot a lui și sunetul lui separat.

Un loc = (profil Chrome propriu, port CDP propriu, pereche PulseAudio proprie):
  wa_in_N     -> ce spune apelantul (podul scrie aici)
  mic_wa_N    -> microfonul Chrome-ului N (remap din wa_in_N.monitor)
  chrome_out_N-> ce spune Kelion în Chrome-ul N (podul citește din chrome_out_N.monitor)
Chrome N pornește cu PULSE_SINK=chrome_out_N și PULSE_SOURCE=mic_wa_N, deci sunetul nu se amestecă între apeluri.
Locul 1 păstrează numele de azi (wa_in, chrome_out, mic_wa, CDP 9277, profilul chrome) ca să nu strice podul existent.

Toate canalele au prioritate egală: un apel nou primește primul loc liber; nu se scrie niciodată în pagina altui loc.
Managerul nu execută nimic singur: primește un «executor» (comenzi reale pe server, simulate în teste).
"""
import threading
import time
from dataclasses import dataclass, field

from .resurse import Config, calculeaza

OPRIT, PORNIRE, LOGIN_NECESAR, PREGATIT, OCUPAT, DEFECT = (
    "oprit", "pornire", "login_necesar", "pregatit", "ocupat", "defect")

CHROME_FLAGS = [
    "--no-first-run", "--no-default-browser-check", "--password-store=basic",
    "--use-fake-ui-for-media-stream", "--autoplay-policy=no-user-gesture-required",
    "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--disable-features=CalculateNativeWinOcclusion,IntensiveWakeUpThrottling",
    "--remote-debugging-address=127.0.0.1",
]
LOGIN_FLAGS = ["--no-first-run", "--no-default-browser-check", "--password-store=basic"]
DOTS_URL = "https://chatgpt.com/dots/home"
LOGIN_URL = "https://chatgpt.com/auth/login"


def valideaza_apel_id(apel_id):
    if not isinstance(apel_id, str) or not apel_id.strip():
        raise ValueError("apel_id trebuie sa fie un identificator text nevid")


@dataclass
class Loc:
    numar: int
    profil: str
    port_cdp: int
    wa_in: str
    chrome_out: str
    mic: str
    stare: str = OPRIT
    apel: str = None
    schimbat: float = field(default_factory=time.time)

    def ca_dict(self):
        return {"numar": self.numar, "stare": self.stare, "apel": self.apel, "port_cdp": self.port_cdp,
                "profil": self.profil, "sunet": {"wa_in": self.wa_in, "chrome_out": self.chrome_out, "mic": self.mic}}


def descrie_loc(numar, *, director_profile="/var/lib/kelion-pod", port_baza=9277):
    if numar == 1:
        return Loc(1, f"{director_profile}/chrome", port_baza, "wa_in", "chrome_out", "mic_wa")
    # Locurile noi stau departe de porturile/profilele folosite azi (9278/chrome2 = invitați).
    return Loc(numar, f"{director_profile}/loc{numar}", port_baza + 100 + numar,
               f"wa_in_{numar}", f"chrome_out_{numar}", f"mic_wa_{numar}")


def comenzi_sunet(loc):
    """Perechea PulseAudio a locului (idempotent: «pactl list» decide în executor dacă există deja)."""
    if loc.numar == 1:
        return []   # locul 1 e creat de kelion-pod-ecran.sh, ca azi
    return [
        ["pactl", "load-module", "module-null-sink", f"sink_name={loc.wa_in}", "rate=48000", "channels=1",
         f"sink_properties=device.description=WhatsApp_in_{loc.numar}"],
        ["pactl", "load-module", "module-null-sink", f"sink_name={loc.chrome_out}", "rate=48000", "channels=1",
         f"sink_properties=device.description=Chrome_out_{loc.numar}"],
        ["pactl", "load-module", "module-remap-source", f"master={loc.wa_in}.monitor", f"source_name={loc.mic}",
         f"source_properties=device.description=Microfon_WhatsApp_{loc.numar}"],
    ]


def comanda_chrome(loc, *, login=False):
    """Mediul și argumentele Chrome-ului locului. În modul login: Chrome curat, fără automatizare,
    deschis pe pagina de logare, ca Adrian să se logheze el (fără copiere de sesiuni sau cookie-uri)."""
    env = {"PULSE_SINK": loc.chrome_out, "PULSE_SOURCE": loc.mic, "PULSE_LATENCY_MSEC": "90"}
    if login:
        return env, ["google-chrome", f"--user-data-dir={loc.profil}", *LOGIN_FLAGS,
                     "--window-size=1000,700", LOGIN_URL]
    return env, ["google-chrome", f"--user-data-dir={loc.profil}", *CHROME_FLAGS,
                 f"--remote-debugging-port={loc.port_cdp}", "--window-size=1000,700", DOTS_URL]


class Manager:
    """executor trebuie să ofere:
         porneste(loc, login: bool) -> None      (sunet + Chrome pentru loc)
         opreste(loc) -> None
         pregatit(loc) -> "pregatit" | "login_necesar" | "pornire" | "defect"   (verifică pagina dot prin CDP)
         alerta(text) -> None                    (WhatsApp către Adrian)
         jurnal(eveniment: dict) -> None
    """

    def __init__(self, executor, config_cale=None, *, citeste_resurse=None, director_profile="/var/lib/kelion-pod",
                 dormi=time.sleep):
        self.executor = executor
        self._dormi = dormi
        self.config = Config(config_cale)
        self.config.actualizeaza()
        self.citeste_resurse = citeste_resurse or (lambda cfg, active: calculeaza(cfg, locuri_active=active))
        self.director_profile = director_profile
        self.locuri = {}
        self.capacitate = None
        self.lock = threading.RLock()
        self._alerta_la = None
        self._anulate = set()
        self._alocari = {}  # cereri în curs per apel; anularea le acoperă pe toate

    # ------------------------------------------------------------ capacitate
    def _active(self):
        return sum(1 for l in self.locuri.values() if l.stare != OPRIT)

    def recalculeaza(self):
        config_noua = self.config.actualizeaza()
        vechi = self.capacitate.maxim if self.capacitate else None
        self.capacitate = self.citeste_resurse(self.config.valori, self._active())
        if vechi is not None and (self.capacitate.maxim != vechi or config_noua):
            self.executor.jurnal({"ev": "capacitate_noua", "de_la": vechi, "la": self.capacitate.maxim,
                                  "configurare_noua": config_noua, **self.capacitate.ca_dict()})
        return self.capacitate

    # ------------------------------------------------------------ ciclul periodic (la ~60 s și după fiecare apel)
    def sincronizeaza(self):
        with self.lock:
            cap = self.recalculeaza()
            for loc in list(self.locuri.values()):
                if loc.stare in (PORNIRE, LOGIN_NECESAR, DEFECT):
                    self._verifica(loc)
            ocupate = sum(1 for l in self.locuri.values() if l.stare == OCUPAT)
            gata = sum(1 for l in self.locuri.values() if l.stare in (PREGATIT, PORNIRE))
            dorite = min(cap.maxim, ocupate + int(self.config.valori["locuri_pregatite"]))
            numar = 1
            while self._active() < dorite and gata < self.config.valori["locuri_pregatite"]:
                while numar in self.locuri and self.locuri[numar].stare != OPRIT:
                    numar += 1
                self._porneste(numar)
                gata += 1
            # Locurile libere în plus (peste rezervă și peste maxim) se opresc; cele ocupate nu se ating niciodată.
            libere = sorted((l for l in self.locuri.values() if l.stare == PREGATIT), key=lambda l: -l.numar)
            de_oprit = max(0, gata - int(self.config.valori["locuri_pregatite"]), self._active() - cap.maxim)
            for loc in libere[:de_oprit]:
                if loc.numar == 1:
                    continue
                self.executor.opreste(loc)
                self._schimba(loc, OPRIT)
            return self.stare()

    def _porneste(self, numar):
        loc = self.locuri.get(numar) or descrie_loc(numar, director_profile=self.director_profile)
        self.locuri[numar] = loc
        self.executor.porneste(loc, login=False)
        self._schimba(loc, PORNIRE)
        self._verifica(loc)

    def _verifica(self, loc):
        rezultat = self.executor.pregatit(loc)
        if rezultat == LOGIN_NECESAR and loc.stare != LOGIN_NECESAR:
            # Profil nou, nelogat: repornit în modul login și Adrian e anunțat o singură dată.
            self.executor.opreste(loc)
            self.executor.porneste(loc, login=True)
            self.executor.alerta(f"Locul de apel {loc.numar} are nevoie de logarea ta in ChatGPT: "
                                 "intra pe kelionai.app/app/pod-ecran si logheaza-te in fereastra deschisa.")
        if rezultat in (PREGATIT, LOGIN_NECESAR, DEFECT, PORNIRE):
            self._schimba(loc, rezultat)

    def _schimba(self, loc, stare):
        if loc.stare != stare:
            vechi, loc.stare, loc.schimbat = loc.stare, stare, time.time()
            self.executor.jurnal({"ev": "loc_stare", "loc": loc.numar, "de_la": vechi, "la": stare, "apel": loc.apel})

    # ------------------------------------------------------------ apeluri
    def _primul_pregatit(self):
        return next((l for l in sorted(self.locuri.values(), key=lambda l: l.numar) if l.stare == PREGATIT), None)

    def aloca(self, apel_id, asteapta_s=None):
        """Primul loc pregătit. Dacă un loc doar se pregătește (ex. reîncărcare după apelul anterior), apelul AȘTEAPTĂ
        până la asteapta_s secunde în loc să fie refuzat. None doar când toate locurile posibile sunt ocupate
        sau nimic nu s-a pregătit în timp (atunci: «ocupat» + alertă)."""
        valideaza_apel_id(apel_id)
        with self.lock:
            self._alocari[apel_id] = self._alocari.get(apel_id, 0) + 1
        try:
            return self._aloca(apel_id, asteapta_s)
        finally:
            with self.lock:
                self._alocari[apel_id] -= 1
                if not self._alocari[apel_id]:
                    del self._alocari[apel_id]
                    self._anulate.discard(apel_id)

    def _aloca(self, apel_id, asteapta_s):
        with self.lock:
            self.config.actualizeaza()               # o configurare schimbată chiar acum se vede la acest apel
        if asteapta_s is None:
            asteapta_s = float(self.config.valori.get("asteptare_loc_s", 15))
        termen = time.monotonic() + max(0.0, asteapta_s)
        inceput = time.monotonic()
        sincronizat = False
        while True:
            with self.lock:
                if apel_id in self._anulate:         # apelul s-a terminat cât aștepta: nu mai ocupă niciun loc
                    self.executor.jurnal({"ev": "alocare_anulata", "apel": apel_id})
                    return None
                for loc in self.locuri.values():
                    if loc.apel == apel_id:
                        return loc
                liber = self._primul_pregatit()
                if liber is None and time.monotonic() < termen:
                    for loc in list(self.locuri.values()):   # un loc în pornire poate fi gata chiar acum
                        if loc.stare == PORNIRE and time.monotonic() < termen:
                            self._verifica(loc)
                    liber = self._primul_pregatit()
                if liber is None and not sincronizat:
                    self.sincronizeaza()
                    sincronizat = True
                    liber = self._primul_pregatit()
                if liber is not None:
                    liber.apel = apel_id
                    self._schimba(liber, OCUPAT)
                    if time.monotonic() - inceput > 0.2:
                        self.executor.jurnal({"ev": "loc_dupa_asteptare", "apel": apel_id, "loc": liber.numar,
                                              "asteptat_s": round(time.monotonic() - inceput, 1)})
                    return liber
                se_pregatesc = any(l.stare == PORNIRE for l in self.locuri.values())
                if not se_pregatesc or time.monotonic() >= termen:
                    ocupate = sum(1 for l in self.locuri.values() if l.stare == OCUPAT)
                    if ocupate >= (self.capacitate.maxim if self.capacitate else 1):
                        acum = time.time()
                        if self._alerta_la is None or acum - self._alerta_la > 600:
                            self._alerta_la = acum
                            self.executor.alerta(f"Serverul e la capacitate: {ocupate} apeluri simultane "
                                                 f"(limita {self.capacitate.motiv}). Mareste planul Contabo; "
                                                 "locurile noi pornesc singure.")
                    self.executor.jurnal({"ev": "fara_loc", "apel": apel_id, "ocupate": ocupate,
                                          "stari": {str(l.numar): l.stare for l in self.locuri.values()},
                                          "asteptat_s": round(time.monotonic() - inceput, 1)})
                    return None
            self._dormi(0.5)

    def elibereaza(self, apel_id):
        valideaza_apel_id(apel_id)
        with self.lock:
            if apel_id in self._alocari:
                self._anulate.add(apel_id)
            for loc in self.locuri.values():
                if loc.apel == apel_id:
                    loc.apel = None
                    self._schimba(loc, PORNIRE)   # pagina se reîmprospătează, apoi redevine «pregatit»
                    self._verifica(loc)
                    return loc
            return None

    def stare(self):
        return {"capacitate": self.capacitate.ca_dict() if self.capacitate else None,
                "locuri": [l.ca_dict() for l in sorted(self.locuri.values(), key=lambda l: l.numar)]}
