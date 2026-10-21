"""Câte apeluri WhatsApp simultane duce serverul ACUM — calculat din resursele reale, recitit periodic.

Fără număr fix: când Adrian mărește serverul (RAM / nuclee) sau schimbă fișierul de configurare,
maximul crește singur, fără restart și fără modificare de cod.
"""
import json
import os
from dataclasses import dataclass, asdict

CONFIG_IMPLICIT = {
    "ram_pe_loc_mb": 650,        # un Chrome cu dot în apel + sunetul (măsurat ~400–600 MB); se ajustează din proba reală
    "cpu_pe_loc": 0.15,          # fracțiune dintr-un nucleu pe apel (aiortc + Chrome audio)
    "rezerva_ram_procent": 20,   # RAM păstrat liber pentru restul serverului
    "rezerva_cpu_procent": 25,
    "locuri_maxim_absolut": 64,  # plafon de siguranță, nu limită de business
    "locuri_pregatite": 2,       # câte locuri libere stau gata de apel (pornire din prima)
    "asteptare_loc_s": 15,       # un apel așteaptă un loc care se pregătește (reîncărcare după apelul anterior), nu e refuzat
}


@dataclass
class Capacitate:
    ram_total_mb: int
    ram_disponibil_mb: int
    nuclee: int
    incarcare_1m: float
    maxim_ram: int
    maxim_cpu: int
    maxim: int
    motiv: str

    def ca_dict(self):
        return asdict(self)


def citeste_meminfo(cale="/proc/meminfo"):
    valori = {}
    with open(cale) as h:
        for linie in h:
            cheie, _, rest = linie.partition(":")
            parti = rest.split()
            if parti and parti[0].isdigit():
                valori[cheie] = int(parti[0]) // 1024   # kB -> MB
    return valori


def limita_cgroup_mb(cale="/sys/fs/cgroup/memory.max"):
    try:
        text = open(cale).read().strip()
        return None if text == "max" else int(text) // (1024 * 1024)
    except (OSError, ValueError):
        return None


def cgroup_folosit_mb(cale="/sys/fs/cgroup/memory.current"):
    try:
        return int(open(cale).read().strip()) // (1024 * 1024)
    except (OSError, ValueError):
        return None


def nuclee_disponibile():
    try:
        return len(os.sched_getaffinity(0))
    except AttributeError:   # pragma: no cover - doar pe sisteme fără sched_getaffinity
        return os.cpu_count() or 1


class Config:
    """Fișierul de configurare se recitește singur când se schimbă (după mtime)."""

    def __init__(self, cale=None):
        self.cale = cale
        self._mtime = None
        self.valori = dict(CONFIG_IMPLICIT)

    def actualizeaza(self):
        """Întoarce True dacă s-a încărcat o configurație nouă."""
        if not self.cale:
            return False
        try:
            mtime = os.stat(self.cale).st_mtime_ns
        except OSError:
            return False
        if mtime == self._mtime:
            return False
        try:
            with open(self.cale) as h:
                nou = json.load(h)
        except (OSError, ValueError):
            return False       # o configurație stricată nu înlocuiește una bună
        if not isinstance(nou, dict):
            return False
        valori = dict(CONFIG_IMPLICIT)
        for cheie, implicit in CONFIG_IMPLICIT.items():
            v = nou.get(cheie, implicit)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
                valori[cheie] = type(implicit)(v)
        self.valori, self._mtime = valori, mtime
        return True


def calculeaza(cfg, *, meminfo=None, nuclee=None, incarcare=None, cgroup_mb=None, locuri_active=0):
    """Maximul de locuri = câte încap în RAM și CPU, după rezervă. Locurile deja active se socotesc incluse."""
    meminfo = meminfo if meminfo is not None else citeste_meminfo()
    nuclee = nuclee if nuclee is not None else nuclee_disponibile()
    incarcare = incarcare if incarcare is not None else os.getloadavg()[0]
    cgroup_mb = cgroup_mb if cgroup_mb is not None else limita_cgroup_mb()

    total = meminfo.get("MemTotal", 0)
    disponibil = meminfo.get("MemAvailable", 0)
    if cgroup_mb:
        # Sub o limită cgroup, liberul real e limita minus ce folosește deja grupul, nu memoria întregii mașini.
        total = min(total, cgroup_mb)
        folosit_cgroup = cgroup_folosit_mb()
        if folosit_cgroup is not None:
            disponibil = min(disponibil, max(0, cgroup_mb - folosit_cgroup))
        disponibil = min(disponibil, total)
    ram_loc = max(1, cfg["ram_pe_loc_mb"])
    rezerva_ram = total * cfg["rezerva_ram_procent"] / 100
    # RAM-ul locurilor deja pornite e deja consumat din «disponibil»: îl adunăm înapoi.
    ram_pentru_locuri = disponibil + locuri_active * ram_loc - rezerva_ram
    # Niciodată peste ce încape în totalul permis, după rezervă (și cu locurile active adunate înapoi).
    ram_pentru_locuri = min(ram_pentru_locuri, total - rezerva_ram)
    maxim_ram = max(0, int(ram_pentru_locuri // ram_loc))

    cpu_loc = max(0.01, cfg["cpu_pe_loc"])
    cpu_liber = nuclee * (1 - cfg["rezerva_cpu_procent"] / 100) - max(0.0, incarcare - locuri_active * cpu_loc)
    maxim_cpu = max(0, int(cpu_liber // cpu_loc))

    maxim = max(1, min(maxim_ram, maxim_cpu, int(cfg["locuri_maxim_absolut"])))
    motiv = "RAM" if maxim_ram <= maxim_cpu else "CPU"
    if maxim == int(cfg["locuri_maxim_absolut"]):
        motiv = "plafon de siguranta"
    return Capacitate(total, disponibil, nuclee, round(incarcare, 2), maxim_ram, maxim_cpu, maxim, motiv)
