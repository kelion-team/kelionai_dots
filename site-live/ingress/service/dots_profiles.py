"""Profilurile DOTS (22) legate de magistrală.

Kelion alege profilul potrivit pentru cerere (determinist, după cuvinte-cheie) sau utilizatorul îl
cheamă explicit cu @nume (ex. „@reparator repară scriptul”, „@dots_ux ...”). Cererea pleacă spre
backend împreună cu instrucțiunile profilului, în faza „work”. Registrul vine din
orchestration/native_roles.json (Library index v15); nimic nu se inventează.
"""
import json
import re
from pathlib import Path

DEFAULT_PATHS = (
    Path(__file__).resolve().parents[3] / "orchestration" / "native_roles.json",
    Path("/etc/kelion-magistrala/native_roles.json"),
)

# Cuvinte-cheie → profil (primul potrivit câștigă; ordinea contează: specific înainte de general).
KEYWORDS = (
    ("dots_teste_reparatii", ("teste", "test ", "testeaza", "verifica reparatia")),
    ("dots_loguri", ("log", "loguri", "jurnal", "journalctl", "traceback")),
    ("dots_lansare", ("deploy", "lansare", "lanseaza", "publica", "release", "systemctl")),
    ("dots_defecte_git", ("istoric git", "git log", "commit", "regresie")),
    ("dots_reparator", ("repara", "bug", "eroare", "defect", "nu merge", "fix")),
    ("dots_cautare_cod", ("cauta in cod", "unde e definit", "gaseste functia", "cauta cod")),
    ("dots_harta_sectiuni_cod", ("harta codului", "lista functiilor", "sectiuni de cod")),
    ("dots_arhitectura", ("arhitectura", "design de sistem", "structura proiectului")),
    ("dots_ux", ("interfata", "ux", "ecran", "buton", "design", "pagina")),
    ("dots_verificare", ("securitate", "vulnerab", "audit", "verifica")),
    ("dots_cerinte", ("cerinte", "document", "tabel", "specificatie", "raport")),
    ("dots_memorie", ("tine minte", "noteaza", "aminteste")),
    ("dots_programare", ("cod", "script", "python", "javascript", "functie", "program")),
)


def _plain(text):
    table = str.maketrans("ăâîșşțţĂÂÎȘŞȚŢ", "aaisstt" + "AAISSTT")
    return text.translate(table).lower()


class Profiles:
    def __init__(self, roles):
        self.roles = {r["name"]: r for r in roles if r.get("name") and r.get("developer_instructions")}
        self.alias = {}
        for name, role in self.roles.items():
            for key in (name, name.removeprefix("dots_"), role.get("role", "")):
                if key:
                    self.alias[key.lower().replace("-", "_")] = name

    @classmethod
    def load(cls, path=None):
        for candidate in ([Path(path)] if path else list(DEFAULT_PATHS)):
            if candidate.is_file():
                return cls(json.loads(candidate.read_text(encoding="utf-8")).get("roles", []))
        return cls([])

    def __len__(self):
        return len(self.roles)

    def pick(self, task):
        """(profil, motiv, text_fără_adresare) sau (None, None, text)."""
        m = re.match(r"\s*@([A-Za-z_\-]+)[\s:,]+", task)
        if m:
            name = self.alias.get(m.group(1).lower().replace("-", "_"))
            if name:
                return name, "chemat explicit: @" + m.group(1), task[m.end():]
        t = _plain(task)
        for name, words in KEYWORDS:
            if name in self.roles:
                hit = next((w for w in words if w.strip() and re.search(
                    r"\b" + re.escape(w.strip()) + (r"\b" if len(w.strip()) <= 3 else ""), t)), None)
                if hit:
                    return name, "potrivire: " + hit.strip(), task
        return None, None, task

    def display(self, name):
        return (self.roles.get(name) or {}).get("display_name", name)

    def compose(self, name, task, task_id=""):
        role = self.roles[name]
        return ("[Profil DOTS: {}]\n{}\n\nphase=work\ntask_id={}\nSarcina:\n{}").format(
            role.get("display_name", name), role["developer_instructions"], task_id, task)
